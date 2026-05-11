"""Web, Wikipedia and YouTube search tools for HAL.

All searches run in asyncio.to_thread so the event loop stays free.
Sources are returned as structured dicts so the frontend can render
clickable hyperlinks without trusting LLM-generated URLs."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

log = logging.getLogger("astroagent.tools.web")


# ── DuckDuckGo web search ──────────────────────────────────────────────────


async def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Full-text web search via DuckDuckGo (no API key required).

    Returns a list of {title, url, snippet} dicts ordered by relevance."""
    def _do() -> list[dict[str, str]]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                raw = ddgs.text(query, max_results=max_results)
            return [
                {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                for r in raw
            ]
        except Exception as exc:
            log.warning("DDG text search failed: %s", exc)
            return []

    return await asyncio.to_thread(_do)


# ── Wikipedia ─────────────────────────────────────────────────────────────


async def search_wikipedia(query: str, lang: str = "es") -> dict[str, Any]:
    """Return the Wikipedia summary + URL for the best matching article.

    Falls back to English if the Spanish article is not found."""
    def _do() -> dict[str, Any]:
        try:
            import wikipedia as _wiki  # type: ignore
            _wiki.set_lang(lang)
            try:
                page = _wiki.page(_wiki.search(query, results=1)[0], auto_suggest=False)
            except (_wiki.DisambiguationError, IndexError):
                if lang != "en":
                    _wiki.set_lang("en")
                    page = _wiki.page(_wiki.search(query, results=1)[0], auto_suggest=False)
                else:
                    return {"error": f"Artículo no encontrado: {query}"}
            return {
                "title": page.title,
                "summary": page.summary[:800],
                "url": page.url,
                "source": "wikipedia",
            }
        except Exception as exc:
            log.warning("Wikipedia search failed: %s", exc)
            return {"error": str(exc)}

    return await asyncio.to_thread(_do)


# ── YouTube ────────────────────────────────────────────────────────────────


def _extract_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else None


async def find_youtube_video(query: str) -> dict[str, str]:
    """Find the most relevant YouTube video for a query.

    Uses DuckDuckGo site:youtube.com search — no YouTube API key needed.
    Returns {video_id, title, url, embed_url}."""
    def _do() -> dict[str, str]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(f"site:youtube.com {query}", max_results=8))
            for r in results:
                url = r.get("href", "")
                vid = _extract_video_id(url)
                if vid:
                    return {
                        "video_id": vid,
                        "title": r.get("title", query),
                        "url": url,
                        "embed_url": f"https://www.youtube.com/embed/{vid}?autoplay=1",
                    }
            return {"error": f"No YouTube video found for: {query}"}
        except Exception as exc:
            log.warning("YouTube search failed: %s", exc)
            return {"error": str(exc)}

    return await asyncio.to_thread(_do)
