"""
대전노인복지 HUB — 사람 맞춤형 통합 웹앱 (로그인 → 프로필 → 맞춤 상담).

일반 챗봇은 누구에게나 같은 일반 정보를 주지만, 이 앱은 어르신이 '내 계정'에
자기 정보를 넣어두면, 로그인하는 순간 '당신이 받을 수 있는 복지'를 알려주고,
이어지는 대화도 그 어르신의 나이·소득·거주지에 맞춰 답한다.

세 가지를 하나로 합쳤다:
  1) 계정(이름 기반, 프로토타입)         — 어르신별 프로필 저장
  2) 자격 매칭(src.welfare_rules)        — 받을 수 있는 복지 자동 추천
  3) RAG 상담(rag_lecture) + 프로필 주입  — 그 사람 상황에 맞춘 문서 근거 답변

설치·실행:
  pip install fastapi uvicorn
  python3 -m uvicorn app_personal:app --host 0.0.0.0 --port 8002
  브라우저:  http://localhost:8002

※ 프로토타입이라 비밀번호 없이 이름만으로 계정을 구분한다. 실제 서비스에서는
  본인 동의·인증·암호화가 필요하다(개인정보). 프로필은 data/profiles.json에
  로컬 저장하며 git에 커밋하지 않는다.
"""
from __future__ import annotations
import json
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.welfare_rules import Profile, recommend
from src import db   # 저장소 계층(MySQL 또는 파일 폴백)

app = FastAPI(title="대전노인복지 HUB — 맞춤 상담")

HERE = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_K = int(os.environ.get("RAG_EVIDENCE_K", "3"))
EVIDENCE_MIN_SIM = float(os.environ.get("RAG_EVIDENCE_MIN_SIM", "0.62"))


# ── RAG(rag_lecture/ask.py) 지연 로드 ──────────────────────────────
_RAG = None
_RAG_TRIED = False


