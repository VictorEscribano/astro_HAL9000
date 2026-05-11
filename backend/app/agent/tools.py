"""HAL tool layer.

Two responsibilities:

1.  `parse_tool_call(text, schema)` — convert free-form user input into a
    validated `HALToolCall` Pydantic instance via `instructor`.  This is
    what makes tool calls reliable: the LLM is forced to emit JSON that
    matches the schema or the call fails (and we route it to the
    self-correction node).

2.  `execute_tool(call)` — dispatch a validated `HALToolCall` to the actual
    Python implementation in `app/tools/*` and return a uniform `ToolResult`.

The instructor client uses Ollama's OpenAI-compatible endpoint
(`/v1/chat/completions`), so no extra Ollama configuration is required."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Type

from app.agent.llm import get_active_model_name, get_instructor_client
from app.agent.models import (
    CameraExposure,
    CameraSequence,
    HALToolCall,
    Intent,
    MountAbort,
    MountGoto,
    MountPark,
    MountTrack,
    MoonInfoQuery,
    ObjectPositionQuery,
    Plan,
    PythonExec,
    SatelliteGroundTrack,
    SatellitePassesQuery,
    SatelliteSearch,
    SkyTonightQuery,
    ToolResult,
    TOOL_NAME_TO_SCHEMA,
    ToolSelection,
    TrackingFeasibilityCheck,
    WeatherQuery,
    WebSearch,
    YouTubeOpen,
    WidgetCreate,
    tool_list_for_prompt,
)
from app.agent.prompts import INTENT_CLASSIFIER_PROMPT, TOOL_EXTRACTION_PROMPT
from app.config import get_settings

log = logging.getLogger("astroagent.tools")


# ── Instructor client (backend-agnostic) ─────────────────────────────────────


def client():
    """Backwards-compatible alias for the backend-aware instructor client.
    All extraction calls below use this so they automatically follow the
    `llm_backend` setting."""
    return get_instructor_client()


# ── Structured extraction ────────────────────────────────────────────────────


def _format_history_tail(history: list[dict] | None, max_turns: int = 4) -> str:
    """Render the last few turns as a short transcript for the classifier
    and planner.  Without this, single-word replies like 'dale' / 'sí' /
    'vale' lose all context and get mis-routed."""
    if not history:
        return ""
    tail = history[-max_turns:]
    lines = []
    for turn in tail:
        role = turn.get("role", "?")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        speaker = "Usuario" if role == "user" else "HAL"
        lines.append(f"{speaker}: {content[:300]}")
    if not lines:
        return ""
    return "Contexto reciente de la conversación:\n" + "\n".join(lines) + "\n\n"


_CONV_KEYWORDS = {
    "hola", "hi", "hello", "hey", "buenas", "buenos", "gracias", "thank", "thanks",
    "ok", "vale", "genial", "perfecto", "cool", "adiós", "bye", "adios",
    "qué es", "que es", "qué son", "cuéntame", "cuentame", "explícame", "explicame",
    "what is", "tell me about", "explain",
}


def _fast_conv_check(msg: str) -> bool:
    """Return True if the message is obviously conversational (no tool needed).
    Bypasses the LLM call entirely to save CPU time."""
    low = msg.lower().strip()
    # Short greetings / single words
    if len(low.split()) <= 2 and any(kw in low for kw in _CONV_KEYWORDS):
        return True
    # No action verbs or hardware keywords → likely conversation
    action_hints = {"mueve", "apunta", "goto", "park", "sigue", "track", "expón",
                    "busca", "satellite", "iss", "clima", "weather", "visible",
                    "foto", "imagen", "graba", "abre youtube", "crea widget",
                    "move", "point", "expose", "search", "show"}
    if not any(h in low for h in action_hints) and len(low.split()) <= 6:
        return True
    return False


async def classify_intent(user_message: str, history: list[dict] | None = None) -> Intent:
    """Decide whether this turn needs a tool or is conversation.  Runs as a
    blocking openai call wrapped in a thread to keep the event loop free.
    For CPU backends a keyword fast-path is applied first to skip the LLM."""
    s = get_settings()

    if s.llm_backend in ("llamacpp", "onnx") and _fast_conv_check(user_message):
        return Intent(intent="conversation", rationale="keyword fast-path")

    history_block = _format_history_tail(history)
    prompt = history_block + INTENT_CLASSIFIER_PROMPT.format(user_message=user_message)
    max_retries = 1 if s.llm_backend in ("llamacpp", "onnx") else 2

    def _call():
        return client().chat.completions.create(
            model=get_active_model_name(),
            response_model=Intent,
            temperature=0.1,
            max_retries=max_retries,
            max_tokens=80,
            messages=[
                {"role": "system",
                 "content": (
                     "Eres un clasificador de intención. Si el turno actual es una "
                     "respuesta corta ('sí', 'dale', 'vale', 'no', 'ok') interpreta "
                     "la intención a partir del contexto reciente. Responde solo "
                     "con el JSON pedido."
                 )},
                {"role": "user", "content": prompt},
            ],
        )

    return await asyncio.to_thread(_call)


async def make_plan(user_message: str, history: list[dict] | None = None) -> Plan:
    """Decompose a tool-bearing turn into an ordered list of tool names.
    Returns an empty Plan if the message is purely conversational (the
    intent classifier should already have routed those, but we tolerate it)."""
    s = get_settings()
    tool_list = tool_list_for_prompt()
    history_block = _format_history_tail(history)

    max_retries = 1 if get_settings().llm_backend in ("llamacpp", "onnx") else 2

    def _call():
        return client().chat.completions.create(
            model=get_active_model_name(),
            response_model=Plan,
            temperature=0.1,
            max_retries=max_retries,
            max_tokens=120,
            messages=[
                {"role": "system",
                 "content": (
                     "Eres el planner de HAL.  Recibes un turno del usuario "
                     "(opcionalmente con contexto reciente) y devuelves la lista "
                     "mínima de herramientas a ejecutar, en orden de dependencia. "
                     "Si el turno actual es una respuesta corta ('sí', 'dale', "
                     "'vale'), interpreta qué confirmó el usuario a partir del "
                     "contexto reciente y planifica esa acción.  No inventes "
                     "pasos que el usuario no pidió.\n\n"
                     "Reglas obligatorias:\n"
                     "- Si una herramienta necesita un dato que sólo se obtiene "
                     "ejecutando otra antes (ej: NORAD ID antes de "
                     "satellite_ground_track), pónlas en orden.\n"
                     "- Para objetivos del catálogo de Stellarium (planetas, "
                     "estrellas, objetos de cielo profundo): TODO `mount_goto` "
                     "DEBE ir precedido por un `object_position` del mismo "
                     "objetivo, para que el frontend lo seleccione y centre en "
                     "Stellarium antes del slew.\n"
                     "- Para satélites (ISS, Hubble, etc.) que NO están en "
                     "Stellarium: el orden es `satellite_search` → "
                     "`satellite_ground_track` (para mostrar la traza en el "
                     "mapa terrestre) → `tracking_feasibility` (comprobar que "
                     "la velocidad angular cabe dentro de la velocidad máxima "
                     "del motor) → solo si es factible, `mount_goto` o "
                     "`mount_track`.  NO uses `object_position` para satélites.\n\n"
                     "Devuelve solo JSON."
                 )},
                {"role": "user",
                 "content": (
                     f"Catálogo:\n{tool_list}\n\n"
                     + history_block +
                     "Turno actual del usuario:\n"
                     f'"""{user_message}"""\n\n'
                     "Devuelve un Plan JSON con `steps` y `rationale`."
                 )},
            ],
        )

    return await asyncio.to_thread(_call)


async def extract_tool_args(
    tool_name: str,
    user_message: str,
    prior_results: list[dict] | None = None,
    prev_error: str | None = None,
    history: list[dict] | None = None,
) -> HALToolCall:
    """Extract just the arguments for an already-chosen tool, given the user
    message and (optionally) the results of prior steps in the same plan.

    `prior_results` is a list of `{"tool": str, "result": Any}` from earlier
    steps so the LLM can chain (e.g. take the NORAD ID returned by
    `satellite_search` and use it as `norad_id` in `satellite_ground_track`).
    `history` provides recent conversation turns so short replies like
    "dale" / "sí" can be resolved against what the user just confirmed.
    """
    s = get_settings()
    schema = TOOL_NAME_TO_SCHEMA[tool_name]

    history_block = _format_history_tail(history)

    prior_block = ""
    if prior_results:
        import json as _json
        prior_block = "Resultados de pasos anteriores en este plan:\n"
        for step in prior_results:
            try:
                snippet = _json.dumps(step["result"], default=str)[:600]
            except Exception:
                snippet = str(step["result"])[:600]
            prior_block += f"- {step['tool']} → {snippet}\n"
        prior_block += "\nUsa estos datos cuando un argumento dependa de ellos.\n\n"

    err_block = ""
    if prev_error:
        err_block = f"El intento anterior falló con: {prev_error}\nCorrige los argumentos.\n\n"

    max_retries = 1 if s.llm_backend in ("llamacpp", "onnx") else 2

    def _call():
        return client().chat.completions.create(
            model=get_active_model_name(),
            response_model=schema,
            temperature=0.1,
            max_retries=max_retries,
            max_tokens=150,
            messages=[
                {"role": "system",
                 "content": (
                     f"Rellena los argumentos para la herramienta `{tool_name}` "
                     "desde el mensaje del usuario, el contexto reciente y los "
                     "resultados previos. Si el turno actual es una confirmación "
                     "corta, deduce el objetivo del contexto reciente. Devuelve "
                     "solo JSON válido con los campos del schema."
                 )},
                {"role": "user",
                 "content": (
                     history_block + prior_block + err_block +
                     f'Turno actual del usuario:\n"""{user_message}"""'
                 )},
            ],
        )

    return await asyncio.to_thread(_call)


async def extract_tool_call(
    user_message: str,
    prev_error: str | None = None,
) -> HALToolCall:
    """Pick a tool and fill its arguments from the user's message.

    Two-step extraction:
      1. `ToolSelection` — small schema with a Literal of tool names.
         Avoids the `$ref` indirection problem Qwen 2.5 emits when faced
         with a Pydantic Union of many concrete schemas.
      2. The chosen tool's full schema, extracted from the same message.

    `prev_error` is set by the self-correction loop on retry so the LLM gets
    a chance to fix whatever went wrong (e.g. validation rejected
    `altitude=95` because of `le=90`).
    """
    s = get_settings()

    # Step 1: pick a tool name.
    tool_list = tool_list_for_prompt()

    def _select():
        return client().chat.completions.create(
            model=get_active_model_name(),
            response_model=ToolSelection,
            temperature=0.1,
            max_retries=2,
            messages=[
                {"role": "system",
                 "content": "Eres un selector de herramientas. Devuelve solo el JSON pedido."},
                {"role": "user",
                 "content": (
                     "Catálogo de herramientas disponibles:\n"
                     f"{tool_list}\n\n"
                     "Selecciona la herramienta más adecuada para este turno:\n"
                     f'"""{user_message}"""'
                 )},
            ],
        )

    selection: ToolSelection = await asyncio.to_thread(_select)
    schema = TOOL_NAME_TO_SCHEMA[selection.tool_name]
    log.info("tool selection → %s", selection.tool_name)

    # Step 2: fill the arguments for the chosen schema.
    prompt = TOOL_EXTRACTION_PROMPT.format(
        user_message=user_message,
        prev_error=prev_error or "(ninguno — primer intento)",
    )

    def _extract():
        return client().chat.completions.create(
            model=get_active_model_name(),
            response_model=schema,
            temperature=0.1,
            max_retries=2,
            messages=[
                {"role": "system",
                 "content": (
                     f"Rellena los parámetros para la herramienta `{selection.tool_name}` "
                     "desde el mensaje del usuario. Devuelve un único JSON válido."
                 )},
                {"role": "user", "content": prompt},
            ],
        )

    return await asyncio.to_thread(_extract)


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _ok(tool: str, payload: Any) -> ToolResult:
    if isinstance(payload, (dict, list, str)):
        return ToolResult(tool=tool, success=True, result=payload)
    # pydantic models
    if hasattr(payload, "model_dump"):
        return ToolResult(tool=tool, success=True, result=payload.model_dump(mode="json"))
    return ToolResult(tool=tool, success=True, result={"value": str(payload)})


def _err(tool: str, msg: str) -> ToolResult:
    return ToolResult(tool=tool, success=False, error=msg)


async def execute_tool(call: HALToolCall) -> ToolResult:
    """Dispatch a validated `HALToolCall` to its concrete implementation."""
    tool_name = type(call).__name__

    # Mount ──────────────────────────────────────────────────────────────────
    if isinstance(call, MountGoto):
        from app.tools.mount import execute_mount_command
        from app.models.mount import SlewCommand, TrackingRate
        try:
            cmd = SlewCommand(
                ra_h=call.ra_h, dec_deg=call.dec_deg,
                alt_deg=call.alt_deg, az_deg=call.az_deg,
                target_name=call.target_name,
                tracking_rate=TrackingRate.SIDEREAL if call.tracking else TrackingRate.OFF,
            )
            return _ok("mount_goto", execute_mount_command(cmd))
        except Exception as e:
            return _err("mount_goto", str(e))

    if isinstance(call, MountTrack):
        from app.tools.mount import execute_mount_command
        from app.models.mount import SlewCommand, TrackingRate
        rate_map = {
            "sidereal": TrackingRate.SIDEREAL,
            "lunar":    TrackingRate.LUNAR,
            "solar":    TrackingRate.SOLAR,
        }
        try:
            cmd = SlewCommand(target_name="__TRACK__", tracking_rate=rate_map[call.rate])
            return _ok("mount_track", execute_mount_command(cmd))
        except Exception as e:
            return _err("mount_track", str(e))

    if isinstance(call, MountPark):
        from app.tools.mount import execute_mount_command
        from app.models.mount import SlewCommand
        try:
            cmd = SlewCommand(target_name="__PARK__")
            return _ok("mount_park", execute_mount_command(cmd))
        except Exception as e:
            return _err("mount_park", str(e))

    if isinstance(call, MountAbort):
        from app.tools.mount import execute_mount_command
        from app.models.mount import SlewCommand
        try:
            cmd = SlewCommand(target_name="__STOP__")
            return _ok("mount_abort", execute_mount_command(cmd))
        except Exception as e:
            return _err("mount_abort", str(e))

    # Ephemerides ────────────────────────────────────────────────────────────
    if isinstance(call, ObjectPositionQuery):
        from app.tools.ephemeris import get_object_position_now
        try:
            pos = get_object_position_now(call.name)
            if not pos:
                return _err("object_position", f"Objeto '{call.name}' no encontrado.")
            return _ok("object_position", pos)
        except Exception as e:
            return _err("object_position", str(e))

    if isinstance(call, SkyTonightQuery):
        from app.tools.ephemeris import get_sky_objects_tonight
        try:
            return _ok("sky_tonight", [o.model_dump(mode="json")
                                       for o in get_sky_objects_tonight(min_alt_deg=call.min_alt_deg)])
        except Exception as e:
            return _err("sky_tonight", str(e))

    if isinstance(call, MoonInfoQuery):
        from app.tools.ephemeris import get_moon_info_now
        try:
            return _ok("moon_info", get_moon_info_now())
        except Exception as e:
            return _err("moon_info", str(e))

    # Satellites ─────────────────────────────────────────────────────────────
    if isinstance(call, SatelliteSearch):
        from app.services.celestrak import resolve_known_satellite, search_satellite_by_name
        try:
            norad = resolve_known_satellite(call.name)
            if norad:
                return _ok("satellite_search", [{"norad_id": norad, "name": call.name, "source": "known"}])
            results = await search_satellite_by_name(call.name)
            if not results:
                return _err("satellite_search", f"No encontrado: '{call.name}'.")
            return _ok("satellite_search", results)
        except Exception as e:
            return _err("satellite_search", str(e))

    if isinstance(call, SatellitePassesQuery):
        from app.tools.satellites import get_satellite_passes
        try:
            passes = await get_satellite_passes(call.norad_id, call.days)
            return _ok("satellite_passes", [p.model_dump(mode="json") for p in passes])
        except Exception as e:
            return _err("satellite_passes", str(e))

    if isinstance(call, SatelliteGroundTrack):
        from app.tools.satellites import get_satellite_ground_track
        try:
            track = await get_satellite_ground_track(call.norad_id, call.minutes)
            return _ok("satellite_ground_track", [t.model_dump(mode="json") for t in track])
        except Exception as e:
            return _err("satellite_ground_track", str(e))

    if isinstance(call, TrackingFeasibilityCheck):
        from app.tools.satellites import check_tracking_feasibility
        try:
            return _ok("tracking_feasibility",
                       check_tracking_feasibility(call.target_name, call.peak_rate_arcsec_s))
        except Exception as e:
            return _err("tracking_feasibility", str(e))

    # Camera (stubbed — hardware not yet wired) ──────────────────────────────
    if isinstance(call, (CameraExposure, CameraSequence)):
        return _err(
            "camera",
            "El control de cámara aún no está conectado al hardware. "
            "Por ahora solo puedo simular la solicitud: "
            f"{call.model_dump(mode='json')}",
        )

    # Environment ────────────────────────────────────────────────────────────
    if isinstance(call, WeatherQuery):
        from app.tools.weather import get_weather_and_seeing
        try:
            return _ok("weather", await get_weather_and_seeing())
        except Exception as e:
            return _err("weather", str(e))

    # Generic Python ─────────────────────────────────────────────────────────
    if isinstance(call, PythonExec):
        from app.tools.python_exec import execute_python
        try:
            return _ok("python_exec", await execute_python(call.code))
        except Exception as e:
            return _err("python_exec", str(e))

    # Web / Wikipedia search ──────────────────────────────────────────────────
    if isinstance(call, WebSearch):
        from app.tools.web import find_youtube_video, search_web, search_wikipedia
        try:
            source = call.source
            if source == "wikipedia" or (source == "auto" and _looks_like_wiki(call.query)):
                result = await search_wikipedia(call.query)
                if "error" not in result:
                    return _ok("web_search", {"source": "wikipedia", "results": [result]})
                # fall through to web search on wiki failure
            results = await search_web(call.query, max_results=5)
            return _ok("web_search", {"source": "web", "results": results})
        except Exception as e:
            return _err("web_search", str(e))

    # YouTube ──────────────────────────────────────────────────────────────────
    if isinstance(call, YouTubeOpen):
        from app.tools.web import find_youtube_video
        try:
            result = await find_youtube_video(call.query)
            if "error" in result:
                return _err("youtube_open", result["error"])
            return _ok("youtube_open", result)
        except Exception as e:
            return _err("youtube_open", str(e))

    # Widget forge ────────────────────────────────────────────────────────────
    if isinstance(call, WidgetCreate):
        from app.tools.widget_forge import save_widget
        try:
            record = save_widget(call.name, call.description, call.html_content)
            return _ok("widget_create", record)
        except Exception as e:
            return _err("widget_create", str(e))

    return _err(tool_name, f"Sin dispatcher para {tool_name}.")


def _looks_like_wiki(query: str) -> bool:
    """Heuristic: does this query look like it wants a Wikipedia article?"""
    wiki_keywords = {"qué es", "what is", "who is", "quién es", "historia de",
                     "definición", "definition", "wikipedia", "enciclopedia"}
    q = query.lower()
    return any(kw in q for kw in wiki_keywords)


# ── Frontend UI commands derived from tool results ───────────────────────────


def ui_command_from_result(call: HALToolCall, result: ToolResult) -> dict | None:
    """Translate a tool result into a frontend UI hint (select target on the
    sky chart, show passes panel, etc.).  Returns None if no UI side-effect."""
    if not result.success or result.result is None:
        return None

    if isinstance(call, ObjectPositionQuery) and isinstance(result.result, dict):
        d = result.result
        return {
            "action": "select_target",
            "name": d.get("name"),
            "ra_h": d.get("ra_h"), "dec_deg": d.get("dec_deg"),
            "alt_deg": d.get("alt_deg"), "az_deg": d.get("az_deg"),
            "view": "skyChart",
        }

    if isinstance(call, SatelliteGroundTrack) and isinstance(result.result, list):
        return {"action": "show_ground_track", "view": "earthMap",
                "track_count": len(result.result)}

    if isinstance(call, SatelliteSearch) and isinstance(result.result, list) and result.result:
        first = result.result[0]
        return {"action": "select_satellite",
                "name": first.get("name"), "norad_id": first.get("norad_id")}

    if isinstance(call, SatellitePassesQuery) and isinstance(result.result, list):
        return {"action": "show_passes", "passes": result.result}

    if isinstance(call, SkyTonightQuery) and isinstance(result.result, list):
        return {"action": "refresh_sky_objects", "count": len(result.result)}

    if isinstance(call, (MountGoto, MountTrack, MountPark, MountAbort)):
        return {"action": "mount_command", "result": result.result}

    if isinstance(call, YouTubeOpen) and isinstance(result.result, dict):
        d = result.result
        return {
            "action": "open_youtube",
            "video_id": d.get("video_id"),
            "title": d.get("title"),
            "embed_url": d.get("embed_url"),
            "url": d.get("url"),
        }

    if isinstance(call, WebSearch) and isinstance(result.result, dict):
        sources = result.result.get("results", [])
        if sources:
            return {"action": "show_sources", "sources": sources}

    if isinstance(call, WidgetCreate) and isinstance(result.result, dict):
        d = result.result
        return {
            "action": "new_widget",
            "widget_id": d.get("id"),
            "name": d.get("name"),
        }

    return None
