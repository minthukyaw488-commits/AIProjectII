"""
사람 맞춤형(개인 맞춤) MVP — 복지 자격 조건을 '표(규칙)'로 구조화한 모듈.

RAG는 "질문에 맞는 문서를 찾아 답"하지만, 사람 맞춤형은 한 걸음 더 간다:
어르신의 프로필(나이·소득·거주지·가구·건강)을 받아, 받을 수 있는 복지를
'자동으로' 가려내 먼저 추천한다. 그 핵심이 이 규칙 표다.

여기 담긴 자격 기준은 대전 독거노인 관련 대표 복지의 '대략적' 조건이며,
정확한 금액·등급 기준은 반드시 공공문서(RAG)·주민센터로 최종 확인해야 한다.
→ 그래서 각 서비스에 verify_note(확인 안내)를 함께 둔다.

이 파일은 외부 라이브러리 없이(표준 라이브러리만) 동작한다 → 어디서나 데모 가능.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional

# 대전광역시 5개 자치구
DAEJEON_DISTRICTS = ["동구", "중구", "서구", "유성구", "대덕구"]


@dataclass
class Profile:
    """어르신 한 분의 기본 정보(동의 아래 수집)."""
    age: Optional[int] = None            # 나이(만)
    income_low: Optional[bool] = None    # 저소득(기초수급·차상위 등) 여부
    district: Optional[str] = None       # 거주 구 (DAEJEON_DISTRICTS 중 하나)
    living_alone: Optional[bool] = None  # 독거 여부
    mobility_issue: Optional[bool] = None  # 거동 불편 여부
    chronic_illness: Optional[bool] = None  # 만성질환·치매 우려 여부


@dataclass
class Welfare:
    """복지 서비스 하나의 자격 규칙."""
    name: str
    summary: str                 # 한 줄 설명
    min_age: Optional[int] = None
    need_income_low: bool = False
    need_living_alone: bool = False
    need_mobility: bool = False
    need_illness: bool = False
    daejeon_only: bool = True
    verify_note: str = "정확한 기준·금액은 주민센터 또는 관련 문서로 확인 필요"
    # 소프트 조건(있으면 가점/안내만, 자격 탈락 사유는 아님)
    soft_notes: list[str] = field(default_factory=list)


# ── 대전 독거노인 관련 대표 복지 규칙 표 ────────────────────────────
# (기준은 대략치. 실제 소득 하위 %·장기요양 등급 등은 문서로 확정)
WELFARE_TABLE: list[Welfare] = [
    Welfare(
        name="기초연금",
        summary="만 65세 이상·소득 하위 70%에게 매월 연금 지급",
        min_age=65, need_income_low=True,
        verify_note="소득인정액 하위 70% 기준 — 국민연금공단·주민센터 확인",
    ),
    Welfare(
        name="노인맞춤돌봄서비스",
        summary="돌봄이 필요한 어르신께 안전확인·생활교육·가사지원 등 제공",
        min_age=65, need_living_alone=True,
        verify_note="독거·취약 어르신 우선 — 읍면동 주민센터 신청",
        soft_notes=["독거이면 우선 대상", "거동 불편 시 지원 범위 확대"],
    ),
    Welfare(
        name="재가노인 식사배달",
        summary="결식 우려 저소득 어르신께 평일 식사 배달",
        min_age=60, need_income_low=True, need_living_alone=True,
        verify_note="만 60세 이상 저소득 독거 중심 — 구별 수행기관 상이",
        soft_notes=["거동 불편 시 우선"],
    ),
    Welfare(
        name="노인일자리 및 사회활동 지원",
        summary="만 65세 이상께 공익활동·사회서비스형 일자리 제공",
        min_age=65,
        verify_note="유형별(공익형/사회서비스형) 연령·소득 요건 상이",
    ),
    Welfare(
        name="장기요양보험(재가·시설)",
        summary="거동이 어려운 어르신께 요양보호사 방문·시설 이용 지원",
        min_age=65, need_mobility=True,
        verify_note="장기요양 등급 판정 필요 — 국민건강보험공단 신청",
        soft_notes=["만성질환 시 등급 가능성↑"],
    ),
    Welfare(
        name="치매검진·치매안심센터",
        summary="치매 조기검진과 치매 어르신·가족 지원",
        min_age=60,
        verify_note="보건소 치매안심센터 — 연 1회 무료검진 등",
        soft_notes=["만성질환·기억력 저하 시 적극 권장"],
    ),
    Welfare(
        name="독거노인 응급안전안심서비스",
        summary="댁내 감지기로 화재·응급 상황을 자동 감지·신고",
        min_age=65, need_living_alone=True,
        verify_note="상시 보호가 필요한 독거 어르신 대상 — 주민센터 신청",
    ),
    Welfare(
        name="노인복지관·경로당 이용",
        summary="여가·건강·식사·교육 프로그램 이용",
        min_age=60,
        verify_note="지역 복지관·경로당별 운영 상이",
    ),
]


def to_dict(w: Welfare) -> dict:
    """카탈로그(DB) 저장용 — 매칭에 쓰는 핵심 필드만."""
    return {"name": w.name, "summary": w.summary, "min_age": w.min_age,
            "need_income_low": w.need_income_low,
            "need_living_alone": w.need_living_alone,
            "need_mobility": w.need_mobility, "need_illness": w.need_illness,
            "verify_note": w.verify_note}


def _from_row(r: dict) -> Welfare:
    return Welfare(
        name=r["name"], summary=r.get("summary", ""), min_age=r.get("min_age"),
        need_income_low=bool(r.get("need_income_low")),
        need_living_alone=bool(r.get("need_living_alone")),
        need_mobility=bool(r.get("need_mobility")),
        need_illness=bool(r.get("need_illness")),
        verify_note=r.get("verify_note") or "")


def get_welfare_table() -> list[Welfare]:
    """복지 규칙표를 돌려준다. DB 카탈로그에 내용이 있으면 그걸 쓰고(Phase 4),
    없으면 코드 기본표(WELFARE_TABLE)로 폴백한다."""
    try:
        from src import db
        rows = db.list_welfare()
        if rows:
            return [_from_row(r) for r in rows]
    except Exception:                            # noqa: BLE001
        pass
    return WELFARE_TABLE


@dataclass
class MatchResult:
    welfare: Welfare
    status: str          # "eligible" | "maybe" | "not"
    reasons: list[str]   # 판정 근거


def _check_one(p: Profile, w: Welfare) -> MatchResult:
    """프로필 한 명 ↔ 복지 하나를 대조. 정보가 없으면 '확인 필요'."""
    reasons: list[str] = []
    unknown = False  # 판정에 필요한 정보가 비어 있는가

    # 거주지(대전) — 명시적으로 타지역이면 탈락
    if w.daejeon_only and p.district is not None and p.district not in DAEJEON_DISTRICTS:
        return MatchResult(w, "not", [f"대전 거주가 아님({p.district}) → 대전 사업 대상 아님"])

    # 나이
    if w.min_age is not None:
        if p.age is None:
            unknown = True
            reasons.append(f"나이 정보 필요(기준: 만 {w.min_age}세 이상)")
        elif p.age < w.min_age:
            return MatchResult(w, "not", [f"만 {w.min_age}세 미만({p.age}세) → 대상 아님"])
        else:
            reasons.append(f"만 {w.min_age}세 이상 충족({p.age}세)")

    # 저소득
    if w.need_income_low:
        if p.income_low is None:
            unknown = True
            reasons.append("소득(저소득 여부) 정보 필요")
        elif not p.income_low:
            return MatchResult(w, "not", ["저소득 요건 미해당 → 대상 아님"])
        else:
            reasons.append("저소득 요건 충족")

    # 독거
    if w.need_living_alone:
        if p.living_alone is None:
            unknown = True
            reasons.append("가구 형태(독거 여부) 정보 필요")
        elif not p.living_alone:
            return MatchResult(w, "not", ["독거 대상 사업 — 비독거 → 대상 아님"])
        else:
            reasons.append("독거 요건 충족")

    # 거동 불편
    if w.need_mobility:
        if p.mobility_issue is None:
            unknown = True
            reasons.append("거동 불편 여부 정보 필요")
        elif not p.mobility_issue:
            return MatchResult(w, "not", ["거동 불편 대상 — 해당 없음 → 대상 아님"])
        else:
            reasons.append("거동 불편 요건 충족")

    # 소프트 조건(안내만)
    if p.mobility_issue and "거동 불편 시 우선" in " ".join(w.soft_notes):
        reasons.append("※ 거동 불편 → 우선 대상")
    if p.chronic_illness and any("만성질환" in s for s in w.soft_notes):
        reasons.append("※ 만성질환 → 적극 권장")

    status = "maybe" if unknown else "eligible"
    return MatchResult(w, status, reasons)


def match_profile(p: Profile, table: list[Welfare] | None = None) -> list[MatchResult]:
    """프로필을 전체 복지 표와 대조해 결과 리스트 반환.
    table 을 안 주면 DB 카탈로그(있으면)·기본표를 자동 선택한다."""
    if table is None:
        table = get_welfare_table()
    return [_check_one(p, w) for w in table]


def recommend(p: Profile, table: list[Welfare] | None = None):
    """상태별로 묶어 돌려준다: (받을 수 있음, 확인 필요, 해당 없음)."""
    res = match_profile(p, table)
    eligible = [r for r in res if r.status == "eligible"]
    maybe = [r for r in res if r.status == "maybe"]
    not_elig = [r for r in res if r.status == "not"]
    return eligible, maybe, not_elig
