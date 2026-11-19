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

import streamlit as st

from src import db

st.set_page_config(page_title="관리자 모니터 · 대전노인복지HUB",
                   page_icon="🚨", layout="wide")

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


from src.admin_monitor import render  # noqa: E402

render()
