-- 대전노인복지 HUB — 관계형 스키마 (팀 과제 T1 · 강의 STEP 06)
--
-- 파일(profiles.json) 저장을 관계형 DB로 옮긴다. 사용자-프로필-대화기록이
-- 외래키로 연결되어(= 데이터가 서로 이어져) 전문 서비스의 뼈대가 된다.
--
-- 서버에서 한 번 실행:
--   sudo mysql < deploy/schema.sql
-- 또는 각자 DB에 들어가서:
--   mysql -u <본인이름> -p db_<본인이름> < deploy/schema.sql

CREATE DATABASE IF NOT EXISTS welfare_hub
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE welfare_hub;

-- 1) 사용자(계정)
CREATE TABLE IF NOT EXISTS users (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  name       VARCHAR(100) NOT NULL UNIQUE,      -- 로그인 성함(지금은 이것으로 식별)
  pw_hash    VARCHAR(255) NULL,                 -- 비밀번호 해시(Phase 2에서 사용)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2) 프로필(사용자 1명당 1개) — users 에 연결
CREATE TABLE IF NOT EXISTS profiles (
  user_id         INT PRIMARY KEY,
  age             INT      NULL,
  income_low      TINYINT  NULL,                -- 1=예 0=아니오 NULL=모름
  district        VARCHAR(20) NULL,
  living_alone    TINYINT  NULL,
  mobility_issue  TINYINT  NULL,
  chronic_illness TINYINT  NULL,
  gender          VARCHAR(10) NULL,             -- 남성/여성 (선택)
  phone           VARCHAR(20) NULL,             -- 연락처 (선택, 개인정보)
  updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 3) 대화 기록 — users 에 연결(한 사용자가 여러 대화)
CREATE TABLE IF NOT EXISTS chat_logs (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  user_id    INT NOT NULL,
  question   TEXT,
  answer     TEXT,
  sources    TEXT,                              -- 근거 출처(JSON 문자열)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_user_time (user_id, created_at)
) ENGINE=InnoDB;

-- 4) 복지 카탈로그(Phase 4) — 복지 정보를 DB로. src.seed_welfare 로 채운다.
--    (시딩 시 통째로 재생성되므로 컬럼은 거기서도 보장됨)
CREATE TABLE IF NOT EXISTS welfare_catalog (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  name       VARCHAR(120) NOT NULL,
  summary    VARCHAR(255),
  min_age    INT     NULL,
  need_income_low   TINYINT DEFAULT 0,
  need_living_alone TINYINT DEFAULT 0,
  need_mobility     TINYINT DEFAULT 0,
  need_illness      TINYINT DEFAULT 0,
  verify_note       TEXT NULL
) ENGINE=InnoDB;

-- 비밀번호 요청(어르신이 '사회복지사에게 알리기'를 누름) — 앱이 없으면 자동으로 만듦
CREATE TABLE IF NOT EXISTS pw_requests (
  name         VARCHAR(100) PRIMARY KEY,
  requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  issued_at    TIMESTAMP NULL,                   -- 사회복지사가 임시 비밀번호를 보낸 시각
  req_phone    VARCHAR(20) NULL                  -- 등록 번호가 없는 분이 요청 때 적은 번호
) ENGINE=InnoDB;

-- 임시 비밀번호(사회복지사가 만든 것)로 로그인하면 새 비밀번호를 직접 정하게 함
CREATE TABLE IF NOT EXISTS pw_temp (
  name       VARCHAR(100) PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- (기존 DB) 성별·연락처 컬럼 추가 — 앱이 처음 저장할 때 자동으로도 추가함
-- ALTER TABLE profiles ADD COLUMN gender VARCHAR(10) NULL;
-- ALTER TABLE profiles ADD COLUMN phone  VARCHAR(20) NULL;
-- ALTER TABLE profiles ADD COLUMN contact_phone VARCHAR(20) NULL;  -- 필요할 때 연락할 번호
