"""
사회복지사 전용 관리자 모니터링 앱 (별도 interface).

어르신용 상담 앱(app.py)과 분리된 '관리자' 화면이다. 어르신 대화에서 감지된
이상신호(통증·우울·위기 키워드, 대화 분석)를 DB(src.db.alerts)에서 읽어
어르신 한 분 한 분을 개별로 모니터링한다.

  어르신 앱(app.py) ──(이상신호 감지)──▶ DB ──(읽기)──▶ 관리자 앱(app_admin.py)

실행(별도 포트):
  streamlit run app_admin.py --server.port 8502
  (선택) 비밀번호:  ADMIN_PW=원하는비밀번호 streamlit run app_admin.py --server.port 8502
  (서버 DB 공유 시)  USE_MYSQL=1 DB_HOST=... DB_USER=... DB_PASSWORD=... streamlit run ...
"""
from __future__ import annotations
import os
from collections import defaultdict

import streamlit as st

from src import db

st.set_page_config(page_title="관리자 모니터 · 대전노인복지HUB",
                   page_icon="🚨", layout="wide")

NAVY, ACCENT, RED = "#0f2f6f", "#2f6bff", "#d93025"
st.markdown(f"""
<style>
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
  html, body, [class*="css"] {{font-family:'Pretendard','Noto Sans KR',sans-serif}}
  .ahead {{display:flex;align-items:center;gap:12px;font-size:1.9rem;font-weight:800;
    color:{NAVY};letter-spacing:-.03em;margin-bottom:2px}}
  .ucard {{background:#fff;border:1px solid #e6ebf4;border-left:5px solid {ACCENT};
    border-radius:14px;padding:14px 16px;margin-bottom:10px;
    box-shadow:0 8px 24px -16px rgba(16,35,61,.3)}}
  .ucard.crisis {{border-left-color:{RED};background:#fdecec}}
  .ucard .u {{font-size:1.15rem;font-weight:800;color:{NAVY}}}
  .ucard.crisis .u {{color:{RED}}}
  .ucard .meta {{color:#5c6b86;font-size:.9rem;margin:2px 0 6px}}
  .ucard .msg {{font-size:1.02rem;color:#15233d}}
  .badge {{display:inline-block;font-size:.76rem;font-weight:800;border-radius:999px;
    padding:2px 10px;margin-left:6px}}
  .badge.c {{background:#fde7ea;color:{RED}}}
  .badge.w {{background:#fff4e6;color:#b45309}}
  .badge.ok {{background:#e6f4ea;color:#1f7a43}}
  .ucard.ok {{border-left-color:#1f7a43}}
</style>
""", unsafe_allow_html=True)


