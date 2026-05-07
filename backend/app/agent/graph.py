"""HAL agent — LangGraph state machine with multi-step planning.

Pipeline:

    START
      │
      ▼
    intent_classifier ──── conversation ──┐
      │                                   │
      │  tool                              │
      ▼                                   │
    memory_retrieval ◀────────────────────┘
      │
      ├── tool branch ──► planner ──► tool_executor ◀──┐
      │                                  │              │
      │                                  ▼              │
      │                          (success?)             │
      │                              ├── no (retry < 2) ┴ self_correction
      │                              ▼
      │                          (more steps?)
      │                              ├── yes ── tool_executor (next)
      │                              ▼ no
      │                          memory_write ─────► response_seed
      └── conversation ─────────────────────────────► response_seed
                                                        │
                                                        ▼
                                                       END

Multi-step plans let HAL chain actions in one turn:
    "muestra la ISS en el mapa"
       → plan = [satellite_search, satellite_ground_track]
       → step 1: satellite_search("ISS") → norad_id=25544
       → step 2: satellite_ground_track receives norad_id from step 1's result

Tool-related events (start/end/ui_command/plan) are accumulated into
`state["events"]` as the graph runs.  The wrapper `run_agent_stream` drains
that list before streaming the final response token-by-token via the
LangChain ChatOllama client (so users see text appear in the chat panel)."""
from __future__ import annotations

import logging
import uuid
from typing import Any, AsyncIterator, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.agent.llm import make_streaming_llm
from app.agent.memory import get_memory
from app.agent.models import HALToolCall, Intent, Plan, ToolResult
from app.agent.prompts import RESPONSE_GENERATION_PROMPT, build_system_prompt
from app.agent.tools import (
    classify_intent,
    execute_tool,
    extract_tool_args,
    make_plan,
    ui_command_from_result,
)

log = logging.getLogger("astroagent.graph")


MAX_RETRIES = 2
MAX_PLAN_STEPS = 6   # hard ceiling, also enforced by Plan.steps max_length


# ── State ────────────────────────────────────────────────────────────────────


class StepRecord(TypedDict, total=False):
    """Outcome of a single executed step in the plan."""
    tool: str
    success: bool
    result: dict | list | str | None
    error: str | None


class HALState(TypedDict, total=False):
    user_message: str
    history: list[dict]
    user_id: str
    session_id: str

    intent: Intent | None
    memory_context: str

    plan: Plan | None
    plan_step: int           # next step index to execute (0-based)
    step_results: list[StepRecord]   # accumulated outcomes; fed into next step

    tool_call: HALToolCall | None
    tool_result: ToolResult | None
    retry_count: int         # retries for the CURRENT step
    last_error: str | None

    events: list[dict]
    response_seed: str


# ── Nodes ────────────────────────────────────────────────────────────────────


async def node_intent_classifier(state: HALState) -> dict[str, Any]:
    intent = await classify_intent(state["user_message"], history=state.get("history"))
    log.info("intent → %s | %s", intent.kind, intent.rationale[:80])
    return {"intent": intent}


async def node_memory_retrieval(state: HALState) -> dict[str, Any]:
    mem = get_memory()
    snippets = mem.format_for_prompt(state["user_id"], state["user_message"], top_k=3)
    return {"memory_context": snippets}


_SATELLITE_CHAIN_STEPS = {
    "satellite_search",
    "satellite_ground_track",
    "satellite_passes",
    "tracking_feasibility",
}


