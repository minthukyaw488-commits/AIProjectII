"""
Step 1: RAG pipeline for Daejeon elderly-welfare information.

Responsibilities
  1. Load documents from data/welfare_docs (.pdf via pdfplumber, .md/.txt directly)
  2. Chunk long text into 200-500 char overlapping pieces
  3. Embed chunks and store them in ChromaDB (persisted on disk)
  4. Retrieve the top-K most relevant chunks for a user question

If ChromaDB is unavailable, a small in-memory cosine store is used so the
retrieval logic can still be demonstrated offline.
"""
from __future__ import annotations
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from . import config
from .embeddings import EmbeddingModel


# --------------------------------------------------------------------------
# Document loading
# --------------------------------------------------------------------------
# A page with fewer than this many extracted characters is treated as a
# scanned/image page and sent to OCR (if OCR is available).
_OCR_MIN_CHARS_PER_PAGE = 20


_YEAR_RE = re.compile(r"(20\d{2})")


def _doc_date(name: str) -> str:
    """Pull a publication year (e.g. 2025) from the file name for citation.
    Returns '' when none is found. Cheap, deterministic, no file read."""
    m = _YEAR_RE.search(name or "")
    return m.group(1) if m else ""


def load_pages_from_pdf(pdf_path: Path) -> List[Tuple[int, str]]:
    """Extract a PDF as [(page_number_1based, text), …] with OCR fallback.

    Keeping page boundaries lets each chunk carry the page it came from, so a
    citation can point the reader to "…pdf · p.12" instead of just the file.
    Digital pages are read directly; scanned/image pages go to Tesseract OCR.
    """
    import pdfplumber
    parts: List[str] = []
    scanned_pages: List[int] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if len(text.strip()) < _OCR_MIN_CHARS_PER_PAGE:
                scanned_pages.append(i)
            parts.append(text)

    if scanned_pages:
        ocr_text = _ocr_pdf_pages(pdf_path, scanned_pages)
        for i, text in ocr_text.items():
            parts[i] = text
    parts = _strip_running_headers(parts)
    return [(i + 1, t) for i, t in enumerate(parts)]


def load_text_from_pdf(pdf_path: Path) -> str:
    """Whole-PDF text (backward-compatible). Pages joined with newlines."""
    return "\n".join(t for _, t in load_pages_from_pdf(pdf_path))


def _strip_running_headers(pages: List[str]) -> List[str]:
    """Remove running headers/footers repeated across many pages.

    Government booklets print the same short line (e.g. "힘이 되는 평생친구
    보건복지부", section titles, page numbers) on most pages. A line that is
    short and appears on a large fraction of pages is boilerplate, not content,
    and it pollutes chunks/retrieval - so drop it.
    """
    n = len(pages)
    if n < 4:
        return pages
    freq: Counter = Counter()
    for p in pages:
        for ln in {l.strip() for l in p.splitlines() if l.strip()}:
            freq[ln] += 1
    threshold = max(3, int(n * 0.2))
    banned = {ln for ln, c in freq.items() if c >= threshold and len(ln) <= 40}
    if not banned:
        return pages
    cleaned = []
    for p in pages:
        cleaned.append("\n".join(l for l in p.splitlines() if l.strip() not in banned))
    return cleaned


