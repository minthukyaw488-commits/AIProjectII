"""
정답지(ground truth) 기반 정량 평가 — RAG 검색 + 이상신호 감지.

make_ground_truth.py 가 만든 '사람이 정한 정답'(data/eval/ground_truth_*.jsonl)을
기준으로 시스템 출력을 비교해 보고서용 숫자를 뽑는다.

  1) RAG 검색  : 질문에 대해 올바른 근거가 상위 k개 안에 검색됐는가
                 - Hit@1 / Hit@3 (전체 + 주제별)
                 - 범위 밖(out) 질문은 '관련성 게이트 아래로 떨어뜨렸는가'(거절 지표)
  2) 이상신호  : 대화의 위험도(정상/주의/위험)를 맞혔는가
                 - 3단계 혼동행렬 + 클래스별 Precision/Recall/F1
                 - 이진(이상 여부) Precision/Recall/F1
                 - ★ '위험' Recall (놓치면 사람이 위험 — 가장 중요한 지표)

전부 로컬에서 동작. 기본은 재현성을 위해 규칙 기반 신호(USE_LLM_SIGNAL=0)로 측정.

실행:
  python eval_ground_truth.py                 # 검색 + 신호(규칙 기반)
  USE_LLM_SIGNAL=1 python eval_ground_truth.py  # 신호에 LLM 심판까지 사용
"""
from __future__ import annotations
import json
import os
from collections import defaultdict
from pathlib import Path

# 재현성: 신호는 규칙 기반이 기본(원하면 USE_LLM_SIGNAL=1), 검색은 결정형 경로.
os.environ.setdefault("USE_LLM_SIGNAL", "0")
os.environ.setdefault("USE_AGENT", "0")

from src import config  # noqa: E402
from src.abnormal_signal import AbnormalSignalDetector, SentimentAnalyzer  # noqa: E402
from src.rag_pipeline import RagPipeline  # noqa: E402

EVAL_DIR = Path("data/eval")
LEVELS = ["정상", "주의", "위험"]


def _load(name):
    path = EVAL_DIR / name
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --------------------------------------------------------------------------
# 1) RAG 검색 평가
# --------------------------------------------------------------------------
def evaluate_rag(rag: RagPipeline, rows) -> dict:
    in_rows = [r for r in rows if r["scope"] == "in"]
    out_rows = [r for r in rows if r["scope"] == "out"]

    hit1 = hit3 = 0
    per_topic = defaultdict(lambda: [0, 0, 0])   # topic -> [hit1, hit3, n]
    for r in in_rows:
        kw = r["gold_keyword"]
        results = rag.retrieve(r["q"], top_k=3)
        texts = [x.text for x in results]
        h1 = bool(texts) and kw in texts[0]
        h3 = any(kw in t for t in texts)
        hit1 += h1
        hit3 += h3
        t = per_topic[r["topic"]]
        t[0] += h1
        t[1] += h3
        t[2] += 1

    # 범위 밖(out): 최상위 점수가 관련성 게이트 아래면 '덮어쓰지 않고 거절' = 정답
    gate = config.RAG_MIN_RELEVANCE
    refused = 0
    for r in out_rows:
        results = rag.retrieve(r["q"], top_k=3)
        top = results[0].score if results else 0.0
        if top < gate:
            refused += 1

    n_in = len(in_rows)
    n_out = len(out_rows)
    return {
        "n_in": n_in, "n_out": n_out,
        "hit1": hit1, "hit3": hit3,
        "hit1_rate": hit1 / n_in if n_in else 0.0,
        "hit3_rate": hit3 / n_in if n_in else 0.0,
        "refused": refused,
        "refuse_rate": refused / n_out if n_out else 0.0,
        "gate": gate,
        "per_topic": {k: {"hit1": v[0], "hit3": v[1], "n": v[2],
                          "hit3_rate": v[1] / v[2] if v[2] else 0.0}
                      for k, v in per_topic.items()},
    }