def _ensure_select_before_goto(plan: Plan) -> Plan:
    """Defensive post-process: every `mount_goto` to a Stellarium-catalogued
    target must be preceded by `object_position` so the frontend selects +
    centres the object in Stellarium before the slew.  Satellites are NOT in
    Stellarium — they live in the earth-map view — so when a satellite chain
    (`satellite_*` / `tracking_feasibility`) precedes the goto we leave it
    alone.  We also force a `tracking_feasibility` check before any goto
    that follows a satellite chain, so we never command the mount past its
    max angular rate."""
    out: list[str] = []
    for step in plan.steps:
        if step in ("mount_goto", "mount_track"):
            preceded_by_satellite = any(s in _SATELLITE_CHAIN_STEPS for s in out)
            if preceded_by_satellite:
                # Mount motion targeting a satellite — feasibility check is
                # mandatory so we never command the mount past its max rate.
                if "tracking_feasibility" not in out:
                    out.append("tracking_feasibility")
            elif step == "mount_goto":
                # Stellarium target — must be selected first.
                if not out or out[-1] != "object_position":
                    out.append("object_position")
            # mount_track on its own (sidereal/lunar/solar) is a config-style
            # tool with no target, so we leave it alone.
        out.append(step)
    if out == list(plan.steps):
        return plan
    if len(out) > 6:
        out = out[:6]
    return Plan(steps=out, rationale=plan.rationale)


async def node_planner(state: HALState) -> dict[str, Any]:
    """Decompose the user's request into an ordered list of tools to run."""
    events = list(state.get("events", []))
    try:
        plan = await make_plan(state["user_message"], history=state.get("history"))
    except Exception as e:
        log.warning("planner failed (%s) — falling back to single-step plan", e)
        plan = Plan(steps=[], rationale=f"planner error: {e}")

    plan = _ensure_select_before_goto(plan)

    events.append({
        "type": "plan",
        "steps": list(plan.steps),
        "rationale": plan.rationale,
    })
    log.info("plan → %s | %s", plan.steps, plan.rationale[:80])
    return {
        "plan": plan,
        "plan_step": 0,
        "step_results": [],
        "retry_count": 0,
        "last_error": None,
        "events": events,
    }


async def node_tool_executor(state: HALState) -> dict[str, Any]:
    """Execute the current step of the plan.

    On success: record the outcome, advance `plan_step`, reset retries.
    On failure: increment `retry_count` so the routing decides between
    self-correction (retry) and giving up on this plan."""
    events = list(state.get("events", []))
    plan: Plan | None = state.get("plan")
    step_idx = state.get("plan_step", 0)
    prev_err = state.get("last_error")
    retry = state.get("retry_count", 0)
    step_results: list[StepRecord] = list(state.get("step_results", []))

    if not plan or step_idx >= len(plan.steps):
        return {}  # nothing to do — router will exit the loop

    tool_name = plan.steps[step_idx]

    try:
        call = await extract_tool_args(
            tool_name=tool_name,
            user_message=state["user_message"],
            prior_results=step_results,
            prev_error=prev_err,
            history=state.get("history"),
        )
    except Exception as e:
        err = f"No pude extraer argumentos para `{tool_name}`: {e}"
        events.append({"type": "tool_error", "stage": "extract",
                       "tool": tool_name, "error": err})
        return {
            "tool_result": ToolResult(tool=tool_name, success=False, error=err),
            "last_error": err, "retry_count": retry + 1, "events": events,
        }

    schema_name = type(call).__name__
    events.append({"type": "tool_start", "tool": schema_name,
                   "step": step_idx + 1, "of": len(plan.steps),
                   "input": call.model_dump(mode="json")})
    log.info("step %d/%d → %s(%s) [retry=%d]",
             step_idx + 1, len(plan.steps), schema_name,
             str(call.model_dump())[:80], retry)

    result = await execute_tool(call)
    events.append({"type": "tool_end", "tool": schema_name,
                   "step": step_idx + 1,
                   "output": (result.result if result.success else result.error)})

    if result.success:
        ui = ui_command_from_result(call, result)
        if ui:
            events.append({"type": "ui_command", **ui})
        # record + advance
        step_results.append({
            "tool": tool_name,
            "success": True,
            "result": result.result,
            "error": None,
        })
        return {
            "tool_call": call, "tool_result": result,
            "step_results": step_results,
            "plan_step": step_idx + 1,
            "retry_count": 0, "last_error": None,
            "events": events,
        }

    # Failure — let the router decide: retry or abort the plan.
    return {
        "tool_call": call, "tool_result": result,
        "last_error": result.error,
        "retry_count": retry + 1,
        "events": events,
    }


