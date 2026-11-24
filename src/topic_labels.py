"""복지 질문 라벨 체계(label) + 라벨별 키워드(label keyword) — 단일 기준.

교수님 피드백 1: "모델 출력은 사전에 정의한 정답 라벨 범위 안에 있어야 하고,
라벨과 키워드를 명확히 정의한다(형태소 분석은 생략 가능)."

  · 라벨은 아래 LABELS 14개뿐이다. classify() 는 이 밖의 값을 절대 돌려주지 않는다.
  · 키워드는 평가 질문이 아니라 보건복지부 사업안내 문서의 '용어'에서 골랐다
    (평가 데이터에 맞춰 고르면 점수가 부풀려지므로). 자세한 설명: docs/LABELS.md
  · 형태소 분석 없이 '공백 제거 후 부분 문자열' 로 비교한다
    ("기초 연금" == "기초연금", "치매검사를" ⊃ "치매").

판정 순서(위에서 먼저 걸리면 그 라벨):
  1) 위기     — src/crisis.is_crisis       (검색·생성 없이 109/119/129 고정 안내)
  2) 잡담     — src/router.is_smalltalk    (인사·감사)
  3) 범위 밖  — src/router.is_off_domain   (주식·여행 등 복지와 무관)
  4) 복지 10개 주제 — 키워드 점수가 가장 높은 주제
  5) 기타 복지 — 복지 관련이지만 10개 주제 키워드가 없음 → 문서 검색(관련성 게이트)에 맡김
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── 10개 복지 주제 (평가 정답지 data/eval/ground_truth_rag.jsonl 의 topic 과 같은 이름) ──
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "기초연금": ("기초연금", "국민연금공단", "소득인정액", "선정기준액", "기준연금액", "연금"),
    "노인맞춤돌봄": ("노인맞춤돌봄", "맞춤돌봄", "돌봄서비스", "생활지원사", "안부확인",
                  "가사지원", "말벗", "돌봄기관", "돌봄"),
    "응급안전안심": ("응급안전", "안심서비스", "응급호출", "화재감지", "댁내장비",
                  "활동감지", "응급"),
    "치매안심": ("치매안심센터", "치매", "선별검사", "인지", "기억력", "깜빡"),
    "무료급식": ("경로식당", "무료급식", "식사배달", "도시락", "밑반찬", "결식", "노인급식", "급식", "식사"),
    "에너지바우처": ("에너지바우처", "바우처", "난방비", "냉방비", "난방", "냉방",
                  "전기요금", "가스요금", "연탄"),
    "정신건강": ("정신건강", "우울", "외로", "자살예방", "마음상담", "불면", "고독"),
    "방문건강관리": ("방문건강", "방문간호", "건강관리", "혈압", "당뇨", "만성질환"),
    "노인일자리": ("노인일자리", "공익활동", "시니어클럽", "사회서비스형", "활동비",
                "노노케어", "일자리"),
    "경로우대": ("경로우대", "무임승차", "도시철도", "노인승차권", "노인교통비", "지하철", "무임",
             "교통", "철도", "할인"),
}

LABEL_CRISIS = "위기"
LABEL_SMALLTALK = "잡담"
LABEL_OUT = "범위 밖"
LABEL_OTHER = "기타 복지"

TOPICS: tuple[str, ...] = tuple(TOPIC_KEYWORDS)
LABELS: tuple[str, ...] = TOPICS + (LABEL_OTHER, LABEL_OUT, LABEL_SMALLTALK, LABEL_CRISIS)

# 평가 정답지의 out_of_scope → 범위 밖
GOLD_TO_LABEL = {**{t: t for t in TOPICS}, "out_of_scope": LABEL_OUT}


def _norm(text: str) -> str:
    return "".join((text or "").split())


@dataclass
class LabelResult:
    label: str                      # 항상 LABELS 중 하나
    score: float                    # 키워드 점수(주제일 때). 규칙 라벨은 1.0
    matched: list[str] = field(default_factory=list)   # 근거가 된 키워드
    rule: str = ""                  # 어떤 규칙으로 정했는가(설명용)


def keyword_score(text: str, topic: str) -> tuple[float, list[str]]:
    """주제 키워드 점수 = 일치한 키워드마다 (글자 수 3 이상이면 2점, 아니면 1점).
    긴 키워드(기초연금·치매안심센터)는 짧은 키워드(연금·인지)보다 특정적이라 가중치를 준다.
    겹치는 키워드(치매안심센터 ⊃ 치매)는 둘 다 센다 — 더 구체적인 표현에 자연스럽게 가점."""
    t = _norm(text)
    hits = [k for k in TOPIC_KEYWORDS[topic] if k in t]
    return float(sum(2 if len(k) >= 3 else 1 for k in hits)), hits


def topic_scores(text: str) -> dict[str, float]:
    return {tp: keyword_score(text, tp)[0] for tp in TOPICS}


def classify(text: str, fallback: "SimilarQuestionFallback | None" = None,
             tau: float = 0.0) -> LabelResult:
    """질문 → 라벨 하나(LABELS 범위 안). 동점이면 TOPIC_KEYWORDS 순서가 앞선 주제.
    키워드가 하나도 없으면(=기타 복지) fallback(학습 질문 유사도)이 있을 때 그것으로 정한다:
    가장 비슷한 학습 질문의 유사도가 tau 이상이면 그 질문들의 라벨, 아니면 기타 복지."""
    from .crisis import is_crisis
    from .router import is_off_domain, is_smalltalk

    if is_crisis(text):
        return LabelResult(LABEL_CRISIS, 1.0, [], "crisis.is_crisis")
    if is_smalltalk(text):
        return LabelResult(LABEL_SMALLTALK, 1.0, [], "router.is_smalltalk")
    if is_off_domain(text):
        return LabelResult(LABEL_OUT, 1.0, [], "router.is_off_domain")
    best, best_s, best_hits = None, 0.0, []
    for tp in TOPICS:
        s, hits = keyword_score(text, tp)
        if s > best_s:
            best, best_s, best_hits = tp, s, hits
    if best is None:
        if fallback is not None:
            lab, sim, near = fallback.predict(text)
            if sim >= tau and lab in LABELS:
                return LabelResult(lab, sim, [near], f"similar question (cos={sim:.2f})")
        return LabelResult(LABEL_OTHER, 0.0, [], "no topic keyword")
    return LabelResult(best, best_s, best_hits, "topic keywords")


def chunk_has_topic(chunk: str, topic: str) -> bool:
    """검색된 조각이 해당 주제 키워드를 하나라도 담고 있는가(검색 가점용)."""
    if topic not in TOPIC_KEYWORDS:
        return False
    return keyword_score(chunk, topic)[0] > 0


class SimilarQuestionFallback:
    """키워드가 없는 질문용 보조 분류기 — '학습 질문 중 가장 비슷한 k개'의 라벨 투표.

    어르신은 '끼니', '간호사가 와 주나요' 처럼 제도 이름 없이 묻는 경우가 많아
    문서 용어 키워드만으로는 라벨을 못 정한다. 학습(Train) 질문을 글자 2~3-gram
    TF-IDF 로 바꿔 두고, 새 질문과의 코사인 유사도로 가까운 질문을 찾는다.
    점수 = 1위 유사도(0~1) → '어떤 학습 질문과 얼마나 닮았는가'로 설명 가능.
    """

    def __init__(self, k: int = 3):
        self.k = k
        self._vec = None
        self._mat = None
        self._qs: list[str] = []
        self._labels: list[str] = []

    def fit(self, questions: list[str], labels: list[str]) -> "SimilarQuestionFallback":
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._qs = list(questions)
        self._labels = list(labels)
        self._vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), sublinear_tf=True)
        self._mat = self._vec.fit_transform([_norm(q) for q in self._qs])
        return self

    def predict(self, text: str) -> tuple[str, float, str]:
        """→ (라벨, 1위 유사도, 1위 학습 질문)."""
        if self._vec is None or not self._qs:
            return LABEL_OTHER, 0.0, ""
        sims = (self._vec.transform([_norm(text)]) @ self._mat.T).toarray()[0]
        order = sims.argsort()[::-1][: self.k]
        votes: dict[str, float] = {}
        for i in order:
            votes[self._labels[i]] = votes.get(self._labels[i], 0.0) + float(sims[i])
        lab = max(votes, key=votes.get)
        return lab, float(sims[order[0]]), self._qs[order[0]]


if __name__ == "__main__":
    for q in ["기초연금 얼마 받아요?", "치매 검사 어디서 해요?", "죽고 싶어요",
              "비트코인 어떻게 사요?", "안녕하세요", "장기요양 등급 신청"]:
        r = classify(q)
        print(f"{q!r:28} → {r.label:8} score={r.score} {r.matched} ({r.rule})")
