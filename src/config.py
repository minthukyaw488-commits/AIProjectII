"""
Central configuration for the elderly welfare voice AI system (대전노인복지 HUB).

Answer generation uses a cloud LLM API (GPT-4o by default), combined with a
Retrieval-Augmented Generation (RAG) index built from Daejeon public welfare
data. The LLM provides language ability; the RAG index grounds every answer in
대전 공공데이터 so the assistant does not hallucinate and can be corrected by
updating the documents (no retraining). The answer model is swappable via
LLM_BACKEND (openai / gemini / ollama), and a local Ollama backend is kept as
a fallback so the pipeline still runs without an API key. Sensitive data is
handled on the server side (encryption / access control) rather than sent to a
third-party store beyond the model call.
"""
import os
from pathlib import Path

# --- Paths ---------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
WELFARE_DOCS_DIR = DATA_DIR / "welfare_docs"
AUDIO_DIR = DATA_DIR / "audio"
CHROMA_DIR = DATA_DIR / "chroma_db"          # persisted vector store
ALERT_LOG_DIR = DATA_DIR / "alerts"          # local social-worker alert log

# --- RAG / embedding -----------------------------------------------------
# bge-m3 is multilingual (Korean + English) and was validated in the
# original prototype. If sentence-transformers or the model is unavailable,
# the pipeline falls back to a lightweight local embedding (see embeddings.py)
# so the demo still runs offline.
EMBED_MODEL = "BAAI/bge-m3"
CHROMA_COLLECTION = "daejeon_welfare"

# Chunking: welfare PDFs can be long, so split into small overlapping chunks.
CHUNK_SIZE = 400          # target characters per chunk (200-500 range)
CHUNK_OVERLAP = 80        # characters shared between neighbouring chunks
RAG_TOP_K = 3             # chunks passed to the LLM (after reranking)

# --- Reranking (cross-encoder) -------------------------------------------
# A bi-encoder (bge-m3) can rank a keyword-overlapping chunk above the truly
# relevant one. Retrieve a larger candidate pool, then a cross-encoder reranker
# reads (question, chunk) together and reorders them; we keep the top RAG_TOP_K.
# Falls back to embedding order if the reranker model can't be loaded.
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"   # multilingual (Korean), no auth
RAG_CANDIDATES = 10        # candidates fetched by embedding before reranking
RAG_USE_RERANK = os.environ.get("RAG_RERANK", "1") != "0"   # set RAG_RERANK=0 to disable

# Relevance gate: if the top (reranked) chunk scores below this, the question is
# off-topic or not covered by the documents. Instead of letting the LLM answer
# from a weak/wrong chunk (hallucination), return a warm referral. Calibrated
# for the cross-encoder's 0-1 relevance score (valid matches are usually > 0.5,
# off-topic < 0.1). Set RAG_MIN_RELEVANCE=0 to disable the gate.
RAG_MIN_RELEVANCE = float(os.environ.get("RAG_MIN_RELEVANCE", "0.25"))

# Exclude '명단/현황' directory spreadsheets from the index. These are address
# lists (경로당·시설 현황) — pure location data, not Q&A content — and they flood
# retrieval with many short, near-duplicate rows that crowd out real answers
# (confirmed by GT_DEBUG). A file is skipped if its name contains any of these
# substrings. They belong in a map/location lookup, not the semantic index.
# Override with RAG_EXCLUDE_DOCS="a,b" (comma-separated); set "" to disable.
# Takes effect on re-index (RAG_REINDEX=1).
RAG_EXCLUDE_DOCS = [s.strip() for s in os.environ.get(
    "RAG_EXCLUDE_DOCS", "현황,silverleisure,silverhome,silverhouse").split(",")
    if s.strip()]

# --- LLM backend ---------------------------------------------------------
# Answer generation backend. Default is "openai" (a cloud LLM API; GPT-4o, or
# any OpenAI-compatible endpoint such as Groq via OPENAI_BASE_URL). "gemini"
# (Google Gemini) is another cloud option, and "ollama" runs a local model
# on-device. If the chosen cloud backend has no API key, the pipeline falls
# back to local Ollama, then a transparent template, so the system always runs.
LLM_BACKEND = os.environ.get("LLM_BACKEND", "openai").lower()

