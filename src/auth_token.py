"""
로그인 유지용 서명 토큰.

Streamlit 은 페이지 reload(카드·칩 링크 클릭) 시 세션이 초기화되므로 URL 로
로그인을 되살려야 한다. 예전에는 ?u=<성함> 을 그대로 믿어서, 주소만 알면
누구나 남의 계정으로 들어갈 수 있었다. 이제는 서버 비밀키로 HMAC 서명한
토큰(?s=...)만 받아들이고, 만료 시간도 둔다.

비밀키: 환경변수 APP_SECRET, 없으면 data/.app_secret 파일을 자동 생성해 쓴다
(git 에 커밋하지 않음).
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import secrets
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SECRET_FILE = os.path.join(_HERE, "..", "data", ".app_secret")
TTL_SECONDS = int(os.environ.get("LOGIN_TTL_SECONDS", str(12 * 3600)))  # 12시간


def _secret() -> bytes:
    env = os.environ.get("APP_SECRET")
    if env:
        return env.encode("utf-8")
    try:
        with open(_SECRET_FILE, "rb") as f:
            key = f.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
    key = secrets.token_hex(32).encode("ascii")
    with open(_SECRET_FILE, "wb") as f:
        f.write(key)
    try:
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest())


def make_token(name: str) -> str:
    """성함 → 서명 토큰 (만료 시각 포함)."""
    payload = f"{_b64(name.encode('utf-8'))}.{int(time.time()) + TTL_SECONDS}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str | None) -> str | None:
    """올바르고 만료되지 않은 토큰이면 성함, 아니면 None."""
    if not token or token.count(".") != 2:
        return None
    try:
        name_b64, exp, sig = token.split(".")
        payload = f"{name_b64}.{exp}"
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        if int(exp) < time.time():
            return None
        return _unb64(name_b64).decode("utf-8") or None
    except Exception:                            # noqa: BLE001
        return None
