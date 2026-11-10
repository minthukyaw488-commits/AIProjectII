"""
LLM 답변 후처리 — 지어낸 내용이 어르신께 그대로 가지 않도록 한다.

  · clean_answer: '(예시)' 처럼 프롬프트의 예시 표기를 베낀 줄을 지운다.
  · drop_unverified_phones: 참고 자료에 없는 전화번호가 든 줄을 지운다
    (작은 모델이 그럴듯한 번호를 만들어내는 것을 막는다).
줄을 지워 답이 비면 주민센터 안내로 대신한다.
"""
from __future__ import annotations
import re

FALLBACK = "가까운 주민센터(행정복지센터)에 문의하시면 자세히 안내받으실 수 있습니다."
_PHONE = re.compile(r"(?<!\d)(0\d{1,2})[-.\s)]?(\d{3,4})[-.\s]?(\d{4})(?!\d)")
_EXAMPLE = re.compile(r"\(\s*예시\s*\)|예시\s*\)|^\s*예시\s*[:：]")


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _finish(lines) -> str:
    out = "\n".join(lines).strip()
    return out if re.search(r"[가-힣]", out) else FALLBACK


def clean_answer(answer: str) -> str:
    if not answer:
        return answer
    lines = [ln for ln in answer.splitlines() if not _EXAMPLE.search(ln)]
    return _finish(lines)


def drop_unverified_phones(answer: str, contexts) -> str:
    """답변의 전화번호가 참고 자료(contexts)에 없으면 그 줄을 지운다."""
    if not answer:
        return answer
    ctx = _digits(" ".join(contexts or []))
    kept, dropped = [], False
    for ln in answer.splitlines():
        nums = ["".join(m.groups()) for m in _PHONE.finditer(ln)]
        if any(n not in ctx for n in nums):
            dropped = True
            continue
        kept.append(ln)
    if not dropped:
        return answer
    out = _finish(kept)
    if out != FALLBACK and "주민센터" not in out:
        out += "\n- 정확한 연락처는 가까운 **주민센터(행정복지센터)**에서 확인해 주세요."
    return out
