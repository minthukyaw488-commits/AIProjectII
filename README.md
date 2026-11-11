# 대전 독거노인 복지 안내 · 이상신호 감지 시스템
### On-device LLM + RAG for elderly welfare (Daejeon)

대전광역시 독거노인을 위한 음성·문자 AI입니다. 어르신이 음성 또는 글로 복지
관련 질문을 하면 **대전 공공문서에 근거해(RAG) LLM이 답변**하고, 대화 속 반복
증상 호소나 정서적 이상신호를 감지해 **사회복지사에게 알림**을 보냅니다.

> **구성 원칙**: 현재 배포는 **온디바이스(로컬 Ollama) LLM — EXAONE 3.5 2.4B** 와
> **RAG**로 답변을 생성합니다(개인정보가 외부로 나가지 않음). LLM은 언어 능력을,
> RAG는 대전 공공데이터에 대한 **근거**를 제공해 환각을 막습니다. 검색·재랭킹·
> 음성인식·이상신호 분석도 모두 로컬에서 수행합니다. 답변 모델은 `LLM_BACKEND`
> 로 교체할 수 있어 클라우드 API(OpenAI·Gemini)로도 전환 가능하지만, **평가·시연에
> 사용한 모델은 온디바이스 EXAONE 3.5 2.4B** 입니다.

---

## 개발 진행 현황 (Roadmap)

| 단계 | 내용 | 상태 |
|---|---|---|
| **1. 텍스트 대화** | RAG 기반 복지 Q&A (정제·재랭킹·관련성 게이트·의도 라우팅) | ✅ **완료** |
| **2. 이상신호 감지** | 감정 분석 + 증상 반복 + 개인 baseline 지표 | ✅ 구현 (고도화 예정) |
| **3. 두 모델 융합** | 하나의 입력을 ①복지 안내 + ②이상신호로 동시 처리 | ✅ 통합 완료 |
| 4. 음성 대화 | STT·TTS voice-to-voice (핸즈프리) | 🔷 실험 구현 |
| 5. UI 디자인 | 정부포털 스타일 · 접근성 · 모바일/PWA | ✅ 구현 |
| 6. 평가 | 정량 평가 하네스 (RAG·이상신호·답변품질·모델비교) | ✅ 구축 |
| **7. 사람 맞춤형** | 계정별 프로필로 **받을 수 있는 복지 자동 추천** + 프로필 반영 상담 | ✅ **구현** |
| **8. 계정·관계형 DB** | 회원가입·비밀번호(해시), MySQL(users·profiles·chat_logs·복지 카탈로그), 대화 기억 | ✅ **구현** |
| **9. 배포(서비스화)** | AWS 서버 공개 배포 · 고정 IP · 폰 접속(PWA) | ✅ **구현** |

**성능 (재현 가능):** 사람이 만든 정답지(`data/eval/ground_truth_rag.jsonl`,
200문항 = 정보 질문 150 + 범위 밖 50)로 **검색 정확도**와 **범위 밖 안전 거절**,
그리고 **이상신호 감지**를 정량 측정합니다. 측정 지표는 **Hit@1 / Hit@3**(정답
근거가 상위 1·3개 안에 검색됐는가), **범위 밖 거절률**, 이상신호 **3단계 정확도 ·
위험 Recall** 입니다.

> 📊 **최신 수치는 `data/eval/eval_report.md` 에 자동 기록됩니다.**
> 재현: `RAG_REINDEX=1 python eval_ground_truth.py` (로컬 Ollama·모델 필요).
> 숫자를 본문에 직접 적지 않는 이유: 온디바이스 2.4B 모델과 코퍼스가 바뀌면
> 값이 달라지므로, **커밋된 리포트가 유일한 공식 수치**가 되도록 합니다.

> ⚠️ Hit@K·거절률은 **검색 전용** 지표라 답변 경로(에이전트 on/off)와 무관합니다.
> 답변 문장의 정확도(사실 일치·충실성)는 별도 평가이며, 과장된 수치를 본문에
> 싣지 않습니다. 필요한 답변 품질 지표는 정답지의 `facts` 필드로 측정할 수 있습니다.