def _get_rag():
    global _RAG, _RAG_TRIED
    if _RAG_TRIED:
        return _RAG
    _RAG_TRIED = True
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            "rag_lecture_ask", os.path.join(HERE, "rag_lecture", "ask.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _RAG = mod
    except Exception:                      # noqa: BLE001
        _RAG = None
    return _RAG


def _profile_from(d: dict) -> Profile:
    return Profile(
        age=d.get("age"), income_low=d.get("income_low"),
        district=d.get("district"), living_alone=d.get("living_alone"),
        mobility_issue=d.get("mobility_issue"), chronic_illness=d.get("chronic_illness"))


def _profile_text(d: dict) -> str:
    """프롬프트에 넣을 어르신 정보 한 줄 요약."""
    def yn(v):
        return "예" if v is True else ("아니오" if v is False else "모름")
    parts = []
    if d.get("age") is not None:
        parts.append(f"나이 {d['age']}세")
    if d.get("district"):
        parts.append(f"대전 {d['district']} 거주")
    parts.append(f"저소득 {yn(d.get('income_low'))}")
    parts.append(f"독거 {yn(d.get('living_alone'))}")
    parts.append(f"거동불편 {yn(d.get('mobility_issue'))}")
    parts.append(f"만성질환 {yn(d.get('chronic_illness'))}")
    return ", ".join(parts)


def _eligible_names(d: dict):
    eligible, _, _ = recommend(_profile_from(d))
    return [r.welfare.name for r in eligible]


# ── API 모델 ────────────────────────────────────────────────────────
class LoginIn(BaseModel):
    name: str


class ProfileIn(BaseModel):
    name: str
    age: int | None = None
    income_low: bool | None = None
    district: str | None = None
    living_alone: bool | None = None
    mobility_issue: bool | None = None
    chronic_illness: bool | None = None


class ChatIn(BaseModel):
    name: str
    question: str


@app.post("/login")
def login(inp: LoginIn):
    """이름으로 계정을 찾는다(없으면 신규)."""
    name = (inp.name or "").strip()
    if not name:
        return {"ok": False, "msg": "성함을 입력해 주세요."}
    prof = db.get_profile(name)
    return {"ok": True, "name": name, "profile": prof, "is_new": prof is None,
            "history": db.list_chats(name, limit=10)}


@app.post("/profile")
def save_profile(p: ProfileIn):
    """어르신 프로필 저장 + 받을 수 있는 복지 추천."""
    name = (p.name or "").strip()
    if not name:
        return {"ok": False, "msg": "성함을 입력해 주세요."}
    d = p.model_dump()
    d.pop("name")
    db.save_profile(name, d)
    return {"ok": True, "eligible": _eligible_names(d), "summary": _profile_text(d)}


@app.post("/chat")
def chat(c: ChatIn):
    """어르신 프로필을 반영한 RAG 상담."""
    name = (c.name or "").strip()
    q = (c.question or "").strip()
    if not q:
        return {"answer": "궁금한 점을 입력해 주세요.", "sources": []}
    d = db.get_profile(name) or {}
    rag = _get_rag()
    if rag is None:
        return {"answer": "(상담 엔진이 준비되지 않았습니다 — 인덱스/Ollama 확인)",
                "sources": []}
    try:
        hits = rag.search(q, k=EVIDENCE_K)
        ctx = "\n\n".join(h[0] for h in hits)
        prof_line = _profile_text(d) if d else "정보 없음"
        elig = ", ".join(_eligible_names(d)) if d else ""
        prompt = (
            "당신은 대전 독거노인 복지 상담사입니다. 아래 [어르신 정보]와 [자료]만 "
            "근거로 한국어로 짧고 공손하게 답하세요. 어르신의 나이·소득·거주지 상황에 "
            "맞춰 안내하고, 자료에 없으면 '자료에 없습니다. 가까운 주민센터에 "
            "문의하세요'라고 답하세요.\n\n"
            f"[어르신 정보] {prof_line}\n"
            f"[규칙상 받을 수 있는 복지] {elig or '정보 부족'}\n\n"
            f"[자료]\n{ctx}\n\n[질문] {q}")
        import requests
        r = requests.post(rag.OLLAMA + "/api/generate",
                          json={"model": rag.CHAT_MODEL, "prompt": prompt,
                                "stream": False}, timeout=120)
        r.raise_for_status()
        answer = r.json().get("response", "").strip()
    except Exception as e:                 # noqa: BLE001
        return {"answer": f"(오류: {e}) Ollama 실행 여부를 확인하세요.", "sources": []}
    srcs = [{"source": s, "score": round(sim, 3)} for _, s, sim in hits
            if sim >= EVIDENCE_MIN_SIM]
    if name:
        try:
            db.save_chat(name, q, answer, srcs)   # 대화 기록 저장(관계형 DB)
        except Exception:                          # noqa: BLE001
            pass
    return {"answer": answer, "sources": srcs}


@app.get("/history/{name}")
def history(name: str):
    """사용자의 최근 대화 기록."""
    return {"history": db.list_chats(name.strip(), limit=20)}


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>대전노인복지 HUB</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>
  :root{--navy:#0f2f6f;--navy2:#0a2350;--accent:#2f6bff;--ink:#15233d;--muted:#5c6b86;
        --bg:#eef2f9;--surface:#fff;--surface2:#f5f8fd;--line:#e6ebf4;--ok:#1f7a43;--okbg:#eaf2e9}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:'Pretendard','Pretendard Variable',-apple-system,'Noto Sans KR',sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:860px;margin:0 auto;padding:0 20px}
  /* 상단 유틸 바 */
  .util{background:var(--navy2);color:#c7d4ee;font-size:12.5px}
  .util .wrap{display:flex;justify-content:flex-end;gap:20px;padding:8px 20px}
  .util span{opacity:.85}
  /* 헤더 */
  .gnav{background:rgba(255,255,255,.92);backdrop-filter:saturate(1.4) blur(8px);
    border-bottom:1px solid var(--line);position:sticky;top:0;z-index:50}
  .gnav .row{display:flex;align-items:center;gap:13px;padding:15px 20px;max-width:860px;margin:0 auto}
  .seal{width:42px;height:42px;border-radius:13px;background:linear-gradient(140deg,var(--accent),var(--navy));
    color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;
    box-shadow:0 6px 16px -4px rgba(47,107,255,.4)}
  .brand b{font-size:21px;font-weight:800;color:var(--navy);letter-spacing:-.03em}
  .brand small{display:block;font-size:12px;color:var(--muted);font-weight:600;margin-top:1px}
  /* 히어로 배너 */
  .hero{color:#fff;padding:30px 0;
    background:linear-gradient(90deg,var(--navy2) 0%,var(--navy) 55%,rgba(15,47,111,.55) 100%)}
  .hero .eyebrow{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.12em;
    text-transform:uppercase;color:#e2ecff;background:#ffffff2b;padding:5px 13px;border-radius:999px;margin-bottom:10px}
  .hero h1{font-size:30px;font-weight:800;margin:0 0 6px;letter-spacing:-.03em;line-height:1.18}
  .hero p{font-size:16px;color:#eaf1ff;margin:0;line-height:1.5}
  main{padding:26px 0 48px}
  /* 카드 */
  .card{background:var(--surface);border:1px solid var(--line);border-radius:22px;
    padding:26px;margin-bottom:18px;box-shadow:0 18px 40px -26px rgba(15,47,111,.35)}
  .step{display:inline-block;font-size:12.5px;font-weight:800;color:var(--accent);
    background:var(--surface2);padding:5px 12px;border-radius:999px;margin-bottom:16px;letter-spacing:-.01em}
  label{display:block;font-size:13.5px;font-weight:700;margin:12px 0 6px;color:var(--ink)}
  input,select{width:100%;border:1.5px solid var(--line);border-radius:12px;padding:12px 14px;
    font-size:16px;outline:none;background:var(--surface);color:var(--ink);transition:border-color .15s,box-shadow .15s}
  input:focus,select:focus{border-color:var(--navy);box-shadow:0 0 0 3px rgba(47,107,255,.18)}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  .btn{width:100%;margin-top:18px;border:0;border-radius:14px;color:#fff;font-size:16.5px;font-weight:800;
    padding:14px;cursor:pointer;background:linear-gradient(135deg,var(--accent),var(--navy));
    box-shadow:0 14px 28px -12px rgba(47,107,255,.55);transition:transform .16s,box-shadow .16s}
  .btn:hover{transform:translateY(-2px);box-shadow:0 20px 36px -12px rgba(47,107,255,.65)}
  .btn:disabled{background:#aebfd8;box-shadow:none;transform:none}
  .hide{display:none}
  /* 받을 수 있는 복지 패널 */
  .elig{background:var(--okbg);border:1px solid #cadfc7;border-left:5px solid var(--ok);
    border-radius:14px;padding:16px 18px;margin:4px 0 14px;font-size:15px;line-height:1.55}
  .elig b{color:var(--ok)}
  /* 채팅 */
  #chat{display:flex;flex-direction:column;gap:12px;min-height:200px;max-height:48vh;overflow-y:auto;padding:4px}
  .row{display:flex;gap:9px;max-width:88%}
  .row.me{align-self:flex-end;flex-direction:row-reverse}
  .av{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;
    background:var(--surface2);border:1px solid var(--line);font-size:17px;flex:none}
  .row.me .av{background:linear-gradient(135deg,var(--accent),var(--navy));border:0}
  .bub{padding:12px 16px;border-radius:18px;font-size:15.5px;line-height:1.55;white-space:pre-wrap;
    box-shadow:0 1px 3px rgba(15,47,111,.07)}
  .bot .bub{background:var(--surface);border:1px solid var(--line);border-bottom-left-radius:6px}
  .me .bub{background:linear-gradient(135deg,var(--accent),var(--navy));color:#fff;border-bottom-right-radius:6px}
  .src{margin-top:6px;font-size:12px;color:var(--muted)}
  .inrow{display:flex;gap:9px;margin-top:14px}
  #q{flex:1;border:1.5px solid var(--line);border-radius:22px;padding:12px 16px;font-size:16px;outline:none}
  #q:focus{border-color:var(--navy);box-shadow:0 0 0 3px rgba(47,107,255,.18)}
  #send{width:50px;border:0;border-radius:50%;color:#fff;font-size:20px;cursor:pointer;
    background:linear-gradient(135deg,var(--accent),var(--navy))}
  .note{font-size:12.5px;color:var(--muted);margin-top:12px;line-height:1.5}
  .link{color:var(--accent);font-weight:700;cursor:pointer;font-size:13px;margin-left:6px}
  @media(max-width:560px){.grid{grid-template-columns:1fr}.hero h1{font-size:24px}}
</style></head><body>

<div class="util"><div class="wrap"><span>로그인</span><span>회원가입</span><span>사이트맵</span><span>English</span></div></div>
<div class="gnav"><div class="row">
  <div class="seal">🏠</div>
  <div class="brand"><b>대전노인복지 HUB</b><small>대전광역시 · 어르신 복지 AI</small></div>
</div></div>
<div class="hero"><div class="wrap">
  <span class="eyebrow">맞춤형 복지 안내</span>
  <h1>어르신, 받으실 수 있는 복지를 찾아드립니다</h1>
  <p>내 정보를 넣으면 나에게 맞는 복지를 알려주고, 공공문서 근거로 상담해 드립니다.</p>
</div></div>

<main><div class="wrap">

  <!-- STEP 1: 로그인 -->
  <div class="card" id="c1">
    <div class="step">1단계 · 로그인</div>
    <label>성함 (계정)</label>
    <input id="name" placeholder="예: 홍길동" autocomplete="off">
    <button class="btn" id="loginBtn">시작하기</button>
    <div class="note">※ 프로토타입이라 성함만으로 구분합니다. 실제 서비스에서는 본인 인증·동의가 필요합니다.</div>
  </div>

  <!-- STEP 2: 프로필 -->
  <div class="card hide" id="c2">
    <div class="step">2단계 · 내 정보</div>
    <div class="grid">
      <div><label>나이 (만)</label><input id="age" type="number" min="0" placeholder="예: 72"></div>
      <div><label>거주 구</label><select id="district">
        <option value="">선택 안 함</option><option>동구</option><option>중구</option>
        <option>서구</option><option>유성구</option><option>대덕구</option></select></div>
      <div><label>저소득</label><select id="income_low">
        <option value="">모름</option><option value="true">예</option><option value="false">아니오</option></select></div>
      <div><label>독거</label><select id="living_alone">
        <option value="">모름</option><option value="true">예</option><option value="false">아니오</option></select></div>
      <div><label>거동 불편</label><select id="mobility_issue">
        <option value="">모름</option><option value="true">예</option><option value="false">아니오</option></select></div>
      <div><label>만성질환·기억력 저하</label><select id="chronic_illness">
        <option value="">모름</option><option value="true">예</option><option value="false">아니오</option></select></div>
    </div>
    <button class="btn" id="saveBtn">저장하고 상담 시작</button>
  </div>

  <!-- STEP 3: 상담 -->
  <div class="card hide" id="c3">
    <div class="step">3단계 · 맞춤 상담 <span class="link" id="editLink">[내 정보 수정]</span></div>
    <div id="eligBox"></div>
    <div id="chat"></div>
    <div class="inrow">
      <input id="q" placeholder="궁금한 복지를 물어보세요…" autocomplete="off">
      <button id="send">➤</button>
    </div>
    <div class="note">답변은 어르신 정보와 대전 공공문서 근거를 함께 반영합니다.</div>
  </div>

</div></main>
<script>
const $=id=>document.getElementById(id);
let USER=null;
function triv(v){return v===''?null:(v==='true');}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function show(step){ for(const i of [1,2,3]) $('c'+i).classList.toggle('hide', i!==step); }

async function post(url,body){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return r.json();
}

// STEP 1
$('loginBtn').onclick=async()=>{
  const name=$('name').value.trim(); if(!name){alert('성함을 입력해 주세요.');return;}
  const d=await post('/login',{name});
  if(!d.ok){alert(d.msg);return;}
  USER=d.name;
  if(d.profile){ // 기존 회원 → 프로필 채우고 바로 상담
    const p=d.profile;
    $('age').value=p.age??''; $('district').value=p.district||'';
    $('income_low').value=p.income_low===null?'':String(p.income_low);
    $('living_alone').value=p.living_alone===null?'':String(p.living_alone);
    $('mobility_issue').value=p.mobility_issue===null?'':String(p.mobility_issue);
    $('chronic_illness').value=p.chronic_illness===null?'':String(p.chronic_illness);
  }
  show(2);
};

// STEP 2
$('saveBtn').onclick=async()=>{
  const ageV=$('age').value.trim();
  const body={name:USER, age: ageV===''?null:parseInt(ageV,10),
    district:$('district').value||null, income_low:triv($('income_low').value),
    living_alone:triv($('living_alone').value), mobility_issue:triv($('mobility_issue').value),
    chronic_illness:triv($('chronic_illness').value)};
  const d=await post('/profile',body);
  if(!d.ok){alert(d.msg);return;}
  const names=d.eligible||[];
  $('eligBox').innerHTML='<div class="elig"><b>'+esc(USER)+'</b> 님, 받으실 수 있는 복지는 <b>'
    +(names.length?esc(names.join(', ')):'추가 정보 필요')+'</b> 입니다.<br>'
    +'<span style="font-size:12.5px;color:#5b6b86">'+esc(d.summary||'')+'</span></div>';
  $('chat').innerHTML='';
  addBot('안녕하세요, '+USER+' 님. 위 복지에 대해 더 궁금하신 점을 물어보세요. 😊');
  show(3);
};
$('editLink').onclick=()=>show(2);

// STEP 3 chat
function addRow(who){
  const r=document.createElement('div');r.className='row '+who;
  const a=document.createElement('div');a.className='av';a.textContent=who==='me'?'🙂':'🤖';
  const w=document.createElement('div');const b=document.createElement('div');b.className='bub';
  w.appendChild(b);r.append(a,w);$('chat').appendChild(r);$('chat').scrollTop=$('chat').scrollHeight;
  return {b,w};
}
function addBot(t){const {b}=addRow('bot');b.textContent=t;}
async function ask(){
  const t=$('q').value.trim(); if(!t)return; $('q').value='';
  addRow('me').b.textContent=t;
  const {b,w}=addRow('bot'); b.textContent='…';
  try{
    const d=await post('/chat',{name:USER,question:t});
    b.textContent=d.answer||'(답변 없음)';
    if(d.sources&&d.sources.length){
      const s=document.createElement('div');s.className='src';
      s.textContent='📄 근거: '+d.sources.map(x=>x.source+' ['+x.score+']').join(', ');
      w.appendChild(s);
    }
  }catch(e){b.textContent='오류가 발생했습니다.';}
  $('chat').scrollTop=$('chat').scrollHeight;
}
$('send').onclick=ask;
$('q').addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE
