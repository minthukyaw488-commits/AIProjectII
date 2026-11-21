"""복지 질문(RAG) — 50/25/25 분할 × 5회 반복 검증 + 하이퍼파라미터 탐색.

교수님 피드백 3·5 반영:
  · 데이터를 학습 50% / 검증 25% / 테스트 25% 로 나누고(주제 비율 유지), 이를
    서로 다른 시드로 5번 반복해 '평균 ± 표준편차' 로 보고한다.
  · 학습(Train)   : ① 키워드가 없는 질문을 위한 '유사 질문 분류기'(학습 질문 TF-IDF)를
                    학습하고 ② 관련성 게이트 임계값을 학습한다(균형 정확도 최대).
  · 검증(Val)     : 하이퍼파라미터 조합(유사 질문 k·임계값·재랭킹·후보 수·키워드 가점) 중
                    검증 점수가 가장 높은 것을 고른다.
  · 테스트(Test)  : 고른 설정으로 딱 한 번 측정 → 보고. 같은 테스트에서 현재 운영 설정
                    (기준선)도 함께 측정해 '개선 전/후' 를 정직하게 비교한다.

무거운 모델(bge-m3·재랭커)은 질문마다 한 번만 돌리도록 두 단계로 나눈다.

  1) dump  — 서버(GPU)에서 1회:  질문별 검색 후보 20개 + 임베딩 점수 + 재랭커 점수 저장
       python eval_cv.py dump                         # 운영 인덱스(Chroma·bge-m3) 그대로
       python eval_cv.py dump --embed intfloat/multilingual-e5-large --chunk-size 600
                                                      # 다른 임베딩/청크 크기(메모리 인덱스)
  2) cv    — 어디서든(수 초~수 분):  분할·학습·선택·테스트
       python eval_cv.py cv                           # data/eval/cv_cache/*.json 전부 비교

결과: data/eval/cv_report.md (사람용), data/eval/cv_results.json (원자료)

예측 점수(관련성 점수)의 정의 — 교수님 피드백 2:
  score = sigmoid(재랭커 로짓)  ∈ [0,1]  (재랭킹을 끄면 임베딩 코사인 유사도)
  순위   = score + w · 1[조각이 질문 라벨의 키워드를 포함]     (w = 키워드 가점, 검증으로 선택)
  거절   = 1위 조각의 score < 게이트 임계값(학습으로 결정)  → "문서에 없음, 주민센터 안내"
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import statistics as st
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from src import topic_labels as TL  # noqa: E402

EVAL_DIR = Path("data/eval")
CACHE_DIR = EVAL_DIR / "cv_cache"
GT_FILE = EVAL_DIR / "ground_truth_rag.jsonl"
ADV_FILE = EVAL_DIR / "adversarial_rag.jsonl"
POOL_MAX = 20

# ── 하이퍼파라미터 탐색 공간 ──────────────────────────────────────────────
GRID = {
    "knn_k": [1, 3, 5],             # 유사 질문 분류: 가장 비슷한 학습 질문 몇 개로 투표하나
    "knn_tau": [0.0, 0.1, 0.2, 0.3],  # 유사 질문 분류: 1위 유사도가 이 값 미만이면 '기타 복지'
    "rerank": [True, False],        # 재랭커 사용 여부
    "pool": [10, 20],               # 재랭킹 전 임베딩 후보 수
    "kw_boost": [0.0, 0.05, 0.1, 0.2],  # 라벨 키워드를 담은 조각에 주는 가점 w
}
BASELINE = {"knn_k": None, "knn_tau": None, "rerank": True, "pool": 10,
            "kw_boost": 0.0, "gate": 0.25}   # 현재 운영 설정(src/config.py)

RULE_REFUSE = {TL.LABEL_OUT, TL.LABEL_SMALLTALK, TL.LABEL_CRISIS}   # 검색 없이 처리되는 라벨


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


# ══════════════════════════════════════════════════════════════════════
# 1) dump — 질문별 검색 후보·점수 저장 (모델 필요)
# ══════════════════════════════════════════════════════════════════════
def _memory_index(embed_model: str, chunk_size: int):
    """운영 Chroma 를 건드리지 않고, 다른 임베딩/청크 크기로 메모리 인덱스를 만든다."""
    import numpy as np
    from src.embeddings import EmbeddingModel
    from src.rag_pipeline import chunk_text, is_low_quality, load_documents
    overlap = max(20, chunk_size // 5)
    chunks, sources = [], []
    for doc in load_documents():
        for _pg, seg in doc["segments"]:
            for c in chunk_text(seg, chunk_size=chunk_size, overlap=overlap):
                if not is_low_quality(c):
                    chunks.append(c)
                    sources.append(doc["source"])
    emb = EmbeddingModel(embed_model)
    emb.fit(chunks)
    t0 = time.time()
    mat = np.asarray(emb.encode(chunks), dtype="float32")
    mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    print(f"[dump] {len(chunks)} 조각 임베딩 {time.time() - t0:.0f}s ({emb.backend})")

    def search(q: str, n: int):
        v = np.asarray(emb.encode([q])[0], dtype="float32")
        v /= (np.linalg.norm(v) + 1e-9)
        sims = mat @ v
        idx = np.argsort(-sims)[:n]
        return [{"text": chunks[i], "source": sources[i], "emb": float(sims[i])} for i in idx]
    return search, emb.backend, len(chunks)


def cmd_dump(args):
    from src.reranker import Reranker
    rows = _load_jsonl(GT_FILE) + _load_jsonl(ADV_FILE)
    if args.embed or args.chunk_size:
        from src import config
        search, backend, n_chunks = _memory_index(args.embed or config.EMBED_MODEL,
                                                  args.chunk_size or config.CHUNK_SIZE)
        setting = f"{args.embed or config.EMBED_MODEL}|chunk{args.chunk_size or config.CHUNK_SIZE}"
    else:
        from src import config
        from src.rag_pipeline import RagPipeline
        rag = RagPipeline(use_rerank=False)
        n_chunks = rag.index()

        def search(q, n):
            return [{"text": r.text, "source": r.source, "emb": float(r.score)}
                    for r in rag._vector_search(q, n)]
        backend = f"{rag.backend}/{rag.embedder.backend}"
        setting = f"{config.EMBED_MODEL}|chunk{config.CHUNK_SIZE}(운영 인덱스)"
    rr = Reranker()
    print(f"[dump] 설정={setting} · 재랭커={'ON' if rr.available else '없음(임베딩 점수만)'}")
    out = []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        cands = search(r["q"], POOL_MAX)
        rerank = None
        if rr.available and cands:
            scores = dict(rr.rerank(r["q"], [c["text"] for c in cands]))
            rerank = [float(scores[j]) for j in range(len(cands))]
        out.append({**r, "cands": cands, "rerank": rerank})
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}  ({time.time() - t0:.0f}s)")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(ch if ch.isalnum() else "_" for ch in setting)[:80]
    path = Path(args.out) if args.out else CACHE_DIR / f"{slug}.json"
    meta = {"setting": setting, "backend": backend, "n_chunks": n_chunks,
            "reranker": rr.model_name if rr.available else None,
            "created": time.strftime("%Y-%m-%d %H:%M"), "pool": POOL_MAX}
    path.write_text(json.dumps({"meta": meta, "rows": out}, ensure_ascii=False), encoding="utf-8")
    print(f"[dump] 저장: {path}  ({len(out)}문항, {time.time() - t0:.0f}s)")


# ══════════════════════════════════════════════════════════════════════
# 2) cv — 분할 · 학습 · 선택 · 테스트
# ══════════════════════════════════════════════════════════════════════
def gold_label(r: dict) -> str:
    return TL.GOLD_TO_LABEL.get(r["topic"], r["topic"])


def split_50_25_25(rows: list[dict], seed: int):
    """주제(라벨)별 비율을 유지하는 50/25/25 분할.
    각 주제 안에서 섞은 뒤 (순번+난수)/n 을 키로 전체를 정렬하고 앞에서부터 자른다
    → 모든 주제가 학습·검증·테스트에 고르게 퍼진다."""
    rng = random.Random(seed)
    by = defaultdict(list)
    for r in rows:
        by[gold_label(r)].append(r)
    keyed = []
    for _lab, items in sorted(by.items()):
        items = items[:]
        rng.shuffle(items)
        n = len(items)
        keyed += [((i + rng.random()) / n, r) for i, r in enumerate(items)]
    keyed.sort(key=lambda x: x[0])
    ordered = [r for _, r in keyed]
    n = len(ordered)
    a, b = round(n * 0.5), round(n * 0.75)
    return ordered[:a], ordered[a:b], ordered[b:]


def fit_fallback(train: list[dict], k: int) -> TL.SimilarQuestionFallback:
    """학습 질문으로 유사 질문 분류기 학습(검증·테스트 질문은 보지 않음)."""
    return TL.SimilarQuestionFallback(k).fit([r["q"] for r in train],
                                            [gold_label(r) for r in train])


def _prep(rows, fb=None, tau: float = 0.0):
    """질문 라벨(키워드 → 없으면 유사 질문)과 후보 조각의 '라벨 키워드 포함' 여부를 미리 계산."""
    out = []
    for r in rows:
        lab = TL.classify(r["q"], fb, tau)
        flags = ([TL.chunk_has_topic(c["text"], lab.label) for c in r["cands"]]
                 if lab.label in TL.TOPICS else [False] * len(r["cands"]))
        out.append((r, lab, flags))
    return out


def _rank(r, flags, rerank: bool, pool: int, w: float):
    """후보 → (상위 3개 텍스트, 1위의 원점수). 순위는 점수 + 키워드 가점."""
    cands = r["cands"][:pool]
    use_rr = rerank and r.get("rerank") is not None
    base = [(r["rerank"][i] if use_rr else c["emb"]) for i, c in enumerate(cands)]
    order = sorted(range(len(cands)), key=lambda i: base[i] + (w if flags[i] else 0.0),
                   reverse=True)
    top3 = [cands[i]["text"] for i in order[:3]]
    return top3, (base[order[0]] if order else 0.0)


def _evaluate(prepped, hp: dict, gate: float) -> dict:
    """한 설정의 지표. in=복지 질문, out=범위 밖 질문."""
    n_in = n_out = 0
    hit1 = hit3 = answered_in = refused_out = label_ok = 0
    per_topic = defaultdict(lambda: [0, 0])
    for r, lab, flags in prepped:
        gl = gold_label(r)
        top3, top_score = _rank(r, flags, hp["rerank"], hp["pool"], hp["kw_boost"])
        refused = lab.label in RULE_REFUSE or top_score < gate
        final = lab.label if lab.label in RULE_REFUSE else (TL.LABEL_OUT if refused else lab.label)
        if r["scope"] == "in":
            n_in += 1
            kw = r["gold_keyword"]
            h1 = bool(top3) and kw in top3[0]
            h3 = any(kw in t for t in top3)
            hit1 += h1
            hit3 += h3
            answered_in += not refused
            per_topic[gl][0] += h3
            per_topic[gl][1] += 1
        else:
            n_out += 1
            refused_out += refused
        label_ok += (final == gl)
    ans = answered_in / n_in if n_in else 0.0
    ref = refused_out / n_out if n_out else 0.0
    return {
        "n": n_in + n_out,
        "hit1": hit1 / n_in if n_in else 0.0,
        "hit3": hit3 / n_in if n_in else 0.0,
        "answered_in": ans,                      # 복지 질문을 (잘못 거절하지 않고) 답한 비율
        "refused_out": ref,                      # 범위 밖 질문을 거절한 비율
        "gate_bacc": (ans + ref) / 2,            # 게이트 균형 정확도
        "label_acc": label_ok / (n_in + n_out) if (n_in + n_out) else 0.0,
        "per_topic_hit3": {k: v[0] / v[1] for k, v in per_topic.items() if v[1]},
    }


def _fit_gate(prepped, hp) -> float:
    """학습 데이터에서 게이트 임계값 학습: 균형 정확도(복지 답변율·범위 밖 거절율 평균) 최대.
    동점이면 더 낮은 임계값(=복지 질문을 덜 거절)."""
    pts = []                                   # (1위 점수, in?, 규칙으로 이미 거절?)
    for r, lab, f in prepped:
        top = _rank(r, f, hp["rerank"], hp["pool"], hp["kw_boost"])[1]
        pts.append((top, r["scope"] == "in", lab.label in RULE_REFUSE))
    n_in = sum(1 for p in pts if p[1]) or 1
    n_out = sum(1 for p in pts if not p[1]) or 1
    tops = sorted({p[0] for p in pts})
    cands = [0.0] + [(a + b) / 2 for a, b in zip(tops, tops[1:])] + ([tops[-1] + 1e-3] if tops else [])
    best_g, best = 0.0, -1.0
    for g in cands:
        ans = sum(1 for t, i, rule in pts if i and not rule and t >= g) / n_in
        ref = sum(1 for t, i, rule in pts if not i and (rule or t < g)) / n_out
        m = (ans + ref) / 2
        if m > best + 1e-9:
            best_g, best = g, m
    return round(best_g, 4)


def _objective(m: dict) -> float:
    """검증 선택 기준 = (라벨 정확도 + Hit@1 + 게이트 균형 정확도) / 3."""
    return (m["label_acc"] + m["hit1"] + m["gate_bacc"]) / 3


def _combos(has_rerank: bool):
    for k in GRID["knn_k"]:
        for tau in GRID["knn_tau"]:
            for rr in GRID["rerank"]:
                if rr and not has_rerank:
                    continue
                for pool in GRID["pool"]:
                    for w in GRID["kw_boost"]:
                        yield {"knn_k": k, "knn_tau": tau, "rerank": rr,
                               "pool": pool, "kw_boost": w}


def _adv_eval(adv_rows, fb, hp, gate) -> dict:
    """거짓 유도 질문(검색 단계): '없는 제도'·'문서에 없는 세부정보' 를 게이트가 거절했나."""
    by = defaultdict(lambda: [0, 0])
    for r, lab, flags in _prep(adv_rows, fb, hp.get("knn_tau") or 0.0):
        _t, top = _rank(r, flags, hp["rerank"], hp["pool"], hp["kw_boost"])
        refused = lab.label in RULE_REFUSE or top < gate
        by[r["adv_type"]][0] += refused
        by[r["adv_type"]][1] += 1
    return {k: v[0] / v[1] for k, v in by.items()}


def cmd_cv(args):
    paths = sorted(glob.glob(str(CACHE_DIR / "*.json"))) if not args.caches else args.caches
    if not paths:
        sys.exit("cv_cache 가 없습니다. 먼저 서버에서:  python eval_cv.py dump")
    caches = []
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        caches.append((d["meta"], d["rows"]))
    print(f"[cv] 검색 설정 {len(caches)}개: " + ", ".join(m["setting"] for m, _ in caches))

    gt_qs = [r["q"] for r in _load_jsonl(GT_FILE)]
    results = []
    for rep in range(args.repeats):
        seed = args.seed + rep
        ref_rows = [r for r in caches[0][1] if r.get("scope") in ("in", "out")]
        tr, va, te = split_50_25_25(ref_rows, seed)
        split_q = ({r["q"] for r in tr}, {r["q"] for r in va}, {r["q"] for r in te})
        best = None
        for ci, (meta, rows) in enumerate(caches):
            gt = [r for r in rows if r.get("scope") in ("in", "out")]
            TR = [r for r in gt if r["q"] in split_q[0]]
            VA = [r for r in gt if r["q"] in split_q[1]]
            has_rr = any(r.get("rerank") for r in gt)
            fb_cache = {}
            for hp in _combos(has_rr):
                key = (hp["knn_k"], hp["knn_tau"])
                if key not in fb_cache:
                    fb = fit_fallback(TR, hp["knn_k"])
                    # 학습 질문 자신은 자기와 가장 비슷하므로(누수) 학습 쪽 라벨은 키워드만으로
                    fb_cache[key] = (fb, _prep(TR), _prep(VA, fb, hp["knn_tau"]))
                fb, ptr, pva = fb_cache[key]
                gate = _fit_gate(ptr, hp)
                mv = _evaluate(pva, hp, gate)
                score = _objective(mv)
                if best is None or score > best["val_obj"] + 1e-9:
                    best = {"cache": ci, "hp": {**hp, "gate": gate}, "fb": fb,
                            "val_obj": score, "val": mv}
        # 테스트: 선택된 설정 1회 + 같은 테스트에서 기준선(운영 설정)
        meta, rows = caches[best["cache"]]
        TE = [r for r in rows if r.get("scope") in ("in", "out") and r["q"] in split_q[2]]
        pte = _prep(TE, best["fb"], best["hp"]["knn_tau"])
        test = _evaluate(pte, best["hp"], best["hp"]["gate"])
        fb_examples = [{"q": r["q"], "near": lab.matched[0], "label": lab.label,
                        "gold": gold_label(r), "sim": round(lab.score, 2)}
                       for r, lab, _f in pte if lab.rule.startswith("similar")][:8]
        base_rows = [r for r in caches[0][1] if r.get("scope") in ("in", "out") and r["q"] in split_q[2]]
        base_rr = BASELINE["rerank"] and any(r.get("rerank") for r in base_rows)
        base_hp = {**BASELINE, "rerank": base_rr}
        baseline = _evaluate(_prep(base_rows, None), base_hp, BASELINE["gate"])
        adv_rows = [r for r in rows if r.get("scope") == "adv"]
        adv = _adv_eval(adv_rows, best["fb"], best["hp"], best["hp"]["gate"]) if adv_rows else {}
        adv_base = (_adv_eval([r for r in caches[0][1] if r.get("scope") == "adv"], None,
                              base_hp, BASELINE["gate"]) if adv_rows else {})
        results.append({"repeat": rep + 1, "seed": seed, "sizes": [len(s) for s in split_q],
                        "setting": meta["setting"], "hp": best["hp"],
                        "fallback_examples": fb_examples, "val": best["val"],
                        "test": test, "baseline_test": baseline,
                        "adv_refused": adv, "adv_refused_baseline": adv_base})
        print(f"[cv] 반복 {rep + 1}/{args.repeats} seed={seed} 선택={best['hp']} "
              f"→ test Hit@1 {test['hit1']:.2f} 라벨 {test['label_acc']:.2f} "
              f"(기준선 Hit@1 {baseline['hit1']:.2f} 라벨 {baseline['label_acc']:.2f})")
    meta_all = [m for m, _ in caches]
    (EVAL_DIR / "cv_results.json").write_text(
        json.dumps({"caches": meta_all, "grid": GRID, "baseline": BASELINE,
                    "n_gt": len(gt_qs), "results": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    _write_report(meta_all, results)
    print(f"[cv] 보고서: {EVAL_DIR / 'cv_report.md'}")


def _ms(vals):
    vals = list(vals)
    if not vals:
        return "—"
    m = st.mean(vals)
    s = st.stdev(vals) if len(vals) > 1 else 0.0
    return f"{m * 100:.1f}% ± {s * 100:.1f}"


def _write_report(metas, results):
    K = [("label_acc", "라벨 정확도(14개 라벨)"), ("hit1", "Hit@1"), ("hit3", "Hit@3"),
         ("answered_in", "복지 질문 답변율(잘못 거절 안 함)"), ("refused_out", "범위 밖 거절율"),
         ("gate_bacc", "게이트 균형 정확도")]
    L = ["# 복지 질문(RAG) 5회 반복 검증 리포트 (자동 생성)", "",
         f"- 생성: {time.strftime('%Y-%m-%d %H:%M')} · 재현: `python eval_cv.py cv`",
         f"- 데이터: `ground_truth_rag.jsonl` 200문항(복지 150 + 범위 밖 50) → "
         f"주제 비율 유지 **학습 50% / 검증 25% / 테스트 25%**, 시드 {results[0]['seed']}~{results[-1]['seed']} 로 {len(results)}회 반복",
         "- 검색 설정 후보: " + "; ".join(f"`{m['setting']}` (재랭커: {m['reranker'] or '없음'}, {m['backend']})" for m in metas),
         "", "## 1) 테스트 결과 (평균 ± 표준편차)", "",
         "| 지표 | 현재 운영 설정(기준선) | 검증으로 고른 설정 |", "|---|---|---|"]
    for k, name in K:
        L.append(f"| {name} | {_ms(r['baseline_test'][k] for r in results)} | "
                 f"**{_ms(r['test'][k] for r in results)}** |")
    L += ["", "> 기준선 = 지금 서비스 설정(재랭커 ON, 후보 10, 키워드 가점 0, 게이트 0.25, 유사 질문 분류 없음)을 "
          "**같은 테스트 문항**에서 측정한 값.", ""]
    adv_types = sorted({k for r in results for k in r["adv_refused"]})
    if adv_types:
        name = {"false_premise": "틀린 전제", "nonexistent": "없는 제도", "unanswerable": "문서에 없는 세부정보"}
        L += ["## 2) 거짓 유도 질문 — 검색 단계에서 거절한 비율", "",
              "| 유형 | 기준선 | 고른 설정 | 바람직한 방향 |", "|---|---|---|---|"]
        for t in adv_types:
            want = "답하되 전제를 바로잡기(거절 낮아도 됨)" if t == "false_premise" else "높을수록 좋음"
            L.append(f"| {name.get(t, t)} | {_ms(r['adv_refused_baseline'].get(t, 0) for r in results)} | "
                     f"{_ms(r['adv_refused'].get(t, 0) for r in results)} | {want} |")
        L += ["", "> 검색 단계 지표만입니다. '실제 답변에 거짓이 섞였는가'(거짓 답변률)는 LLM 답변 생성이 "
              "필요해 다음 단계(④, GPU 서버)에서 측정합니다.", ""]
    L += ["## 3) 반복별 선택된 하이퍼파라미터", "",
          "| 반복 | 학습/검증/테스트 | 검색 설정 | 재랭커 | 후보 수 | 키워드 가점 w | 게이트(학습) | 유사 질문 k / 임계값 | 검증 점수 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        h = r["hp"]
        L.append(f"| {r['repeat']} | {'/'.join(map(str, r['sizes']))} | `{r['setting'].replace('|', ' · ')}` | "
                 f"{'ON' if h['rerank'] else 'OFF'} | {h['pool']} | {h['kw_boost']} | {h['gate']} | "
                 f"{h['knn_k']} / {h['knn_tau']} | {_objective(r['val']) * 100:.1f}% |")
    topics = sorted({t for r in results for t in r["test"]["per_topic_hit3"]})
    L += ["", "## 4) 주제별 테스트 Hit@3 (평균)", "", "| 주제 | 기준선 | 고른 설정 |", "|---|---|---|"]
    for t in topics:
        b = [r["baseline_test"]["per_topic_hit3"].get(t) for r in results]
        s = [r["test"]["per_topic_hit3"].get(t) for r in results]
        L.append(f"| {t} | {_ms(x for x in b if x is not None)} | {_ms(x for x in s if x is not None)} |")
    L += ["", "## 5) 유사 질문 분류 예시 (마지막 반복 테스트 — 키워드가 없던 질문)", "",
          "| 질문 | 가장 비슷한 학습 질문 | 유사도 | 판정 | 정답 |", "|---|---|---|---|---|"]
    for e in results[-1]["fallback_examples"]:
        mark = "✅" if e["label"] == e["gold"] else "❌"
        L.append(f"| {e['q']} | {e['near']} | {e['sim']} | {e['label']} {mark} | {e['gold']} |")
    L += ["", "## 6) 예측 점수와 판정 규칙(설명 가능성)", "",
          "1. **라벨**: `src/topic_labels.py` — 위기 → 잡담 → 범위 밖 → 10개 주제(키워드 점수 최대) → "
          "키워드가 없으면 학습 질문 유사도(k개 투표, 1위 유사도 ≥ 임계값) → 그래도 없으면 기타 복지. "
          "출력은 항상 14개 라벨 중 하나. 키워드 점수 = 문서 용어 일치 수(3글자 이상 2점, 그 외 1점).",
          "2. **관련성 점수**: 재랭커(`bge-reranker-v2-m3`) 로짓의 시그모이드(0~1). 재랭커를 끄면 임베딩 코사인 유사도.",
          "3. **순위**: 관련성 점수 + w × [조각이 질문 라벨의 키워드를 포함]. w 는 검증으로 선택.",
          "4. **거절(게이트)**: 1위 조각의 관련성 점수가 임계값 미만이면 답을 지어내지 않고 주민센터 안내. "
          "임계값은 학습 데이터에서 '복지 질문 답변율'과 '범위 밖 거절율'의 평균이 최대가 되는 값으로 학습.",
          "5. **Hit@K 판정**: 정답지의 정답 키워드(gold_keyword)가 상위 K개 조각에 들어 있으면 정답(기존 리포트와 같은 기준).",
          "", "## 7) 한계", "",
          "- 테스트가 반복마다 50문항(주제당 약 3~4문항)이라 주제별 수치는 흔들림이 큽니다 → 표준편차를 함께 봅니다.",
          "- Hit@K 는 '근거가 검색됐는가'까지만 봅니다. 답변의 사실 정확도·거짓 답변률은 ④(LLM 생성 평가)에서 측정합니다.",
          "", "*이 파일은 `eval_cv.py cv` 가 자동 생성합니다. 손으로 고치지 마세요.*"]
    (EVAL_DIR / "cv_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="질문별 검색 후보·점수 저장(모델 필요, 서버에서 1회)")
    d.add_argument("--embed", help="다른 임베딩 모델(메모리 인덱스). 생략 시 운영 인덱스")
    d.add_argument("--chunk-size", type=int, help="다른 청크 크기(메모리 인덱스)")
    d.add_argument("--out", help="저장 경로(기본 data/eval/cv_cache/<설정>.json)")
    c = sub.add_parser("cv", help="50/25/25 × 반복 검증 + 하이퍼파라미터 선택")
    c.add_argument("--repeats", type=int, default=5)
    c.add_argument("--seed", type=int, default=42)
    c.add_argument("--caches", nargs="*", help="사용할 캐시 파일(기본: cv_cache/*.json 전부)")
    args = ap.parse_args()
    {"dump": cmd_dump, "cv": cmd_cv}[args.cmd](args)


if __name__ == "__main__":
    main()
