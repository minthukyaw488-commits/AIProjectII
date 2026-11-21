"""
Step 3: Abnormal-signal detection layer.

Two independent signals are combined by simple rule-based thresholds:

  (A) Sentiment  - negative emotion probability per utterance, averaged over
                   the recent conversation. Primary backend is a public Korean
                   sentiment model from Hugging Face (no auth needed); a local
                   lexicon fallback keeps it working offline.
  (B) Symptom repetition - the same physical/emotional complaint mentioned
                   >= N times across the conversation history.

If either threshold is crossed (or a crisis keyword appears), an abnormal
signal is raised and a summary is generated for the social worker (사회복지사).

All processing is local. Conversation content never leaves the device.
"""
from __future__ import annotations
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import config
from .crisis import is_crisis


# Risk levels, lowest to highest, so two assessments can be combined by severity.
RISK_ORDER = {"정상": 0, "주의": 1, "위험": 2}


def _max_risk(a: str, b: str) -> str:
    return a if RISK_ORDER.get(a, 0) >= RISK_ORDER.get(b, 0) else b


# --------------------------------------------------------------------------
# (A) Sentiment analysis
# --------------------------------------------------------------------------
# Local lexicon fallback: negative / positive Korean cue words. Rough, but
# lets the abnormal-signal logic run and be tested without a model download.
_NEG_WORDS = ["아프", "힘들", "외로", "혼자", "쓸쓸", "우울", "슬프", "죽고 싶",
              "살기 싫", "못 자", "잠이 안", "입맛이 없", "답답", "숨이 차",
              "어지러", "무섭", "불안", "지치", "의욕이 없", "희망이 없", "싫"]
_POS_WORDS = ["좋", "행복", "고맙", "감사", "괜찮", "즐겁", "기쁘", "편안",
              "든든", "다행"]


class SentimentAnalyzer:
    def __init__(self, model_name: str = config.SENTIMENT_MODEL):
        self.model_name = model_name
        self.backend = "fallback-lexicon"
        self._pipe = None
        try:
            from transformers import pipeline
            # device=-1 forces CPU. On Apple Silicon the MPS backend crashes
            # (bus error) when run from Streamlit's worker thread; CPU avoids it.
            self._pipe = pipeline("sentiment-analysis", model=model_name, device=-1)
            self.backend = f"transformers:{model_name}"
        except Exception as exc:
            print(f"[sentiment] model unavailable ({exc.__class__.__name__}); "
                  f"using local Korean lexicon fallback.")

    def negative_score(self, text: str) -> float:
        """Return probability that `text` is negative, in [0, 1].

        The sentiment model is binary and has no neutral class, so plain
        info-seeking questions can score as strongly negative. To avoid false
        alarms we only trust a high negative score when the utterance actually
        contains an emotional/distress cue word; otherwise it is capped at
        neutral (0.5).
        """
        if self._pipe is not None:
            res = self._pipe(text[:512])[0]
            label = res["label"].lower()
            score = float(res["score"])
            # Map various label schemes to a negative probability.
            if any(k in label for k in ("neg", "label_0", "1 star", "부정")):
                neg = score
            elif any(k in label for k in ("pos", "label_1", "5 star", "긍정")):
                neg = 1.0 - score
            else:
                neg = 0.5
        else:
            neg = self._lexicon_score(text)

        # Emotional-cue gate: no distress word -> treat as neutral, not negative.
        if not self._has_negative_cue(text):
            return min(neg, 0.5)
        return neg

    @staticmethod
    def _has_negative_cue(text: str) -> bool:
        return any(w in text for w in _NEG_WORDS)

    @staticmethod
    def _lexicon_score(text: str) -> float:
        neg = sum(text.count(w) for w in _NEG_WORDS)
        pos = sum(text.count(w) for w in _POS_WORDS)
        if neg == 0 and pos == 0:
            return 0.5                      # neutral
        return neg / (neg + pos)


