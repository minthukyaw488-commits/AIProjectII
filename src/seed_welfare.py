"""
복지 카탈로그 시딩 — 코드의 기본 복지표(WELFARE_TABLE)를 DB 카탈로그로 넣는다.

하드코딩된 복지 정보를 '관계형 DB'로 옮기는 Phase 4. 한 번 실행하면
welfare_catalog 테이블이 채워지고, 이후 추천은 DB에서 복지 목록을 읽는다.
(DB 미설정이면 data/welfare_catalog.json 파일에 저장 — 어디서나 동작)

  USE_MYSQL=1 DB_HOST=localhost DB_USER=root DB_PASSWORD= DB_NAME=welfare_hub \
    python -m src.seed_welfare
"""
from __future__ import annotations

from src import db
from src.welfare_rules import WELFARE_TABLE, to_dict


def main():
    items = [to_dict(w) for w in WELFARE_TABLE]
    n = db.seed_welfare(items)
    print(f"복지 카탈로그 시딩 완료: {n}건  (저장소: {db.backend_name()})")
    print("저장된 복지:", ", ".join(it["name"] for it in items))


if __name__ == "__main__":
    main()
