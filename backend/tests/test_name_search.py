"""Search by name on the build-your-own page. Offline: no call reaches Google."""

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import rate_limit
from config import Settings
from deps import get_nearby_places_service
from main import app
from services.google_places import GooglePlacesProvider
from services.nearby_places_service import NearbyPlacesService
from services.places_exceptions import (
    FeatureUnavailableError,
    LocationNotFoundError,
    ProviderQuotaError,
    ProviderTimeoutError,
)
from services.places_provider import RawPlace, ResolvedLocation

# The area the creator chose.
LAT, LNG = 12.9716, 77.6400


def _settings(**overrides) -> Settings:
    return Settings(GOOGLE_PLACES_API_KEY="test-key", **overrides)


def _place(name: str = "Third Wave Coffee", **overrides) -> RawPlace:
    fields = {
        "provider_id": f"id-{name}",
        "name": name,
        "address": "12th Main Rd, Indiranagar, Bengaluru, Karnataka 560038, India",
        "lat": LAT,
        "lng": LNG,
        "rating": 4.4,
        "types": ["cafe", "food", "point_of_interest", "establishment"],
        "user_ratings_total": 900,
        "business_status": "OPERATIONAL",
    }
    fields.update(overrides)
    return RawPlace(**fields)


class FakeProvider:
    def __init__(self, places=(), *, error=None, geocode_error=None) -> None:
        self.places = list(places)
        self.error = error
        self.geocode_error = geocode_error
        self.geocoded: list[str] = []
        self.searches: list[tuple[str, float, float]] = []

    async def geocode(self, query):
        self.geocoded.append(query)
        if self.geocode_error:
            raise self.geocode_error
        return ResolvedLocation(name="Indiranagar, Bengaluru, India", lat=LAT, lng=LNG)

    async def search_by_text(self, *, text, lat, lng):
        self.searches.append((text, lat, lng))
        if self.error:
            raise self.error
        return self.places


def _service(provider: FakeProvider, **overrides) -> NearbyPlacesService:
    return NearbyPlacesService(provider, _settings(**overrides))


async def _names(provider: FakeProvider) -> list[str]:
    result = await _service(provider).search_by_name(text="third wave", lat=LAT, lng=LNG)
    return [p.name for p in result.places]


# ── What is sent to Google ──


async def test_text_search_request_leans_to_the_area_and_asks_for_no_costlier_fields(
    monkeypatch,
):
    provider = GooglePlacesProvider(_settings())
    sent: dict = {}

    async def fake_post(url, payload, field_mask):
        sent.update(url=url, payload=payload, field_mask=field_mask)
        return {
            "places": [
                {
                    "id": "ChIJabc",
                    "displayName": {"text": "Toit"},
                    "location": {"latitude": LAT, "longitude": LNG},
                }
            ]
        }

    monkeypatch.setattr(provider, "_post_json_new", fake_post)
    found = await provider.search_by_text(text="toit", lat=LAT, lng=LNG)

    assert sent["url"] == "https://places.googleapis.com/v1/places:searchText"
    assert sent["payload"]["textQuery"] == "toit"
    assert sent["payload"]["pageSize"] == 20
    circle = sent["payload"]["locationBias"]["circle"]
    assert circle["center"] == {"latitude": LAT, "longitude": LNG}
    assert 0 < circle["radius"] <= 50_000
    # A lean, never a fence.
    assert "locationRestriction" not in sent["payload"]
    # Exactly these. Anything from the Atmosphere tier would raise the price of
    # every search by name.
    assert set(sent["field_mask"].split(",")) == {
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "places.businessStatus",
        "places.priceLevel",
        "places.priceRange",
    }
    assert [(p.provider_id, p.name) for p in found] == [("ChIJabc", "Toit")]


async def test_text_search_with_the_legacy_api_makes_no_call(monkeypatch):
    provider = GooglePlacesProvider(_settings(PLACES_USE_NEW_API=False))

    async def must_not_run(*args, **kwargs):
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(provider, "_post_json_new", must_not_run)
    with pytest.raises(FeatureUnavailableError):
        await provider.search_by_text(text="toit", lat=LAT, lng=LNG)


async def test_legacy_api_is_refused_before_the_area_is_geocoded():
    fake = FakeProvider([_place()])
    with pytest.raises(FeatureUnavailableError):
        await _service(fake, PLACES_USE_NEW_API=False).search_by_name(
            text="toit", area="Indiranagar"
        )
    assert fake.geocoded == []
    assert fake.searches == []


