import json
import logging
import uuid
from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from curated_quests import CURATED_CITIES, find_city, find_quest
from deps import get_nearby_places_service, get_places_provider
from models import (
    ALLOWED_NEARBY_TYPES,
    FILM_MINUTES,
    PLACE_ID_PATTERN,
    STOP_KIND_SEARCHES,
    LocationSuggestion,
    LocationSuggestionsResponse,
    NameSearchRequest,
    NearbyPlacesRequest,
    NearbyPlacesResponse,
    PlaceItem,
    PlaceBlurbsRequest,
    PlaceBlurbsResponse,
    Quest,
    QuestGenerationRequest,
    Stop,
    StopAlternative,
    StopCategory,
    StopKind,
    StopSwapDelta,
    StoredQuestCreateResponse,
    StoredQuestStats,
    SuggestionLocation,
    SwapEvent,
)
from quest_store import fetch_quest, store_quest
from swap_log import record_swap
from price_inference import CostBand, estimate_cost_band
from quest_generator import (
    _DWELL,
    _add_min,
    _popularity_cap,
    _score,
    _swap_kind,
    _travel_time,
    _why,
    assemble_quest,
    haversine_m,
)
from quest_templates import (
    CAFE,
    DESSERT,
    DRINKS,
    MEAL,
    PLAY,
    SIGHT,
    STROLL,
    TemplateStop,
)
from services.google_places import GooglePlacesProvider
from services.nearby_places_service import NearbyPlacesService, map_provider_error
from services.place_blurbs_service import generate_place_blurbs
from services.place_photo_service import fetch_place_photo
from services.places_exceptions import LocationNotFoundError, PlacesProviderError

logger = logging.getLogger(__name__)

router = APIRouter()


def _stop_category_for_places(stop: Stop) -> str | None:
    category = stop.category.value
    if category in ALLOWED_NEARBY_TYPES:
        return category

    place_types = stop.place.types or []
    for place_type in place_types:
        if place_type in ALLOWED_NEARBY_TYPES:
            return place_type
    return None


async def _search_around(
    service: NearbyPlacesService,
    lat: float,
    lng: float,
    places_type: str,
) -> NearbyPlacesResponse:
    """The one paid search behind a swap or an added stop."""
    try:
        return await service.search(
            NearbyPlacesRequest(
                query=f"{lat},{lng}",
                categories=[places_type],
                radius_meters=3_000,
                limit=20,
            )
        )
    except PlacesProviderError as exc:
        raise _provider_http_error(exc) from exc


def _not_in_quest(places: list[PlaceItem], quest: Quest) -> list[PlaceItem]:
    """Places the quest does not already visit, matched by id or name and address."""
    used_provider_ids = {s.place.provider_id for s in quest.stops if s.place.provider_id}
    used_place_keys = {(s.place.name.strip().casefold(), s.place.address.strip().casefold()) for s in quest.stops}
    return [
        place
        for place in places
        if place.provider_id not in used_provider_ids
        and (place.name.strip().casefold(), place.address.strip().casefold()) not in used_place_keys
    ]


# The stop in quest_templates.py that says what belongs in each kind a person
# can choose, so that a swap or an added stop is ordered as the generator would.
_KIND_STOPS: dict[StopKind, TemplateStop] = {
    StopKind.meal: MEAL,
    StopKind.coffee: CAFE,
    StopKind.dessert: DESSERT,
    StopKind.drinks: DRINKS,
    StopKind.walk: STROLL,
    StopKind.sights: SIGHT,
    StopKind.movie: PLAY,
    StopKind.bowling: PLAY,
}


