"""
대전노인복지HUB (demo) - Streamlit.

A public-service style welfare portal for elderly residents of Daejeon:
official-style header + nav, a prominent voice AI welfare assistant, welfare
search, large service-category cards, popular services, announcements,
accessibility controls, and an official footer. A hidden 관리자 view holds the
abnormal-signal monitor.

Run with the SAME interpreter that has the models installed:
    python -m streamlit run app.py
"""
from __future__ import annotations   # Python 3.8/3.9 에서도 'dict | None' 표기 허용

import streamlit as st

from src import config
from src.tts import TextToSpeech
from src.worker import AssistantClient

st.set_page_config(page_title="대전노인복지HUB", layout="wide",
                   initial_sidebar_state="expanded")

# --- service categories & content ----------------------------------------
# (name, desc, color, icon-key, question) - no emoji, no red.
CATEGORIES = [
    ("기초연금", "매월 연금을 지원합니다", "#2563eb", "coin", "기초연금은 어떻게 신청하나요?"),
    ("노인맞춤돌봄", "생활지원사 방문·안부", "#4f46e5", "care", "노인맞춤돌봄서비스를 받고 싶어요"),
    ("방문건강관리", "간호사 가정 방문", "#0d9488", "cross", "집에서 혈압 건강관리 받고 싶어요"),
    ("치매안심", "무료 검진·상담", "#0284c7", "bulb", "치매 검진 무료로 받고 싶어요"),
    ("응급안전안심", "화재·응급 감지", "#0f766e", "shield", "혼자 사는데 응급상황이 걱정돼요"),
    ("노인일자리", "일자리·사회활동", "#7c3aed", "case", "노인 일자리를 구하고 싶어요"),
]
_S = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
      ' stroke-linecap="round" stroke-linejoin="round">')
ICONS = {
    "coin": f'{_S}<circle cx="12" cy="12" r="9"/><path d="M9 9l3 5 3-5"/><path d="M8 12h8"/></svg>',
    "care": f'{_S}<path d="M12 20s-6.5-4.3-6.5-9A3.5 3.5 0 0112 8a3.5 3.5 0 016.5 3c0 4.7-6.5 9-6.5 9z"/></svg>',
    "cross": f'{_S}<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8v8M8 12h8"/></svg>',
    "bulb": f'{_S}<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 00-3.5 10.9c.3.3.5.7.5 1.1v.5h6v-.5c0-.4.2-.8.5-1.1A6 6 0 0012 3z"/></svg>',
    "shield": f'{_S}<path d="M12 3l7 3v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6z"/></svg>',
    "case": f'{_S}<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M3 12h18"/></svg>',
}
POPULAR = ["기초연금", "치매 검진", "노인일자리", "에너지 바우처", "경로우대", "방문간호"]
NOTICES = [
    ("2026-08-20", "2026년 기초연금 선정기준액 인상 안내"),
    ("2026-08-14", "겨울철 에너지바우처 신청 접수 시작"),
    ("2026-08-05", "치매안심센터 무료 조기검진 프로그램 운영"),
    ("2026-07-28", "노인맞춤돌봄서비스 신규 대상자 모집"),
]


@st.cache_resource
def get_client():
    return AssistantClient()


class _LazyClient:
    """포털·채팅에서 '처음 필요할 때만' 무거운 어시스턴트(모델+인덱싱)를 만든다.
    덕분에 로그인·내 정보·포털 화면은 인덱싱을 기다리지 않고 바로 뜨고, 첫 질문에서만
    준비 시간이 걸린다(모델·인덱스는 한 번 만들면 캐시돼 이후엔 빠르다)."""
    def __getattr__(self, name):
        with st.spinner("상담을 준비하는 중입니다… (첫 질문은 조금 걸릴 수 있어요)"):
            real = get_client()          # @st.cache_resource: 한 번만 생성
        return getattr(real, name)


@st.cache_resource
def get_tts():
    return TextToSpeech()


@st.cache_data
def hero_bg_css_value() -> str:
    """Return a CSS value for the hero background image.

    If an illustration is saved at ``assets/hero_bg.(png|jpg|jpeg|webp)`` it is
    embedded as a data URI (works offline, no external host). Otherwise an empty
    string is returned and the CSS falls back to the navy gradient only.
    """
    import base64
    from pathlib import Path
    root = Path(__file__).resolve().parent / "assets"
    for name, mime in (("hero_bg.png", "image/png"), ("hero_bg.jpg", "image/jpeg"),
                       ("hero_bg.jpeg", "image/jpeg"), ("hero_bg.webp", "image/webp")):
        f = root / name
        if f.exists():
            b64 = base64.b64encode(f.read_bytes()).decode("ascii")
            return f"url('data:{mime};base64,{b64}')"
    return ""


