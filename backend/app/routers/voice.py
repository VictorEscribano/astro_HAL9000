"""Voice synthesis endpoints — frontend talks to Kokoro through here.

The router is intentionally thin: it parses the request, hands the text
off to `KokoroEngine.stream_speech(...)`, and turns each `(sentence, wav)`
the engine yields into an SSE event the browser can play immediately.

The browser plays sentences back-to-back via the Web Audio API; we don't
have to stream a single WAV (which would force the client to wait for the
whole reply to finish synthesising before any audio starts)."""

import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.kokoro_tts import KokoroEngine, process_for_speech
from app.services.whisper_stt import WhisperEngine

log = logging.getLogger("astroagent.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    voice: Optional[str] = Field(default=None,
                                 description="Kokoro voice name; resolved to a sensible default per language if absent.")
    lang: str = Field(default="es",
                      description="BCP-47-ish hint (`es`, `en`, `es-es`, `en-us` …).  Used for default voice + phonemizer.")
    speed: float = Field(default=0.9, ge=0.5, le=1.5,
                         description="Playback rate; <1 slower, >1 faster.")


@router.get("/health")
async def voice_health():
    """Quick capability probe the frontend uses to decide whether to even
    show the voice toggle.  Doesn't load the model — just checks files."""
    eng = KokoroEngine.get()
    return {
        "available": eng.is_available,
        "loaded": eng._loaded,  # noqa: SLF001 — internal flag is fine here
    }


@router.get("/voices")
async def voice_list():
    """Return the catalogue baked into voices-v1.0.bin so the frontend's
    picker stays in sync with whatever voicepack is installed.

    Loads the model on first call (lazy)."""
    eng = KokoroEngine.get()
    if not eng.is_available:
        raise HTTPException(503, "Kokoro model files not present on disk.")
    await eng._ensure_loaded()
    voices = eng.list_voices()
    # Group by leading letter so the UI can render a clean dropdown:
    #   a* = American English, e* = Spanish, b* = British, j* = Japanese, …
    grouped: dict[str, list[str]] = {}
    for v in voices:
        prefix = v[0] if v else "?"
        grouped.setdefault(prefix, []).append(v)
    return {"voices": voices, "grouped": grouped}


@router.post("/speak")
async def voice_speak(req: SpeakRequest):
    """Stream synthesised audio sentence-by-sentence as SSE events.

    Event types yielded:
      - `{type: "filtered", text: str}` — what survived `process_for_speech`,
        sent once up-front so the frontend can show the user what's about
        to be spoken (handy for debug)
      - `{type: "audio", sentence: str, wav_b64: str}` — one WAV per sentence
      - `{type: "done"}` — end of stream
      - `{type: "error", message: str}` — on synth failure (terminal)"""
    eng = KokoroEngine.get()
    if not eng.is_available:
        raise HTTPException(503, "Kokoro model files not present on disk.")

    async def event_generator():
        try:
            # Emit the filtered text upfront so the UI knows what's being
            # vocalised vs what's only visible on the page.
            filtered = process_for_speech(req.text)
            yield f"data: {json.dumps({'type': 'filtered', 'text': filtered})}\n\n"

            if not filtered.strip():
                yield f"data: {json.dumps({'type': 'done', 'reason': 'nothing_to_say'})}\n\n"
                return

            async for sentence, wav in eng.stream_speech(
                req.text,
                voice=req.voice or "",
                lang=req.lang,
                speed=req.speed,
            ):
                payload = {
                    "type": "audio",
                    "sentence": sentence,
                    "wav_b64": base64.b64encode(wav).decode("ascii"),
                }
                yield f"data: {json.dumps(payload)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            log.exception("Kokoro stream failed: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Whisper STT ──────────────────────────────────────────────────────────────


@router.post("/transcribe")
async def voice_transcribe(
    audio: UploadFile = File(..., description="Recorded audio blob (any ffmpeg-readable format; webm/opus from MediaRecorder works)."),
    language: Optional[str] = Form(default=None, description="ISO 639-1 code; if omitted Whisper auto-detects."),
):
    """One-shot transcription: receive an audio blob, return the
    transcribed text.  Frontend pipes the result into the chat input so
    the user can review / edit before sending."""
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio payload.")

    try:
        eng = WhisperEngine.get()
        result = await eng.transcribe(data, language=language)
    except Exception as e:
        log.exception("Whisper transcription failed")
        raise HTTPException(500, f"Transcription failed: {e}")

    log.info("Whisper: %.1fs audio → %d chars (%s, p=%.2f)",
             result.get("duration", 0.0),
             len(result.get("text", "")),
             result.get("language"),
             result.get("language_probability", 0.0))
    return result


@router.get("/transcribe/health")
async def transcribe_health():
    """Frontend uses this to decide whether to even show the MIC button."""
    eng = WhisperEngine.get()
    return {
        "available": True,
        "loaded": eng.is_loaded,
        "model": __import__("os").environ.get("WHISPER_MODEL", "small"),
    }
