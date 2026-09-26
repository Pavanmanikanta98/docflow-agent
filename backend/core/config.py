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
    # Override Groq's base URL to point at scripts/fake_groq.py for a local
    # load test (ADR 006). Empty means "use Groq's real endpoint" — never set
    # in a real deployment.
    groq_base_url: str = Field("")

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

    # ADR 006 — token budget (Groq free tier: 30 RPM, 1K RPD, 8K TPM, 200K TPD).
    # Moving to a paid tier is an env change, not a code change.
    llm_tpm: int = Field(8000)
    llm_rpm: int = Field(30)
    llm_tpd: int = Field(200000)
    llm_rpd: int = Field(1000)
    llm_max_completion_tokens: int = Field(1024)
    # How many documents one browser session may have in flight at once,
    # so one visitor's batch upload cannot starve everyone else's queue.
    session_inflight_cap: int = Field(2)

settings = Settings()