# --------------------------------------------------------------------------
# Styling (navy public-service palette, large type, high contrast)
# --------------------------------------------------------------------------
def inject_css():
    scale = st.session_state.get("font_scale", 1.0)
    hc = st.session_state.get("high_contrast", False)
    base = 17 * scale
    navy = "#0f2f6f"                       # brand
    navy2 = "#0a2350"                      # deep
    accent = "#2f6bff"                     # vivid CTA blue
    ink = "#000000" if hc else "#15233d"
    muted = "#334155" if hc else "#5c6b86"
    bg = "#ffffff" if hc else "#eef2f9"    # cool light ground
    surface = "#ffffff"
    surface2 = "#f5f8fd"
    line = "#000000" if hc else "#e6ebf4"
    card_bd = "#000000" if hc else "#e8edf7"
    hero_img = hero_bg_css_value()          # data-URI illustration, or "" (gradient only)
    hero_layer = f"{hero_img}, " if hero_img else ""
    st.markdown(f"""
    <style>
      @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

      #MainMenu, header[data-testid="stHeader"], footer {{visibility:hidden; height:0}}
      .block-container{{padding:0 !important; max-width:100% !important}}
      .stApp{{background:{bg}}}
      html, body, [class*="css"], .stApp{{font-size:{base}px;
        font-family:'Pretendard','Pretendard Variable',-apple-system,'Noto Sans KR',sans-serif;
        color:{ink}; -webkit-font-smoothing:antialiased}}
      .gov-wrap{{max-width:1140px; margin:0 auto; padding:0 24px}}

      /* top utility bar */
      .util{{background:{navy2}; color:#c7d4ee; font-size:.82rem}}
      .util .gov-wrap{{display:flex; justify-content:flex-end; gap:22px; padding:9px 24px}}
      .util span{{opacity:.85; cursor:pointer}} .util span:hover{{opacity:1;color:#fff}}

      /* header + nav */
      .gnav{{background:rgba(255,255,255,.9); backdrop-filter:saturate(1.4) blur(8px);
        border-bottom:1px solid {line}; position:sticky; top:0; z-index:50}}
      .gnav .row{{display:flex; align-items:center; justify-content:space-between; padding:16px 24px}}
      .brand{{display:flex; align-items:center; gap:13px; font-weight:800; color:{navy};
        font-size:1.45rem; letter-spacing:-.03em}}
      .brand .seal{{width:42px;height:42px;border-radius:13px;
        background:linear-gradient(140deg,{accent},{navy}); color:#fff;
        display:flex;align-items:center;justify-content:center;font-size:1.25rem;
        box-shadow:0 6px 16px -4px {accent}66}}
      .menu{{display:flex; gap:8px; font-weight:600; font-size:1.02rem}}
      .menu span{{padding:9px 15px; border-radius:11px; color:{muted}; cursor:pointer;
        transition:all .15s}}
      .menu span:hover{{background:{surface2}; color:{navy}}}

      /* hero - full-bleed short banner with illustration background */
      .hero .gov-wrap{{padding:0; max-width:100%}}
      .hero-inner{{border-radius:0; padding:26px 6vw; color:#fff; position:relative;
        overflow:hidden; min-height:120px; display:flex; flex-direction:column;
        justify-content:center;
        background:
          linear-gradient(90deg, {navy2}f0 0%, {navy}cc 46%, {navy}66 78%, {navy}33 100%),
          {hero_layer}
          linear-gradient(135deg, {navy} 0%, {navy2} 100%);
        background-size:cover, cover, cover;
        background-position:center, center right, center;
        background-repeat:no-repeat}}
      .hero .eyebrow{{display:inline-block; font-size:.78rem; font-weight:700;
        letter-spacing:.14em; text-transform:uppercase; color:#e2ecff;
        background:#ffffff2b; padding:5px 13px; border-radius:999px; margin-bottom:10px}}
      .hero h1{{font-size:2rem; font-weight:800; margin:0 0 6px; letter-spacing:-.03em;
        line-height:1.18; text-shadow:0 2px 14px {navy2}cc}}
      .hero p{{font-size:1.04rem; color:#eaf1ff; margin:0; max-width:60ch; line-height:1.5;
        position:relative; z-index:1; text-shadow:0 1px 10px {navy2}b3}}
      .hero .eyebrow, .hero h1{{position:relative; z-index:1}}
      /* concentric SVG art is only shown when there is no photo background */
      .hero-art{{position:absolute; right:20px; top:50%; transform:translateY(-50%);
        width:200px; height:200px; opacity:.9; pointer-events:none;
        display:{"none" if hero_img else "block"}}}
      @media(max-width:820px){{.hero-art{{display:none}} .hero-inner{{padding:22px 24px}}}}

      /* section */
      .sec{{padding:44px 0}}
      .sec.alt{{background:{surface2}}}
      .sec h2{{font-size:1.72rem; font-weight:800; color:{ink}; margin:0 0 6px;
        letter-spacing:-.03em}}
      .sec .sub{{color:{muted}; margin:0 0 26px; font-size:1.05rem}}

      /* header row (brand | search | nav) */
      .brand-svg{{width:24px;height:24px;color:#fff}}
      .menu{{justify-content:flex-end}}
      .util .gov-wrap{{justify-content:flex-end}}
      /* header search: strip Streamlit form chrome so it aligns with brand/nav */
      [data-testid="stForm"]{{border:0 !important; padding:0 !important; box-shadow:none !important}}
      [data-testid="stForm"] [data-testid="stTextInput"] input{{height:44px}}
      [data-testid="stForm"] button{{height:44px}}
      /* remove the "Press Enter to submit form" helper text under inputs */
      [data-testid="InputInstructions"]{{display:none !important}}
      /* no red anywhere: text inputs + 보내기 button use the navy palette */
      [data-testid="stTextInput"] input:focus{{
        border-color:{navy} !important; box-shadow:0 0 0 2px {accent}55 !important}}
      [data-testid="stForm"] button[kind="secondaryFormSubmit"],
      [data-testid="stForm"] button[kind="primaryFormSubmit"]{{
        background:{navy} !important; border-color:{navy} !important; color:#fff !important}}
      [data-testid="stForm"] button:hover{{background:{navy2} !important;
        border-color:{navy2} !important; color:#fff !important}}

      /* colored category cards */
      .cat-grid{{display:grid; grid-template-columns:repeat(3,1fr); gap:20px}}
      .cat-card{{display:flex; flex-direction:column; gap:12px; min-height:172px;
        padding:26px 24px; border-radius:22px; text-decoration:none; color:#fff;
        background:var(--c); background-image:linear-gradient(150deg,#ffffff22,#0000001f);
        box-shadow:0 20px 38px -18px var(--c); position:relative; overflow:hidden;
        transition:transform .22s cubic-bezier(.2,.7,.3,1), box-shadow .22s;
        animation:fadeUp .55s both}}
      .cat-card:hover{{transform:translateY(-6px); box-shadow:0 30px 54px -18px var(--c)}}
      a.cat-card, a.cat-card *, a.chip{{text-decoration:none !important}}
      a.cat-card, a.cat-card *{{color:#fff !important}}
      .cat-card:nth-child(2){{animation-delay:.05s}} .cat-card:nth-child(3){{animation-delay:.1s}}
      .cat-card:nth-child(4){{animation-delay:.15s}} .cat-card:nth-child(5){{animation-delay:.2s}}
      .cat-card:nth-child(6){{animation-delay:.25s}}
      .cat-ic{{width:54px;height:54px;border-radius:16px;background:#ffffff2b;
        display:flex;align-items:center;justify-content:center}}
      .cat-ic svg{{width:27px;height:27px;color:#fff}}
      .cat-name{{font-size:1.36rem;font-weight:800;letter-spacing:-.02em;color:#ffffff}}
      .cat-desc{{font-size:1.02rem;color:#ffffff;font-weight:500;opacity:.92}}
      .cat-card .arw{{position:absolute;right:24px;bottom:22px;font-size:1.4rem;opacity:.55;
        transition:transform .2s}}
      .cat-card:hover .arw{{transform:translateX(5px);opacity:.95}}
      @media(max-width:920px){{.cat-grid{{grid-template-columns:repeat(2,1fr)}}}}
      @media(max-width:560px){{.cat-grid{{grid-template-columns:1fr}}}}
      @keyframes fadeUp{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:none}}}}
      .hero-inner{{animation:fadeUp .6s both}}

      /* general Streamlit buttons */
      div[data-testid="stButton"] > button{{
        border:1px solid {card_bd}; border-radius:13px; background:{surface}; color:{ink};
        font-size:1.02rem; font-weight:700; padding:.7rem 1.15rem; letter-spacing:-.01em;
        box-shadow:0 1px 2px rgba(16,35,61,.05);
        transition:transform .16s, box-shadow .16s, border-color .16s}}
      div[data-testid="stButton"] > button:hover{{border-color:{accent};
        transform:translateY(-2px); color:{navy};
        box-shadow:0 10px 22px -12px {accent}66}}
      /* primary buttons (CTA / voice) */
      .stButton button[kind="primary"], .stButton button[kind="primaryFormSubmit"]{{
        min-height:0; background:linear-gradient(135deg,{accent},{navy});
        border:none; color:#fff; box-shadow:0 12px 24px -10px {accent}88}}
      .stButton button[kind="primary"]:hover{{transform:translateY(-2px); color:#fff;
        box-shadow:0 18px 32px -10px {accent}aa}}

      /* chat bubbles (user right, assistant left) */
      .chat{{display:flex; flex-direction:column; gap:12px; padding:10px 0}}
      .row{{display:flex}} .row.r{{justify-content:flex-end}} .row.l{{justify-content:flex-start}}
      .bub{{max-width:76%; padding:13px 18px; border-radius:18px; font-size:1.05rem;
        line-height:1.55; box-shadow:0 1px 3px rgba(16,35,61,.07); word-break:break-word}}
      .bub.user{{background:linear-gradient(135deg,{accent},{navy}); color:#fff;
        border-bottom-right-radius:6px}}
      .bub.bot{{background:{surface}; color:{ink}; border:1px solid {card_bd};
        border-bottom-left-radius:6px}}

      /* AI assistant */
      .ai-head{{display:flex; align-items:center; gap:11px; font-weight:800; color:{navy};
        font-size:1.42rem; padding:6px 2px 12px; letter-spacing:-.02em}}
      .stChatMessage{{font-size:1.06rem; border-radius:16px}}
      .stTextInput input{{border-radius:12px !important; border:1px solid {card_bd} !important;
        font-size:1.05rem !important}}
      [data-testid="stChatInput"]{{border-radius:14px}}

      /* chips */
      .chips{{display:flex; flex-wrap:wrap; gap:11px}}
      .chip{{background:{surface}; border:1px solid {card_bd}; border-radius:999px;
        padding:11px 20px; font-weight:600; color:{navy}; font-size:1.02rem;
        text-decoration:none; display:inline-block;
        box-shadow:0 1px 2px rgba(16,35,61,.04); transition:all .15s}}
      .chip:hover{{border-color:{accent}; color:{accent}; transform:translateY(-2px)}}

      /* notices */
      .notice{{display:flex; gap:16px; align-items:center; padding:15px 12px;
        border-bottom:1px solid {line}; font-size:1.05rem; border-radius:12px;
        transition:background .15s}}
      .notice:hover{{background:{surface2}}}
      .notice .date{{color:#8493ac; font-variant-numeric:tabular-nums; min-width:104px;
        font-size:.95rem}}
      .notice .t{{font-weight:600; color:{ink}}}
      .newtag{{background:{accent}; color:#fff; font-size:.68rem; font-weight:800;
        border-radius:6px; padding:2px 7px; margin-left:9px; vertical-align:middle;
        letter-spacing:.05em}}

      /* footer */
      .foot{{background:linear-gradient(180deg,{navy2},#071a3d); color:#b9c8e6; margin-top:24px}}
      .foot .gov-wrap{{padding:40px 24px 34px}}
      .foot .cols{{display:flex; gap:48px; flex-wrap:wrap; margin-bottom:22px; font-size:.98rem;
        line-height:1.9}}
      .foot b{{color:#fff; display:block; margin-bottom:10px; font-size:1.02rem; font-weight:700}}
      .foot .copy{{border-top:1px solid #ffffff1a; padding-top:18px; font-size:.86rem; color:#8195b8}}

      /* hands-free voice orb */
      .orb{{width:184px;height:184px;border-radius:50%;margin:30px auto;
        background:radial-gradient(circle at 42% 32%,#dfe7ff,{accent} 62%,{navy});
        box-shadow:0 20px 60px -12px {accent}88, inset 0 -10px 30px #0a235066}}
      .orb.listen{{animation:breathe 2.6s ease-in-out infinite}}
      .orb.think{{animation:spin 1.1s linear infinite}}
      .orb.speak{{animation:pulse .7s ease-in-out infinite}}
      @keyframes breathe{{0%,100%{{transform:scale(1);opacity:.92}}50%{{transform:scale(1.07);opacity:1}}}}
      @keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.13)}}}}
      @keyframes spin{{to{{transform:rotate(360deg)}}}}
      .vstatus{{text-align:center;color:{navy};font-weight:800;font-size:1.3rem;margin-bottom:6px;
        letter-spacing:-.02em}}

      @media (prefers-reduced-motion:reduce){{
        div[data-testid="stButton"] > button, .chip{{transition:none}}
        .orb{{animation:none !important}}
      }}

      /* ---- phone layout (PWA / mobile web) ------------------------------ */
      @media(max-width:640px){{
        /* Streamlit 기본 위젯(탭·입력창·버튼)이 화면 끝에 붙지 않도록 좌우 여백 */
        .block-container{{padding-left:16px !important; padding-right:16px !important}}
        .gov-wrap{{padding:0}}
        .hero, .foot, .util{{margin-left:-16px; margin-right:-16px}}
        .foot .gov-wrap, .util .gov-wrap{{padding:0 16px}}
        .sec{{padding:26px 0}}
        .sec h2{{font-size:1.42rem}} .sec .sub{{font-size:1rem; margin-bottom:18px}}
        /* nav links are decorative on a phone -> hide to reduce clutter */
        .menu{{display:none}}
        .util .gov-wrap{{gap:16px; justify-content:center; flex-wrap:wrap}}
        .brand{{font-size:1.2rem}} .brand .seal{{width:36px;height:36px}}
        .hero h1{{font-size:1.6rem}} .hero p{{font-size:.98rem}}
        .hero-inner{{min-height:100px; padding:20px 18px}}
        .cat-name{{font-size:1.22rem}} .cat-desc{{font-size:.98rem}}
        .cat-card{{min-height:132px; padding:22px 20px}}
        .bub{{max-width:88%; font-size:1.02rem}}
        .orb{{width:150px;height:150px;margin:22px auto}}
        .vstatus{{font-size:1.12rem}}
        .ai-head{{font-size:1.22rem}}
        .notice{{flex-direction:column; align-items:flex-start; gap:3px}}
        .notice .date{{min-width:0}}
        .foot .cols{{gap:24px}}
        /* comfortable touch targets */
        [data-testid="stForm"] button, [data-testid="stTextInput"] input{{
          min-height:48px !important; font-size:1.05rem !important}}
        .chip{{padding:12px 18px}}
      }}

      /* ---- professional polish (desktop + phone) ----------------------- */
      html{{scroll-behavior:smooth}}
      [id]{{scroll-margin-top:72px}}
      /* labeled assistant bubble (ChatGPT-style header on each AI reply) */
      .bub.bot{{position:relative}}
      .bub.bot::before{{content:"복지 도우미"; display:block; font-size:.72rem;
        font-weight:800; color:{accent}; letter-spacing:.01em; margin:0 0 4px}}
      /* tactile press feedback — feels like a native app */
      .cat-card:active{{transform:scale(.97)}}
      div[data-testid="stButton"] > button:active{{transform:translateY(0) scale(.98)}}
      .chip:active{{transform:scale(.96)}}

      /* 마크다운 렌더(굵게/불릿) — 어르신 가독성 */
      .bub.bot strong{{color:{navy}; font-weight:800}}
      .bub.bot{{line-height:1.6}}
      /* 빠른 선택 칩(즉시 전송) — pill 모양 */
      .st-key-qreply{{margin:0 2px 6px}}
      .st-key-qreply div[data-testid="stButton"] > button{{
        border:1px solid {card_bd} !important; border-radius:999px !important;
        background:{surface} !important; color:{navy} !important; font-weight:700 !important;
        font-size:.98rem !important; padding:.55rem .6rem !important; min-height:46px !important}}
      .st-key-qreply div[data-testid="stButton"] > button:hover{{
        border-color:{accent} !important; background:#eef3ff !important; color:{accent} !important}}
      /* Generative-UI 액션 버튼(지도·후속질문) — 작고 가볍게 */
      [class*="st-key-acts"]{{margin:-2px 2px 10px}}
      [class*="st-key-acts"] div[data-testid="stButton"] > button{{
        min-height:40px !important; padding:.4rem .7rem !important;
        font-size:.95rem !important; border-radius:11px !important;
        border:1px solid {card_bd} !important; background:{surface} !important;
        color:{navy} !important; font-weight:600 !important}}
      [class*="st-key-acts"] div[data-testid="stButton"] > button:hover{{
        border-color:{accent} !important; background:#f2f6ff !important}}
      /* 스트리밍 답변 위 '복지 도우미' 라벨 */
      .bub-label{{font-size:.78rem; font-weight:800; color:{accent};
        margin:6px 2px 2px; letter-spacing:.01em}}
      /* (1) RAG 답변 아래 근거 출처 칩 */
      .cite{{display:flex; gap:7px; flex-wrap:wrap; align-items:center;
        margin:-4px 2px 2px; font-size:.84rem; color:{muted}}}
      .cite .src{{background:{surface}; border:1px solid {card_bd}; border-radius:8px;
        padding:3px 9px; color:{navy}; font-weight:600; font-size:.8rem}}
      /* (2) 통증·위기 표현 시 빨간 경고 배너 */
      .warn-banner{{display:flex; gap:13px; align-items:center; margin:10px 0 4px;
        background:#fdecec; border:1px solid #f3b4b4; border-left:5px solid #d93025;
        border-radius:14px; padding:14px 16px; color:#8a1c13; font-size:1.05rem;
        line-height:1.5; font-weight:500}}
      .warn-banner.crisis{{background:#fde7ea; border-color:#f0a3b2;
        border-left-color:#b00020; color:#7a0b1c}}
      .warn-banner b{{color:#c0392b}}
      .warn-banner.crisis b{{color:#b00020}}
      .warn-banner .ic{{font-size:1.65rem; flex-shrink:0}}
      /* (3) 어르신용 빠른 질문 버튼 — 크고 둥글게 */
      .st-key-quickask div[data-testid="stButton"] > button{{
        border:1px solid {card_bd} !important; border-radius:14px !important;
        background:{surface2} !important; color:{navy} !important; font-weight:700 !important;
        font-size:1.05rem !important; padding:.7rem .5rem !important; min-height:52px !important}}
      .st-key-quickask div[data-testid="stButton"] > button:hover{{
        border-color:{accent} !important; background:#eef3ff !important; color:{accent} !important}}
      /* 선택된 분야(primary) 강조 */
      .st-key-quickask div[data-testid="stButton"] > button[kind="primary"],
      .st-key-quickask div[data-testid="stButton"] > button[data-testid*="primary"]{{
        background:linear-gradient(135deg,{accent},{navy}) !important; color:#fff !important;
        border-color:{navy} !important}}
      /* 펼쳐진 자주 묻는 질문 목록 — 왼쪽 정렬, 가볍게 */
      .st-key-quickfaq div[data-testid="stButton"] > button{{
        border:1px solid {card_bd} !important; border-radius:12px !important;
        background:{surface} !important; color:{ink} !important; font-weight:600 !important;
        font-size:1.02rem !important; text-align:left !important; justify-content:flex-start !important;
        padding:.65rem .9rem !important; min-height:48px !important; margin-bottom:2px}}
      .st-key-quickfaq div[data-testid="stButton"] > button:hover{{
        border-color:{accent} !important; background:#f2f6ff !important; color:{navy} !important}}
      .st-key-quickfaq div[data-testid="stButton"] > button p{{text-align:left !important}}

      /* ---- app bottom tab bar — LinkedIn-style compact icon+label row --- */
      .st-key-htnav{{position:fixed; left:50%; transform:translateX(-50%); bottom:16px;
        width:min(440px,92vw); z-index:9999; background:rgba(255,255,255,.98);
        backdrop-filter:saturate(1.3) blur(12px); border:1px solid {line};
        border-radius:20px; box-shadow:0 14px 40px -16px rgba(16,35,61,.4);
        padding:3px 6px}}
      /* keep all 4 tabs on ONE horizontal row even on a phone (Streamlit would
         otherwise stack the columns vertically on narrow widths) */
      .st-key-htnav [data-testid="stHorizontalBlock"]{{gap:2px !important;
        flex-wrap:nowrap !important}}
      .st-key-htnav [data-testid="stColumn"]{{min-width:0 !important;
        width:auto !important; flex:1 1 0 !important}}
      /* each tab: emoji icon stacked OVER the label, flat + compact */
      .st-key-htnav div[data-testid="stButton"] > button{{
        display:flex !important; flex-direction:column !important; align-items:center !important;
        gap:0 !important; border:0 !important; background:transparent !important;
        background-image:none !important; box-shadow:none !important;
        color:#8493ac !important; font-weight:600 !important; font-size:.68rem !important;
        letter-spacing:-.03em; white-space:nowrap; padding:.3rem .1rem !important;
        border-radius:12px !important; min-height:0 !important; line-height:1.15 !important;
        transform:none !important}}
      .st-key-htnav div[data-testid="stButton"] > button::before{{
        font-size:1.24rem; line-height:1; margin-bottom:2px}}
      .st-key-nav_home button::before{{content:"🏠"}}
      .st-key-nav_mywelfare button::before{{content:"✨"}}
      .st-key-nav_talk button::before{{content:"💬"}}
      .st-key-nav_services button::before{{content:"📋"}}
      .st-key-htnav div[data-testid="stButton"] > button:hover{{
        color:{navy} !important; background:{surface2} !important; transform:none !important}}
      /* active tab (primary) — just a colour highlight, must out-rank the base */
      .st-key-htnav div[data-testid="stButton"] > button[kind="primary"],
      .st-key-htnav div[data-testid="stButton"] > button[data-testid*="primary"]{{
        background:transparent !important; background-image:none !important;
        color:{accent} !important; box-shadow:none !important; font-weight:800 !important;
        transform:none !important}}
      .block-container{{padding-bottom:92px !important}}
      @media(max-width:640px){{
        /* full-width slim bottom bar on phone, hugging the home indicator */
        .st-key-htnav{{left:0; right:0; transform:none; bottom:0; width:auto;
          border-radius:16px 16px 0 0; border-bottom:0; padding:3px 4px;
          padding-bottom:calc(3px + env(safe-area-inset-bottom))}}
        .st-key-htnav div[data-testid="stButton"] > button{{
          font-size:.66rem !important; padding:.26rem .05rem !important}}
        .st-key-htnav div[data-testid="stButton"] > button::before{{font-size:1.3rem}}
        .block-container{{padding-bottom:70px !important}}
        .gnav{{box-shadow:0 2px 14px -8px rgba(16,35,61,.35)}}
        .util{{display:none}}
        .bub.bot::before{{font-size:.68rem}}
      }}
    </style>
    """, unsafe_allow_html=True)


