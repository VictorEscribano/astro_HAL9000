from typing import Literal

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
MODELS_DIR = Path(__file__).parent.parent.parent / "models"
EPHEMERIS_CACHE = DATA_DIR / "ephemeris"
EPHEMERIS_CACHE.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    n2yo_api_key: str = Field(default="", env="N2YO_API_KEY")
    observer_lat: float = Field(default=41.548, env="OBSERVER_LAT")
    observer_lng: float = Field(default=2.105, env="OBSERVER_LNG")
    observer_alt_m: float = Field(default=190.0, env="OBSERVER_ALT_M")
    observer_name: str = Field(default="Sabadell", env="OBSERVER_NAME")

    # ── LLM backend ─────────────────────────────────────────────────────────
    # Four backends supported:
    #   ollama       — external Ollama server (original default)
    #   ik_llama     — external ik_llama.cpp llama-server
    #   llamacpp     — llama-cpp-python embedded as FastAPI sub-app at /api/llm/v1
    #   onnx         — onnxruntime-genai embedded, endpoint at /api/onnx/v1
    llm_backend: Literal["ollama", "ik_llama", "llamacpp", "onnx"] = Field(
        default="ollama", env="LLM_BACKEND"
    )

    # -- Ollama (existing) ---------------------------------------------------
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b", env="OLLAMA_MODEL")

    # -- ik_llama (existing) -------------------------------------------------
    ik_llama_base_url: str = Field(default="http://localhost:8080", env="IK_LLAMA_BASE_URL")
    ik_llama_model: str = Field(default="ik", env="IK_LLAMA_MODEL")

    # -- llamacpp embedded ---------------------------------------------------
    # Path to the GGUF model file.  Use MODEL_PROFILE to auto-resolve from
    # the registry (see model_registry.py), or set LLAMACPP_MODEL_PATH directly.
    llamacpp_model_path: str = Field(
        default=str(MODELS_DIR / "qwen3-4b-q4_k_m.gguf"),
        env="LLAMACPP_MODEL_PATH",
    )
    llamacpp_n_ctx: int = Field(default=8192, env="LLAMACPP_N_CTX")
    llamacpp_n_threads: int = Field(default=0, env="LLAMACPP_N_THREADS")  # 0 = auto

    # -- ONNX embedded -------------------------------------------------------
    # Path to the directory containing the ONNX model files.
    # Example: models/phi4mini-onnx/cpu-int4-rtn-block-32
    onnx_model_path: str = Field(
        default=str(MODELS_DIR / "phi4mini-onnx" / "cpu-int4-rtn-block-32"),
        env="ONNX_MODEL_PATH",
    )

    # -- Model profile shortcut ----------------------------------------------
    # Set MODEL_PROFILE=qwen3-4b (or any id from model_registry) to override
    # the llamacpp/onnx model paths automatically.
    model_profile: str = Field(default="", env="MODEL_PROFILE")

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
