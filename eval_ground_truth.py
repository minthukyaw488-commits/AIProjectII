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

# 네이티브 크래시(bus error) 방지 — torch/OpenMP/pyarrow 라이브러리 충돌을 막는다.
# worker_server.py 와 동일한 가드. 이 평가 스크립트는 (워커 프로세스가 아니라)
# 메인 프로세스에서 모델을 직접 로드하므로, 반드시 heavy import 이전에 설정해야
# Apple Silicon 등에서 'zsh: bus error' 로 죽지 않는다.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 재현성: 신호는 규칙 기반이 기본(원하면 USE_LLM_SIGNAL=1), 검색은 결정형 경로.
os.environ.setdefault("USE_LLM_SIGNAL", "0")
os.environ.setdefault("USE_AGENT", "0")

from src import config  # noqa: E402
from src.abnormal_signal import AbnormalSignalDetector, SentimentAnalyzer  # noqa: E402
from src.rag_pipeline import RagPipeline  # noqa: E402
from src.router import is_off_domain  # noqa: E402  (실서비스의 범위 밖 판정 경로)
from src.llm import (make_llm, build_answer_prompt,  # noqa: E402
                     ANSWER_SYSTEM_PROMPT, OFF_DOMAIN_REPLY)

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

    import os
    debug = os.environ.get("GT_DEBUG") not in (None, "", "0")

    hit1 = hit3 = 0
    per_topic = defaultdict(lambda: [0, 0, 0])   # topic -> [hit1, hit3, n]
    misses = []
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
        if not h3:
            misses.append({
                "q": r["q"], "topic": r["topic"], "keyword": kw,
                "top3": [(round(x.score, 3), x.source,
                          x.text[:70].replace("\n", " ")) for x in results],
            })

    # 범위 밖(out): 실서비스와 동일하게 ① 라우터가 off-domain으로 거르거나
    #   ② 검색 최상위 점수가 관련성 게이트 아래이면 '지어내지 않고 거절' = 정답.
    gate = config.RAG_MIN_RELEVANCE
    refused = 0
    for r in out_rows:
        if is_off_domain(r["q"]):
            refused += 1
            continue
        results = rag.retrieve(r["q"], top_k=3)
        top = results[0].score if results else 0.0
        if top < gate:
            refused += 1

    if debug and misses:
        print(f"\n  [GT_DEBUG] 검색 실패 {len(misses)}문항 — 상위 3개 실제 조각:")
        for m in misses[:40]:
            print(f"   ✗ ({m['topic']}) \"{m['q']}\"  기대 키워드='{m['keyword']}'")
            for sc, src, snip in m["top3"]:
                print(f"       [{sc}] ({src}) {snip}...")

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
# 1b) 답변 정확도 — fact-coverage (정답지의 facts 가 답변에 실제로 담겼는가)
#     검색 Hit@K 는 '근거가 상위에 왔는가'만 보지만, 이 지표는 '생성된 답변'이
#     핵심 사실(금액·기관·나이 등)을 담았는지를 본다. LLM 로 답변을 생성하므로
#     EVAL_ANSWERS=1 일 때만 동작(느리고 Ollama 필요).
# --------------------------------------------------------------------------
def _norm(s: str) -> str:
    """사실 매칭용 정규화: 공백 제거(‘33만 원’ ↔ ‘33만원’, ‘만 65세’ ⊇ ‘65세’)."""
    return "".join((s or "").split())


def _grounded_answer(rag, llm, question: str) -> str:
    """결정형 RAG 답변(검색→게이트→근거 기반 생성). 실서비스 결정형 경로와 동일."""
    retrieved = rag.retrieve(question, top_k=3)
    top = retrieved[0].score if retrieved else 0.0
    if not retrieved or top < config.RAG_MIN_RELEVANCE:
        return OFF_DOMAIN_REPLY
    contexts = [r.text for r in retrieved]
    prompt = build_answer_prompt(question, contexts)
    return llm.generate(prompt, system=ANSWER_SYSTEM_PROMPT, num_predict=256)


