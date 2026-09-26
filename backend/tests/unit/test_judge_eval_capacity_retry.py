"""ADR 006/008 — the judge eval must retry a capacity wait (local Redis
token bucket, or a real Groq 429) instead of crashing the whole process.
The first live run hit exactly this: a routine CapacityWaitError with an
8.8s retry hint crashed the script and forced a full restart from
scripts/run_eval_resilient.sh, which works but is wasteful for a wait that
short."""

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from backend.core.token_budget import CapacityWaitError
from backend.tests.evaluation.run_judge_eval import _with_capacity_retry


@pytest.mark.asyncio
async def test_succeeds_immediately_when_no_capacity_error():
    async def call():
        return "ok"

    assert await _with_capacity_retry(call) == "ok"


@pytest.mark.asyncio
async def test_retries_after_a_capacity_wait_error(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = {"count": 0}

    async def call():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise CapacityWaitError(wait_seconds=8.8, model="openai/gpt-oss-120b")
        return "ok"

    result = await _with_capacity_retry(call)
    assert result == "ok"
    assert attempts["count"] == 2
    assert sleeps == [pytest.approx(9.8)]


@pytest.mark.asyncio
async def test_retries_after_a_real_429(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = {"count": 0}

    async def call():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ModelHTTPError(
                status_code=429, model_name="m", headers={"retry-after": "5"}
            )
        return "ok"

    result = await _with_capacity_retry(call)
    assert result == "ok"
    assert sleeps == [pytest.approx(6.0)]


@pytest.mark.asyncio
async def test_non_429_http_error_is_not_retried():
    async def call():
        raise ModelHTTPError(status_code=500, model_name="m")

    with pytest.raises(ModelHTTPError):
        await _with_capacity_retry(call)


@pytest.mark.asyncio
async def test_gives_up_after_max_retries(monkeypatch):
    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    async def call():
        raise CapacityWaitError(wait_seconds=0.1, model="m")

    with pytest.raises(RuntimeError, match="Exceeded"):
        await _with_capacity_retry(call)
