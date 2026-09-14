"""3-layer rate limiting middleware.

LAYER 1: Per-session  — 10 extractions/day (tracked by X-Session-Id header)
LAYER 2: Per-IP       — 30 extractions/day (backstop against session farming)
LAYER 3: Global       — 500 extractions/day (absolute budget ceiling)

BYPASS: Only when ALLOW_USER_LLM_KEY=true — a request carrying an X-LLM-Key
header pays its own LLM bill, so it skips the limits. When the setting is false
(the default), the header is ignored and normal limits apply; otherwise anyone
could bypass the limits by sending any string in that header.

HOW IT WORKS:
─────────────
1. Middleware intercepts every POST /documents/upload request
2. Checks Redis counters for session + IP + global
3. If any limit is exceeded → returns 429 with JSON body
4. If allowed → increments all counters and continues
5. Response headers tell the frontend how many requests remain

IMPORTANT: The X-LLM-Key header is NEVER logged, stored, or included
in error tracking. It passes through to the pipeline for one request
and is then garbage-collected from memory.
"""

import time
from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.core.config import settings

# Which routes are rate-limited (only the expensive LLM operation)
RATE_LIMITED_PATHS = {"/api/v1/documents/upload"}

# Sensitive headers that must NEVER be logged
SENSITIVE_HEADERS = {"x-llm-key"}


def _get_redis():
    """Lazy import to avoid circular dependency."""
    from backend.core.db import redis_client
    return redis_client


def _today_key() -> str:
    """Return today's date string for Redis key namespacing (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ttl_until_midnight() -> int:
    """Seconds until midnight UTC — TTL for daily counters."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Add 1 day to get next midnight
    from datetime import timedelta
    next_midnight = midnight + timedelta(days=1)
    return int((next_midnight - now).total_seconds())


def _limit_message() -> str:
    """429 message; only mention bringing your own key when that is enabled."""
    if settings.allow_user_llm_key:
        return (
            "You've used all your free extractions for today. "
            "Send your own Groq API key to continue, "
            "or get in touch for production access."
        )
    return (
        "You've used all your free extractions for today. "
        "Come back tomorrow, or get in touch for production access."
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces 3-layer rate limiting on upload requests."""

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit specific paths
        if request.url.path not in RATE_LIMITED_PATHS or request.method != "POST":
            return await call_next(request)

        # BYPASS: user-supplied LLM key skips limits — only if the feature is on
        if settings.allow_user_llm_key and request.headers.get("x-llm-key"):
            response = await call_next(request)
            response.headers["X-RateLimit-Bypassed"] = "true"
            return response

        redis = _get_redis()
        today = _today_key()
        ttl = _ttl_until_midnight()

        # --- Resolve identifiers ---
        session_id = request.headers.get("x-session-id", "anonymous")
        client_ip = request.client.host if request.client else "unknown"

        # --- Redis keys ---
        session_key = f"ratelimit:session:{session_id}:{today}"
        ip_key = f"ratelimit:ip:{client_ip}:{today}"
        global_key = f"ratelimit:global:{today}"

        # --- Read current counts ---
        pipe = redis.pipeline()
        pipe.get(session_key)
        pipe.get(ip_key)
        pipe.get(global_key)
        session_count, ip_count, global_count = pipe.execute()

        session_count = int(session_count or 0)
        ip_count = int(ip_count or 0)
        global_count = int(global_count or 0)

        # --- Check limits (most specific → least specific) ---
        limit_hit = None
        limit_value = 0

        if session_count >= settings.rate_limit_per_session:
            limit_hit = "session"
            limit_value = settings.rate_limit_per_session
        elif ip_count >= settings.rate_limit_per_ip:
            limit_hit = "ip"
            limit_value = settings.rate_limit_per_ip
        elif global_count >= settings.rate_limit_global:
            limit_hit = "global"
            limit_value = settings.rate_limit_global

        if limit_hit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Demo limit reached",
                    "limit_type": limit_hit,
                    "limit": limit_value,
                    "used": (
                        session_count
                        if limit_hit == "session"
                        else ip_count
                        if limit_hit == "ip"
                        else global_count
                    ),
                    "reset_seconds": ttl,
                    "message": _limit_message(),
                },
                headers={
                    "X-RateLimit-Limit": str(settings.rate_limit_per_session),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + ttl),
                    "Retry-After": str(ttl),
                },
            )

        # --- Allowed: increment all counters atomically ---
        pipe = redis.pipeline()
        pipe.incr(session_key)
        pipe.expire(session_key, ttl)
        pipe.incr(ip_key)
        pipe.expire(ip_key, ttl)
        pipe.incr(global_key)
        pipe.expire(global_key, ttl)
        pipe.execute()

        session_remaining = max(0, settings.rate_limit_per_session - session_count - 1)

        # --- Process the request ---
        response = await call_next(request)

        # --- Attach rate limit headers to the response ---
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_session)
        response.headers["X-RateLimit-Remaining"] = str(session_remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + ttl)

        return response
