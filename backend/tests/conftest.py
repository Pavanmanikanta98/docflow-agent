"""Environment for the unit and integration suites.

``backend.core.config`` builds its ``Settings`` singleton on import and reads
required values from ``.env`` at the repo root. Developers have that file; CI
does not. When it is absent, supply placeholder values so the modules import.
Only the fields declared without a default in ``Settings`` are covered here, and
``setdefault`` keeps any value already exported in the environment.

This file is loaded by pytest before any test module is imported, which is what
makes it run ahead of the ``Settings()`` call.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PLACEHOLDER_ENV = {
    "DATABASE_URL": "postgresql://ci:ci@localhost:5432/ci",
    "REDIS_URL": "redis://localhost:6379/0",
    "CONFIDENCE_THRESHOLD": "0.75",
    "MAX_UPLOAD_SIZE_MB": "10",
    "ENVIRONMENT": "test",
    "WEBHOOK_TIMEOUT_SECONDS": "10",
}

if not (REPO_ROOT / ".env").exists():
    for name, value in PLACEHOLDER_ENV.items():
        os.environ.setdefault(name, value)
