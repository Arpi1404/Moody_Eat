"""Swapping and adding stops are paid searches, so they are rate limited."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import rate_limit
from config import get_settings
from deps import get_nearby_places_service
from main import app
from services.nearby_places_service import NearbyPlacesService
from tests.test_nearby_places import FakeProvider, _quest_payload

QUEST_ID = "11111111-1111-4111-8111-111111111111"
SWAP = f"/api/quest/{QUEST_ID}/stop/1/alternatives"
ADD = f"/api/quest/{QUEST_ID}/stop/1/additions?kind=coffee"


@pytest.fixture
def two_searches_a_minute(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_per_minute=2,
            suggest_rate_limit_per_minute=3,
        ),
    )
    monkeypatch.setattr(rate_limit, "_limiters", {})


@pytest.fixture
def provider():
    fake = FakeProvider()
    service = NearbyPlacesService(fake, get_settings())
    app.dependency_overrides[get_nearby_places_service] = lambda: service
    yield fake
    app.dependency_overrides.clear()


def _post(client: TestClient, path: str, caller: str = "10.0.0.1", **headers):
    return client.post(path, json=_quest_payload(), headers={"x-forwarded-for": caller, **headers})


@pytest.mark.parametrize("path", [SWAP, f"{SWAP}?kind=walk", ADD])
def test_a_stop_search_is_refused_past_the_allowance(two_searches_a_minute, provider, path: str) -> None:
    with TestClient(app) as client:
        codes = [_post(client, path).status_code for _ in range(3)]

    assert codes == [200, 200, 429]


def test_swaps_additions_and_nearby_searches_share_one_allowance(two_searches_a_minute, provider) -> None:
    with TestClient(app) as client:
        assert _post(client, SWAP).status_code == 200
        assert _post(client, ADD).status_code == 200
        searches_so_far = len(provider.nearby_types)

        # Another quest and another stop do not buy a fresh allowance.
        other = "/api/quest/22222222-2222-4222-8222-222222222222/stop/0/alternatives"
        assert _post(client, other).status_code == 429
        assert _post(client, ADD).status_code == 429
        nearby = client.post(
            "/api/places/nearby",
            json={"query": "Somewhere", "categories": ["cafe"]},
            headers={"x-forwarded-for": "10.0.0.1"},
        )
        assert nearby.status_code == 429

    assert len(provider.nearby_types) == searches_so_far  # a refusal costs nothing


def test_each_caller_has_an_allowance_of_their_own(two_searches_a_minute, provider) -> None:
    with TestClient(app) as client:
        for _ in range(3):
            _post(client, SWAP, caller="10.0.0.1")

        assert _post(client, SWAP, caller="10.0.0.2").status_code == 200


def test_the_refusal_can_be_read_by_the_site(two_searches_a_minute, provider) -> None:
    """Without CORS headers the browser hides the 429 and reports a failed fetch."""
    origin = "http://localhost:5173"
    with TestClient(app) as client:
        responses = [_post(client, SWAP, origin=origin) for _ in range(3)]

    assert responses[-1].status_code == 429
    assert responses[-1].headers.get("access-control-allow-origin") == origin
    assert responses[-1].json()["detail"] == "Rate limit exceeded. Try again later."
