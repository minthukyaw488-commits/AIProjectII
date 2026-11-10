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
top = st.columns([4, 1, 1])
top[0].markdown('<div class="ahead">🚨 사회복지사 모니터 — 어르신 이상신호</div>'
                '<p style="color:#5c6b86;margin-top:-4px">어르신 대화에서 감지된 '
                '통증·우울·위기 신호를 실시간으로 모니터링합니다.</p>',
                unsafe_allow_html=True)
if top[1].button("🔄 새로고침", use_container_width=True):
    st.rerun()
auto = top[2].toggle("자동(10초)", value=False)
if auto:
    import streamlit.components.v1 as components
    components.html("<script>setTimeout(function(){window.parent.location.reload()},"
                    "10000)</script>", height=0)

alerts = db.list_alerts(1000)          # 최신 → 오래된

# ── 요약 지표 ─────────────────────────────────────────────────────────
n_crisis = sum(1 for a in alerts if a.get("level") == "위기")
users = sorted({a.get("name") for a in alerts if a.get("name")})
m = st.columns(4)
m[0].metric("총 이상신호", f"{len(alerts)}건")
m[1].metric("🆘 위기", f"{n_crisis}건")
m[2].metric("⚠️ 주의", f"{len(alerts) - n_crisis}건")
m[3].metric("모니터 대상", f"{len(users)}명")
st.caption(f"저장소: {db.backend_name()}")

if not alerts:
    st.info("아직 감지된 이상신호가 없습니다. 어르신 앱에서 대화가 쌓이면 여기에 표시됩니다.")
    st.stop()

# ── 필터 (사이드바) ───────────────────────────────────────────────────
with st.sidebar:
    st.subheader("필터")
    sel_users = st.multiselect("어르신(이름)", users, default=users)
    sel_level = st.radio("위험도", ["전체", "위기만", "주의만"], index=0)

fil = [a for a in alerts if a.get("name") in sel_users]
if sel_level == "위기만":
    fil = [a for a in fil if a.get("level") == "위기"]
elif sel_level == "주의만":
    fil = [a for a in fil if a.get("level") == "주의"]

# ── 어르신별 모니터 (개별) ────────────────────────────────────────────
st.markdown("### 👵 어르신별 모니터")
by_user = defaultdict(list)
for a in fil:
    by_user[a.get("name") or "(이름없음)"].append(a)

# 정렬: 위기 보유 → 신호 많은 → 최근 순
def _rank(items):
    has_c = any(x.get("level") == "위기" for x in items)
    return (has_c, len(items), items[0].get("time", ""))


for name in sorted(by_user, key=lambda n: _rank(by_user[n]), reverse=True):
    items = by_user[name]
    crisis = any(x.get("level") == "위기" for x in items)
    latest = items[0]
    badge = ('<span class="badge c">위기</span>' if crisis
             else '<span class="badge w">주의</span>')
    st.markdown(
        f'<div class="ucard {"crisis" if crisis else ""}">'
        f'<div class="u">{name} 님{badge}'
        f'<span style="font-weight:600;color:#5c6b86;font-size:.9rem"> · 신호 '
        f'{len(items)}건</span></div>'
        f'<div class="meta">최근 {latest.get("time","")} · {latest.get("reason","")}</div>'
        f'<div class="msg">“{latest.get("message","")}”</div></div>',
        unsafe_allow_html=True)
    with st.expander(f"{name} 님 전체 신호 {len(items)}건 보기"):
        st.dataframe(
            [{"시각": x.get("time"), "위험도": x.get("level"),
              "메시지": x.get("message"), "근거": x.get("reason")} for x in items],
            use_container_width=True, hide_index=True)

# ── 전체 타임라인 ─────────────────────────────────────────────────────
st.markdown("### 🕒 전체 타임라인")
st.dataframe(
    [{"시각": a.get("time"), "어르신": a.get("name"), "위험도": a.get("level"),
      "메시지": a.get("message"), "근거": a.get("reason")} for a in fil],
    use_container_width=True, hide_index=True)