# ── Which matches are offered ──


async def test_a_small_place_is_findable_whatever_its_rating():
    # Nearby search would drop all three; someone typing the name wants them.
    names = await _names(
        FakeProvider(
            [
                _place("New Chai Cart", rating=None, user_ratings_total=None),
                _place("Two Review Cafe", rating=5.0, user_ratings_total=2),
                _place("Low Rated Diner", rating=2.9, user_ratings_total=15),
            ]
        )
    )
    assert names == ["New Chai Cart", "Two Review Cafe", "Low Rated Diner"]


@pytest.mark.parametrize("status", ["CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY", "FUTURE_OPENING"])
async def test_places_that_are_not_operating_are_left_out(status):
    names = await _names(FakeProvider([_place("Shut", business_status=status), _place("Open")]))
    assert names == ["Open"]


async def test_a_place_google_gives_no_status_for_is_kept():
    # Same rule as category browsing: some parks and landmarks carry none.
    assert await _names(FakeProvider([_place("Lake", business_status=None)])) == ["Lake"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"types": ["lodging", "restaurant"]},
        {"types": ["veterinary_care", "park"]},
        {"name": "Sharma Enterprises"},
        {"name": "Bright Coaching Classes"},
        {"name": "City Book Depot", "types": ["book_store"]},
    ],
)
async def test_the_type_and_name_denylists_apply(overrides):
    assert await _names(FakeProvider([_place(**overrides)])) == []


@pytest.mark.parametrize(
    "types",
    [
        ["neighborhood", "political"],
        ["locality", "political"],
        ["postal_code"],
        ["street_address"],
        ["plus_code"],
        ["intersection"],
    ],
)
async def test_map_areas_and_addresses_are_not_offered_as_stops(types):
    assert await _names(FakeProvider([_place("Indiranagar", types=types)])) == []


async def test_unusable_and_repeated_rows_are_skipped():
    names = await _names(
        FakeProvider(
            [
                _place("No Id", provider_id=""),
                _place("", provider_id="id-blank"),
                _place("Twice"),
                _place("Twice"),
            ]
        )
    )
    assert names == ["Twice"]


async def test_matches_nowhere_near_the_area_are_dropped():
    names = await _names(
        FakeProvider(
            [
                _place("Another City", lat=17.385, lng=78.4867),
                _place("Across Town", lat=LAT + 0.2),  # about 22 km
            ]
        )
    )
    assert names == ["Across Town"]


async def test_googles_order_is_kept_and_distances_are_from_the_area():
    result = await _service(
        FakeProvider(
            [
                _place("Farther Branch", lat=LAT + 0.02),
                _place("Nearer Branch"),
            ]
        )
    ).search_by_name(text="branch", lat=LAT, lng=LNG)
    assert [p.name for p in result.places] == ["Farther Branch", "Nearer Branch"]
    assert result.places[0].distance_meters == pytest.approx(2224, abs=5)
    assert result.places[1].distance_meters == 0
    assert result.count == 2


async def test_at_most_eight_results_after_filtering():
    places = [_place(f"Shut {i}", business_status="CLOSED_PERMANENTLY") for i in range(5)]
    places += [_place(f"Open {i}") for i in range(12)]
    assert await _names(FakeProvider(places)) == [f"Open {i}" for i in range(8)]


# ── Where the search is anchored ──


async def test_coordinates_are_used_as_given_without_geocoding():
    fake = FakeProvider([_place()])
    result = await _service(fake).search_by_name(
        text="wave", lat=LAT, lng=LNG, area="ignored when there are coordinates"
    )
    assert fake.geocoded == []
    assert fake.searches == [("wave", LAT, LNG)]
    assert result.resolved_location.name == ""


async def test_a_typed_area_is_geocoded_as_typed():
    fake = FakeProvider([_place()])
    # Nearby search would read "park" as a category and strip it; here it is
    # only ever part of the area's name.
    result = await _service(fake).search_by_name(text="wave", area=" Park Street ")
    assert fake.geocoded == ["Park Street"]
    assert result.resolved_location.name == "Indiranagar, Bengaluru, India"


async def test_results_are_not_cached():
    fake = FakeProvider([_place()])
    service = _service(fake)
    await service.search_by_name(text="wave", lat=LAT, lng=LNG)
    await service.search_by_name(text="wave", lat=LAT, lng=LNG)
    assert len(fake.searches) == 2


