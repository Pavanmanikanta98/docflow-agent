"""
Central configuration — all env vars loaded here.
Never call os.getenv() anywhere else in the codebase.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore leftover env vars (e.g. ENCRYPTION_KEY from old BYOK)
    )

    # LLM (used for all demo requests; users can override via X-LLM-Key header)
    llm_provider: str = Field("groq", env="LLM_PROVIDER")
    llm_model: str = Field("llama-3.1-8b-instant", env="LLM_MODEL")
    groq_api_key: str = Field("", env="GROQ_API_KEY")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Redis / ARQ
    redis_url: str = Field(..., env="REDIS_URL")

    # Rate limiting
    rate_limit_per_session: int = Field(10, env="RATE_LIMIT_PER_SESSION")   # per session per day
    rate_limit_per_ip: int = Field(30, env="RATE_LIMIT_PER_IP")             # per IP per day
    rate_limit_global: int = Field(500, env="RATE_LIMIT_GLOBAL")            # global daily cap

    # App
    allowed_origins: str = Field("http://localhost:3000", env="ALLOWED_ORIGINS")
    confidence_threshold: float = Field(..., env="CONFIDENCE_THRESHOLD")
    max_upload_size_mb: int = Field(..., env="MAX_UPLOAD_SIZE_MB")
    environment: str = Field(..., env="ENVIRONMENT")
    webhook_timeout_seconds: int = Field(..., env="WEBHOOK_TIMEOUT_SECONDS")

settings = Settings()