async def node_self_correction(state: HALState) -> dict[str, Any]:
    """Pass-through node — the actual reformulation happens on the next
    `tool_executor` run, which reads `last_error` from state.  Kept as a
    distinct node so the graph topology is explicit and inspectable in logs."""
    log.info("self-correct (retry %d) | err=%s",
             state.get("retry_count", 0), (state.get("last_error") or "")[:80])
    return {}


async def node_memory_write(state: HALState) -> dict[str, Any]:
    """Persist one observation per successful step to episodic memory."""
    mem = get_memory()
    if not mem.available:
        return {}
    user_msg = state["user_message"][:120]
    sid = state.get("session_id")
    for step in state.get("step_results", []) or []:
        if not step.get("success"):
            continue
        target = None
        # try to pull a target name out of the result (varies by tool)
        if isinstance(step.get("result"), dict):
            for k in ("name", "target", "target_name"):
                v = step["result"].get(k)
                if v:
                    target = str(v)
                    break
        obs = f"Usuario: «{user_msg}» → ejecutó {step['tool']}"
        if target:
            obs += f" sobre «{target}»"
        mem.save_observation(
            user_id=state["user_id"],
            observation=obs,
            tool_used=step["tool"],
            target_object=target,
            session_id=sid,
        )
    return {}


async def node_response_seed(state: HALState) -> dict[str, Any]:
    """Build the prompt context the response generator will use.  Summarises
    every step (successes + the final failure if the plan was aborted)."""
    steps = state.get("step_results") or []
    last_res = state.get("tool_result")
    last_err = state.get("last_error")
    retries = state.get("retry_count", 0)

    if not steps and not last_res:
        return {"response_seed": ""}

    parts: list[str] = []
    if steps:
        parts.append("Pasos ejecutados con éxito en este turno:")
        for i, st in enumerate(steps, 1):
            parts.append(f"{i}. {st['tool']} → {_summarise_step_result(st['result'])}")

    # If the plan was aborted on a failure, the failed step isn't in step_results
    # (we only append on success).  Surface it from `last_error`.
    if last_res is not None and not last_res.success:
        parts.append(
            f"\nEl paso `{last_res.tool}` falló tras {retries} intento(s). "
            f"Error: {last_res.error}.\n"
            f"Explícaselo al usuario y propón un siguiente paso concreto."
        )
    elif steps:
        parts.append("\nResume al usuario, en su idioma, qué hiciste y los datos clave.")

    return {"response_seed": "\n".join(parts)}


# ── Routing ──────────────────────────────────────────────────────────────────


def route_after_intent(state: HALState) -> Literal["planner", "response_seed"]:
    intent = state.get("intent")
    return "planner" if (intent and intent.kind == "tool") else "response_seed"


def route_after_planner(state: HALState) -> Literal["tool_executor", "response_seed"]:
    """If the planner produced an empty plan (e.g. it decided no tool was
    actually needed despite the intent classifier's vote), skip straight to
    response generation — there's nothing to execute."""
    plan = state.get("plan")
    if plan and plan.steps:
        return "tool_executor"
    return "response_seed"


def route_after_tool(state: HALState) -> Literal["tool_executor", "self_correction", "memory_write", "response_seed"]:
    res = state.get("tool_result")
    plan = state.get("plan")
    if res and res.success:
        # Step succeeded — continue the loop if more steps remain.
        if plan and state.get("plan_step", 0) < len(plan.steps):
            return "tool_executor"
        return "memory_write"
    # Step failed — retry if budget left, else surface the error.
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "self_correction"
    return "response_seed"


# ── Graph wiring ─────────────────────────────────────────────────────────────


