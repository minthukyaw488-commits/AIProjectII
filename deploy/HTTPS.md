# HTTPS 적용 — DuckDNS(무료 도메인) + Caddy(자동 인증서)

왜: `http://IP:8003` 은 ① 폰 브라우저가 "안전하지 않음" 표시 ② **마이크(음성 상담) 차단**
③ 안드로이드에서 앱처럼 설치(PWA) 불가. HTTPS 를 붙이면 세 가지가 모두 풀린다.
코드 수정은 없다 — 앞단에 Caddy 를 두고 8003 으로 넘겨줄 뿐이다.

```
휴대폰 ──https://djwelfare.duckdns.org──▶ Caddy(:443, 인증서) ──▶ Streamlit(localhost:8003)
```

## 0. 준비 (팀장 / AWS 콘솔 권한자)
- EC2 → 보안 그룹 → 인바운드 규칙에 **TCP 80, TCP 443 (0.0.0.0/0)** 추가
  (80 은 인증서 발급 확인용, 443 이 실제 HTTPS)
- 가능하면 **Elastic IP** 를 붙여 IP 가 바뀌지 않게 한다(중지→시작 시 IP 변경 방지)

## 1. DuckDNS 도메인 만들기 (2분)
1. https://www.duckdns.org 접속 → GitHub/Google 로 로그인
2. sub domain 에 이름 입력(예: `djwelfare`) → **add domain**
3. current ip 칸에 서버 IP(예: `16.208.136.61`) 입력 → **update ip**
4. 확인(서버에서): `getent hosts djwelfare.duckdns.org` → 서버 IP 가 나오면 OK

## 2. 서버: 80/443 을 다른 프로그램이 쓰는지 확인
```bash
sudo ss -tlnp | grep -E ':(80|443) '
```
아무것도 안 나오면 OK. nginx 등 다른 팀원 서비스가 쓰고 있으면 **먼저 팀과 상의**.

## 3. 서버: Caddy 설치 (공식 저장소)
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
caddy version
```

## 4. 서버: 설정 적용
```bash
cd ~/team/novem/ondevice_llm
git pull origin main
sed -i 's/djwelfare.duckdns.org/본인도메인.duckdns.org/' deploy/Caddyfile   # 이름이 다를 때만
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager
```
로그에 `certificate obtained successfully` 가 보이면 인증서 발급 완료.

## 5. 확인
- 폰에서 `https://djwelfare.duckdns.org` → 자물쇠 🔒 표시 + 로그인 화면
- AI상담에서 🎤 음성 기능이 마이크 권한을 묻는지
- 안드로이드 Chrome: 메뉴 → **앱 설치**, iPhone Safari: 공유 → **홈 화면에 추가**

기존 `http://IP:8003` 도 그대로 열려 있으므로(비상용) 발표 때 둘 다 쓸 수 있다.

## 문제 해결
| 증상 | 확인 |
|---|---|
| 인증서 발급 실패 | 보안 그룹 80/443 열림? DuckDNS IP 가 현재 서버 IP? `sudo journalctl -u caddy -n 50` |
| 502 Bad Gateway | 앱이 꺼짐 → `systemctl status welfarehub-8003` |
| 화면이 계속 연결 중 | 브라우저 새로고침. 계속되면 Caddy 로그 확인 |
| IP 가 바뀜 | DuckDNS 사이트에서 update ip (Elastic IP 권장) |
