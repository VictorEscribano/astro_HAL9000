"""Streaming chat endpoint using Server-Sent Events."""
import asyncio
import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

log = logging.getLogger("astroagent.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])


class HistoryMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = []


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    from app.agent.graph import run_agent_stream
    log.info("Chat request: %r (history=%d msgs)", req.message[:80], len(req.history))

    async def event_generator():
        try:
            history = [{"role": m.role, "content": m.content} for m in req.history]
            async for event in run_agent_stream(req.message, history=history):
                payload = json.dumps(event)
                log.debug("SSE event: %s", payload[:120])
                yield f"data: {payload}\n\n"
        except Exception as e:
            log.exception("Agent error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"
            log.info("Stream finished for: %r", req.message[:40])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def chat_health():
    """Check if Ollama is reachable."""
    import httpx
    from app.config import get_settings
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{s.ollama_base_url}/api/tags")
            return {"ok": True, "models": [m["name"] for m in resp.json().get("models", [])]}
    except Exception as e:
        log.warning("Ollama health check failed: %s", e)
        return {"ok": False, "error": str(e)}