# --------------------------------------------------------------------------
# 2) 이상신호 평가 (3단계 + 이진)
# --------------------------------------------------------------------------
def _prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def evaluate_signal(rows) -> dict:
    shared = SentimentAnalyzer()                     # 모델 1회만 로드
    # 혼동행렬: confusion[gold][pred]
    confusion = {g: {p: 0 for p in LEVELS} for g in LEVELS}
    bin_tp = bin_tn = bin_fp = bin_fn = 0
    details = []
    for row in rows:
        det = AbnormalSignalDetector(sentiment=shared)   # 대화마다 히스토리 초기화
        res = None
        for u in row["utterances"]:
            res = det.add_utterance(u)
        gold = row["label"]
        pred = res.risk_level
        confusion[gold][pred] += 1
        # 이진(이상 여부)
        g_ab = row["abnormal"]
        p_ab = res.is_abnormal
        if g_ab and p_ab:
            bin_tp += 1
        elif g_ab and not p_ab:
            bin_fn += 1
        elif not g_ab and p_ab:
            bin_fp += 1
        else:
            bin_tn += 1
        details.append({"gold": gold, "pred": pred, "note": row["note"],
                        "last": row["utterances"][-1]})

    n = len(rows)
    correct = sum(confusion[l][l] for l in LEVELS)
    # 클래스별 P/R/F1
    per_class = {}
    for l in LEVELS:
        tp = confusion[l][l]
        fp = sum(confusion[g][l] for g in LEVELS if g != l)
        fn = sum(confusion[l][p] for p in LEVELS if p != l)
        p, r, f = _prf(tp, fp, fn)
        per_class[l] = {"precision": p, "recall": r, "f1": f,
                        "support": sum(confusion[l].values())}
    bp, br, bf = _prf(bin_tp, bin_fp, bin_fn)
    return {
        "n": n,
        "accuracy3": correct / n if n else 0.0,
        "confusion": confusion,
        "per_class": per_class,
        "danger_recall": per_class["위험"]["recall"],   # ★ 핵심 안전 지표
        "binary": {"tp": bin_tp, "tn": bin_tn, "fp": bin_fp, "fn": bin_fn,
                   "precision": bp, "recall": br, "f1": bf,
                   "accuracy": (bin_tp + bin_tn) / n if n else 0.0},
        "details": details,
    }


# --------------------------------------------------------------------------
# 리포트
# --------------------------------------------------------------------------
def main():
    rag_rows = _load("ground_truth_rag.jsonl")
    sig_rows = _load("ground_truth_signal.jsonl")

    print("정답지 로드:")
    print(f"  RAG    {len(rag_rows)}문항  |  신호 {len(sig_rows)}대화")
    print("파이프라인 로딩(복지 문서 색인)...\n")
    rag = RagPipeline()
    rag.index()
    print(f"RAG backend: {rag.backend} / {rag.embedder.backend}\n")

    print("=" * 66)
    print(" 1) RAG 검색 (정답 근거가 상위 3개 안에 오는가)")
    print("=" * 66)
    rr = evaluate_rag(rag, rag_rows)
    for topic, v in rr["per_topic"].items():
        print(f"  {topic:<10} Hit@3 {v['hit3']:>2}/{v['n']:<2} = {v['hit3_rate']:.0%}")
    print(f"\n  [전체]  Hit@1 = {rr['hit1']}/{rr['n_in']} = {rr['hit1_rate']:.0%}"
          f"    Hit@3 = {rr['hit3']}/{rr['n_in']} = {rr['hit3_rate']:.0%}")
    print(f"  [범위 밖 거절]  {rr['refused']}/{rr['n_out']} = {rr['refuse_rate']:.0%}"
          f"  (관련성 게이트 {rr['gate']})")

    print("\n" + "=" * 66)
    print(" 2) 이상신호 감지 (정상/주의/위험 3단계)")
    print("=" * 66)
    ss = evaluate_signal(sig_rows)
    print("  혼동행렬 (행=정답, 열=예측):")
    print("            " + "".join(f"{p:>6}" for p in LEVELS))
    for g in LEVELS:
        print(f"    {g:<6}" + "".join(f"{ss['confusion'][g][p]:>6}" for p in LEVELS))
    print("\n  클래스별 (Precision / Recall / F1):")
    for l in LEVELS:
        c = ss["per_class"][l]
        print(f"    {l}  P {c['precision']:.0%}  R {c['recall']:.0%}  "
              f"F1 {c['f1']:.2f}  (n={c['support']})")
    b = ss["binary"]
    print(f"\n  3단계 정확도 = {ss['accuracy3']:.0%}")
    print(f"  이진(이상 여부)  Acc {b['accuracy']:.0%}  P {b['precision']:.0%}  "
          f"R {b['recall']:.0%}  F1 {b['f1']:.2f}")
    print(f"  ★ '위험' Recall = {ss['danger_recall']:.0%}  (위기 신호를 놓치지 않는 비율)")

    print("\n" + "=" * 66)
    print(" 요약 (보고서용)")
    print("=" * 66)
    print(f"  RAG   : Hit@1 {rr['hit1_rate']:.0%} | Hit@3 {rr['hit3_rate']:.0%} | "
          f"범위밖 거절 {rr['refuse_rate']:.0%}")
    print(f"  신호  : 3단계 Acc {ss['accuracy3']:.0%} | 이상 F1 {b['f1']:.2f} | "
          f"위험 Recall {ss['danger_recall']:.0%}")

    results = {"rag": rr, "signal": ss,
               "backend": f"{rag.backend}/{rag.embedder.backend}",
               "use_llm_signal": config.USE_LLM_SIGNAL}
    out = EVAL_DIR / "results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → 상세 결과 저장: {out}")


if __name__ == "__main__":
    main()
