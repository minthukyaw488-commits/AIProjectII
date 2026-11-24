"""라벨 신뢰도 검토 — 팀원 1명이 정답 라벨을 보지 않고 붙인 라벨 vs 기존 정답지.

교수님 피드백 1(정답 라벨의 신뢰성) 대응. 검토자가 1명이므로
'기존 정답지 작성자'와 '새 검토자' 두 사람의 일치율(+ Cohen's kappa)을 보고한다.

    python eval_label_agreement.py make    # → data/eval/label_review_blind.csv (라벨 칸이 빈 50문항)
    python eval_label_agreement.py score   # 검토자가 채운 CSV 채점 → data/eval/label_agreement.md

검토자는 data/eval/ground_truth_rag.jsonl(정답)을 보지 않고 docs/LABELS.md 의 정의만 보고 붙인다.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
import topic_labels as TL  # noqa: E402

GT = ROOT / "data/eval/ground_truth_rag.jsonl"
BLIND = ROOT / "data/eval/label_review_blind.csv"
REPORT = ROOT / "data/eval/label_agreement.md"
PER_TOPIC, N_OUT, SEED = 4, 10, 7          # 10개 주제 × 4 + 범위 밖 10 = 50문항
COLS = ["id", "질문", "라벨", "메모"]


def load_gt() -> list[dict]:
    rows = [json.loads(l) for l in GT.open(encoding="utf-8") if l.strip()]
    for i, r in enumerate(rows):
        r["id"] = f"gt_{i:03d}"
        r["gold"] = TL.GOLD_TO_LABEL.get(r["topic"], r["topic"])
    return rows


def norm(label: str) -> str:
    """'범위밖', ' 기초연금 ' 처럼 띄어쓰기가 달라도 같은 라벨로 본다."""
    key = "".join(label.split())
    for lab in TL.LABELS:
        if "".join(lab.split()) == key:
            return lab
    return label.strip()


def make() -> None:
    rows = load_gt()
    rng = random.Random(SEED)
    by = defaultdict(list)
    for r in rows:
        by[r["gold"]].append(r)
    pick = []
    for lab, rs in by.items():
        pick += rng.sample(rs, N_OUT if lab == TL.LABEL_OUT else PER_TOPIC)
    rng.shuffle(pick)
    with BLIND.open("w", encoding="utf-8-sig", newline="") as f:   # BOM: 엑셀에서 한글 깨짐 방지
        w = csv.writer(f)
        w.writerow(COLS)
        for r in pick:
            w.writerow([r["id"], r["q"], "", ""])
    print(f"{BLIND.relative_to(ROOT)} — {len(pick)}문항. '라벨' 칸에 아래 14개 중 하나를 적어 주세요:")
    print(" · ".join(TL.LABELS))


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def score() -> None:
    gold = {r["id"]: r for r in load_gt()}
    with BLIND.open(encoding="utf-8-sig", newline="") as f:
        filled = [r for r in csv.DictReader(f) if r.get("라벨", "").strip()]
    if not filled:
        sys.exit(f"{BLIND.name} 의 '라벨' 칸이 비어 있습니다.")
    bad = [r["라벨"] for r in filled if norm(r["라벨"]) not in TL.LABELS]
    if bad:
        sys.exit(f"정의에 없는 라벨: {sorted(set(bad))}\n허용: {' · '.join(TL.LABELS)}")

    pairs, diff = [], []
    for r in filled:
        g, h = gold[r["id"]]["gold"], norm(r["라벨"])
        pairs.append((g, h))
        if g != h:
            diff.append((r["id"], r["질문"], g, h, r.get("메모", "")))
    n, agree = len(pairs), sum(a == b for a, b in pairs)
    k = kappa(pairs)
    L = ["# 라벨 신뢰도 검토 (기존 정답지 vs 팀원 독립 검토)", "",
         f"- 검토 문항: {n}개 (10개 주제 × {PER_TOPIC} + 범위 밖 {N_OUT}, 시드 {SEED})",
         f"- **일치율 {agree}/{n} = {agree / n:.1%}** · Cohen's kappa = {k:.2f}",
         "- 검토자는 정답을 보지 않고 docs/LABELS.md 의 라벨 정의만 보고 붙임", "",
         "## 불일치 문항", "", "| id | 질문 | 기존 정답 | 검토자 | 메모 |", "|---|---|---|---|---|"]
    L += [f"| {i} | {q} | {g} | {h} | {m} |" for i, q, g, h, m in diff] or ["| - | 없음 | | | |"]
    L += ["", "> 불일치 문항은 둘이 논의해 정답지를 고치거나(정답 오류) 라벨 정의를 보완한다(정의가 모호).",
          "> 정답지를 고쳤다면 eval_cv.py 를 다시 돌려 수치를 갱신한다."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"일치율 {agree}/{n} = {agree / n:.1%} · kappa {k:.2f} · 불일치 {len(diff)}개 → {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    {"make": make, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
