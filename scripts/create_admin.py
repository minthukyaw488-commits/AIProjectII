"""관리자(사회복지사) 계정 만들기 — 서버에서 한 번만 실행한다.

  python3 scripts/create_admin.py            # 기본 이름: config.ADMIN_USERS 의 첫 번째("관리자")
  python3 scripts/create_admin.py 복지사1     # 이름 지정(ADMIN_USERS 에도 들어 있어야 관리자 화면이 열림)

비밀번호는 화면에 보이지 않게 입력받는다(명령어·기록에 남지 않음).
일반 회원가입 화면에서는 관리자 이름으로 가입할 수 없게 막혀 있다.
"""
from __future__ import annotations

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, db  # noqa: E402


def main() -> int:
    name = (sys.argv[1] if len(sys.argv) > 1 else config.ADMIN_USERS[0]).strip()
    if not config.is_admin(name):
        print(f"'{name}' 은(는) ADMIN_USERS({', '.join(config.ADMIN_USERS)})에 없습니다. "
              "환경변수 ADMIN_USERS 에 추가한 뒤 다시 실행하세요.")
        return 1
    pw = getpass.getpass(f"'{name}' 관리자 비밀번호(8자 이상): ")
    if len(pw) < 8:
        print("비밀번호는 8자 이상으로 해 주세요.")
        return 1
    if getpass.getpass("비밀번호 확인: ") != pw:
        print("비밀번호가 서로 다릅니다.")
        return 1
    ok, msg = db.signup(name, pw)
    print(("✅ " if ok else "⚠️ ") + msg + f" — 관리자 계정: {name} (저장소: {db.backend_name()})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
