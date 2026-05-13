"""Per-user profile storage.

Every user that's ever logged in via the UI gets a JSON file at
`backend/data/users/<username>.json`.  The file holds the settings the
user has explicitly saved through the Settings panel:

  - **appearance**: font size, accent colour
  - **session**:    observer location, the last targets / chat
                    history is intentionally NOT persisted here
  - **llm**:        backend choice (ollama / ik_llama), model hint,
                    thinking on/off, response language
  - **voice**:      Kokoro voice, speed, enabled-by-default

A sidecar file `.active` in the same dir stores the username that
`./start.sh` should load on next launch.  We re-create it after every
"switch user" or "create user" so future starts pick up the right
defaults — and `./start.sh` can override via the `HAL_USER` env.

The schema is intentionally permissive (just nested dicts) so the
frontend can add new keys without forcing a backend migration.  We only
parse the user-supplied JSON to assert the username matches the URL
parameter and to enforce a length / charset on the username itself."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

log = logging.getLogger("astroagent.users")

# ── Paths ────────────────────────────────────────────────────────────────────
_USERS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "users"
_USERS_DIR.mkdir(parents=True, exist_ok=True)
_ACTIVE_FILE = _USERS_DIR / ".active"

# ── Validation ───────────────────────────────────────────────────────────────
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-. ]{0,31}$")


def is_valid_username(name: str) -> bool:
    return bool(name and USERNAME_RE.match(name))


# ── Default profile ──────────────────────────────────────────────────────────
class UserProfile(TypedDict, total=False):
    username: str
    created_at: str
    appearance: dict[str, Any]
    session: dict[str, Any]
    llm: dict[str, Any]
    voice: dict[str, Any]


def _default_profile(username: str) -> UserProfile:
    """Sensible defaults for a brand-new user.  Values mirror what the
    frontend's Zustand store falls back to so the first save round-trip
    is idempotent."""
    return {
        "username": username,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "appearance": {
            "fontSize": "md",
            "themeAccent": "red",
        },
        "session": {
            "observer": {
                "name": "Sabadell",
                "lat": 41.548,
                "lng": 2.105,
                "alt_m": 190,
            },
        },
        "llm": {
            "backend": "ik_llama",
            "model_hint": "4b",
            "thinking": True,
            "language": "es",
        },
        "voice": {
            "voice": "ef_dora",
            "speed": 0.9,
            "enabled": False,
        },
    }


# ── Disk I/O (sync helpers, wrapped in to_thread where needed) ───────────────
def _path_for(username: str) -> Path:
    # `username` is validated by the caller; the regex forbids path separators.
    return _USERS_DIR / f"{username}.json"


def _read_sync(username: str) -> UserProfile | None:
    p = _path_for(username)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Corrupt user profile %s: %s", p, e)
        return None


def _write_sync(username: str, data: UserProfile) -> None:
    p = _path_for(username)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)  # atomic on POSIX


def _list_sync() -> list[str]:
    return sorted(
        p.stem for p in _USERS_DIR.glob("*.json") if not p.stem.startswith(".")
    )


def _read_active_sync() -> str | None:
    if _ACTIVE_FILE.is_file():
        try:
            name = _ACTIVE_FILE.read_text(encoding="utf-8").strip()
            return name or None
        except Exception:
            return None
    return None


def _write_active_sync(username: str) -> None:
    _ACTIVE_FILE.write_text(username, encoding="utf-8")


# ── Public async API ─────────────────────────────────────────────────────────


# In-memory active-user pointer.  Initialised lazily on first call so the
# import order doesn't matter; reads first the HAL_USER env var (so
# `./start.sh` can hint the desired user without writing to disk), falls
# back to the .active sentinel, and finally bootstraps a "Victor" profile
# if neither exists.
_active_user: str | None = None
_lock = asyncio.Lock()


def _bootstrap_if_empty() -> None:
    """Ensure at least one user profile exists.  On a fresh install with no
    profiles, create one named `Victor` (the user's name in this project).
    Idempotent.  Sync because it only does small disk I/O — wrap in
    `to_thread` if you need to keep the event loop fully unblocked."""
    if _list_sync():
        return
    default_user = os.environ.get("HAL_USER", "Victor")
    if not is_valid_username(default_user):
        default_user = "Victor"
    _write_sync(default_user, _default_profile(default_user))
    _write_active_sync(default_user)
    log.info("Bootstrapped first user profile: %s", default_user)


async def get_active_user() -> str:
    """Return the currently active username, falling back to env →
    `.active` sentinel → first available → "Victor"."""
    global _active_user
    async with _lock:
        if _active_user is not None:
            return _active_user
        _bootstrap_if_empty()

        # Priority order: explicit env > .active sentinel > first user.
        env_user = os.environ.get("HAL_USER", "").strip()
        existing = await asyncio.to_thread(_list_sync)
        if env_user and env_user in existing:
            _active_user = env_user
        else:
            sentinel = await asyncio.to_thread(_read_active_sync)
            if sentinel and sentinel in existing:
                _active_user = sentinel
            elif existing:
                _active_user = existing[0]
            else:
                _active_user = "Victor"
        return _active_user


async def set_active_user(username: str) -> None:
    global _active_user
    async with _lock:
        existing = await asyncio.to_thread(_list_sync)
        if username not in existing:
            raise ValueError(f"User '{username}' does not exist.")
        _active_user = username
        await asyncio.to_thread(_write_active_sync, username)


async def list_users() -> list[str]:
    await asyncio.to_thread(_bootstrap_if_empty)
    return await asyncio.to_thread(_list_sync)


async def get_user(username: str) -> UserProfile | None:
    return await asyncio.to_thread(_read_sync, username)


async def create_user(username: str) -> UserProfile:
    if not is_valid_username(username):
        raise ValueError(
            "Invalid username — must start with a letter and contain only "
            "letters/digits/spaces/dot/hyphen/underscore (max 32 chars)."
        )
    existing = await asyncio.to_thread(_list_sync)
    if username in existing:
        raise ValueError(f"User '{username}' already exists.")
    profile = _default_profile(username)
    await asyncio.to_thread(_write_sync, username, profile)
    return profile


async def update_user(username: str, settings: dict[str, Any]) -> UserProfile:
    """Merge `settings` into the user's profile.  Top-level keys are
    REPLACED (so the frontend just sends the whole subsection back);
    keys not present in `settings` are preserved.  `username` /
    `created_at` are not overwritable by the client."""
    current = await asyncio.to_thread(_read_sync, username)
    if current is None:
        raise ValueError(f"User '{username}' does not exist.")
    merged: UserProfile = {**current}
    for k, v in settings.items():
        if k in ("username", "created_at"):
            continue
        merged[k] = v  # type: ignore[literal-required]
    await asyncio.to_thread(_write_sync, username, merged)
    return merged


async def delete_user(username: str) -> None:
    global _active_user
    async with _lock:
        path = _path_for(username)
        if path.is_file():
            path.unlink()
        # If we just deleted the active user, point at any remaining one
        # (or recreate the default).
        if _active_user == username:
            remaining = await asyncio.to_thread(_list_sync)
            if remaining:
                _active_user = remaining[0]
                await asyncio.to_thread(_write_active_sync, _active_user)
            else:
                _active_user = None
                if _ACTIVE_FILE.is_file():
                    _ACTIVE_FILE.unlink()
