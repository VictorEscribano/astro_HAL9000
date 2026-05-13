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
from app.agent.models import HALToolCall, Plan, ToolResult
from app.agent.prompts import RESPONSE_GENERATION_PROMPT, build_system_prompt
from app.agent.tools import (
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


def route_after_planner(state: HALState) -> Literal["tool_executor", "response_seed"]:
    """The planner is the single is-this-a-tool-turn decision: empty
    `plan.steps` means conversation, jump straight to response generation;
    non-empty means the tool executor takes over."""
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
    """Pipeline:

        START → memory_retrieval → planner ─┬→ tool_executor (loop) → memory_write → response_seed → END
                                            └→ response_seed (no tools needed) → END

    The planner is the single is-this-a-tool-turn decision; we used to run
    a separate `intent_classifier` LLM call before it but its only job was
    to gate the planner, and the planner already returns `steps=[]` for
    pure-conversation turns.  Dropping the classifier saves one LLM call
    per turn (≈25 % latency on hybrid-MoE backends like ik_llama)."""
    g = StateGraph(HALState)
    g.add_node("memory_retrieval",  node_memory_retrieval)
    g.add_node("planner",           node_planner)
    g.add_node("tool_executor",     node_tool_executor)
    g.add_node("self_correction",   node_self_correction)
    g.add_node("memory_write",      node_memory_write)
    g.add_node("response_seed",     node_response_seed)

    g.add_edge(START, "memory_retrieval")
    g.add_edge("memory_retrieval", "planner")
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
    # panel sees tokens appear progressively.  `_stream_response` now yields
    # event dicts directly (token / thinking).
    async for ev in _stream_response(final_state):
        yield ev

    log.info("HAL turn done | retries=%d | tool=%s",
             final_state.get("retry_count", 0),
             final_state.get("tool_result").tool if final_state.get("tool_result") else "—")
    yield {"type": "done"}


class _ThinkSplitter:
    """Stateful stream splitter for `<think>…</think>` content.

    `.feed(token)` returns `(visible, thinking)` — both possibly empty —
    instead of dropping the thinking part as the old `_ThinkStripper` did.
    The tags themselves are consumed, never emitted.  Callers route the
    two streams to different UI surfaces (reasoning card vs. response body).

    Failsafe on flush: if the stream ends inside an unclosed `<think>`,
    the buffered thinking content is released as thinking output (so a
    truncated reasoning block is still visible to the user) — and if no
    visible content was ever emitted, the caller is responsible for
    surfacing a user-facing note (we no longer leak reasoning into the
    response body)."""

    def __init__(self) -> None:
        self._inside = False
        self._buf = ""             # pending bytes that may complete a tag
        self._inside_buf = ""      # thinking bytes held until we flush

    def feed(self, token: str) -> tuple[str, str]:
        out_vis: list[str] = []
        out_th: list[str] = []
        text = self._buf + token
        self._buf = ""
        i = 0
        while i < len(text):
            if self._inside:
                close = text.find("</think>", i)
                if close < 0:
                    out_th.append(text[i:])
                    return "".join(out_vis), "".join(out_th)
                out_th.append(text[i:close])
                i = close + len("</think>")
                self._inside = False
                continue
            open_idx = text.find("<think>", i)
            if open_idx < 0:
                # Keep up to (len("<think>") - 1) bytes back in case the
                # next chunk completes an opening tag.
                tail_start = max(i, len(text) - len("<think>") + 1)
                out_vis.append(text[i:tail_start])
                self._buf = text[tail_start:]
                return "".join(out_vis), "".join(out_th)
            out_vis.append(text[i:open_idx])
            i = open_idx + len("<think>")
            self._inside = True
        return "".join(out_vis), "".join(out_th)

    def flush(self) -> tuple[str, str]:
        if not self._inside and self._buf:
            tail = self._buf
            self._buf = ""
            return tail, ""
        # Inside an unclosed <think>: release as thinking, not as visible.
        leftover = self._buf
        self._buf = ""
        if leftover:
            return "", leftover
        return "", ""


async def _stream_response(state: HALState) -> AsyncIterator[dict]:
    """Stream the final assistant message token-by-token from the configured
    LLM backend (Ollama or ik_llama.cpp).  Yields event dicts:
      - `{type: "token",    content: str}` — visible response token(s)
      - `{type: "thinking", content: str}` — bytes inside a `<think>` block

    Ollama defaults are tight (num_ctx=2048, num_predict=128 chop replies
    mid-sentence); the factory widens both.  For ik_llama, num_ctx is set
    at server launch — only num_predict (max_tokens) takes effect per
    request."""
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

    splitter = _ThinkSplitter()
    visible_emitted = False
    try:
        async for chunk in llm.astream(msgs):
            content = getattr(chunk, "content", "")
            if not content:
                continue
            vis, think = splitter.feed(content)
            if think:
                yield {"type": "thinking", "content": think}
            if vis:
                visible_emitted = True
                yield {"type": "token", "content": vis}
        vis_tail, think_tail = splitter.flush()
        if think_tail:
            yield {"type": "thinking", "content": think_tail}
        if vis_tail:
            visible_emitted = True
            yield {"type": "token", "content": vis_tail}
        if not visible_emitted:
            # Model spent all its budget thinking and never closed the block —
            # the reasoning is still visible in the thinking card, but the
            # response body would otherwise be empty.
            yield {"type": "token",
                   "content": "(razonamiento incompleto — el modelo no llegó a generar respuesta)"}
    except Exception as e:
        log.exception("response stream failed: %s", e)
        yield {"type": "token", "content": f"\n\n[error generando respuesta: {e}]"}