def evaluate_answers(rag, llm, in_rows) -> dict:
    """각 정보 질문에 답변을 생성하고, 정답지 facts 중 몇 개가 담겼는지 측정.
    - fact-coverage = (답변에 등장한 gold fact 수) / (gold fact 수)  평균
    - pass(≥50% 사실 포함) 비율도 함께 보고(주제별 포함)."""
    total = 0.0
    passed = 0
    n = 0
    per_topic = defaultdict(lambda: [0.0, 0])      # topic -> [coverage합, n]
    samples = []
    for r in in_rows:
        facts = [f for f in (r.get("facts") or []) if f]
        if not facts:
            continue
        ans = _grounded_answer(rag, llm, r["q"])
        a = _norm(ans)
        hit = sum(1 for f in facts if _norm(f) in a)
        cov = hit / len(facts)
        total += cov
        n += 1
        if cov >= 0.5:
            passed += 1
        pt = per_topic[r["topic"]]
        pt[0] += cov
        pt[1] += 1
        if len(samples) < 5:
            samples.append({"q": r["q"], "cov": cov, "hit": hit,
                            "total": len(facts), "ans": ans[:80].replace("\n", " ")})
    return {
        "n": n,
        "mean_coverage": total / n if n else 0.0,
        "pass_rate": passed / n if n else 0.0,
        "per_topic": {k: {"coverage": v[0] / v[1] if v[1] else 0.0, "n": v[1]}
                      for k, v in per_topic.items()},
        "samples": samples,
    }


# --------------------------------------------------------------------------
# 2) 이상신호 평가 (3단계 + 이진)
# --------------------------------------------------------------------------
def _prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def evaluate_signal(rows, llm=None) -> dict:
    shared = SentimentAnalyzer()                     # 모델 1회만 로드
    # 혼동행렬: confusion[gold][pred]
    confusion = {g: {p: 0 for p in LEVELS} for g in LEVELS}
    bin_tp = bin_tn = bin_fp = bin_fn = 0
    details = []
    for row in rows:
        # llm 을 넘기면 USE_LLM_SIGNAL=1 일 때 LLM 심판까지 사용(실서비스와 동일).
        det = AbnormalSignalDetector(sentiment=shared, llm=llm)   # 대화마다 초기화
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

    # 1b) 답변 정확도(fact-coverage) — EVAL_ANSWERS=1 일 때만(느리고 Ollama 필요).
    ans_res = None
    if os.environ.get("EVAL_ANSWERS") not in (None, "", "0", "false", "False"):
        print("\n" + "=" * 66)
        print(" 1b) 답변 정확도 — fact-coverage (facts 가 답변에 담겼는가)")
        print("=" * 66)
        a_llm = make_llm()
        print(f"  답변 모델: {type(a_llm).__name__}:{a_llm.model} "
              f"({'ON' if a_llm.available else '사용 불가'})")
        if a_llm.available:
            in_rows = [r for r in rag_rows if r.get("scope") == "in"]
            ans_res = evaluate_answers(rag, a_llm, in_rows)
            for topic, v in ans_res["per_topic"].items():
                print(f"  {topic:<10} fact-coverage {v['coverage']:.0%}  (n={v['n']})")
            print(f"\n  [전체] 평균 fact-coverage = {ans_res['mean_coverage']:.0%}"
                  f"   ·  사실 ≥50% 포함(pass) = {ans_res['pass_rate']:.0%}  (n={ans_res['n']})")
        else:
            print("  (LLM 미연결 → 건너뜀. Ollama 실행 후 EVAL_ANSWERS=1 로 다시 실행)")

    print("\n" + "=" * 66)
    print(" 2) 이상신호 감지 (정상/주의/위험 3단계)")
    print("=" * 66)
    # USE_LLM_SIGNAL=1 이면 실서비스처럼 LLM 심판을 붙여 평가(문맥 위기 표현 포착).
    llm = None
    if config.USE_LLM_SIGNAL:
        llm = make_llm()
        print(f"  신호 LLM 심판: {type(llm).__name__}:{llm.model} "
              f"({'ON' if llm.available else '사용 불가 → 규칙 기반'})")
    else:
        print("  신호 LLM 심판: OFF (규칙 기반만 — USE_LLM_SIGNAL=1 로 켜면 개선)")
    ss = evaluate_signal(sig_rows, llm=llm)
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

    if ans_res:
        print(f"  답변  : 평균 fact-coverage {ans_res['mean_coverage']:.0%} | "
              f"사실 pass {ans_res['pass_rate']:.0%}")

    results = {"rag": rr, "answers": ans_res, "signal": ss,
               "backend": f"{rag.backend}/{rag.embedder.backend}",
               "use_llm_signal": config.USE_LLM_SIGNAL}
    out = EVAL_DIR / "results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → 상세 결과 저장: {out}")

    # 재현 가능한 리포트(저장소에 커밋): README 수치의 출처가 된다.
    report = _render_report(rr, ss, results["backend"], config.USE_LLM_SIGNAL, ans_res)
    rep = EVAL_DIR / "eval_report.md"
    rep.write_text(report, encoding="utf-8")
    print(f"  → 리포트 저장(커밋용): {rep}")


