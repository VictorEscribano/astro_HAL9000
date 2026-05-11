"""llama-cpp-python embedded server for HAL9000.

Mounts a llama-cpp-python OpenAI-compatible server as a FastAPI sub-application
at /api/llm — no external process required.  The main HAL backend then uses
http://localhost:8000/api/llm/v1 as its LLM endpoint, which works with both
the instructor (structured extraction) and ChatOpenAI (streaming) paths.

Usage in main.py:
    from app.agent.backends.llamacpp_embed import build_llama_app
    sub = build_llama_app(model_path, n_ctx=8192, n_threads=None)
    if sub:
        app.mount("/api/llm", sub)

Requires: pip install llama-cpp-python[server]
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger("astroagent.backends.llamacpp")


def build_llama_app(
    model_path: str | Path,
    *,
    n_ctx: int = 8192,
    n_threads: int | None = None,
    n_batch: int = 512,
    chat_format: str | None = None,
):
    """Build and return the llama-cpp-python ASGI application, or None on failure.

    The returned app can be mounted into the main FastAPI instance:
        app.mount("/api/llm", build_llama_app(...))

    It will serve:
        POST /api/llm/v1/chat/completions  (streaming + non-streaming)
        GET  /api/llm/v1/models
    """
    try:
        from llama_cpp.server.app import create_app  # type: ignore
        from llama_cpp.server.settings import (  # type: ignore
            ModelSettings,
            ServerSettings,
        )
    except ImportError:
        log.warning(
            "llama-cpp-python[server] not installed — llamacpp backend unavailable. "
            "Install with: pip install 'llama-cpp-python[server]'"
        )
        return None

    model_path = str(model_path)
    if not Path(model_path).exists():
        log.error("GGUF model not found: %s", model_path)
        return None

    cores = n_threads or max(1, (os.cpu_count() or 4) - 1)
    log.info("Building llama-cpp sub-app: model=%s ctx=%d threads=%d", model_path, n_ctx, cores)

    server_settings = ServerSettings(
        host="0.0.0.0",
        port=8000,
    )
    model_settings = [
        ModelSettings(
            model=model_path,
            n_ctx=n_ctx,
            n_threads=cores,
            n_batch=n_batch,
            chat_format=chat_format,
            verbose=False,
        )
    ]

    app = create_app(
        server_settings=server_settings,
        model_settings=model_settings,
    )
    log.info("llama-cpp sub-app built OK")
    return app


def is_available() -> bool:
    """Return True if llama-cpp-python[server] is installed."""
    try:
        import llama_cpp.server.app  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False
