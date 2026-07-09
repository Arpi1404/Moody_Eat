import uuid
from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from curated_quests import CURATED_QUESTS
from deps import get_nearby_places_service
from models import (
    ALLOWED_NEARBY_TYPES,
    NearbyPlacesRequest,
    NearbyPlacesResponse,
    PlaceBlurbsRequest,
    PlaceBlurbsResponse,
    Quest,
    QuestGenerationRequest,
    Stop,
    StopAlternative,
    StopSwapDelta,
)
from quest_generator import (
    _DWELL,
    _add_min,
    _score,
    _travel_time,
    _why,
    assemble_quest,
    haversine_m,
)
from services.nearby_places_service import NearbyPlacesService, map_provider_error
from services.place_blurbs_service import generate_place_blurbs
from services.place_photo_service import fetch_place_photo
from services.places_exceptions import PlacesProviderError

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


def _minutes_between(start: time, end: time) -> int:
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute
    if end_min < start_min:
        end_min += 24 * 60
    return end_min - start_min


@router.get("/api/quests/curated", response_model=list[Quest])
async def get_curated_quests(city: str = Query(min_length=1)) -> list[Quest]:
    key = city.strip().lower()
    if key not in CURATED_QUESTS:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"No curated quests for '{city}'.",
                "available_cities": list(CURATED_QUESTS.keys()),
            },
        )
    return CURATED_QUESTS[key]


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


@router.post(
    "/api/quest/{quest_id}/stop/{stop_index}/alternatives",
    response_model=list[StopAlternative],
)
async def stop_alternatives(
    quest_id: uuid.UUID,
    stop_index: int,
    payload: Quest,
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> list[StopAlternative]:
    if payload.id != quest_id:
        raise HTTPException(status_code=422, detail={"message": "Quest id does not match request body."})
    if stop_index < 0 or stop_index >= len(payload.stops):
        raise HTTPException(status_code=404, detail={"message": "Stop index not found."})

    original = payload.stops[stop_index]
    places_type = _stop_category_for_places(original)
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

    try:
        result = await service.search(
            NearbyPlacesRequest(
                query=f"{anchor_place.lat},{anchor_place.lng}",
                categories=[places_type],
                radius_meters=3_000,
                limit=20,
            )
        )
    except PlacesProviderError as exc:
        status_code, message = map_provider_error(exc)
        detail: dict[str, object] = {"message": message}
        if exc.provider_status:
            detail["provider_status"] = exc.provider_status
        raise HTTPException(status_code=status_code, detail=detail) from exc

    used_provider_ids = {s.place.provider_id for s in payload.stops if s.place.provider_id}
    used_place_keys = {(s.place.name.strip().casefold(), s.place.address.strip().casefold()) for s in payload.stops}
    candidates = [
        place
        for place in result.places
        if place.provider_id not in used_provider_ids
        and (place.name.strip().casefold(), place.address.strip().casefold()) not in used_place_keys
    ]
    candidates.sort(
        key=lambda place: (
            -_score(place, payload.total_cost_estimate, anchor_place.lat, anchor_place.lng),
            place.distance_meters,
        )
    )

    original_dwell = _minutes_between(original.time_block_start, original.time_block_end)
    if original_dwell <= 0:
        original_dwell = _DWELL.get(original.category, 30)

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
        candidate_end = _add_min(candidate_start, original_dwell)

        candidate_outgoing_dist = (
            haversine_m(place.lat, place.lng, next_stop.place.lat, next_stop.place.lng)
            if next_stop is not None
            else 0.0
        )
        outgoing_pair = _travel_time(candidate_outgoing_dist) if next_stop is not None else None
        candidate_outgoing_minutes = outgoing_pair[0] if outgoing_pair is not None else 0

        alternatives.append(
            StopAlternative(
                place=place,
                category=original.category,
                time_block_start=candidate_start,
                time_block_end=candidate_end,
                travel_to_next_minutes=outgoing_pair[0] if outgoing_pair is not None else None,
                travel_mode=outgoing_pair[1] if outgoing_pair is not None else None,
                why_this_place=_why(
                    place,
                    payload.total_cost_estimate,
                    candidate_incoming_dist if previous_stop is not None else place.distance_meters,
                ),
                delta=StopSwapDelta(
                    cost_change=0,
                    time_change_minutes=round(
                        (candidate_incoming_minutes + candidate_outgoing_minutes)
                        - (original_incoming_minutes + original_outgoing_minutes)
                    ),
                    distance_change_meters=round(
                        (candidate_incoming_dist + candidate_outgoing_dist)
                        - (original_incoming_dist + original_outgoing_dist)
                    ),
                ),
            )
        )

    return alternatives


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

