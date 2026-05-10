"""Routes: usage status — lets the frontend show remaining extractions.

GET /usage?session_id=ses_abc123
Returns how many extractions remain for this session today.
"""

import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from backend.core.config import settings
from backend.core.db import redis_client

router = APIRouter(prefix="/usage", tags=["usage"])


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ttl_until_midnight() -> int:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight = midnight + timedelta(days=1)
    return int((next_midnight - now).total_seconds())


@router.get("")
async def get_usage(
    session_id: str = Query("anonymous", description="Browser session ID"),
):
    """Return how many extractions this session has left today.

    The frontend calls this on page load to populate the usage badge.
    """
    today = _today_key()
    session_key = f"ratelimit:session:{session_id}:{today}"

    used = int(redis_client.get(session_key) or 0)
    limit = settings.rate_limit_per_session
    remaining = max(0, limit - used)
    ttl = _ttl_until_midnight()

    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "reset_seconds": ttl,
        "reset_at": int(time.time()) + ttl,
    }
