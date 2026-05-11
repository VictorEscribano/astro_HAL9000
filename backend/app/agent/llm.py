"""LLM backend factory.

Four backends supported in this branch (dev_cpu_llms):

  * **ollama** — external Ollama server (original default).
  * **ik_llama** — external ik_llama.cpp llama-server.
  * **llamacpp** — llama-cpp-python embedded as a FastAPI sub-app at
      /api/llm/v1.  No external process needed; the model is loaded in-process.
  * **onnx** — onnxruntime-genai serving a Phi-4-mini or similar ONNX INT4
      model via /api/onnx/v1.  Fastest CPU option (~20 tok/s on modern i7).

All four surface OpenAI-shaped chat completions so the structured-extraction
path (instructor + Pydantic) is identical across backends.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

log = logging.getLogger("astroagent.llm")

# Self-hosted endpoint base URLs (the embedded servers run inside the HAL process)
_LLAMACPP_INTERNAL_BASE = "http://localhost:8000/api/llm/v1"
_ONNX_INTERNAL_BASE = "http://localhost:8000/api/onnx/v1"


def _backend_endpoint(s) -> tuple[str, str]:
    """Return ``(openai_compatible_base_url, model_name)`` for the active backend."""
    if s.llm_backend == "ik_llama":
        return f"{s.ik_llama_base_url}/v1", s.ik_llama_model
    if s.llm_backend == "llamacpp":
        return _LLAMACPP_INTERNAL_BASE, "llamacpp"
    if s.llm_backend == "onnx":
        return _ONNX_INTERNAL_BASE, "onnx"
    # default: ollama
    return f"{s.ollama_base_url}/v1", s.ollama_model


@lru_cache
def get_instructor_client():
    """Return an instructor-wrapped OpenAI client for the active backend.
    Used by the planner / classifier / arg-extractor for JSON-constrained output."""
    import instructor
    from openai import OpenAI

    s = get_settings()
    base_url, model = _backend_endpoint(s)
    log.info("LLM (instructor) → backend=%s  base=%s  model=%s",
             s.llm_backend, base_url, model)
    return instructor.from_openai(
        OpenAI(base_url=base_url, api_key=s.llm_backend),
        mode=instructor.Mode.JSON,
    )


def get_active_model_name() -> str:
    s = get_settings()
    _, model = _backend_endpoint(s)
    return model


def make_streaming_llm(
    *,
    temperature: float = 0.3,
    num_ctx: int = 8192,
    num_predict: int = 1024,
) -> BaseChatModel:
    """Build the streaming LangChain chat model for the user-facing reply.

    Ollama gets per-request num_ctx/num_predict knobs; all other backends
    use ChatOpenAI pointing at their respective OpenAI-compatible endpoints."""
    s = get_settings()

    if s.llm_backend == "ollama":
        from langchain_ollama import ChatOllama
        log.info("LLM (stream) → ollama  model=%s", s.ollama_model)
        return ChatOllama(
            model=s.ollama_model,
            base_url=s.ollama_base_url,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )

    # All non-Ollama backends: use ChatOpenAI pointing at an OpenAI-compat endpoint
    from langchain_openai import ChatOpenAI

    base_url, model = _backend_endpoint(s)
    log.info("LLM (stream) → %s  base=%s  model=%s", s.llm_backend, base_url, model)
    extra: dict = {}
    if s.llm_backend in ("llamacpp", "onnx"):
        # CPU inference can take >2 min for first token on long prompts;
        # disable the LangChain chunk-level timeout entirely.
        extra["stream_chunk_timeout"] = None

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=s.llm_backend,   # not checked by embedded servers
        temperature=temperature,
        max_tokens=num_predict,
        streaming=True,
        **extra,
    )
