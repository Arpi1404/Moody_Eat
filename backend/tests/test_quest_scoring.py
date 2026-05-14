from models import CostEstimate, PlaceItem
from quest_generator import _pick, _score_breakdown


def _place(
    provider_id: str,
    name: str,
    *,
    rating: float = 4.5,
    reviews: int = 400,
    price_level: int | None = None,
    lat: float = 0.0,
    lng: float = 0.0,
) -> PlaceItem:
    return PlaceItem(
        name=name,
        address="Test Road",
        lat=lat,
        lng=lng,
        distance_meters=0,
        rating=rating,
        user_ratings_total=reviews,
        price_level=price_level,
        types=["restaurant"],
        provider_id=provider_id,
    )


def test_budget_changes_pick_when_price_levels_differ() -> None:
    cheap_fit = _place(
        "cheap",
        "Budget Hero",
        rating=4.4,
        reviews=500,
        price_level=1,
    )
    splurge_fit = _place(
        "splurge",
        "Premium Room",
        rating=4.9,
        reviews=1000,
        price_level=3,
    )
    candidates = [cheap_fit, splurge_fit]

    cheap_pick = _pick(candidates, CostEstimate.cheap, None, None, set())
    splurge_pick = _pick(candidates, CostEstimate.splurge, None, None, set())

    assert cheap_pick == cheap_fit
    assert splurge_pick == splurge_fit


def test_unknown_price_has_lower_confidence_than_known_price() -> None:
    known = _place("known", "Known Mid", price_level=2)
    unknown = _place("unknown", "Unknown Price", price_level=None)

    known_score = _score_breakdown(known, CostEstimate.mid, None, None)
    unknown_score = _score_breakdown(unknown, CostEstimate.mid, None, None)

    assert known_score.price_source == "google_price_level"
    assert unknown_score.price_source == "unknown"
    assert known_score.confidence > unknown_score.confidence
    assert known_score.total > unknown_score.total


def test_price_mismatch_can_outweigh_nearby_high_rating_for_cheap_budget() -> None:
    nearby_expensive = _place(
        "nearby_expensive",
        "Nearby Premium",
        rating=5.0,
        reviews=1200,
        price_level=4,
        lat=0.0,
        lng=0.001,
    )
    farther_cheap = _place(
        "farther_cheap",
        "Farther Budget",
        rating=4.3,
        reviews=250,
        price_level=1,
        lat=0.0,
        lng=0.012,
    )

    picked = _pick(
        [nearby_expensive, farther_cheap],
        CostEstimate.cheap,
        0.0,
        0.0,
        set(),
    )

    assert picked == farther_cheap
