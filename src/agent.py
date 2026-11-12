"""
Phase 1: a bounded, local tool-calling agent (experimental).

The deterministic pipeline (src/pipeline.py) runs a fixed sequence
    route -> retrieve -> rerank -> gate -> answer.
This agent instead lets the LLM *decide* what to do: on each step it picks a
tool, sees the result, and repeats up to AGENT_MAX_STEPS before answering. It
is deliberately kept safe for an on-device welfare setting:

  * Local only        - same Ollama model, no cloud (privacy preserved).
  * Bounded loop      - at most AGENT_MAX_STEPS tool calls (latency + safety).
  * Whitelisted tools - the model can only call the tools registered below.
  * Relevance gate    - if no tool ever finds relevant evidence, it refers the
                        user to the 주민센터 instead of making something up.
  * Graceful fallback - greetings, clearly off-domain questions, a missing LLM,
                        or any invalid tool call fall back to the proven
                        deterministic pipeline, so behaviour never gets worse.

This is Phase 1 of the agentic roadmap (Phase 2: multi-intent planner,
Phase 3: task agents that draft applications / send alerts on confirmation).
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from . import config
from .llm import (ANSWER_SYSTEM_PROMPT, OFF_DOMAIN_REPLY, build_answer_prompt,
                  clean_answer)
from .pipeline import TurnResult, WelfareAssistant
from .router import is_off_domain, is_smalltalk


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
@dataclass
class ToolResult:
    text: str                 # observation shown back to the agent
    sources: List[str]        # document sources gathered (for citation)
    max_score: float = 0.0    # best retrieval score seen (for the gate)


@dataclass
class Tool:
    name: str
    description: str
    args: str                 # human-readable arg spec for the prompt
    run: Callable[..., ToolResult]


class WelfareAgent:
    """A bounded tool-calling wrapper around WelfareAssistant."""

    def __init__(self, assistant: WelfareAssistant | None = None,
                 max_steps: int = config.AGENT_MAX_STEPS,
                 mode: str = "planner"):
        self.bot = assistant or WelfareAssistant()
        self.max_steps = max_steps
        self.max_subintents = config.AGENT_MAX_SUBINTENTS
        self.mode = mode                 # "planner" (Phase 2) or "react" (Phase 1)
        self.model = config.AGENT_MODEL
        self.tools: Dict[str, Tool] = self._build_tools()

    # -- tool registry -----------------------------------------------------
    def _build_tools(self) -> Dict[str, Tool]:
        tools = [
            Tool("search_welfare_docs",
                 "복지 제도·서비스 내용을 문서에서 검색합니다 (기초연금·돌봄·급식 등).",
                 '{"query": "검색어"}',
                 self._t_search),
            Tool("lookup_facility",
                 "대전 자치구별 시설·서비스 현황을 찾습니다 (식사배달·복지관·경로당 등).",
                 '{"district": "구 이름(선택)", "service_type": "시설/서비스 유형"}',
                 self._t_facility),
        ]
        return {t.name: t for t in tools}

    def _t_search(self, query: str = "", **_) -> ToolResult:
        hits = self.bot.rag.retrieve(str(query))
        return self._pack(hits)

    def _t_facility(self, district: str = "", service_type: str = "", **_) -> ToolResult:
        # Structured facility data is indexed as text, so a targeted query
        # retrieves the matching rows. Combine district + type into the query.
        q = " ".join(x for x in (str(district), str(service_type), "현황") if x.strip())
        hits = self.bot.rag.retrieve(q)
        return self._pack(hits)

    @staticmethod
    def _pack(hits) -> ToolResult:
        if not hits:
            return ToolResult("검색 결과가 없습니다.", [], 0.0)
        top = hits[0].score
        lines, sources = [], []
        for h in hits:
            lines.append(f"({h.source}) {h.text[:300]}")
            if h.source not in sources:
                sources.append(h.source)
        return ToolResult("\n".join(lines), sources, top)

    # -- main entry --------------------------------------------------------
    def ask(self, question: str, verbose: bool = False) -> TurnResult:
        # Small talk / off-domain / no local LLM -> proven deterministic path
        # (it also records the abnormal signal and dispatches alerts).
        if (not self.bot.llm.available or is_smalltalk(question)
                or is_off_domain(question)):
            if verbose:
                print("   ⟳ [route] 스몰토크/off-domain/LLM 없음 → 결정형 파이프라인")
            return self.bot.ask_text(question)

        # Welfare question -> run the agent. Record the signal once here.
        signal = self.bot.detector.add_utterance(question)
        try:
            if self.mode == "planner":         # Phase 2: decompose -> gather -> answer
                answer, sources = self._plan_and_answer(question, verbose=verbose)
            else:                              # Phase 1: ReAct tool loop
                answer, sources = self._run_loop(question, verbose=verbose)
        except Exception as exc:               # never fail worse than the pipeline
            print(f"[agent] {self.mode} error ({exc.__class__.__name__}); using pipeline.")
            answer, sources = self._rag_answer(question)
        if answer is None:                     # agent gave up -> deterministic RAG
            if verbose:
                print("   ⟳ [fallback] 유효한 결과 없음 → 결정형 RAG")
            answer, sources = self._rag_answer(question)
        return TurnResult(question, answer, sources, signal,
                          self.bot._maybe_alert(signal))

    # Drop-in compatibility with the eval harness / app (which call ask_text).
    def ask_text(self, question: str) -> TurnResult:
        return self.ask(question)

    def run_welfare(self, question: str) -> Tuple[str, List[str]]:
        """Answer a welfare question with the planner/tool loop, falling back to
        the deterministic RAG path on any failure. Returns (answer, sources).

        Called by WelfareAssistant.ask_text for welfare turns; routing, signal
        and alert handling stay there, so this never calls back into ask_text
        (no recursion)."""
        try:
            if self.mode == "planner":
                answer, sources = self._plan_and_answer(question)
            else:
                answer, sources = self._run_loop(question)
        except Exception as exc:               # never fail worse than the pipeline
            print(f"[agent] {self.mode} error ({exc.__class__.__name__}); using pipeline.")
            return self._rag_answer(question)
        if answer is None:                     # agent gave up -> deterministic RAG
            return self._rag_answer(question)
        return answer, sources

    def reset_conversation(self) -> None:
        self.bot.reset_conversation()

    # -- the ReAct-style loop ---------------------------------------------
    def _run_loop(self, question: str,
                  verbose: bool = False) -> Tuple[str | None, List[str]]:
        scratch: List[str] = []
        gathered: List[str] = []
        sources: List[str] = []
        seen_calls: set = set()
        best_score = 0.0

        for step in range(self.max_steps):
            action = self._decide(question, scratch)
            if action is None:                 # unparseable -> bail to fallback
                if verbose:
                    print(f"   ⟳ [step {step+1}] JSON tool-call 파싱 실패")
                return None, []
            if "answer" in action:
                if verbose:
                    print(f"   ⟳ [step {step+1}] 최종 답변 결정 "
                          f"(수집 근거 {len(gathered)}개, 최고점수 {best_score:.2f})")
                # Gate: don't let the agent answer with no real evidence.
                if best_score < config.RAG_MIN_RELEVANCE and not gathered:
                    return OFF_DOMAIN_REPLY, []
                # Split of concerns: the agent model decides WHICH tools to call
                # and WHEN to stop, but the final answer is always synthesized by
                # the Korean answer model under ANSWER_SYSTEM_PROMPT on the
                # gathered evidence - so answer quality stays at pipeline level
                # regardless of how the (possibly weaker) agent model writes.
                return self._synthesize(question, gathered), sources

            name = action.get("tool")
            tool = self.tools.get(name)
            if tool is None:                   # malformed / unknown -> stop wasting steps
                if verbose:
                    print(f"   ⟳ [step {step+1}] 유효한 도구 없음('{name}') → 답변 합성")
                break
            args = action.get("args") or {}
            # Small models tend to repeat the same search; once we've run a call,
            # a repeat means we're not learning anything new -> synthesize.
            sig = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            if sig in seen_calls:
                if verbose:
                    print(f"   ⟳ [step {step+1}] 동일 검색 반복 → 답변 합성")
                break
            seen_calls.add(sig)
            result = tool.run(**args) if isinstance(args, dict) else tool.run()
            best_score = max(best_score, result.max_score)
            if verbose:
                print(f"   ⟳ [step {step+1}] 도구 호출: {name}"
                      f"({json.dumps(args, ensure_ascii=False)}) "
                      f"→ 점수 {result.max_score:.2f}, 출처 {result.sources}")
            if result.text and result.text != "검색 결과가 없습니다.":
                gathered.append(result.text)
                for s in result.sources:
                    if s not in sources:
                        sources.append(s)
            scratch.append(
                f"행동: {name}({json.dumps(args, ensure_ascii=False)})\n"
                f"관찰: {result.text[:600]}")

        # Ran out of steps: synthesize a grounded answer from what we gathered.
        if verbose:
            print(f"   ⟳ [max {self.max_steps}스텝 도달] 수집 근거로 답변 합성")
        if best_score < config.RAG_MIN_RELEVANCE and not gathered:
            return OFF_DOMAIN_REPLY, []
        return self._synthesize(question, gathered), sources

    def _synthesize(self, question: str, contexts: List[str],
                    num_predict: int = 130) -> str:
        """Final answer, always via the Korean answer model + ANSWER_SYSTEM_PROMPT
        on the gathered evidence (keeps answer quality independent of the agent
        model, which may be weaker/less Korean-native)."""
        prompt = build_answer_prompt(question, contexts)
        return clean_answer(self.bot.llm.generate(
            prompt, system=self.bot.answer_system, num_predict=num_predict))

    # -- Phase 2: multi-intent planner ------------------------------------
    def _plan(self, question: str, verbose: bool = False) -> List[str]:
        """Split a compound question into single-topic sub-questions.

        Returns [question] unchanged when it is a single topic or the model
        can't produce a valid list, so the flow degrades to normal retrieval.
        """
        prompt = (
            "질문에 서로 다른 복지 영역(건강·돌봄·비용지원·일자리·상담 등)이 여러 개 "
            "있으면 각각을 독립된 하위 질문으로 나누세요. 한 영역뿐이면 하나만 담습니다.\n"
            "예시1)\n"
            '질문: "허리도 아프고 끼니 챙기기도 힘들고 요즘 너무 외로워요"\n'
            '출력: ["허리 통증 방문건강관리", "무료 급식 도시락 배달", "외로움 정신건강 상담"]\n'
            "예시2)\n"
            '질문: "기초연금은 어떻게 신청하나요?"\n'
            '출력: ["기초연금 신청 방법"]\n\n'
            f'질문: "{question}"\n'
            "출력: (JSON 배열만, 설명 없이)"
        )
        raw = self.bot.llm.generate(prompt, system=_PLANNER_SYSTEM, model=self.model,
                                    num_predict=160, temperature=0.2)
        # Some models return list items as objects ({"health": "..."}); take the
        # value text so the sub-question is a clean search string.
        def _norm(s):
            if isinstance(s, dict):
                return " ".join(str(v) for v in s.values()).strip()
            return str(s).strip()
        subs = [_norm(s) for s in (_parse_list(raw) or [question])]
        subs = [s for s in subs if s][:self.max_subintents] or [question]
        if verbose:
            print(f"   ⟳ [plan] 하위 의도 {len(subs)}개: {subs}")
        return subs

    def _plan_and_answer(self, question: str,
                         verbose: bool = False) -> Tuple[str | None, List[str]]:
        # Cheap guard: only spend a planner LLM call on questions that actually
        # look compound. This avoids over-splitting a single-topic question
        # (e.g. "기초연금은 어떻게 신청하나요?") and is faster.
        if _looks_compound(question):
            subs = self._plan(question, verbose=verbose)
        else:
            subs = [question]
            if verbose:
                print("   ⟳ [plan] 단일 주제(휴리스틱) → 분해 생략")
        kept: List[Tuple[str, List[str]]] = []   # (sub-question, its context texts)
        sources: List[str] = []
        for sq in subs:
            hits = self.bot.rag.retrieve(sq)
            top = hits[0].score if hits else 0.0
            # Per-sub relevance gate: keep only sub-topics with real evidence.
            if not hits or top < config.RAG_MIN_RELEVANCE:
                if verbose:
                    print(f"   ⟳ [gather] '{sq}' → 근거 부족({top:.2f}) 스킵")
                continue
            kept.append((sq, [h.text for h in hits]))
            for h in hits:
                if h.source not in sources:
                    sources.append(h.source)
            if verbose:
                print(f"   ⟳ [gather] '{sq}' → 점수 {top:.2f}, 출처 {hits[0].source}")
        if not kept:                           # nothing relevant -> safe referral
            return OFF_DOMAIN_REPLY, []

        if len(kept) == 1:                     # single intent -> one grounded answer
            return self._synthesize(question, kept[0][1], num_predict=150), sources

        # Multi-intent: answer each sub-topic from its own evidence, then combine.
        # Per-sub synthesis guarantees every topic is actually covered (one
        # combined generation tends to drop topics on a small answer model).
        parts: List[str] = []
        for sq, ctx in kept:
            a = self._synthesize(sq, ctx, num_predict=110).strip()
            if a and OFF_DOMAIN_REPLY[:12] not in a:   # skip empty/refusal fragments
                parts.append(f"• {a}")
        if not parts:
            return OFF_DOMAIN_REPLY, []
        if verbose:
            print(f"   ⟳ [synth] {len(parts)}개 주제별 답변 결합")
        return "\n".join(parts), sources

    def _decide(self, question: str, scratch: List[str]) -> dict | None:
        """Ask the LLM for the next action as strict JSON."""
        prompt = self._agent_prompt(question, scratch)
        raw = self.bot.llm.generate(prompt, system=_AGENT_SYSTEM, model=self.model,
                                    num_predict=200, temperature=0.2)
        return _parse_action(raw)

    def _agent_prompt(self, question: str, scratch: List[str]) -> str:
        tool_desc = "\n".join(
            f"- {t.name}{t.args}: {t.description}" for t in self.tools.values())
        history = "\n".join(scratch) if scratch else "(아직 없음)"
        return (
            f"어르신 질문: {question}\n\n"
            f"사용 가능한 도구:\n{tool_desc}\n\n"
            f"지금까지의 행동/관찰:\n{history}\n\n"
            "다음 행동을 JSON 한 줄로만 출력하세요. 두 가지 형식 중 하나입니다:\n"
            '  도구 호출: {"tool": "도구이름", "args": {...}}\n'
            '  최종 답변: {"answer": "어르신께 드릴 한국어 답변"}\n'
            "규칙:\n"
            "1) 관찰에 근거가 이미 있으면 도구를 더 부르지 말고 즉시 answer를 내세요.\n"
            "2) 같은 검색을 반복하지 마세요.\n"
            "3) 우울·외로움·상담 등 정서 지원이나 제도 '내용' 질문은 "
            "search_welfare_docs를 쓰고, 특정 구의 '시설 위치'를 찾을 때만 "
            "lookup_facility를 쓰세요.\n"
            "4) args 값은 리스트가 아니라 문자열로 주세요.\n"
            "5) 설명 없이 JSON만 출력합니다."
        )

    # -- deterministic fallback (same logic as pipeline, no re-signal) ------
    def _rag_answer(self, question: str) -> Tuple[str, List[str]]:
        hits = self.bot.rag.retrieve(question)
        top = hits[0].score if hits else 0.0
        if not hits or top < config.RAG_MIN_RELEVANCE:
            return OFF_DOMAIN_REPLY, []
        contexts = [h.text for h in hits]
        prompt = build_answer_prompt(question, contexts)
        answer = clean_answer(self.bot.llm.generate(prompt, system=self.bot.answer_system))
        return answer, [h.source for h in hits]


_AGENT_SYSTEM = (
    "당신은 대전 독거노인 복지 안내 에이전트입니다. 도구를 사용해 근거를 모은 뒤 "
    "한국어로 정확히 답합니다. 자료에 없는 내용은 지어내지 말고, 반드시 지정된 JSON "
    "형식으로만 응답합니다."
)

_PLANNER_SYSTEM = (
    "당신은 대전 독거노인 복지 상담의 계획 도우미입니다. 사용자의 질문을 서로 다른 "
    "복지 주제별 하위 질문으로 나눕니다. 반드시 JSON 배열만 출력합니다."
)

# Clause connectors that suggest a compound (multi-topic) question.
_COMPOUND_RE = re.compile(r"(고\s|하고|하며|이며|그리고|,\s|·)")


def _looks_compound(question: str) -> bool:
    """Heuristic: does the question likely bundle several welfare topics?

    True when it has >=2 clause connectors or repeats the '~도' marker, e.g.
    "무릎도 아프고 난방비도 걱정이고 일자리도 필요해요". A single clause like
    "기초연금은 어떻게 신청하나요?" returns False, so we skip decomposition.
    """
    q = question or ""
    connectors = len(_COMPOUND_RE.findall(q))
    do_markers = len(re.findall(r"도\s", q))
    return connectors >= 2 or do_markers >= 2


def _parse_list(raw: str) -> list | None:
    """Extract the first JSON array from the model output. Robust to extra text."""
    if not raw:
        return None
    start = raw.find("[")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "[":
            depth += 1
        elif raw[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(raw[start:i + 1])
                    return obj if isinstance(obj, list) else None
                except json.JSONDecodeError:
                    return None
    return None


def _parse_action(raw: str) -> dict | None:
    """Extract the first JSON object from the model output. Robust to extra text."""
    if not raw:
        return None
    # Grab the first balanced {...} block.
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                blob = raw[start:i + 1]
                try:
                    obj = json.loads(blob)
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


if __name__ == "__main__":
    print("Initialising agent (indexing welfare docs)...\n")
    agent = WelfareAgent()
    llm = "on" if agent.bot.llm.available else "off (deterministic fallback)"
    print(f"agent model={agent.model} | LLM={llm} | mode={agent.mode}\n")
    for q in ["기초연금은 어떻게 신청하나요?",
              "무릎도 아프고 겨울 난방비도 걱정이고 일자리도 필요해요",   # compound
              "우울하고 외로워요"]:
        print("=" * 70)
        print(f"👵 {q}")
        res = agent.ask(q, verbose=True)
        print(f"🤖 {res.answer[:520]}")
        print(f"   📄 {res.sources}")
        if res.alert:
            print("🚨 (사회복지사 알림 생성됨)")
        print()