# ── (선택) 관리자 비밀번호 ────────────────────────────────────────────
_PW = os.environ.get("ADMIN_PW")
if _PW:
    if not st.session_state.get("admin_ok"):
        st.markdown('<div class="ahead">🔒 관리자 로그인</div>', unsafe_allow_html=True)
        pw = st.text_input("관리자 비밀번호", type="password")
        if st.button("로그인", type="primary"):
            if pw == _PW:
                st.session_state["admin_ok"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
        st.stop()


# ── 헤더 + 새로고침 ───────────────────────────────────────────────────
# 자동 새로고침은 streamlit_autorefresh(설치 시)를 우선 사용한다.
# 이 방식은 '브라우저 전체 reload'가 아니라 '스크립트만 재실행'이라
# JSON 데이터만 다시 읽고 화면 깜빡임(flicker)이 거의 없다.
try:
    from streamlit_autorefresh import st_autorefresh   # pip install streamlit-autorefresh
    _HAS_AUTOREFRESH = True
except Exception:                                       # 미설치 시 JS fallback
    _HAS_AUTOREFRESH = False

top = st.columns([4, 1, 1])
top[0].markdown('<div class="ahead">🚨 사회복지사 모니터 — 어르신 이상신호</div>'
                '<p style="color:#5c6b86;margin-top:-4px">어르신 대화에서 감지된 '
                '통증·우울·위기 신호를 실시간으로 모니터링합니다.</p>',
                unsafe_allow_html=True)
# 1) 수동 새로고침 — 누르면 JSON에서 최신 데이터를 다시 읽고 UI 갱신
if top[1].button("🔄 새로고침 (Refresh)", use_container_width=True):
    st.rerun()
with top[2]:
    # 2) 자동 새로고침 토글 — 5초마다 데이터만 다시 읽음
    auto = st.toggle("자동 새로고침 (Auto-refresh)", value=False,
                     help="5초마다 최신 이상신호를 자동으로 불러옵니다.")
    if st.button("🗑 알림 비우기", use_container_width=True):
        db.clear_alerts()
        st.rerun()

# 3) 깜빡임 최소화: 가능하면 스크립트만 재실행(st_autorefresh),
#    라이브러리가 없으면 전체 reload로 대체
if auto:
    if _HAS_AUTOREFRESH:
        st_autorefresh(interval=5000, key="admin_autorefresh")   # 5초
    else:
        import streamlit.components.v1 as components
        components.html("<script>setTimeout(function(){window.parent.location.reload()},"
                        "5000)</script>", height=0)

alerts = db.list_alerts(1000)          # 최신 → 오래된
all_users = db.list_users()            # 가입/로그인한 모든 어르신

# 어르신별 알림 묶기
by_user = defaultdict(list)
for a in alerts:
    by_user[a.get("name") or "(이름없음)"].append(a)

# 모니터 대상 = 로그인한 모든 어르신 ∪ 알림이 있는 이름
monitored = sorted(set(all_users) | set(by_user.keys()))

# ── 요약 지표 ─────────────────────────────────────────────────────────
n_crisis = sum(1 for a in alerts if a.get("level") == "위기")
n_risk_users = sum(1 for u in monitored if by_user.get(u))
m = st.columns(4)
m[0].metric("모니터 대상", f"{len(monitored)}명")
m[1].metric("🆘 위기 신호", f"{n_crisis}건")
m[2].metric("⚠️ 주의 신호", f"{len(alerts) - n_crisis}건")
m[3].metric("신호 발생 어르신", f"{n_risk_users}명")
st.caption(f"저장소: {db.backend_name()} · 총 신호 {len(alerts)}건")

if not monitored:
    st.info("아직 로그인한 어르신이 없습니다. 어르신 앱에서 가입·대화가 쌓이면 "
            "여기에 표시됩니다.")
    st.stop()

# ── 필터 (사이드바) ───────────────────────────────────────────────────
with st.sidebar:
    st.subheader("필터")
    sel_users = st.multiselect("어르신(이름)", monitored, default=monitored)
    view_users = sel_users or monitored            # 비어 있으면 전체 표시
    sel_level = st.radio("보기", ["전체", "신호 있는 분만", "위기만"], index=0)


def _ulevel(items):
    if any(x.get("level") == "위기" for x in items):
        return "위기"
    if items:
        return "주의"
    return "정상"


# ── 어르신별 모니터 (로그인한 모든 어르신) ────────────────────────────
st.markdown("### 👵 어르신별 모니터")

def _rank(u):
    items = by_user.get(u, [])
    lv = {"위기": 2, "주의": 1, "정상": 0}[_ulevel(items)]
    latest = items[0].get("time", "") if items else ""
    return (lv, len(items), latest)


shown = 0
for name in sorted(view_users, key=_rank, reverse=True):
    items = by_user.get(name, [])
    lv = _ulevel(items)
    if sel_level == "위기만" and lv != "위기":
        continue
    if sel_level == "신호 있는 분만" and not items:
        continue
    shown += 1
    if lv == "위기":
        cls, badge = "crisis", '<span class="badge c">위기</span>'
    elif lv == "주의":
        cls, badge = "", '<span class="badge w">주의</span>'
    else:
        cls, badge = "ok", '<span class="badge ok">정상</span>'
    latest = items[0] if items else None
    body = (f'<div class="meta">최근 {latest.get("time","")} · {latest.get("reason","")}</div>'
            f'<div class="msg">“{latest.get("message","")}”</div>') if latest else \
           '<div class="meta">감지된 이상신호 없음 (정상 모니터 중)</div>'
    st.markdown(
        f'<div class="ucard {cls}"><div class="u">{name} 님{badge}'
        f'<span style="font-weight:600;color:#5c6b86;font-size:.9rem"> · 신호 '
        f'{len(items)}건</span></div>{body}</div>', unsafe_allow_html=True)
    if items:
        with st.expander(f"{name} 님 전체 신호 {len(items)}건 보기"):
            st.dataframe(
                [{"시각": x.get("time"), "위험도": x.get("level"),
                  "메시지": x.get("message"), "근거": x.get("reason")} for x in items],
                use_container_width=True, hide_index=True)
if shown == 0:
    st.caption("조건에 해당하는 어르신이 없습니다.")

# ── 전체 타임라인 ─────────────────────────────────────────────────────
st.markdown("### 🕒 전체 이상신호 타임라인")
tl = [a for a in alerts if a.get("name") in view_users]
if sel_level == "위기만":
    tl = [a for a in tl if a.get("level") == "위기"]
if tl:
    st.dataframe(
        [{"시각": a.get("time"), "어르신": a.get("name"), "위험도": a.get("level"),
          "메시지": a.get("message"), "근거": a.get("reason")} for a in tl],
        use_container_width=True, hide_index=True)
else:
    st.caption("표시할 이상신호가 없습니다.")
