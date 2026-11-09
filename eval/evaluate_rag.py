"""
RAGAS 방식 RAG 평가 모듈 — 검색 + 생성 4대 지표 + CSV/MD 리포트.

검증 기준(교수님 체크리스트)에 맞춰 설계:
  1) 데이터셋: question / contexts / ground_truth / answer 4개 컬럼을 구성
     - 일반 복지 질의 + 엣지 케이스(범위 밖·응급/정신건강)를 함께 포함
  2) 지표:
     - 검색: Context Precision, Context Recall
     - 생성: Faithfulness, Answer Relevance
  3) 산출물: eval/eval_results.csv(샘플별 점수) + eval/eval_report.md(요약)
             + eval/eval_dataset.jsonl(4컬럼 데이터셋)

정답지(ground truth)는 data/eval/ground_truth_rag.jsonl 을 사용한다.
심판(judge)과 답변 생성은 로컬 LLM(config.LLM_BACKEND, 기본 EXAONE)을 그대로 쓴다.

실행(모델이 있는 Mac/서버에서):
  LLM_BACKEND=ollama python eval/evaluate_rag.py
  EVAL_PER_TOPIC=3 EVAL_OUT=8 python eval/evaluate_rag.py   # 표본 크기 조절

구조 점검(모델 없이 — 합성 스텁):
  EVAL_SELFTEST=1 python eval/evaluate_rag.py
"""
from __future__ import annotations
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ.setdefault("USE_AGENT", "0")        # 결정형 RAG 경로
os.environ.setdefault("USE_LLM_SIGNAL", "0")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLD = ROOT / "data" / "eval" / "ground_truth_rag.jsonl"
OUT_DIR = ROOT / "eval"
SELFTEST = os.environ.get("EVAL_SELFTEST") not in (None, "", "0")
PER_TOPIC = int(os.environ.get("EVAL_PER_TOPIC", "2"))
N_OUT = int(os.environ.get("EVAL_OUT", "5"))


# --------------------------------------------------------------------------
# 데이터셋 구성(일반 + 엣지)
# --------------------------------------------------------------------------
def load_dataset():
    rows = [json.loads(l) for l in GOLD.open(encoding="utf-8") if l.strip()]
    in_by_topic = defaultdict(list)
    out_rows = []
    for r in rows:
        if r["scope"] == "in":
            in_by_topic[r["topic"]].append(r)
        else:
            out_rows.append(r)
    sample = []
    for topic, rs in in_by_topic.items():          # 주제별 N개(응급·정신건강 포함)
        sample.extend(rs[:PER_TOPIC])
    sample.extend(out_rows[:N_OUT])                # 엣지 케이스(범위 밖)
    return sample


# --------------------------------------------------------------------------
# 파이프라인(실제 모델) 또는 스텁(구조 점검)
# --------------------------------------------------------------------------
class _StubLLM:
    model = "selftest-stub"
    available = True

    def generate(self, prompt, system="", **kw):
        p = prompt + " " + system
        if "예" in system and "아니오" in system:      # judge 호출
            # 자료/답변에 질문 토큰이 있으면 '예'
            import re
            toks = [t for t in re.findall(r"[가-힣]{2,}", prompt)][:3]
            return "예" if any(t in prompt[prompt.find("[자료]"):] for t in toks) else "예"
        return "주민센터에서 신청하실 수 있습니다. 65세 이상이면 대상입니다."


class _StubRetrieved:
    def __init__(self, text, source="stub.pdf", score=0.5):
        self.text, self.source, self.score = text, source, score


def _stub_retrieve(q, top_k=3, gold=None):
    kw = (gold or {}).get("gold_keyword") or ""
    facts = (gold or {}).get("facts") or []
    # 약 70%는 근거 포함, 일부 주제는 비워 '낮은 검색'을 재현
    if gold and gold.get("topic") in ("에너지바우처", "정신건강"):
        return [_StubRetrieved("관련 없는 일반 안내 문단입니다.", score=0.2)]
    body = f"{kw} 관련 안내. " + " ".join(facts[:3])
    return [_StubRetrieved(body, score=0.6),
            _StubRetrieved(f"{facts[0] if facts else ''} 추가 설명", score=0.5),
            _StubRetrieved("부가적인 일반 문단", score=0.3)][:top_k]


def get_pipeline():
    """(retrieve_fn, generate_answer_fn, judge_llm, gate, off_reply, is_off_domain)."""
    if SELFTEST:
        llm = _StubLLM()
        def retrieve(q, gold=None):
            return _stub_retrieve(q, gold=gold)
        def gen(q, contexts):
            return llm.generate(f"[질문]{q}")
        return retrieve, gen, llm, 0.25, "주민센터에 문의해 주세요.", (lambda q: False)

    from src import config
    from src.llm import (ANSWER_SYSTEM_PROMPT, OFF_DOMAIN_REPLY,
                         build_answer_prompt, make_llm)
    from src.rag_pipeline import RagPipeline
    from src.router import is_off_domain

    rag = RagPipeline()
    rag.index()
    llm = make_llm()
    print(f"RAG     : {rag.backend} / {rag.embedder.backend}")
    print(f"심판/생성 LLM: {type(llm).__name__}:{llm.model} "
          f"({'ON' if llm.available else 'OFF'})\n")

    def retrieve(q, gold=None):
        return rag.retrieve(q)

    def gen(q, contexts):
        return (llm.generate(build_answer_prompt(q, contexts),
                             system=ANSWER_SYSTEM_PROMPT) or "").strip()

    return retrieve, gen, llm, config.RAG_MIN_RELEVANCE, OFF_DOMAIN_REPLY, is_off_domain


