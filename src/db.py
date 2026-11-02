"""
저장소 계층 — 프로필·대화기록을 관계형 DB(MySQL)에 저장.

전문 서비스라면 데이터를 파일이 아니라 DB에 두고, 사용자-프로필-대화가 서로
연결(외래키)되어야 한다. 이 모듈이 그 한 창구다. 같은 함수가 두 백엔드를 쓴다:

  · USE_MYSQL=1 (+ DB 접속정보)  → MySQL (전문 서비스 경로, 강의 STEP 06)
  · 그 외 / 접속 실패            → JSON 파일 (data/*.json, 어디서나 동작·데모용)

환경변수(서버):
  USE_MYSQL=1 DB_HOST=localhost DB_USER=... DB_PASSWORD=... DB_NAME=welfare_hub

스키마는 deploy/schema.sql 참고.
"""
from __future__ import annotations
import json
import os
import threading

_PROFILE_KEYS = ("age", "income_low", "district", "living_alone",
                 "mobility_issue", "chronic_illness")
_BOOL_KEYS = ("income_low", "living_alone", "mobility_issue", "chronic_illness")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "..", "data")
_PROFILE_JSON = os.path.join(_DATA, "profiles.json")
_CHAT_JSON = os.path.join(_DATA, "chat_logs.json")

_USE_MYSQL = os.environ.get("USE_MYSQL", "0") not in ("0", "", "false", "False")
_lock = threading.Lock()


# ── MySQL ────────────────────────────────────────────────────────────
def _conn():
    """pymysql 연결. 설정이 없거나 실패하면 None(→ 파일 폴백)."""
    if not _USE_MYSQL:
        return None
    try:
        import pymysql
        return pymysql.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "welfare_hub"),
            charset="utf8mb4", autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:                       # noqa: BLE001
        print(f"[db] MySQL 연결 실패 → 파일 저장으로 폴백: {e}")
        return None


def _user_id(cur, name: str) -> int:
    """이름으로 사용자 id를 얻고, 없으면 만든다."""
    cur.execute("SELECT id FROM users WHERE name=%s", (name,))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute("INSERT INTO users (name) VALUES (%s)", (name,))
    cur.execute("SELECT id FROM users WHERE name=%s", (name,))
    return cur.fetchone()["id"]


def _b2i(v):
    return None if v is None else (1 if v else 0)


def _i2b(v):
    return None if v is None else bool(v)


# ── 파일 폴백 ──────────────────────────────────────────────────────────
def _load_json(path: str) -> dict:
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:                            # noqa: BLE001
        return {}


def _save_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ── 공개 API (앱이 쓰는 함수) ─────────────────────────────────────────
def get_profile(name: str):
    """사용자 프로필(dict) 또는 None."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT p.* FROM profiles p JOIN users u ON p.user_id=u.id "
                        "WHERE u.name=%s", (name,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    return {"age": row["age"], "district": row["district"],
                            **{k: _i2b(row[k]) for k in _BOOL_KEYS}}
            finally:
                c.close()
        return _load_json(_PROFILE_JSON).get(name)


def save_profile(name: str, profile: dict):
    """프로필 저장(사용자 없으면 생성)."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    uid = _user_id(cur, name)
                    cur.execute(
                        "REPLACE INTO profiles "
                        "(user_id, age, income_low, district, living_alone, "
                        " mobility_issue, chronic_illness) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (uid, profile.get("age"), _b2i(profile.get("income_low")),
                         profile.get("district"), _b2i(profile.get("living_alone")),
                         _b2i(profile.get("mobility_issue")),
                         _b2i(profile.get("chronic_illness"))))
                return
            finally:
                c.close()
        store = _load_json(_PROFILE_JSON)
        store[name] = {k: profile.get(k) for k in _PROFILE_KEYS}
        _save_json(_PROFILE_JSON, store)


def save_chat(name: str, question: str, answer: str, sources=None):
    """대화 한 줄 저장."""
    src = json.dumps(sources or [], ensure_ascii=False)
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    uid = _user_id(cur, name)
                    cur.execute(
                        "INSERT INTO chat_logs (user_id, question, answer, sources) "
                        "VALUES (%s,%s,%s,%s)", (uid, question, answer, src))
                return
            finally:
                c.close()
        store = _load_json(_CHAT_JSON)
        store.setdefault(name, []).append(
            {"question": question, "answer": answer, "sources": sources or []})
        _save_json(_CHAT_JSON, store)


def list_chats(name: str, limit: int = 20):
    """최근 대화 목록(오래된 → 최신)."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT question, answer, sources FROM chat_logs cl "
                        "JOIN users u ON cl.user_id=u.id WHERE u.name=%s "
                        "ORDER BY cl.created_at DESC LIMIT %s", (name, limit))
                    rows = cur.fetchall()[::-1]
                    for r in rows:
                        try:
                            r["sources"] = json.loads(r["sources"] or "[]")
                        except Exception:        # noqa: BLE001
                            r["sources"] = []
                    return rows
            finally:
                c.close()
        return _load_json(_CHAT_JSON).get(name, [])[-limit:]


def backend_name() -> str:
    return "mysql" if (_USE_MYSQL and _conn() is not None) else "file(json)"