# ── Endpoint ──


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, rate_limit_per_minute=0),
    )


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client(provider: FakeProvider, **overrides) -> TestClient:
    app.dependency_overrides[get_nearby_places_service] = lambda: _service(
        provider, **overrides
    )
    return TestClient(app)


def _search(client: TestClient, **body):
    return client.post("/api/places/search", json={"q": "third wave", **body})


def test_endpoint_returns_the_same_place_shape_as_nearby_search():
    with _client(FakeProvider([_place(price_level=2)])) as client:
        res = _search(client, lat=LAT, lng=LNG)
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    assert set(body["places"][0]) >= {
        "name",
        "address",
        "lat",
        "lng",
        "distance_meters",
        "rating",
        "user_ratings_total",
        "price_level",
        "types",
        "provider_id",
    }
    assert body["places"][0]["price_level"] == 2


def test_endpoint_tidies_the_typed_text():
    fake = FakeProvider()
    with _client(fake) as client:
        res = client.post(
            "/api/places/search",
            json={"q": "  third\n  wave ", "lat": LAT, "lng": LNG},
        )
    assert res.status_code == 200
    assert fake.searches == [("third wave", LAT, LNG)]


@pytest.mark.parametrize("q", ["", "ab", "  a   ", "x" * 121])
def test_endpoint_spends_no_call_on_text_that_is_too_short_or_long(q):
    fake = FakeProvider()
    with _client(fake) as client:
        res = client.post("/api/places/search", json={"q": q, "area": "Indiranagar"})
    assert res.status_code == 422
    assert fake.geocoded == []
    assert fake.searches == []


@pytest.mark.parametrize("where", [{}, {"area": "   "}, {"lat": LAT}, {"lng": LNG}])
def test_endpoint_needs_an_area(where):
    fake = FakeProvider()
    with _client(fake) as client:
        res = _search(client, **where)
    assert res.status_code == 422
    assert res.json()["detail"]["message"] == "Pick an area first."
    assert fake.searches == []


def test_endpoint_rejects_coordinates_off_the_map():
    with _client(FakeProvider()) as client:
        res = _search(client, lat=120, lng=LNG)
    assert res.status_code == 422


def test_endpoint_marks_an_unknown_area():
    fake = FakeProvider(geocode_error=LocationNotFoundError("No results."))
    with _client(fake) as client:
        res = _search(client, area="zzzzzz")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "area_not_found"
    assert fake.searches == []


@pytest.mark.parametrize(
    "error, status",
    [(ProviderQuotaError("Places quota exceeded."), 503), (ProviderTimeoutError("slow"), 504)],
)
def test_endpoint_maps_provider_failures(error, status):
    with _client(FakeProvider(error=error)) as client:
        res = _search(client, lat=LAT, lng=LNG)
    assert res.status_code == status


def test_endpoint_with_the_legacy_api_gives_a_clear_error():
    with _client(FakeProvider(), PLACES_USE_NEW_API=False) as client:
        res = _search(client, lat=LAT, lng=LNG)
    assert res.status_code == 503
    assert "Search by name" in res.json()["detail"]["message"]


def test_endpoint_does_not_log_what_was_typed(caplog):
    caplog.set_level(logging.DEBUG)
    with _client(FakeProvider([_place()])) as client:
        res = client.post(
            "/api/places/search", json={"q": "zanzibar secret spot", "area": "Quibbleton"}
        )
    assert res.status_code == 200
    ours = [r.getMessage() for r in caplog.records if not r.name.startswith("httpx")]
    assert any("places_name_search" in m for m in ours)
    assert not [m for m in ours if "zanzibar" in m or "Quibbleton" in m]


# ── Rate limit: a bucket of its own, with a low ceiling ──


def _limit_to(monkeypatch, per_minute: int) -> None:
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_per_minute=per_minute,
            suggest_rate_limit_per_minute=120,
        ),
    )
    monkeypatch.setattr(rate_limit, "_limiters", {})


def test_name_search_is_limited_to_twenty_a_minute_in_its_own_bucket(monkeypatch):
    _limit_to(monkeypatch, 60)
    with _client(FakeProvider()) as client:
        codes = [_search(client, lat=LAT, lng=LNG).status_code for _ in range(21)]
        # The shared search allowance is untouched.
        stored = client.post("/api/quest/store", content=b"not json")
    assert codes == [200] * 20 + [429]
    assert stored.status_code != 429


def test_name_search_never_gets_more_than_the_general_allowance(monkeypatch):
    _limit_to(monkeypatch, 2)
    with _client(FakeProvider()) as client:
        codes = [_search(client, lat=LAT, lng=LNG).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
