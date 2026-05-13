"""Web search tool for HAL.

Two providers, tried in order:

  1. **Tavily** — purpose-built for LLM agents, returns clean snippets with
     relevance scores.  Free tier (1000 searches/month) requires an API key
     in `TAVILY_API_KEY`.
  2. **DuckDuckGo** via the `ddgs` library — no key needed but lower
     snippet quality and rate-limited.  Used as a fallback so HAL keeps
     working even without a Tavily account.

Both paths return the same shape so the dispatcher / response generator
doesn't have to branch downstream:

    {
        "query":    str,
        "provider": "tavily" | "duckduckgo",
        "results": [
            { "index": 1, "title": str, "url": str, "snippet": str },
            ...
        ],
    }

`index` is 1-based — the response generator instructs the LLM to cite facts
as `[N]` matching these indices, and the frontend surfaces them as styled
inline references with the URLs available in a footer."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings

log = logging.getLogger("astroagent.web_search")

# Hard upper bound to keep payloads (and the response prompt) reasonable;
# the tool schema enforces a stricter ≤10 but we re-clamp here in case a
# future caller bypasses the schema.
MAX_RESULTS_CAP = 10
SNIPPET_MAX_CHARS = 500


def _trim_snippet(text: str | None) -> str:
    if not text:
        return ""
    s = " ".join(text.split())  # collapse whitespace
    return s if len(s) <= SNIPPET_MAX_CHARS else s[:SNIPPET_MAX_CHARS] + "…"


async def _search_tavily(query: str, n: int, api_key: str) -> list[dict[str, Any]] | None:
    """Hit Tavily's /search endpoint.  Returns None if the call fails so the
    caller can fall back to DuckDuckGo without surfacing a failure."""
    try:
        # Lazy import — keeps tavily-python optional.
        from tavily import TavilyClient
    except ImportError:
        log.info("tavily-python not installed; falling back to DDG")
        return None

    def _call() -> Any:
        client = TavilyClient(api_key=api_key)
        # search_depth="basic" is faster and free-tier friendly; "advanced"
        # crawls deeper but costs 2 credits per call.
        return client.search(query=query, max_results=n, search_depth="basic")

    try:
        raw = await asyncio.to_thread(_call)
    except Exception as e:
        log.warning("tavily search failed (%s) — falling back to DDG", e)
        return None

    results = raw.get("results", []) if isinstance(raw, dict) else []
    return [
        {
            "title":   (r.get("title") or "").strip(),
            "url":     r.get("url") or "",
            "snippet": _trim_snippet(r.get("content")),
            "score":   r.get("score"),
        }
        for r in results
        if r.get("url")
    ][:n]


async def _search_duckduckgo(query: str, n: int) -> list[dict[str, Any]] | None:
    """Backstop search via the `ddgs` library (no API key)."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            # Older package name.
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            log.warning("neither `ddgs` nor `duckduckgo_search` installed — "
                        "no web search backend available")
            return None

    def _call() -> list[dict[str, Any]]:
        with DDGS() as ddg:
            return list(ddg.text(query, max_results=n)) or []

    try:
        raw = await asyncio.to_thread(_call)
    except Exception as e:
        log.warning("ddg search failed: %s", e)
        return None

    return [
        {
            "title":   (r.get("title") or "").strip(),
            "url":     r.get("href") or r.get("url") or "",
            "snippet": _trim_snippet(r.get("body") or r.get("snippet")),
            "score":   None,
        }
        for r in raw
        if r.get("href") or r.get("url")
    ][:n]


async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Run a web search and return a uniform result envelope.

    Raises `RuntimeError` only if BOTH providers are unavailable — anything
    less catastrophic (empty results, rate limit on one path, missing
    library) falls back transparently."""
    n = max(1, min(int(max_results), MAX_RESULTS_CAP))
    s = get_settings()

    results: list[dict[str, Any]] | None = None
    provider = "duckduckgo"

    if s.tavily_api_key:
        results = await _search_tavily(query, n, s.tavily_api_key)
        if results is not None:
            provider = "tavily"

    if results is None:
        results = await _search_duckduckgo(query, n)
        if results is None:
            raise RuntimeError(
                "No web-search backend available. Install `ddgs` "
                "(pip install ddgs) or set TAVILY_API_KEY in .env."
            )

    # Number them 1..N so the LLM can cite as [1], [2], …
    numbered = [
        {"index": i + 1, **r}
        for i, r in enumerate(results)
        if r.get("url")  # drop entries we couldn't extract a URL from
    ]

    log.info("web_search via %s | query=%r | %d results",
             provider, query[:80], len(numbered))

    return {
        "query":    query,
        "provider": provider,
        "results":  numbered,
    }
