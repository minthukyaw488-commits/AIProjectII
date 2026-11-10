"""업로드한 사진·문서에서 글자(text)를 뽑아낸다 — 완전 offline(OCR 기반).

우리 로컬 LLM(EXAONE 3.5)은 '텍스트'만 이해한다. 그래서 어르신이 올린
고지서·안내문 '사진'은 tesseract OCR(한국어+영어)로 글자를 읽어 텍스트로 바꾼 뒤
LLM에 전달한다. PDF/txt/csv/docx 같은 문서는 직접 텍스트를 추출한다.

사용:
    text, kind = extract_text_from_upload(filename, data_bytes)
      kind ∈ {"image", "pdf", "text", "docx"}
  - 라이브러리/시스템 패키지(tesseract 등)가 없으면 RuntimeError(한국어 안내)를 던진다.
  - 추출 결과가 비면 text="" 로 돌아온다(호출부에서 '글자 못 찾음' 안내).

시스템 패키지(서버/Mac):
    tesseract-ocr, tesseract-ocr-kor, poppler-utils  (스캔 PDF용)
"""
from __future__ import annotations

import io
import os

# 사진으로 취급할 확장자
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
# LLM 입력 보호: 너무 길면 자른다(앞부분이 보통 핵심)
MAX_CHARS = 6000


def _clean(text: str) -> str:
    """OCR/추출 결과 정리: 과도한 빈 줄·공백 제거, 길이 제한."""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    out, blank = [], 0
    for ln in lines:
        if ln:
            out.append(ln)
            blank = 0
        else:
            blank += 1
            if blank <= 1:          # 연속 빈 줄은 1개까지만
                out.append("")
    cleaned = "\n".join(out).strip()
    if len(cleaned) > MAX_CHARS:
        cleaned = cleaned[:MAX_CHARS] + "\n…(이하 생략)"
    return cleaned


def _ocr_image_bytes(data: bytes) -> str:
    """사진 bytes → OCR(kor+eng) 텍스트."""
    try:
        import pytesseract
        from PIL import Image
    except Exception as e:                                  # 라이브러리 미설치
        raise RuntimeError(
            "사진 글자 읽기(OCR) 라이브러리가 없습니다. "
            "`pip install pytesseract pillow` 후 다시 시도하세요.") from e
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise RuntimeError("사진 파일을 열 수 없습니다. 다른 사진으로 시도해 주세요.") from e
    # 간단 전처리: 회색조로 바꾸면 글자 인식률이 올라간다
    try:
        img = img.convert("L")
    except Exception:
        pass
    try:
        return pytesseract.image_to_string(img, lang="kor+eng")
    except Exception as e:
        # 보통 tesseract 실행파일/한국어 데이터가 없을 때
        raise RuntimeError(
            "글자 인식 엔진(tesseract)이 설치되어 있지 않습니다. 서버/Mac에 "
            "tesseract-ocr, tesseract-ocr-kor 를 설치해 주세요. "
            "(Mac: `brew install tesseract tesseract-lang`, "
            "Ubuntu: `sudo apt install -y tesseract-ocr tesseract-ocr-kor`)") from e


def _pdf_text_bytes(data: bytes) -> str:
    """PDF bytes → 텍스트. 글자가 거의 없으면(스캔본) OCR 로 대체."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        text = ""
    if len((text or "").strip()) >= 20:
        return text
    # 스캔 PDF → 페이지를 이미지로 바꿔 OCR
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception as e:
        raise RuntimeError(
            "스캔본 PDF를 읽으려면 OCR 도구가 필요합니다. "
            "`pip install pytesseract pdf2image` 와 시스템 패키지 "
            "poppler-utils, tesseract-ocr(-kor) 를 설치해 주세요.") from e
    try:
        imgs = convert_from_bytes(data)                    # poppler 필요
    except Exception as e:
        raise RuntimeError(
            "PDF를 이미지로 변환하지 못했습니다. poppler-utils 설치가 필요합니다. "
            "(Ubuntu: `sudo apt install -y poppler-utils`, Mac: `brew install poppler`)"
        ) from e
    parts = []
    for im in imgs[:10]:                                   # 최대 10쪽
        try:
            parts.append(pytesseract.image_to_string(im.convert("L"), lang="kor+eng"))
        except Exception as e:
            raise RuntimeError(
                "글자 인식 엔진(tesseract)이 설치되어 있지 않습니다. "
                "tesseract-ocr, tesseract-ocr-kor 를 설치해 주세요.") from e
    return "\n".join(parts)


def _docx_text_bytes(data: bytes) -> str:
    """.docx bytes → 텍스트(문단 + 표)."""
    try:
        import docx                                        # python-docx
    except Exception as e:
        raise RuntimeError(
            "워드(.docx) 파일을 읽으려면 `pip install python-docx` 가 필요합니다.") from e
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs]
    for tbl in getattr(d, "tables", []):
        for row in tbl.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def _plain_text_bytes(data: bytes) -> str:
    """txt/md/csv bytes → 문자열(utf-8 우선, 실패 시 cp949)."""
    for enc in ("utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def extract_text_from_upload(filename: str, data: bytes) -> tuple[str, str]:
    """업로드 파일 → (정리된 텍스트, 종류). 지원하지 않는 형식은 RuntimeError."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in IMAGE_EXTS:
        return _clean(_ocr_image_bytes(data)), "image"
    if ext == ".pdf":
        return _clean(_pdf_text_bytes(data)), "pdf"
    if ext == ".docx":
        return _clean(_docx_text_bytes(data)), "docx"
    if ext in (".txt", ".md", ".csv", ".tsv", ".log", ".json"):
        return _clean(_plain_text_bytes(data)), "text"
    raise RuntimeError(
        f"지원하지 않는 형식이에요({ext or '알 수 없음'}). "
        "사진(jpg·png), PDF, 또는 txt 파일을 올려 주세요.")
