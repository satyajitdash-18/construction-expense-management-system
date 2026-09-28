"""Redis-backed sliding-window rate limiting middleware with in-memory fallback."""

import logging
import math
import time
import uuid
from collections import defaultdict
from typing import Callable, Optional, Set, Tuple

import redis.asyncio as aioredis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window rate limiter supporting Redis with automatic in-memory fallback."""

    def __init__(self, redis_url: str = settings.REDIS_URL) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None
        self._memory_cache: dict[str, list[float]] = defaultdict(list)
        self._redis_available: bool = True

    async def get_redis(self) -> Optional[aioredis.Redis]:
        if not self._redis_available:
            return None
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(
                    "Redis rate limiter unavailable, falling back to in-memory: %s", e
                )
                self._redis_available = False
                self._redis = None
        return self._redis

    async def is_rate_limited(
        self, key: str, limit: int, window_seconds: int
    ) -> Tuple[bool, int, int]:
        """Check whether key exceeds limit within sliding window.

        Returns:
            Tuple[is_limited, current_count, retry_after_seconds]
        """
        now = time.time()
        redis_client = await self.get_redis()

        if redis_client is not None:
            try:
                pipe = redis_client.pipeline(transaction=True)
                window_start = now - window_seconds
                member = f"{now}:{uuid.uuid4().hex[:8]}"

                # Remove entries older than window
                pipe.zremrangebyscore(key, 0, window_start)
                # Add current request
                pipe.zadd(key, {member: now})
                # Count items in set
                pipe.zcard(key)
                # Fetch earliest timestamp to calculate retry-after
                pipe.zrange(key, 0, 0, withscores=True)
                # Set key expiry
                pipe.expire(key, window_seconds + 5)

                results = await pipe.execute()
                current_count = results[2]
                earliest_entries = results[3]

                if current_count > limit:
                    earliest_ts = (
                        earliest_entries[0][1] if earliest_entries else window_start
                    )
                    retry_after = max(1, math.ceil(earliest_ts + window_seconds - now))
                    return True, current_count, retry_after

                return False, current_count, 0
            except Exception as e:
                logger.warning(
                    "Redis error during rate limit check, using in-memory fallback: %s",
                    e,
                )
                self._redis_available = False

        # In-memory fallback
        timestamps = self._memory_cache[key]
        window_start = now - window_seconds
        # Retain only timestamps within the window
        valid_timestamps = [t for t in timestamps if t > window_start]
        valid_timestamps.append(now)
        self._memory_cache[key] = valid_timestamps
        current_count = len(valid_timestamps)

        if current_count > limit:
            earliest_ts = valid_timestamps[0]
            retry_after = max(1, math.ceil(earliest_ts + window_seconds - now))
            return True, current_count, retry_after

        return False, current_count, 0

    async def reset(self) -> None:
        """Clear all rate limit data (used primarily in tests)."""
        self._memory_cache.clear()
        if self._redis is not None:
            try:
                keys = await self._redis.keys("ratelimit:*")
                if keys:
                    await self._redis.delete(*keys)
            except Exception:
                pass


rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware enforcing sliding-window rate limits per client IP."""

    EXEMPT_PATHS: Set[str] = {
        "/api/v1/health",
        "/metrics",
        "/api/v1/openapi.json",
        "/api/v1/docs",
        "/api/v1/redoc",
        "/favicon.ico",
        "/",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path

        # Check exemption
        if path in self.EXEMPT_PATHS or path.startswith("/metrics"):
            return await call_next(request)

        # Determine route category and thresholds
        if path.startswith(f"{settings.API_V1_PREFIX}/auth/login") or path == f"{settings.API_V1_PREFIX}/auth/token":
            limit = settings.RATE_LIMIT_AUTH
            group = "auth"
        elif path.startswith(f"{settings.API_V1_PREFIX}/webhooks"):
            limit = settings.RATE_LIMIT_WEBHOOK
            group = "webhooks"
        else:
            limit = settings.RATE_LIMIT_DEFAULT
            group = "general"

        window = settings.RATE_LIMIT_WINDOW_SECONDS

        # Extract client IP
        client_ip = self._get_client_ip(request)
        rate_key = f"ratelimit:{group}:{client_ip}"

        is_limited, count, retry_after = await rate_limiter.is_rate_limited(
            rate_key, limit, window
        )

        now = int(time.time())
        reset_time = str(now + (retry_after if is_limited else window))

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": reset_time,
                },
            )

        response: Response = await call_next(request)
        remaining = max(0, limit - count)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = reset_time
        return response

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"
