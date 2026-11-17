# HTTPS 적용 — DuckDNS(무료 도메인) + Caddy(자동 인증서)

왜: `http://IP:8003` 은 ① 폰 브라우저가 "안전하지 않음" 표시 ② **마이크(음성 상담) 차단**
③ 안드로이드에서 앱처럼 설치(PWA) 불가. HTTPS 를 붙이면 세 가지가 모두 풀린다.
코드 수정은 없다 — 앞단에 Caddy 를 두고 8003 으로 넘겨줄 뿐이다.

```
휴대폰 ──https://aiproject2.duckdns.org──▶ Caddy(:443, 인증서) ──▶ Streamlit(localhost:8003)
```

## 0. 준비 (팀장 / AWS 콘솔 권한자)
- EC2 → 보안 그룹 → 인바운드 규칙에 **TCP 80, TCP 443 (0.0.0.0/0)** 추가
  (80 은 인증서 발급 확인용, 443 이 실제 HTTPS)
- 가능하면 **Elastic IP** 를 붙여 IP 가 바뀌지 않게 한다(중지→시작 시 IP 변경 방지)

## 1. DuckDNS 도메인 만들기 (2분)
1. https://www.duckdns.org 접속 → GitHub/Google 로 로그인
2. sub domain 에 이름 입력(예: `aiproject2`) → **add domain**
3. current ip 칸에 서버 IP(예: `16.208.136.61`) 입력 → **update ip**
4. 확인(서버에서): `getent hosts aiproject2.duckdns.org` → 서버 IP 가 나오면 OK

## 2. 서버: 80/443 을 다른 프로그램이 쓰는지 확인 (apache2 가 보이면 맨 아래 ★ 절로)
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
sed -i 's/aiproject2.duckdns.org/본인도메인.duckdns.org/' deploy/Caddyfile   # 이름이 다를 때만
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager
```
로그에 `certificate obtained successfully` 가 보이면 인증서 발급 완료.

## 5. 확인
- 폰에서 `https://aiproject2.duckdns.org` → 자물쇠 🔒 표시 + 로그인 화면
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

---

## ★ Apache 가 이미 80 을 쓰는 경우 (우리 서버 = 이 방법)
`sudo ss -tlnp | grep -E ':(80|443) '` 에 **apache2** 가 보이면 Caddy 대신 **기존 Apache 를 그대로
HTTPS 프록시로 쓴다.** 기존 사이트(000-default, `/var/www/html` 팀원 페이지)는 건드리지 않는다 —
도메인(aiproject2.duckdns.org)으로 들어온 요청만 8003 으로 넘긴다.

```bash
cd ~/team/novem/ondevice_llm
git pull origin main
sudo a2enmod proxy proxy_http proxy_wstunnel rewrite headers ssl
sudo cp deploy/apache-aiproject2.conf /etc/apache2/sites-available/aiproject2.conf
sudo a2ensite aiproject2
sudo apache2ctl configtest
sudo systemctl reload apache2
curl -sI http://aiproject2.duckdns.org | head -3
```
`Syntax OK`, 그리고 마지막 줄 결과가 `HTTP/1.1 200` 이면 http 프록시 성공.

인증서(Let's Encrypt) 발급 + https 자동 설정:
```bash
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/local/bin/certbot
sudo certbot --apache -d aiproject2.duckdns.org --redirect --agree-tos --register-unsafely-without-email -n
curl -sI https://aiproject2.duckdns.org | head -3
```
> ⚠️ `apt install certbot` 은 쓰지 않는다: 앱용으로 pip 설치한 최신 cryptography/pyOpenSSL
> (`/usr/local/lib/python3.12`) 과 충돌해 `module 'OpenSSL.crypto' has no attribute 'X509Req'`
> 오류가 난다. snap 판은 격리돼 있어 앱 패키지와 충돌하지 않는다(실제 서버에서 확인).
`Congratulations` / `Successfully deployed certificate` 가 보이면 완료. 인증서는 certbot 이 자동 갱신한다.

되돌리기: `sudo a2dissite aiproject2 aiproject2-le-ssl; sudo systemctl reload apache2`
(기존 Apache 사이트는 영향 없음)
