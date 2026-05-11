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
from app.routers import sky, satellites, mount, chat, stel_proxy, widgets
from app.config import get_settings

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
    asyncio.create_task(_log_model_info())
    yield


async def _warm_ephemeris():
    try:
        from app.tools.ephemeris import _get_eph
        _get_eph()
        log.info("Ephemeris loaded (DE421)")
    except Exception as e:
        log.warning("Ephemeris load failed: %s", e)


async def _log_model_info():
    """Log the active LLM configuration and Pareto recommendation at startup."""
    try:
        from app.services.model_registry import pareto_table, recommend
        s = get_settings()
        log.info("LLM backend: %s", s.llm_backend)
        if s.model_profile:
            log.info("Model profile: %s", s.model_profile)
        log.info("CPU model Pareto table:\n%s", pareto_table())
    except Exception as e:
        log.debug("Model registry log failed: %s", e)


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
app.include_router(stel_proxy.router)   # must be before SPA catch-all
app.include_router(widgets.router)

# ── CPU LLM backends (dev_cpu_llms branch) ───────────────────────────────────
_s = get_settings()

if _s.llm_backend == "llamacpp":
    from app.agent.backends.llamacpp_embed import build_llama_app
    _threads = _s.llamacpp_n_threads or None
    _llama_sub = build_llama_app(
        _s.llamacpp_model_path,
        n_ctx=_s.llamacpp_n_ctx,
        n_threads=_threads,
    )
    if _llama_sub:
        app.mount("/api/llm", _llama_sub)
        log.info("llama-cpp sub-app mounted at /api/llm")
    else:
        log.error("llamacpp backend configured but model could not be loaded.")

elif _s.llm_backend == "onnx":
    from app.routers.onnx_chat import router as onnx_router
    app.include_router(onnx_router)
    log.info("ONNX chat router mounted at /api/onnx/v1")

# Serve React frontend in production (MUST be last — catch-all)
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(str(FRONTEND_DIST / "index.html"))
