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
import hashlib
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
_USERS_JSON = os.path.join(_DATA, "users.json")   # 파일 폴백용 계정(이름→해시)

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


# ── 비밀번호 해시(표준 라이브러리 pbkdf2) ────────────────────────────
def _hash_pw(password: str, salt: bytes | None = None) -> str:
    """salt 와 pbkdf2-sha256 으로 비밀번호를 해시한다(평문 저장 금지)."""
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + "$" + dk.hex()


def _verify_pw(password: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), 100_000)
        return dk.hex() == dk_hex
    except Exception:                            # noqa: BLE001
        return False


# ── 계정(회원가입·로그인) ─────────────────────────────────────────────
def signup(name: str, password: str):
    """새 계정 생성. (ok, msg)."""
    if not name or not password:
        return False, "성함과 비밀번호를 입력해 주세요."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."
    pw = _hash_pw(password)
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute("SELECT id, pw_hash FROM users WHERE name=%s", (name,))
                    row = cur.fetchone()
                    if row and row["pw_hash"]:
                        return False, "이미 있는 계정입니다. 로그인해 주세요."
                    if row:                       # 레거시(비번 없는) 계정 → 비번 설정
                        cur.execute("UPDATE users SET pw_hash=%s WHERE id=%s",
                                    (pw, row["id"]))
                    else:
                        cur.execute("INSERT INTO users (name, pw_hash) VALUES (%s,%s)",
                                    (name, pw))
                return True, "회원가입 완료"
            finally:
                c.close()
        users = _load_json(_USERS_JSON)
        if name in users and users[name]:
            return False, "이미 있는 계정입니다. 로그인해 주세요."
        users[name] = pw
        _save_json(_USERS_JSON, users)
        return True, "회원가입 완료"


def login_check(name: str, password: str):
    """로그인 검증. (ok, msg). 계정 없으면 회원가입 유도."""
    if not name or not password:
        return False, "성함과 비밀번호를 입력해 주세요."
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute("SELECT pw_hash FROM users WHERE name=%s", (name,))
                    row = cur.fetchone()
                    if not row:
                        return False, "계정이 없습니다. 회원가입을 해 주세요."
                    if not row["pw_hash"]:        # 레거시 계정: 비번 없음 → 통과
                        return True, "로그인(비밀번호 미설정 계정)"
                    return (_verify_pw(password, row["pw_hash"]),
                            "로그인 완료" if _verify_pw(password, row["pw_hash"])
                            else "비밀번호가 올바르지 않습니다.")
            finally:
                c.close()
        users = _load_json(_USERS_JSON)
        if name not in users:
            return False, "계정이 없습니다. 회원가입을 해 주세요."
        stored = users[name]
        if not stored:
            return True, "로그인(비밀번호 미설정 계정)"
        return (_verify_pw(password, stored),
                "로그인 완료" if _verify_pw(password, stored)
                else "비밀번호가 올바르지 않습니다.")


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


def list_users() -> list[str]:
    """가입/로그인한 모든 어르신 이름 목록(관리자 모니터용)."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute("SELECT name FROM users ORDER BY name")
                    return [r["name"] for r in cur.fetchall() if r.get("name")]
            except Exception:                     # noqa: BLE001
                return []
            finally:
                c.close()
        names = set(_load_json(_USERS_JSON).keys()) | set(_load_json(_PROFILE_JSON).keys())
        return sorted(n for n in names if n)


# ── 이상신호 알림(관리자 모니터용) ────────────────────────────────────
_ALERTS_JSON = os.path.join(_DATA, "alerts.json")
_ALERTS_DDL = (
    "CREATE TABLE IF NOT EXISTS alerts ("
    " id INT AUTO_INCREMENT PRIMARY KEY,"
    " user_id INT NULL,"
    " name VARCHAR(100),"
    " message TEXT,"
    " level VARCHAR(10),"           # 주의 / 위기
    " reason VARCHAR(255),"
    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    " INDEX idx_name_time (name, created_at)) ENGINE=InnoDB")


def save_alert(name: str, message: str, level: str, reason: str = ""):
    """어르신 대화에서 감지된 이상신호를 저장(관리자 모니터가 읽는다)."""
    import time
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute(_ALERTS_DDL)
                    uid = _user_id(cur, name) if name else None
                    cur.execute(
                        "INSERT INTO alerts (user_id, name, message, level, reason) "
                        "VALUES (%s,%s,%s,%s,%s)", (uid, name, message, level, reason))
                return
            except Exception as e:                # noqa: BLE001
                print(f"[db] save_alert 실패: {e}")
            finally:
                c.close()
        store = _load_json(_ALERTS_JSON)
        store.setdefault("alerts", []).append({
            "name": name, "message": message, "level": level, "reason": reason,
            "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        _save_json(_ALERTS_JSON, store)


def clear_alerts():
    """저장된 이상신호 알림을 모두 비운다(관리자가 확인 후 초기화)."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute("DELETE FROM alerts")
                return
            except Exception:                     # noqa: BLE001
                pass
            finally:
                c.close()
        _save_json(_ALERTS_JSON, {"alerts": []})


