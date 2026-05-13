"""Kokoro-TTS engine with text interception filter.

Separates two concerns that used to be tangled in the chat UI:

  1. **Text the user SEES** — the full LLM output, including `<think>` blocks,
     fenced code, headers, bold markers and citation footers.  Untouched by
     this module; the chat panel still renders it via react-markdown.

  2. **Text the user HEARS** — a narrative-only subset produced by
     `process_for_speech(text)`.  Reasoning is dropped (already redundant
     with the visible thinking card), fenced code is skipped (no one wants
     to hear Python syntax read aloud), markdown noise is cleaned, citation
     markers `[1]` are softened to natural pauses, and the result is split
     into sentences so we can stream audio chunk-by-chunk without waiting
     for the entire reply.

Inference runs on CPU via OpenVINOExecutionProvider — much faster than
the default CPUExecutionProvider on x86 because OpenVINO does graph-level
fusions and uses AVX-VNNI / DL Boost where available.  Falls back to plain
CPU if OpenVINO isn't installed."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import wave
from pathlib import Path
from typing import AsyncIterator

import numpy as np

log = logging.getLogger("astroagent.kokoro")

# ── Paths ────────────────────────────────────────────────────────────────────
# Models are downloaded into backend/data/kokoro/ by the setup steps; see
# scripts/README_kokoro.md (or the download lines in start.sh).
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "kokoro"
MODEL_PATH = _DATA_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = _DATA_DIR / "voices-v1.0.bin"

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_VOICE_ES = "ef_dora"     # Spanish female (Kokoro v1.0).  `es_santa`
                                 # is requested by name but the v1 voicepack
                                 # ships `ef_dora`/`em_alex`/`em_santa` —
                                 # callers can pass any name they want;
                                 # we just resolve at runtime.
DEFAULT_VOICE_EN = "af_heart"    # English female warm
DEFAULT_SPEED = 0.9              # pausado / natural

SAMPLE_RATE = 24_000             # Kokoro v1 always outputs 24kHz mono


# espeak (the phonemizer backend Kokoro uses) is strict about language codes:
# bare "en"/"es" raise.  Map our short hints + browser BCP-47 codes to the
# full espeak identifier the tokenizer expects.
_LANG_ALIASES = {
    "en":    "en-us",
    "en_us": "en-us",
    "en-gb": "en-gb",
    "en-us": "en-us",
    "es":    "es",
    "es-es": "es",
    "es-mx": "es",
    "es_es": "es",
    "fr":    "fr-fr",
    "fr-fr": "fr-fr",
    "it":    "it",
    "pt":    "pt-br",
    "pt-br": "pt-br",
    "pt-pt": "pt",
    "ja":    "ja",
    "zh":    "cmn",
    "hi":    "hi",
}


def _normalize_lang(lang: str) -> str:
    """Return an espeak-compatible language code for `lang`.  Accepts the
    short forms we use in the API (`es`, `en`) and the browser BCP-47 forms
    (`es-ES`, `en-US`)."""
    key = (lang or "en").lower().strip()
    if key in _LANG_ALIASES:
        return _LANG_ALIASES[key]
    # Fallback: take the leading 2 chars and re-check.
    short = key.split("-")[0].split("_")[0]
    return _LANG_ALIASES.get(short, "en-us")


# ── Text interceptor ─────────────────────────────────────────────────────────


_RE_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_RE_THOUGHT = re.compile(r"<thought>.*?</thought>", re.IGNORECASE | re.DOTALL)
_RE_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`([^`]+)`")
_RE_BOLD_STAR = re.compile(r"\*\*(.+?)\*\*")
_RE_BOLD_UNDER = re.compile(r"__(.+?)__")
_RE_ITALIC_STAR = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_RE_ITALIC_UNDER = re.compile(r"(?<!_)_([^_]+)_(?!_)")
_RE_HEADER = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_RE_CITATION = re.compile(r"\s*\[\d+\]")                  # `[1]`, `[12]`
_RE_SOURCES_FOOTER = re.compile(                          # "Fuentes:\n[1] … — URL"
    r"\n\s*(?:Fuentes|Sources|Referencias)\s*:.*$",
    re.IGNORECASE | re.DOTALL,
)
_RE_URL = re.compile(r"https?://\S+")
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")        # [text](url) → text
_RE_LIST_BULLET = re.compile(r"^\s*[-*]\s+", re.MULTILINE)
_RE_MULTI_BLANK = re.compile(r"\n{3,}")
_RE_WHITESPACE = re.compile(r"[ \t]+")

# Sentence boundary: terminator (.!?…) followed by whitespace OR end of string.
# Keep the terminator with the sentence.  Tolerates trailing quotes/parens.
_RE_SENT_SPLIT = re.compile(r'(?<=[.!?…])["\')\]]*\s+(?=[A-ZÁÉÍÓÚÑ¿¡])')


def process_for_speech(text: str) -> str:
    """Strip everything that shouldn't reach the audio buffer.

    Operates in a fixed order so the filters compose predictably:
      1. drop `<think>` / `<thought>` (already shown in the thinking card)
      2. drop fenced ```…``` blocks
      3. drop the "Fuentes:" footer (URLs read aloud are awful)
      4. drop bare URLs (in case the model embeds one inline)
      5. flatten `[text](url)` → `text`
      6. drop citation markers `[1]`, `[12]`
      7. remove markdown structure (headers, bold, italic, list bullets,
         inline code backticks)
      8. collapse whitespace
    """
    s = text
    s = _RE_THINK.sub("", s)
    s = _RE_THOUGHT.sub("", s)
    s = _RE_FENCED_CODE.sub("", s)
    s = _RE_SOURCES_FOOTER.sub("", s)
    s = _RE_MD_LINK.sub(r"\1", s)
    s = _RE_URL.sub("", s)
    s = _RE_CITATION.sub("", s)
    s = _RE_HEADER.sub("", s)
    s = _RE_BOLD_STAR.sub(r"\1", s)
    s = _RE_BOLD_UNDER.sub(r"\1", s)
    s = _RE_ITALIC_STAR.sub(r"\1", s)
    s = _RE_ITALIC_UNDER.sub(r"\1", s)
    s = _RE_LIST_BULLET.sub("", s)
    s = _RE_INLINE_CODE.sub(r"\1", s)
    s = _RE_MULTI_BLANK.sub("\n\n", s)
    s = _RE_WHITESPACE.sub(" ", s)
    return s.strip()


def split_sentences(text: str, min_len: int = 12) -> list[str]:
    """Break `text` into sentences for streaming TTS.

    `min_len` collapses very short fragments into the next sentence so we
    don't churn the model for one-word chunks ("Sí.", "OK.")."""
    if not text:
        return []
    raw = _RE_SENT_SPLIT.split(text)
    out: list[str] = []
    buf = ""
    for piece in raw:
        piece = piece.strip()
        if not piece:
            continue
        combined = f"{buf} {piece}".strip() if buf else piece
        if len(combined) < min_len:
            buf = combined
            continue
        out.append(combined)
        buf = ""
    if buf:
        # Tail too short on its own — append to last sentence if any,
        # else emit alone (better short audio than dropped content).
        if out:
            out[-1] = f"{out[-1]} {buf}"
        else:
            out.append(buf)
    return out


