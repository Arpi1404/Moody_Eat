from services.place_utils import attach_distances, dedupe_places, haversine_meters
from services.places_provider import RawPlace


def test_haversine_known_short_distance():
    # ~111 km per degree latitude at equator; small delta ~111 m
    d = haversine_meters(0.0, 0.0, 0.001, 0.0)
    assert 110 < d < 112


def test_dedupe_by_provider_id():
    places = [
        RawPlace("x", "Same", "Addr", 1.0, 1.0, None, None),
        RawPlace("x", "Same", "Addr", 1.0, 1.0, None, None),
        RawPlace("y", "Other", "Addr2", 2.0, 2.0, None, None),
    ]
    out = dedupe_places(places)
    assert len(out) == 2


def test_dedupe_fuzzy_without_id():
    places = [
        RawPlace("", "Same", "Addr", 1.0, 1.0, None, None),
        RawPlace("", "same", "addr", 1.0, 1.0, None, None),
    ]
    out = dedupe_places(places)
    assert len(out) == 1


def test_sort_by_distance_from_origin():
    origin_lat, origin_lng = 0.0, 0.0
    places = [
        RawPlace("a", "Far", "", 0.01, 0.0, None, None),
        RawPlace("b", "Near", "", 0.001, 0.0, None, None),
    ]
    scored = attach_distances(origin_lat, origin_lng, places)
    names = [p[0].name for p in scored]
    assert names == ["Near", "Far"]