---

## 시스템 아키텍처 (2-layer)

```
어르신 입력 (음성 또는 문자)
    │
  STT (Whisper, 로컬)  →  텍스트
    │
  의도 라우팅 ── 인사·잡담 ─▶ 따뜻한 대화형 응답 (RAG 미사용)
    │  └ 복지 질문
    ├─▶ Layer 1: RAG  (정제 → 섹션 청킹 → bge-m3 임베딩 → ChromaDB 후보 10
    │              → cross-encoder 재랭킹 → 관련성 게이트 → 상위 3)
    │
    └─▶ Layer 2: 이상신호 분석 (증상 반복 + 감정 점수 + 개인 baseline)
    │
  LLM (온디바이스 로컬 Ollama · EXAONE 3.5 2.4B / 클라우드 API 전환 가능) — 검색 근거만으로 한국어 답변
    │
  응답 생성  +  (이상신호 시) 사회복지사 알림 요약
```

**핵심 설계**
- **정확성(근거 기반)**: LLM이 아는 지식이 아니라 검색된 대전 공공문서 근거로만 답변.
- **개인정보 보호**: 검색·이상신호 분석은 로컬, 민감정보는 서버 암호화·접근통제로 처리.
  (`LLM_BACKEND=ollama`로 답변까지 완전 온디바이스 실행도 선택 가능.)
- **안정성**: 모델 추론을 Streamlit과 분리된 별도 워커 프로세스에서 실행(bus error 방지).
- **검색 정밀도**: 임베딩으로 후보를 넓게 뽑고 cross-encoder로 재랭킹.
- **환각 억제**: 관련성 게이트 — 검색 점수가 낮으면 잘못된 근거로 답하지 않고 주민센터 안내.
- **자연스러운 대화**: 인사/잡담은 라우터가 따뜻하게 응대.
- **off-domain 가드**: 복지와 무관한 질문(투자·반려동물·여행·가전 등)은 검색 전에
  걸러 곧바로 안전 안내 → 대규모 시설 데이터에서도 환각 없이 100% 거절.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `src/config.py` | 모델·임계값 등 설정 (LLM/임베딩/재랭킹/게이트) |
| `src/rag_pipeline.py` | **Step 1** 문서 로딩(PDF/MD/TXT/CSV/XLS/XLSX)·정제·청킹·재랭킹·검색 |
| `src/reranker.py` | Cross-encoder 재랭킹 (BAAI/bge-reranker-v2-m3) |
| `src/router.py` | 의도 라우팅 (인사·잡담 vs 복지 질문) |
| `src/embeddings.py` | bge-m3 임베딩 (+ 오프라인 TF-IDF 대체) |
| `src/stt.py` | **Step 2** Whisper 음성인식 |
| `src/abnormal_signal.py` | **Step 3** 감정 분석 + 증상 반복 + baseline 이상징후 |
| `src/llm.py` | LLM 클라이언트(클라우드 API: OpenAI/GPT-4o·Gemini·Groq, 또는 로컬 Ollama) + 프롬프트(근거 기반·잡담·거절) |
| `src/pipeline.py` | **Step 4** 전체 통합 (라우팅·게이트·알림) |
| `src/agent.py` | **실험** 에이전트 (도구 호출 + 다중 의도 플래너, 로컬·안전) |
| `src/worker.py`, `src/worker_server.py` | 모델 추론용 별도 워커 프로세스 |
| `src/vad_stream.py`, `src/tts.py` | 핸즈프리 음성(VAD) · 로컬 TTS |
| `app.py` | Streamlit 웹/모바일 데모 (정부포털 스타일, PWA, 로그인·맞춤 복지·대화 기억) |
| `src/welfare_rules.py` | **사람 맞춤형** 복지 자격 규칙표 + 프로필 매칭 |
| `src/db.py` | 저장소 계층 — 프로필·대화·계정(MySQL 또는 파일), 비밀번호 해시 |
| `src/seed_welfare.py` | 복지 카탈로그 시딩(기본표 → DB) |
| `profile_match.py` | 맞춤형 CLI 데모(프로필→복지 추천, `--rag` 근거) |
| `profile_server.py`, `app_personal.py` | 맞춤형 웹(FastAPI) — 폼·로그인·맞춤 상담 |
| `deploy/` | 배포 가이드·스키마·systemd (`DEPLOY*.md`, `schema.sql`, `STABLE_ACCESS.md`) |
| `desktop_app.py` | 데스크톱 앱(전체화면) 실행기 |
| `run_phone.sh` | 휴대폰용 로컬 HTTPS 실행기 (마이크 지원) |
| `set_hero_image.py` | 홈 배너 배경 이미지 설정 |
| `evaluate.py` | RAG Hit@k · 이상신호 F1 평가 |
| `eval_qa.py` | 답변 품질 평가 (200문항, `data/eval/qa_200.jsonl`) |
| `eval_models.py` | 여러 로컬 LLM 성능 비교 |
| `eval_agent.py` | 결정형 vs 에이전트 파이프라인 비교 |
| `make_eval200.py` | 200문항 평가셋 생성기 |
| `data/welfare_docs/` | 복지 문서 (실데이터 + 샘플) |

