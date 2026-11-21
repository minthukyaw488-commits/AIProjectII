"""
LLM client.

Two interchangeable backends expose the same interface (`.available`, `.model`,
`.generate(...)`):

  * OpenAILLM  - GPT-4o via the OpenAI API (default). General language ability;
                 grounded by the RAG index so answers stay on 대전 공공데이터.
  * LocalLLM   - Ollama running a local model (http://localhost:11434), kept as
                 a fallback when no API key is set.

`make_llm()` picks the backend from config (LLM_BACKEND), falling back to
Ollama, then to a transparent template responder so the full pipeline can
always be demonstrated. The template simply relays the retrieved welfare text
and is clearly marked so it is never mistaken for a real model answer.
"""
from __future__ import annotations
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import List

from . import config

# Retry on HTTP 429 (rate limit). Free API tiers (e.g. Groq TPM caps) return
# 429 with a "try again in Xs" hint; wait that long and retry so batch jobs
# (eval, comparison) finish instead of dropping to the fallback.
_MAX_RETRIES = 5
_RETRY_AFTER_RE = re.compile(r"try again in ([0-9.]+)\s*s", re.IGNORECASE)


def _retry_wait(detail: str, attempt: int) -> float:
    m = _RETRY_AFTER_RE.search(detail or "")
    if m:
        return min(float(m.group(1)) + 0.5, 30.0)
    return min(2.0 ** attempt, 30.0)   # exponential backoff, capped

# Some API gateways sit behind Cloudflare, which blocks urllib's default
# "Python-urllib/x" User-Agent with HTTP 403 (error 1010). Send a normal
# browser-like UA so requests get through.
_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/122.0.0.0 Safari/537.36")


ANSWER_SYSTEM_PROMPT = (
    "당신은 대전광역시 독거노인을 돕는 친절한 복지 안내 도우미입니다.\n"
    "규칙:\n"
    "1) 아래 '참고 자료'에 실제로 적힌 내용만 근거로 답합니다. "
    "자료에 없는 금액·전화번호·기관명·조건을 절대 지어내지 않습니다.\n"
    "2) 참고 자료에서 질문과 관련된 내용을 찾을 수 없으면, 다른 말은 하지 말고 "
    "'가까운 주민센터(행정복지센터)에 문의하시면 자세히 안내받으실 수 있습니다.'라고만 답합니다.\n"
    "3) 반드시 한국어로만 답합니다. 영어 단어·알파벳·웹주소(URL)를 쓰지 않으며, "
    "참고 자료에 영문 기관명이나 주소가 있어도 한글로 옮기거나 생략합니다.\n"
    "3-1) 질문의 핵심 주제가 참고 자료의 주제와 다르면(예: 반려동물·자동차·주식·"
    "여행 등 노인복지와 무관한 질문) 억지로 자료를 갖다 붙이지 말고, 2)의 안내 문장만 "
    "답합니다.\n"
    "4) 어르신이 눈으로 읽기 쉽도록 아래 형식을 반드시 지킵니다:\n"
    "   - 한 줄에 한 가지만, 짧은 문장으로 씁니다(긴 문장 금지).\n"
    "   - 핵심은 '- '로 시작하는 짧은 항목(불릿) 2~4개로 정리합니다.\n"
    "   - 대상·준비물·신청 장소 같은 중요한 말은 **굵게** 표시합니다.\n"
    "   - 항목은 줄바꿈으로 띄워 여백을 둡니다. 한 문단으로 길게 붙여 쓰지 않습니다.\n"
    "   - 전체는 짧게, 핵심만. 여러 기관을 길게 나열하지 않습니다.\n"
    "5) 비용(무료/유료·금액)이나 자격을 물으면, 참고 자료에 명시된 경우에만 그대로 "
    "답합니다. 자료에 '무료'나 금액이 없으면 '국가 보조금' 같은 추측을 하지 말고 "
    "주민센터 문의로 안내합니다.\n"
    "6) 어려운 제도 이름은 어르신이 한눈에 알 수 있도록 쉬운 말로 풀어 줍니다. "
    "예: '에너지바우처'는 '냉·난방비 지원', '장기요양보험'은 '요양 돌봄 지원'처럼 "
    "쉬운 설명을 함께 적습니다.\n"
    "7) 전화번호·주소·기관 이름은 참고 자료에 그대로 적힌 것만 씁니다. 자료에 없으면 "
    "지어내지 말고 '가까운 주민센터(행정복지센터)'로 안내합니다. '예시'라는 말이나 "
    "괄호 속 설명 표시를 답변에 쓰지 않습니다.\n"
    "8) 질문 속 숫자·나이·금액·요일·조건을 그대로 믿지 않습니다. 참고 자료와 다르면 "
    "'아닙니다. 자료에는 ○○로 되어 있습니다'처럼 먼저 바로잡고, 자료에 없으면 "
    "'자료에서 확인되지 않습니다'라고 말합니다. 질문에 나온 제도·사업 이름이 참고 자료에 "
    "없으면 그 제도가 있다고 가정하지 말고, 다른 제도의 신청 방법을 옮겨 붙이지 않습니다.\n"
    "[답변 모양 참고 — 아래 내용은 모양만 참고하고 그대로 옮기지 않습니다]\n"
    "질문: 기초연금은 어떻게 신청하나요?\n"
    "답변:\n"
    "- **대상**: 만 65세 이상 어르신\n"
    "- **준비물**: 신분증, 통장 사본\n"
    "- **신청 장소**: 가까운 **주민센터** 또는 **국민연금공단** 지사"
)