def build_graph():
    g = StateGraph(HALState)
    g.add_node("intent_classifier", node_intent_classifier)
    g.add_node("memory_retrieval",  node_memory_retrieval)
    g.add_node("planner",           node_planner)
    g.add_node("tool_executor",     node_tool_executor)
    g.add_node("self_correction",   node_self_correction)
    g.add_node("memory_write",      node_memory_write)
    g.add_node("response_seed",     node_response_seed)

    g.add_edge(START, "intent_classifier")
    g.add_edge("intent_classifier", "memory_retrieval")
    g.add_conditional_edges("memory_retrieval", route_after_intent)
    g.add_conditional_edges("planner", route_after_planner)
    g.add_conditional_edges("tool_executor", route_after_tool)
    g.add_edge("self_correction", "tool_executor")
    g.add_edge("memory_write", "response_seed")
    g.add_edge("response_seed", END)
    return g.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


# ── Public streaming API ─────────────────────────────────────────────────────


def _truncate(value: Any, max_chars: int = 1200) -> str:
    import json
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = str(value)
    return s if len(s) <= max_chars else s[:max_chars] + "…"


def _summarise_step_result(value: Any, max_chars: int = 400) -> str:
    """Render a tool result for inclusion in the response_seed.  Avoids
    raw-JSON dumps for long lists (which the LLM tends to echo verbatim
    inside a ```json block) — instead gives count + a peek at the first
    entry, so the model has enough to talk about without being tempted to
    paste the array."""
    import json
    if isinstance(value, list):
        n = len(value)
        if n == 0:
            return "lista vacía"
        head = value[0]
        try:
            head_s = json.dumps(head, ensure_ascii=False, default=str)
        except Exception:
            head_s = str(head)
        if len(head_s) > max_chars:
            head_s = head_s[:max_chars] + "…"
        return f"{n} elemento(s); primero: {head_s}"
    if isinstance(value, dict):
        try:
            s = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            s = str(value)
        return s if len(s) <= max_chars else s[:max_chars] + "…"
    return _truncate(value, max_chars)


async def run_agent_stream(
    user_message: str,
    history: list[dict] | None = None,
    user_id: str = "default",
) -> AsyncIterator[dict]:
    """Drive the HAL graph and yield SSE-shaped events.

    Stream order: tool events (as the graph executes them) → response tokens
    (streamed from ChatOllama with the system prompt + memory + tool result
    seed) → done.
    """
    graph = get_graph()
    initial: HALState = {
        "user_message": user_message,
        "history": history or [],
        "user_id": user_id,
        "session_id": str(uuid.uuid4())[:8],
        "events": [],
        "retry_count": 0,
    }

    log.info("HAL turn start | user=%s | msg=%r", user_id, user_message[:80])

    # Run the graph with stream_mode="updates" so we can flush tool events
    # as soon as each node completes (instead of all-at-once at the end).
    final_state: HALState = dict(initial)  # type: ignore[assignment]
    seen_event_ids: set[int] = set()

    # Default recursion_limit (25) is tight for a 6-step plan that may also
    # self-correct twice per step.  Bump it generously.
    config = {"recursion_limit": 60}
    async for step in graph.astream(initial, stream_mode="updates", config=config):
        for node_name, update in step.items():
            if not isinstance(update, dict):
                continue
            final_state.update(update)
            for ev in update.get("events", []) or []:
                eid = id(ev)
                if eid in seen_event_ids:
                    continue
                seen_event_ids.add(eid)
                yield ev

    # Stream the final natural-language response with ChatOllama so the chat
    # panel sees tokens appear progressively.
    async for tok in _stream_response(final_state):
        yield {"type": "token", "content": tok}

    log.info("HAL turn done | retries=%d | tool=%s",
             final_state.get("retry_count", 0),
             final_state.get("tool_result").tool if final_state.get("tool_result") else "—")
    yield {"type": "done"}