## 설치 & 실행

```bash
pip install -r requirements.txt

# 답변 LLM 백엔드 선택 (기본: 클라우드 API)
#  · 클라우드 API (기본):
export LLM_BACKEND=openai
export OPENAI_API_KEY=...          # OpenAI(GPT-4o) 또는 Groq 키
# Groq 등 OpenAI 호환 엔드포인트를 쓸 때:
#   export OPENAI_BASE_URL=https://api.groq.com/openai/v1
#   export OPENAI_MODEL=openai/gpt-oss-20b
#  · 또는 온디바이스(로컬) 실행:
#   export LLM_BACKEND=ollama && ollama pull exaone3.5:2.4b
# 키가 없으면 자동으로 로컬 Ollama → 템플릿으로 폴백하여 항상 동작합니다.

# 문서 색인 확인 (RAG 검색)
python -m src.rag_pipeline

# 웹/모바일 데모 (Streamlit) — 모델이 설치된 동일 환경의 파이썬으로 실행.
python -m streamlit run app.py

# 데스크톱 앱 (태블릿·PC·미니PC)
python desktop_app.py

# 답변 품질 평가 (200문항)
python eval_qa.py
```

> `streamlit run`이 다른 환경(anaconda base 등)을 가리키면 워커가 그 환경의
> torch를 로드하다 bus error로 죽을 수 있습니다. 모델이 설치된 환경에서
> `python -m streamlit run app.py`로 실행하거나, `WORKER_PYTHON`에 그 환경의
> 파이썬 경로를 지정하세요.

## 데이터

복지 문서를 `data/welfare_docs/`에 넣으면 **자동으로 색인**됩니다. 지원 형식:

| 형식 | 처리 |
|---|---|
| `.pdf` | pdfplumber 추출 + 스캔 페이지 OCR(tesseract-kor) |
| `.md`, `.txt` | 직접 로딩 |
| `.csv` | 행을 "컬럼: 값, …" 텍스트로 변환 (cp949/euc-kr 지원) |
| `.xls`, `.xlsx` | pandas로 로딩 (openpyxl/xlrd 필요) |

문서는 **정제(머리말/꼬리말·페이지번호·기호 잡음 제거) → 섹션 단위 청킹 →
저품질 청크 제거** 후 색인됩니다. (`.hwp`는 아직 미지원 — 향후 과제)

**현재 사용 데이터(예)**: 보건복지부 「2025 노인보건복지 사업안내(1·2권)」,
대전광역시 노인맞춤돌봄·재가노인 식사배달 현황(CSV), 실버 시설 현황(XLS) 등.

## 사람 맞춤형 (Personalization)

