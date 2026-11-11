"""
Standalone assistant worker (runs as its own process).

Launched via `python -m src.worker_server` by AssistantClient. It talks
line-delimited JSON over stdin/stdout and imports ONLY the pipeline - never
Streamlit. That matters: when the worker was started with multiprocessing
"spawn", the child re-imported app.py and therefore imported Streamlit before
torch, and the mix of native libraries (pyarrow / OpenMP / torch) crashed with
a bus error (SIGBUS). A clean subprocess avoids importing Streamlit at all,
matching the environment where the models load fine.

Protocol
  stdout : ONE JSON object per line (responses only - kept clean)
  stderr : all logs and library noise (model download bars, prints)
  stdin  : ONE JSON request per line: {"cmd": "ask"|"ask_audio"|"state"|"reset"|"stop", ...}
"""
from __future__ import annotations
import json
import os
import sys

# Native-crash guards (belt and suspenders) before any heavy import.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# No-RAG mode (demo): answer with the LLM alone, no retrieved documents, so the
# RAG effect can be compared in the UI.
NO_RAG_SYSTEM = ("당신은 복지 상담 도우미입니다. 질문에 한국어로 2~3문장으로 "
                 "답하세요.")


def _turn_dict(res, bot) -> dict:
    return {
        "question": res.question,
        "answer": res.answer,
        "sources": list(res.sources),
        "alert": res.alert,
        **_state_dict(bot),
    }


def _state_dict(bot) -> dict:
    sig = bot.detector.evaluate()
    return {
        "is_abnormal": sig.is_abnormal,
        "crisis": sig.crisis,
        "avg_negative": sig.avg_negative,
        "symptom_counts": dict(sig.symptom_counts),
        "history_len": len(bot.detector.history),
        "metrics": dict(sig.metrics),
    }


def main() -> None:
    # Keep stdout pristine for JSON; send every other print to stderr.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    def log(msg: str) -> None:
        print(f"[worker] {msg}", file=sys.stderr, flush=True)

    def send(obj: dict) -> None:
        real_stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        real_stdout.flush()

    try:
        log("starting… importing pipeline")
        from src.pipeline import WelfareAssistant
        log("building assistant (loading models + indexing welfare docs)…")
        bot = WelfareAssistant(user_name="데모 어르신")
        log("assistant ready")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        send({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return

    send({"ready": True, "meta": {
        "rag_backend": bot.rag.backend,
        "embedder": bot.rag.embedder.backend,
        "llm": bot.llm.available,
        "sentiment": bot.detector.sentiment.backend,
        "alert_channels": bot.alerts.channels,
    }})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        cmd = req.get("cmd")
        if cmd == "stop":
            break
        try:
            if cmd == "ask":
                send(_turn_dict(
                    bot.ask_text(req["text"], profile=req.get("profile")), bot))
            elif cmd == "ask_norag":
                q = req["text"]
                sig = bot.detector.add_utterance(q)
                ans = (bot.llm.generate(q, system=NO_RAG_SYSTEM).strip()
                       if bot.llm.available else "(LLM 미연결)")
                send({"question": q, "answer": ans, "sources": [],
                      "alert": bot._maybe_alert(sig), **_state_dict(bot)})
            elif cmd == "ask_audio":
                send(_turn_dict(bot.ask_audio(req["path"]), bot))
            elif cmd == "transcribe":
                send({"text": bot.transcribe(req["path"])})
            elif cmd == "reset":
                bot.reset_conversation()
                send(_state_dict(bot))
            elif cmd == "state":
                send(_state_dict(bot))
            else:
                send({"error": f"unknown command: {cmd}"})
        except Exception as exc:
            send({"error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
