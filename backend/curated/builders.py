"""Small constructors that keep the per-city quest modules readable."""

from datetime import datetime, time

from models import PlaceItem, Stop, StopCategory, TravelMode

CREATED_AT = datetime(2026, 5, 5, 18, 0, 0)


def place(
    provider_id: str,
    name: str,
    address: str,
    lat: float,
    lng: float,
    rating: float,
    types: list[str],
    user_ratings_total: int = 250,
) -> PlaceItem:
    return PlaceItem(
        provider_id=provider_id,
        name=name,
        address=address,
        lat=lat,
        lng=lng,
        distance_meters=0,
        rating=rating,
        user_ratings_total=user_ratings_total,
        business_status="OPERATIONAL",
        types=types,
    )


def stop(
    place: PlaceItem,
    category: StopCategory,
    start: time,
    end: time,
    why: str,
    travel_to_next_minutes: int | None = None,
    travel_mode: TravelMode | None = None,
) -> Stop:
    """One stop. `travel_to_next_minutes` is omitted on the last stop; the
    mode defaults to driving when only the minutes are given."""
    mode = travel_mode
    if travel_to_next_minutes is not None and mode is None:
        mode = TravelMode.driving
    return Stop(
        place=place,
        category=category,
        time_block_start=start,
        time_block_end=end,
        travel_to_next_minutes=travel_to_next_minutes,
        travel_mode=mode,
        why_this_place=why,
    )