# --------------------------------------------------------------------------
# LLM 심판 지표
# --------------------------------------------------------------------------
def _judge_yes(llm, prompt):
    r = (llm.generate(prompt, system="당신은 꼼꼼한 평가자입니다. '예' 또는 "
                      "'아니오' 한 단어로만 답하세요.") or "").strip()
    head = r.replace(" ", "")[:6]
    return ("예" in head) and ("아니오" not in head)


def context_precision(llm, q, contexts):
    """검색 조각 중 질문과 관련 있는 비율(노이즈 적을수록 ↑)."""
    if not contexts:
        return 0.0
    hit = 0
    for c in contexts:
        hit += int(_judge_yes(llm, f"[질문] {q}\n\n[자료]\n{c[:600]}\n\n"
                              "이 자료가 질문에 답하는 데 관련 있습니까? '예'/'아니오'."))
    return hit / len(contexts)


def context_recall(facts, contexts):
    """정답에 필요한 핵심 사실이 검색 자료에 들어왔는가(누락 적을수록 ↑).
    정답지의 gold facts 중 자료에 나타난 비율(결정형·재현 가능)."""
    if not facts:
        return None
    joined = " ".join(contexts)
    found = sum(1 for f in facts if f in joined)
    return found / len(facts)


def faithfulness(llm, answer, contexts):
    """답변이 자료에만 근거하는가(환각 없을수록 ↑)."""
    if not contexts or not answer:
        return None
    ctx = "\n\n".join(c[:500] for c in contexts)
    return int(_judge_yes(llm, f"[자료]\n{ctx}\n\n[답변]\n{answer}\n\n"
                          "답변의 모든 내용이 자료에 근거합니까? 지어냈으면 '아니오'."))


def answer_relevance(llm, q, answer):
    """답변이 질문에 실제로 답하는가(정합성 높을수록 ↑)."""
    if not answer:
        return None
    return int(_judge_yes(llm, f"[질문] {q}\n\n[답변] {answer}\n\n"
                          "이 답변이 질문에 적절히 답합니까? '예'/'아니오'."))


# --------------------------------------------------------------------------
# 평가 루프
# --------------------------------------------------------------------------
def run():
    OUT_DIR.mkdir(exist_ok=True)
    data = load_dataset()
    retrieve, gen, llm, gate, off_reply, is_off = get_pipeline()
    print(f"표본: {len(data)}개 "
          f"(일반 {sum(1 for r in data if r['scope']=='in')} / "
          f"엣지(범위밖) {sum(1 for r in data if r['scope']=='out')})"
          + ("   [SELFTEST — 합성 스텁]" if SELFTEST else "") + "\n")

    records, dataset = [], []
    for i, r in enumerate(data, 1):
        q = r["q"]
        gtruth = r.get("gold_answer", "")
        facts = r.get("facts", [])
        edge = r["scope"] == "out"

        if edge and is_off(q):
            contexts, answer, refused = [], off_reply, True
        else:
            retrieved = retrieve(q, gold=r)
            top = retrieved[0].score if retrieved else 0.0
            contexts = [x.text for x in retrieved]
            if not retrieved or top < gate:
                answer, refused = off_reply, True
                contexts = [] if top < gate else contexts
            else:
                answer, refused = gen(q, contexts), False

        # 4대 지표 (엣지/거절은 생성 지표 N/A — 거절 자체가 정답)
        if edge:
            cp = cr = faith = ar = None
        else:
            cp = context_precision(llm, q, contexts)
            cr = context_recall(facts, contexts)
            faith = None if refused else faithfulness(llm, answer, contexts)
            ar = None if refused else answer_relevance(llm, q, answer)

        rec = {"id": i, "scope": r["scope"], "topic": r["topic"], "question": q,
               "context_precision": cp, "context_recall": cr,
               "faithfulness": faith, "answer_relevance": ar,
               "refused": int(refused), "answer": answer[:160],
               "ground_truth": gtruth}
        records.append(rec)
        dataset.append({"question": q, "contexts": contexts,
                        "ground_truth": gtruth, "answer": answer})
        tag = "EDGE" if edge else r["topic"]
        print(f"[{i:2}/{len(data)}] {tag:<10} cp={_fmt(cp)} cr={_fmt(cr)} "
              f"faith={_fmt(faith)} ar={_fmt(ar)} {'(거절)' if refused else ''}")

    _write_outputs(records, dataset)
    return records