# ── 맞춤형(개인화): 프로필을 시스템 프롬프트에 주입 ────────────────────────────
# 나이 요건이 있는 대표 복지(질문에 이 말이 있고 어르신 나이가 미달이면 자격 안내).
_AGE_MIN_SERVICES = [
    ("기초연금", 65), ("노인맞춤돌봄", 65), ("노인 맞춤 돌봄", 65),
    ("노인일자리", 65), ("노인 일자리", 65), ("노인장기요양", 65),
    ("장기요양", 65), ("경로우대", 65), ("경로 우대", 65),
]


def _profile_sentence(profile: dict) -> str:
    """프로필 dict → 사람이 읽는 한 줄 요약(시스템 프롬프트용)."""
    parts = []
    age = profile.get("age")
    if age is not None:
        parts.append(f"{age}세")
    if profile.get("district"):
        parts.append(f"대전 {profile['district']} 거주")
    if profile.get("living_alone") is True:
        parts.append("독거(혼자 거주)")
    health = []
    if profile.get("mobility_issue") is True:
        health.append("거동 불편")
    if profile.get("chronic_illness") is True:
        health.append("만성질환")
    if health:
        parts.append("건강: " + "·".join(health))
    if profile.get("income_low") is True:
        parts.append("저소득")
    return ", ".join(parts)


def _eligibility_note(profile: dict, question: str) -> str:
    """질문한 서비스의 나이 요건을 어르신이 못 채우면, 정중히 설명하고 대안을
    안내하도록 지시하는 문장을 돌려준다(없으면 빈 문자열)."""
    try:
        age = int(profile.get("age"))
    except (TypeError, ValueError):
        return ""
    q = question or ""
    for svc, minage in _AGE_MIN_SERVICES:
        if svc in q and age < minage:
            return (f"\n[자격 주의] 이 어르신은 {age}세로 '{svc}'의 나이 요건"
                    f"(만 {minage}세 이상)에 못 미칩니다. 신청이 어려운 이유를 "
                    "정중히 한두 문장으로 설명하고, 지금 나이에 받을 수 있는 복지"
                    "(예: 저소득·건강·돌봄 관련)를 1~2가지 대안으로 안내하세요.")
    return ""


def build_personal_system(profile, question: str = "",
                          base: str = ANSWER_SYSTEM_PROMPT) -> str:
    """어르신 프로필을 시스템 프롬프트에 주입해 '맞춤형' 답변을 유도한다.
    프로필이 없으면 기본 프롬프트를 그대로 돌려준다."""
    if not profile:
        return base
    summary = _profile_sentence(profile)
    if not summary:
        return base
    block = (
        "\n\n[상담 대상 어르신 정보]\n"
        f"- {summary}\n"
        "위 어르신에게 답할 때:\n"
        "- 나이·거주지(구)·건강 상태에 맞춰, 참고 자료를 근거로 구체적으로 안내합니다.\n"
        "- 거동이 불편하면 방문·전화 신청 방법을 우선 알려 줍니다.\n"
        "- 거주 '구'가 있으면 그 구의 주민센터·기관 이용을 안내합니다.\n"
        "- 나이 요건이 맞지 않는 서비스를 물으면, 안 되는 이유를 정중히 설명하고 "
        "받을 수 있는 다른 복지를 안내합니다."
    )
    return base + block + _eligibility_note(profile, question)


