"""Recall@K / MRR / Precision@K — 사람이 라벨링한 '정답 근거(문서·쪽)' 기준.

Hit@K(키워드 부분일치)는 '정답 용어가 청크에 있나'만 보는 느슨한 지표다. 이 평가는
사람이 (문서, 쪽) 단위로 표시한 정답 근거를 기준으로, 검색이 그 근거를 상위 K개
안에 가져오는지 엄밀하게 측정한다.

  - Recall@K  : 정답 근거를 상위 K개 안에 가져온 질문 비율
  - Precision@K: 상위 K개 중 정답 근거의 비율(평균)
  - MRR       : 첫 정답 근거의 순위 역수 평균(1위=1.0, 2위=0.5, …)

라벨은 (source, page) 라서 재색인(청크 번호 변동)에도 안정적이며, 평가 시 매번
새로 검색해 라벨과 대조한다.

실행:
  1) python make_recall_labels.py   (라벨 풀 생성)
  2) data/eval/recall_pool.jsonl 에서 정답 근거를 relevant:1 로 표시
  3) python eval_recall.py
"""
from __future__ import annotations
import json
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("USE_AGENT", "0")

from src.rag_pipeline import RagPipeline  # noqa: E402

EVAL = Path("data/eval")
K = 3


def load_gold(path: Path) -> dict:
    """recall_pool.jsonl → {질문: {(source, page), …}}  (relevant==1 만)."""
    gold = defaultdict(set)
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if int(d.get("relevant", 0)) == 1:
            gold[d["q"]].add((d.get("source"), d.get("page")))
    return gold


def score(gold: dict, retrieve, k: int = K) -> dict:
    """gold(라벨) 과 retrieve(질문→[(source,page),…]) 로 지표 계산. 테스트 가능."""
    n = recall_hits = 0
    prec_sum = mrr_sum = 0.0
    per_q = []
    for q, gset in gold.items():
        got = retrieve(q)[:k]
        hit = any(g in gset for g in got)
        recall_hits += 1 if hit else 0
        prec_sum += sum(1 for g in got if g in gset) / k
        rr = 0.0
        for rank, g in enumerate(got, 1):
            if g in gset:
                rr = 1.0 / rank
                break
        mrr_sum += rr
        n += 1
        per_q.append({"q": q, "hit": hit, "rr": rr})
    return {
        "n": n,
        "recall_at_k": recall_hits / n if n else 0.0,
        "precision_at_k": prec_sum / n if n else 0.0,
        "mrr": mrr_sum / n if n else 0.0,
        "k": k, "per_q": per_q,
        "gold_pages": sum(len(v) for v in gold.values()),
    }


def main() -> None:
    pool = EVAL / "recall_pool.jsonl"
    if not pool.exists():
        print(f"{pool} 없음. 먼저 'python make_recall_labels.py' 실행 후 라벨링하세요.")
        return
    gold = load_gold(pool)
    if not gold:
        print("라벨된 정답(relevant=1)이 없습니다. recall_pool.jsonl 에서 "
              "정답 근거 줄의 \"relevant\" 를 1 로 바꾸세요.")
        return

    print(f"라벨 질문 {len(gold)}개 · 정답 근거(문서·쪽) {sum(len(v) for v in gold.values())}개")
    print("파이프라인 로딩(색인)...")
    rag = RagPipeline()
    rag.index()

    def retrieve(q):
        return [(h.source, h.page) for h in rag.retrieve(q, top_k=K)]

    res = score(gold, retrieve, K)
    print("\n" + "=" * 50)
    print(f"  Recall@{K}    = {res['recall_at_k']:.0%}   (정답 근거를 상위 {K}개 안에)")
    print(f"  Precision@{K} = {res['precision_at_k']:.0%}")
    print(f"  MRR         = {res['mrr']:.3f}   (1위=1.0, 2위=0.5 …)")
    print("=" * 50)
    out = EVAL / "recall_results.json"
    out.write_text(json.dumps({k: v for k, v in res.items() if k != "per_q"},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → 저장: {out}")


if __name__ == "__main__":
    main()
