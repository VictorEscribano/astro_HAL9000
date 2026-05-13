"""AstroAgent FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.services.cache import init_db
from app.routers import sky, satellites, mount, chat, stel_proxy, voice

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("astroagent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(_warm_ephemeris())
    yield


async def _warm_ephemeris():
    try:
        from app.tools.ephemeris import _get_eph
        _get_eph()
        log.info("Ephemeris loaded (DE421)")
    except Exception as e:
        log.warning("Ephemeris load failed: %s", e)


app = FastAPI(
    title="AstroAgent",
    description="Local AI assistant for astrophotography and visual astronomy",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check first — before the SPA catch-all
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "AstroAgent"}

app.include_router(sky.router)
app.include_router(satellites.router)
app.include_router(mount.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(stel_proxy.router)   # must be before SPA catch-all

# Serve React frontend in production (MUST be last — catch-all)
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(str(FRONTEND_DIST / "index.html"))
