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

    def is_spent(self, client_id: str) -> bool:
        """Whether the allowance is used up. Counts nothing."""
        dq = self._hits.get(client_id)
        if not dq:
            return False
        oldest_kept = time.monotonic() - self._window
        while dq and dq[0] < oldest_kept:
            dq.popleft()
        return len(dq) >= self._max

    def record(self, client_id: str) -> None:
        self._hits[client_id].append(time.monotonic())


_limiters: dict[str, tuple[int, _SlidingWindowLimiter]] = {}

# Every search by name is a billed Text Search (plus a geocode when the area
# was typed) and nobody needs many a minute, so the bucket has a low ceiling.
_NAME_SEARCH_BUCKET = "name_search"
_BUCKET_CEILINGS = {_NAME_SEARCH_BUCKET: 20}

# A creator's manage key is the only way into their page. Only wrong keys are
# counted; whoever keeps sending them is turned away for a while.
_CREATOR_KEY_PREFIX = "/api/creator/"
_creator_key_failures = _SlidingWindowLimiter(max_requests=10, window_seconds=600.0)


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _guard_creator_key(request: Request, call_next) -> Response:
    client_id = _client_id(request)
    if _creator_key_failures.is_spent(client_id):
        return JSONResponse(
            status_code=429,
            content={
                "detail": {
                    "code": "too_many",
                    "message": "Too many tries with a link that doesn't work. "
                    "Wait a few minutes.",
                },
                "retry_after_seconds": 600,
            },
        )
    response = await call_next(request)
    if response.status_code == 401:
        _creator_key_failures.record(client_id)
    return response


def _get_limiter(bucket: str, max_rpm: int) -> _SlidingWindowLimiter:
    max_rpm = min(max_rpm, _BUCKET_CEILINGS.get(bucket, max_rpm))
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
    ("POST", "/api/places/search"): _NAME_SEARCH_BUCKET,
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
        if request.url.path.startswith(_CREATOR_KEY_PREFIX) and request.method != "OPTIONS":
            return await _guard_creator_key(request, call_next)
        bucket = _LIMITED_ENDPOINTS.get((request.method, request.url.path))
        if bucket is None:
            return await call_next(request)
        max_rpm = _allowance(bucket, settings)
        if max_rpm <= 0:
            return await call_next(request)

        client_id = _client_id(request)
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