일반 챗봇은 누구에게나 같은 정보를 주지만, 이 시스템은 **계정에 내 정보를 넣으면
받을 수 있는 복지를 먼저 알려주고**, 이어지는 상담도 그 사람 상황에 맞춥니다.

- **프로필 → 자격 매칭(규칙):** 나이·소득·거주 구·독거·거동·질환을 대전 복지
  자격 조건과 자동 대조해 **받을 수 있음 / 확인 필요 / 대상 아님**으로 분류
  (`src/welfare_rules.py`). 복지 목록은 **DB 카탈로그**에서 읽습니다(`welfare_catalog`).
- **맞춤 상담:** 질문에 프로필을 반영해 "이 분 상황에 맞춰" 답하고, 인사·잡담은
  복지를 나열하지 않고 짧게 응대.
- **문서 근거 결합:** 추천된 복지마다 RAG로 실제 공문서 근거(출처·유사도)를 함께 표시.
- 실행: 포털(`app.py`) 로그인→내 정보→맞춤 복지 카드, CLI(`profile_match.py --rag`),
  API(`profile_server.py` / `app_personal.py`).

## 계정 · 관계형 DB (MySQL)

프로필·대화를 파일이 아닌 **관계형 DB**에 저장해 전문 서비스의 뼈대를 갖춥니다
(`src/db.py`, `deploy/schema.sql`). `USE_MYSQL=1`이면 MySQL, 아니면 JSON 파일로
자동 폴백하여 **어디서나 동작**합니다.

```
users ─< profiles        (사용자 1명당 프로필 1개)
users ─< chat_logs       (사용자 1명당 대화 여러 개 — "지난 대화" 기억)
welfare_catalog          (복지 정보를 DB로)
```

- **보안 로그인:** 회원가입/로그인, 비밀번호는 **salt + pbkdf2-sha256 해시**로 저장(평문 금지).
- **대화 기억:** 로그인하면 지난 대화를 불러와 이어서 보여줌.
- 개인정보(`profiles.json`·`chat_logs.json`·`users.json`)는 `.gitignore`로 커밋 제외.

```bash
# MySQL 사용 시
mysql -u root < deploy/schema.sql
USE_MYSQL=1 DB_USER=... DB_PASSWORD=... DB_NAME=welfare_hub python -m src.seed_welfare  # 복지 카탈로그 시딩
USE_MYSQL=1 DB_USER=... DB_PASSWORD=... DB_NAME=welfare_hub python -m streamlit run app.py
```

## 배포 (서비스화 · 서버 · 폰)

노트북 없이도 **인터넷에서 누구나 접속**할 수 있게 서버에 배포합니다.
가이드: `deploy/DEPLOY.md`(FastAPI), `deploy/DEPLOY_STREAMLIT.md`(Streamlit),
`deploy/STABLE_ACCESS.md`(고정 IP·도메인), `docs/demo_rehearsal.md`.

- **AWS GPU 서버**에 Apache·FastAPI/Streamlit·Ollama·MySQL을 올려 공개 URL로 접속.
- **고정 IP(Elastic IP)**로 서버를 껐다 켜도 같은 주소 유지.
- **폰**: 공개 URL을 모바일 브라우저로 열고 **홈 화면에 추가**하면 앱처럼 전체화면(PWA).
- **지연 로딩:** 화면(로그인·프로필·포털)은 즉시 뜨고, 무거운 인덱싱은 첫 질문에서만
  수행(이후 캐시돼 빠름).
- `systemd`로 상시 가동(터미널을 닫아도 유지).

## 이상신호 판정 로직 (rule-based)

`src/config.py`에서 조정할 수 있습니다.

