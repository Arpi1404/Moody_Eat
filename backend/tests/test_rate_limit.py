"""Who a request counts against, the limits on the billed routes, and that
idle callers are forgotten.

Offline. The limiter runs before the handler, so every request here has an
invalid body and no handler runs; outbound requests are blocked anyway.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import rate_limit
from deps import get_nearby_places_service, get_places_provider
from main import app

CALLER = "203.0.113.7"
OTHER = "198.51.100.23"

# Each billed route with a request its handler never sees, and its ceiling.
GENERATE = ("POST", "/api/quest/generate", 10)
PHOTO = ("GET", "/api/places/photo", 120)
BLURBS = ("POST", "/api/places/blurbs", 20)


def _settings(per_minute: int = 60, enabled: bool = True):
    return SimpleNamespace(
        rate_limit_enabled=enabled,
        rate_limit_per_minute=per_minute,
        suggest_rate_limit_per_minute=120,
    )


@pytest.fixture(autouse=True)
def offline_and_fresh(monkeypatch):
    async def no_network(*args, **kwargs):
        raise AssertionError("a test tried to reach the network")

    async def no_handler(*args, **kwargs):
        raise AssertionError("a billed handler ran")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    monkeypatch.setattr("routes.fetch_place_photo", no_handler)
    monkeypatch.setattr("routes.generate_place_blurbs", no_handler)
    monkeypatch.setattr("routes.assemble_quest", no_handler)
    app.dependency_overrides[get_nearby_places_service] = lambda: object()
    app.dependency_overrides[get_places_provider] = lambda: object()
    monkeypatch.setattr("rate_limit.get_settings", _settings)
    monkeypatch.setattr(rate_limit, "_limiters", {})
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _call(client, route, headers=None) -> int:
    method, path, _ = route
    kwargs = {"json": {}} if method == "POST" else {}
    return client.request(method, path, headers=headers or {}, **kwargs).status_code


def _xff(value: str) -> dict:
    return {"X-Forwarded-For": value}


def _use_up(client, route, headers) -> None:
    codes = [_call(client, route, headers) for _ in range(route[2])]
    assert 429 not in codes, codes


# ── The billed routes ──


@pytest.mark.parametrize("route", [GENERATE, PHOTO, BLURBS], ids=["generate", "photo", "blurbs"])
def test_each_billed_route_answers_429_at_its_ceiling(client, route):
    codes = [_call(client, route, _xff(CALLER)) for _ in range(route[2] + 1)]
    # 422 is the invalid body being turned away after the limiter let it by.
    assert codes == [422] * route[2] + [429]


def test_each_billed_route_has_a_bucket_of_its_own(client):
    nearby = ("POST", "/api/places/nearby", 60)
    for route in (GENERATE, PHOTO, BLURBS):
        _use_up(client, route, _xff(CALLER))
        assert _call(client, route, _xff(CALLER)) == 429
    # None of them touched the search allowance...
    _use_up(client, nearby, _xff(CALLER))
    # ...and using that up leaves a different caller's billed routes alone.
    assert _call(client, nearby, _xff(CALLER)) == 429
    assert _call(client, GENERATE, _xff(OTHER)) == 422


def test_a_lower_general_limit_also_holds_generate_and_blurbs(client, monkeypatch):
    monkeypatch.setattr("rate_limit.get_settings", lambda: _settings(per_minute=5))
    for route in (GENERATE, BLURBS):
        codes = [_call(client, route, _xff(CALLER)) for _ in range(6)]
        assert codes == [422] * 5 + [429]
    # Photos keep their own number: a page needs many at once.
    _use_up(client, PHOTO, _xff(CALLER))


def test_the_global_switch_still_turns_limiting_off(client, monkeypatch):
    monkeypatch.setattr("rate_limit.get_settings", lambda: _settings(enabled=False))
    assert {_call(client, GENERATE, _xff(CALLER)) for _ in range(30)} == {422}


def test_the_other_limits_are_unchanged():
    settings = _settings()
    expected = {"search": 60, "suggest": 120, "swap_log": 20}
    assert {b: rate_limit._allowance(b, settings) for b in expected} == expected
    new = {"generate": 10, "photo": 120, "blurbs": 20}
    assert {b: rate_limit._allowance(b, settings) for b in new} == new
    buckets = rate_limit._LIMITED_ENDPOINTS
    assert buckets[("POST", "/api/places/nearby")] == "search"
    assert buckets[("POST", "/api/quest/store")] == "search"
    assert buckets[("GET", "/api/places/autocomplete")] == "suggest"
    assert buckets[("GET", "/api/places/autocomplete/location")] == "suggest"
    assert buckets[("POST", "/api/quest/swap-log")] == "swap_log"


# ── Who a request counts against ──


def test_changing_the_first_entry_evades_nothing(client):
    codes = [
        _call(client, GENERATE, _xff(f"10.0.0.{n}, {CALLER}")) for n in range(11)
    ]
    assert codes == [422] * 10 + [429]


def test_two_last_entries_are_two_callers(client):
    _use_up(client, GENERATE, _xff(f"10.0.0.1, {CALLER}"))
    assert _call(client, GENERATE, _xff(f"10.0.0.1, {OTHER}")) == 422
    assert _call(client, GENERATE, _xff(f"10.0.0.1, {CALLER}")) == 429


def test_a_forged_entry_cannot_use_up_someone_elses_allowance(client):
    # Naming a victim first counts against the sender, not the victim.
    _use_up(client, GENERATE, _xff(f"{OTHER}, {CALLER}"))
    assert _call(client, GENERATE, _xff(OTHER)) == 422


def test_the_last_of_several_headers_counts(client):
    codes = [
        _call(
            client,
            GENERATE,
            [("X-Forwarded-For", f"10.0.0.{n}"), ("X-Forwarded-For", CALLER)],
        )
        for n in range(11)
    ]
    assert codes == [422] * 10 + [429]


def test_addresses_in_one_ipv6_network_are_one_caller(client):
    codes = [
        _call(client, GENERATE, _xff(f"2001:db8:abcd:12::{n:x}")) for n in range(1, 12)
    ]
    assert codes == [422] * 10 + [429]
    # The network next door is someone else.
    assert _call(client, GENERATE, _xff("2001:db8:abcd:13::1")) == 422


@pytest.mark.parametrize("production_flags", [False, True], ids=["plain", "as-dockerfile"])
def test_forged_entries_evade_nothing_behind_uvicorns_proxy_headers(production_flags):
    # The Dockerfile's --forwarded-allow-ips='*' makes uvicorn set the client
    # address to the first entry. Neither the usual case nor a last entry that
    # does not parse may fall back to it.
    served = ProxyHeadersMiddleware(app, trusted_hosts="*") if production_flags else app
    client = TestClient(served)
    for last in (CALLER, "not-an-address", "unknown"):
        rate_limit._limiters.clear()
        codes = [
            _call(client, GENERATE, _xff(f"10.1.1.{n}, {last}")) for n in range(11)
        ]
        assert codes == [422] * 10 + [429], last


def _request(forwarded: list[str], peer: str | None) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", v.encode()) for v in forwarded],
            "client": None if peer is None else (peer, 5000),
        }
    )


@pytest.mark.parametrize(
    "forwarded, peer, expected",
    [
        ([], "192.0.2.1", "192.0.2.1"),
        ([], "2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ([], "testclient", "testclient"),
        ([], None, "unknown"),
        (["10.0.0.1, 203.0.113.7"], "192.0.2.1", "203.0.113.7"),
        (["203.0.113.7, , "], "192.0.2.1", "203.0.113.7"),
        (["  203.0.113.7  "], "192.0.2.1", "203.0.113.7"),
        (["10.0.0.1", "203.0.113.7"], "192.0.2.1", "203.0.113.7"),
        (["::ffff:203.0.113.7"], "192.0.2.1", "203.0.113.7"),
        (["2001:DB8:0:0:ffff::1"], "192.0.2.1", "2001:db8::/64"),
        (["fe80::1%eth0"], "192.0.2.1", "fe80::/64"),
        # A last entry that is not an address: the connection's own address...
        (["10.0.0.1, garbage"], "192.0.2.1", "192.0.2.1"),
        (["10.0.0.1, 203.0.113.7:443"], "192.0.2.1", "192.0.2.1"),
        # ...unless that was copied out of the header by the server.
        (["10.0.0.1, garbage"], "10.0.0.1", "unknown"),
        (["garbage, junk"], "garbage", "unknown"),
        ([", garbage"], "", "unknown"),
        (["garbage"], None, "unknown"),
        ([""], "192.0.2.1", "192.0.2.1"),
    ],
)
def test_client_id(forwarded, peer, expected):
    assert rate_limit._client_id(_request(forwarded, peer)) == expected


# ── Forgetting idle callers ──


@pytest.fixture
def clock(monkeypatch):
    now = SimpleNamespace(value=1_000.0)
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now.value)
    return now


def test_a_returning_caller_starts_afresh_once_the_window_has_emptied(clock):
    limiter = rate_limit._SlidingWindowLimiter(2, 60.0)
    assert [limiter.is_allowed("a") for _ in range(3)] == [True, True, False]
    clock.value += 61
    assert limiter.is_allowed("a")
    assert len(limiter._hits["a"]) == 1


def test_idle_callers_are_swept_once_the_table_is_large(clock, monkeypatch):
    monkeypatch.setattr(rate_limit, "_SWEEP_AT", 3)
    limiter = rate_limit._SlidingWindowLimiter(2, 60.0)
    for caller in ("a", "b", "c"):
        limiter.is_allowed(caller)
    clock.value += 30
    limiter.is_allowed("c")
    clock.value += 31
    limiter.is_allowed("d")
    # a and b have nothing left in their window; c was active 31 s ago.
    assert set(limiter._hits) == {"c", "d"}
    # The sweep forgave nothing: c has one hit left in the window.
    assert [limiter.is_allowed("c") for _ in range(2)] == [True, False]


def test_a_table_full_of_active_callers_is_not_swept_for_every_newcomer(
    clock, monkeypatch
):
    monkeypatch.setattr(rate_limit, "_SWEEP_AT", 4)
    limiter = rate_limit._SlidingWindowLimiter(2, 60.0)
    sweeps = []
    real = limiter._forget_idle
    monkeypatch.setattr(
        limiter, "_forget_idle", lambda cutoff: sweeps.append(len(limiter._hits)) or real(cutoff)
    )
    for n in range(40):
        limiter.is_allowed(f"caller-{n}")
    assert sweeps == [4, 8, 16, 32]
    assert len(limiter._hits) == 40
    # Once they have all gone quiet, the next sweep clears them out.
    clock.value += 61
    for n in range(40, 70):
        limiter.is_allowed(f"caller-{n}")
    assert len(limiter._hits) == 30


def test_a_large_table_stays_bounded_over_many_windows(clock, monkeypatch):
    monkeypatch.setattr(rate_limit, "_SWEEP_AT", 100)
    limiter = rate_limit._SlidingWindowLimiter(10, 60.0)
    for window in range(20):
        for n in range(150):
            limiter.is_allowed(f"{window}-{n}")
        clock.value += 61
    assert len(limiter._hits) <= 300
