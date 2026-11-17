"""사진 이해(vision) — 클라우드 Gemini → 서버 안 Ollama vision → OCR 순서로 자동 전환.

  1순위  Gemini vision     : GEMINI_API_KEY 환경변수가 있을 때만(키는 코드에 절대 적지 않음).
  2순위  Ollama vision      : 서버 안(on-device) 멀티모달 모델. 기본 qwen2.5vl:3b
                               (OLLAMA_VISION_MODEL 로 변경). 외부 전송 없음.
  3순위  OCR(tesseract)     : 위 둘 다 안 되면 글자만 추출(src/file_intake).

반환값은 (설명 텍스트, 사용한 엔진 이름). 실패하면 ("", 이유)를 돌려준다.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import urllib.request

from . import config

OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:3b")
# 고지서·안내문의 작은 글자를 읽어야 하므로 너무 작게 줄이지 않는다(512px 는 글자가 뭉개짐).
MAX_SIDE = int(os.environ.get("VISION_MAX_SIDE", "1280"))

VISION_PROMPT = (
    "당신은 어르신에게 사진 속 문서나 물건을 쉽게 설명해 주는 친절한 복지 도우미입니다.\n"
    "사진에 실제로 보이는 글자·숫자·모양만 근거로 설명하고, 보이지 않는 내용은 절대 "
    "지어내지 마세요. 글자가 흐려 읽을 수 없으면 '잘 보이지 않는다'고 말하세요.\n"
    "아래 모양으로 짧고 쉬운 한국어로 답하세요:\n\n"
    "이 사진은 **(문서 또는 물건 이름)**입니다.\n\n"
    "- **무엇인가요?** 핵심 내용 1문장\n"
    "- **중요한 내용:** 사진에 적힌 금액·기한·기관·복용법 등(있는 것만)\n"
    "- **어떻게 하면 되나요?** 사진에 보이는 안내대로 1~2문장\n\n"
    "고지서·안내문이면 어디에 언제까지 무엇을 해야 하는지, 약 봉투면 언제 몇 알 먹는지를 "
    "알려 주세요. 확실하지 않으면 '가까운 주민센터(행정복지센터)에 확인해 보세요'라고 덧붙이세요."
)

_GEMINI_FAIL = ("사진을 분석하지 못했어요", "이미지 분석은 Gemini API 키가")


def _prepare(image_bytes: bytes) -> bytes:
    """큰 사진을 MAX_SIDE 이하 JPEG 로 줄여 전송·추론 시간을 줄인다(실패하면 원본)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_SIDE:
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return image_bytes


def _gemini(image_jpeg: bytes) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return ""
    try:
        from .llm import GeminiLLM
        text = GeminiLLM(api_key=key).generate_vision(VISION_PROMPT, image_jpeg, "image/jpeg",
                                                      temperature=0.2)
    except Exception as exc:
        print(f"[vision] Gemini 실패: {exc}", file=sys.stderr)
        return ""
    if not text or text.startswith(_GEMINI_FAIL):
        return ""
    return text.strip()


def _ollama(image_jpeg: bytes) -> str:
    body = {
        "model": OLLAMA_VISION_MODEL,
        "messages": [{"role": "user", "content": VISION_PROMPT,
                      "images": [base64.b64encode(image_jpeg).decode("ascii")]}],
        "stream": False,
        "options": {"temperature": 0.2, "repeat_penalty": 1.2, "num_predict": 500},
    }
    req = urllib.request.Request(
        f"{config.OLLAMA_HOST.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read())
        return (out.get("message", {}).get("content") or "").strip()
    except Exception as exc:
        print(f"[vision] Ollama({OLLAMA_VISION_MODEL}) 실패: {exc}", file=sys.stderr)
        return ""


def read_image(image_bytes: bytes, filename: str = "photo.jpg") -> tuple[str, str]:
    """사진 → (쉬운 설명, 엔진). Gemini → Ollama vision → OCR 순으로 시도한다."""
    jpeg = _prepare(image_bytes)
    text = _gemini(jpeg)
    if text:
        return text, "Gemini vision(클라우드)"
    text = _ollama(jpeg)
    if text:
        return text, f"{OLLAMA_VISION_MODEL}(서버 안)"
    try:
        from .file_intake import extract_text_from_upload
        text, _kind = extract_text_from_upload(filename, image_bytes)
    except Exception as exc:
        print(f"[vision] OCR 실패: {exc}", file=sys.stderr)
        text = ""
    return (text or "").strip(), "OCR(글자 추출)"
