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
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b", env="OLLAMA_MODEL")
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