import re as _re
_URL_RE = _re.compile(r"(?:https?://|www\.)[^\s)>\]]+", _re.IGNORECASE)


def clean_answer(text: str) -> str:
    """답변에서 URL(웹주소)을 결정적으로 제거한다.

    시스템 프롬프트가 URL 금지를 지시하지만, 작은 온디바이스 모델(2.4B)이 검색
    문서의 주소(예: http://online.bokjiro.go.kr)를 그대로 옮겨 적는 경우가 있다.
    어르신용이라 URL은 쓸모가 없고 프롬프트 규칙에도 어긋나므로, 생성 후 제거한다.
    (평가지표 fact-coverage 로 드러난 실제 버그를 생성 단계에서 차단.)"""
    if not text:
        return text
    t = _URL_RE.sub("", text)
    t = _re.sub(r"\(\s*\)", "", t)          # URL 제거 후 남은 빈 괄호 ( )
    t = _re.sub(r"\(\s*$", "", t)           # 줄 끝에 매달린 여는 괄호 (
    t = _re.sub(r"[ \t]{2,}", " ", t)       # 중복 공백
    t = _re.sub(r"\s+([.,)])", r"\1", t)    # 구두점 앞 공백
    return t.strip()


# 전화번호(지역번호형 02-123-4567 / 대표번호형 1577-0199). 109·119·129 같은 3자리
# 긴급·상담 번호는 이 패턴에 걸리지 않으므로 항상 유지된다.
_PHONE_RE = _re.compile(r"(?<!\d)(?:0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}|1[5-9]\d{2}[-.\s]?\d{4})(?!\d)")
_EXAMPLE_RE = _re.compile(r"\(\s*예시\s*\)|예시\s*[)）:：]\s*|\[\s*예시\s*\]")
PHONE_FALLBACK_LINE = "- 정확한 연락처는 **가까운 주민센터(행정복지센터)** 또는 **보건복지상담센터 129**에 확인해 주세요."


# 지역번호 + 한 묶음만 남은 '번호 조각'(예: "042-6773"). 완전한 번호가 아니라 _PHONE_RE 에
# 걸리지 않지만, 어르신이 그대로 걸면 엉뚱한 곳으로 간다(평가에서 실제로 나옴).
_PHONE_FRAG_RE = _re.compile(r"(?<![\d-])0\d{1,2}[-.)]\d{3,4}(?![-.\s]?\d)")


def _digits(s: str) -> str:
    return _re.sub(r"\D", "", s)


def _mostly_foreign(text: str) -> bool:
    """한글보다 영문이 많은 답(작은 모델이 가끔 영어로 답함) → 어르신께 내보내지 않는다."""
    ko = len(_re.findall(r"[가-힣]", text or ""))
    en = len(_re.findall(r"[A-Za-z]", text or ""))
    return en > 20 and en > ko


def ground_answer(text: str, contexts) -> str:
    """답변을 검색 근거(contexts)에 맞춰 결정적으로 정리한다(생성 후 처리).

    ① 프롬프트의 형식 안내를 모델이 그대로 옮긴 '(예시)'·'예시)' 표기를 지운다.
    ② 참고 자료에 없는 전화번호가 들어간 줄은 통째로 지운다(작은 모델이 그럴듯한
       번호를 지어내는 환각 — 어르신이 잘못된 곳에 전화하면 안 됨). 지운 줄이 있으면
       주민센터·129 확인 안내 한 줄을 덧붙인다.
    """
    if not text:
        return text
    if _mostly_foreign(text):
        return OFF_DOMAIN_REPLY
    t = _EXAMPLE_RE.sub("", text)
    allowed = {_digits(m) for c in (contexts or []) for m in _PHONE_RE.findall(c or "")}
    kept, dropped = [], False
    for line in t.split("\n"):
        nums = _PHONE_RE.findall(line)
        frags = _PHONE_FRAG_RE.findall(line)
        if (nums and any(_digits(n) not in allowed for n in nums)) or \
                any(not any(_digits(f) in a for a in allowed) for f in frags):
            dropped = True
            continue
        kept.append(line.rstrip())
    out = "\n".join(kept).strip()
    if dropped and PHONE_FALLBACK_LINE not in out:
        out = (out + "\n" + PHONE_FALLBACK_LINE).strip()
    return out


