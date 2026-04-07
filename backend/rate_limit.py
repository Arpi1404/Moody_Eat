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


_limiter_state: tuple[int, _SlidingWindowLimiter] | None = None


def _get_limiter(max_rpm: int) -> _SlidingWindowLimiter:
    global _limiter_state
    if _limiter_state is None or _limiter_state[0] != max_rpm:
        _limiter_state = (max_rpm, _SlidingWindowLimiter(max_requests=max_rpm, window_seconds=60.0))
    return _limiter_state[1]


class NearbyPlacesRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-client rate limiting to POST /api/places/nearby only."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled or settings.rate_limit_per_minute <= 0:
            return await call_next(request)
        if request.method != "POST" or request.url.path != "/api/places/nearby":
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_id = forwarded.split(",")[0].strip()
        else:
            client_id = request.client.host if request.client else "unknown"

        limiter = _get_limiter(settings.rate_limit_per_minute)
        if not limiter.is_allowed(client_id):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after_seconds": 60,
                },
            )
        return await call_next(request)
