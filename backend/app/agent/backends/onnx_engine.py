"""ONNX Runtime GenAI inference engine for HAL9000.

Wraps microsoft/onnxruntime-genai to provide a streaming token generator
compatible with the existing HAL SSE pipeline.  Loaded lazily on first use
so the module can be imported even when onnxruntime-genai is not installed
(the import only fails at generate-time, not at startup).

Recommended models (download via setup_cpu_llm.sh):
  - microsoft/Phi-4-mini-instruct-onnx  (cpu-int4-rtn-block-32 subfolder)
  - microsoft/Phi-3.5-mini-instruct-onnx-cpu
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import AsyncGenerator

log = logging.getLogger("astroagent.backends.onnx")

# Module-level singletons — loaded once, reused across requests
_model = None
_tokenizer = None
_model_path: str | None = None


def _load_model(model_path: str) -> None:
    global _model, _tokenizer, _model_path
    if _model is not None and _model_path == model_path:
        return
    try:
        import onnxruntime_genai as og  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "onnxruntime-genai not installed. "
            "Run: pip install onnxruntime-genai"
        ) from exc

    log.info("Loading ONNX model from %s …", model_path)
    _model = og.Model(model_path)
    _tokenizer = og.Tokenizer(_model)
    _model_path = model_path
    log.info("ONNX model ready.")


def _apply_chat_template(messages: list[dict], model_path: str) -> str:
    """Format messages using the model's Jinja2 chat template via transformers.

    Falls back to a basic system/user/assistant format if transformers is not
    available (handles Phi-4-mini's <|im_start|> format natively)."""
    try:
        from transformers import AutoTokenizer  # type: ignore
        hf_tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        return hf_tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        pass

    # Fallback: Phi/Qwen chatml format
    parts: list[str] = []
    for m in messages:
        role, content = m.get("role", "user"), m.get("content", "")
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


async def stream_chat(
    messages: list[dict],
    model_path: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """Yield tokens as strings, streaming from the ONNX model.

    Runs the CPU-bound generation loop in a thread so the asyncio event
    loop stays responsive for SSE delivery."""

    def _generate():
        import onnxruntime_genai as og  # type: ignore
        _load_model(model_path)

        prompt = _apply_chat_template(messages, model_path)
        input_tokens = _tokenizer.encode(prompt)

        params = og.GeneratorParams(_model)
        params.set_search_options(
            max_length=len(input_tokens) + max_tokens,
            temperature=temperature,
            do_sample=temperature > 0.0,
            top_p=0.9,
        )
        params.input_ids = input_tokens

        token_stream = _tokenizer.create_stream()
        generator = og.Generator(_model, params)
        tokens: list[str] = []
        while not generator.is_done():
            generator.compute_logits()
            generator.generate_next_token()
            new_token = generator.get_next_tokens()[0]
            decoded = token_stream.decode(new_token)
            tokens.append(decoded)
        del generator
        return tokens

    tokens = await asyncio.to_thread(_generate)
    for tok in tokens:
        yield tok


async def complete_chat(
    messages: list[dict],
    model_path: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.1,
) -> str:
    """Non-streaming completion — used by instructor for structured extraction."""
    chunks: list[str] = []
    async for tok in stream_chat(messages, model_path,
                                 max_tokens=max_tokens, temperature=temperature):
        chunks.append(tok)
    return "".join(chunks)


def is_available() -> bool:
    """Return True if onnxruntime-genai is installed."""
    try:
        import onnxruntime_genai  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False