# ── ① 없는 제도 확인(생성 전, 결정적) ──────────────────────────────────────────
# 평가(eval_adversarial.py)에서 "무료 해외여행 지원금 신청법?" 같은 없는 제도에, 모델이
# 검색된 '다른 제도'의 신청 절차를 그대로 옮겨 붙여 사실처럼 답했다. 그래서 질문이
# 특정 제도·사업을 가리키면 그 이름(수식어)이 검색된 근거에 실제로 있는지 먼저 본다.
# 없으면 LLM 을 부르지 않고 "자료에서 확인되지 않는 제도" 로 안내한다.
_SERVICE_HEADS = ("사업", "서비스", "제도", "지원금", "지급", "배달", "바우처", "혜택", "프로그램")
_RARE_HEADS = ("보너스", "대출", "면제", "대여", "파견")       # 그 자체가 내용어인 머리말
_STOP_TERMS = {"대전", "대전시", "대전광역시", "어르신", "노인", "독거노인", "무료", "전용", "지원",
               "신청", "방법", "어떻게", "어디서", "어디", "언제", "우리", "동네", "특별", "일시",
               "현금", "이상", "매달", "매일", "정부", "국가", "관련", "복지", "새로운", "요즘",
               "여름", "겨울", "봄", "가을", "올해", "내년", "작년", "세대", "가구", "제공",
               # 동사 활용형(맨 형태로 남아 명사처럼 보이는 것)
               "나눠", "보내", "가져다", "도와", "챙겨", "해줘", "알려"}
# 복지 일반 어휘 — 검색 근거에 똑같은 글자가 없어도 실재 제도일 수 있으니 확인 대상에서 뺀다.
_SAFE_TERMS = {"돌봄", "요양", "간호", "방문", "급식", "식사", "도시락", "반찬", "목욕", "병원", "동행",
               "상담", "교육", "검진", "검사", "일자리", "교통", "주거", "난방", "냉방", "안부", "건강",
               "장비", "생활", "가사", "이동", "주간", "보호", "재가", "치매", "연금", "의료", "약",
               "안전", "응급", "여가", "문화", "운동", "경로", "공익", "활동", "사회",
               # 어르신이 흔히 쓰는 생활어(문서 용어와 글자가 달라도 실재 제도)
               "전기세", "가스비", "기름값", "난방비", "냉방비", "밥", "끼니", "보건소", "주민센터"}
_PARTICLE_END = ("에서", "으로", "에게", "은", "는", "이", "가", "을", "를", "에", "의", "도", "로",
                 "와", "과", "만", "요")
UNSUPPORTED_SERVICE_REPLY = (
    "말씀하신 **'{term}'** 관련 제도는 제가 가진 복지 자료에서 확인되지 않아요.\n"
    "- 있지 않은 제도를 안내해 드리면 안 되기 때문에, 신청 방법은 말씀드리지 않을게요.\n"
    "- 비슷한 지원이 있는지는 가까운 **주민센터(행정복지센터)** 또는 "
    "**보건복지상담센터 129**에 꼭 확인해 주세요."
)


def _service_terms(question: str) -> list[str]:
    """질문에서 '제도 이름을 이루는 내용어' 후보(맨 명사만)를 뽑는다."""
    from .topic_labels import TOPIC_KEYWORDS
    known = {k for ks in TOPIC_KEYWORDS.values() for k in ks}
    toks = _re.findall(r"[가-힣A-Za-z0-9]+", question or "")
    cands: list[str] = []
    for i, tok in enumerate(toks):
        head = next((h for h in _SERVICE_HEADS + _RARE_HEADS if h in tok), None)
        if not head:
            continue
        pre = tok[: tok.index(head)]                     # "노인맞춤돌봄서비스를" → "노인맞춤돌봄"
        window = ([pre] if pre else []) + toks[max(0, i - 3): i]
        if head in _RARE_HEADS:
            window.append(head)
        for w in window:
            if any(w.endswith(e) for e in _PARTICLE_END) or _re.search(r"\d", w):
                continue                                 # 조사·어미가 붙은 말, 숫자는 수식어 아님
            if len(w) < 2 or w in _STOP_TERMS or w in _SAFE_TERMS:
                continue
            if any(w in k or k in w for k in known) or any(s in w for s in _SAFE_TERMS):
                continue
            cands.append(w)
    return list(dict.fromkeys(cands))