def _best_first(
    places: list[PlaceItem],
    quest: Quest,
    anchor: PlaceItem,
    places_type: str,
    wanted: TemplateStop | None,
) -> None:
    """Sort places for one stop: the wanted kind first, then by score.

    A search for `bar` also returns the restaurants that carry the tag, and
    "Dessert" searches bakeries, many of which only take cake orders. Nothing
    is dropped, so a thin area still gets its options.
    """
    popularity_cap = _popularity_cap(quest.occasion, places_type)
    places.sort(
        key=lambda place: (
            wanted is not None
            and not wanted.suits(place.name, place.primary_type, place.types),
            -_score(
                place,
                quest.total_cost_estimate,
                anchor.lat,
                anchor.lng,
                popularity_cap=popularity_cap,
            ),
            place.distance_meters,
        )
    )


def _is_film(stop: Stop) -> bool:
    return stop.category == StopCategory.activity and "movie_theater" in (stop.place.types or [])


def _kind_dwell(kind: StopKind, category: StopCategory) -> int:
    """How long a newly chosen kind of stop takes."""
    if kind == StopKind.movie:
        return FILM_MINUTES
    return _DWELL.get(category, 30)


def _swap_dwell(original: Stop, original_dwell: int, kind: StopKind | None, category: StopCategory) -> int:
    """How long the replacement stop lasts.

    The same sort of stop keeps the time the old one had. A different sort takes
    its own: dinner swapped for coffee should not keep dinner's hour. A film
    counts as a sort of its own, and is never cut short of a film's length.
    """
    if kind is None:
        return original_dwell
    if kind == StopKind.movie:
        return max(original_dwell, FILM_MINUTES) if _is_film(original) else FILM_MINUTES
    if category == original.category and not _is_film(original):
        return original_dwell
    return _kind_dwell(kind, category)


def _band_midpoint(band: CostBand | None) -> int | None:
    if band is None:
        return None
    return round((band.min_inr + band.max_inr) / 2)


def _minutes_between(start: time, end: time) -> int:
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute
    if end_min < start_min:
        end_min += 24 * 60
    return end_min - start_min


@router.get("/api/quests/curated", response_model=list[Quest])
async def get_curated_quests(city: str = Query(min_length=1)) -> list[Quest]:
    """The six hand-made quests for one curated city (key or alias)."""
    found = find_city(city)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"No curated quests for '{city}'.",
                "available_cities": [c.key for c in CURATED_CITIES],
            },
        )
    return found.quests


@router.get("/api/quests/curated/{quest_id}", response_model=Quest)
async def get_curated_quest(quest_id: uuid.UUID) -> Quest:
    """One curated quest by id, so its link opens on any device."""
    quest = find_quest(quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail={"message": "Curated quest not found."})
    return quest


@router.post("/api/quest/generate", response_model=Quest)
async def generate_quest(
    payload: QuestGenerationRequest,
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> Quest:
    try:
        return await assemble_quest(payload, service)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except PlacesProviderError as exc:
        status_code, message = map_provider_error(exc)
        detail: dict[str, object] = {"message": message}
        if exc.provider_status:
            detail["provider_status"] = exc.provider_status
        raise HTTPException(status_code=status_code, detail=detail) from exc


# A 4-stop quest serializes to ~6 KB; the cap only exists so the public
# endpoint can't be used as arbitrary blob storage on the volume.
_MAX_STORE_BYTES = 100_000
_SHORT_ID_PATTERN = r"^[a-z0-9]{4,16}$"


@router.post("/api/quest/store", response_model=StoredQuestCreateResponse)
async def store_shared_quest(request: Request) -> StoredQuestCreateResponse:
    """Persist a quest for short-link sharing (moodyeat.in/q/<short_id>)."""
    body = await request.body()
    if len(body) > _MAX_STORE_BYTES:
        raise HTTPException(status_code=413, detail={"message": "Quest payload is too large."})
    try:
        quest = Quest.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"message": "Invalid quest payload."}) from exc

    short_id = await run_in_threadpool(store_quest, quest)
    return StoredQuestCreateResponse(short_id=short_id, path=f"/q/{short_id}")