# OpenAI (GPT-4o). Set your key at runtime:  OPENAI_API_KEY=sk-... python app.py
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Google Gemini via its OpenAI-compatible endpoint (free tier from Google AI
# Studio: https://aistudio.google.com/apikey). Reuses the OpenAI client code —
# only the base URL, key and model name differ. Get a key, then:
#   LLM_BACKEND=gemini GEMINI_API_KEY=... python demo_cli.py
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# "…-latest" auto-tracks the current Flash model, so it won't 404 when a
# specific version is retired for new users (e.g. gemini-2.5-flash was).
# Override to a pinned version if you prefer, e.g. GEMINI_MODEL=gemini-3.6-flash
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
# Native Gemini REST base (models/<model>:generateContent). Same endpoint the
# key works with for listing models, so it's more reliable than the
# OpenAI-compatibility layer (which 404s for some keys/projects).
GEMINI_BASE_URL = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")

# --- Local LLM (Ollama) — fallback backend -------------------------------
# Used when LLM_BACKEND=ollama, or as a fallback when the OpenAI key is absent.
# Runs via the Ollama server (http://localhost:11434). If neither backend is
# available, a transparent template fallback keeps the demo running.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Override at runtime with:  LLM_MODEL=qwen2.5:1.5b python eval_qa.py
LLM_MODEL = os.environ.get("LLM_MODEL", "exaone3.5:2.4b")  # Korean-native (LG AI)
LLM_TIMEOUT = 120         # seconds

# --- Agentic mode (experimental, src/agent.py) --------------------------
# A bounded tool-calling agent: the LLM plans, picks a tool (welfare search /
# facility lookup), observes, and repeats up to AGENT_MAX_STEPS before
# answering. Kept small and local; falls back to the deterministic pipeline
# whenever the model can't produce a valid tool call.
AGENT_MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "3"))
# Phase 2 planner: a compound question ("무릎도 아프고 난방비도 걱정") is split into
# up to this many single-topic sub-questions, each retrieved, then answered as one.
AGENT_MAX_SUBINTENTS = int(os.environ.get("AGENT_MAX_SUBINTENTS", "4"))
# Tool-calling works better on a model tuned for it; override without touching
# the answer model, e.g.  AGENT_MODEL=qwen2.5:7b  (stays local via Ollama).
AGENT_MODEL = os.environ.get("AGENT_MODEL", LLM_MODEL)
# When on (default), welfare questions are answered by the tool-calling agent,
# with an automatic fallback to the deterministic RAG path when the model can't
# produce a valid tool call. Set USE_AGENT=0 to force the classic pipeline
# (e.g. the fastest evaluation runs, or a small model that can't tool-call).
USE_AGENT = os.environ.get("USE_AGENT", "1") not in ("0", "false", "False", "")

# --- STT (Whisper) -------------------------------------------------------
WHISPER_MODEL = "base"    # tiny/base/small - base is a good speed/quality mix
WHISPER_LANGUAGE = "ko"   # elderly speak Korean

# --- Abnormal signal detection ------------------------------------------
# Public Korean sentiment model (no auth / token needed).
SENTIMENT_MODEL = "sangrimlee/bert-base-multilingual-cased-nsmc"
# LLM conversation judge: when on and an LLM is available, the detector also
# asks the LLM to rate the whole conversation (정상/주의/위험) and combines it
# with the rules (taking the higher severity). Rules remain the safety net, so
# turning this off (USE_LLM_SIGNAL=0) falls back to rules-only detection.
USE_LLM_SIGNAL = os.environ.get("USE_LLM_SIGNAL", "1") not in ("0", "false", "False", "")
# Fallback smaller multilingual option is handled in abnormal_signal.py.

# Symptom keywords to track across the conversation history. Grouped so that
# different phrasings of the same complaint count together.
SYMPTOM_KEYWORDS = {
    "무릎": ["무릎", "무릎이", "무릎 아프", "다리 아프", "다리가 아프"],
    "허리": ["허리", "허리가 아프", "허리 아프"],
    "두통": ["머리 아프", "머리가 아프", "두통", "어지러"],
    "가슴": ["가슴이 아프", "가슴 답답", "숨이 차", "숨쉬기"],
    "수면": ["잠을 못", "잠이 안", "불면", "밤에 못 자"],
    "외로움": ["외로", "혼자", "쓸쓸", "말할 사람이 없"],
    "우울": ["죽고 싶", "살기 싫", "우울", "의욕이 없", "희망이 없"],
    "식사": ["밥을 못", "입맛이 없", "먹기 싫", "굶"],
}

# Thresholds for the rule-based abnormal-signal decision.
SYMPTOM_REPEAT_THRESHOLD = 3      # same symptom mentioned >= N times -> flag
NEGATIVE_SENTIMENT_THRESHOLD = 0.6  # avg negative probability -> flag
# The sentiment model is binary (no neutral class), so a single info-seeking
# question can score as negative. Require a minimum number of utterances
# before the average-sentiment rule may fire, to avoid false alarms.
SENTIMENT_MIN_UTTERANCES = 3
# High-risk keywords escalate immediately regardless of counts.
CRISIS_KEYWORDS = ["죽고 싶", "살기 싫", "자살", "죽어야"]

# --- Anomaly detection: deviation from the person's own baseline ----------
# Anomaly = a meaningful change from an individual's normal pattern, measured
# by comparing a RECENT window against a BASELINE window. This needs multi-day
# history; in a single short session these metrics stay inactive.
RECENT_WINDOW_DAYS = 3        # "recent" behaviour window
BASELINE_WINDOW_DAYS = 14     # "normal/baseline" window (includes recent span)
MIN_BASELINE_UTTERANCES = 5   # need at least this much history to trust a baseline

# Emotional-distress keywords whose *emergence/increase* signals a mood shift.
EMOTION_KEYWORDS = ["외로", "쓸쓸", "혼자", "슬프", "우울", "그립", "보고 싶",
                    "눈물", "허전", "재미가 없", "의욕이 없", "희망이 없"]

# Thresholds for each baseline-vs-recent metric.
FREQ_DROP_THRESHOLD = 0.5         # recent chat rate <= 50% of baseline -> flag
SENTIMENT_SHIFT_THRESHOLD = 0.25  # recent avg negativity rose by >= this
KEYWORD_SHIFT_THRESHOLD = 0.30    # emotional-keyword rate rose by >= this
LENGTH_DROP_THRESHOLD = 0.5       # recent avg reply length <= 50% of baseline
