"""피드백 루프 — 목표 정확도에 도달할 때까지 하이퍼파라미터를 바꿔 가며 찾고, 가장 좋은 값을
'코드북'(data/best_params.json)으로 저장한다. 앱(src/config.py)은 이 파일을 읽어 검색에 쓰고,
그렇게 찾은 근거 조각을 LLM 에 보낸다.

교수님 피드백(11-24): "for문으로 k·threshold·하이퍼파라미터를 바꿔 가며, 정확도 95% 이상이면
출력하고 아니면 계속 돌면서 가장 좋은 값을 찾는다. 최적 값은 코드북으로 저장해 두고 쓴다."

  python3 tune.py                # 50/25/25 분할: 학습·검증으로 찾기 → 테스트 1회 → 코드북 저장
  python3 tune.py --folds 4      # 같은 루프를 4-fold 교차검증으로 평가(모든 문항이 테스트에 한 번)
  python3 tune.py --target 0.9 --metric hit3

필요: data/eval/cv_cache/ 의 운영 인덱스 캐시 (서버에서 `python3 eval_cv.py dump` 1회).
라벨·검색·게이트 계산은 eval_cv.py 와 같은 함수를 쓴다(점수 정의가 리포트와 똑같다).
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import statistics
import time
from pathlib import Path

import eval_cv as E

CODEBOOK = Path("data/best_params.json")
METRICS = {"label_acc": "라벨 정확도", "hit1": "Hit@1", "hit3": "Hit@3"}


def find_best(train, val, target: float, metric: str, verbose: bool = True) -> dict:
    """피드백 루프: 설정을 하나씩 바꿔 검증 정확도를 재고, 목표 이상이면 바로 멈춘다.
    목표에 못 미치면 끝까지 돌고 가장 좋은 설정을 돌려준다."""
    combos = list(itertools.product(
        E.GRID["knn_k"],      # k   : 가장 비슷한 학습 질문 몇 개로 투표할지
        E.GRID["knn_tau"],    # tau : 유사도 임계값(threshold). 이보다 낮으면 '기타 복지'
        E.GRID["rerank"],     #       재랭커 사용 여부
        E.GRID["pool"],       #       재랭킹 전 후보 수
        E.GRID["kw_boost"],   # w   : 라벨 키워드가 든 조각에 주는 가점
        E.GRID["gate"]))      # gate: 거절 임계값(threshold). 1위 관련성 점수가 이보다 낮으면 '문서에 없음'
    best = None
    for n, (k, tau, rerank, pool, w, gate) in enumerate(combos, 1):
        fb = E.fit_fallback(train, k)                          # 학습 질문으로 분류기 학습
        hp = {"knn_k": k, "knn_tau": tau, "rerank": rerank, "pool": pool, "kw_boost": w, "gate": gate}
        m = E._evaluate(E._prep(val, fb, tau), hp, hp["gate"])  # 검증 데이터로 정확도 측정
        # 목표 지표가 같으면 종합 점수(라벨 정확도 + Hit@1 + 게이트 균형 정확도)/3 가 높은 쪽
        if best is None or (m[metric], E._objective(m)) > (best["val"][metric], E._objective(best["val"])):
            best = {"hp": hp, "val": m, "fb": fb, "tried": n}
        if verbose:
            print(f"  [{n:2d}/{len(combos)}] k={k} tau={tau} rerank={'ON' if rerank else 'OFF'} "
                  f"pool={pool} w={w} gate={hp['gate']:.3f} → 검증 {METRICS[metric]} "
                  f"{m[metric]:.1%} (지금까지 최고 {best['val'][metric]:.1%})")
        if m[metric] >= target:                                # 목표 도달 → 루프 종료
            best["reached"] = True
            return best
    best["reached"] = False                                    # 끝까지 돌았지만 목표 미달
    best["tried"] = len(combos)
    return best


def test_once(best, test) -> dict:
    """고른 설정으로 테스트 데이터를 딱 한 번 잰다."""
    hp = best["hp"]
    return E._evaluate(E._prep(test, best["fb"], hp["knn_tau"]), hp, hp["gate"])


def baseline(test) -> dict:
    """비교용: 튜닝 전 운영 설정(eval_cv.BASELINE)을 같은 테스트 문항에서 잰 값."""
    has_rr = any(r.get("rerank") for r in test)
    hp = {**E.BASELINE, "rerank": E.BASELINE["rerank"] and has_rr}
    return E._evaluate(E._prep(test, None), hp, E.BASELINE["gate"])


def load_rows(cache: str | None):
    paths = [cache] if cache else sorted(glob.glob(str(E.CACHE_DIR / "*.json")))
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        if cache or "운영" in d["meta"]["setting"]:
            return d["meta"], [r for r in d["rows"] if r.get("scope") in ("in", "out")]
    raise SystemExit("운영 인덱스 캐시가 없습니다. 서버에서 먼저:  python3 eval_cv.py dump")


def _pct(m: dict) -> str:
    return " · ".join(f"{name} {m[key]:.1%}" for key, name in METRICS.items())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=float, default=0.95, help="목표 검증 정확도 (기본 0.95)")
    ap.add_argument("--metric", choices=list(METRICS), default="label_acc", help="목표로 삼을 지표")
    ap.add_argument("--folds", type=int, default=0, help="k-fold 교차검증으로 루프 자체를 평가 (예: 4)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cache", help="캐시 파일 (기본: cv_cache 의 운영 인덱스 캐시)")
    args = ap.parse_args()
    meta, rows = load_rows(args.cache)
    name = METRICS[args.metric]
    print(f"[tune] 캐시={meta['setting']} · 목표: 검증 {name} ≥ {args.target:.0%}")

    if args.folds:                                  # ── 루프를 k-fold 로 평가 (코드북은 안 바꿈)
        rs = []
        for i, (tr, va, te) in enumerate(E.split_kfold(rows, args.folds, args.seed), 1):
            best = find_best(tr, va, args.target, args.metric, verbose=False)
            t, b = test_once(best, te), baseline(te)
            rs.append((best, t, b))
            print(f"[fold {i}/{args.folds}] 학습/검증/테스트={len(tr)}/{len(va)}/{len(te)} · "
                  f"{best['tried']}개 시도 · 목표 {'도달' if best['reached'] else '미달'} · "
                  f"검증 {name} {best['val'][args.metric]:.1%} → 테스트 {_pct(t)} (기준선 {_pct(b)})")
        for key, nm in METRICS.items():
            v, bv = [t[key] for _, t, _ in rs], [b[key] for _, _, b in rs]
            print(f"[tune] {args.folds}-fold 테스트 평균 {nm}: {statistics.mean(v):.1%} ± "
                  f"{statistics.stdev(v):.1%}  (기준선 {statistics.mean(bv):.1%})")
        return

    tr, va, te = E.split_50_25_25(rows, args.seed)  # ── 코드북 만들기 (50/25/25 한 번)
    print(f"[tune] 학습 {len(tr)} / 검증 {len(va)} / 테스트 {len(te)} (시드 {args.seed})")
    best = find_best(tr, va, args.target, args.metric)
    t, b = test_once(best, te), baseline(te)
    status = "목표 도달 → 루프 종료" if best["reached"] else "목표 미달 → 가장 좋은 설정 사용"
    print(f"[tune] {status} ({best['tried']}개 시도) · 선택: {best['hp']}")
    print(f"[tune] 검증 {_pct(best['val'])}")
    print(f"[tune] 테스트(1회) {_pct(t)}   ← 기준선 {_pct(b)}")
    book = {**best["hp"], "metric": args.metric, "target": args.target, "reached": best["reached"],
            "tried": best["tried"], "val": {k: round(best["val"][k], 4) for k in METRICS},
            "test": {k: round(t[k], 4) for k in METRICS},
            "baseline_test": {k: round(b[k], 4) for k in METRICS},
            "split": f"50/25/25 seed {args.seed} ({len(tr)}/{len(va)}/{len(te)})",
            "cache": meta["setting"], "created": time.strftime("%Y-%m-%d %H:%M"),
            "note": "tune.py 가 생성. src/config.py 가 읽음(환경변수가 있으면 환경변수 우선)."}
    CODEBOOK.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[tune] 코드북 저장: {CODEBOOK}  → 앱 재시작 시 적용 (sudo systemctl restart welfarehub-8003)")


if __name__ == "__main__":
    main()
