"""LLM backend factory.

HAL can run against either:

  * **Ollama** — the original target, easy local-dev install, talks the
    Ollama-native API plus an OpenAI-compatible `/v1` endpoint.
  * **ik_llama.cpp** — Iwan Kawrakow's fork of llama.cpp with state-of-the-art
    quantization (IQK / Trellis) and faster CPU + hybrid GPU inference.  Its
    `llama-server` binary exposes only the OpenAI-compatible API.

Both surface OpenAI-shaped chat completions, so the structured-extraction path
(instructor + Pydantic) is identical for both backends — only the base URL
and model name change.

The streaming path is slightly different: `ChatOllama` understands the
Ollama-native streaming protocol and per-request knobs (`num_ctx`,
`num_predict`); for ik_llama we use `ChatOpenAI`, which speaks the OpenAI
streaming protocol and accepts `max_tokens` per request (context size is
configured at server-launch time via `--ctx-size`).

The two factory functions below are the only places that branch on the
backend setting; every caller asks for "the structured client" or "the
streaming chat model" and gets the right thing for the active configuration.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

log = logging.getLogger("astroagent.llm")


def _backend_endpoint(s) -> tuple[str, str]:
    """Return `(openai_compatible_base_url, model_name)` for the active
    backend.  The base URL already includes the `/v1` suffix the OpenAI SDK
    expects."""
    if s.llm_backend == "ik_llama":
        return f"{s.ik_llama_base_url}/v1", s.ik_llama_model
    return f"{s.ollama_base_url}/v1", s.ollama_model


def _ik_llama_extra_body() -> dict:
    """Default `extra_body` payload sent on every OpenAI-style request when
    the backend is ik_llama.cpp.  Qwen3 (and other reasoning-capable Qwen
    variants) enable a `<think>…</think>` block by default — useful for
    one-shot QA but catastrophic for HAL: each turn issues 4 LLM calls
    and 200-300 thinking tokens per call piles up to ~30-40 s of latency.

    Controlled by the `LLM_THINKING` env var (default off).  Setting it true
    lets reasoning-tuned variants (e.g. Qwen3-Thinking, Qwen3.5-A3B with
    thinking on) reason out loud — useful for evaluating quality, painful
    for real-time chat."""
    return {"chat_template_kwargs": {"enable_thinking": get_settings().llm_thinking}}


@lru_cache
def get_instructor_client():
    """Return an `instructor`-wrapped OpenAI client targeting the active LLM
    backend.  This is what the planner / classifier / arg-extractor use to
    force grammar-constrained JSON output."""
    import instructor
    from openai import OpenAI

    s = get_settings()
    base_url, model = _backend_endpoint(s)
    log.info("LLM (instructor) → backend=%s base=%s model=%s",
             s.llm_backend, base_url, model)
    # JSON mode constrains output to valid JSON for our Pydantic schemas.
    # ik_llama.cpp supports it via the same `response_format` param Ollama uses
    # in OpenAI-compat mode.
    client = instructor.from_openai(
        OpenAI(base_url=base_url, api_key=s.llm_backend),  # api_key is unused but required by SDK
        mode=instructor.Mode.JSON,
    )
    # Wrap the chat.completions.create method so every instructor call
    # carries the extra_body that disables thinking on Qwen3.  Doing it
    # here avoids polluting every call site in tools.py.
    if s.llm_backend == "ik_llama":
        _orig_create = client.chat.completions.create
        _extra = _ik_llama_extra_body()

        def _create_with_extra(*args, **kwargs):
            kwargs.setdefault("extra_body", {})
            # Merge our defaults under any caller-supplied values.
            for k, v in _extra.items():
                kwargs["extra_body"].setdefault(k, v)
            return _orig_create(*args, **kwargs)

        client.chat.completions.create = _create_with_extra
    return client


def get_active_model_name() -> str:
    """Used by callers that need the model id for `chat.completions.create`."""
    s = get_settings()
    _, model = _backend_endpoint(s)
    return model


def make_streaming_llm(*, temperature: float = 0.3,
                       num_ctx: int = 8192,
                       num_predict: int = 1024) -> BaseChatModel:
    """Build the streaming chat model used to generate the user-facing reply.

    `num_ctx` only takes effect on Ollama (it's a per-request knob); on
    ik_llama.cpp the context size must be set at server launch with
    `--ctx-size`, so we ignore it.  `num_predict` maps to `max_tokens` for the
    OpenAI/ik_llama path."""
    s = get_settings()
    if s.llm_backend == "ik_llama":
        # langchain-openai has been on requirements since this branch.
        from langchain_openai import ChatOpenAI

        base_url, model = _backend_endpoint(s)
        log.info("LLM (stream) → ik_llama base=%s model=%s", base_url, model)
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key="ik",   # llama-server does not check the key
            temperature=temperature,
            max_tokens=num_predict,
            streaming=True,
            # Pass-through to the OpenAI SDK as `extra_body`; llama-server
            # forwards `chat_template_kwargs` to the Jinja chat template,
            # which lets us disable Qwen3's thinking mode globally.
            extra_body=_ik_llama_extra_body(),
        )

    from langchain_ollama import ChatOllama

    log.info("LLM (stream) → ollama base=%s model=%s",
             s.ollama_base_url, s.ollama_model)
    return ChatOllama(
        model=s.ollama_model,
        base_url=s.ollama_base_url,
        temperature=temperature,
        num_ctx=num_ctx,
        num_predict=num_predict,
    )
