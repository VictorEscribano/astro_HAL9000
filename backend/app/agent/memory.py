"""Episodic memory for HAL, backed by ChromaDB.

Each user has their own collection of "observations" — short text snippets
written at the end of a turn that the agent can recall in later sessions to
maintain continuity ("Last night you imaged M42 with 30s × 60 frames…").

The store degrades gracefully: if ChromaDB isn't installed or fails to load,
`HALMemory` no-ops instead of crashing the chat endpoint."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("astroagent.memory")

# Persist alongside the rest of the runtime data; matches DATA_DIR convention.
_PERSIST_DIR = Path(__file__).parent.parent.parent / "data" / "chroma"


class HALMemory:
    """Thin wrapper around a ChromaDB persistent client.

    All public methods catch and log exceptions instead of bubbling them up —
    a chat turn must never fail because the memory layer is unhappy."""

    def __init__(self, persist_dir: Path | str = _PERSIST_DIR) -> None:
        self._persist_dir = Path(persist_dir)
        self._client = None
        self._available = False
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self._persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._available = True
            log.info("HAL memory online — persisting at %s", self._persist_dir)
        except Exception as e:
            log.warning("HAL memory disabled (ChromaDB unavailable): %s", e)

    @property
    def available(self) -> bool:
        return self._available

    # ── Public API ────────────────────────────────────────────────────────

    def save_observation(
        self,
        user_id: str,
        observation: str,
        *,
        tool_used: str | None = None,
        target_object: str | None = None,
        session_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Persist a single short observation in the user's collection.

        `observation` should be a self-contained sentence ("User imaged M42
        for 60×30 s on 2026-05-06; reported good seeing.") — that's what
        retrieval will surface to the LLM later."""
        if not self._available or not observation.strip():
            return
        try:
            coll = self._collection(user_id)
            metadata: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ts_unix": time.time(),
            }
            if tool_used:     metadata["tool_used"] = tool_used
            if target_object: metadata["target_object"] = target_object
            if session_id:    metadata["session_id"] = session_id
            if extra:         metadata.update({k: str(v) for k, v in extra.items()})
            coll.add(
                ids=[str(uuid.uuid4())],
                documents=[observation],
                metadatas=[metadata],
            )
        except Exception as e:
            log.warning("save_observation failed: %s", e)

    def retrieve_context(self, user_id: str, query: str, top_k: int = 3) -> list[str]:
        """Return up to `top_k` past observations most relevant to `query`."""
        if not self._available or not query.strip():
            return []
        try:
            coll = self._collection(user_id)
            res = coll.query(query_texts=[query], n_results=top_k)
            docs = (res.get("documents") or [[]])[0]
            return [d for d in docs if d]
        except Exception as e:
            log.warning("retrieve_context failed: %s", e)
            return []

    def format_for_prompt(self, user_id: str, query: str, top_k: int = 3) -> str:
        """Convenience: render retrieved snippets as a bullet list, or an
        empty-state placeholder."""
        snippets = self.retrieve_context(user_id, query, top_k=top_k)
        if not snippets:
            return "(sin observaciones previas relevantes)"
        return "\n".join(f"- {s}" for s in snippets)

    # ── Internal ──────────────────────────────────────────────────────────

    def _collection(self, user_id: str):
        # Chroma requires names matching ^[a-zA-Z0-9._-]{3,512}$, so sanitise.
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in user_id) or "default"
        if len(safe) < 3:
            safe = f"user_{safe}"
        return self._client.get_or_create_collection(
            name=f"obs_{safe}",
            metadata={"hnsw:space": "cosine"},
        )


# ── Singleton ────────────────────────────────────────────────────────────────


_INSTANCE: HALMemory | None = None


def get_memory() -> HALMemory:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = HALMemory()
    return _INSTANCE