- **증상 반복**: 같은 증상군(무릎/허리/수면/우울 등)을 `SYMPTOM_REPEAT_THRESHOLD`(기본 3)회 이상 → 플래그
- **부정 감정**: 최근 대화 평균 부정 확률이 `NEGATIVE_SENTIMENT_THRESHOLD`(기본 0.6) 이상 → 플래그
- **위기 신호**: `CRISIS_KEYWORDS`("죽고 싶다" 등) 감지 시 → 즉시 긴급 알림
- **이상징후(baseline 대비 변화)**: 최근(3일) vs 평소(14일) 구간을 비교해 대화 빈도
  감소·부정감정 상승·외로움 표현 증가·응답 길이 위축 4지표로 정량화

## 평가 (Evaluation)

**공식 평가 하네스(재현 가능):**

```bash
RAG_REINDEX=1 python eval_ground_truth.py     # 검색 Hit@1/Hit@3 · 범위 밖 거절 · 이상신호
#   → data/eval/eval_report.md (커밋된 공식 수치) + data/eval/results.json 생성
```

정답지(`data/eval/ground_truth_rag.jsonl`, 200문항 = 정보 150 + 범위 밖 50)를 기준으로
측정합니다. **측정 지표**

| 지표 | 의미 | 결과 |
|---|---|---|
| Hit@1 / Hit@3 | 정답 근거가 상위 1 / 3개 안에 검색됐는가 | → `eval_report.md` |
| 범위 밖 거절률 | 복지와 무관한 질문을 지어내지 않고 안전하게 거절 | → `eval_report.md` |
| 이상신호 3단계 정확도 · 위험 Recall | 정상/주의/위험 분류, 위기 신호를 놓치지 않는 비율 | → `eval_report.md` |

> **수치를 본문에 직접 적지 않습니다.** 온디바이스 2.4B 모델과 코퍼스가 바뀌면 값이
> 달라지므로, 위 명령으로 생성·커밋되는 `data/eval/eval_report.md` 가 **유일한 공식
> 수치**입니다(실행 환경·모델·일시가 함께 기록됨).

- **범위 밖 거절**: 의도 라우터의 off-domain 가드가 복지와 무관한 질문(투자·반려동물·
  여행·가전 등)을 검색 전에 걸러 환각을 원천 차단합니다.
- **재랭킹 효과(ablation)**: `RAG_RERANK=0` vs `RAG_RERANK=1` 로 각각 돌려 Hit@3 차이를
  비교하면 재랭킹 기여도를 수치로 확인할 수 있습니다.
- **검색 지표의 범위**: Hit@K·거절률은 **검색 전용** 지표라 답변 경로(에이전트 on/off)와
  무관합니다. **답변 문장의 사실 정확도**는 별도 평가이며, 정답지의 `facts` 필드로
  측정하도록 확장할 수 있습니다(현재는 키워드 기반 검색 지표가 공식).
- **한계(정직한 고지)**: 평가셋은 자체 제작(독립 held-out 미구성), 검색 지표는 키워드
  부분일치 기반입니다. 답변 품질(충실성·사실성)은 사람/LLM 평가로 보강이 필요합니다.

## 실험적 에이전트 모드 (Agentic · Phase 1+2)

복지 질문의 **기본 답변 경로는 이 로컬 에이전트**입니다(`USE_AGENT=1`, 기본값). LLM이
스스로 도구를 고르고 복합 질문을 분해하며, 도구 호출에 실패하면 고정 흐름
(route→retrieve→rerank→gate→answer)의 **결정형 파이프라인으로 자동 후퇴**합니다.
`USE_AGENT=0`으로 결정형을 강제할 수 있습니다. **온디바이스·개인정보·안전** 원칙은
그대로 지킵니다.

- **Phase 1 — 도구 호출(ReAct, bounded):** 화이트리스트 도구(`search_welfare_docs`,
  `lookup_facility`)를 최대 `AGENT_MAX_STEPS`회 호출. 반복/오형식 호출은 즉시 중단.
- **Phase 2 — 다중 의도 플래너:** "무릎도 아프고 난방비도 걱정이고 일자리도 필요해요"를
  주제별 하위 질문으로 나눠 각각 검색·게이트 후 하나로 합칩니다. 단일 질문은 휴리스틱으로
  분해를 건너뛰어 과분할을 막습니다.