# --------------------------------------------------------------------------
# (B) Symptom keyword tracking + combined decision
# --------------------------------------------------------------------------
@dataclass
class _Utterance:
    """One recorded utterance with the features anomaly detection needs."""
    ts: float          # unix timestamp
    text: str
    neg: float         # negative-sentiment probability [0,1]
    length: int        # character length (engagement proxy)
    emotion: bool      # contains a loneliness/sadness keyword


@dataclass
class SignalResult:
    is_abnormal: bool
    reasons: List[str]
    avg_negative: float
    symptom_counts: Dict[str, int]
    crisis: bool = False
    # Quantified baseline-vs-recent anomaly metrics (empty until enough history).
    metrics: Dict[str, float] = field(default_factory=dict)
    # Three-level severity ("정상" / "주의" / "위험"), combining rules + LLM judge.
    risk_level: str = "정상"
    # Filled when the LLM conversation judge runs (empty otherwise).
    llm_reason: str = ""
    llm_summary: str = ""


# --------------------------------------------------------------------------
# (C) LLM conversation judge
# --------------------------------------------------------------------------
_JUDGE_SYSTEM = (
    "당신은 독거노인 돌봄 서비스의 안전 모니터입니다. 어르신의 최근 대화를 읽고 "
    "위험 신호를 평가합니다. 단순한 정보 질문이나 일상 인사는 '정상'입니다. "
    "우울·외로움·고립, 건강 악화 호소가 반복되면 '주의', 자살·자해 암시나 "
    "즉시 도움이 필요한 위기 표현은 '위험'으로 판단합니다. 과잉 경보는 피하되 "
    "위기 신호는 절대 놓치지 마세요. 반드시 한국어로 판단합니다."
)


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first {...} object out of an LLM reply (tolerates code fences)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


class LLMRiskJudge:
    """Reads the recent conversation with the LLM and rates the risk level.

    Returns {"risk", "reason", "summary"} or None on any failure, so the
    rule-based detector always remains the safety net.
    """

    def __init__(self, llm):
        self.llm = llm

    def assess(self, history: List[str]) -> Optional[dict]:
        if not history or self.llm is None or not getattr(self.llm, "available", False):
            return None
        convo = "\n".join(f"어르신: {u}" for u in history[-8:])
        prompt = (
            "다음은 독거노인 어르신의 최근 대화입니다.\n\n"
            f"{convo}\n\n"
            "이 대화에 위험 신호가 있는지 평가하세요. 아래 JSON 형식으로만 답하세요 "
            "(설명 없이):\n"
            '{"risk": "정상|주의|위험", "reason": "판단 근거 한 문장", '
            '"summary": "사회복지사를 위한 한 문장 요약"}'
        )
        try:
            raw = self.llm.generate(prompt, system=_JUDGE_SYSTEM,
                                    num_predict=200, temperature=0.1)
            data = _extract_json(raw)
            if not data:
                return None
            risk = str(data.get("risk", "")).strip()
            if risk not in RISK_ORDER:
                return None
            return {
                "risk": risk,
                "reason": str(data.get("reason", "")).strip(),
                "summary": str(data.get("summary", "")).strip(),
            }
        except Exception:
            return None


