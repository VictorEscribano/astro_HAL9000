"""SQLite-backed cache for TLEs and rate-limit tracking."""
import aiosqlite
import asyncio
import json
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "data" / "astroagent.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tle_cache (
                norad_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                line1 TEXT NOT NULL,
                line2 TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS n2yo_rate (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                calls_this_hour INTEGER NOT NULL DEFAULT 0,
                hour_start REAL NOT NULL
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO n2yo_rate (id, calls_this_hour, hour_start)
            VALUES (1, 0, ?)
        """, (time.time(),))
        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await db.commit()


async def get_tle(norad_id: int, max_age_s: float = 3600.0) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name, line1, line2, fetched_at FROM tle_cache WHERE norad_id = ?",
            (norad_id,)
        ) as cur:
            row = await cur.fetchone()
            if row and (time.time() - row[3]) < max_age_s:
                return {"name": row[0], "line1": row[1], "line2": row[2], "fetched_at": row[3]}
    return None


async def put_tle(norad_id: int, name: str, line1: str, line2: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO tle_cache (norad_id, name, line1, line2, fetched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (norad_id, name, line1, line2, time.time())
        )
        await db.commit()


async def check_rate_limit(cost: int = 1) -> bool:
    """Returns True if the call is allowed, increments counter."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT calls_this_hour, hour_start FROM n2yo_rate WHERE id = 1") as cur:
            row = await cur.fetchone()
        calls, hour_start = row
        if now - hour_start >= 3600:
            calls = 0
            hour_start = now
        if calls + cost > 990:  # stay under 1000/hr limit
            return False
        await db.execute(
            "UPDATE n2yo_rate SET calls_this_hour = ?, hour_start = ? WHERE id = 1",
            (calls + cost, hour_start)
        )
        await db.commit()
    return True


async def save_message(role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO session_history (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, time.time())
        )
        await db.commit()