@router.get("/api/quest/stored/{short_id}")
async def get_shared_quest(
    short_id: str = Path(pattern=_SHORT_ID_PATTERN),
    count_view: bool = Query(default=True),
) -> JSONResponse:
    """Return a stored quest by short id.

    The stored JSON is returned as-is (not re-validated against the current
    Quest model) so old links keep working even if the model grows stricter.
    count_view=false is for crawler prefetches (OG previews) so the view
    count only measures humans opening the link.
    """
    stored = await run_in_threadpool(fetch_quest, short_id, count_view=count_view)
    if stored is None:
        raise HTTPException(status_code=404, detail={"message": "Shared quest not found."})
    return JSONResponse(content=json.loads(stored.quest_json))


@router.get("/api/quest/stored/{short_id}/stats", response_model=StoredQuestStats)
async def get_shared_quest_stats(
    short_id: str = Path(pattern=_SHORT_ID_PATTERN),
) -> StoredQuestStats:
    stored = await run_in_threadpool(fetch_quest, short_id, count_view=False)
    if stored is None:
        raise HTTPException(status_code=404, detail={"message": "Shared quest not found."})
    return StoredQuestStats(short_id=stored.short_id, views=stored.views, created_at=stored.created_at)


# A swap event is a dozen place ids and a few enums: well under 1 KB.
_MAX_SWAP_LOG_BYTES = 8_000


@router.post("/api/quest/swap-log", status_code=204)
async def log_stop_swap(request: Request) -> Response:
    """Record that someone replaced one suggested place with another.

    The quest page posts this after a swap is confirmed and never waits on
    the answer, so nothing here can slow down or break a swap. See
    swap_log.py for what is stored and why.
    """
    body = await request.body()
    if len(body) > _MAX_SWAP_LOG_BYTES:
        raise HTTPException(status_code=413, detail={"message": "Swap event is too large."})
    try:
        event = SwapEvent.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={"message": "Invalid swap event."}) from exc

    try:
        await run_in_threadpool(record_swap, event)
    except Exception as exc:
        # Losing an event is acceptable; a 5xx keeps the loss visible in the
        # service's request metrics instead of hiding it behind a 204.
        logger.warning("swap_log_failed err_type=%s", exc.__class__.__name__)
        raise HTTPException(
            status_code=503, detail={"message": "Could not record the swap."}
        ) from exc
    return Response(status_code=204)


