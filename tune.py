"""피드백 루프 — 목표 정확도에 도달할 때까지 하이퍼파라미터를 바꿔 가며 찾고, 가장 좋은 값을
'코드북'(data/best_params.json)으로 저장한다. 앱(src/config.py)은 이 파일을 읽어 검색에 쓰고,
그렇게 찾은 근거 조각을 LLM 에 보낸다.

교수님 피드백(11-24): "for문으로 k·threshold·하이퍼파라미터를 바꿔 가며, 정확도 95% 이상이면
출력하고 아니면 계속 돌면서 가장 좋은 값을 찾는다. 최적 값은 코드북으로 저장해 두고 쓴다."

  python3 tune.py                # ① 4-fold 로 루프 성능 추정  ② 4개 검증의 평균으로 코드북 선택·저장
  python3 tune.py --all          # 루프의 모든 시도를 출력(기본은 최고 기록이 바뀔 때만)
  python3 tune.py --target 0.9 --metric hit3

4-fold: 200문항을 주제 비율대로 4등분 → fold i 테스트, i+1 검증, 나머지 학습(50/25/25).
  ① 성능 추정 : fold 마다 학습·검증으로 루프를 돌려 설정을 고르고, 그 fold 의 테스트로 1번 잰다.
                모든 문항이 테스트에 정확히 한 번 → 평균 ± 표준편차가 이 방법의 정직한 성능.
  ② 코드북   : 설정마다 4개 검증 fold 의 평균 점수를 내고 가장 좋은 설정을 저장한다.
                검증 50문항 하나에 맞춰 우연히 고르는 것을 막는다(11-24: 한 번 분할로는 재랭커 OFF 가
                2문항 차이로 골라짐).

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


# 재랭커는 루프에서 고르지 않고 ON 으로 고정한다(기본). 11-24 서버: 검색 지표만으로 고르면 OFF 가
# Hit@1 이 약간 높았지만, 같은 설정으로 거짓 유도 60문항을 돌리니 거짓 답변 1 → 4, 검토 필요 8 → 10
# 으로 나빠졌다(eval_adversarial.py). 검색 정확도보다 거짓 답변을 줄이는 쪽을 택한다.
RERANK_CHOICES = {"on": [True], "off": [False], "both": [True, False]}


def find_best(pairs, target: float, metric: str, show: str = "best", rerank: str = "on") -> dict:
    """피드백 루프: 설정을 하나씩 바꿔 검증 정확도를 재고, 목표 이상이면 바로 멈춘다.
    pairs = [(학습, 검증), ...] — 여러 개면 검증 점수의 평균으로 비교한다.
    목표에 못 미치면 끝까지 돌고 가장 좋은 설정을 돌려준다."""
    combos = list(itertools.product(
        E.GRID["knn_k"],      # k   : 가장 비슷한 학습 질문 몇 개로 투표할지
        E.GRID["knn_tau"],    # tau : 유사도 임계값(threshold). 이보다 낮으면 '기타 복지'
        RERANK_CHOICES[rerank],  #    재랭커 사용 여부 (기본 ON 고정, 위 설명)
        E.GRID["pool"],       #       재랭킹 전 후보 수
        E.GRID["kw_boost"],   # w   : 라벨 키워드가 든 조각에 주는 가점
        E.GRID["gate"]))      # gate: 거절 임계값(threshold). 1위 관련성 점수가 이보다 낮으면 '문서에 없음'
    fbs = {}                                                   # (몇 번째 쌍, k) → 학습된 분류기
    best = None
    for n, (k, tau, rerank, pool, w, gate) in enumerate(combos, 1):
        hp = {"knn_k": k, "knn_tau": tau, "rerank": rerank, "pool": pool, "kw_boost": w, "gate": gate}
        ms = []
        for i, (train, val) in enumerate(pairs):
            if (i, k) not in fbs:
                fbs[i, k] = E.fit_fallback(train, k)           # 학습 질문으로 분류기 학습
            ms.append(E._evaluate(E._prep(val, fbs[i, k], tau), hp, gate))  # 검증 정확도
        m = {key: statistics.mean(x[key] for x in ms) for key in ("label_acc", "hit1", "hit3", "gate_bacc")}
        # 목표 지표가 같으면 종합 점수(라벨 정확도 + Hit@1 + 게이트 균형 정확도)/3 가 높은 쪽
        improved = best is None or (m[metric], E._objective(m)) > (best["val"][metric], E._objective(best["val"]))
        if improved:
            best = {"hp": hp, "val": m, "fbs": [fbs[i, k] for i in range(len(pairs))], "tried": n}
        if show == "all" or (show == "best" and improved):
            print(f"  [{n:3d}/{len(combos)}] k={k} tau={tau} rerank={'ON' if rerank else 'OFF'} "
                  f"pool={pool} w={w} gate={gate} → 검증 {METRICS[metric]} {m[metric]:.1%}"
                  f"{'  ★ 최고 갱신' if improved else ''}")
        if m[metric] >= target:                                # 목표 도달 → 루프 종료
            best["reached"] = True
            return best
    best["reached"] = False                                    # 끝까지 돌았지만 목표 미달
    best["tried"] = len(combos)
    return best


def test_once(best, test, i: int = 0) -> dict:
    """고른 설정으로 테스트 데이터를 딱 한 번 잰다."""
    hp = best["hp"]
    return E._evaluate(E._prep(test, best["fbs"][i], hp["knn_tau"]), hp, hp["gate"])


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


def _ms(vals) -> dict:
    vals = list(vals)
    return {"mean": round(statistics.mean(vals), 4), "std": round(statistics.stdev(vals), 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=float, default=0.95, help="목표 검증 정확도 (기본 0.95)")
    ap.add_argument("--metric", choices=list(METRICS), default="label_acc", help="목표로 삼을 지표")
    ap.add_argument("--folds", type=int, default=4, help="교차검증 fold 수 (기본 4 = 50/25/25)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--all", action="store_true", help="루프의 모든 시도를 출력")
    ap.add_argument("--rerank", choices=list(RERANK_CHOICES), default="on",
                    help="재랭커: on 고정(기본, 거짓 답변 평가 근거) / off / both(루프에서 선택)")
    ap.add_argument("--cache", help="캐시 파일 (기본: cv_cache 의 운영 인덱스 캐시)")
    args = ap.parse_args()
    meta, rows = load_rows(args.cache)
    name = METRICS[args.metric]
    splits = E.split_kfold(rows, args.folds, args.seed)
    print(f"[tune] 캐시={meta['setting']} · 목표: 검증 {name} ≥ {args.target:.0%} · {args.folds}-fold"
          f" · 재랭커 {args.rerank}")

    # ① 성능 추정 — fold 마다 루프로 설정을 고르고 그 fold 의 테스트로 1번만 잰다
    tests, bases = [], []
    for i, (tr, va, te) in enumerate(splits, 1):
        best = find_best([(tr, va)], args.target, args.metric, show="none", rerank=args.rerank)
        t, b = test_once(best, te), baseline(te)
        tests.append(t)
        bases.append(b)
        print(f"[fold {i}/{args.folds}] {best['tried']}개 시도 · 목표 {'도달' if best['reached'] else '미달'} · "
              f"검증 {name} {best['val'][args.metric]:.1%} → 테스트 {_pct(t)}  (기준선 {_pct(b)})")
    for key, nm in METRICS.items():
        v, bv = _ms(t[key] for t in tests), _ms(b[key] for b in bases)
        print(f"[tune] {args.folds}-fold 테스트 {nm}: {v['mean']:.1%} ± {v['std']:.1%}  "
              f"(기준선 {bv['mean']:.1%} ± {bv['std']:.1%})")

    # ② 코드북 — 설정마다 4개 검증 fold 의 평균 점수로 비교해 가장 좋은 설정을 저장
    print(f"[tune] 코드북 선택: 설정마다 {args.folds}개 검증 fold 의 평균으로 비교")
    best = find_best([(tr, va) for tr, va, _te in splits], args.target, args.metric,
                     show="all" if args.all else "best", rerank=args.rerank)
    status = "목표 도달 → 루프 종료" if best["reached"] else "목표 미달 → 가장 좋은 설정 사용"
    print(f"[tune] {status} ({best['tried']}개 시도) · 선택: {best['hp']}")
    print(f"[tune] 검증 평균 {_pct(best['val'])}")
    book = {**best["hp"], "metric": args.metric, "target": args.target, "reached": best["reached"],
            "tried": best["tried"], "val_mean": {k: round(best["val"][k], 4) for k in METRICS},
            "cv_test": {k: _ms(t[k] for t in tests) for k in METRICS},
            "cv_baseline": {k: _ms(b[k] for b in bases) for k in METRICS},
            "folds": args.folds, "seed": args.seed,
            "cache": meta["setting"], "created": time.strftime("%Y-%m-%d %H:%M"),
            "note": "tune.py 가 생성. src/config.py 가 읽음(환경변수가 있으면 환경변수 우선). "
                    "cv_test = 이 방법의 4-fold 테스트 성능(fold 마다 따로 고른 설정)."}
    CODEBOOK.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[tune] 코드북 저장: {CODEBOOK}  → 앱 재시작 시 적용 (sudo systemctl restart welfarehub-8003)")


if __name__ == "__main__":
    main()