def inject_pwa():
    """Make the page installable to a phone home screen (PWA).

    Streamlit sanitises <script> in st.markdown, so we run a tiny same-origin
    component that appends the manifest link + Apple/Android meta tags into the
    PARENT document <head>. The manifest and icons are served locally from
    ./static (enableStaticServing). No external host, no service worker, no data
    leaves the device - it just gives an app-like icon and full-screen launch.
    """
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        (function () {
          try {
            var head = window.parent.document.head;
            function add(tag, attrs) {
              var key = attrs.rel || attrs.name || 'x';
              if (head.querySelector(tag + '[data-pwa="' + key + '"]')) return;
              var el = window.parent.document.createElement(tag);
              for (var k in attrs) el.setAttribute(k, attrs[k]);
              el.setAttribute('data-pwa', key);
              head.appendChild(el);
            }
            add('link', {rel: 'manifest', href: 'app/static/manifest.json'});
            add('link', {rel: 'apple-touch-icon', href: 'app/static/apple-touch-icon.png'});
            add('meta', {name: 'apple-mobile-web-app-capable', content: 'yes'});
            add('meta', {name: 'mobile-web-app-capable', content: 'yes'});
            add('meta', {name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent'});
            add('meta', {name: 'apple-mobile-web-app-title', content: '복지 도우미'});
            add('meta', {name: 'theme-color', content: '#0f2f6f'});
            // iPhone safe-area: let content reach the edges so env(safe-area-*) works
            var vp = window.parent.document.querySelector('meta[name="viewport"]');
            if (vp && vp.content.indexOf('viewport-fit') === -1) {
              vp.content += ', viewport-fit=cover';
            }
          } catch (e) { /* cross-origin or restricted: silently skip */ }
        })();
        </script>
        """,
        height=0,
    )


def bottom_tab_bar(active="home"):
    """Native-style bottom tab bar made of real Streamlit buttons.

    Fixed to the bottom via the `.st-key-htnav` CSS (a floating pill on desktop,
    a full-width bar on phone). The active tab is drawn as a primary button.
    Robust by design — no JavaScript bridge — so a tap always switches screens.
    """
    # 아이콘은 CSS(::before)가 넣으므로 라벨은 텍스트만 — 아이콘 위, 글자 아래로 쌓인다
    tabs = [("home", "홈"), ("mywelfare", "맞춤복지"),
            ("talk", "AI상담"), ("services", "서비스")]
    with st.container(key="htnav"):
        cols = st.columns(4)
        for col, (tab, label) in zip(cols, tabs):
            kind = "primary" if tab == active else "secondary"
            if col.button(label, key=f"nav_{tab}", use_container_width=True, type=kind):
                st.session_state["tab"] = tab
                st.rerun()


# --------------------------------------------------------------------------
# AI assistant helpers
# --------------------------------------------------------------------------
def _speak(answer: str):
    if not st.session_state.get("voice_mode"):
        return None
    from pathlib import Path
    n = st.session_state.get("reply_n", 0) + 1
    st.session_state["reply_n"] = n
    out = Path("data/audio") / f"reply_{n}.m4a"
    out.parent.mkdir(parents=True, exist_ok=True)
    return get_tts().synthesize(answer, str(out))


def _store(r: dict):
    audio = _speak(r["answer"])
    st.session_state["chat"].append(("user", r["question"]))
    # 봇 메시지 = (role, 답변, 오디오, 근거 출처) — 근거는 답변 아래 칩으로 표시
    st.session_state["chat"].append(("bot", r["answer"], audio, r.get("sources") or []))
    st.session_state["latest_audio"] = audio
    if r.get("alert"):
        urgency = "긴급" if r.get("crisis") else "주의"
        st.session_state["alerts"].insert(0, (urgency, r["alert"]))
    st.session_state["state"] = r


# -- (1) 근거 출처 · (2) 경고 배너 · 채팅 렌더 공용 ----------------------------
def _cite_html(sources) -> str:
    """RAG 답변 아래 '근거' 출처 칩(파일명에서 확장자·중복 제거)."""
    if not sources:
        return ""
    import html as _html
    import os
    seen, names = set(), []
    for s in sources:
        n = os.path.splitext(os.path.basename(str(s)))[0].strip()
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    if not names:
        return ""
    chips = "".join(f'<span class="src">{_html.escape(n)}</span>' for n in names[:3])
    return f'<div class="row l"><div class="cite">📄 근거 {chips}</div></div>'


def _chat_html(messages, limit: int = 8) -> str:
    """채팅 내역 → 말풍선 HTML. 봇 답변 아래에 근거 출처 칩을 붙인다."""
    import html as _html
    rows = ""
    for m in messages[-limit:]:
        if m[0] == "user":
            rows += (f'<div class="row r"><div class="bub user">'
                     f'{_html.escape(m[1])}</div></div>')
        else:
            rows += (f'<div class="row l"><div class="bub bot">'
                     f'{_html.escape(m[1])}</div></div>')
            rows += _cite_html(m[3] if len(m) > 3 else [])   # (1) 근거 출처
    return f'<div class="chat">{rows}</div>'


# 통증·우울·고립 표현(주의) / 자살·자해 암시(위기)
_CONCERN = ("아파", "아프", "불편", "도와줘", "도와주", "힘들", "외로", "우울",
            "슬프", "괴로", "못살", "숨이", "어지럽", "쓰러", "기운이없")
_CRISIS = ("죽고싶", "죽어", "자살", "살기싫", "사라지고싶", "끝내고싶")


def _is_crisis_text(t: str) -> bool:
    from src.crisis import is_crisis
    return is_crisis(t)


def _concern_banner():
    """(2) 마지막 사용자 메시지에 통증·우울·위기 표현이 있으면 상담 안내 배너."""
    last = ""
    for m in reversed(st.session_state.get("chat", [])):
        if m[0] == "user":
            last = m[1]
            break
    if not last:
        return
    t = last.replace(" ", "")
    crisis = _is_crisis_text(t) or any(k in t for k in _CRISIS)
    if crisis:
        st.markdown(
            '<div class="warn-banner crisis"><span class="ic">🆘</span>'
            '<div>많이 힘드신가요? 혼자 견디지 마세요. '
            '<b>자살예방 상담전화 109</b> (24시간·무료·비밀보장)로 지금 바로 '
            '연락하실 수 있어요.</div></div>', unsafe_allow_html=True)
    elif any(k in t for k in _CONCERN):
        st.markdown(
            '<div class="warn-banner"><span class="ic">⚠️</span>'
            '<div>몸이나 마음이 힘드신 것 같아요. <b>복지상담 129</b> 또는 '
            '<b>정신건강 상담 109</b>(24시간)에서 도움을 받으실 수 있어요. '
            '아래 버튼으로 관련 복지도 물어보세요.</div></div>', unsafe_allow_html=True)


def _record_signal(q: str, r: dict | None = None):
    """사용자 메시지의 이상신호를 '메시지당 1건만' 기록한다(관리자 모니터용).

    키워드 감지(아파·불편·죽고싶 등)와 대화 분석(파이프라인 alert)을 하나로 합쳐,
    한 메시지가 두 번 저장되지 않도록 한다(중복 방지). 세션(앱 내 관리자 토글)과
    DB(별도 관리자 앱) 양쪽에 1건씩만 남긴다."""
    import time
    t = q.replace(" ", "")
    crisis = _is_crisis_text(t) or any(k in t for k in _CRISIS)
    concern_kw = any(k in t for k in _CONCERN)
    pipe = bool(r and r.get("alert"))
    if not (crisis or concern_kw or pipe):
        return
    name = st.session_state.get("auth_user", "어르신")
    level = "위기" if (crisis or (r and r.get("crisis"))) else "주의"
    hit = [k for k in (_CRISIS + _CONCERN) if k in t]
    reason = ("키워드: " + ", ".join(hit[:3])) if hit else "대화 분석 이상신호"
    st.session_state.setdefault("admin_alerts", []).insert(0, {
        "name": name, "message": q,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": level, "keyword": ", ".join(hit[:3]),
    })
    try:
        from src import db
        db.save_alert(name, q, level, reason)     # DB 1건
    except Exception:
        pass


# (3) 분야 → 자주 묻는 질문 목록. 분야 버튼을 누르면 질문 목록을 펼쳐 보여준다.
_QUICK_FAQ = {
    "💰 기초연금": ["기초연금은 어떻게 신청하나요?", "기초연금 대상 나이가 어떻게 되나요?",
                "기초연금은 매달 얼마를 받나요?", "기초연금 신청에 필요한 서류가 있나요?"],
    "🧠 치매 검사": ["치매 검사는 어디서 받나요?", "치매 조기검진은 무료인가요?",
                 "치매안심센터는 어디에 있나요?", "치매 가족을 위한 지원이 있나요?"],
    "🚇 경로우대": ["지하철 무료로 탈 수 있나요?", "경로우대 교통카드는 어디서 만들어요?",
                "지하철 무임승차는 몇 살부터 되나요?", "공공시설 입장료 할인이 되나요?"],
    "🚨 응급안전": ["혼자 사는데 응급상황이 걱정돼요", "응급버튼을 설치할 수 있나요?",
                "화재감지기를 무료로 설치해 주나요?", "응급안전안심서비스 대상이 누구인가요?"],
    "💬 마음 상담": ["우울하고 외로울 때 상담받고 싶어요", "자살예방 상담 전화번호가 있나요?",
                 "상담 전화는 24시간 되나요?", "무료 심리상담을 받고 싶어요"],
}


def quick_actions(client):
    """(3) 분야 버튼 → 누르면 그 분야의 '자주 묻는 질문 목록'을 펼쳐 보여준다.
    목록에서 질문을 누르면 그때 상담(스트리밍)을 시작한다."""
    st.markdown('<p class="sub" style="margin:4px 2px 8px">자주 찾는 분야 — 누르면 '
                '관련 질문을 보여드려요</p>', unsafe_allow_html=True)
    cats = list(_QUICK_FAQ.keys())
    sel = st.session_state.get("quick_cat")
    with st.container(key="quickask"):
        pairs = [cats[i:i + 2] for i in range(0, len(cats), 2)]
        for rw in pairs:
            cols = st.columns(len(rw))
            for col, label in zip(cols, rw):
                kind = "primary" if label == sel else "secondary"
                if col.button(label, key=f"qc_{label}", use_container_width=True, type=kind):
                    # 같은 분야를 다시 누르면 접기(토글)
                    st.session_state["quick_cat"] = None if label == sel else label
                    st.rerun()
    # 선택한 분야의 질문 목록을 펼친다
    if sel and sel in _QUICK_FAQ:
        st.markdown(f'<p class="sub" style="margin:8px 2px 4px">{sel} — 궁금한 질문을 '
                    '누르세요</p>', unsafe_allow_html=True)
        with st.container(key="quickfaq"):
            for i, qq in enumerate(_QUICK_FAQ[sel]):
                if st.button("❓ " + qq, key=f"qf_{sel}_{i}", use_container_width=True):
                    st.session_state["pending_q"] = qq      # 이때 상담 시작(스트리밍)
                    st.session_state["quick_cat"] = None
                    st.rerun()


# -- 스트리밍 응답 (st.write_stream) + 출처 캡션 (st.caption) --------------------
def _stream_tokens(text: str):
    """RAG 체인은 완결 답변을 반환하므로, 어절 단위로 잘라 토큰처럼 흘려보낸다
    (타이핑 효과). st.write_stream() 에 넘긴다."""
    import re
    import time
    for tok in re.findall(r"\S+\s*|\s+", text):
        yield tok
        time.sleep(0.015)


def _source_caption(sources) -> str:
    """검색된 청크의 출처로 '📚 Source: xxx.pdf' 캡션 문자열(중복 제거)."""
    if not sources:
        return ""
    import os
    seen = []
    for s in sources:
        b = os.path.basename(str(s)).strip()
        if b and b not in seen:
            seen.append(b)
    return ("📚 Source: " + ", ".join(seen[:3])) if seen else ""


def _answer_for(client, q: str, attach: str | None = None):
    """질문 → 결과 dict. 인사/프로필/오류/저장·알림 처리(채팅 append 는 호출부에서).
    attach: 업로드한 사진·문서에서 읽은 글자(있으면 답변 근거로 함께 전달). 실패 시 None."""
    from src.crisis import CRISIS_REPLY, is_crisis
    if is_crisis(q):
        # 위기 표현 → LLM 을 거치지 않고 항상 같은 안전 안내(109·119·129).
        r = {"question": q, "sources": [], "answer": CRISIS_REPLY,
             "crisis": True, "alert": f"위기 표현 감지: “{q}”"}
    elif not attach and q.replace(" ", "").rstrip("!?.~ ") in _GREETINGS:
        u = st.session_state.get("auth_user", "어르신")
        r = {"question": q, "sources": [],
             "answer": f"안녕하세요, {u} 님 😊 궁금하신 복지를 편하게 물어보세요."}
    else:
        p = st.session_state.get("profile", {})
        # 첨부(사진·문서) 내용이 있으면 질문 앞에 붙여, 그 내용을 근거로 답하게 한다.
        q_send = q
        if attach:
            q_send = (f"[어르신이 올린 사진·문서에서 읽은 내용]\n{attach}\n\n"
                      f"[어르신 질문]\n{q}\n\n"
                      "(위 '읽은 내용'을 근거로, 어르신이 이해하기 쉽게 짧게 설명해 주세요. "
                      "고지서·안내문·신청서라면 무엇에 대한 것이고 어디서 어떻게 해야 하는지 "
                      "알려 주세요.)")
        # 맞춤형: 프로필은 질문에 붙이지 않고 RAG 체인의 '시스템 프롬프트'로 전달한다
        # (나이·거주지·건강 반영 + 나이 자격 안내). 질문 원문은 깔끔하게 유지.
        prof = p if _profile_has_info(p) else None
        try:
            with st.spinner("🔎 복지 문서를 검색하고 답변을 준비하는 중입니다…"):
                r = (client.ask(q_send, profile=prof) if st.session_state.get("use_rag", True)
                     else client.ask_norag(q_send))
        except Exception as e:                        # 상담 엔진(워커) 시작 실패 등
            print(f"[app] 상담 엔진 오류: {e}")
            # 대화창에 남도록 답변 형태로 돌려준다(st.warning 은 rerun 후 사라짐).
            return {"question": q, "sources": [], "engine_error": True,
                    "answer": "⚠️ AI 상담 엔진이 아직 준비되지 않아 답변을 드리지 못했어요.\n"
                              "- 버튼·화면은 정상입니다.\n"
                              "- 답변을 받으려면 AI 패키지 설치(requirements.txt)와 "
                              "API 키(OPENAI_API_KEY) 설정이 필요합니다.\n"
                              "- 자세한 오류는 터미널의 [worker] 줄을 확인하세요."}
        if "error" in r:
            st.error(r["error"])
            return None
        r["question"] = q
    if r.get("engine_error"):
        return r                                      # 엔진 오류는 기록·신호 분석 생략
    try:
        from src import db
        u = st.session_state.get("auth_user")
        if u:
            db.save_chat(u, q, r.get("answer", ""), [])
    except Exception:
        pass
    if r.get("alert"):
        st.session_state["alerts"].insert(
            0, ("긴급" if r.get("crisis") else "주의", r["alert"]))
    st.session_state["state"] = r
    return r


def _md_to_html(text: str) -> str:
    """답변의 마크다운을 안전하게 HTML 로 변환(먼저 escape → 허용 서식만 추가).
    **굵게**, 불릿(- · *), 줄바꿈(여백)을 렌더해 어르신이 읽기 쉽게 한다."""
    import html as _html
    import re
    t = _html.escape(text or "")
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)              # [글자](링크) → 글자만
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)     # **굵게**
    t = re.sub(r"(?m)^\s*[-*•]\s+", "• ", t)                    # 불릿 → •
    t = t.replace("\n\n", "<br><br>").replace("\n", "<br>")     # 줄바꿈=여백
    return t


def _bubble(role: str, text: str):
    import html as _html
    if role == "user":
        side, who, body = "r", "user", _html.escape(text)
    else:
        side, who, body = "l", "bot", _md_to_html(text)        # 봇 답변은 마크다운 렌더
    st.markdown(f'<div class="chat" style="padding:2px 0"><div class="row {side}">'
                f'<div class="bub {who}">{body}</div></div></div>',
                unsafe_allow_html=True)


# -- 간단 Generative-UI: 답변 내용에 따른 액션(지도·후속질문) 버튼 ---------------
_CAT_KW = {"💰 기초연금": ("기초연금", "연금"), "🧠 치매 검사": ("치매",),
           "🚇 경로우대": ("경로", "지하철", "교통", "무임"),
           "🚨 응급안전": ("응급", "화재", "안전"),
           "💬 마음 상담": ("우울", "외로", "상담", "마음", "자살", "힘들")}


def _match_cat(q: str):
    for cat, kws in _CAT_KW.items():
        if any(k in q for k in kws):
            return cat
    return None


def _gen_actions(user_q: str, answer: str):
    """답변 내용에 따라 보여줄 액션: 기관 언급 시 '가까운 기관 찾기'(지도 링크) +
    같은 분야의 다른 질문을 후속 질문으로 1개 추천."""
    import urllib.parse as _up
    acts = []
    a = answer or ""
    for term in ("치매안심센터", "행정복지센터", "주민센터", "보건소",
                 "노인복지관", "복지관", "국민연금공단"):
        if term in a:
            dist = (st.session_state.get("profile") or {}).get("district") or ""
            qs = _up.quote(f"대전 {dist} {term}".replace("  ", " ").strip())
            acts.append(("📍 가까운 " + term, "link", f"https://map.kakao.com/?q={qs}"))
            break
    cat = _match_cat(user_q)
    if cat:
        for faq in _QUICK_FAQ[cat]:
            if faq != user_q:
                acts.append(("❓ " + faq, "ask", faq))
                break
    return acts[:3]


def _answer_actions(idx: int, user_q: str, answer: str):
    """봇 답변 아래 Generative-UI 액션(지도·후속질문)만 표시."""
    acts = _gen_actions(user_q, answer)
    if not acts:
        return
    with st.container(key=f"acts{idx}"):
        cols = st.columns(len(acts))
        for j, (label, kind, payload) in enumerate(acts):
            if kind == "link":
                cols[j].link_button(label, payload, use_container_width=True)
            elif cols[j].button(label, key=f"act{idx}_{j}", use_container_width=True):
                st.session_state["pending_q"] = payload
                st.rerun()


def _render_history(messages):
    """지난 대화를 말풍선으로. 봇 답변 아래에 출처 캡션 + 액션(지도·후속질문)."""
    for i, m in enumerate(messages):
        _bubble(m[0], m[1])
        if m[0] == "bot":
            cap = _source_caption(m[3] if len(m) > 3 else [])
            if cap:
                st.caption(cap)
            uq = messages[i - 1][1] if i > 0 and messages[i - 1][0] == "user" else ""
            _answer_actions(i, uq, m[1])


def ask_and_stream(client, q: str, attach: str | None = None):
    """(1) 답변을 st.write_stream 으로 토큰 단위 스트리밍 + (2) st.caption 출처.
    attach: 업로드한 사진·문서에서 읽은 글자(있으면 근거로 전달)."""
    _bubble("user", q)
    if attach:
        st.caption("📎 올려 주신 사진·문서를 읽어서 참고했어요.")
    r = _answer_for(client, q, attach=attach)
    if not r:
        return
    _record_signal(q, r)        # 이상신호 기록(키워드+대화분석 합쳐 메시지당 1건)
    st.markdown('<div class="bub-label">복지 도우미</div>', unsafe_allow_html=True)
    st.write_stream(_stream_tokens(r["answer"]))          # (1) 토큰 스트리밍
    cap = _source_caption(r.get("sources"))
    if cap:
        st.caption(cap)                                   # (2) 📚 Source: xxx.pdf
    st.session_state["chat"].append(("user", q))
    st.session_state["chat"].append(("bot", r["answer"], None, r.get("sources") or []))


_GREETINGS = {"안녕", "안녕하세요", "안녕하십니까", "하이", "헬로", "반가워요",
              "반갑습니다", "고마워요", "고맙습니다", "감사합니다", "감사해요",
              "잘있어요", "수고하세요", "좋은아침", "좋은하루"}


def ask_text(client, q: str):
    # 인사·짧은 일상 대화는 RAG 없이 짧게 인사로만 답한다(복지 나열 방지).
    if q.replace(" ", "").rstrip("!?.~ ") in _GREETINGS:
        u = st.session_state.get("auth_user", "어르신")
        ans = f"안녕하세요, {u} 님 😊 궁금하신 복지를 편하게 물어보세요."
        _store({"question": q, "answer": ans})
        try:
            from src import db
            if st.session_state.get("auth_user"):
                db.save_chat(st.session_state["auth_user"], q, ans, [])
        except Exception:
            pass
        return
    # 맞춤형: 내 정보가 있으면 질문에 짧은 프로필 메모를 덧붙여, 그 사람 상황에
    # 맞춘 답변을 유도한다(정보가 없으면 질문 그대로 — 기존 동작과 동일).
    p = st.session_state.get("profile", {})
    q_send = q
    if _profile_has_info(p):
        q_send = (f"{q}\n\n(참고 — 상담 대상자: {_profile_summary(p)}. "
                  "복지 관련 질문이면 이 분 상황에 맞춰 답하고, 인사·일상 대화면 "
                  "복지 내용을 나열하지 말고 짧게 인사로만 답하세요.)")
    # Demo toggle: RAG on (문서 근거) vs off (LLM만).
    # (4) 검색/생성 동안 '검색 중…' 스피너 표시.
    with st.spinner("🔎 복지 문서를 검색하고 답변을 준비하는 중입니다…"):
        if st.session_state.get("use_rag", True):
            r = client.ask(q_send)
        else:
            r = client.ask_norag(q_send)
    if "error" in r:
        st.error(r["error"]); return
    r["question"] = q   # 화면에는 원래 질문만 보이게
    _store(r)
    # 대화 기록 저장(MySQL 또는 파일)
    try:
        from src import db
        u = st.session_state.get("auth_user")
        if u:
            db.save_chat(u, q, r.get("answer", ""), [])
    except Exception:
        pass


def ask_audio(client, wav: bytes):
    from pathlib import Path
    tmp = Path("data/audio") / "mic_input.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(wav)
    r = client.ask_audio(str(tmp))
    if "error" in r:
        st.error(r["error"]); return
    _store(r)


# --------------------------------------------------------------------------
# 사람 맞춤형 — 내 정보(프로필) + 받을 수 있는 복지 추천
#   일반 상담(질문 맞춤형)에 더해, 어르신 정보를 넣으면 '받을 수 있는 복지'를
#   먼저 알려주고(규칙 매칭), 이어지는 질문도 그 사람 상황을 참고해 답하도록
#   질문에 짧은 프로필 메모를 덧붙인다. 모두 선택 사항이라 비워두면 기존과 동일.
# --------------------------------------------------------------------------
def _profile_summary(p: dict) -> str:
    def yn(v):
        return "예" if v is True else ("아니오" if v is False else "모름")
    out = []
    if p.get("age") is not None:
        out.append(f"나이 {p['age']}세")
    if p.get("district"):
        out.append(f"대전 {p['district']} 거주")
    out += [f"저소득 {yn(p.get('income_low'))}", f"독거 {yn(p.get('living_alone'))}",
            f"거동불편 {yn(p.get('mobility_issue'))}", f"만성질환 {yn(p.get('chronic_illness'))}"]
    return ", ".join(out)


def _profile_has_info(p: dict) -> bool:
    return bool(p) and any(p.get(k) is not None for k in
                           ("age", "income_low", "district", "living_alone",
                            "mobility_issue", "chronic_illness"))


def _load_user_session(name: str):
    """로그인 세션 복원 — 프로필·지난 대화 불러오기.
    로그인 시, 그리고 새로고침(카드·칩 클릭=전체 페이지 reload) 후 URL(?u=)로
    세션을 되살릴 때 공통으로 쓴다(Streamlit 세션은 reload 시 초기화되므로)."""
    from src import db
    st.session_state["auth_user"] = name
    try:
        prof = db.get_profile(name)
        if prof:
            st.session_state["profile"] = prof
            st.session_state["profile_done"] = True
    except Exception:
        pass
    try:
        hist = db.list_chats(name, limit=10)
        chat = []
        for h in hist:
            if h.get("question"):
                chat.append(("user", h["question"]))
                chat.append(("bot", h.get("answer", ""), None))
        if chat:
            st.session_state["chat"] = chat
    except Exception:
        pass


def _logout():
    """로그아웃 → 로그인 화면으로. 세션·URL(?s= 토큰) 모두 비워 새 계정으로 로그인 가능."""
    for k in ("auth_user", "auth_token", "profile", "profile_done", "chat", "pending_q"):
        st.session_state.pop(k, None)
    st.query_params.clear()
    st.rerun()


def _ask_href(q: str) -> str:
    """카드·칩 링크 주소: ?s=<서명토큰>&ask=<질문>.
    새로고침돼도 로그인이 유지되도록 서버가 서명한 토큰을 싣는다
    (성함을 그대로 실으면 주소만으로 남의 계정에 들어갈 수 있으므로 금지)."""
    from urllib.parse import quote
    tok = st.session_state.get("auth_token", "")
    return f"?s={quote(tok)}&ask={quote(q)}"


def login_screen():
    """1단계 — 로그인(성함 기반, 프로토타입). 성공하면 auth_user 설정."""
    inject_css()
    st.markdown('<div class="gov-wrap sec" style="max-width:500px;margin:7vh auto">',
                unsafe_allow_html=True)
    st.markdown(
        '<div style="text-align:center;margin-bottom:10px">'
        '<div class="seal" style="margin:0 auto 14px;width:58px;height:58px;font-size:30px">🏠</div>'
        '<div style="font-size:26px;font-weight:800;color:#0f2f6f;letter-spacing:-.03em">대전노인복지 HUB</div>'
        '<div style="color:#5c6b86;font-size:14px;margin-top:4px">대전광역시 · 어르신 복지 AI</div>'
        '<span style="display:inline-block;margin-top:15px;font-size:12.5px;font-weight:800;color:#2f6bff;'
        'background:#f5f8fd;padding:6px 14px;border-radius:999px">1단계 · 로그인</span>'
        '</div>', unsafe_allow_html=True)
    from src import db

    def _enter(name: str):
        """로그인 성공 처리: 세션 설정 + 저장된 프로필·지난 대화 불러오기."""
        from src.auth_token import make_token
        _load_user_session(name)
        tok = make_token(name)
        st.session_state["auth_token"] = tok
        st.query_params["s"] = tok    # 새로고침(카드 클릭) 후에도 로그인 유지(서명 토큰)
        st.rerun()

    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])
    with tab_login:
        name = st.text_input("성함", key="li_name", placeholder="예: 홍길동")
        pw = st.text_input("비밀번호", key="li_pw", type="password")
        if st.button("로그인", type="primary", use_container_width=True):
            ok, msg = db.login_check(name.strip(), pw)
            if ok:
                _enter(name.strip())
            else:
                st.warning(msg)
    with tab_signup:
        st.caption("처음이시면 계정을 만들어 주세요. (비밀번호 4자 이상)")
        n2 = st.text_input("성함", key="su_name", placeholder="예: 홍길동")
        p2 = st.text_input("비밀번호", key="su_pw", type="password")
        p3 = st.text_input("비밀번호 확인", key="su_pw2", type="password")
        if st.button("회원가입", type="primary", use_container_width=True):
            if p2 != p3:
                st.warning("비밀번호가 서로 다릅니다.")
            else:
                ok, msg = db.signup(n2.strip(), p2)
                if ok:
                    st.success(msg + " — 바로 시작합니다.")
                    _enter(n2.strip())
                else:
                    st.warning(msg)
    st.caption("※ 프로토타입 — 실제 서비스에서는 본인 인증·개인정보 동의가 필요합니다.")
    st.markdown('</div>', unsafe_allow_html=True)


def profile_screen():
    """2단계 — 내 정보 입력. 저장하면 profile_done 설정 후 포털로."""
    inject_css()
    p = st.session_state.get("profile", {})
    user = st.session_state.get("auth_user", "")
    st.markdown('<div class="gov-wrap sec" style="max-width:620px;margin:5vh auto">',
                unsafe_allow_html=True)
    st.markdown(
        '<div style="text-align:center;margin-bottom:12px">'
        '<div class="seal" style="margin:0 auto 12px;width:52px;height:52px;font-size:26px">🧓</div>'
        f'<div style="font-size:23px;font-weight:800;color:#0f2f6f;letter-spacing:-.03em">{user} 님, 반갑습니다</div>'
        '<span style="display:inline-block;margin-top:12px;font-size:12.5px;font-weight:800;color:#2f6bff;'
        'background:#f5f8fd;padding:6px 14px;border-radius:999px">2단계 · 내 정보</span>'
        '</div>', unsafe_allow_html=True)
    st.caption("받으실 수 있는 복지를 정확히 찾기 위해 사용됩니다. 모르면 비워두셔도 됩니다.")
    tri = {"모름": None, "예": True, "아니오": False}
    rev = {None: "모름", True: "예", False: "아니오"}
    c1, c2 = st.columns(2)
    age_s = c1.text_input("나이(만)", value="" if p.get("age") is None else str(p["age"]))
    districts = ["선택 안 함", "동구", "중구", "서구", "유성구", "대덕구"]
    di = districts.index(p["district"]) if p.get("district") in districts else 0
    district = c2.selectbox("거주 구", districts, index=di)
    income = c1.selectbox("저소득(기초수급 등)", ["모름", "예", "아니오"],
                          index=["모름", "예", "아니오"].index(rev[p.get("income_low")]))
    alone = c2.selectbox("독거(혼자 거주)", ["모름", "예", "아니오"],
                         index=["모름", "예", "아니오"].index(rev[p.get("living_alone")]))
    mob = c1.selectbox("거동 불편", ["모름", "예", "아니오"],
                       index=["모름", "예", "아니오"].index(rev[p.get("mobility_issue")]))
    ill = c2.selectbox("만성질환·기억력 저하", ["모름", "예", "아니오"],
                       index=["모름", "예", "아니오"].index(rev[p.get("chronic_illness")]))
    if st.button("저장하고 시작하기", type="primary", use_container_width=True):
        try:
            age = int(age_s) if age_s.strip() else None
        except ValueError:
            age = None
        prof = {"age": age, "district": None if district == "선택 안 함" else district,
                "income_low": tri[income], "living_alone": tri[alone],
                "mobility_issue": tri[mob], "chronic_illness": tri[ill]}
        st.session_state["profile"] = prof
        st.session_state["profile_done"] = True
        # 저장(MySQL 또는 파일 — 민감정보라 json 산출물은 .gitignore)
        try:
            from src import db
            db.save_profile(user, prof)
        except Exception:
            pass
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def my_welfare_cards():
    """session_state['profile'] 기준으로 '내 맞춤 복지'를 카드로 보여준다.
    카드를 누르면 ?ask= 로 해당 복지를 AI 도우미에게 바로 물어본다."""
    from urllib.parse import quote
    p = st.session_state.get("profile", {})
    if not _profile_has_info(p):
        return
    try:
        from src.welfare_rules import Profile, recommend
        eligible, maybe, _ = recommend(Profile(**p))
    except Exception:
        return
    user = st.session_state.get("auth_user", "어르신")
    # 카드 색상(정부 포털 톤) 순환
    palette = ["#1f7a43", "#1d6fe0", "#b0472b", "#6b4fbb",
               "#0f766e", "#b45309", "#be185d", "#0369a1"]
    cards = ""
    for i, r in enumerate(eligible):
        c = palette[i % len(palette)]
        ask_q = f"{r.welfare.name} 대상과 신청 방법을 알려줘"
        cards += (
            f'<a class="cat-card" style="--c:{c}" href="{_ask_href(ask_q)}" target="_self">'
            f'<span class="cat-ic">✅</span>'
            f'<span class="cat-name">{r.welfare.name}</span>'
            f'<span class="cat-desc">{r.welfare.summary}</span>'
            f'<span class="arw">→</span></a>')
    if not cards:
        cards = ('<div class="cat-desc" style="color:#5c6b86">입력하신 정보로는 '
                 '바로 해당되는 복지를 찾지 못했어요. 정보를 더 입력해 보세요.</div>')
    maybe_html = ""
    if maybe:
        chips = "".join(f'<span class="chip">{r.welfare.name}</span>' for r in maybe)
        maybe_html = ('<p class="sub" style="margin-top:22px">확인하면 받으실 수 있어요</p>'
                      f'<div class="chips">{chips}</div>')
    st.markdown(
        '<div class="sec" id="mywelfare"><div class="gov-wrap">'
        f'<h2>{user} 님 맞춤 복지</h2>'
        f'<p class="sub">입력하신 정보({_profile_summary(p)})로 받으실 수 있는 복지입니다. '
        '카드를 누르면 자세히 안내해 드려요. · 정확한 기준은 주민센터 확인</p>'
        f'<div class="cat-grid">{cards}</div>'
        f'{maybe_html}'
        '</div></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Portal sections
# --------------------------------------------------------------------------
def header_nav(client):
    st.markdown(
        '<div class="util"><div class="gov-wrap">'
        '<span>로그인</span><span>회원가입</span><span>사이트맵</span><span>English</span>'
        '</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="gov-wrap" style="padding-top:14px;padding-bottom:6px">',
                unsafe_allow_html=True)
    b, s, n = st.columns([1.55, 2.05, 2.2], vertical_alignment="center")
    seal = ('<span class="seal"><svg class="brand-svg" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V8l7-4 7 4v13"/>'
            '<path d="M9 21v-5h6v5"/></svg></span>')
    b.markdown(f'<div class="brand">{seal} 대전노인복지HUB</div>', unsafe_allow_html=True)
    with s:
        with st.form("hdr_search", clear_on_submit=True):
            sc1, sc2 = st.columns([3, 1])
            q = sc1.text_input("검색", placeholder="복지 서비스 검색",
                               label_visibility="collapsed")
            go = sc2.form_submit_button("검색", use_container_width=True)
        if go and q.strip():
            st.session_state["pending_q"] = q.strip()   # 상담 탭에서 스트리밍 답변
            st.session_state["tab"] = "talk"
            st.rerun()
    with n:
        st.markdown('<div class="menu"><span>복지서비스</span><span>건강·의료</span>'
                    '<span>어르신 돌봄</span><span>공지사항</span><span>상담·문의</span></div>',
                    unsafe_allow_html=True)
        uu = st.session_state.get("auth_user", "")
        hc1, hc2 = st.columns([1.4, 1], vertical_alignment="center")
        hc1.markdown(f'<div style="text-align:right;color:#5c6b86;font-size:.9rem;'
                     f'font-weight:700">👤 {uu} 님</div>', unsafe_allow_html=True)
        if hc2.button("로그아웃", key="hdr_logout", use_container_width=True,
                      help="로그인 화면으로 돌아가 다른 계정으로 로그인합니다."):
            _logout()
    st.markdown('</div>', unsafe_allow_html=True)


def voice_orb(client):
    """Hands-free voice conversation embedded at the top of the home page."""
    import queue
    import time
    from pathlib import Path
    try:
        import av
        import numpy as np
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
        from src.vad_stream import UtteranceSegmenter
    except Exception:
        # 음성 패키지가 없거나(서버) HTTPS가 아니면 음성은 못 쓴다. 하지만 문자
        # 대화는 보여야 하므로, 채팅 내역을 렌더하고 돌아간다(답변이 안 보이던 버그).
        st.caption("💬 글로 입력해 상담하세요. (음성은 패키지·HTTPS 환경에서 지원)")
        st.markdown(_chat_html(st.session_state.get("chat", [])), unsafe_allow_html=True)
        return

    class VP:
        def __init__(self):
            self.seg = UtteranceSegmenter(aggressiveness=3, silence_ms=800, min_speech_ms=400)
            self.res = av.AudioResampler(format="s16", layout="mono", rate=16000)
            self.utterances = queue.Queue()

        def recv(self, frame):
            for f in self.res.resample(frame):
                w = self.seg.add_pcm(f.to_ndarray().astype(np.int16).tobytes())
                if w:
                    self.utterances.put(w)
            return frame

    orb = st.empty()
    status = st.empty()
    ctx = webrtc_streamer(
        key="home_voice", mode=WebRtcMode.SENDONLY, audio_processor_factory=VP,
        # No external STUN/TURN: browser and hub are on the same LAN, so host
        # candidates connect directly and no audio ever leaves the network.
        rtc_configuration={"iceServers": []},
        media_stream_constraints={
            "audio": {"echoCancellation": True, "noiseSuppression": True},
            "video": False},
        async_processing=True)
    chat_ph = st.empty()
    audio_ph = st.empty()
    tts = get_tts()

    def orbset(s, l):
        orb.markdown(f'<div class="orb {s}"></div>', unsafe_allow_html=True)
        status.markdown(f'<div class="vstatus">{l}</div>', unsafe_allow_html=True)

    def render_chat():
        chat_ph.markdown(_chat_html(st.session_state["chat"]), unsafe_allow_html=True)

    render_chat()
    if not ctx.state.playing:
        orbset("listen", "위의 START를 눌러 음성으로 물어보세요. (또는 아래에 입력)")
        return

    NOISE = {"", ".", "..", "네", "음", "아", "감사합니다", "시청해주셔서 감사합니다",
             "구독과 좋아요", "다음 영상에서 만나요", "고맙습니다", "수고하셨습니다"}

    def drain(proc):
        try:
            while True:
                proc.utterances.get_nowait()
        except queue.Empty:
            pass

    orbset("listen", "듣고 있어요…")
    while ctx.state.playing:
        proc = ctx.audio_processor
        if proc is None:
            time.sleep(0.1); continue
        try:
            wav = proc.utterances.get(timeout=0.5)
        except queue.Empty:
            continue
        Path("data/audio").mkdir(parents=True, exist_ok=True)
        utt = Path("data/audio") / "home_utt.wav"
        utt.write_bytes(wav)
        text = (client.transcribe(str(utt)).get("text") or "").strip()
        if len(text) < 2 or text in NOISE:
            continue
        orbset("think", "생각 중…")
        r = client.ask(text)
        if "error" in r:
            drain(proc); orbset("listen", "듣고 있어요…"); continue
        st.session_state["chat"].append(("user", r["question"]))
        st.session_state["chat"].append(("bot", r["answer"], None, r.get("sources") or []))
        st.session_state["state"] = r
        if r.get("alert"):
            st.session_state["alerts"].insert(
                0, ("긴급" if r.get("crisis") else "주의", r["alert"]))
        render_chat()
        n = st.session_state.get("reply_n", 0) + 1
        st.session_state["reply_n"] = n
        audio = tts.synthesize(r["answer"], str(Path("data/audio") / f"vreply_{n}.m4a"))
        if audio:
            orbset("speak", "말하는 중…")
            audio_ph.audio(audio, format="audio/mp4", autoplay=True)
            end = time.time() + min(max(len(r["answer"]) * 0.09, 2.0), 12.0)
            while time.time() < end:
                drain(proc); time.sleep(0.15)
        drain(proc)
        orbset("listen", "듣고 있어요…")


def hero_banner(subtitle: str | None = None):
    art = ('<div class="hero-art"><svg viewBox="0 0 220 220" fill="none" '
           'stroke="#ffffff" stroke-opacity=".55" stroke-width="2">'
           '<circle cx="150" cy="90" r="70"/><circle cx="150" cy="90" r="48"/>'
           '<circle cx="150" cy="90" r="26"/>'
           '<path d="M40 150c30-10 60-10 90 0" stroke-opacity=".35"/>'
           '<path d="M30 170c40-14 90-14 130 0" stroke-opacity=".25"/></svg></div>')
    sub = subtitle or ("말씀하거나 입력하시면 복지 서비스를 쉽게 안내해 드립니다. "
                       "모든 상담은 안전하게 보호됩니다.")
    st.markdown(f"""
    <div class="hero" id="home"><div class="gov-wrap"><div class="hero-inner">
      {art}
      <span class="eyebrow">대전광역시 · 어르신 복지</span>
      <h1>어르신, 무엇을 도와드릴까요?</h1>
      <p>{sub}</p>
    </div></div></div>
    """, unsafe_allow_html=True)


def home_screen(client):
    """홈 탭 — 환영 배너 + 빠른 질문(누르면 상담 탭에서 바로 답변) + 공지."""
    from urllib.parse import quote
    user = st.session_state.get("auth_user", "어르신")
    hero_banner(f"{user} 님, 궁금한 복지를 아래에서 바로 물어보세요. 모든 상담은 안전하게 보호됩니다.")
    st.markdown('<div class="gov-wrap sec" id="homebody">', unsafe_allow_html=True)
    st.markdown('<h2>무엇이든 물어보세요</h2>'
                '<p class="sub">아래 질문을 누르면 ‘AI상담’에서 바로 답해 드려요. '
                '직접 입력하시려면 아래 탭의 💬 AI상담을 눌러 주세요.</p>',
                unsafe_allow_html=True)
    quicks = ["기초연금 신청 방법 알려줘", "노인맞춤돌봄서비스가 뭐예요?",
              "치매안심센터는 어디서 이용하나요?", "무릎이 아픈데 도움받을 곳이 있나요?",
              "경로당·노인복지관 알려줘", "방문 건강관리 신청하고 싶어요"]
    chips = "".join(
        f'<a class="chip" href="{_ask_href(q)}" target="_self">{q}</a>' for q in quicks)
    st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    notices_block()


# 한 번 누르면 바로 전송되는 빠른 선택 칩(auto-send). payload 가 질문으로 즉시 전송.
_QUICK_REPLIES = [
    ("🏠 처음이에요", "복지 서비스가 처음인데 무엇부터 시작하면 좋을까요?"),
    ("📋 서비스 목록", "어떤 복지 서비스가 있는지 알려주세요"),
    ("💻 온라인 신청", "복지 서비스를 온라인으로 신청할 수 있나요?"),
]


_UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif",
                 "pdf", "txt", "md", "csv", "docx"]


def _read_upload(up):
    """업로드 파일 → (추출 텍스트, 오류메시지). OCR 결과는 파일별로 캐시해 재실행 시
    다시 읽지 않는다. 글자를 못 찾으면 (None, 안내문)."""
    try:
        key = "ocr::" + str(getattr(up, "file_id", None) or up.name)
        if key in st.session_state:
            return st.session_state[key], None
        from src.file_intake import extract_text_from_upload
        with st.spinner("🔎 사진·문서에서 글자를 읽는 중입니다…"):
            text, _kind = extract_text_from_upload(up.name, up.getvalue())
        if not (text or "").strip():
            return None, ("사진에서 글자를 찾지 못했어요. 더 밝고 또렷하게, "
                          "글자가 크게 보이도록 다시 찍어 올려 주세요.")
        st.session_state[key] = text
        return text, None
    except Exception as e:
        return None, f"파일을 읽는 중 문제가 생겼어요. {e}"


def chat_uploader():
    """📎 사진·문서 업로더 — 올리면 글자를 읽어(OCR) 답변 근거로 쓴다.
    반환: (attach_text 또는 None, '설명해 주세요' 버튼이 눌렸는지)."""
    attach_text, ask_file = None, False
    with st.expander("📎 사진·문서 올리기 — 고지서·안내문을 올리면 읽어서 설명해 드려요"):
        up = st.file_uploader(
            "사진을 찍어 올리거나 문서를 선택하세요 (사진·PDF·txt)",
            type=_UPLOAD_TYPES, label_visibility="collapsed", key="chat_upload")
        if up is not None:
            attach_text, err = _read_upload(up)
            if err:
                st.warning(err)
            elif attach_text:
                st.success(f"✅ '{up.name}' 에서 글자를 읽었어요. "
                           "질문을 입력하거나 아래 버튼을 눌러 주세요.")
                with st.expander("읽은 내용 미리보기"):
                    st.text(attach_text[:1500])
                ask_file = st.button("🔎 이 사진·문서를 설명해 주세요",
                                     use_container_width=True, type="primary")
    return attach_text, ask_file


def quick_replies(client):
    """빠른 선택 칩 — 누르면 텍스트박스에 채우지 않고 '즉시 전송'(RAG 실행).
    pending_q 로 넘겨 ask_and_stream 이 사용자 메시지 추가 + 답변 생성(중복 없음)."""
    with st.container(key="qreply"):
        cols = st.columns(len(_QUICK_REPLIES))
        for col, (label, q) in zip(cols, _QUICK_REPLIES):
            if col.button(label, key=f"qr_{label}", use_container_width=True):
                st.session_state["pending_q"] = q      # 즉시 전송(스트리밍)
                st.rerun()


def chat_area(client):
    """AI상담 탭 — 전체 화면 채팅(문자 + 음성)."""
    st.markdown('<div class="gov-wrap sec" id="talk">', unsafe_allow_html=True)
    st.markdown('<div class="ai-head">💬 AI 복지 상담</div>', unsafe_allow_html=True)
    st.markdown('<p class="sub" style="margin-top:-4px">궁금하신 복지를 편하게 물어보세요. '
                '대전 어르신 맞춤으로 답해 드립니다.</p>', unsafe_allow_html=True)
    st.session_state["use_rag"] = True   # 항상 RAG 사용(문서 근거)
    # 레이아웃: 대화(위에서 크게) → 빠른버튼 → 입력(아래). 빠른 칩/분야 버튼을
    # 입력창 바로 위로 내려, 대화 내용이 화면 위쪽에서 잘 보이게 한다.
    _concern_banner()              # 통증·위기 표현 시 상담 안내 배너
    hist_slot = st.container()     # 지난 대화(말풍선 + 출처 캡션) — 위
    live_slot = st.container()     # 새 답변이 토큰 단위로 스트리밍되는 자리
    quick_replies(client)          # 즉시 전송 칩(처음·서비스목록·온라인신청) — 입력 바로 위
    quick_actions(client)          # 분야→질문 빠른 버튼 — 입력 바로 위
    attach_text, ask_file = chat_uploader()   # 📎 사진·문서 업로드(OCR)
    with st.form("ai_text", clear_on_submit=True):
        tc1, tc2 = st.columns([5, 1])
        q = tc1.text_input("입력", placeholder="궁금하신 내용을 글로 입력하셔도 됩니다",
                           label_visibility="collapsed")
        go = tc2.form_submit_button("보내기", use_container_width=True)

    pending = st.session_state.pop("pending_q", None)
    pending_attach = None
    if go and q.strip():
        pending, pending_attach = q.strip(), attach_text      # 글 질문(+ 첨부 있으면 근거로)
    elif ask_file and attach_text:
        pending = "올려 주신 사진·문서의 내용을 쉽게 설명해 주세요."
        pending_attach = attach_text                          # 버튼: 첨부만으로 설명 요청

    with hist_slot:
        _render_history(st.session_state.get("chat", []))
    if pending:
        with live_slot:
            ask_and_stream(client, pending, attach=pending_attach)   # 스트리밍 + 출처 + 첨부근거
        st.rerun()                            # 다음 런에서 지난 대화로 정착
    st.markdown('</div>', unsafe_allow_html=True)


def category_cards(client):
    from urllib.parse import quote
    cards = ""
    for name, desc, color, icon, q in CATEGORIES:
        cards += (
            f'<a class="cat-card" style="--c:{color}" href="{_ask_href(q)}" target="_self">'
            f'<span class="cat-ic">{ICONS[icon]}</span>'
            f'<span class="cat-name">{name}</span>'
            f'<span class="cat-desc">{desc}</span>'
            f'<span class="arw">→</span></a>')
    st.markdown('<div class="sec alt" id="services"><div class="gov-wrap">'
                '<h2>복지 서비스 바로가기</h2>'
                '<p class="sub">필요하신 서비스를 선택하시면 AI 도우미가 안내해 드립니다.</p>'
                f'<div class="cat-grid">{cards}</div>'
                '</div></div>', unsafe_allow_html=True)


def popular_block():
    from urllib.parse import quote
    chips = "".join(
        f'<a class="chip" href="{_ask_href(p + " 알려줘")}" target="_self">{p}</a>'
        for p in POPULAR)
    st.markdown('<div class="sec"><div class="gov-wrap">'
                '<h2>자주 찾는 서비스</h2><p class="sub">많이 이용하시는 서비스입니다. '
                '누르면 바로 안내해 드려요.</p>'
                f'<div class="chips">{chips}</div></div></div>', unsafe_allow_html=True)


def notices_block():
    rows = ""
    for i, (date, title) in enumerate(NOTICES):
        new = '<span class="newtag">NEW</span>' if i == 0 else ""
        rows += (f'<div class="notice"><span class="date">{date}</span>'
                 f'<span class="t">{title}{new}</span></div>')
    st.markdown('<div class="sec"><div class="gov-wrap">'
                '<h2>공지사항</h2><p class="sub">시연용 예시 공지입니다. 실제 일정은 '
                '주민센터·대전시 누리집에서 확인하세요.</p>'
                f'{rows}</div></div>', unsafe_allow_html=True)


def footer():
    st.markdown("""
    <div class="foot"><div class="gov-wrap">
      <div class="cols">
        <div><b>대전노인복지HUB</b>대전 어르신 복지 안내 AI<br>
             (비공식 시연 서비스)</div>
        <div><b>바로가기</b>기초연금 · 노인맞춤돌봄<br>치매안심센터 · 방문건강관리</div>
        <div><b>상담전화</b>보건복지상담 129<br>자살예방상담 109 (24시간)<br>응급 119</div>
        <div><b>이용안내</b>개인정보처리방침<br>웹 접근성 안내 · 이용약관</div>
      </div>
      <div class="copy">본 서비스는 학생 프로젝트 시연용이며 대전광역시 공식 사이트가 아닙니다.
        AI 답변은 틀릴 수 있으니 신청 전 주민센터에서 꼭 확인하세요. © 2026 대전노인복지HUB (demo)</div>
    </div></div>
    """, unsafe_allow_html=True)


def voice_conversation(client):
    """Hands-free ChatGPT-style voice chat inside the portal (no record/send)."""
    import queue
    import time
    from pathlib import Path
    try:
        import av
        import numpy as np
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
        from src.vad_stream import UtteranceSegmenter
    except Exception:
        st.error("음성 대화 기능 패키지가 필요합니다: "
                 "pip install streamlit-webrtc webrtcvad 'setuptools<81'")
        return

    st.markdown('<div class="gov-wrap sec">', unsafe_allow_html=True)
    if st.button("← 대전노인복지HUB 홈으로 돌아가기", use_container_width=True, type="primary"):
        st.session_state["mode"] = "text"
        st.rerun()
    st.caption("대화 중이면 먼저 아래 STOP을 누른 뒤 이 버튼을 눌러 주세요.")
    st.markdown('<h2>음성 대화 (AI 도우미)</h2>'
                '<p class="sub">마이크를 켜고 그냥 말씀하세요. 말이 끝나면 자동으로 답합니다. '
                '(이어폰 사용 권장 · 실험 기능)</p>', unsafe_allow_html=True)

    class VP:
        def __init__(self):
            self.seg = UtteranceSegmenter(aggressiveness=3, silence_ms=800,
                                          min_speech_ms=400)
            self.res = av.AudioResampler(format="s16", layout="mono", rate=16000)
            self.utterances = queue.Queue()

        def recv(self, frame):
            for f in self.res.resample(frame):
                wav = self.seg.add_pcm(f.to_ndarray().astype(np.int16).tobytes())
                if wav:
                    self.utterances.put(wav)
            return frame

    orb = st.empty()
    status = st.empty()
    ctx = webrtc_streamer(
        key="portal_voice", mode=WebRtcMode.SENDONLY, audio_processor_factory=VP,
        media_stream_constraints={
            "audio": {"echoCancellation": True, "noiseSuppression": True},
            "video": False},
        async_processing=True)
    chat_ph = st.empty()
    audio_ph = st.empty()
    tts = get_tts()
    st.session_state.setdefault("vchat", [])

    def render():
        with chat_ph.container():
            for role, text in st.session_state["vchat"][-8:]:
                with st.chat_message("user" if role == "user" else "assistant"):
                    st.write(text)

    def orbset(state, label):
        orb.markdown(f'<div class="orb {state}"></div>', unsafe_allow_html=True)
        status.markdown(f'<div class="vstatus">{label}</div>', unsafe_allow_html=True)

    render()
    st.markdown('</div>', unsafe_allow_html=True)

    if not ctx.state.playing:
        orbset("listen", "위의 START를 눌러 음성 대화를 시작하세요.")
        return

    # Common Whisper hallucinations on silence/noise - ignore these.
    NOISE = {"", ".", "..", "네", "음", "아", "감사합니다", "시청해주셔서 감사합니다",
             "구독과 좋아요", "다음 영상에서 만나요", "고맙습니다", "수고하셨습니다"}

    def drain(proc):
        try:
            while True:
                proc.utterances.get_nowait()
        except queue.Empty:
            pass

    orbset("listen", "듣고 있어요…")
    while ctx.state.playing:
        proc = ctx.audio_processor
        if proc is None:
            time.sleep(0.1)
            continue
        try:
            wav = proc.utterances.get(timeout=0.5)
        except queue.Empty:
            continue

        Path("data/audio").mkdir(parents=True, exist_ok=True)
        utt = Path("data/audio") / "portal_utt.wav"
        utt.write_bytes(wav)

        # Transcribe first and reject noise / the AI's own echoed voice.
        text = (client.transcribe(str(utt)).get("text") or "").strip()
        if len(text) < 2 or text in NOISE:
            continue                                   # keep listening, no reply

        orbset("think", "생각 중…")
        r = client.ask(text)
        if "error" in r:
            st.session_state["vchat"].append(("assistant", f"[오류] {r['error']}"))
            render(); drain(proc); orbset("listen", "듣고 있어요…"); continue

        st.session_state["vchat"].append(("user", r["question"]))
        st.session_state["vchat"].append(("assistant", r["answer"]))
        st.session_state["state"] = r
        if r.get("alert"):
            st.session_state["alerts"].insert(
                0, ("긴급" if r.get("crisis") else "주의", r["alert"]))
        render()

        n = st.session_state.get("reply_n", 0) + 1
        st.session_state["reply_n"] = n
        audio = tts.synthesize(r["answer"], str(Path("data/audio") / f"vreply_{n}.m4a"))
        if audio:
            orbset("speak", "말하는 중…")
            audio_ph.audio(audio, format="audio/mp4", autoplay=True)
            # Half-duplex: while the reply plays, discard whatever the mic hears
            # (the AI's own voice) so it does not answer itself.
            cooldown = min(max(len(r["answer"]) * 0.09, 2.0), 12.0)
            end = time.time() + cooldown
            while time.time() < end:
                drain(proc)
                time.sleep(0.15)
        drain(proc)                                    # final flush before listening
        orbset("listen", "듣고 있어요…")


def _go_home():
    # Safe way to change the sidebar radio: set its keyed state in a callback,
    # before the widget is re-instantiated on the next run.
    st.session_state["view"] = "대전노인복지HUB (어르신)"


def admin_view(client):
    st.markdown('<div class="gov-wrap sec">', unsafe_allow_html=True)
    st.button("← 어르신 화면으로 돌아가기", on_click=_go_home, type="primary")
    st.markdown('<h2>관리자 대시보드 · 이상신호 모니터</h2>'
                '<p class="sub">어르신 화면에는 보이지 않는 배경 모니터링입니다.</p>',
                unsafe_allow_html=True)

    # ── 키워드 감지 알림 (아파·불편해·도와줘 등) ──────────────────────────
    alerts = st.session_state.get("admin_alerts", [])
    n_crisis = sum(1 for a in alerts if a["level"] == "위기")
    st.markdown("### 🚨 키워드 감지 알림")
    a1, a2, a3 = st.columns(3)
    a1.metric("총 알림", f"{len(alerts)}건")
    a2.metric("위기", f"{n_crisis}건")
    a3.metric("주의", f"{len(alerts) - n_crisis}건")
    if st.button("알림 비우기", key="clear_admin_alerts"):
        st.session_state["admin_alerts"] = []
        st.rerun()
    if alerts:
        import html as _html
        for a in alerts[:30]:
            a = {k: _html.escape(str(v)) if isinstance(v, str) else v
                 for k, v in a.items()}     # 이름·메시지 HTML 주입 방지
            cls = "crisis" if a["level"] == "위기" else ""
            ic = "🆘" if a["level"] == "위기" else "⚠️"
            st.markdown(
                f'<div class="warn-banner {cls}" style="align-items:flex-start">'
                f'<span class="ic">{ic}</span><div>'
                f'<b>[{a["level"]}] {a["name"]} 님</b> '
                f'<span style="color:#8493ac;font-size:.9rem">· {a["time"]}'
                f'{" · 키워드: " + a["keyword"] if a.get("keyword") else ""}</span><br>'
                f'<span style="font-size:1.06rem">“{a["message"]}”</span>'
                f'</div></div>', unsafe_allow_html=True)
    else:
        st.caption("감지된 키워드 알림이 없습니다.")
    st.divider()

    s = st.session_state.get("state") or {}
    c1, c2, c3 = st.columns(3)
    status = ("긴급 확인" if s.get("crisis") else
              "주의" if s.get("is_abnormal") else "정상")
    c1.metric("상태", status)
    c2.metric("평균 부정감정", f"{s.get('avg_negative', 0.0):.2f}")
    c3.metric("대화 횟수", f"{s.get('history_len', 0)}회")
    counts = s.get("symptom_counts", {})
    if counts:
        st.write("**반복 호소 증상:** " + ", ".join(f"{k}({v}회)" for k, v in counts.items()))
    m = s.get("metrics", {})
    if m:
        cc = st.columns(4)
        cc[0].metric("대화 빈도", f"-{m['freq_drop']:.0%}")
        cc[1].metric("감정 변화", f"+{m['sentiment_shift']:.2f}")
        cc[2].metric("외로움 표현", f"+{m['keyword_shift']:.0%}")
        cc[3].metric("응답 길이", f"-{m['length_drop']:.0%}")
    st.divider()
    st.markdown("#### 사회복지사 알림 로그")
    if st.session_state["alerts"]:
        for urgency, text in st.session_state["alerts"]:
            st.warning(f"[{urgency}]\n\n{text}")
    else:
        st.caption("아직 알림이 없습니다.")
    st.markdown('</div>', unsafe_allow_html=True)


def main():
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("alerts", [])
    st.session_state.setdefault("state", {})
    st.session_state.setdefault("font_scale", 1.0)
    st.session_state.setdefault("voice_mode", False)
    st.session_state.setdefault("tab", "home")   # 폰 앱 탭: home/mywelfare/talk/services
    st.session_state.setdefault("admin_alerts", [])   # 키워드 감지 → 관리자 알림

    # 새로고침(카드·칩 클릭 = 전체 페이지 reload) 후에도 로그인 유지:
    # Streamlit 세션은 reload 시 초기화되므로, URL 의 ?s=<서명토큰> 으로 세션을 복원한다.
    # (?u=<성함> 은 위조가 쉬워 더 이상 받지 않는다.)
    if "u" in st.query_params:
        try:
            del st.query_params["u"]
        except Exception:
            pass
    if not st.session_state.get("auth_user"):
        from src.auth_token import verify_token
        _tok = st.query_params.get("s")
        _u = verify_token(_tok)
        if _u:
            st.session_state["auth_token"] = _tok
            _load_user_session(_u)
        elif _tok:
            try:
                del st.query_params["s"]    # 만료·위조 토큰 제거 → 로그인 화면
            except Exception:
                pass

    # 접속 흐름: 로그인 → 내 정보 입력 → (이후) 포털 화면.
    # 로그인·내 정보는 무거운 어시스턴트가 필요 없으므로 바로 뜬다.
    if not st.session_state.get("auth_user"):
        login_screen()
        return
    if not st.session_state.get("profile_done"):
        profile_screen()
        return

    # 포털부터 어시스턴트 필요 — 지연 로딩(화면은 먼저 뜨고, 첫 질문에서만 준비).
    client = _LazyClient()

    # A category card links to ?s=<token>&ask=<question>; handle ask, keep s(로그인).
    if "ask" in st.query_params:
        q = st.query_params["ask"]
        try:
            del st.query_params["ask"]      # ask 만 제거, ?s=(로그인)는 유지
        except Exception:
            pass
        if q.strip():
            st.session_state["pending_q"] = q.strip()   # 상담 탭에서 스트리밍으로 답변
            st.session_state["tab"] = "talk"   # 질문하면 상담 화면으로 전환

    with st.sidebar:
        st.subheader("화면 설정")
        st.caption("글자 크기")
        b1, b2, b3 = st.columns(3)
        if b1.button("가", use_container_width=True):
            st.session_state["font_scale"] = 1.0; st.rerun()
        if b2.button("가+", use_container_width=True):
            st.session_state["font_scale"] = 1.18; st.rerun()
        if b3.button("가++", use_container_width=True):
            st.session_state["font_scale"] = 1.38; st.rerun()
        st.session_state["high_contrast"] = st.toggle(
            "고대비 모드", value=st.session_state.get("high_contrast", False))
        st.session_state["voice_mode"] = st.toggle(
            "음성으로 답변 듣기", value=st.session_state.get("voice_mode", False),
            help=f"로컬 TTS: {get_tts().backend or '사용 불가'}")
        st.divider()
        view = st.radio("화면", ["대전노인복지HUB (어르신)", "관리자"], key="view")
        _na = len(st.session_state.get("admin_alerts", []))
        if _na:
            st.markdown(f'<div style="background:#fdecec;border:1px solid #f3b4b4;'
                        f'border-radius:10px;padding:8px 12px;color:#8a1c13;'
                        f'font-weight:700;font-size:.9rem;margin:-4px 0 6px">'
                        f'🚨 관리자 알림 {_na}건 — 관리자 화면에서 확인</div>',
                        unsafe_allow_html=True)
        st.caption("상담 방식")
        if st.button("텍스트·검색", use_container_width=True):
            st.session_state["mode"] = "text"; st.rerun()
        if st.button("음성 대화 (핸즈프리)", use_container_width=True):
            st.session_state["mode"] = "voice"; st.rerun()
        if st.button("대화 초기화", use_container_width=True):
            st.session_state["state"] = client.reset()
            st.session_state["chat"] = []
            st.session_state["alerts"] = []
            st.session_state.pop("last_mic", None)
            st.rerun()

    with st.sidebar:
        st.divider()
        st.caption(f"👤 {st.session_state.get('auth_user','')} 님")
        if st.button("내 정보 수정", use_container_width=True):
            st.session_state["profile_done"] = False; st.rerun()
        if st.button("로그아웃", use_container_width=True):
            _logout()

    inject_css()
    inject_pwa()

    if view == "관리자":
        header_nav(client)
        admin_view(client)
        footer()
    elif st.session_state.get("mode") == "voice":
        header_nav(client)
        voice_conversation(client)   # hands-free ChatGPT-style voice loop
    else:
        header_nav(client)
        tab = st.session_state.get("tab", "home")
        bottom_tab_bar(tab)      # 폰 하단 탭바(홈·맞춤복지·AI상담·서비스) — 블로킹 전에

        if tab == "mywelfare":
            if _profile_has_info(st.session_state.get("profile", {})):
                my_welfare_cards()   # 내 맞춤 복지(카드) — 프로필 기반 추천
            else:
                st.markdown('<div class="sec"><div class="gov-wrap">'
                            '<h2>내 맞춤 복지</h2><p class="sub">내 정보를 입력하시면 '
                            '받으실 수 있는 복지를 추천해 드려요. 왼쪽 메뉴의 '
                            '‘내 정보 수정’에서 입력해 주세요.</p></div></div>',
                            unsafe_allow_html=True)
            footer()
        elif tab == "services":
            category_cards(client)
            popular_block()
            footer()
        elif tab == "talk":
            chat_area(client)    # 전체 화면 AI 상담(문자 + 음성)
        else:                    # home
            home_screen(client)  # 환영 + 빠른 질문 + 공지
            footer()


if __name__ != "__mp_main__":
    main()
