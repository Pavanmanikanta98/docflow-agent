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
    )

    # LLM
    llm_provider: str = Field(..., env="LLM_PROVIDER")
    llm_model: str = Field(..., env="LLM_MODEL")
    groq_api_key: str = Field(..., env="GROQ_API_KEY")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Redis / ARQ
    redis_url: str = Field(..., env="REDIS_URL")

    # App
    confidence_threshold: float = Field(..., env="CONFIDENCE_THRESHOLD")
    max_upload_size_mb: int = Field(..., env="MAX_UPLOAD_SIZE_MB")
    environment: str = Field(..., env="ENVIRONMENT")
    webhook_timeout_seconds: int = Field(..., env="WEBHOOK_TIMEOUT_SECONDS")

settings = Settings()