- **역할 분리(hybrid):** 에이전트 모델은 '무엇을 할지'만 결정하고, **최종 답변은 항상
  한국어 답변 모델(EXAONE)이 `ANSWER_SYSTEM_PROMPT`로 근거 위에서 합성** → 답변 품질이
  에이전트 모델 성능과 무관하게 유지됩니다.
- **안전:** 관련성 게이트 유지(근거 없으면 주민센터 안내), 그리고 스몰토크·off-domain·
  LLM 부재·형식 오류 시 **결정형 파이프라인으로 자동 후퇴**해 성능이 나빠지지 않습니다.

```bash
python -m src.agent                                  # 데모(추적 로그 포함)
AGENT_MODEL=llama3.1:latest python -m src.agent      # 분해가 더 정확한 플래너
python eval_agent.py                                 # 결정형 vs 에이전트 비교
EVAL_LIMIT=30 python eval_agent.py                   # 빠른 부분 비교
```

**관찰(실측):** 표준(단일 의도) 질문에서 에이전트는 결정형과 **동등**(20문항 부분셋에서
양쪽 100%, regression 없음)하며, 복합 질문 처리 능력을 추가로 얻습니다. 다만 **소형 로컬
모델(2.4B)은 도구 선택·질문 분해가 불안정**(과분할/미분할)하여, 플래너에는 더 큰 로컬
모델(예: llama3.1)이 필요합니다 — "안전·저사양이 우선인 환경에서 통제형이 기본이고
에이전트는 확장 옵션"이라는 설계 근거를 실측으로 뒷받침합니다.

## 휴대폰에서 사용 (모바일 웹 · PWA)

어르신 휴대폰은 앱(웹/PWA) 화면·마이크 역할을 하고, 서버(또는 집/센터의 허브)가
RAG 검색과 LLM API 호출로 답변을 생성합니다. 같은 WiFi의 허브로도, 인터넷의
서버로도 접속할 수 있습니다.

```bash
# 서버/허브에서 실행 (휴대폰이 접속)
python -m streamlit run app.py --server.address 0.0.0.0

# 음성(마이크)까지 쓰려면 로컬 HTTPS 실행기
./run_phone.sh
```
휴대폰 브라우저에서 접속 후 **홈 화면에 추가**하면 앱처럼 전체화면으로 열립니다.

## 모델 및 데이터

- **LLM(답변)**: 온디바이스 로컬 `exaone3.5:2.4b`(기본·평가/시연에 사용) — 또는 클라우드 API `GPT-4o`·Gemini·Groq 전환 가능
- **임베딩**: `BAAI/bge-m3` (다국어, 인증 불필요, 로컬)
- **재랭킹**: `BAAI/bge-reranker-v2-m3` (cross-encoder)
- **STT**: Whisper (`faster-whisper`)
- **감정 분석**: 공개 한국어 sentiment 모델 (Hugging Face)

각 구성요소는 모델을 내려받을 수 없는 환경에서도 파이프라인이 끊기지 않도록
로컬 대체 경로(TF-IDF 임베딩, 인메모리 벡터, 감정 어휘 사전, 검색결과 요약)를
갖습니다.

## 참고문헌 (모델·기법 근거)

- Lewis et al. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* NeurIPS 2020. arXiv:2005.11401
- Chen et al. *M3-Embedding (BGE-M3).* ACL 2024 Findings. arXiv:2402.03216
- Nogueira & Cho. *Passage Re-ranking with BERT.* arXiv:1901.04085
- LG AI Research. *EXAONE 3.5.* arXiv:2412.04862
- Qwen Team. *Qwen2.5 Technical Report.* arXiv:2412.15115
- Son et al. *KMMLU: Measuring Massive Multitask Language Understanding in Korean.* NAACL 2025. arXiv:2402.11548
- Radford et al. *Robust Speech Recognition via Large-Scale Weak Supervision (Whisper).* ICML 2023. arXiv:2212.04356
