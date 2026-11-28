from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ResolvedLocation:
    """Geocoded anchor point for nearby search."""

    name: str
    lat: float
    lng: float


@dataclass(frozen=True)
class PlaceSuggestion:
    """One row of the location dropdown: "Banjara Hills" / "Hyderabad, Telangana"."""

    place_id: str
    main_text: str
    secondary_text: str = ""


@dataclass(frozen=True)
class RawPlace:
    """Normalized row from any places provider before distance ranking."""

    provider_id: str
    name: str
    address: str
    lat: float
    lng: float
    rating: float | None
    types: list[str] | None
    user_ratings_total: int | None = None
    business_status: str | None = None
    price_level: int | None = None
    # Per-person price range in INR from Places API (New) `priceRange`.
    # None when the provider has no range data (or the currency is not INR).
    price_range_start_inr: int | None = None
    price_range_end_inr: int | None = None
    # The one type Google says the place mainly is ("pizza_restaurant"), as
    # opposed to `types`, which lists everything it is tagged with. None when
    # the provider has no primary type for it (always, on the legacy API).
    primary_type: str | None = None
    # The place's regular weekly opening hours, as the search returned them,
    # in the shape `hours_for_weekday` reads: {"open": {"day": 0-6, "time":
    # "HHMM"}, "close": {...}}, day 0 = Sunday. None means the search did not
    # ask for hours (the legacy API, or a provider without them), so a lookup
    # is still needed; an empty tuple means it asked and the place lists none.
    opening_periods: tuple[dict[str, Any], ...] | None = None
    # Minutes the place's local time is ahead of UTC (330 in India). None when
    # unknown.
    utc_offset_minutes: int | None = None
    # As Google gives them: "+91 80 4123 4567", "https://example.com/". None
    # when the place lists none.
    phone: str | None = None
    website: str | None = None


@dataclass(frozen=True)
class PlaceHours:
    """Opening hours for a single weekday. All times are local "HH:MM" 24-hour."""

    opens_today: str | None
    closes_today: str | None
    open_24h_today: bool
    # Every (opens, closes) window for the day, earliest first. Places with a
    # midday break — lunch and dinner service, parks open mornings and
    # evenings — have more than one; opens_today/closes_today describe only
    # the first, so anything checking a time slot must look at all of these.
    windows: tuple[tuple[str, str], ...] = ()


def _fmt_hhmm(g_time: str) -> str | None:
    """'HHMM' (e.g. '0900', '2130') to 'HH:MM'."""
    if not g_time or len(g_time) != 4 or not g_time.isdigit():
        return None
    return f"{g_time[:2]}:{g_time[2:]}"


def hours_for_weekday(periods: list[dict[str, Any]] | tuple[dict[str, Any], ...], weekday: int) -> PlaceHours:
    """One weekday's hours from a week of opening periods.

    `periods` is Google's `opening_periods` shape (see RawPlace). A 24h place
    is signalled by a single period with day=0 time='0000' and no close.
    opens_today/closes_today describe the day's first window; `windows` lists
    every window so split-shift places can be checked against any time slot.
    weekday: 0=Sunday ... 6=Saturday.
    """
    if not periods:
        return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)

    # Detect 24h: single period, day 0, open time "0000", no close field.
    if len(periods) == 1:
        only = periods[0]
        opn = only.get("open") or {}
        if opn.get("day") == 0 and opn.get("time") == "0000" and "close" not in only:
            return PlaceHours(opens_today=None, closes_today=None, open_24h_today=True)

    # A weekday can carry several periods: restaurants that close between
    # lunch and dinner, parks open mornings and evenings. Keep them all —
    # reading only the first made every such place look shut in the evening.
    todays: list[tuple[str | None, str | None]] = []
    for p in periods:
        opn = p.get("open") or {}
        if opn.get("day") != weekday:
            continue
        opens = _fmt_hhmm(str(opn.get("time") or ""))
        close = p.get("close") or {}
        closes = _fmt_hhmm(str(close.get("time") or "")) if close else None
        todays.append((opens, closes))

    if not todays:
        return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)

    todays.sort(key=lambda window: window[0] or "")
    first_opens, first_closes = todays[0]
    return PlaceHours(
        opens_today=first_opens,
        closes_today=first_closes,
        open_24h_today=False,
        windows=tuple(
            (opens, closes) for opens, closes in todays if opens and closes
        ),
    )


@runtime_checkable
class PlacesProvider(Protocol):
    async def geocode(self, query: str) -> ResolvedLocation:
        """Resolve free-text (or lat,lng string) to coordinates."""
        ...

    async def nearby_by_type(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        """Places whose primary type matches `place_type` (provider-specific)."""
        ...

    async def place_hours(
        self,
        *,
        provider_id: str,
        weekday: int,
    ) -> PlaceHours:
        """Today's opening/closing time for the given place.

        weekday: 0=Sunday, 1=Monday, ..., 6=Saturday (Google convention).
        Returns all-None when hours are unknown.
        """
        ...

    async def search_by_text(
        self,
        *,
        text: str,
        lat: float,
        lng: float,
        included_type: str | None = None,
        bias_radius_m: float | None = None,
    ) -> list[RawPlace]:
        """Places matching a typed name or a phrase, best match first, leaning
        towards (lat, lng) within `bias_radius_m`; only places of
        `included_type` when given.
        Unfiltered: closed places and non-venues are included."""
        ...
