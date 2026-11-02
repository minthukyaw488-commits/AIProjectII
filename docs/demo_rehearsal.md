# 데모 리허설 체크리스트 — 대전노인복지 HUB

발표 전 이 순서대로 한 번 그대로 해 보면 당일에 안 막힌다.
🇰🇷 = 화면/멘트 · 🇲🇲 = 메모

---

## 0. 준비 (발표 10분 전 · 한 번만)

```bash
# 1) Ollama 켜고 모델 예열(첫 응답 지연 방지)
#    (Ollama 앱 실행 or: ollama serve)
curl -s http://localhost:11434/api/generate \
  -d '{"model":"exaone3.5:2.4b","prompt":"warmup","stream":false}' -o /dev/null

# 2) MySQL 켜기
brew services start mysql

# 3) welfare env + MySQL + Ollama 로 실행 (base 아님!)
conda activate welfare
USE_MYSQL=1 DB_HOST=127.0.0.1 DB_USER=root DB_PASSWORD= DB_NAME=welfare_hub \
LLM_BACKEND=ollama LLM_MODEL=exaone3.5:2.4b python -m streamlit run app.py
```

✅ 확인 체크
- [ ] `conda activate welfare` 됐나 (프롬프트에 `(welfare)`)
- [ ] Ollama 응답하나 (`ollama list` 에 exaone3.5:2.4b)
- [ ] MySQL 살아있나 (`mysqladmin -u root ping` → alive)
- [ ] 브라우저 자동으로 열리나 (localhost:8501)

🇲🇲 ဒီ ၄ ချက် မစခင် သေချာ စစ် — တစ်ခုခု ကျန်ရင် demo မှာ ရပ်မယ်

---

## 1. 로그인 / 회원가입 (보안)

🇰🇷 "먼저 로그인 화면입니다. 일반 복지 포털처럼 계정이 있고, 비밀번호는 해시로 안전하게 저장합니다."

- **회원가입** 탭 → 성함 `박어르신` · 비밀번호 `1234` · 확인 `1234` → 회원가입
- (보여주기) **로그인** 탭에서 틀린 비밀번호 → "비밀번호가 올바르지 않습니다" 뜨는 것 한 번 보여주면 보안 어필

🇲🇲 틀린 password ပြတာ = 보안 အချက် highlight

---

## 2. 내 정보 (프로필)

🇰🇷 "로그인하면 내 정보를 입력합니다. 이게 '사람 맞춤형'의 핵심입니다."

입력: 나이 `76` · 거주 `중구` · 저소득 `예` · 독거 `예` · 거동불편 `예` · 만성질환 `아니오` → 저장하고 시작하기

---

## 3. 내 맞춤 복지 카드 ⭐ (핵심)

🇰🇷 "일반 포털은 메뉴를 찾아야 하지만, 저희는 로그인하면 **받을 수 있는 복지를 먼저 카드로** 보여줍니다."

- 포털 상단 **"박어르신 님 맞춤 복지"** 섹션에 컬러 카드(기초연금·노인맞춤돌봄·식사배달·장기요양·치매검진·응급안전…)
- 카드 하나 클릭 → 그 복지를 챗봇이 **프로필에 맞춰** 설명

🇲🇲 ← ဒါ differentiator။ "일반 챗봇과 다르다" ဆိုတာ ဒီမှာ ပြ

---

## 4. 챗봇 맞춤 상담 ⭐ (핵심)

🇰🇷 "직접 물어볼 수도 있습니다."

입력: `식사배달 신청하고 싶어요`
→ 답변: 60세 이상 저소득 독거·거동불편 대상, 신청 방법, (중구 거주 반영) — **대전 공문서 근거 기반**

🇲🇲 답변 느리면 = 모델 cold-load → 0단계 warmup 했으면 빠름

(선택) RAG 효과 대비: `비행기표 싸게 사는 법?` → "자료에 없습니다 → 주민센터" (환각 안 함)

---

## 5. 대화 기억 (연속성)

🇰🇷 "로그아웃했다가 다시 들어와도 지난 대화를 기억합니다."

- 사이드바 **로그아웃** → **로그인** 탭 `박어르신` + `1234`
- → 아까 "식사배달" 대화가 그대로 보임 ✅

🇲🇲 ← 대화 기억 = DB 연속성 증명

---

## 6. 관계형 DB 증명 (교수님용 · 터미널)

🇰🇷 "데이터는 파일이 아니라 관계형 DB에 저장됩니다. 한 쿼리로 사용자·프로필·대화를 함께 조회합니다."

```bash
mysql -u root welfare_hub -e \
"SELECT u.name, p.age, p.district, LEFT(c.question,16) AS 질문 \
 FROM users u LEFT JOIN profiles p ON u.id=p.user_id \
 LEFT JOIN chat_logs c ON u.id=c.user_id;"
```
→ users ─ profiles ─ chat_logs 가 외래키로 연결된 것을 한 번에 보여줌 (팀 과제 T1)

---

## ⚠ 문제 발생 시 (복구)

| 증상 | 즉시 복구 |
|---|---|
| 답이 `[Ollama 미실행]` | Ollama 켜고 질문 다시(자동 복구됨) · 안 되면 streamlit 재시작 |
| 답이 영어/이상 | `LLM_BACKEND=ollama` 빠졌는지 — 재시작 |
| 모델 bus error | `ollama rm/pull exaone3.5:2.4b` 또는 `LLM_MODEL=qwen3.5:2b-q8_0` |
| worker code -10 | `base` 에서 실행함 → `conda activate welfare` 후 재시작 |
| DB 연결 실패 | 파일로 자동 폴백(앱은 동작) · MySQL 보이려면 `brew services start mysql` |
| 화면 안 뜸 | 포트 8501 · `(welfare)` 인지 확인 |

🇲🇲 **Backup:** 문제 생기면 PPT 9-11p(데모 캡처)로 설명 — "화면은 이렇게 동작합니다"

---

## ⏱ 리허설 타이밍 (전체 2~3분)
1 로그인 20s · 2 정보 20s · 3 맞춤카드 30s · 4 챗봇 40s · 5 대화기억 20s · 6 DB 20s

🇲🇲 핵심은 **3(맞춤 카드) + 4(챗봇)** — 여기서 천천히, 자신 있게