def _ocr_pdf_pages(pdf_path: Path, page_indices: List[int]) -> dict:
    """OCR the given (0-based) pages with Tesseract Korean. Graceful if absent.

    Requires: `pytesseract`, `pdf2image` (Python) and system `tesseract-ocr`
    with the Korean language pack + `poppler-utils`. Returns {page_index: text}.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except Exception:
        print("[rag] scanned pages detected but OCR libraries are not "
              "installed (pip install pytesseract pdf2image; and install "
              "system tesseract-ocr + tesseract-ocr-kor + poppler-utils). "
              "Skipping OCR.")
        return {}

    out = {}
    for idx in page_indices:
        try:
            images = convert_from_path(str(pdf_path), first_page=idx + 1,
                                       last_page=idx + 1, dpi=300)
            if images:
                # Grayscale preprocessing improves OCR accuracy on real scans.
                page_img = images[0].convert("L")
                # 'kor+eng' handles mixed Korean/English welfare documents.
                out[idx] = pytesseract.image_to_string(page_img, lang="kor+eng")
        except Exception as exc:
            print(f"[rag] OCR failed on page {idx + 1}: {exc.__class__.__name__}")
    if out:
        print(f"[rag] OCR recovered text from {len(out)} scanned page(s).")
    return out


def load_text_from_table(path: Path) -> str:
    """Turn a CSV/XLS/XLSX table into retrievable text: one line per row as
    "컬럼: 값, 컬럼: 값 …", prefixed with the file name as a heading.

    Structured Daejeon data (급식소·경로당·시설 현황 등) becomes searchable so
    "가까운 급식소" 같은 질문에 답할 수 있다. Korean government files are often
    encoded in cp949/euc-kr, which is handled below. Graceful (skips) if the
    Excel libraries are not installed.
    """
    suffix = path.suffix.lower()
    row_groups: List[List[List[str]]] = []           # one list of raw rows per sheet

    if suffix == ".csv":
        import csv
        rows = None
        for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
            try:
                with path.open(encoding=enc, newline="") as f:
                    rows = list(csv.reader(f))
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not rows:
            return ""
        row_groups.append([[str(c) for c in r] for r in rows])
    else:                                            # .xls / .xlsx
        try:
            import pandas as pd
        except Exception:
            print(f"[rag] '{path.name}' 건너뜀 (pandas 미설치: pip install pandas openpyxl xlrd).")
            return ""
        frames = None
        for engine in (None, "openpyxl", "xlrd"):    # named .xls may be real xlsx
            try:
                # header=None: real government sheets put a title in row 0 and the
                # column names a few rows down, so we detect the header ourselves.
                frames = pd.read_excel(path, sheet_name=None, dtype=str,
                                       header=None, engine=engine)
                break
            except Exception:
                frames = None
        if frames is None:
            print(f"[rag] '{path.name}' 건너뜀 (엑셀 읽기 실패; openpyxl/xlrd 확인).")
            return ""
        for df in frames.values():
            df = df.fillna("")
            row_groups.append([[str(v) for v in row] for _, row in df.iterrows()])

    rows_text: List[str] = []
    for rows in row_groups:
        rows_text.extend(_table_rows_to_text(rows))
    if not rows_text:
        return ""
    body = "\n\n".join(rows_text)                     # blank line = row boundary
    return f"# {path.stem}\n\n{body}"


def _table_rows_to_text(rows: List[List[str]]) -> List[str]:
    """Turn one raw table (list of rows) into searchable "컬럼: 값" lines.

    Government spreadsheets carry a title row, blank rows, and sometimes a
    multi-line header before the data. We drop empty rows, pick the real header
    (the row with the most non-empty cells among the first few), and skip empty
    / 'Unnamed' column labels so a row reads like a natural sentence.
    """
    def clean(v: str) -> str:
        return " ".join(str(v).replace("\n", " ").split()).strip()

    rows = [[clean(c) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]               # drop fully-empty rows
    if not rows:
        return []
    # Header = the row (within the first 6) with the most non-empty cells.
    scan = min(6, len(rows))
    head_i = max(range(scan), key=lambda i: sum(1 for c in rows[i] if c))
    header = rows[head_i]

    def label(h: str) -> str:
        return "" if (not h or h.lower().startswith("unnamed") or h.startswith("Column")) else h

    lines: List[str] = []
    for r in rows[head_i + 1:]:
        cells = []
        for h, v in zip(header, r):
            if not v:
                continue
            lab = label(h)
            cells.append(f"{lab}: {v}" if lab else v)
        if cells:
            lines.append(", ".join(cells))
    return lines


def load_documents(docs_dir: Path = config.WELFARE_DOCS_DIR) -> List[dict]:
    """Load every supported file in docs_dir.

    Returns [{source, date, segments}] where ``segments`` is a list of
    (page_number | None, text): PDFs keep per-page boundaries (page number for
    citation); tables/markdown/txt are a single segment with page=None.
    """
    docs: List[dict] = []
    for path in sorted(docs_dir.glob("*")):
        # 명단/현황 스프레드시트는 검색 노이즈 → 색인 제외(config.RAG_EXCLUDE_DOCS).
        if any(tok in path.name for tok in config.RAG_EXCLUDE_DOCS):
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            segments: List[Tuple[Optional[int], str]] = list(load_pages_from_pdf(path))
        elif suffix in {".md", ".txt"}:
            segments = [(None, path.read_text(encoding="utf-8"))]
        elif suffix in {".csv", ".xls", ".xlsx"}:
            segments = [(None, load_text_from_table(path))]
        else:
            continue
        segments = [(pg, t) for pg, t in segments if t and t.strip()]
        if segments:
            docs.append({"source": path.name, "date": _doc_date(path.name),
                         "segments": segments})
    return docs


# --------------------------------------------------------------------------
# Cleaning & section segmentation (real government PDFs are noisy)
# --------------------------------------------------------------------------
# Line starts that begin a new welfare item in Korean government documents.
_SECTION_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,2}[).]"            # 1)  1.
    r"|[가-힣][).]"           # 가.  나)
    r"|[①-⑳❶-❿]"             # circled numbers
    r"|[○◦□■●▷▶◇◆❍]"         # bullet marks
    r"|제\s*\d+\s*[조항]"      # 제1조 / 제2항
    r"|[IVX]{1,4}\."          # roman numerals
    r"|#{1,6}\s"              # markdown headings
    r")")


def clean_text(text: str) -> str:
    """Normalise text and drop page-number / symbol-noise lines.

    pdfplumber + OCR leave soft hyphens, zero-width chars, stray page numbers
    and symbol-only lines that hurt embeddings. Strip them while keeping the
    Korean content and line structure.
    """
    text = text.replace("­", "").replace("‑", "-")   # soft hyphens
    text = re.sub(r"[​-‏﻿]", "", text)          # zero-width
    text = re.sub(r"[ \t]+", " ", text)
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if re.fullmatch(r"[-\s]*\d{1,4}[-\s]*", s):            # page-number line
            continue
        # a line that is almost all symbols (few Korean/알파벳/digits) is noise
        content = len(re.findall(r"[0-9A-Za-z가-힣]", s))
        if len(s) >= 4 and content / len(s) < 0.4:
            continue
        out.append(s)
    return "\n".join(out)


def segment_sections(text: str) -> str:
    """Rebuild paragraph structure around section markers.

    Extracted PDF text often lacks blank-line paragraph breaks, so a plain
    window splits mid-sentence and mixes topics. Merge wrapped lines into a
    block and start a new block at each numbered/bulleted welfare item, then
    emit blank-line-separated paragraphs the chunker can group cleanly.
    """
    blocks: List[str] = []
    cur: List[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            if cur:
                blocks.append(" ".join(cur)); cur = []
            continue
        if _SECTION_RE.match(s) and cur:
            blocks.append(" ".join(cur)); cur = [s]
        else:
            cur.append(s)
    if cur:
        blocks.append(" ".join(cur))
    return "\n\n".join(b.strip() for b in blocks if b.strip())


def is_low_quality(chunk: str) -> bool:
    """Drop chunks that are too short or hold almost no Korean (tables/noise)."""
    s = chunk.strip()
    if len(s) < 30:
        return True
    korean = len(re.findall(r"[가-힣]", s))
    return korean / len(s) < 0.15


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------
def chunk_text(text: str,
               chunk_size: int = config.CHUNK_SIZE,
               overlap: int = config.CHUNK_OVERLAP) -> List[str]:
    """Clean, segment, then split text into overlapping ~chunk_size chunks.

    Breaks on section/paragraph boundaries first, then falls back to a sliding
    character window so no chunk exceeds the size limit.
    """
    text = segment_sections(clean_text(text))
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    # Split on blank lines (paragraphs) as the natural welfare-item boundary.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: List[str] = []
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) + 1 <= chunk_size:
            buffer = f"{buffer}\n{para}".strip()
        else:
            if buffer:
                chunks.append(buffer)
            # A single paragraph longer than chunk_size -> sliding window.
            if len(para) > chunk_size:
                chunks.extend(_sliding_window(para, chunk_size, overlap))
                buffer = ""
            else:
                buffer = para
    if buffer:
        chunks.append(buffer)
    return chunks


def _sliding_window(text: str, size: int, overlap: int) -> List[str]:
    step = max(size - overlap, 1)
    return [text[i:i + size] for i in range(0, len(text), step) if text[i:i + size].strip()]


# --------------------------------------------------------------------------
# Vector store
# --------------------------------------------------------------------------
@dataclass
class Retrieved:
    text: str
    source: str
    score: float
    page: Optional[int] = None     # PDF 쪽 번호(있으면 인용에 표시)
    date: str = ""                 # 발행 연도(파일명 기준)


def cite_label(r: "Retrieved") -> str:
    """사람이 읽는 출처 표기: '[2025] 파일명 · p.12' (연도/쪽이 있으면 덧붙임)."""
    label = r.source
    if r.page:
        label += f" · p.{r.page}"
    if r.date:
        label = f"[{r.date}] {label}"
    return label


class _InMemoryStore:
    """Fallback cosine-similarity store used when ChromaDB is unavailable."""

    def __init__(self):
        self._vecs: List[List[float]] = []
        self._docs: List[str] = []
        self._meta: List[dict] = []

    def add(self, ids, embeddings, documents, metadatas):
        self._vecs.extend(embeddings)
        self._docs.extend(documents)
        self._meta.extend(metadatas)

    def query(self, embedding, top_k):
        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5 or 1.0
            nb = sum(y * y for y in b) ** 0.5 or 1.0
            return dot / (na * nb)
        scored = sorted(
            ((cos(embedding, v), d, m) for v, d, m in zip(self._vecs, self._docs, self._meta)),
            key=lambda t: t[0], reverse=True,
        )[:top_k]
        return [Retrieved(text=d, source=m.get("source", "?"), score=float(s),
                          page=m.get("page"), date=m.get("date", ""))
                for s, d, m in scored]

    def count(self):
        return len(self._docs)


class RagPipeline:
    def __init__(self, embed_model: EmbeddingModel | None = None,
                 use_rerank: bool = config.RAG_USE_RERANK):
        self.embedder = embed_model or EmbeddingModel()
        self.backend = "chroma"
        self._collection = self._init_chroma()
        self.use_rerank = use_rerank
        self._reranker = None            # loaded lazily on first retrieve
        self.index_stats: dict = {}      # per-file breakdown set by index()

    @property
    def reranker(self):
        if self._reranker is None and self.use_rerank:
            from .reranker import Reranker
            self._reranker = Reranker()
        return self._reranker

    def _init_chroma(self):
        try:
            import chromadb
            config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
            # Reuse the persisted collection across runs (don't delete it), so
            # the corpus isn't re-embedded on every startup. index() rebuilds it
            # only when it's empty or RAG_REINDEX=1.
            return client.get_or_create_collection(
                config.CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"})
        except Exception as exc:
            print(f"[rag] ChromaDB unavailable ({exc.__class__.__name__}); "
                  f"using in-memory store.")
            self.backend = "in-memory"
            return _InMemoryStore()

    def index(self, docs_dir: Path = config.WELFARE_DOCS_DIR) -> int:
        """Load -> chunk -> embed -> store. Returns number of chunks indexed.

        A per-file breakdown of the run is left on ``self.index_stats`` so a
        caller (e.g. the CLI check report) can show which documents were
        indexed, how many chunks each kept, and what was skipped.

        The ChromaDB store is persisted, so if it's already populated this
        reuses it (no re-embedding) for a fast startup. Set RAG_REINDEX=1 to
        force a rebuild after the documents change.
        """
        force = os.environ.get("RAG_REINDEX", "0") not in ("0", "", "false", "False")
        if self.backend == "chroma" and not force:
            try:
                existing = self._collection.count()
            except Exception:
                existing = 0
            if existing > 0:
                self.index_stats = {"kept": {}, "dropped": {}, "skipped_files": [],
                                    "total_chunks": existing, "total_dropped": 0,
                                    "reused": True}
                print(f"[rag] 기존 벡터 인덱스 재사용: {existing} 조각 "
                      f"(다시 색인하려면 RAG_REINDEX=1)")
                return existing

        documents = load_documents(docs_dir)
        loaded_sources = {d["source"] for d in documents}
        chunks, metadatas, ids = [], [], []
        per_source_kept: Counter = Counter()
        per_source_dropped: Counter = Counter()
        dropped = 0
        for doc in documents:
            kept = 0
            date = doc.get("date", "")
            for page, seg_text in doc["segments"]:
                for chunk in chunk_text(seg_text):
                    if is_low_quality(chunk):
                        dropped += 1
                        per_source_dropped[doc["source"]] += 1
                        continue
                    chunks.append(chunk)
                    meta = {"source": doc["source"], "chunk": kept}
                    if page is not None:
                        meta["page"] = page          # 인용에 '· p.N' 표시
                    if date:
                        meta["date"] = date          # 발행 연도(파일명 기준)
                    metadatas.append(meta)
                    ids.append(f"{doc['source']}::{kept}")
                    kept += 1
            per_source_kept[doc["source"]] = kept

        # Files present but not indexed (unsupported type, or empty after load).
        supported = {".pdf", ".md", ".txt", ".csv", ".xls", ".xlsx"}
        skipped_files = [p.name for p in sorted(docs_dir.glob("*"))
                         if p.is_file() and p.name not in loaded_sources
                         and p.suffix.lower() in supported]
        self.index_stats = {
            "kept": dict(per_source_kept),
            "dropped": dict(per_source_dropped),
            "skipped_files": skipped_files,
            "total_chunks": len(chunks),
            "total_dropped": dropped,
        }

        if dropped:
            print(f"[rag] dropped {dropped} low-quality chunk(s) (noise/tables).")
        if not chunks:
            return 0
        # Rebuild from a CLEAN collection so documents removed from the corpus
        # (e.g. a deleted file) disappear instead of lingering as stale chunks.
        if self.backend == "chroma":
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
                try:
                    client.delete_collection(config.CHROMA_COLLECTION)
                except Exception:
                    pass
                self._collection = client.get_or_create_collection(
                    config.CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"})
            except Exception:
                pass
        # Fit the embedder on the full corpus first (matters for the TF-IDF
        # fallback; a no-op for bge-m3).
        self.embedder.fit(chunks)
        embeddings = [list(map(float, v)) for v in self.embedder.encode(chunks)]
        self._collection.add(ids=ids, embeddings=embeddings,
                             documents=chunks, metadatas=metadatas)
        return len(chunks)

    def _vector_search(self, question: str, n: int) -> List[Retrieved]:
        """Top-n candidates by embedding similarity (bi-encoder)."""
        q_emb = list(map(float, self.embedder.encode([question])[0]))
        if self.backend == "chroma":
            res = self._collection.query(query_embeddings=[q_emb], n_results=n)
            out = []
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                                       res["distances"][0]):
                out.append(Retrieved(text=doc, source=meta.get("source", "?"),
                                     score=1.0 - float(dist),  # cosine dist -> sim
                                     page=meta.get("page"), date=meta.get("date", "")))
            return out
        return self._collection.query(q_emb, n)

    def retrieve(self, question: str, top_k: int = config.RAG_TOP_K) -> List[Retrieved]:
        """Retrieve a candidate pool by embedding, then rerank down to top_k.

        With reranking disabled/unavailable this is a plain top_k embedding
        search, so behaviour degrades gracefully.
        """
        if not self.use_rerank:
            return self._vector_search(question, top_k)
        pool = max(top_k, config.RAG_CANDIDATES)
        candidates = self._vector_search(question, pool)
        rr = self.reranker
        if not (rr and rr.available) or len(candidates) <= top_k:
            return candidates[:top_k]
        order = rr.rerank(question, [c.text for c in candidates])
        out = []
        for idx, score in order[:top_k]:
            c = candidates[idx]
            out.append(Retrieved(text=c.text, source=c.source, score=score))
        return out


def _print_index_report(rag: "RagPipeline", docs_dir: Path, n: int) -> None:
    """Human-readable check of what just got indexed (run after index())."""
    stats = rag.index_stats
    kept = stats.get("kept", {})
    dropped = stats.get("dropped", {})
    print("=" * 60)
    print(f"📂 데이터 폴더: {docs_dir}")
    print(f"📄 색인된 문서: {len(kept)}개   ·   총 청크: {n}개")
    print("-" * 60)
    if kept:
        width = max(len(s) for s in kept)
        for src in sorted(kept):
            d = dropped.get(src, 0)
            extra = f"  (저품질 {d}개 제외)" if d else ""
            print(f"  ✅ {src.ljust(width)}  {kept[src]:>4} 청크{extra}")
    skipped = stats.get("skipped_files", [])
    if skipped:
        print("-" * 60)
        for s in skipped:
            print(f"  ⚠️  건너뜀(빈 내용/읽기 실패): {s}")
    print("=" * 60)


if __name__ == "__main__":
    rag = RagPipeline()
    n = rag.index()
    rr = rag.reranker
    rr_desc = rr.model_name if (rr and rr.available) else "off/unavailable"
    _print_index_report(rag, config.WELFARE_DOCS_DIR, n)
    print(f"backend={rag.backend} embedder={rag.embedder.backend} "
          f"rerank={rr_desc}\n")
    if n == 0:
        print("색인된 청크가 없습니다. data/welfare_docs/ 에 문서를 넣었는지, "
              "지원 형식(pdf/md/txt/csv/xls/xlsx)인지 확인하세요.")
        raise SystemExit(0)
    print("🔎 검색 점검 (샘플 질문):\n")
    for q in ["기초연금은 어떻게 신청하나요?",
              "혼자 사는데 응급상황이 걱정돼요",
              "우울하고 외로울 때 상담받고 싶어요"]:
        print(f"Q: {q}")
        for r in rag.retrieve(q):
            print(f"  [{r.score:.3f}] ({r.source}) {r.text[:60].replace(chr(10),' ')}...")
        print()