def _render_report(rr, ss, backend, use_llm_signal, ans_res=None) -> str:
    """사람이 읽는 평가 리포트(마크다운). README 가 인용하는 '진짜 수치'의 출처."""
    from datetime import datetime, timezone
    b = ss["binary"]
    agent = os.environ.get("USE_AGENT", "0") not in ("0", "false", "False", "")
    lines = []
    lines.append("# 평가 리포트 (자동 생성)\n")
    lines.append(f"- 생성 시각(UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M}")
    lines.append(f"- 백엔드: `{backend}`")
    lines.append(f"- 답변 경로: {'에이전트(USE_AGENT=1)' if agent else '결정형 검색(USE_AGENT=0)'}  "
                 f"· 신호 LLM 심판: {'ON' if use_llm_signal else 'OFF(규칙 기반)'}")
    lines.append(f"- 재현 명령: `RAG_REINDEX=1 python eval_ground_truth.py`\n")
    lines.append("> 주의: Hit@K·거절률은 검색 전용 지표라 답변 경로(USE_AGENT)와 무관합니다.\n")
    lines.append("## 1) RAG 검색 (정답 근거가 상위 3개 안에)\n")
    lines.append(f"- **Hit@1 = {rr['hit1']}/{rr['n_in']} = {rr['hit1_rate']:.0%}**")
    lines.append(f"- **Hit@3 = {rr['hit3']}/{rr['n_in']} = {rr['hit3_rate']:.0%}**")
    lines.append(f"- **범위 밖 안전 거절 = {rr['refused']}/{rr['n_out']} = {rr['refuse_rate']:.0%}** "
                 f"(관련성 게이트 {rr['gate']})\n")
    lines.append("| 주제 | Hit@3 | 비율 |")
    lines.append("|---|---|---|")
    for topic, v in rr["per_topic"].items():
        lines.append(f"| {topic} | {v['hit3']}/{v['n']} | {v['hit3_rate']:.0%} |")
    if ans_res:
        lines.append("\n## 1b) 답변 정확도 — fact-coverage\n")
        lines.append("생성된 답변이 정답지 `facts`(금액·기관·나이 등)를 얼마나 담았는가.\n")
        lines.append(f"- **평균 fact-coverage = {ans_res['mean_coverage']:.0%}**")
        lines.append(f"- **사실 ≥50% 포함(pass) = {ans_res['pass_rate']:.0%}** (n={ans_res['n']})\n")
        lines.append("| 주제 | fact-coverage |")
        lines.append("|---|---|")
        for topic, v in ans_res["per_topic"].items():
            lines.append(f"| {topic} | {v['coverage']:.0%} (n={v['n']}) |")
    lines.append("\n## 2) 이상신호 감지 (정상/주의/위험)\n")
    lines.append(f"- 3단계 정확도 = **{ss['accuracy3']:.0%}**")
    lines.append(f"- 이진(이상 여부) F1 = **{b['f1']:.2f}** (P {b['precision']:.0%} / R {b['recall']:.0%})")
    lines.append(f"- ★ '위험' Recall = **{ss['danger_recall']:.0%}** (위기 신호를 놓치지 않는 비율)\n")
    lines.append("---\n*이 파일은 `eval_ground_truth.py` 가 자동 생성합니다. 손으로 고치지 마세요.*")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
