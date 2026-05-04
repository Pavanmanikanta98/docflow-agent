"""Test 1: Settings loads without error when all required env vars are set."""

import os
import pytest


def test_config_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that Settings instantiates successfully when every required
    env var is present.  We set them all via monkeypatch so we don't need
    a real .env file or external services."""

    env = {
        "DATABASE_URL": "postgresql://test:test@localhost:5432/test_db",
        "REDIS_URL": "redis://localhost:6379/0",
        "CONFIDENCE_THRESHOLD": "0.7",
        "MAX_UPLOAD_SIZE_MB": "10",
        "ENVIRONMENT": "test",
        "WEBHOOK_TIMEOUT_SECONDS": "30",
        "GROQ_API_KEY": "gsk_fake_key_for_testing",
        "LLM_PROVIDER": "groq",
        "LLM_MODEL": "llama-3.1-8b-instant",
        "ALLOWED_ORIGINS": "http://localhost:3000",
    }

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    # Import inside the test so monkeypatched env is in effect.
    # Settings is instantiated at module level in config.py, so we
    # need to build a fresh instance rather than import the singleton.
    from backend.core.config import Settings

    settings = Settings()

    assert settings.database_url == env["DATABASE_URL"]
    assert settings.redis_url == env["REDIS_URL"]
    assert settings.confidence_threshold == float(env["CONFIDENCE_THRESHOLD"])
    assert settings.max_upload_size_mb == int(env["MAX_UPLOAD_SIZE_MB"])
    assert settings.environment == env["ENVIRONMENT"]
    assert settings.webhook_timeout_seconds == int(env["WEBHOOK_TIMEOUT_SECONDS"])
    assert settings.llm_provider == env["LLM_PROVIDER"]
    assert settings.llm_model == env["LLM_MODEL"]
    assert settings.allowed_origins == env["ALLOWED_ORIGINS"]


def test_config_missing_required_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must raise a validation error when a required field
    (DATABASE_URL) is missing."""

    # Set everything *except* DATABASE_URL
    env = {
        "REDIS_URL": "redis://localhost:6379/0",
        "CONFIDENCE_THRESHOLD": "0.7",
        "MAX_UPLOAD_SIZE_MB": "10",
        "ENVIRONMENT": "test",
        "WEBHOOK_TIMEOUT_SECONDS": "30",
    }

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    # Make sure DATABASE_URL is truly absent
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from backend.core.config import Settings

    with pytest.raises(Exception):
        # _env_file=None prevents pydantic-settings from reading the
        # real .env file on disk — forces it to rely only on env vars.
        Settings(_env_file=None)