def list_alerts(limit: int = 500) -> list[dict]:
    """최근 이상신호 알림(최신 → 오래된). 각 항목: name·message·level·reason·time."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute(_ALERTS_DDL)
                    cur.execute(
                        "SELECT name, message, level, reason, created_at "
                        "FROM alerts ORDER BY created_at DESC LIMIT %s", (limit,))
                    rows = cur.fetchall()
                    for r in rows:
                        r["time"] = str(r.pop("created_at"))
                    return rows
            except Exception:                     # noqa: BLE001
                return []
            finally:
                c.close()
        rows = _load_json(_ALERTS_JSON).get("alerts", [])
        return list(reversed(rows))[:limit]


# ── 복지 카탈로그(복지 정보를 DB로 · Phase 4) ─────────────────────────
_CATALOG_JSON = os.path.join(_DATA, "welfare_catalog.json")
_CATALOG_COLS = ("name", "summary", "min_age", "need_income_low",
                 "need_living_alone", "need_mobility", "need_illness",
                 "verify_note")


def seed_welfare(items: list[dict]):
    """복지 목록을 카탈로그에 넣는다(참조 데이터라 통째로 재생성). items 는
    welfare_rules 의 Welfare 를 dict 로 바꾼 것."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS welfare_catalog")
                    cur.execute(
                        "CREATE TABLE welfare_catalog ("
                        " id INT AUTO_INCREMENT PRIMARY KEY,"
                        " name VARCHAR(120) NOT NULL,"
                        " summary VARCHAR(255),"
                        " min_age INT NULL,"
                        " need_income_low TINYINT DEFAULT 0,"
                        " need_living_alone TINYINT DEFAULT 0,"
                        " need_mobility TINYINT DEFAULT 0,"
                        " need_illness TINYINT DEFAULT 0,"
                        " verify_note TEXT) ENGINE=InnoDB")
                    for it in items:
                        cur.execute(
                            "INSERT INTO welfare_catalog "
                            "(name, summary, min_age, need_income_low, "
                            " need_living_alone, need_mobility, need_illness, "
                            " verify_note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (it["name"], it["summary"], it["min_age"],
                             int(it["need_income_low"]), int(it["need_living_alone"]),
                             int(it["need_mobility"]), int(it["need_illness"]),
                             it["verify_note"]))
                return len(items)
            finally:
                c.close()
        _save_json(_CATALOG_JSON, {"items": items})
        return len(items)


def list_welfare() -> list[dict]:
    """카탈로그의 복지 목록. 비어 있으면 빈 리스트(→ 코드 기본표 사용)."""
    with _lock:
        c = _conn()
        if c:
            try:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT name, summary, min_age, need_income_low, "
                        "need_living_alone, need_mobility, need_illness, verify_note "
                        "FROM welfare_catalog ORDER BY id")
                    rows = cur.fetchall()
                    for r in rows:
                        for k in ("need_income_low", "need_living_alone",
                                  "need_mobility", "need_illness"):
                            r[k] = bool(r[k])
                    return rows
            except Exception:                    # noqa: BLE001 (테이블 없음 등)
                return []
            finally:
                c.close()
        return _load_json(_CATALOG_JSON).get("items", [])