# ── Engine ───────────────────────────────────────────────────────────────────


def _pcm_to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    """Wrap a float32 PCM array in a WAV header so a browser <audio> tag
    can play it without any decoding library on the frontend."""
    pcm16 = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16.tobytes())
    return buf.getvalue()


class KokoroEngine:
    """Singleton-friendly Kokoro-TTS wrapper with text interception.

    Construction is lazy: the ONNX session is only built on the first
    `synth*` call so import-time cost is paid only when voice is actually
    used.  Subsequent calls reuse the loaded session."""

    _instance: "KokoroEngine | None" = None

    def __init__(self) -> None:
        self._kokoro = None
        self._loaded = False
        self._load_lock = asyncio.Lock()

    @classmethod
    def get(cls) -> "KokoroEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_available(self) -> bool:
        """Cheap predicate the router uses to decide whether voice synthesis
        is possible at all (i.e. model files are on disk)."""
        return MODEL_PATH.is_file() and VOICES_PATH.is_file()

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            if not self.is_available:
                raise RuntimeError(
                    f"Kokoro model files missing.  Expected:\n"
                    f"  {MODEL_PATH}\n  {VOICES_PATH}\n"
                    f"Download from https://github.com/thewh1teagle/kokoro-onnx/releases."
                )

            # Build a session.  Prefer OpenVINOExecutionProvider for the
            # graph fusions + AVX-VNNI it enables on x86 CPUs, but fall back
            # to plain CPUExecutionProvider if OpenVINO refuses the graph
            # (Kokoro contains an STFT op the OpenVINO CPU plugin currently
            # rejects, so on a fresh install we systematically hit that).
            import os
            import onnxruntime as ort

            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = max(2, (os.cpu_count() or 4) // 2)
            available = ort.get_available_providers()
            session = None
            chosen_providers: list = []

            if "OpenVINOExecutionProvider" in available:
                try:
                    chosen_providers = [
                        ("OpenVINOExecutionProvider", {"device_type": "CPU"}),
                        "CPUExecutionProvider",
                    ]
                    session = ort.InferenceSession(
                        str(MODEL_PATH), sess_options=sess_opts,
                        providers=chosen_providers,
                    )
                    log.info("Kokoro session ready via OpenVINO (CPU)")
                except Exception as e:
                    log.warning("Kokoro: OpenVINO load failed (%s) — "
                                "falling back to plain CPUExecutionProvider",
                                str(e).splitlines()[0][:200])
                    session = None

            if session is None:
                try:
                    session = ort.InferenceSession(
                        str(MODEL_PATH), sess_options=sess_opts,
                        providers=["CPUExecutionProvider"],
                    )
                    log.info("Kokoro session ready — providers: %s",
                             session.get_providers())
                except Exception:
                    log.exception("Kokoro: failed to build ONNX session")
                    raise

            # kokoro_onnx exposes `from_session(session, voices_path)` to
            # reuse an externally-built session.  If that's not available,
            # fall back to the high-level constructor (which builds its own
            # default session — usually CPU).
            from kokoro_onnx import Kokoro

            if hasattr(Kokoro, "from_session"):
                self._kokoro = Kokoro.from_session(session, str(VOICES_PATH))
            else:
                self._kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))

            self._loaded = True

    def list_voices(self) -> list[str]:
        """Return the catalogue of voices baked into voices-v1.0.bin.  Useful
        for the frontend's voice picker."""
        if not self._loaded:
            # Pre-loading just to list voices is wasteful; return [] and let
            # the caller hit `/api/voice/voices` later when needed.
            return []
        try:
            return sorted(self._kokoro.get_voices())  # type: ignore[union-attr]
        except Exception:
            return []

    def resolve_voice(self, voice: str | None, lang: str) -> str:
        """Map a friendly voice name to one that's actually present in the
        voicepack.  Honours the user's choice when possible; falls back to a
        sensible default per language."""
        if self._kokoro is None:
            return voice or (DEFAULT_VOICE_ES if lang.startswith("es") else DEFAULT_VOICE_EN)
        try:
            available = set(self._kokoro.get_voices())
        except Exception:
            available = set()
        if voice and voice in available:
            return voice
        # Try common aliases first ("es_santa" → "em_santa" etc.)
        if voice:
            for cand in (voice.replace("es_", "em_"),
                         voice.replace("es_", "ef_"),
                         voice.replace("en_", "af_"),
                         voice.replace("en_", "am_")):
                if cand in available:
                    return cand
        # Fall back by language prefix
        prefix = "e" if lang.startswith("es") else "a"
        for cand in available:
            if cand.startswith(prefix):
                return cand
        # Last resort: anything present
        return next(iter(available), voice or DEFAULT_VOICE_EN)

    async def synth_sentence(
        self,
        text: str,
        *,
        voice: str = DEFAULT_VOICE_ES,
        lang: str = "es",
        speed: float = DEFAULT_SPEED,
    ) -> bytes:
        """One-shot synth for a single sentence.  Returns WAV bytes."""
        await self._ensure_loaded()
        resolved = self.resolve_voice(voice, lang)
        normalised = _normalize_lang(lang)
        # kokoro-onnx's `create()` is synchronous CPU-bound — push it onto a
        # thread so the event loop stays free for the SSE writer.
        audio, sr = await asyncio.to_thread(
            self._kokoro.create,  # type: ignore[union-attr]
            text, resolved, speed, normalised,
        )
        return _pcm_to_wav(audio, sr)

    async def stream_speech(
        self,
        full_text: str,
        *,
        voice: str = DEFAULT_VOICE_ES,
        lang: str = "es",
        speed: float = DEFAULT_SPEED,
    ) -> AsyncIterator[tuple[str, bytes]]:
        """High-level streaming entry point.

        Pipeline:
          1. Filter LLM output → narrative-only text
          2. Split into sentences
          3. Synthesize each sentence, yield `(sentence_text, wav_bytes)`

        The router wraps these in SSE events so the frontend can play audio
        chunks back-to-back as they arrive (no need to wait for the whole
        response to finish synthesising)."""
        clean = process_for_speech(full_text)
        sentences = split_sentences(clean)
        if not sentences:
            return
        await self._ensure_loaded()
        for s in sentences:
            wav = await self.synth_sentence(s, voice=voice, lang=lang, speed=speed)
            yield s, wav
