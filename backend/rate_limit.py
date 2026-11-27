"""Simple sliding-window rate limiter for protecting upstream quotas."""

from __future__ import annotations

import ipaddress
import re
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import get_settings


# Callers with nothing left in their window are swept out once a table holds
# this many, so it cannot grow for as long as the process lives.
_SWEEP_AT = 5_000


class _SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._sweep_at = _SWEEP_AT

    def is_allowed(self, client_id: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        dq = self._hits.get(client_id)
        if dq is not None:
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq:
                del self._hits[client_id]
                dq = None
        if dq is None:
            if len(self._hits) >= self._sweep_at:
                self._forget_idle(cutoff)
            dq = self._hits[client_id] = deque()
        if len(dq) >= self._max:
            return False
        dq.append(now)
        return True

    def _forget_idle(self, cutoff: float) -> None:
        idle = [c for c, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for client_id in idle:
            del self._hits[client_id]
        # If most callers are still active, wait for the table to double before
        # looking again, so that a busy minute is not spent sweeping.
        self._sweep_at = max(_SWEEP_AT, 2 * len(self._hits))


_limiters: dict[str, tuple[int, _SlidingWindowLimiter]] = {}


def _get_limiter(bucket: str, max_rpm: int) -> _SlidingWindowLimiter:
    state = _limiters.get(bucket)
    if state is None or state[0] != max_rpm:
        state = (max_rpm, _SlidingWindowLimiter(max_requests=max_rpm, window_seconds=60.0))
        _limiters[bucket] = state
    return state[1]


# Swapping or adding a stop is a paid places search too. These paths carry a
# quest id and a stop number, so they are matched by shape, not listed below.
_STOP_SEARCH_PATH = re.compile(r"/api/quest/[^/]+/stop/[^/]+/(?:alternatives|additions)")


def _is_stop_search(method: str, path: str) -> bool:
    return method == "POST" and _STOP_SEARCH_PATH.fullmatch(path) is not None


# Endpoints that spend money (Google or the model API) or write to disk, and
# the allowance each one counts against. Location suggestions fire every few
# keystrokes, so they are counted apart from searches.
_SEARCH_BUCKET = "search"
_SUGGEST_BUCKET = "suggest"
_SWAP_LOG_BUCKET = "swap_log"
_GENERATE_BUCKET = "generate"
_PHOTO_BUCKET = "photo"
_BLURBS_BUCKET = "blurbs"
_LIMITED_ENDPOINTS = {
    ("POST", "/api/quest/generate"): _GENERATE_BUCKET,
    ("GET", "/api/places/photo"): _PHOTO_BUCKET,
    ("POST", "/api/places/blurbs"): _BLURBS_BUCKET,
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

# One generated quest is 8 to 15 or more billed Google calls.
_GENERATE_MAX_PER_MINUTE = 10
# Each blurbs request is a call to the model API.
_BLURBS_MAX_PER_MINUTE = 20
# A page asks for many photos at once (curated cards, stops, swap options), so
# this one is above the general allowance on purpose.
_PHOTO_MAX_PER_MINUTE = 120

# Buckets held below the general allowance (PLACES_RATE_LIMIT_PER_MINUTE).
_CEILINGS = {
    _SWAP_LOG_BUCKET: _SWAP_LOG_MAX_PER_MINUTE,
    _GENERATE_BUCKET: _GENERATE_MAX_PER_MINUTE,
    _BLURBS_BUCKET: _BLURBS_MAX_PER_MINUTE,
}


def _allowance(bucket: str, settings) -> int:
    """Requests per minute one client may make against `bucket`."""
    if bucket == _SUGGEST_BUCKET:
        return settings.suggest_rate_limit_per_minute
    if bucket == _PHOTO_BUCKET:
        return _PHOTO_MAX_PER_MINUTE
    general = settings.rate_limit_per_minute
    return min(general, _CEILINGS.get(bucket, general))


def _caller_key(address: str) -> str | None:
    """An address as the limits count it, or None if it is not an address."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    # One phone or home line holds a whole /64, so a limit on single addresses
    # is evaded by moving to the next one.
    return str(ipaddress.IPv6Network((int(ip) >> 64 << 64, 64)))


def _client_id(request: Request) -> str:
    """Who a request counts against. Every limit uses this.

    Production is Cloud Run, called directly on its run.app address. Google's
    front end keeps whatever X-Forwarded-For the caller sent and appends the
    address it saw, so the LAST entry is the only one a caller cannot write.
    With a load balancer in front, the balancer appends an address too, and
    the caller becomes the second entry from the end.

    request.client is used only when it did not come out of that header. The
    Dockerfile runs uvicorn with --forwarded-allow-ips='*', which sets it to
    the FIRST entry, the one the caller writes.
    """
    sent = [
        entry.strip()
        for value in request.headers.getlist("x-forwarded-for")
        for entry in value.split(",")
    ]
    entries = [entry for entry in sent if entry]
    if entries:
        key = _caller_key(entries[-1])
        if key is not None:
            return key
    peer = request.client.host if request.client else ""
    if not peer or peer in sent:
        return "unknown"
    return _caller_key(peer) or peer


class NearbyPlacesRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-client rate limiting to quota- and disk-spending endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled or settings.rate_limit_per_minute <= 0:
            return await call_next(request)
        bucket = (
            _SEARCH_BUCKET
            if _is_stop_search(request.method, request.url.path)
            else _LIMITED_ENDPOINTS.get((request.method, request.url.path))
        )
        if bucket is None:
            return await call_next(request)
        max_rpm = _allowance(bucket, settings)
        if max_rpm <= 0:
            return await call_next(request)

        limiter = _get_limiter(bucket, max_rpm)
        if not limiter.is_allowed(_client_id(request)):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after_seconds": 60,
                },
            )
        return await call_next(request)