def unsupported_service_term(question: str, contexts) -> str | None:
    """질문이 가리키는 제도 이름이 검색 근거에 없으면 그 낱말을 돌려준다(없으면 None)."""
    ctx = "".join("".join((c or "").split()) for c in (contexts or []))
    if not ctx:
        return None
    for w in _service_terms(question):
        if w not in ctx:
            return w
    return None


# Warm, chatbot-like replies for greetings / small talk (no RAG, no refusal).
SMALLTALK_SYSTEM_PROMPT = (
    "당신은 대전광역시 독거노인을 돕는 따뜻하고 친근한 복지 도우미입니다. "
    "어르신의 인사나 가벼운 안부에 1~2문장으로 다정하고 공손하게 한국어로 답합니다. "
    "사실이나 숫자를 지어내지 말고, 자연스럽게 안부를 나눈 뒤 '복지 관련해 궁금하신 점을 "
    "편하게 말씀해 주세요'처럼 부드럽게 안내합니다. 영어 단어나 이모지는 쓰지 않습니다."
)

# Shown when retrieval finds nothing relevant (off-topic or not in the docs):
# warm, not a cold refusal, and it steers the user back to what we can help with.
OFF_DOMAIN_REPLY = (
    "저는 대전 어르신 복지 안내를 도와드리고 있어요. 방금 말씀은 제가 가진 자료로는 "
    "정확히 알려드리기 어렵네요. 기초연금, 돌봄, 건강, 일자리 같은 복지 관련이라면 편하게 "
    "물어봐 주시고, 자세한 문의는 가까운 주민센터(행정복지센터)로 연락하시면 됩니다."
)


# Smaller models answer far faster on-device. Prefer these for low latency;
# fall back to whatever is installed so nothing breaks if they are absent.
FAST_MODELS = ["exaone3.5:2.4b", "qwen2.5:1.5b", "llama3.2:1b", "qwen2.5:0.5b",
               "gemma2:2b", "llama3.2:3b"]


