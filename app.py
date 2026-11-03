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
          } catch (e) { /* cross-origin or restricted: silently skip */ }
        })();
        </script>
        """,
        height=0,
    )


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
    st.session_state["chat"].append(("bot", r["answer"], audio))
    st.session_state["latest_audio"] = audio
    if r.get("alert"):
        urgency = "긴급" if r.get("crisis") else "주의"
        st.session_state["alerts"].insert(0, (urgency, r["alert"]))
    st.session_state["state"] = r


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
        st.session_state["auth_user"] = name
        try:
            prof = db.get_profile(name)
            if prof:
                st.session_state["profile"] = prof
                st.session_state["profile_done"] = True
        except Exception:
            pass
        # 지난 대화 기록을 불러와 이어서 보여준다(대화 기억).
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
            f'<a class="cat-card" style="--c:{c}" href="?ask={quote(ask_q)}" target="_self">'
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
        '<div class="sec"><div class="gov-wrap">'
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
            ask_text(client, q.strip()); st.rerun()
    n.markdown('<div class="menu"><span>복지서비스</span><span>건강·의료</span>'
               '<span>어르신 돌봄</span><span>공지사항</span><span>상담·문의</span></div>',
               unsafe_allow_html=True)
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
        st.info("음성 대화 기능: pip install streamlit-webrtc webrtcvad 'setuptools<81'")
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
        import html as _html
        rows = ""
        for m in st.session_state["chat"][-8:]:
            side, who = ("r", "user") if m[0] == "user" else ("l", "bot")
            rows += (f'<div class="row {side}"><div class="bub {who}">'
                     f'{_html.escape(m[1])}</div></div>')
        chat_ph.markdown(f'<div class="chat">{rows}</div>', unsafe_allow_html=True)

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
        st.session_state["chat"].append(("bot", r["answer"], None))
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


def hero(client):
    art = ('<div class="hero-art"><svg viewBox="0 0 220 220" fill="none" '
           'stroke="#ffffff" stroke-opacity=".55" stroke-width="2">'
           '<circle cx="150" cy="90" r="70"/><circle cx="150" cy="90" r="48"/>'
           '<circle cx="150" cy="90" r="26"/>'
           '<path d="M40 150c30-10 60-10 90 0" stroke-opacity=".35"/>'
           '<path d="M30 170c40-14 90-14 130 0" stroke-opacity=".25"/></svg></div>')
    st.markdown(f"""
    <div class="hero"><div class="gov-wrap"><div class="hero-inner">
      {art}
      <span class="eyebrow">대전광역시 · 어르신 복지</span>
      <h1>어르신, 무엇을 도와드릴까요?</h1>
      <p>말씀하거나 입력하시면 복지 서비스를 쉽게 안내해 드립니다. 모든 상담은 안전하게 보호됩니다.</p>
    </div></div></div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="gov-wrap sec">', unsafe_allow_html=True)
    st.markdown('<div class="ai-head">음성·문자 복지 상담 (AI 도우미)</div>',
                unsafe_allow_html=True)
    st.session_state["use_rag"] = True   # 항상 RAG 사용(문서 근거)
    orb_slot = st.container()          # voice orb sits here (top), filled last
    # text input (renders before the blocking voice loop, so it always shows)
    with st.form("ai_text", clear_on_submit=True):
        tc1, tc2 = st.columns([5, 1])
        q = tc1.text_input("입력", placeholder="궁금하신 내용을 글로 입력하셔도 됩니다",
                           label_visibility="collapsed")
        go = tc2.form_submit_button("보내기", use_container_width=True)
    if go and q.strip():
        ask_text(client, q.strip()); st.rerun()
    with orb_slot:
        voice_orb(client)
    st.markdown('</div>', unsafe_allow_html=True)


def category_cards(client):
    from urllib.parse import quote
    cards = ""
    for name, desc, color, icon, q in CATEGORIES:
        cards += (
            f'<a class="cat-card" style="--c:{color}" href="?ask={quote(q)}" target="_self">'
            f'<span class="cat-ic">{ICONS[icon]}</span>'
            f'<span class="cat-name">{name}</span>'
            f'<span class="cat-desc">{desc}</span>'
            f'<span class="arw">→</span></a>')
    st.markdown('<div class="sec alt"><div class="gov-wrap">'
                '<h2>복지 서비스 바로가기</h2>'
                '<p class="sub">필요하신 서비스를 선택하시면 AI 도우미가 안내해 드립니다.</p>'
                f'<div class="cat-grid">{cards}</div>'
                '</div></div>', unsafe_allow_html=True)


def popular_and_notices():
    st.markdown('<div class="sec"><div class="gov-wrap">', unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown('<h2>자주 찾는 서비스</h2><p class="sub">많이 이용하시는 서비스입니다.</p>',
                    unsafe_allow_html=True)
        chips = "".join(f'<span class="chip">{p}</span>' for p in POPULAR)
        st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<h2>공지사항</h2><p class="sub">복지 관련 최신 소식입니다.</p>',
                    unsafe_allow_html=True)
        rows = ""
        for i, (date, title) in enumerate(NOTICES):
            new = '<span class="newtag">NEW</span>' if i == 0 else ""
            rows += (f'<div class="notice"><span class="date">{date}</span>'
                     f'<span class="t">{title}{new}</span></div>')
        st.markdown(rows, unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)


def footer():
    st.markdown("""
    <div class="foot"><div class="gov-wrap">
      <div class="cols">
        <div><b>대전노인복지HUB</b>대전광역시 서구 둔산로 100<br>
             노인복지과 042-000-0000</div>
        <div><b>바로가기</b>기초연금 · 노인맞춤돌봄<br>치매안심센터 · 방문건강관리</div>
        <div><b>상담전화</b>복지상담 129<br>자살예방상담 109 (24시간)</div>
        <div><b>이용안내</b>개인정보처리방침<br>웹 접근성 안내 · 이용약관</div>
      </div>
      <div class="copy">본 서비스는 모든 처리를 기기 내에서 수행하며 대화 내용을 외부로 전송하지 않습니다.
        © 2026 Daejeon Welfare Portal (demo).</div>
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
    st.markdown('<h2>관리자 · 이상신호 모니터</h2>'
                '<p class="sub">어르신 화면에는 보이지 않는 배경 모니터링입니다.</p>',
                unsafe_allow_html=True)
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

    # A category card links to ?ask=<question>; handle it, then clear the param.
    if "ask" in st.query_params:
        q = st.query_params["ask"]
        st.query_params.clear()
        if q.strip():
            ask_text(client, q.strip())

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
            for k in ("auth_user", "profile", "profile_done"):
                st.session_state.pop(k, None)
            st.rerun()

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
        # Container ordering: the hero holds a blocking voice loop, so render the
        # sections BELOW it first (into a later container), then fill the hero.
        hero_c = st.container()
        lower_c = st.container()
        with lower_c:
            my_welfare_cards()   # 내 맞춤 복지(카드) — 프로필 기반 추천
            category_cards(client)
            popular_and_notices()
            footer()
        with hero_c:
            hero(client)


if __name__ != "__mp_main__":
    main()
