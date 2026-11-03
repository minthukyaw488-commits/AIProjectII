"""
Step 4: Full integration pipeline.

    (voice or text)
         |
      STT (Whisper)            [voice input only]
         |
   +-----+------------------------------+
   |                                     |
 RAG search                     Abnormal-signal analysis
 (welfare chunks)               (sentiment + symptom repetition)
   |                                     |
   +-----------------+-------------------+
                     |
              Local LLM (Ollama)
                     |
        answer  +  (if abnormal) social-worker alert summary

Everything runs locally. Conversation content never leaves the device.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from . import config
from .abnormal_signal import AbnormalSignalDetector, SignalResult
from .alerts import AlertDispatcher
from .llm import (ANSWER_SYSTEM_PROMPT, OFF_DOMAIN_REPLY, SMALLTALK_SYSTEM_PROMPT,
                  build_answer_prompt, make_llm)
from .rag_pipeline import RagPipeline
from .router import is_smalltalk, is_off_domain


@dataclass
class TurnResult:
    question: str
    answer: str
    sources: List[str]
    signal: SignalResult
    alert: Optional[str]        # social-worker summary, only if abnormal


class WelfareAssistant:
    """One long-lived object per elderly user (keeps conversation history)."""

    def __init__(self, user_name: str = "어르신"):
        self.user_name = user_name
        self.rag = RagPipeline()
        self.rag.index()                         # build the welfare index once
        self.llm = make_llm()               # Gemini/GPT-4o (API) or Ollama fallback
        # The detector also uses the LLM to judge the conversation (정상/주의/위험),
        # with the keyword/sentiment rules as the safety net.
        self.detector = AbnormalSignalDetector(llm=self.llm)  # accumulates history
        self.alerts = AlertDispatcher()           # local log (+ opt-in channels)
        self._stt = None                          # Whisper, loaded on first use
        self.use_agent = config.USE_AGENT         # answer via tool-calling agent
        self._agent = None                        # lazily built (avoids import cycle)

    @property
    def agent(self):
        if self._agent is None:
            from .agent import WelfareAgent       # local import breaks the cycle
            self._agent = WelfareAgent(assistant=self)
        return self._agent

    # -- main entry points -------------------------------------------------
    def ask_text(self, question: str) -> TurnResult:
        # Layer 2 (abnormal signal) runs on every utterance, incl. small talk.
        signal = self.detector.add_utterance(question)

        # 1) Greetings / small talk -> warm chatbot reply, no RAG, no refusal.
        if is_smalltalk(question):
            answer = self._smalltalk_reply(question)
            return TurnResult(question, answer, [], signal, self._maybe_alert(signal))

        # 1b) Clearly off-domain (invest, pets, travel, gadgets, ...) -> refer
        #     back WITHOUT retrieval. With a large facility index almost any
        #     question finds a nearest chunk above the relevance gate, so the
        #     model would answer by twisting an unrelated facility row; skipping
        #     retrieval here removes that hallucination path entirely.
        if is_off_domain(question):
            return TurnResult(question, OFF_DOMAIN_REPLY, [], signal,
                              self._maybe_alert(signal))

        # 2) Welfare question -> the tool-calling agent decides which tools to
        #    use and (Phase 2) splits compound questions, with a deterministic
        #    fallback baked in. With USE_AGENT off, or when the local LLM is
        #    unavailable, use the classic RAG pipeline.
        if self.use_agent and self.llm.available:
            answer, sources = self.agent.run_welfare(question)
        else:
            answer, sources = self._deterministic_answer(question)

        return TurnResult(question, answer, sources, signal, self._maybe_alert(signal))

    def _deterministic_answer(self, question: str):
        """Classic RAG path: retrieve -> relevance gate -> grounded answer.
        Used when USE_AGENT is off or the LLM is unavailable."""
        retrieved = self.rag.retrieve(question)
        top_score = retrieved[0].score if retrieved else 0.0
        if not retrieved or top_score < config.RAG_MIN_RELEVANCE:
            return OFF_DOMAIN_REPLY, []               # not covered / off-topic
        contexts = [r.text for r in retrieved]
        prompt = build_answer_prompt(question, contexts)
        # 답변이 중간에 끊기지 않도록 생성 토큰 여유를 둔다(기본 130 → 256).
        answer = self.llm.generate(prompt, system=ANSWER_SYSTEM_PROMPT,
                                   num_predict=256)
        return answer, [r.source for r in retrieved]

    def _smalltalk_reply(self, question: str) -> str:
        """Warm, human reply to a greeting. Uses the LLM with a friendly persona;
        a canned line if the local LLM is unavailable."""
        if self.llm.available:
            return self.llm.generate(question, system=SMALLTALK_SYSTEM_PROMPT)
        return ("안녕하세요, 어르신. 오늘 어떻게 지내세요? 복지 관련해서 궁금하신 점을 "
                "편하게 말씀해 주세요.")

    def _maybe_alert(self, signal: SignalResult) -> Optional[str]:
        if not signal.is_abnormal:
            return None
        alert = self._build_alert(signal)
        urgency = "긴급" if (signal.crisis or signal.risk_level == "위험") else "주의"
        self.alerts.dispatch(self.user_name, urgency, alert)  # log + notify
        return alert

    def reset_conversation(self) -> None:
        """Clear the conversation history for a new session/demo.

        Reuses the already-loaded sentiment model so no reload is needed.
        """
        self.detector = AbnormalSignalDetector(
            sentiment=self.detector.sentiment, llm=self.llm)

    def transcribe(self, audio_path: str) -> str:
        """Speech-to-text only (Whisper loaded once, then cached)."""
        if self._stt is None:
            from .stt import SpeechToText
            self._stt = SpeechToText()
        return self._stt.transcribe_file(audio_path)

    def ask_audio(self, audio_path: str) -> TurnResult:
        return self.ask_text(self.transcribe(audio_path))

    # -- social-worker alert ----------------------------------------------
    def _build_alert(self, signal: SignalResult) -> str:
        """Generate a concise Korean alert summary for the 사회복지사."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        urgency = "긴급" if (signal.crisis or signal.risk_level == "위험") else "주의"
        lines = [
            f"[{urgency}] 독거노인 이상신호 알림 ({signal.risk_level}) - {self.user_name}",
            f"발생시각: {stamp}",
            f"대화 횟수: {len(self.detector.history)}회 / 평균 부정감정: "
            f"{signal.avg_negative:.2f}",
        ]
        if signal.llm_summary:
            lines.append(f"AI 요약: {signal.llm_summary}")
        lines.append("감지 근거:")
        lines += [f"  - {r}" for r in signal.reasons]
        if signal.symptom_counts:
            top = ", ".join(f"{k}({v}회)" for k, v in signal.symptom_counts.items())
            lines.append(f"반복 호소 증상: {top}")
        m = signal.metrics
        if m:
            lines.append(
                f"이상징후 지표(최근 vs 평소): 대화빈도 -{m['freq_drop']:.0%}, "
                f"감정 +{m['sentiment_shift']:.2f}, 외로움표현 +{m['keyword_shift']:.0%}, "
                f"응답길이 -{m['length_drop']:.0%}")
        recent = self.detector.history[-3:]
        lines.append("최근 발화: " + " / ".join(f'"{u}"' for u in recent))
        action = ("자살예방상담(109) 연계 및 즉시 방문 확인 권장"
                  if signal.crisis else "안부 확인 방문 또는 상담 권장")
        lines.append(f"권장 조치: {action}")
        return "\n".join(lines)


if __name__ == "__main__":
    print("Initialising assistant (indexing welfare docs)...\n")
    bot = WelfareAssistant(user_name="김OO 어르신")
    print(f"RAG={bot.rag.backend}/{bot.rag.embedder.backend} | "
          f"LLM={type(bot.llm).__name__}:{bot.llm.model}"
          f"({'on' if bot.llm.available else 'off (fallback)'}) | "
          f"sentiment={bot.detector.sentiment.backend}\n")

    conversation = [
        "기초연금은 어떻게 신청하나요?",
        "무릎이 아픈데 도움받을 수 있는 곳이 있나요?",
        "요즘 무릎도 아프고 잠도 안 와요.",
        "무릎이 계속 아프고 혼자라 너무 외롭고 우울해요.",
    ]
    for q in conversation:
        res = bot.ask_text(q)
        print("=" * 70)
        print(f"👵 질문: {res.question}")
        print(f"🤖 답변: {res.answer[:220]}")
        print(f"   📄 근거: {res.sources}")
        if res.alert:
            print("\n🚨 사회복지사 알림 -----------------------------")
            print(res.alert)
        print()