@dataclass
class AbnormalSignalDetector:
    """Tracks a running conversation and decides when to alert a social worker.

    Two families of signals are combined:
      - Immediate rules   : symptom repetition, sustained negativity, crisis words.
      - Anomaly (baseline) : deviation of a RECENT window from the person's own
                             BASELINE window, quantified as four metrics
                             (frequency drop, sentiment shift, keyword shift,
                             response-length drop).
    """

    sentiment: SentimentAnalyzer = field(default_factory=SentimentAnalyzer)
    repeat_threshold: int = config.SYMPTOM_REPEAT_THRESHOLD
    neg_threshold: float = config.NEGATIVE_SENTIMENT_THRESHOLD
    sentiment_min_utterances: int = config.SENTIMENT_MIN_UTTERANCES
    # Optional LLM (GeminiLLM/OpenAILLM) that judges the conversation as a whole.
    # None -> rules only; the LLM judge is an additive signal, never required.
    llm: object = None
    use_llm: bool = config.USE_LLM_SIGNAL

    history: List[str] = field(default_factory=list)
    _neg_scores: List[float] = field(default_factory=list)
    _symptom_counts: Counter = field(default_factory=Counter)
    _records: List[_Utterance] = field(default_factory=list)
    _judge: Optional["LLMRiskJudge"] = field(default=None, repr=False)

    def __post_init__(self):
        if self.llm is not None and self.use_llm:
            self._judge = LLMRiskJudge(self.llm)

    def add_utterance(self, text: str, timestamp: Optional[float] = None) -> SignalResult:
        """Record one elderly utterance and re-evaluate the abnormal signal.

        `timestamp` (unix seconds) can be supplied to replay historical data;
        it defaults to now.
        """
        ts = timestamp if timestamp is not None else time.time()
        neg = self.sentiment.negative_score(text)

        self.history.append(text)
        self._neg_scores.append(neg)
        self._records.append(_Utterance(
            ts=ts, text=text, neg=neg, length=len(text.strip()),
            emotion=any(k in text for k in config.EMOTION_KEYWORDS)))

        # Count symptom groups mentioned in this utterance (once per group).
        for group, variants in config.SYMPTOM_KEYWORDS.items():
            if any(v in text for v in variants):
                self._symptom_counts[group] += 1

        return self.evaluate(now=ts)

    def evaluate(self, now: Optional[float] = None) -> SignalResult:
        reasons: List[str] = []

        # --- Immediate rules ---------------------------------------------
        avg_neg = (sum(self._neg_scores) / len(self._neg_scores)
                   if self._neg_scores else 0.0)
        if (len(self._neg_scores) >= self.sentiment_min_utterances
                and avg_neg >= self.neg_threshold):
            reasons.append(f"부정 감정 평균 {avg_neg:.2f} (기준 {self.neg_threshold})")

        for g, c in self._symptom_counts.items():
            if c >= self.repeat_threshold:
                reasons.append(f"'{g}' 관련 호소 {c}회 반복 (기준 {self.repeat_threshold})")

        # 위기 표현: 공용 기준(src/crisis.py, 띄어쓰기 무시). config.CRISIS_KEYWORDS 4개는
        # crisis.CRISIS_PATTERNS 에 모두 들어 있어 따로 보지 않는다(따로 보면 '혼자살면' 안의
        # '자살' 같은 오탐을 crisis.py 의 보정 없이 다시 잡게 됨).
        crisis = any(is_crisis(h) for h in self.history)
        if crisis:
            reasons.append("위기 신호 키워드 감지 (즉시 확인 필요)")

        # --- Anomaly (baseline-vs-recent) metrics ------------------------
        metrics, anomaly_reasons = self._baseline_metrics(
            now if now is not None else time.time())
        reasons.extend(anomaly_reasons)

        # --- Rule-based severity -----------------------------------------
        rule_risk = "위험" if crisis else ("주의" if reasons else "정상")

        # --- LLM conversation judge (additive) ---------------------------
        final_risk = rule_risk
        llm_reason = llm_summary = ""
        if self._judge is not None:
            assessment = self._judge.assess(self.history)
            if assessment:
                llm_reason = assessment["reason"]
                llm_summary = assessment["summary"]
                final_risk = _max_risk(final_risk, assessment["risk"])
                if assessment["risk"] != "정상" and llm_reason:
                    reasons.append(f"AI 대화 판단({assessment['risk']}): {llm_reason}")
        # A crisis keyword always forces the highest level, regardless of the LLM.
        if crisis:
            final_risk = "위험"

        return SignalResult(
            is_abnormal=(final_risk != "정상"),
            reasons=reasons,
            avg_negative=avg_neg,
            symptom_counts=dict(self._symptom_counts),
            crisis=crisis,
            metrics=metrics,
            risk_level=final_risk,
            llm_reason=llm_reason,
            llm_summary=llm_summary,
        )

    def _baseline_metrics(self, now: float):
        """Compare a recent window to a baseline window. Returns (metrics, reasons).

        Metrics (each a plain number the report can cite):
          freq_drop       : 1 - recent_rate/baseline_rate     (conversation frequency)
          sentiment_shift : recent_neg_avg - baseline_neg_avg (mood worsening)
          keyword_shift   : recent_emotion_rate - baseline_emotion_rate
          length_drop     : 1 - recent_len/baseline_len       (disengagement)
        """
        recent_cut = now - config.RECENT_WINDOW_DAYS * 86400
        baseline_cut = now - config.BASELINE_WINDOW_DAYS * 86400
        recent = [r for r in self._records if r.ts >= recent_cut]
        baseline = [r for r in self._records if baseline_cut <= r.ts < recent_cut]

        # Need enough baseline history and some recent activity to compare.
        if len(baseline) < config.MIN_BASELINE_UTTERANCES or not recent:
            return {}, []

        def mean(vals):
            return sum(vals) / len(vals) if vals else 0.0

        baseline_days = max(config.BASELINE_WINDOW_DAYS - config.RECENT_WINDOW_DAYS, 1)
        base_rate = len(baseline) / baseline_days
        recent_rate = len(recent) / config.RECENT_WINDOW_DAYS

        freq_drop = max(0.0, 1 - recent_rate / base_rate) if base_rate else 0.0
        sentiment_shift = mean([r.neg for r in recent]) - mean([r.neg for r in baseline])
        keyword_shift = mean([r.emotion for r in recent]) - mean([r.emotion for r in baseline])
        base_len = mean([r.length for r in baseline])
        length_drop = max(0.0, 1 - mean([r.length for r in recent]) / base_len) if base_len else 0.0

        metrics = {
            "freq_drop": round(freq_drop, 3),
            "sentiment_shift": round(sentiment_shift, 3),
            "keyword_shift": round(keyword_shift, 3),
            "length_drop": round(length_drop, 3),
            "baseline_n": len(baseline),
            "recent_n": len(recent),
        }

        reasons = []
        if freq_drop >= config.FREQ_DROP_THRESHOLD:
            reasons.append(f"대화 빈도 {freq_drop:.0%} 감소 (기준 {config.FREQ_DROP_THRESHOLD:.0%})")
        if sentiment_shift >= config.SENTIMENT_SHIFT_THRESHOLD:
            reasons.append(f"부정 감정 +{sentiment_shift:.2f} 상승 (기준 +{config.SENTIMENT_SHIFT_THRESHOLD})")
        if keyword_shift >= config.KEYWORD_SHIFT_THRESHOLD:
            reasons.append(f"외로움·우울 표현 +{keyword_shift:.0%} 증가 (기준 +{config.KEYWORD_SHIFT_THRESHOLD:.0%})")
        if length_drop >= config.LENGTH_DROP_THRESHOLD:
            reasons.append(f"응답 길이 {length_drop:.0%} 감소 (기준 {config.LENGTH_DROP_THRESHOLD:.0%})")
        return metrics, reasons


if __name__ == "__main__":
    det = AbnormalSignalDetector()
    print("sentiment backend:", det.sentiment.backend, "\n")
    convo = [
        "안녕하세요, 오늘 날씨가 좋네요.",
        "요즘 무릎이 너무 아파요.",
        "어제도 무릎이 아파서 잠을 못 잤어요.",
        "무릎도 아프고 혼자 있으니 너무 외롭고 우울해요.",
    ]
    for utt in convo:
        res = det.add_utterance(utt)
        flag = "🚨 ABNORMAL" if res.is_abnormal else "정상"
        print(f"- {utt}\n    avg_neg={res.avg_negative:.2f} symptoms={res.symptom_counts} -> {flag}")
    print("\nfinal reasons:", det.evaluate().reasons)
