from typing import Literal

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
EPHEMERIS_CACHE = DATA_DIR / "ephemeris"
EPHEMERIS_CACHE.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    n2yo_api_key: str = Field(default="", env="N2YO_API_KEY")
    observer_lat: float = Field(default=41.548, env="OBSERVER_LAT")
    observer_lng: float = Field(default=2.105, env="OBSERVER_LNG")
    observer_alt_m: float = Field(default=190.0, env="OBSERVER_ALT_M")
    observer_name: str = Field(default="Sabadell", env="OBSERVER_NAME")

    # ── LLM backend ─────────────────────────────────────────────────────────
    # Both Ollama and ik_llama.cpp's `llama-server` expose an OpenAI-compatible
    # `/v1/chat/completions` endpoint, so the only thing that changes between
    # backends is the base URL, the model identifier, and (for streaming) which
    # LangChain wrapper we instantiate.  Defaults preserve the Ollama setup so
    # this branch doesn't break the existing dev environment.
    llm_backend: Literal["ollama", "ik_llama"] = Field(default="ollama", env="LLM_BACKEND")
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b", env="OLLAMA_MODEL")
    # ik_llama.cpp's llama-server defaults to port 8080 and ignores the model
    # name (it serves whatever GGUF was loaded at launch time) but the OpenAI
    # client requires *some* string, so we send "ik" by default.
    ik_llama_base_url: str = Field(default="http://localhost:8080", env="IK_LLAMA_BASE_URL")
    ik_llama_model: str = Field(default="ik", env="IK_LLAMA_MODEL")
    # Enable Qwen3-style `<think>…</think>` reasoning blocks on every request.
    # Default OFF because HAL's 4-calls-per-turn flow turns 200-300 thinking
    # tokens/call into ~30-40 s of latency.  Flip to true to let the model
    # reason out loud — useful for evaluating reasoning-tuned variants.
    llm_thinking: bool = Field(default=False, env="LLM_THINKING")

    # Web search — Tavily is preferred (cleaner LLM-tuned snippets, free
    # 1000/mo) but optional; without it the web_search tool falls back to
    # DuckDuckGo via the `ddgs` library (no key, lower quality, rate-limited).
    tavily_api_key: str = Field(default="", env="TAVILY_API_KEY")

    use_voice: bool = Field(default=False, env="USE_VOICE")

    # OAT hardware parameters (OpenAstroTracker)
    oat_steps_per_rev: int = 400           # motor steps/revolution
    oat_microstepping: int = 32            # microstepping factor
    oat_ra_gear_ratio: float = 19.2 * 2.85  # worm × belt reduction
    oat_dec_gear_ratio: float = 19.2 * 1.0
    oat_max_step_rate_hz: float = 2000.0   # max step pulse frequency

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
