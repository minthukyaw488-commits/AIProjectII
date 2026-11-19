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
import streamlit as st

from src import config
from src.tts import TextToSpeech
from src.worker import AssistantClient
from src.crisis import CRISIS_PATTERNS, CRISIS_REPLY, is_crisis

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
# (날짜, 제목, 누르면 AI 상담에 보낼 질문)
# (날짜, 제목, 상세 본문[마크다운], AI 상담용 질문)
NOTICES = [
    ("2026-08-20", "2026년 기초연금 선정기준액 인상 안내",
     "2026년도 기초연금 **선정기준액이 조정**되었습니다. 만 65세 이상 어르신 중 "
     "소득이 기준 이하이면 매월 연금을 받으실 수 있습니다.\n\n"
     "- **대상**: 만 **65세 이상**, 소득인정액이 선정기준액 이하\n"
     "- **신청 장소**: 가까운 **주민센터**·**국민연금공단** 또는 **복지로**(온라인)\n"
     "- **준비물**: 신분증, 통장 사본\n"
     "- **문의**: 가까운 주민센터 *(정확한 기준액·지급액은 주민센터에서 확인)*",
     "기초연금 선정기준액이 얼마인가요? 저도 받을 수 있나요?"),
    ("2026-08-14", "겨울철 에너지바우처 신청 접수 시작",
     "겨울철 **냉·난방비를 지원**하는 에너지바우처 신청이 시작되었습니다.\n\n"
     "- **대상**: 생계·의료·주거·교육급여 수급자 중 노인·영유아·장애인 등 "
     "**더위·추위에 취약한 분**\n"
     "- **지원 내용**: 전기·도시가스·등유 등 **냉·난방 비용** 지원\n"
     "- **신청 장소**: 가까운 **주민센터**(행정복지센터)\n"
     "- **문의**: 가까운 주민센터",
     "에너지바우처는 누가 받을 수 있고 어떻게 신청하나요?"),
    ("2026-08-05", "치매안심센터 무료 조기검진 프로그램 운영",
     "보건소 **치매안심센터**에서 **무료 조기검진·상담**을 운영합니다. 기억력이 "
     "걱정되시면 편하게 검진받으실 수 있습니다.\n\n"
     "- **대상**: 만 60세 이상 어르신 *(지역 기준은 센터 확인)*\n"
     "- **내용**: 인지선별검사, 상담, 치매 어르신·가족 지원\n"
     "- **비용**: **무료**\n"
     "- **문의**: 가까운 **보건소 치매안심센터**",
     "치매 조기검진은 무료인가요? 어디서 받나요?"),
    ("2026-07-28", "노인맞춤돌봄서비스 신규 대상자 모집",
     "혼자 지내시는 어르신께 **생활지원사가 방문·안부 확인**을 도와드리는 "
     "노인맞춤돌봄서비스의 신규 대상자를 모집합니다.\n\n"
     "- **대상**: 돌봄이 필요한 **독거·취약 어르신**\n"
     "- **내용**: 안전·안부 확인, 생활교육, 가사·외출 동행 등\n"
     "- **신청 장소**: 가까운 **주민센터**(행정복지센터)\n"
     "- **문의**: 가까운 주민센터",
     "노인맞춤돌봄서비스 대상과 신청 방법을 알려주세요"),
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
      /* 헤더는 숨기되, 닫은 사이드바(설정·관리자 화면)를 다시 여는 버튼은 보이게 —
         예전엔 헤더와 함께 숨겨져 한 번 닫으면 새로고침 전까지 다시 열 수 없었다. */
      header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"]{{
        visibility:visible !important; position:fixed; top:10px; left:10px; z-index:10000;
        background:#ffffff; border:2px solid {navy}; border-radius:12px;
        width:48px; height:48px; box-shadow:0 4px 14px -6px rgba(16,35,61,.45)}}
      header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] *{{
        visibility:visible !important; color:{navy} !important}}
      .block-container{{padding:0 !important; max-width:100% !important}}
      .stApp{{background:{bg}}}
      html, body, [class*="css"], .stApp{{font-size:{base}px;
        font-family:'Pretendard','Pretendard Variable',-apple-system,'Noto Sans KR',sans-serif;
        color:{ink}; -webkit-font-smoothing:antialiased}}
      .gov-wrap{{max-width:1140px; margin:0 auto; padding:0 24px}}

      /* top utility bar */
      .util{{background:{navy2}; color:#c7d4ee; font-size:.82rem}}
      .util .gov-wrap{{display:flex; justify-content:flex-end; gap:22px; padding:9px 24px}}
      .util a{{opacity:.85; cursor:pointer; color:#c7d4ee !important; text-decoration:none !important}}
      .util a:hover{{opacity:1; color:#fff !important}}

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
      .menu{{flex-wrap:wrap}}
      .menu a{{padding:9px 12px; border-radius:11px; color:{muted} !important; cursor:pointer;
        transition:all .15s; text-decoration:none !important; white-space:nowrap}}
      .menu a:hover{{background:{surface2}; color:{navy} !important}}

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
      a.notice{{text-decoration:none !important; cursor:pointer; color:inherit}}
      a.notice .go{{margin-left:auto; color:#2f6bff; font-size:1.6rem; font-weight:700; line-height:1;
        white-space:nowrap}}
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
        .gov-wrap{{padding:0 15px}}
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
    st.markdown(_PAGE_MARGIN_CSS, unsafe_allow_html=True)
    if not hc:                     # 고대비 모드는 자체 흑백 팔레트를 그대로 사용
        st.markdown(_ELDER_CSS, unsafe_allow_html=True)
    st.markdown(_PHONE_TEXT_CSS, unsafe_allow_html=True)   # 폰: 버튼·하단 탭 글씨 16px 이상
    # 움직임(애니메이션): 고대비 모드에서는 끄고, 기기의 '동작 줄이기' 설정도 존중한다.
    st.markdown(_NO_MOTION_CSS if hc else _MOTION_CSS, unsafe_allow_html=True)


# ── UI 애니메이션 — 어르신용이라 느리고 부드럽게(0.2~0.4초), 깜빡임 없음 ─────────────
#  ① 새 말풍선 부드럽게 등장(마지막 두 개만 — 지난 대화가 매번 다시 움직이지 않게)
#  ② 답변 준비 중 '점 세 개' 표시(아래 _TYPING_HTML)
#  ③ 버튼을 누르면 살짝 눌리는 느낌
#  ④ 맞춤복지 카드 순서대로 등장(기존 fadeUp, 9장까지 지연)
#  ⑤ 위기 안내 배너: 2.4초 주기의 은은한 테두리 빛(초당 3회 이상 깜빡임 금지 기준 준수)
#  기기 설정 '동작 줄이기(prefers-reduced-motion)'면 모든 움직임을 끈다.
_MOTION_CSS = """
<style>
  @keyframes bubIn{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
  @keyframes dotJump{0%,60%,100%{transform:translateY(0);opacity:.45}30%{transform:translateY(-6px);opacity:1}}
  @keyframes softGlow{0%,100%{box-shadow:0 0 0 0 rgba(176,0,32,0)}50%{box-shadow:0 0 0 6px rgba(176,0,32,.18)}}
  .chat .row:nth-last-child(-n+2) .bub, .bub-label{animation:bubIn .35s ease-out both}
  .bub.typing{display:inline-flex; align-items:center; gap:10px; color:#5c6b86}
  .bub.typing .dots i{display:inline-block; width:9px; height:9px; margin:0 2px; border-radius:50%;
    background:#2f6bff; animation:dotJump 1.2s ease-in-out infinite}
  .bub.typing .dots i:nth-child(2){animation-delay:.15s}
  .bub.typing .dots i:nth-child(3){animation-delay:.3s}
  .stApp div[data-testid="stButton"] > button,
  .stApp div[data-testid="stFormSubmitButton"] > button{transition:transform .12s ease, box-shadow .12s ease}
  .stApp div[data-testid="stButton"] > button:active,
  .stApp div[data-testid="stFormSubmitButton"] > button:active{transform:scale(.96)}
  .stApp .st-key-htnav div[data-testid="stButton"] > button:active{transform:scale(.92) !important}
  .cat-card:nth-child(7){animation-delay:.3s} .cat-card:nth-child(8){animation-delay:.35s}
  .cat-card:nth-child(9){animation-delay:.4s}
  .warn-banner.crisis{animation:softGlow 2.4s ease-in-out infinite}
  @media (prefers-reduced-motion: reduce){
    *, *::before, *::after{animation:none !important; transition:none !important}
  }
</style>
"""
_NO_MOTION_CSS = """
<style>*, *::before, *::after{animation:none !important; transition:none !important}</style>
"""
_TYPING_HTML = ('<div class="chat" style="padding:2px 0"><div class="row l">'
                '<div class="bub bot typing"><span class="dots"><i></i><i></i><i></i></span>'
                '답변을 준비하고 있어요</div></div></div>')


# 폰(640px 이하)에서 버튼·하단 탭·접기 메뉴 글씨가 14.9px 등 16px 보다 작아지던 문제.
# 어르신 가독성 기준(최소 16px)으로 올린다. 1rem = 기본 글자 크기(가/가+/가++ 반영).
_PHONE_TEXT_CSS = """
<style>
  @media(max-width:640px){
    .stApp div[data-testid="stButton"] > button,
    .stApp div[data-testid="stButton"] > button p,
    .stApp div[data-testid="stFormSubmitButton"] > button,
    .stApp div[data-testid="stFormSubmitButton"] > button p,
    .stApp [data-testid="stExpander"] summary p{font-size:max(16px, 1rem) !important}
    .stApp .st-key-htnav div[data-testid="stButton"] > button,
    .stApp .st-key-htnav div[data-testid="stButton"] > button p{
      font-size:16px !important; letter-spacing:-.04em}
  }
</style>
"""


# 페이지 좌우 여백(표준 폭) — 화면 끝에 붙던 입력창·버튼·채팅에 여백을 준다.
# 기능 코드는 건드리지 않고 CSS 만 덧붙인다.
#  · 본문 블록: 최대 1180px, 가운데 정렬, 좌우 16~40px(화면 크기에 따라)
#  · 배경이 화면 끝까지 가야 하는 상단 띠(.util)·배너(.hero)·푸터(.foot)는 제외
_TOP = '.block-container > [data-testid="stVerticalBlock"] > '
_BODY = _TOP + ':not(:has(.util, .hero, .foot))'
_PAGE_MARGIN_CSS = f"""
<style>
  {_BODY}{{width:100% !important; max-width:1180px !important;
    margin-left:auto !important; margin-right:auto !important; box-sizing:border-box;
    padding-left:clamp(16px,4vw,40px) !important; padding-right:clamp(16px,4vw,40px) !important}}
  {_BODY} .gov-wrap{{padding-left:0 !important; padding-right:0 !important}}
  /* 상단 메뉴 글자가 '복/지/서/비/스'처럼 한 글자씩 세로로 끊기지 않게 */
  .menu{{flex-wrap:wrap; row-gap:4px}}
  .menu > *{{white-space:nowrap; padding-left:11px !important; padding-right:11px !important}}
</style>
"""

# 어르신 눈에 편한 색 — 노안·수정체 황변을 고려해 대비 7:1 이상(WCAG AAA),
# 눈부심이 적은 따뜻한 미색 바탕, 색이 아닌 아이콘·글자로 구분. CSS 만 덧붙인다.
_ELDER_CSS = """
<style>
  .stApp{background:#f7f5f0 !important}
  .sub, .sec .sub{color:#3d4655 !important}
  .sec.alt{background:transparent !important}   /* 서비스 영역 회색 사각 배경 제거 */
  .menu a, .menu span{color:#3d4655 !important}
  .util{font-size:1rem !important}
  /* 공지 */
  .notice .date{color:#4a5363 !important; font-weight:600}
  .notice .t{font-size:1.05rem}
  .newtag{background:#9b1c13 !important; font-size:.8rem !important}
  /* 서비스·맞춤복지 카드: 흰 카드 + 진한 글자 + 왼쪽 색 띠(색은 보조 표시) */
  .cat-card{background:#ffffff !important; background-image:none !important;
    color:#1c2430 !important; border:2px solid #d9d4c7 !important;
    border-left:10px solid var(--c) !important; box-shadow:0 2px 8px rgba(0,0,0,.06) !important;
    animation:none !important}
  .cat-card:hover{transform:none !important; border-color:#1e3a8a !important;
    border-left-color:var(--c) !important; box-shadow:0 4px 14px rgba(0,0,0,.10) !important}
  .cat-card, .cat-card *{text-decoration:none !important}
  .cat-name{color:#1c2430 !important}
  .cat-desc{color:#3d4655 !important; opacity:1 !important}
  .cat-ic{background:var(--c) !important}
  .cat-ic svg{color:#ffffff !important}
  .cat-card .arw{color:#1e3a8a !important; opacity:1 !important}
  /* 버튼: 그라데이션 대신 단색 진남색 */
  .stApp .stButton button[kind="primary"],
  .stApp div[data-testid="stForm"] button[kind="primaryFormSubmit"],
  .stApp div[data-testid="stForm"] button[kind="secondaryFormSubmit"]{
    background:#1e3a8a !important; background-image:none !important;
    border:2px solid #1e3a8a !important; color:#ffffff !important; box-shadow:none !important}
  .stApp div[data-testid="stButton"] > button[kind="secondary"]{
    border:2px solid #b9b3a4 !important; color:#1c2430 !important}
  /* 입력창 테두리를 또렷하게 */
  [data-baseweb="input"]{border:2px solid #8a8476 !important}
  /* 질문 칩 */
  .chip{border:2px solid #1e3a8a !important; color:#1e3a8a !important; font-weight:700}
  /* 말풍선 */
  .bub.user{background:#1e3a8a !important; background-image:none !important}
  .bub.bot{border:2px solid #d9d4c7 !important}
  .bub.bot::before{font-size:.85rem !important; color:#1e3a8a !important}
  /* 하단 탭: 선택 안 된 탭 글자도 잘 보이게 */
  .stApp .st-key-htnav div[data-testid="stButton"] > button[kind]{border:0 !important;
    background:transparent !important; box-shadow:none !important}
  .stApp .st-key-htnav div[data-testid="stButton"] > button[kind="secondary"]{color:#3d4655 !important}
  .stApp .st-key-htnav div[data-testid="stButton"] > button[kind="primary"]{color:#1e3a8a !important;
    font-weight:800 !important}
</style>
"""

# 로그인·내 정보 화면은 폼이 너무 넓게 퍼지지 않도록 가운데 좁은 폭으로.
_NARROW_FORM_CSS = "<style>" + _BODY + "{{max-width:{w}px !important}}</style>"


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
                st.session_state.pop("notice", None)   # 탭 이동 시 공지 상세 닫기
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
# 위기 표현은 앱·파이프라인·이상신호가 같은 기준을 쓴다(src/crisis.py, 띄어쓰기 무시).
_CRISIS = CRISIS_PATTERNS


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
    crisis = any(k in t for k in _CRISIS)
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
    crisis = any(k in t for k in _CRISIS)
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


def _answer_for(client, q: str, attach: str | None = None, spinner: bool = True):
    """질문 → 결과 dict. 인사/프로필/오류/저장·알림 처리(채팅 append 는 호출부에서).
    attach: 업로드한 사진·문서에서 읽은 글자(있으면 답변 근거로 함께 전달). 실패 시 None."""
    if is_crisis(q):
        # 위기(자살·자해) 표현 → 검색·LLM 없이 즉시 고정 '도움 연결' 안내(109·119·129).
        # 이상신호 기록·관리자 알림은 호출부의 _record_signal 이 '위기'로 남긴다.
        r = {"question": q, "sources": [], "answer": CRISIS_REPLY, "crisis": True,
             "alert": f"위기 표현 감지 — 즉시 확인 필요: {q}"}
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
        import contextlib
        with (st.spinner("🔎 복지 문서를 검색하고 답변을 준비하는 중입니다…") if spinner
              else contextlib.nullcontext()):
            r = (client.ask(q_send, profile=prof) if st.session_state.get("use_rag", True)
                 else client.ask_norag(q_send))
        if "error" in r:
            st.error(r["error"])
            return None
        r["question"] = q
        # 대상 연령이 아닌 복지를 물으면 답변 맨 앞에 안내(코드로 확정 — 모델이 빠뜨리지 않게)
        from src.welfare_rules import age_notice
        r["answer"] = age_notice(q, p.get("age"),
                                 p.get("name") or st.session_state.get("auth_user", "")) + r.get("answer", "")
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
    typing = st.empty()
    typing.markdown(_TYPING_HTML, unsafe_allow_html=True)   # ② 답변 준비 중 '점 세 개'
    try:
        r = _answer_for(client, q, attach=attach, spinner=False)
    finally:
        typing.empty()
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
    """프로필 한 줄 요약 — '예'인 항목만 이름으로 적는다('아니오'·'모름'은 생략).
    예) 나이 80세, 대전 서구 거주, 저소득, 혼자 거주, 거동 불편"""
    out = []
    if p.get("age") is not None:
        out.append(f"나이 {p['age']}세")
    if p.get("district"):
        out.append(f"대전 {p['district']} 거주")
    for key, label in (("income_low", "저소득"), ("living_alone", "혼자 거주"),
                       ("mobility_issue", "거동 불편"), ("chronic_illness", "만성질환")):
        if p.get(key) is True:
            out.append(label)
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
    st.session_state["is_admin"] = config.is_admin(name)
    if st.session_state["is_admin"]:
        # 관리자(사회복지사) 계정: 어르신 프로필·대화 기록 없이 모니터 화면으로 바로 간다.
        st.session_state["profile_done"] = True
        return
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


def _app_secret() -> bytes:
    """URL 로그인 토큰 서명용 비밀키. data/.app_secret 에 1회 생성·보관(커밋 금지).
    서버 재시작에도 같은 키를 쓰도록 파일로 유지한다."""
    from pathlib import Path
    p = Path(__file__).resolve().parent / "data" / ".app_secret"
    try:
        if p.exists():
            b = p.read_bytes()
            if b:
                return b
        import secrets as _secrets
        sec = _secrets.token_bytes(32)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(sec)
        return sec
    except Exception:
        # 파일 접근 불가 시에도 동작은 유지(데모). 운영에선 파일 키를 권장.
        return b"welfare-hub-insecure-fallback-change-me"


def _user_token(name: str) -> str:
    """성함에 대한 서명 토큰(HMAC-SHA256). 비밀키 없이는 위조 불가."""
    import hashlib
    import hmac
    return hmac.new(_app_secret(), (name or "").encode("utf-8"),
                    hashlib.sha256).hexdigest()[:24]


def _verify_user_token(name: str, tok: str) -> bool:
    """URL 의 ?u=성함 이 유효한 서명(?t=)과 함께 왔는지 확인(계정 도용 차단)."""
    import hmac
    if not name or not tok:
        return False
    return hmac.compare_digest(_user_token(name), tok)


_LOGIN_COOKIE = "whub_login"
_LOGIN_COOKIE_DAYS = 30

_REMEMBER_HELP = (
    '<div class="remember-help">체크하시면 다음에 다시 들어오실 때 '
    '<b>성함과 비밀번호를 넣지 않아도</b> 바로 들어가집니다. (30일 동안)<br>'
    '⚠️ 복지관·가족이 함께 쓰는 컴퓨터에서는 체크하지 마세요.</div>'
    '<style>.remember-help{font-size:.95rem; line-height:1.6; color:#3d4655; background:#fff;'
    'border:1px solid #d9d4c7; border-radius:12px; padding:10px 14px; margin:-6px 0 12px}'
    '[data-testid="stCheckbox"] label p{font-size:1.08rem !important; font-weight:700}</style>')


def _read_login_cookie():
    """브라우저 쿠키의 (성함, 서명토큰). 없거나 형식이 틀리면 None."""
    from urllib.parse import unquote
    try:
        raw = st.context.cookies.get(_LOGIN_COOKIE)
    except Exception:
        return None
    if not raw or "|" not in unquote(raw):
        return None
    name, tok = unquote(raw).rsplit("|", 1)
    return (name, tok) if name and tok else None


def _write_login_cookie(name):
    """'로그인 상태 유지' 쿠키 저장(name) 또는 삭제(None). 값은 성함|서명토큰(비밀번호 아님)."""
    import json
    import time
    import streamlit.components.v1 as components
    if name:
        val = json.dumps(f"{name}|{_user_token(name)}")
        age = _LOGIN_COOKIE_DAYS * 24 * 3600
    else:
        val, age = '""', 0
    components.html(
        f"<!-- {time.time_ns()} --><script>try{{var w=window.parent;"
        f"w.document.cookie='{_LOGIN_COOKIE}='+encodeURIComponent({val})+"
        f"'; max-age={age}; path=/; SameSite=Lax'+(w.location.protocol==='https:'?'; Secure':'');"
        "}catch(e){}</script>", height=0)


def _set_login_params(name: str):
    """로그인 유지용 URL 파라미터 설정: ?u=성함 &t=서명토큰."""
    st.query_params["u"] = name
    st.query_params["t"] = _user_token(name)


@st.dialog("로그아웃 확인")
def _confirm_logout():
    """잘못 눌러 바로 로그아웃되지 않도록 한 번 더 묻는다.
    (성함·비밀번호를 기억하지 못하는 어르신이 다시 못 들어오는 일을 막기 위함)"""
    st.markdown('<div style="font-size:1.12rem;line-height:1.7">정말 <b>로그아웃</b> 하시겠어요?'
                '<br>다시 들어오실 때 <b>성함과 비밀번호</b>가 필요합니다.</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("아니요, 계속 이용", type="primary", use_container_width=True,
                 key="logout_no"):
        st.rerun()                       # 창 닫기
    if c2.button("네, 로그아웃", use_container_width=True, key="logout_yes"):
        _logout()


def _logout():
    """로그아웃 → 로그인 화면으로. 세션·URL(?u=,?t=) 모두 비워 새 계정으로 로그인 가능."""
    st.session_state["clear_login_cookie"] = True   # '로그인 상태 유지' 쿠키도 지움
    st.session_state["logged_out"] = True
    for k in ("auth_user", "is_admin", "profile", "profile_done", "chat", "pending_q"):
        st.session_state.pop(k, None)
    st.query_params.clear()
    st.rerun()


_TABS = ("home", "mywelfare", "talk", "services")


def _nav_href(tab: str) -> str:
    """상단 메뉴 링크 주소: ?u=<성함>&t=<서명토큰>&tab=<탭>.
    _ask_href 와 같은 방식(서명 토큰 포함)이라 눌러도 로그인이 유지된다."""
    from urllib.parse import quote
    u = st.session_state.get("auth_user", "")
    t = _user_token(u) if u else ""
    return f"?u={quote(u)}&t={quote(t)}&tab={quote(tab)}"


def _ask_href(q: str) -> str:
    """카드·칩 링크 주소: ?u=<성함>&t=<서명토큰>&ask=<질문>.
    새로고침돼도 로그인이 유지되되, 서명(t) 없이는 복원되지 않아 계정 도용을 막는다."""
    from urllib.parse import quote
    u = st.session_state.get("auth_user", "")
    t = _user_token(u) if u else ""
    return f"?u={quote(u)}&t={quote(t)}&ask={quote(q)}"


def _notice_href(i: int) -> str:
    """공지 상세 페이지 링크: ?u=&t=&notice=<번호> (로그인 유지)."""
    from urllib.parse import quote
    u = st.session_state.get("auth_user", "")
    t = _user_token(u) if u else ""
    return f"?u={quote(u)}&t={quote(t)}&notice={i}"


def notice_detail(client, i: int):
    """공지사항 상세 화면 — 제목·날짜·본문 + 목록으로/AI 상담 버튼(챗봇 아님)."""
    if i < 0 or i >= len(NOTICES):
        st.session_state.pop("notice", None)
        st.rerun()
        return
    date, title, body, ask_q = NOTICES[i]
    st.markdown('<div class="gov-wrap sec" id="notice-detail">', unsafe_allow_html=True)
    if st.button("← 공지 목록으로", key="notice_back"):
        st.session_state.pop("notice", None)
        st.rerun()
    st.markdown(
        f'<div style="border-bottom:2px solid #e6ebf4;padding-bottom:12px;margin:6px 0 16px">'
        f'<div style="font-size:1.5rem;font-weight:800;color:#0f2f6f;letter-spacing:-.02em">'
        f'{title}</div>'
        f'<div style="color:#8493ac;font-size:.92rem;margin-top:6px">📅 {date} · '
        f'대전노인복지HUB 공지</div></div>', unsafe_allow_html=True)
    st.markdown(body)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💬 이 내용 AI 도우미에게 물어보기", key="notice_ask",
                 type="primary", use_container_width=True):
        st.session_state["pending_q"] = ask_q
        st.session_state["tab"] = "talk"
        st.session_state.pop("notice", None)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def login_screen():
    """1단계 — 로그인(성함 기반, 프로토타입). 성공하면 auth_user 설정."""
    inject_css()
    st.markdown(_NARROW_FORM_CSS.format(w=520), unsafe_allow_html=True)
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
        _load_user_session(name)
        _set_login_params(name)       # ?u=성함 &t=서명토큰 (새로고침 후에도 로그인 유지)
        st.rerun()

    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])
    # 입력란을 st.form 으로 묶어, 노트북에서는 Enter, 휴대폰에서는 키보드의
    # '이동/완료' 만 눌러도 로그인·회원가입이 되게 한다(버튼 클릭도 그대로 동작).
    # form 버튼도 기존 로그인 버튼과 같은 파란 그라데이션으로 보이게.
    # (이 style 은 로그인 화면을 그릴 때만 페이지에 있으므로 다른 화면의 form 은 그대로)
    st.markdown(
        '<style>div[data-testid="stForm"] button[kind="primaryFormSubmit"]{'
        'background:linear-gradient(135deg,#2f6bff,#0f2f6f) !important;border:none !important;'
        'box-shadow:0 12px 24px -10px #2f6bff88 !important}</style>',
        unsafe_allow_html=True)
    with tab_login:
        with st.form("login_form", border=False):
            name = st.text_input("성함", key="li_name", placeholder="예: 홍길동")
            pw = st.text_input("비밀번호", key="li_pw", type="password")
            remember = st.checkbox("이 기기에서 로그인 상태 유지", key="li_remember")
            st.markdown(_REMEMBER_HELP, unsafe_allow_html=True)
            submitted = st.form_submit_button("로그인", type="primary",
                                              use_container_width=True)
        if submitted:
            ok, msg = db.login_check(name.strip(), pw)
            if ok and config.is_admin(name) and "미설정" in msg:
                ok, msg = False, "관리자 계정은 비밀번호가 필요합니다. 서버 담당자에게 문의하세요."
            if ok:
                if remember and not config.is_admin(name.strip()):
                    # 다음 화면에서 브라우저 쿠키에 저장(관리자 계정은 보안상 저장하지 않음)
                    st.session_state["set_login_cookie"] = name.strip()
                _enter(name.strip())
            else:
                st.warning(msg)
    with tab_signup:
        st.caption("처음이시면 계정을 만들어 주세요. (비밀번호 4자 이상)")
        with st.form("signup_form", border=False):
            n2 = st.text_input("성함", key="su_name", placeholder="예: 홍길동")
            p2 = st.text_input("비밀번호", key="su_pw", type="password")
            p3 = st.text_input("비밀번호 확인", key="su_pw2", type="password")
            submitted2 = st.form_submit_button("회원가입", type="primary",
                                               use_container_width=True)
        if submitted2:
            if p2 != p3:
                st.warning("비밀번호가 서로 다릅니다.")
            elif config.is_admin(n2):
                st.warning("이 이름은 사용할 수 없습니다. 다른 성함으로 가입해 주세요.")
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
    st.markdown(_NARROW_FORM_CSS.format(w=660), unsafe_allow_html=True)
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
    ps = _profile_summary(p)
    info = f"({ps})" if ps else ""          # '예'인 항목만 — 하나도 없으면 괄호 생략
    st.markdown(
        '<div class="sec" id="mywelfare"><div class="gov-wrap">'
        f'<h2>{user} 님 맞춤 복지</h2>'
        f'<p class="sub">입력하신 정보{info}로 받으실 수 있는 복지입니다. '
        '카드를 누르면 자세히 안내해 드려요. · 정확한 기준은 주민센터 확인</p>'
        f'<div class="cat-grid">{cards}</div>'
        f'{maybe_html}'
        '</div></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Portal sections
# --------------------------------------------------------------------------
def header_nav(client):
    st.markdown(
        # 상단 띠: 하단 탭(홈·맞춤복지·AI상담·서비스)과 겹치던 링크를 빼고 안내만 표시
        '<div class="util"><div class="gov-wrap">'
        '<span>대전광역시 어르신 복지 AI 안내</span>'
        '<span>궁금한 점은 복지상담 ☎ 129</span>'
        '</div></div>' + _HEADER_TIDY_CSS, unsafe_allow_html=True)
    st.markdown('<div class="gov-wrap" style="padding-top:14px;padding-bottom:6px">',
                unsafe_allow_html=True)
    b, s, n = st.columns([1.5, 2.1, 2.1], vertical_alignment="center")
    seal = ('<span class="seal"><svg class="brand-svg" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V8l7-4 7 4v13"/>'
            '<path d="M9 21v-5h6v5"/></svg></span>')
    b.markdown(f'<div class="brand">{seal} 대전노인복지HUB</div>', unsafe_allow_html=True)
    with s, st.container(key="hdrsearch"):
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
        # 메뉴: 하단 탭과 겹치는 '복지서비스'(=서비스)·'상담·문의'(=AI상담)는 빼고
        # 하단 탭에 없는 바로가기만 둔다.
        st.markdown(
            '<div class="menu">'
            f'<a href="{_ask_href("어르신 건강·의료 지원 서비스를 알려주세요")}" target="_self">건강·의료</a>'
            f'<a href="{_ask_href("노인맞춤돌봄서비스가 뭐예요?")}" target="_self">어르신 돌봄</a>'
            f'<a href="{_nav_href("home")}#notices" target="_self">공지사항</a>'
            '</div>', unsafe_allow_html=True)
        uu = st.session_state.get("auth_user", "")
        hc1, hc2 = st.container(key="hdruser").columns([1.4, 1], vertical_alignment="center")
        hc1.markdown(f'<div style="text-align:right;color:#5c6b86;font-size:.9rem;'
                     f'font-weight:700">👤 {uu} 님</div>', unsafe_allow_html=True)
        if hc2.button("로그아웃", key="hdr_logout", use_container_width=True,
                      help="로그인 화면으로 돌아가 다른 계정으로 로그인합니다."):
            _confirm_logout()            # 바로 나가지 않고 한 번 더 확인
    st.markdown('</div>', unsafe_allow_html=True)


# 머리글 정리: 로고·검색·로그아웃 글자가 좁은 화면에서 '검'·'로그…'처럼 잘리거나
# 로고가 두 줄로 꺾이지 않게 한 줄 유지.
_HEADER_TIDY_CSS = """
<style>
  .brand{white-space:nowrap}
  .util .gov-wrap{justify-content:space-between !important}
  .util span{opacity:.9}
  [data-testid="stForm"] button p, .st-key-hdr_logout button p{white-space:nowrap}
  .st-key-hdr_logout button{min-width:88px}
  .menu{justify-content:flex-end; flex-wrap:nowrap}
  /* 폰: 검색창+검색 버튼, 이름+로그아웃을 각각 한 줄로(세로로 쌓여 화면 절반을 차지하던 것) */
  @media(max-width:640px){
    .st-key-hdrsearch [data-testid="stHorizontalBlock"],
    .st-key-hdruser[data-testid="stHorizontalBlock"], .st-key-hdruser [data-testid="stHorizontalBlock"]{
      flex-wrap:nowrap !important; gap:8px !important; align-items:center}
    .st-key-hdrsearch [data-testid="stColumn"], .st-key-hdruser [data-testid="stColumn"]{
      min-width:0 !important; width:auto !important}
    .st-key-hdrsearch [data-testid="stColumn"]:first-child,
    .st-key-hdruser [data-testid="stColumn"]:first-child{flex:1 1 auto !important}
    .st-key-hdrsearch [data-testid="stColumn"]:last-child,
    .st-key-hdruser [data-testid="stColumn"]:last-child{flex:0 0 96px !important}
  }
</style>
"""


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
      <h1>어르신, 무엇을 도와드릴까요?</h1>
      <p>{sub}</p>
    </div></div></div>
    """, unsafe_allow_html=True)


def home_screen(client):
    """홈 탭 — 환영 배너 + 빠른 질문(누르면 상담 탭에서 바로 답변) + 공지."""
    from urllib.parse import quote
    user = st.session_state.get("auth_user", "어르신")
    hero_banner(f"{user} 님, 궁금한 것을 아래에서 눌러 보세요.")
    st.markdown('<div class="gov-wrap sec" id="homebody">', unsafe_allow_html=True)
    st.markdown('<h2>자주 묻는 질문</h2>'
                '<p class="sub">누르시면 바로 답해 드려요.</p>', unsafe_allow_html=True)
    # (버튼에 보이는 짧은 이름, 누르면 AI상담에 보내는 질문) — 읽기 쉽게 짧은 이름만 보여 준다
    quicks = [("기초연금 신청", "기초연금 신청 방법 알려줘"),
              ("노인맞춤돌봄", "노인맞춤돌봄서비스가 뭐예요?"),
              ("치매안심센터", "치매안심센터는 어디서 이용하나요?"),
              ("무릎·관절 도움", "무릎이 아픈데 도움받을 곳이 있나요?"),
              ("경로당·복지관", "경로당·노인복지관 알려줘"),
              ("방문 건강관리", "방문 건강관리 신청하고 싶어요")]
    chips = "".join(
        f'<a class="chip" href="{_ask_href(q)}" target="_self">{label}</a>'
        for label, q in quicks)
    st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
    # 원하는 질문이 없을 때: 직접 물어볼 곳을 크게 안내(어르신이 다음 행동을 바로 알 수 있게)
    st.markdown(f'<a class="ask-own" href="{_nav_href("talk")}" target="_self">'
                '💬 다른 질문은 <b>여기를 눌러</b> 직접 물어보세요 ›</a>'
                '<style>a.ask-own{display:block; margin:18px 0 4px; padding:16px 18px;'
                'border-radius:16px; background:#1e3a8a; color:#fff !important;'
                'font-size:1.1rem; text-align:center; text-decoration:none !important}'
                'a.ask-own b{color:#fff}</style>', unsafe_allow_html=True)
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
    """업로드 파일 → (추출 텍스트, 오류메시지). 결과는 파일별로 캐시한다.

    - 사진: src/image_reader — Gemini vision(키 있을 때) → 서버 안 Ollama vision
      (qwen2.5vl) → OCR 순으로 '보고' 읽어 쉬운 설명을 만든다.
    - 문서(PDF·txt): OCR/텍스트 추출(on-device).
    추출된 내용은 질문의 근거(attach)로 쓰여 RAG 답변에 반영된다."""
    import os
    try:
        key = "ocr::" + str(getattr(up, "file_id", None) or up.name)
        if key in st.session_state:
            return st.session_state[key], None
        ext = os.path.splitext(up.name)[1].lower()
        from src.file_intake import IMAGE_EXTS
        if ext in IMAGE_EXTS:
            # 사진: Gemini vision(키 있을 때) → 서버 안 Ollama vision → OCR 순 자동 전환
            from src.image_reader import read_image
            with st.spinner("🔎 사진을 자세히 살펴보고 있습니다…"):
                text, engine = read_image(up.getvalue(), up.name)
            st.session_state["vision_engine::" + key] = engine
        else:
            from src.file_intake import extract_text_from_upload
            with st.spinner("🔎 문서에서 글자를 읽는 중입니다…"):
                text, _kind = extract_text_from_upload(up.name, up.getvalue())
        if not (text or "").strip():
            return None, ("사진에서 내용을 읽지 못했어요. 더 밝고 또렷하게, "
                          "글자가 크게 보이도록 다시 올려 주세요.")
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
                st.success(f"✅ '{up.name}' 분석이 끝났어요. 더 궁금한 점은 아래에 물어보세요.")
                st.markdown(attach_text[:3000])          # 접지 않고 바로 설명을 보여 준다
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
    # 어르신이 위아래로 스크롤하지 않도록: ① 입력창은 화면 아래에 고정
    # ② 질문하면 새 질문·답변 위치로 자동 이동 ③ 빠른 버튼은 접어 두기(대화 시작 전엔 펼침)
    st.markdown(_CHATBAR_CSS, unsafe_allow_html=True)
    hist_slot = st.container()     # 지난 대화(말풍선 + 출처 캡션) — 위
    live_slot = st.container()     # 새 답변이 토큰 단위로 스트리밍되는 자리
    has_chat = bool(st.session_state.get("chat"))
    with st.expander("💡 자주 묻는 질문 보기 — 눌러서 바로 물어보세요", expanded=not has_chat):
        quick_replies(client)      # 즉시 전송 칩(처음·서비스목록·온라인신청)
        quick_actions(client)      # 분야→질문 빠른 버튼
    attach_text, ask_file = chat_uploader()   # 📎 사진·문서 업로드(OCR)
    with st.container(key="chatbar"):          # 화면 아래 고정 입력창
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
            st.markdown('<div id="live-q"></div>', unsafe_allow_html=True)
            _scroll_to("#live-q")                  # 답변을 기다리는 동안 새 질문 위치로
            ask_and_stream(client, pending, attach=pending_attach)   # 스트리밍 + 출처 + 첨부근거
        st.session_state["scroll_last_q"] = True
        st.rerun()                            # 다음 런에서 지난 대화로 정착
    if st.session_state.pop("scroll_last_q", False):
        _scroll_to(".bub.user", last=True)    # 방금 한 질문(과 그 아래 답변)이 보이게
    st.markdown('</div>', unsafe_allow_html=True)


# AI상담 화면 전용: 입력창을 하단 탭 바로 위에 고정하고, 고정창에 가리지 않도록 아래 여백을 둔다.
_CHATBAR_CSS = """
<style>
  .st-key-chatbar{position:fixed; left:50%; transform:translateX(-50%); bottom:84px;
    width:min(1100px, calc(100% - 32px)); z-index:9998; background:#ffffff;
    border:2px solid #d9d4c7; border-radius:16px; padding:8px 10px 2px;
    box-shadow:0 8px 24px -10px rgba(16,35,61,.35)}
  .block-container{padding-bottom:190px !important}
  @media(max-width:640px){
    .st-key-chatbar{bottom:calc(58px + env(safe-area-inset-bottom)); width:calc(100% - 16px);
      border-radius:14px; padding:6px 8px 0}
    /* 폰에서도 입력창과 '보내기'를 한 줄에(세로로 쌓이면 화면을 너무 가림) */
    .st-key-chatbar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important; gap:6px !important}
    .st-key-chatbar [data-testid="stColumn"]{min-width:0 !important; width:auto !important}
    .st-key-chatbar [data-testid="stColumn"]:first-child{flex:1 1 auto !important}
    .st-key-chatbar [data-testid="stColumn"]:last-child{flex:0 0 84px !important}
    .block-container{padding-bottom:160px !important}
  }
</style>
"""


def _scroll_to(selector: str, last: bool = False):
    """부모 페이지에서 selector 위치로 부드럽게 스크롤(고정 입력창·상단 여백 고려)."""
    import json
    import time
    import streamlit.components.v1 as components
    pick = "els[els.length-1]" if last else "els[0]"
    # 매번 내용이 달라야 Streamlit 이 스크립트를 다시 실행한다(같으면 재사용되어 안 움직임)
    components.html(
        f"<!-- {time.time_ns()} -->"
        "<script>setTimeout(function(){try{var d=window.parent.document;"
        f"var els=d.querySelectorAll({json.dumps(selector)});if(!els.length)return;"
        f"var el={pick};el.scrollIntoView({{behavior:'smooth',block:'start'}});"
        "}catch(e){}},350);</script>", height=0)


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
    for i, (date, title, _body, _ask_q) in enumerate(NOTICES):
        new = '<span class="newtag">NEW</span>' if i == 0 else ""
        # 공지를 누르면 상세 내용 페이지로 이동(챗봇이 아니라 공지 상세)
        rows += (f'<a class="notice" href="{_notice_href(i)}" target="_self">'
                 f'<span class="date">{date}</span>'
                 f'<span class="t">{title}{new}</span>'
                 f'<span class="go" aria-label="자세히">›</span></a>')
    st.markdown('<div class="sec" id="notices"><div class="gov-wrap">'
                '<h2>공지사항</h2>'
                f'{rows}</div></div>', unsafe_allow_html=True)


def _sync_state(widget_key: str, state_key: str):
    """토글 위젯 값 → 앱 상태 키로 복사(on_change 콜백: rerun 전에 실행됨)."""
    st.session_state[state_key] = st.session_state[widget_key]


def footer():
    # 시연용 학생 프로젝트임을 분명히 하고(가짜 주소·전화번호 금지), 도움 전화는 실제 번호만.
    # 개인정보 문구는 '실제 설정'대로 표시한다(클라우드 답변·사진 이해를 켜면 외부 전송됨).
    import os
    external = (config.LLM_BACKEND != "ollama") or bool(os.environ.get("GEMINI_API_KEY"))
    privacy = ("답변 생성(또는 사진 이해)을 위해 질문 내용이 외부 AI 서비스로 전송될 수 있습니다. "
               "주민번호·계좌번호 같은 민감한 정보는 입력하지 마세요."
               if external else
               "질문과 답변은 이 서버 안의 AI 모델로 처리하며 외부 AI 서비스로 보내지 않습니다.")
    st.markdown(f"""
    <div class="foot"><div class="gov-wrap">
      <div class="cols">
        <div><b>대전노인복지HUB</b>학생 프로젝트 시연 서비스<br>
             (대전광역시 공식 서비스가 아닙니다)</div>
        <div><b>바로가기</b>기초연금 · 노인맞춤돌봄<br>치매안심센터 · 방문건강관리</div>
        <div><b>도움이 필요할 때</b>보건복지상담센터 129<br>자살예방 상담전화 109 · 응급 119 (24시간)</div>
        <div><b>자료 출처</b>보건복지부 · 대전광역시 공개 자료<br>정확한 내용은 주민센터에서 확인하세요</div>
      </div>
      <div class="copy">{privacy}
        © 2026 AI프로젝트2 8조 (시연용).</div>
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


def admin_screen():
    """관리자(사회복지사) 화면 — 모든 어르신의 이상신호를 DB 에서 읽어 모니터링한다.
    일반 어르신 계정에는 이 화면으로 가는 메뉴가 없다(관리자 계정으로 로그인해야 보임)."""
    import html as _html
    inject_css()
    st.markdown('<div class="gov-wrap sec">', unsafe_allow_html=True)
    h1, h2 = st.columns([5, 1], vertical_alignment="center")
    h1.markdown(f'<div style="color:#5c6b86;font-weight:700">👤 {_html.escape(st.session_state.get("auth_user", ""))} '
                '(관리자)</div>', unsafe_allow_html=True)
    if h2.button("로그아웃", key="admin_logout", use_container_width=True):
        _confirm_logout()
    from src.admin_monitor import render
    render(exclude=config.ADMIN_USERS)
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
    # Streamlit 세션은 reload 시 초기화되므로 URL 로 세션을 복원하되, 반드시 서명
    # 토큰(?t=)을 검증한다. ?u=성함 만으로는 복원하지 않아 계정 도용을 막는다.
    if not st.session_state.get("auth_user"):
        _u = st.query_params.get("u")
        _t = st.query_params.get("t")
        if _u and _verify_user_token(_u, _t):
            _load_user_session(_u)
        elif _u:
            # 서명 없는/위조된 ?u= 는 무시하고 URL 을 정리(로그인 화면으로).
            st.query_params.clear()
    # '로그인 상태 유지'를 체크했던 기기: 쿠키(성함|서명토큰, 30일)로 자동 로그인.
    # 같은 세션에서 로그아웃했다면(logged_out) 남은 쿠키로 다시 들어가지 않는다.
    if not st.session_state.get("auth_user") and not st.session_state.get("logged_out"):
        _c = _read_login_cookie()
        if _c and not config.is_admin(_c[0]) and _verify_user_token(*_c):
            _load_user_session(_c[0])
            _set_login_params(_c[0])
    if st.session_state.pop("clear_login_cookie", False):
        _write_login_cookie(None)                  # 로그아웃 → 저장된 로그인 지우기
    if st.session_state.get("auth_user") and st.session_state.get("set_login_cookie"):
        _write_login_cookie(st.session_state.pop("set_login_cookie"))

    # 접속 흐름: 로그인 → 내 정보 입력 → (이후) 포털 화면.
    # 로그인·내 정보는 무거운 어시스턴트가 필요 없으므로 바로 뜬다.
    if not st.session_state.get("auth_user"):
        login_screen()
        return
    if st.session_state.get("is_admin"):
        admin_screen()               # 관리자(사회복지사) 계정 → 전체 어르신 이상신호 모니터
        return
    if not st.session_state.get("profile_done"):
        profile_screen()
        return

    # 포털부터 어시스턴트 필요 — 지연 로딩(화면은 먼저 뜨고, 첫 질문에서만 준비).
    client = _LazyClient()

    # 상단 메뉴 링크: ?u=<성함>&tab=<탭> → 그 탭으로 이동(u 는 유지).
    if "tab" in st.query_params:
        t = st.query_params["tab"]
        try:
            del st.query_params["tab"]
        except Exception:
            pass
        if t in _TABS:
            st.session_state["tab"] = t
            st.session_state.pop("mode", None)          # 음성 모드였으면 일반 화면으로

    # A category card links to ?u=<성함>&ask=<question>; handle ask, keep u(로그인).
    if "ask" in st.query_params:
        q = st.query_params["ask"]
        try:
            del st.query_params["ask"]      # ask 만 제거, ?u=(로그인)는 유지
        except Exception:
            pass
        if q.strip():
            st.session_state["pending_q"] = q.strip()   # 상담 탭에서 스트리밍으로 답변
            st.session_state["tab"] = "talk"   # 질문하면 상담 화면으로 전환

    # 공지사항 상세 보기: ?notice=<번호> → 상세 화면(챗봇 아님)
    if "notice" in st.query_params:
        try:
            st.session_state["notice"] = int(st.query_params["notice"])
        except (TypeError, ValueError):
            pass
        try:
            del st.query_params["notice"]
        except Exception:
            pass

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
        # on_change 콜백은 다음 실행(rerun) '전에' 값을 반영한다 → 화면 맨 위 inject_css 가
        # 바뀐 값을 바로 본다(예전엔 한 박자 늦어 고대비를 끌 때 두 번 눌러야 했음).
        st.toggle("고대비 모드", value=st.session_state.get("high_contrast", False),
                  key="hc_toggle", on_change=_sync_state, args=("hc_toggle", "high_contrast"))
        st.toggle(
            "음성으로 답변 듣기", value=st.session_state.get("voice_mode", False),
            key="voice_toggle", on_change=_sync_state, args=("voice_toggle", "voice_mode"),
            help=f"로컬 TTS: {get_tts().backend or '사용 불가'}")
        st.divider()
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
            _confirm_logout()            # 바로 나가지 않고 한 번 더 확인

    inject_css()
    inject_pwa()

    if st.session_state.get("mode") == "voice":
        header_nav(client)
        voice_conversation(client)   # hands-free ChatGPT-style voice loop
    else:
        header_nav(client)
        tab = st.session_state.get("tab", "home")
        bottom_tab_bar(tab)      # 폰 하단 탭바(홈·맞춤복지·AI상담·서비스) — 블로킹 전에

        if st.session_state.get("notice") is not None:
            notice_detail(client, st.session_state["notice"])   # 공지 상세(챗봇 아님)
            footer()
        elif tab == "mywelfare":
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