class _ThinkStripper:
    """Stateful stream filter that drops everything inside <think>…</think>.

    The HAL prompt instructs the model to use those blocks for internal
    reasoning, so they must never reach the user.  We process tokens as they
    arrive — buffering only when we're inside a tag or potentially mid-tag.

    Failsafe: if the stream ends while we're still inside an unclosed
    `<think>` AND we never produced any visible output, we release the
    buffered content anyway — better to leak reasoning than to leave the
    user with a blank reply."""

    def __init__(self) -> None:
        self._inside = False
        self._buf = ""
        self._inside_buf = ""  # held while inside, used as failsafe on flush
        self._emitted_anything = False

    def feed(self, token: str) -> str:
        out: list[str] = []
        text = self._buf + token
        self._buf = ""
        i = 0
        while i < len(text):
            if self._inside:
                close = text.find("</think>", i)
                if close < 0:
                    self._inside_buf += text[i:]
                    return self._record(out)
                self._inside_buf += text[i:close]
                i = close + len("</think>")
                self._inside = False
                continue
            open_idx = text.find("<think>", i)
            if open_idx < 0:
                tail_start = max(i, len(text) - len("<think>") + 1)
                out.append(text[i:tail_start])
                self._buf = text[tail_start:]
                return self._record(out)
            out.append(text[i:open_idx])
            i = open_idx + len("<think>")
            self._inside = True
        return self._record(out)

    def _record(self, parts: list[str]) -> str:
        s = "".join(parts)
        if s:
            self._emitted_anything = True
        return s

    def flush(self) -> str:
        # On end-of-stream `_buf` may hold up to len("<think>")-1 chars that we
        # were keeping back in case they completed an opening tag.  If we're
        # NOT inside a think block, those bytes are visible content and must
        # be released — otherwise the last few characters of the reply get
        # silently truncated mid-word.
        if not self._inside and self._buf:
            tail = self._buf
            self._buf = ""
            self._inside_buf = ""
            self._emitted_anything = True
            return tail
        if self._emitted_anything:
            # Inside an unclosed <think> after visible content — discard.
            self._buf = ""
            self._inside_buf = ""
            return ""
        # Nothing visible was emitted.  Failsafe: release whatever we held so
        # the user doesn't get a blank reply.  Strip the <think> wrapper.
        leftover = (self._inside_buf + self._buf).strip()
        self._buf = ""
        self._inside_buf = ""
        return leftover


async def _stream_response(state: HALState) -> AsyncIterator[str]:
    """Stream the final assistant message token-by-token from the configured
    LLM backend (Ollama or ik_llama.cpp).  Ollama defaults are tight
    (num_ctx=2048, num_predict=128 chop replies mid-sentence); the factory
    widens both.  For ik_llama, num_ctx is set at server launch — only
    num_predict (max_tokens) takes effect per request."""
    llm = make_streaming_llm(temperature=0.3, num_ctx=8192, num_predict=1024)

    system = build_system_prompt(memory_context=state.get("memory_context") or "")
    seed = state.get("response_seed") or ""
    history = state.get("history") or []

    msgs: list = [SystemMessage(content=system)]
    for turn in history:
        if turn["role"] == "user":
            msgs.append(HumanMessage(content=turn["content"]))
        elif turn["role"] == "assistant" and turn.get("content"):
            msgs.append(AIMessage(content=turn["content"]))
    msgs.append(HumanMessage(content=state["user_message"]))
    if seed:
        msgs.append(SystemMessage(content=RESPONSE_GENERATION_PROMPT + "\n\n" + seed))

    stripper = _ThinkStripper()
    try:
        async for chunk in llm.astream(msgs):
            content = getattr(chunk, "content", "")
            if not content:
                continue
            visible = stripper.feed(content)
            if visible:
                yield visible
        tail = stripper.flush()
        if tail:
            yield tail
    except Exception as e:
        log.exception("response stream failed: %s", e)
        yield f"\n\n[error generando respuesta: {e}]"