class LocalLLM:
    def __init__(self, model: str = config.LLM_MODEL, host: str = config.OLLAMA_HOST):
        self.host = host.rstrip("/")
        self.model = model
        self.available = self._ping_and_pick(model)

    def _ping_and_pick(self, preferred: str) -> bool:
        """Ping Ollama and choose the model: preferred if present, else the
        fastest installed model, else the first available one."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                installed = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        except Exception:
            return False
        names = set(installed) | {n.split(":")[0] for n in installed}
        if preferred in names:
            self.model = preferred
        else:
            self.model = next((m for m in FAST_MODELS if m in names),
                              installed[0] if installed else preferred)
        return True

    def generate(self, prompt: str, system: str = "", num_predict: int = 130,
                 model: str | None = None, temperature: float = 0.3) -> str:
        """Generate a completion. `num_predict`/`model`/`temperature` can be
        overridden (the agent uses a longer budget and its own model)."""
        if not self.available:
            # 시작 시 Ollama가 꺼져 있었더라도, 이후 켜지면 자동 복구(재확인 1회).
            # 스트림릿 워커는 시작할 때 한 번만 핑하므로, 이게 없으면 Ollama를
            # 나중에 켜도 재시작 전까지 계속 '미실행'으로 나온다.
            self.available = self._ping_and_pick(self.model)
            if not self.available:
                return self._fallback(prompt)
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "keep_alive": "30m",          # keep the model loaded -> no reload latency
            "options": {
                "num_predict": num_predict,
                "num_ctx": 2048,          # smaller context -> faster prompt eval
                "temperature": temperature,
                "top_k": 20,
                "repeat_penalty": 1.3,    # stop small models looping the same phrase
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate", data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
                return json.loads(resp.read())["response"].strip()
        except (urllib.error.URLError, KeyError, TimeoutError) as exc:
            return self._fallback(prompt, error=str(exc))

    @staticmethod
    def _fallback(prompt: str, error: str = "") -> str:
        note = "[로컬 LLM(Ollama) 미실행 - 아래는 검색된 자료 요약입니다]"
        # The prompt already carries the retrieved context; return it plainly.
        return f"{note}\n{prompt.split('참고 자료:', 1)[-1].strip()[:600]}"


class OpenAILLM:
    """GPT-4o via the OpenAI Chat Completions API.

    Same interface as LocalLLM (`.available`, `.model`, `.generate(...)`), so the
    rest of the pipeline (pipeline.py, agent.py) does not change. Answers are
    still grounded by the RAG context that build_answer_prompt() injects, so the
    model answers from 대전 공공데이터 rather than its own memory.

    `.available` is False when no API key is set; generate() then returns the
    transparent template fallback, keeping the demo runnable offline.
    """

    def __init__(self, model: str = config.OPENAI_MODEL,
                 api_key: str = config.OPENAI_API_KEY,
                 base_url: str = config.OPENAI_BASE_URL):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.host = self.base_url          # parity with LocalLLM.host
        self.available = bool(api_key)

    def generate(self, prompt: str, system: str = "", num_predict: int = 130,
                 model: str | None = None, temperature: float = 0.3) -> str:
        """Generate a completion. Signature matches LocalLLM.generate so callers
        are unchanged. An Ollama-style `model` override (e.g. the agent's
        'exaone3.5:2.4b') is ignored here; only a 'gpt*' override is honoured."""
        if not self.available:
            return self._fallback(prompt)
        # An Ollama-style override (e.g. the agent's 'exaone3.5:2.4b') carries a
        # ':' tag; ignore those and keep this backend's own model. A bare API
        # model name (no ':') is honoured.
        mdl = model if (model and ":" not in model) else self.model
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": mdl,
            "messages": messages,
            "temperature": temperature,
            # num_predict is sized for Ollama tokens; Korean needs more OpenAI
            # tokens per character, so give the completion headroom.
            "max_tokens": max(int(num_predict * 3), 300),
        }
        data = json.dumps(payload).encode("utf-8")
        for attempt in range(_MAX_RETRIES):
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data,
                headers={"Content-Type": "application/json",
                         "User-Agent": _USER_AGENT,
                         "Authorization": f"Bearer {self.api_key}"})
            try:
                with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
                    body = json.loads(resp.read())
                    return body["choices"][0]["message"]["content"].strip()
            except urllib.error.HTTPError as exc:
                # The API returns a JSON error body (invalid key, quota, model
                # not found); surface it so failures are debuggable. Fall back
                # to the raw body when it isn't {"error": {"message": ...}}.
                raw = ""
                try:
                    raw = exc.read().decode("utf-8", "replace")
                    detail = json.loads(raw).get("error", {}).get("message", "") or raw
                except Exception:
                    detail = raw
                if exc.code == 429 and attempt < _MAX_RETRIES - 1:
                    time.sleep(_retry_wait(detail, attempt))   # rate limit: wait + retry
                    continue
                msg = f"HTTP {exc.code} {detail}".strip()[:400]
                print(f"[OpenAI] API 호출 실패: {msg}", file=sys.stderr)
                return self._fallback(prompt, error=msg)
            except (urllib.error.URLError, KeyError, IndexError, TimeoutError) as exc:
                print(f"[OpenAI] 요청 실패: {exc}", file=sys.stderr)
                return self._fallback(prompt, error=str(exc))
        return self._fallback(prompt, error="rate limit")

    @staticmethod
    def _fallback(prompt: str, error: str = "") -> str:
        why = f" ({error})" if error else ""
        note = f"[LLM API 호출 실패{why} — API 키/크레딧 확인 필요. 아래는 검색된 자료입니다]"
        # The prompt already carries the retrieved context; return it plainly.
        return f"{note}\n{prompt.split('참고 자료:', 1)[-1].strip()[:600]}"


class GeminiLLM:
    """Google Gemini via the native REST API (models/<model>:generateContent).

    Same interface as LocalLLM/OpenAILLM (`.available`, `.model`, `.generate`).
    Uses the same endpoint + `?key=` auth that works for listing models, so it
    avoids the OpenAI-compatibility layer that 404s for some keys/projects.
    """

    def __init__(self, model: str = config.GEMINI_MODEL,
                 api_key: str = config.GEMINI_API_KEY,
                 base_url: str = config.GEMINI_BASE_URL):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.host = self.base_url
        self.available = bool(api_key)

    def generate(self, prompt: str, system: str = "", num_predict: int = 130,
                 model: str | None = None, temperature: float = 0.3) -> str:
        if not self.available:
            return self._fallback(prompt)
        mdl = model if (model and ":" not in model) else self.model
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                # Gemini 2.5+/3.x flash spend "thinking" tokens from this budget
                # before writing the reply, so a tight cap truncates the answer.
                # Give generous headroom; the system prompt still keeps the reply
                # to 2-3 sentences.
                "maxOutputTokens": max(int(num_predict * 8), 1200),
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/models/{mdl}:generateContent?key={self.api_key}"
        data = json.dumps(body).encode("utf-8")
        for attempt in range(_MAX_RETRIES):
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json",
                                         "User-Agent": _USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
                    out = json.loads(resp.read())
                    parts = out["candidates"][0]["content"]["parts"]
                    return "".join(p.get("text", "") for p in parts).strip()
            except urllib.error.HTTPError as exc:
                raw = ""
                try:
                    raw = exc.read().decode("utf-8", "replace")
                    detail = json.loads(raw).get("error", {}).get("message", "") or raw
                except Exception:
                    detail = raw
                if exc.code == 429 and attempt < _MAX_RETRIES - 1:
                    time.sleep(_retry_wait(detail, attempt))   # rate limit: wait + retry
                    continue
                print(f"[Gemini] API 호출 실패: HTTP {exc.code} {detail}".strip()[:400],
                      file=sys.stderr)
                return self._fallback(prompt, error=f"HTTP {exc.code}")
            except (urllib.error.URLError, KeyError, IndexError, TimeoutError) as exc:
                print(f"[Gemini] 요청 실패: {exc}", file=sys.stderr)
                return self._fallback(prompt, error=str(exc))
        return self._fallback(prompt, error="rate limit")

    def generate_vision(self, prompt: str, image_bytes: bytes,
                        mime: str = "image/jpeg", temperature: float = 0.3) -> str:
        """이미지를 '보고' 답하는 멀티모달 호출(Gemini vision). 사진 속 글자뿐 아니라
        표·그림·전체 맥락까지 이해한다. 키가 없으면 안내 문구를 돌려준다."""
        if not self.available:
            return "이미지 분석은 Gemini API 키가 설정된 경우에만 가능합니다."
        import base64
        b64 = base64.b64encode(image_bytes).decode("ascii")
        body = {
            "contents": [{"role": "user", "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 1200},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json",
                                     "User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
                out = json.loads(resp.read())
                parts = out["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts).strip()
        except Exception as exc:
            print(f"[Gemini-vision] 실패: {exc}", file=sys.stderr)
            return "사진을 분석하지 못했어요. 더 또렷한 사진으로 다시 올려 주세요."


def make_llm():
    """Pick the answer-generation backend from config.

    LLM_BACKEND=openai (default) -> cloud LLM API: GPT-4o, or any
                                    OpenAI-compatible endpoint (e.g. Groq) via
                                    OPENAI_BASE_URL. This is the default.
    LLM_BACKEND=gemini            -> Google Gemini (native REST API).
    LLM_BACKEND=ollama            -> local on-device model (Ollama · EXAONE 3.5).
    A cloud backend with no API key falls back to local Ollama, which itself
    falls back to a template responder, so the pipeline always runs.
    """
    backend = config.LLM_BACKEND
    if backend == "gemini":
        # GEMINI_API_KEY preferred; fall back to OPENAI_API_KEY for convenience.
        key = config.GEMINI_API_KEY or config.OPENAI_API_KEY
        llm = GeminiLLM(api_key=key)
        if llm.available:
            return llm
    elif backend == "openai":
        llm = OpenAILLM()
        if llm.available:
            return llm
    # Default (ollama) and the cloud-key-missing case both run on-device.
    return LocalLLM()


def build_answer_prompt(question: str, contexts: List[str]) -> str:
    """Combine the question with retrieved welfare chunks into an LLM prompt."""
    if contexts:
        joined = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(contexts))
    else:
        joined = "(관련 자료 없음)"
    return (f"질문: {question}\n\n"
            f"참고 자료 (아래 내용에만 근거해 답하세요):\n{joined}\n\n"
            f"위 자료만 사용해 한국어 1~2문장으로 답하세요. 자료에 없으면 "
            f"주민센터 문의 안내만 하세요.\n답변:")


if __name__ == "__main__":
    llm = make_llm()
    print(f"LLM backend: {type(llm).__name__} | available: {llm.available} "
          f"(model={llm.model})")
    prompt = build_answer_prompt(
        "기초연금은 어떻게 신청하나요?",
        ["기초연금은 만 65세 이상이고 소득 기준 이하인 어르신에게 매월 지급되며, "
         "주민센터나 국민연금공단 지사에서 신청합니다."])
    print(llm.generate(prompt, system=ANSWER_SYSTEM_PROMPT))
