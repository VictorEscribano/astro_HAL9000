"""Whisper speech-to-text service.

Uses `faster-whisper` (CTranslate2 backend) for CPU inference — 4× faster
than the reference PyTorch implementation on the same hardware and with a
fraction of the memory.  INT8 quantization keeps the resident set under
~300 MB for the `small` model so it co-exists with the LLM on a single
laptop without thrashing.

Model size is controlled by the `WHISPER_MODEL` env var (`tiny` /
`base` / `small` / `medium` / `large-v3`); default is `small` which is
the best speed/quality trade-off for short voice queries in Spanish."""

from __future__ import annotations

import asyncio
import io
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("astroagent.whisper")

_MODEL_NAME = os.environ.get("WHISPER_MODEL", "small")
_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")  # "int8" | "float32"
_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")               # "cpu" | "cuda"
# Cache the CT2-converted model under the project's data dir so we don't
# pollute ~/.cache and so it's easy to wipe.
_MODEL_CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "whisper"
_MODEL_CACHE.mkdir(parents=True, exist_ok=True)


class WhisperEngine:
    """Singleton wrapper around faster_whisper.WhisperModel.

    Lazy-loads on first call so import-time cost is paid only when the
    mic actually fires.  Subsequent transcriptions reuse the loaded
    model — first call after start incurs the ~5-10 s download + load,
    later calls run in ~0.5-2 s for typical voice queries."""

    _instance: "WhisperEngine | None" = None

    def __init__(self) -> None:
        self._model = None
        self._lock = asyncio.Lock()

    @classmethod
    def get(cls) -> "WhisperEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel

            def _build() -> Any:
                log.info("Loading Whisper model: %s (device=%s, compute=%s)",
                         _MODEL_NAME, _DEVICE, _COMPUTE_TYPE)
                return WhisperModel(
                    _MODEL_NAME,
                    device=_DEVICE,
                    compute_type=_COMPUTE_TYPE,
                    download_root=str(_MODEL_CACHE),
                )
            self._model = await asyncio.to_thread(_build)
            log.info("Whisper ready (%s, %s, %s)", _MODEL_NAME, _DEVICE, _COMPUTE_TYPE)

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        language: str | None = "es",
        beam_size: int = 5,
    ) -> dict[str, Any]:
        """Decode an in-memory audio blob (any format ffmpeg understands —
        webm/opus from MediaRecorder works directly).  Returns:

            {
              "text":     "concatenated transcription",
              "language": "es",
              "duration": 3.14,             # seconds
            }
        """
        await self._ensure_loaded()

        def _run() -> dict[str, Any]:
            # faster_whisper takes a path or a file-like; BytesIO works.
            buf = io.BytesIO(audio_bytes)
            segments, info = self._model.transcribe(  # type: ignore[union-attr]
                buf,
                language=language,
                beam_size=beam_size,
                vad_filter=True,            # skip leading/trailing silence
                vad_parameters={"min_silence_duration_ms": 300},
            )
            # `segments` is a generator — exhaust it to get the full text.
            parts = [seg.text for seg in segments]
            text = "".join(parts).strip()
            return {
                "text": text,
                "language": info.language,
                "language_probability": float(info.language_probability),
                "duration": float(info.duration),
            }

        return await asyncio.to_thread(_run)