def _fmt(x):
    return "  -" if x is None else f"{x:.2f}"


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# --------------------------------------------------------------------------
# 산출물: CSV + dataset.jsonl + report.md
# --------------------------------------------------------------------------
def _write_outputs(records, dataset):
    # 1) 샘플별 점수 CSV
    csv_path = OUT_DIR / "eval_results.csv"
    cols = ["id", "scope", "topic", "question", "context_precision",
            "context_recall", "faithfulness", "answer_relevance",
            "refused", "answer", "ground_truth"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            w.writerow(r)

    # 2) 4컬럼 데이터셋
    ds_path = OUT_DIR / "eval_dataset.jsonl"
    with ds_path.open("w", encoding="utf-8") as f:
        for d in dataset:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # 3) 평균 + 약점
    ins = [r for r in records if r["scope"] == "in"]
    outs = [r for r in records if r["scope"] == "out"]
    avg = {
        "context_precision": _avg([r["context_precision"] for r in ins]),
        "context_recall": _avg([r["context_recall"] for r in ins]),
        "faithfulness": _avg([r["faithfulness"] for r in ins]),
        "answer_relevance": _avg([r["answer_relevance"] for r in ins]),
    }
    refuse_rate = (_avg([r["refused"] for r in outs]) if outs else None)
    # 주제별 recall(검색 누락 진단)
    topic_recall = defaultdict(list)
    for r in ins:
        if r["context_recall"] is not None:
            topic_recall[r["topic"]].append(r["context_recall"])
    weak_topics = sorted((t for t, v in topic_recall.items()
                          if (sum(v) / len(v)) < 0.5),
                         key=lambda t: sum(topic_recall[t]) / len(topic_recall[t]))

    weaks = []
    if (avg["context_precision"] or 1) < 0.7:
        weaks.append("Context Precision 낮음 → 검색 노이즈 많음(관련 없는 조각이 섞임).")
    if (avg["context_recall"] or 1) < 0.7:
        weaks.append("Context Recall 낮음 → 정답 근거 누락(일부 주제는 코퍼스 공백 가능).")
    if (avg["faithfulness"] or 1) < 0.9:
        weaks.append("Faithfulness 낮음 → 자료에 없는 내용을 지어낼 위험(환각).")
    if (avg["answer_relevance"] or 1) < 0.8:
        weaks.append("Answer Relevance 낮음 → 질문과 답변의 정합성 부족.")
    if weak_topics:
        weaks.append("검색 약한 주제: " + ", ".join(weak_topics)
                     + " (근거 문서 보강 또는 소관 외 명시 필요).")
    if not weaks:
        weaks.append("임계치 기준 두드러진 약점 없음.")

    md = OUT_DIR / "eval_report.md"
    lines = [
        "# RAG 평가 리포트 (RAGAS 방식)", "",
        f"- 생성 시각: {datetime.now():%Y-%m-%d %H:%M}",
        f"- 모드: {'SELFTEST(합성 스텁 — 숫자는 구조 점검용)' if SELFTEST else '실제 모델'}",
        f"- 표본: {len(records)}개 (일반 {len(ins)} / 엣지 {len(outs)})", "",
        "## 평균 지표 (일반 질의)", "",
        "| 축 | 지표 | 평균 |", "|---|---|---|",
        f"| 검색 | Context Precision | {_pct(avg['context_precision'])} |",
        f"| 검색 | Context Recall | {_pct(avg['context_recall'])} |",
        f"| 생성 | Faithfulness | {_pct(avg['faithfulness'])} |",
        f"| 생성 | Answer Relevance | {_pct(avg['answer_relevance'])} |", "",
        f"**엣지(범위 밖) 거절률: {_pct(refuse_rate)}**  "
        "(복지 무관 질문을 지어내지 않고 거절한 비율)", "",
        "## 식별된 약점", "",
    ]
    lines += [f"- {w}" for w in weaks]
    lines += ["", "## 산출물",
              "- `eval/eval_results.csv` — 샘플별 점수",
              "- `eval/eval_dataset.jsonl` — question/contexts/ground_truth/answer",
              "- `eval/eval_report.md` — 이 요약", ""]
    md.write_text("\n".join(lines), encoding="utf-8")

    # 콘솔 요약
    print("\n" + "=" * 60)
    print(" 평균 지표 (일반 질의)")
    print("=" * 60)
    print(f"  Context Precision : {_pct(avg['context_precision'])}")
    print(f"  Context Recall    : {_pct(avg['context_recall'])}")
    print(f"  Faithfulness      : {_pct(avg['faithfulness'])}")
    print(f"  Answer Relevance  : {_pct(avg['answer_relevance'])}")
    print(f"  엣지 거절률       : {_pct(refuse_rate)}")
    print("\n  약점:")
    for w in weaks:
        print(f"   - {w}")
    print(f"\n  → 저장: {csv_path.name}, eval_dataset.jsonl, {md.name} (eval/ 아래)")


def _pct(x):
    return "N/A" if x is None else f"{x:.0%}"


if __name__ == "__main__":
    run()
