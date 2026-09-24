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
        extra="ignore",  # Ignore leftover env vars (e.g. ENCRYPTION_KEY, now unused)
    )

    # LLM (the server's key is used for every request by default)
    llm_provider: str = Field("groq")
    llm_model: str = Field("openai/gpt-oss-20b")
    groq_api_key: str = Field("")
    openai_api_key: str = Field("")

    # Database
    database_url: str = Field(...)

    # Redis / ARQ
    redis_url: str = Field(...)

    # Rate limiting
    rate_limit_per_session: int = Field(10)  # per session per day
    rate_limit_per_ip: int = Field(30)  # per IP per day
    rate_limit_global: int = Field(500)  # global daily cap

    # App
    allowed_origins: str = Field("http://localhost:3000")
    confidence_threshold: float = Field(...)
    max_upload_size_mb: int = Field(...)
    environment: str = Field(...)
    webhook_timeout_seconds: int = Field(...)
    # Outbound webhooks are off unless explicitly enabled (keep off on the public demo).
    webhooks_enabled: bool = Field(False)
    webhook_secret: str = Field("")

settings = Settings()


