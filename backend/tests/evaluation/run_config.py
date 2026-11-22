"""The configuration an evaluation run must record to be reproducible
(issue #40; 17 Nov plan delta R4 item 1d).

A result without the model id, prompt, sampling settings and library
version that produced it cannot be compared with another result, so every
result file written by `run_eval.py` carries this block.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.plugins import REGISTRY
from backend.plugins.base import DocumentPlugin
from backend.tests.evaluation.conftest import GOLDEN_DIR

GOLDEN_FILES = ("invoices.json", "contracts.json")
REPO_ROOT = Path(__file__).resolve().parents[3]

# The extractor does not set a temperature, so the provider default applies.
# Recorded as None on purpose: "not set" is a fact about the run.
EXTRACTION_TEMPERATURE: float | None = None


def prompt_sha256(plugin: DocumentPlugin) -> str:
    """Hash of everything the model is instructed with: the system prompt
    and the output schema (field names and descriptions become the tool
    definition the model sees)."""
    schema = plugin.extraction_schema.model_json_schema()
    payload = plugin.system_prompt + "\n" + json.dumps(schema, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def build_run_config(model_name: str) -> dict[str, Any]:
    """Everything needed to reproduce, or explain a change in, a run."""
    return {
        "model_id": model_name,
        "prompt_sha256": {name: prompt_sha256(p) for name, p in REGISTRY.items()},
        "temperature": EXTRACTION_TEMPERATURE,
        "max_tokens": settings.llm_max_completion_tokens,
        "pydantic_ai_version": _package_version("pydantic-ai-slim")
        or _package_version("pydantic-ai"),
        "golden_sha256": {n: _file_sha256(GOLDEN_DIR / n) for n in GOLDEN_FILES},
        "git_commit": _git_commit(),
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _git_commit() -> str | None:
    """CI exports GITHUB_SHA; locally ask git. None when neither is there."""
    if sha := os.environ.get("GITHUB_SHA"):
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None
