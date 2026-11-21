# Streamlit 포털(app.py) 서버 배포 — 음성 orb·카테고리·맞춤상담 그대로

FastAPI 통합 앱(app_personal.py) 대신, **Streamlit 포털 app.py 자체**를 서버에
올려 지금 Mac 에서 보는 디자인(음성 orb · 복지 서비스 바로가기 · 맞춤 상담)을
그대로 보여준다.

> 포트는 **8003** 사용(보안 그룹 8001-8003 에 이미 열려 있음).
> app_personal(8001) 과 동시에 띄울 수 있다.

---

## ⚠ 먼저 알아둘 것
- **무거운 설치**: torch · sentence-transformers(bge-m3) · chromadb · reranker 를
  받고, 첫 실행에 **임베딩 모델 다운로드(~2GB)+인덱스 빌드**로 10~15분 걸린다.
  GPU 서버(g4dn)라 가능하다.
- **음성(voice orb)은 http 서버에서는 동작하지 않는다**(브라우저 마이크는 HTTPS·
  localhost 에서만 허용). **화면·카테고리·문자 상담은 정상 동작**한다.
- **LLM 은 Ollama** 로: `LLM_BACKEND=ollama` 환경변수 필요.

---

## 1. (Mac) 원본 복지문서를 git 에 올리기 — 서버가 인덱스를 빌드하도록
`data/welfare_docs/` 는 git 에 없다. 서버에서 ChromaDB 인덱스를 만들려면 필요.
**Mac 에서 한 번만:**
```bash
cd ~/ondevice_llm
git add -f data/welfare_docs
git commit -m "서버 배포용 복지문서 추가"
git push origin claude/elderly-welfare-voice-ai-8v6bii
```
> 용량이 크면(수십 MB) scp 로 올려도 된다:
> `scp -i ~/Downloads/novem18-2.pem -r data/welfare_docs ubuntu@<IP>:~/team/novem/ondevice_llm/data/`

## 2. (서버) 코드·문서 받기
```bash
cd ~/team/novem/ondevice_llm
git pull origin claude/elderly-welfare-voice-ai-8v6bii
ls data/welfare_docs | head        # 문서가 보이면 OK
```

## 3. (서버) 패키지 설치 (몇 분)
```bash
pip install streamlit chromadb sentence-transformers pdfplumber pandas openpyxl requests --break-system-packages
# torch 가 없으면(대개 CUDA AMI 엔 있음): pip install torch --break-system-packages
python3 -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
```

## 4. (서버) Ollama 모델 확인
```bash
ollama list      # exaone3.5:2.4b 있어야 함 (없으면 ollama pull exaone3.5:2.4b)
```

## 5. (서버) 실행 — 포트 8003, Ollama 백엔드
```bash
cd ~/team/novem/ondevice_llm
LLM_BACKEND=ollama LLM_MODEL=exaone3.5:2.4b \
  nohup streamlit run app.py \
    --server.port 8003 --server.address 0.0.0.0 --server.headless true \
    --server.enableCORS false --server.enableXsrfProtection false \
    > ~/streamlit.log 2>&1 &
```
첫 실행은 모델 다운로드+인덱싱으로 시간이 걸린다. 진행 상황:
```bash
tail -f ~/streamlit.log
# "You can now view your Streamlit app" + 인덱싱 로그가 보이면 준비 완료
```

## 6. 브라우저
```
http://16.208.136.61:8003
```
→ 로그인 → 내 정보 → 포털(음성 orb · 복지 서비스 바로가기 · 맞춤 상담)

- 음성 orb 는 보이지만 http 라 녹음은 안 된다(문자 입력으로 상담).
- 느리면: 첫 임베딩/인덱싱 중이거나 Ollama 가 셋이 동시 사용 중 → `nvidia-smi`.

## 끄기 / 재시작
```bash
pkill -f "streamlit run app.py"
# 다시 5번 실행
```

## systemd 로 상시 실행 (발표 필수)
SSH 를 닫거나 앱이 죽어도, 서버를 재부팅해도 앱이 **자동으로 다시 켜지게** 한다.
유닛 파일: `deploy/welfarehub-8003.service` (계정 ubuntu · 폴더 `~/team/novem/ondevice_llm` · 포트 8003).

```bash
cd ~/team/novem/ondevice_llm
git pull origin main
# 0) streamlit 이 /usr/bin/python3 에 설치돼 있는지 확인 (버전이 나오면 OK)
/usr/bin/python3 -m streamlit version
# 1) nohup 으로 띄운 기존 앱 끄기 (포트 8003 충돌 방지)
pkill -f "streamlit run app.py"
# 2) 설치 + 자동 시작 등록
sudo cp deploy/welfarehub-8003.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now welfarehub-8003
# 3) 확인 — active (running) 이면 성공
systemctl status welfarehub-8003 --no-pager
```

| 할 일 | 명령 |
|---|---|
| 로그 보기 | `journalctl -u welfarehub-8003 -f` |
| 코드 업데이트 후 재시작 | `git pull origin main && sudo systemctl restart welfarehub-8003` |
| 끄기 / 켜기 | `sudo systemctl stop welfarehub-8003` / `sudo systemctl start welfarehub-8003` |
| 자동 시작 해제 | `sudo systemctl disable --now welfarehub-8003` |

> ⚠️ systemd 로 돌리는 동안에는 `nohup streamlit run ...` 을 **같이 띄우지 않는다**(포트 충돌).
> 업데이트는 항상 `sudo systemctl restart welfarehub-8003` 로.

**(선택) Gemini 키** — 저장소가 아니라 서버에만, 관리자만 읽게 둔다:
```bash
echo 'GEMINI_API_KEY=새로_발급한_키' | sudo tee /etc/welfarehub.env >/dev/null
sudo chmod 600 /etc/welfarehub.env
sudo systemctl restart welfarehub-8003
```
키를 빼려면 `sudo rm /etc/welfarehub.env && sudo systemctl restart welfarehub-8003`
(키가 없으면 사진은 서버 안 qwen2.5vl 이 읽는다).

**발표 당일 아침 체크:** `systemctl status welfarehub-8003` · `ollama list` · 휴대폰으로 접속해 질문 1개.

---

## 자주 나오는 문제
| 증상 | 해결 |
|---|---|
| 화면이 안 열림 | 포트 8003 보안그룹 확인 · `tail streamlit.log` |
| 인덱싱이 안 끝남 | 첫 실행 모델 다운로드 중 — 로그 확인, 기다리기 |
| 답이 영어/이상 | `LLM_BACKEND=ollama` 빠졌는지 확인(안 주면 openai 시도) |
| 음성이 안 됨 | http 라 정상 — 문자 입력 사용(서비스화 땐 HTTPS) |
| torch CUDA False | CPU로도 임베딩은 되지만 느림 — AMI/드라이버 확인 |
