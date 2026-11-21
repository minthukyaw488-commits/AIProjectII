"""Recall@K / MRR 평가용 '라벨링 풀' 생성.

검색 품질을 Hit@K(키워드 부분일치)보다 엄밀하게 보려면, 각 질문의 '정답 근거'가
무엇인지 사람이 라벨링해야 한다. 이 스크립트는 주제별로 몇 문항을 골라 상위 후보를
덤프하고, 사람이 그 중 정답 근거를 표시(relevant: 0→1)할 수 있는 파일을 만든다.

정답은 (문서, 쪽) 단위로 라벨링되므로, 재색인(청크 번호 변동)에도 안정적이다
(page+date 메타데이터 도입 덕분).

워크플로:
  1) python make_recall_labels.py          → data/eval/recall_pool.jsonl 생성
  2) 각 후보의 "relevant": 0 → 1 로 표시     (그 후보가 정답 근거면 1)
  3) python eval_recall.py                 → Recall@3 · Precision@3 · MRR

설정: 주제당 문항 수(N_PER_TOPIC), 후보 수(TOPK)는 아래 상수로 조절.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

# 네이티브 크래시 방지(worker_server 와 동일) — heavy import 이전에 설정.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("USE_AGENT", "0")

from src.rag_pipeline import RagPipeline  # noqa: E402

EVAL = Path("data/eval")
N_PER_TOPIC = 3     # 주제당 라벨링할 질문 수 (10주제 → 30문항)
TOPK = 10           # 질문당 덤프할 상위 후보 수


def main() -> None:
    gt = [json.loads(l) for l in open(EVAL / "ground_truth_rag.jsonl", encoding="utf-8")]
    in_rows = [r for r in gt if r.get("scope") == "in"]

    by_topic: dict = {}
    for r in in_rows:
        by_topic.setdefault(r["topic"], []).append(r)
    picked = []
    for _topic, rows in by_topic.items():
        picked.extend(rows[:N_PER_TOPIC])

    print(f"파이프라인 로딩(색인)... 질문 {len(picked)}개 × 상위 {TOPK}")
    rag = RagPipeline()
    rag.index()

    out = []
    for r in picked:
        hits = rag.retrieve(r["q"], top_k=TOPK)
        for rank, h in enumerate(hits, 1):
            out.append({
                "q": r["q"], "topic": r["topic"], "rank": rank,
                "source": h.source, "page": h.page,
                "snippet": h.text[:90].replace("\n", " "),
                "relevant": 0,     # ← 사람이 정답 근거면 1 로 바꿈
            })

    path = EVAL / "recall_pool.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"→ {path} 생성 ({len(picked)}문항, 후보 {len(out)}개)")
    print('다음: 각 줄의 "relevant": 0 → 1 로 표시(정답 근거면 1). 그 뒤 python eval_recall.py')


if __name__ == "__main__":
    main()
