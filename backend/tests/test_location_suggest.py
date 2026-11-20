"""Location suggestions: the dropdown under the "Where?" field."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import rate_limit
from config import Settings
from deps import get_places_provider
from main import app
from services.google_places import GooglePlacesProvider
from services.places_exceptions import LocationNotFoundError, ProviderQuotaError
from services.places_provider import PlaceSuggestion

SESSION = "7b0c2b9e-3c1a-4a5f-9d2e-0f6a1b2c3d4e"
PLACE_ID = "ChIJx9Lr6tqZyzsRwvu6koO3k64"


def _prediction(place_id: str, main: str, secondary: str) -> dict:
    return {
        "placePrediction": {
            "placeId": place_id,
            "text": {"text": f"{main}, {secondary}"},
            "structuredFormat": {
                "mainText": {"text": main},
                "secondaryText": {"text": secondary},
            },
        }
    }


def _provider() -> GooglePlacesProvider:
    return GooglePlacesProvider(Settings(GOOGLE_PLACES_API_KEY="test-key"))


# ── Provider: request sent to Google, and how its answer is read ──


async def test_suggest_request_is_biased_to_the_user_and_carries_the_session(monkeypatch):
    provider = _provider()
    sent: dict = {}

    async def fake_post(url, payload, field_mask):
        sent.update(url=url, payload=payload, field_mask=field_mask)
        return {"suggestions": []}

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    await provider.suggest_locations("banj", session_token=SESSION, bias=(12.97, 77.59))

    assert sent["url"].endswith("/v1/places:autocomplete")
    payload = sent["payload"]
    assert payload["input"] == "banj"
    assert payload["sessionToken"] == SESSION
    # Not tied to a country unless SUGGEST_REGION_CODE says so.
    assert "includedRegionCodes" not in payload
    circle = payload["locationBias"]["circle"]
    assert circle["center"] == {"latitude": 12.97, "longitude": 77.59}
    assert 0 < circle["radius"] <= 50_000
    # Only the four fields the dropdown shows are requested.
    assert set(sent["field_mask"].split(",")) == {
        "suggestions.placePrediction.placeId",
        "suggestions.placePrediction.text.text",
        "suggestions.placePrediction.structuredFormat.mainText.text",
        "suggestions.placePrediction.structuredFormat.secondaryText.text",
    }


async def test_suggest_without_session_sends_no_token(monkeypatch):
    provider = _provider()
    sent: dict = {}

    async def fake_post(url, payload, field_mask):
        sent.update(payload=payload)
        return {}

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    assert await provider.suggest_locations("banj") == []
    assert "sessionToken" not in sent["payload"]


async def test_suggest_without_a_position_is_not_biased_anywhere(monkeypatch):
    provider = _provider()
    sent: dict = {}

    async def fake_post(url, payload, field_mask):
        sent.update(payload=payload)
        return {}

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    await provider.suggest_locations("banj")
    assert sent["payload"] == {"input": "banj", "languageCode": "en"}


async def test_suggest_can_be_limited_to_one_country(monkeypatch):
    provider = GooglePlacesProvider(
        Settings(GOOGLE_PLACES_API_KEY="test-key", SUGGEST_REGION_CODE="in")
    )
    sent: dict = {}

    async def fake_post(url, payload, field_mask):
        sent.update(payload=payload)
        return {}

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    await provider.suggest_locations("banj")
    assert sent["payload"]["includedRegionCodes"] == ["in"]


async def test_suggest_reads_predictions_and_skips_unusable_rows(monkeypatch):
    provider = _provider()

    async def fake_post(url, payload, field_mask):
        return {
            "suggestions": [
                _prediction("id-1", "Banjara Hills", "Hyderabad, Telangana, India"),
                # A search-term suggestion, not a place.
                {"queryPrediction": {"text": {"text": "banjara restaurants"}}},
                # No structured text: the full text stands in as the title.
                {"placePrediction": {"placeId": "id-2", "text": {"text": "Bandlaguda, Telangana"}}},
                # No place id: nothing to resolve, so it is dropped.
                {"placePrediction": {"text": {"text": "Nameless"}}},
            ]
        }

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    assert await provider.suggest_locations("ban") == [
        PlaceSuggestion("id-1", "Banjara Hills", "Hyderabad, Telangana, India"),
        PlaceSuggestion("id-2", "Bandlaguda, Telangana", ""),
    ]


async def test_suggest_returns_at_most_five(monkeypatch):
    provider = _provider()

    async def fake_post(url, payload, field_mask):
        return {"suggestions": [_prediction(f"id-{i}", f"Place {i}", "India") for i in range(9)]}

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    found = await provider.suggest_locations("pla")
    assert [s.place_id for s in found] == ["id-0", "id-1", "id-2", "id-3", "id-4"]


# ── Endpoints ──


class FakeSuggestProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.suggest_calls: list[tuple[str, str | None]] = []
        self.biases: list[tuple[float, float] | None] = []
        self.location_calls: list[tuple[str, str | None]] = []

    async def suggest_locations(self, text, *, session_token=None, bias=None):
        self.suggest_calls.append((text, session_token))
        self.biases.append(bias)
        if self.error:
            raise self.error
        return [PlaceSuggestion(PLACE_ID, "Banjara Hills", "Hyderabad, Telangana, India")]

    async def suggestion_location(self, place_id, *, session_token=None):
        self.location_calls.append((place_id, session_token))
        if self.error:
            raise self.error
        return 17.4169, 78.4387


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, rate_limit_per_minute=0),
    )


def _client(provider: FakeSuggestProvider) -> TestClient:
    app.dependency_overrides[get_places_provider] = lambda: provider
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_autocomplete_returns_suggestions():
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete", params={"q": " banj ", "session": SESSION})
    assert res.status_code == 200
    assert res.json() == {
        "suggestions": [
            {
                "place_id": PLACE_ID,
                "main_text": "Banjara Hills",
                "secondary_text": "Hyderabad, Telangana, India",
            }
        ]
    }
    assert provider.suggest_calls == [("banj", SESSION)]
    assert provider.biases == [None]


def test_autocomplete_passes_the_users_rough_position_on():
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get(
            "/api/places/autocomplete", params={"q": "ban", "lat": "12.9", "lng": "77.6"}
        )
    assert res.status_code == 200
    assert provider.biases == [(12.9, 77.6)]


@pytest.mark.parametrize("params", [{"lat": "12.9"}, {"lng": "77.6"}])
def test_autocomplete_ignores_half_a_position(params):
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete", params={"q": "ban", **params})
    assert res.status_code == 200
    assert provider.biases == [None]


def test_autocomplete_rejects_coordinates_off_the_map():
    with _client(FakeSuggestProvider()) as client:
        res = client.get(
            "/api/places/autocomplete", params={"q": "ban", "lat": "120", "lng": "77.6"}
        )
    assert res.status_code == 422


@pytest.mark.parametrize("q", ["", "b", "  b  "])
def test_autocomplete_does_not_spend_a_call_on_one_character(q):
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete", params={"q": q})
    assert res.status_code == 200
    assert res.json() == {"suggestions": []}
    assert provider.suggest_calls == []


@pytest.mark.parametrize("session", ["has space", "x" * 37, "semi;colon"])
def test_autocomplete_rejects_a_malformed_session_token(session):
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete", params={"q": "banj", "session": session})
    assert res.status_code == 422
    assert provider.suggest_calls == []


def test_autocomplete_maps_provider_failures():
    provider = FakeSuggestProvider(error=ProviderQuotaError("Places quota exceeded."))
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete", params={"q": "banj"})
    assert res.status_code == 503
    assert res.json()["detail"]["message"] == "Places quota exceeded."


def test_location_returns_coordinates_and_passes_the_session_on():
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get(
            "/api/places/autocomplete/location",
            params={"place_id": PLACE_ID, "session": SESSION},
        )
    assert res.status_code == 200
    assert res.json() == {"lat": 17.4169, "lng": 78.4387}
    assert provider.location_calls == [(PLACE_ID, SESSION)]


@pytest.mark.parametrize("place_id", ["short", "ChIJ/../../etc", "ChIJ abc def ghi", "a" * 401])
def test_location_rejects_ids_that_are_not_place_ids(place_id):
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete/location", params={"place_id": place_id})
    assert res.status_code == 422
    assert provider.location_calls == []


def test_location_unknown_place_is_a_404():
    provider = FakeSuggestProvider(error=LocationNotFoundError("Unknown place."))
    with _client(provider) as client:
        res = client.get("/api/places/autocomplete/location", params={"place_id": PLACE_ID})
    assert res.status_code == 404


# ── Rate limit: typing must not use up the allowance for searches ──


def test_suggestions_are_limited_apart_from_searches(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_per_minute=1,
            suggest_rate_limit_per_minute=3,
        ),
    )
    monkeypatch.setattr(rate_limit, "_limiters", {})
    provider = FakeSuggestProvider()
    with _client(provider) as client:
        typed = [
            client.get("/api/places/autocomplete", params={"q": "banj"}).status_code
            for _ in range(4)
        ]
        # The search allowance (1 a minute here) is still untouched.
        stored = client.post("/api/quest/store", content=b"not json")
    assert typed == [200, 200, 200, 429]
    assert stored.status_code != 429
