from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    APP_ENV: str = "development"  # development | production
    DATABASE_URL: str = "sqlite:///./careerforge.db"
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h default (was 7d — tighter for security)

    # --- AI keys (never log these) ---
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: Optional[str] = None

    # --- CORS (comma-separated in env) ---
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001"

    # --- DB pool (used for non-SQLite) ---
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # --- Vector store (Chroma) ---
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_ENABLED: bool = True

    # --- Upload / security ---
    MAX_UPLOAD_MB: int = 10
    BCRYPT_ROUNDS: int = 12

    # --- faster-whisper (mock interview STT) ---
    # RTX 4050 defaults: medium.en + auto CUDA + float16.
    # CPU fallback uses small.en + int8 if cuda unavailable or WHISPER_DEVICE=cpu.
    # Models: tiny.en | base.en | small.en | medium.en | medium | large-v3
    WHISPER_MODEL: str = "medium.en"
    # auto = CUDA if GPU + cuBLAS work, else CPU. Set "cpu" if you see cublas64_12.dll errors.
    WHISPER_DEVICE: str = "auto"  # auto | cuda | cpu
    WHISPER_COMPUTE_TYPE: str = "auto"  # auto | float16 | int8 | int8_float16
    WHISPER_DOWNLOAD_DIR: str = ""  # empty = default HuggingFace cache
    WHISPER_CPU_THREADS: int = 0  # 0 = auto
    WHISPER_BEAM_SIZE: int = 5  # final pass (GPU can afford higher)
    WHISPER_BEST_OF: int = 5  # final pass only

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @field_validator("SECRET_KEY")
    @classmethod
    def warn_weak_secret(cls, v: str) -> str:
        if not v or v in {
            "your-super-secret-key-change-in-production",
            "change-me",
            "supersecretkeychangethisinproduction2025",
        }:
            # Allow dev defaults; production check happens at startup
            return v
        if len(v) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        return v


settings = Settings()
