"""OpenAI-compatible chat/completions endpoint backed by onnxruntime-genai.

Mounted at /api/onnx/v1 when LLM_BACKEND=onnx, this router exposes:

  POST /api/onnx/v1/chat/completions   (streaming + non-streaming)
  GET  /api/onnx/v1/models

The ChatOpenAI and instructor clients in llm.py point to
http://localhost:8000/api/onnx/v1 so they get the same OpenAI-compatible
interface regardless of which backend is active."""
from __future__ import annotations

import json
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/api/onnx/v1", tags=["onnx-llm"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "onnx"
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int = 1024
    temperature: float = 0.3


def _sse_chunk(delta: str, model: str, finish: bool = False) -> str:
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": delta} if not finish else {},
            "finish_reason": "stop" if finish else None,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


async def _stream_response(req: ChatRequest) -> AsyncGenerator[bytes, None]:
    from app.agent.backends.onnx_engine import stream_chat

    s = get_settings()
    messages = [m.model_dump() for m in req.messages]

    async for token in stream_chat(
        messages,
        s.onnx_model_path,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    ):
        yield _sse_chunk(token, req.model).encode()

    yield _sse_chunk("", req.model, finish=True).encode()
    yield b"data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(req: ChatRequest):
    if req.stream:
        return StreamingResponse(
            _stream_response(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    from app.agent.backends.onnx_engine import complete_chat

    s = get_settings()
    messages = [m.model_dump() for m in req.messages]
    content = await complete_chat(
        messages,
        s.onnx_model_path,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1},
    }


@router.get("/models")
async def list_models():
    s = get_settings()
    return {
        "object": "list",
        "data": [{
            "id": "onnx",
            "object": "model",
            "created": 0,
            "owned_by": "hal9000",
            "root": s.onnx_model_path,
        }],
    }
