"""Simple sliding-window rate limiter for protecting upstream quotas."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import get_settings


class _SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, client_id: str) -> bool:
        now = time.monotonic()
        dq = self._hits[client_id]
        while dq and dq[0] < now - self._window:
            dq.popleft()
        if len(dq) >= self._max:
            return False
        dq.append(now)
        return True


_limiters: dict[str, tuple[int, _SlidingWindowLimiter]] = {}


def _get_limiter(bucket: str, max_rpm: int) -> _SlidingWindowLimiter:
    state = _limiters.get(bucket)
    if state is None or state[0] != max_rpm:
        state = (max_rpm, _SlidingWindowLimiter(max_requests=max_rpm, window_seconds=60.0))
        _limiters[bucket] = state
    return state[1]


# Endpoints that either spend Google quota or write to disk, and the allowance
# each one counts against. Location suggestions fire every few keystrokes, so
# they are counted apart from searches.
_SEARCH_BUCKET = "search"
_SUGGEST_BUCKET = "suggest"
_SWAP_LOG_BUCKET = "swap_log"
_LIMITED_ENDPOINTS = {
    ("POST", "/api/places/nearby"): _SEARCH_BUCKET,
    ("POST", "/api/quest/store"): _SEARCH_BUCKET,
    ("GET", "/api/places/autocomplete"): _SUGGEST_BUCKET,
    ("GET", "/api/places/autocomplete/location"): _SUGGEST_BUCKET,
    ("POST", "/api/quest/swap-log"): _SWAP_LOG_BUCKET,
}

# Nobody confirms more than a few swaps a minute, so the swap log gets a
# small allowance of its own: a script posting to it cannot fill the log
# quickly, and cannot use up a real person's allowance for searches either.
_SWAP_LOG_MAX_PER_MINUTE = 20


def _allowance(bucket: str, settings) -> int:
    """Requests per minute one client may make against `bucket`."""
    if bucket == _SUGGEST_BUCKET:
        return settings.suggest_rate_limit_per_minute
    if bucket == _SWAP_LOG_BUCKET:
        return min(settings.rate_limit_per_minute, _SWAP_LOG_MAX_PER_MINUTE)
    return settings.rate_limit_per_minute


class NearbyPlacesRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-client rate limiting to quota- and disk-spending endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled or settings.rate_limit_per_minute <= 0:
            return await call_next(request)
        bucket = _LIMITED_ENDPOINTS.get((request.method, request.url.path))
        if bucket is None:
            return await call_next(request)
        max_rpm = _allowance(bucket, settings)
        if max_rpm <= 0:
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_id = forwarded.split(",")[0].strip()
        else:
            client_id = request.client.host if request.client else "unknown"

        limiter = _get_limiter(bucket, max_rpm)
        if not limiter.is_allowed(client_id):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after_seconds": 60,
                },
            )
        return await call_next(request)