@router.post(
    "/api/quest/{quest_id}/stop/{stop_index}/alternatives",
    response_model=list[StopAlternative],
)
async def stop_alternatives(
    quest_id: uuid.UUID,
    stop_index: int,
    payload: Quest,
    chosen_kind: StopKind | None = Query(default=None, alias="kind"),
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> list[StopAlternative]:
    """Replacements for one stop: the same type as it is now, or `?kind=`."""
    if payload.id != quest_id:
        raise HTTPException(status_code=422, detail={"message": "Quest id does not match request body."})
    if stop_index < 0 or stop_index >= len(payload.stops):
        raise HTTPException(status_code=404, detail={"message": "Stop index not found."})

    original = payload.stops[stop_index]
    if chosen_kind is None:
        places_type = _stop_category_for_places(original)
        category = original.category
    else:
        places_type, category = STOP_KIND_SEARCHES[chosen_kind]
    if places_type is None:
        raise HTTPException(
            status_code=422,
            detail={"message": f"No nearby-search category is available for '{original.category.value}' stops."},
        )

    previous_stop = payload.stops[stop_index - 1] if stop_index > 0 else None
    next_stop = payload.stops[stop_index + 1] if stop_index + 1 < len(payload.stops) else None
    # The Quest model does not persist a separate start coordinate yet. For the
    # first stop, anchor the search to the stop being replaced as the closest proxy.
    anchor_place = previous_stop.place if previous_stop is not None else original.place

    result = await _search_around(service, anchor_place.lat, anchor_place.lng, places_type)
    candidates = _not_in_quest(result.places, payload)
    # With no kind chosen, more of what the stop already was.
    wanted = (
        _swap_kind(original, places_type, payload.occasion)
        if chosen_kind is None
        else _KIND_STOPS[chosen_kind]
    )
    _best_first(candidates, payload, anchor_place, places_type, wanted)

    original_dwell = _minutes_between(original.time_block_start, original.time_block_end)
    if original_dwell <= 0:
        original_dwell = _DWELL.get(original.category, 30)
    dwell = _swap_dwell(original, original_dwell, chosen_kind, category)

    original_incoming_dist = (
        haversine_m(previous_stop.place.lat, previous_stop.place.lng, original.place.lat, original.place.lng)
        if previous_stop is not None
        else 0.0
    )
    original_incoming_minutes = _travel_time(original_incoming_dist)[0] if previous_stop is not None else 0
    original_outgoing_dist = (
        haversine_m(original.place.lat, original.place.lng, next_stop.place.lat, next_stop.place.lng)
        if next_stop is not None
        else 0.0
    )
    original_outgoing_minutes = original.travel_to_next_minutes or (
        _travel_time(original_outgoing_dist)[0] if next_stop is not None else 0
    )

    original_cost_mid = _band_midpoint(estimate_cost_band(original.place))

    alternatives: list[StopAlternative] = []
    for place in candidates[:6]:
        candidate_incoming_dist = (
            haversine_m(previous_stop.place.lat, previous_stop.place.lng, place.lat, place.lng)
            if previous_stop is not None
            else 0.0
        )
        candidate_incoming_minutes = _travel_time(candidate_incoming_dist)[0] if previous_stop is not None else 0
        candidate_start = (
            _add_min(previous_stop.time_block_end, candidate_incoming_minutes)
            if previous_stop is not None
            else original.time_block_start
        )
        candidate_end = _add_min(candidate_start, dwell)

        candidate_outgoing_dist = (
            haversine_m(place.lat, place.lng, next_stop.place.lat, next_stop.place.lng)
            if next_stop is not None
            else 0.0
        )
        outgoing_pair = _travel_time(candidate_outgoing_dist) if next_stop is not None else None
        candidate_outgoing_minutes = outgoing_pair[0] if outgoing_pair is not None else 0

        candidate_band = estimate_cost_band(place)
        candidate_cost_mid = _band_midpoint(candidate_band)
        cost_change = (
            candidate_cost_mid - original_cost_mid
            if candidate_cost_mid is not None and original_cost_mid is not None
            else 0
        )

        alternatives.append(
            StopAlternative(
                place=place,
                category=category,
                kind=chosen_kind,
                time_block_start=candidate_start,
                time_block_end=candidate_end,
                travel_to_next_minutes=outgoing_pair[0] if outgoing_pair is not None else None,
                travel_mode=outgoing_pair[1] if outgoing_pair is not None else None,
                why_this_place=_why(
                    place,
                    payload.total_cost_estimate,
                    candidate_incoming_dist if previous_stop is not None else place.distance_meters,
                ),
                est_cost_per_person_min_inr=candidate_band.min_inr if candidate_band else None,
                est_cost_per_person_max_inr=candidate_band.max_inr if candidate_band else None,
                price_source=candidate_band.source if candidate_band else None,
                delta=StopSwapDelta(
                    cost_change=cost_change,
                    time_change_minutes=round(
                        (candidate_incoming_minutes + candidate_outgoing_minutes + dwell)
                        - (original_incoming_minutes + original_outgoing_minutes + original_dwell)
                    ),
                    distance_change_meters=round(
                        (candidate_incoming_dist + candidate_outgoing_dist)
                        - (original_incoming_dist + original_outgoing_dist)
                    ),
                ),
            )
        )

    return alternatives


# The most stops the quest page lets a person build up to.
_MAX_QUEST_STOPS = 4


@router.post(
    "/api/quest/{quest_id}/stop/{stop_index}/additions",
    response_model=list[StopAlternative],
)
async def stop_additions(
    quest_id: uuid.UUID,
    stop_index: int,
    payload: Quest,
    chosen_kind: StopKind = Query(alias="kind"),
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> list[StopAlternative]:
    """Places of one kind that could be added right after `stop_index`.

    A route of its own so that a server without it answers 404, rather than
    quietly returning replacements for some other stop. In `delta`, the values
    are what adding the place does to the quest: minutes and metres it grows
    by, and the middle of the new stop's price estimate (0 when unknown).
    """
    if payload.id != quest_id:
        raise HTTPException(status_code=422, detail={"message": "Quest id does not match request body."})
    if stop_index < 0 or stop_index >= len(payload.stops):
        raise HTTPException(status_code=404, detail={"message": "Stop index not found."})
    if len(payload.stops) >= _MAX_QUEST_STOPS:
        raise HTTPException(
            status_code=422,
            detail={"message": f"A quest holds up to {_MAX_QUEST_STOPS} stops."},
        )

    places_type, category = STOP_KIND_SEARCHES[chosen_kind]
    before = payload.stops[stop_index]
    after = payload.stops[stop_index + 1] if stop_index + 1 < len(payload.stops) else None
    anchor = before.place

    result = await _search_around(service, anchor.lat, anchor.lng, places_type)
    candidates = _not_in_quest(result.places, payload)
    _best_first(candidates, payload, anchor, places_type, _KIND_STOPS[chosen_kind])

    dwell = _kind_dwell(chosen_kind, category)
    direct_dist = (
        haversine_m(anchor.lat, anchor.lng, after.place.lat, after.place.lng)
        if after is not None
        else 0.0
    )
    # The hop the new stop replaces, as the quest has it: hand-made quests write
    # their own, and the site keeps the hops an edit does not touch.
    direct_minutes = 0
    if after is not None:
        direct_minutes = (
            before.travel_to_next_minutes
            if before.travel_to_next_minutes is not None
            else _travel_time(direct_dist)[0]
        )

    additions: list[StopAlternative] = []
    for place in candidates[:6]:
        incoming_dist = haversine_m(anchor.lat, anchor.lng, place.lat, place.lng)
        incoming_minutes = _travel_time(incoming_dist)[0]
        start = _add_min(before.time_block_end, incoming_minutes)
        outgoing_dist = (
            haversine_m(place.lat, place.lng, after.place.lat, after.place.lng)
            if after is not None
            else 0.0
        )
        outgoing = _travel_time(outgoing_dist) if after is not None else None
        band = estimate_cost_band(place)
        additions.append(
            StopAlternative(
                place=place,
                category=category,
                kind=chosen_kind,
                time_block_start=start,
                time_block_end=_add_min(start, dwell),
                travel_to_next_minutes=outgoing[0] if outgoing is not None else None,
                travel_mode=outgoing[1] if outgoing is not None else None,
                why_this_place=_why(place, payload.total_cost_estimate, incoming_dist),
                est_cost_per_person_min_inr=band.min_inr if band else None,
                est_cost_per_person_max_inr=band.max_inr if band else None,
                price_source=band.source if band else None,
                delta=StopSwapDelta(
                    cost_change=_band_midpoint(band) or 0,
                    time_change_minutes=round(
                        incoming_minutes + (outgoing[0] if outgoing is not None else 0) + dwell - direct_minutes
                    ),
                    distance_change_meters=round(incoming_dist + outgoing_dist - direct_dist),
                ),
            )
        )

    return additions


@router.post("/api/places/nearby", response_model=NearbyPlacesResponse)
async def nearby_places(
    payload: NearbyPlacesRequest,
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> NearbyPlacesResponse:
    try:
        return await service.search(payload)
    except PlacesProviderError as exc:
        status_code, message = map_provider_error(exc)
        detail: dict[str, object] = {"message": message}
        if exc.provider_status:
            detail["provider_status"] = exc.provider_status
        raise HTTPException(status_code=status_code, detail=detail) from exc


# Google's own limits: a session token is at most 36 URL-safe characters (a
# UUID). The place id ends up in an upstream URL path, hence the strict shape.
_SESSION_TOKEN_PATTERN = r"^[A-Za-z0-9_-]{1,36}$"
_PLACE_ID_PATTERN = PLACE_ID_PATTERN


def _provider_http_error(exc: PlacesProviderError) -> HTTPException:
    status_code, message = map_provider_error(exc)
    detail: dict[str, object] = {"message": message}
    if exc.provider_status:
        detail["provider_status"] = exc.provider_status
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/api/places/autocomplete", response_model=LocationSuggestionsResponse)
async def autocomplete_locations(
    q: str = Query(max_length=120),
    session: str | None = Query(default=None, pattern=_SESSION_TOKEN_PATTERN),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    provider: GooglePlacesProvider = Depends(get_places_provider),
) -> LocationSuggestionsResponse:
    """Suggestions for the "Where?" field as the user types.

    `lat`/`lng` are a rough idea of where the user is; places near there are
    offered first. Without them the suggestions are not tied to any area.
    """
    text = q.strip()
    if len(text) < 2:
        return LocationSuggestionsResponse(suggestions=[])
    bias = (lat, lng) if lat is not None and lng is not None else None
    try:
        found = await provider.suggest_locations(text, session_token=session, bias=bias)
    except PlacesProviderError as exc:
        raise _provider_http_error(exc) from exc
    return LocationSuggestionsResponse(
        suggestions=[
            LocationSuggestion(
                place_id=s.place_id,
                main_text=s.main_text,
                secondary_text=s.secondary_text,
            )
            for s in found
        ]
    )


@router.get("/api/places/autocomplete/location", response_model=SuggestionLocation)
async def autocomplete_location(
    place_id: str = Query(pattern=_PLACE_ID_PATTERN),
    session: str | None = Query(default=None, pattern=_SESSION_TOKEN_PATTERN),
    provider: GooglePlacesProvider = Depends(get_places_provider),
) -> SuggestionLocation:
    """Coordinates of the suggestion the user picked."""
    try:
        lat, lng = await provider.suggestion_location(place_id, session_token=session)
    except PlacesProviderError as exc:
        raise _provider_http_error(exc) from exc
    return SuggestionLocation(lat=lat, lng=lng)


@router.post("/api/places/search", response_model=NearbyPlacesResponse)
async def search_places_by_name(
    payload: NameSearchRequest,
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> NearbyPlacesResponse:
    """Find a place by its name for the build-your-own page.

    A POST so the typed text stays out of request logs; it is not stored.
    """
    has_position = payload.lat is not None and payload.lng is not None
    if not has_position and not (payload.area or "").strip():
        raise HTTPException(status_code=422, detail={"message": "Pick an area first."})
    try:
        return await service.search_by_name(
            text=payload.q, lat=payload.lat, lng=payload.lng, area=payload.area
        )
    except LocationNotFoundError as exc:
        # `code` tells this apart from the plain 404 of a backend that does not
        # have this endpoint yet.
        raise HTTPException(
            status_code=404,
            detail={"message": "We couldn't find that area.", "code": "area_not_found"},
        ) from exc
    except PlacesProviderError as exc:
        raise _provider_http_error(exc) from exc


@router.get("/api/places/photo")
async def place_photo(
    place_id: str = Query(min_length=1),
    max_width: int = Query(default=800, ge=100, le=1600),
) -> Response:
    result = await fetch_place_photo(place_id, max_width)
    if result is None:
        raise HTTPException(status_code=404, detail="Photo not available")
    data, content_type = result
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/api/places/blurbs", response_model=PlaceBlurbsResponse)
async def place_blurbs(payload: PlaceBlurbsRequest) -> PlaceBlurbsResponse:
    blurbs = await generate_place_blurbs(
        payload.places,
        payload.mood.strip(),
        payload.budget.strip(),
        payload.people,
    )
    return PlaceBlurbsResponse(blurbs=blurbs)

