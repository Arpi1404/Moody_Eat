import uuid
from datetime import datetime, time

from models import (
    CostEstimate,
    Occasion,
    PlaceItem,
    Quest,
    Stop,
    StopCategory,
    TravelMode,
)


def _place(
    provider_id: str,
    name: str,
    address: str,
    lat: float,
    lng: float,
    rating: float,
    types: list[str],
) -> PlaceItem:
    return PlaceItem(
        provider_id=provider_id,
        name=name,
        address=address,
        lat=lat,
        lng=lng,
        distance_meters=0,
        rating=rating,
        user_ratings_total=250,
        business_status="OPERATIONAL",
        types=types,
    )


def _stop(
    place: PlaceItem,
    category: StopCategory,
    start: time,
    end: time,
    why: str,
    travel_to_next_minutes: int | None = None,
) -> Stop:
    return Stop(
        place=place,
        category=category,
        time_block_start=start,
        time_block_end=end,
        travel_to_next_minutes=travel_to_next_minutes,
        travel_mode=TravelMode.driving if travel_to_next_minutes is not None else None,
        why_this_place=why,
    )


_CREATED_AT = datetime(2026, 5, 5, 18, 0, 0)

_HYDERABAD_QUESTS = [
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        title="Durgam Cheruvu Date Quest",
        occasion=Occasion.date,
        total_duration_minutes=190,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A calm date-night route with dinner first, dessert after, and a lakefront finish "
            "so the evening has room to slow down."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-hyd-date-dinner",
                    "Olive Bistro",
                    "Road 46, Jubilee Hills, Hyderabad",
                    17.4308,
                    78.3928,
                    4.3,
                    ["restaurant", "food"],
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 20),
                "Warm lighting and a dinner-first pace make it easy to settle into the evening.",
                14,
            ),
            _stop(
                _place(
                    "curated-hyd-date-dessert",
                    "Concu",
                    "Jubilee Hills, Hyderabad",
                    17.4319,
                    78.4071,
                    4.4,
                    ["cafe", "bakery"],
                ),
                StopCategory.cafe,
                time(20, 34),
                time(21, 10),
                "A polished dessert stop that keeps the night light without turning it into another meal.",
                10,
            ),
            _stop(
                _place(
                    "curated-hyd-date-walk",
                    "Durgam Cheruvu Lakefront",
                    "Durgam Cheruvu, Hyderabad",
                    17.4300,
                    78.3899,
                    4.5,
                    ["tourist_attraction", "park"],
                ),
                StopCategory.attraction,
                time(21, 20),
                time(22, 10),
                "A low-pressure final stop for a walk, photos, and a calmer end to the date.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000002"),
        title="Banjara Friends Food Run",
        occasion=Occasion.friends,
        total_duration_minutes=205,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A social evening built around familiar food, a lively second stop, and dessert that works "
            "for groups who keep talking after dinner."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-hyd-friends-dinner",
                    "Chutneys",
                    "Banjara Hills, Hyderabad",
                    17.4148,
                    78.4385,
                    4.2,
                    ["restaurant", "food"],
                ),
                StopCategory.restaurant,
                time(18, 45),
                time(20, 0),
                "Fast-moving comfort food keeps the group fed without making the first stop too formal.",
                12,
            ),
            _stop(
                _place(
                    "curated-hyd-friends-activity",
                    "GVK One",
                    "Banjara Hills, Hyderabad",
                    17.4190,
                    78.4485,
                    4.4,
                    ["shopping_mall", "activity"],
                ),
                StopCategory.activity,
                time(20, 12),
                time(21, 35),
                "A flexible middle stop where the group can walk, browse, or split for quick snacks.",
                9,
            ),
            _stop(
                _place(
                    "curated-hyd-friends-dessert",
                    "Cream Stone",
                    "Banjara Hills, Hyderabad",
                    17.4136,
                    78.4497,
                    4.2,
                    ["bakery", "food"],
                ),
                StopCategory.cafe,
                time(21, 44),
                time(22, 10),
                "Shared dessert makes a simple final milestone before everyone heads home.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000003"),
        title="Solo Reset Loop",
        occasion=Occasion.solo,
        total_duration_minutes=160,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "A quieter solo route with coffee, green space, and a small snack stop so the plan feels "
            "restorative instead of packed."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-hyd-solo-coffee",
                    "Roastery Coffee House",
                    "Banjara Hills, Hyderabad",
                    17.4215,
                    78.4266,
                    4.4,
                    ["cafe", "food"],
                ),
                StopCategory.cafe,
                time(17, 30),
                time(18, 25),
                "Good coffee and calmer seating make it a friendly first stop for solo time.",
                10,
            ),
            _stop(
                _place(
                    "curated-hyd-solo-walk",
                    "KBR National Park",
                    "Jubilee Hills, Hyderabad",
                    17.4239,
                    78.4212,
                    4.5,
                    ["park", "tourist_attraction"],
                ),
                StopCategory.attraction,
                time(18, 35),
                time(19, 25),
                "A green reset between food stops, with enough movement to make the outing feel fresh.",
                12,
            ),
            _stop(
                _place(
                    "curated-hyd-solo-snack",
                    "Subhan Bakery",
                    "Nampally, Hyderabad",
                    17.3918,
                    78.4677,
                    4.3,
                    ["bakery", "food"],
                ),
                StopCategory.cafe,
                time(19, 37),
                time(20, 10),
                "A low-cost final treat that keeps the solo quest light and satisfying.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000004"),
        title="Family Easy Evening",
        occasion=Occasion.family,
        total_duration_minutes=180,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A family-friendly plan with predictable food, an open-air pause, and dessert at the end "
            "so no one has to overthink the route."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-hyd-family-dinner",
                    "Ohri's Jiva Imperia",
                    "Begumpet, Hyderabad",
                    17.4445,
                    78.4660,
                    4.1,
                    ["restaurant", "food"],
                ),
                StopCategory.restaurant,
                time(18, 30),
                time(19, 45),
                "A broad menu and comfortable seating make it easier for mixed age groups.",
                14,
            ),
            _stop(
                _place(
                    "curated-hyd-family-walk",
                    "Necklace Road",
                    "Hussain Sagar, Hyderabad",
                    17.4239,
                    78.4738,
                    4.4,
                    ["tourist_attraction", "park"],
                ),
                StopCategory.attraction,
                time(19, 59),
                time(20, 45),
                "An open, simple middle stop where everyone can walk without committing to another booking.",
                10,
            ),
            _stop(
                _place(
                    "curated-hyd-family-dessert",
                    "Karachi Bakery",
                    "Moazzam Jahi Market, Hyderabad",
                    17.3846,
                    78.4747,
                    4.3,
                    ["bakery", "food"],
                ),
                StopCategory.cafe,
                time(20, 55),
                time(21, 30),
                "A classic dessert-and-snack finish that works whether the family wants sweets or take-home treats.",
            ),
        ],
    ),
]

_GURGAON_QUESTS = [
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
        title="CyberHub Date Quest",
        occasion=Occasion.date,
        total_duration_minutes=185,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A compact date-night plan around CyberHub: dinner, dessert, and an easy walk so the "
            "evening feels planned without becoming rushed."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-ggn-date-dinner",
                    "SodaBottleOpenerWala",
                    "CyberHub, DLF Cyber City, Gurugram",
                    28.4958,
                    77.0892,
                    4.2,
                    ["restaurant", "food"],
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 15),
                "A lively dinner spot that keeps the first stop warm, casual, and conversation-friendly.",
                6,
            ),
            _stop(
                _place(
                    "curated-ggn-date-dessert",
                    "Theobroma",
                    "CyberHub, DLF Cyber City, Gurugram",
                    28.4965,
                    77.0898,
                    4.3,
                    ["bakery", "cafe"],
                ),
                StopCategory.cafe,
                time(20, 21),
                time(20, 55),
                "A low-commitment dessert stop that gives the date a sweet second beat.",
                8,
            ),
            _stop(
                _place(
                    "curated-ggn-date-walk",
                    "CyberHub Promenade",
                    "DLF Cyber City, Gurugram",
                    28.4960,
                    77.0887,
                    4.4,
                    ["tourist_attraction", "activity"],
                ),
                StopCategory.activity,
                time(21, 3),
                time(22, 5),
                "An easy final walk with lights, music, and enough energy to end the night naturally.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000002"),
        title="32nd Avenue Friends Trail",
        occasion=Occasion.friends,
        total_duration_minutes=210,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A group-friendly route with food, browsing, and dessert clustered tightly enough that "
            "nobody has to coordinate a long transfer."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-ggn-friends-dinner",
                    "Como Pizzeria",
                    "32nd Avenue, Sector 15, Gurugram",
                    28.4597,
                    77.0474,
                    4.4,
                    ["restaurant", "food"],
                ),
                StopCategory.restaurant,
                time(18, 45),
                time(20, 0),
                "Pizza works well for groups because it is easy to share and keeps the mood casual.",
                5,
            ),
            _stop(
                _place(
                    "curated-ggn-friends-activity",
                    "32nd Avenue",
                    "Sector 15, Gurugram",
                    28.4594,
                    77.0471,
                    4.5,
                    ["activity", "tourist_attraction"],
                ),
                StopCategory.activity,
                time(20, 5),
                time(21, 25),
                "A flexible hangout stretch for photos, browsing, and deciding what the group wants next.",
                6,
            ),
            _stop(
                _place(
                    "curated-ggn-friends-dessert",
                    "Sibang Bakery",
                    "South Point Mall, Golf Course Road, Gurugram",
                    28.4599,
                    77.0935,
                    4.4,
                    ["bakery", "cafe"],
                ),
                StopCategory.cafe,
                time(21, 31),
                time(22, 15),
                "A bakery finish gives the group one last shared stop without making the evening heavier.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000003"),
        title="Solo Aravalli Reset",
        occasion=Occasion.solo,
        total_duration_minutes=165,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "A lighter solo plan that pairs a calm cafe stop with greenery and a simple snack, built "
            "for clearing your head."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-ggn-solo-cafe",
                    "Roots Cafe",
                    "Leisure Valley Road, Sector 29, Gurugram",
                    28.4670,
                    77.0644,
                    4.2,
                    ["cafe", "food"],
                ),
                StopCategory.cafe,
                time(17, 30),
                time(18, 25),
                "A relaxed first stop for coffee, reading, or easing into a solo evening.",
                14,
            ),
            _stop(
                _place(
                    "curated-ggn-solo-walk",
                    "Aravalli Biodiversity Park",
                    "MG Road, Gurugram",
                    28.4806,
                    77.1074,
                    4.5,
                    ["park", "tourist_attraction"],
                ),
                StopCategory.attraction,
                time(18, 39),
                time(19, 30),
                "Green space adds the reset part of the quest without requiring a packed schedule.",
                11,
            ),
            _stop(
                _place(
                    "curated-ggn-solo-snack",
                    "Galleria Market",
                    "DLF Phase IV, Gurugram",
                    28.4649,
                    77.0838,
                    4.3,
                    ["activity", "food"],
                ),
                StopCategory.activity,
                time(19, 41),
                time(20, 15),
                "A flexible final stop where you can grab a small snack or just browse before heading home.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000004"),
        title="Family Galleria Evening",
        occasion=Occasion.family,
        total_duration_minutes=175,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A family-friendly route with familiar food, a low-stress market walk, and dessert close by "
            "so the plan stays easy."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "curated-ggn-family-dinner",
                    "The Big Chill",
                    "DLF Galleria, Gurugram",
                    28.4652,
                    77.0837,
                    4.4,
                    ["restaurant", "food"],
                ),
                StopCategory.restaurant,
                time(18, 30),
                time(19, 45),
                "A familiar menu and comfortable setting make it easier for mixed preferences.",
                4,
            ),
            _stop(
                _place(
                    "curated-ggn-family-walk",
                    "Galleria Market",
                    "DLF Phase IV, Gurugram",
                    28.4649,
                    77.0838,
                    4.3,
                    ["activity", "shopping_mall"],
                ),
                StopCategory.activity,
                time(19, 49),
                time(20, 35),
                "A simple walk-and-browse stop keeps the family moving without needing another booking.",
                6,
            ),
            _stop(
                _place(
                    "curated-ggn-family-dessert",
                    "Binge Bakery",
                    "Galleria Market, Gurugram",
                    28.4650,
                    77.0840,
                    4.2,
                    ["bakery", "cafe"],
                ),
                StopCategory.cafe,
                time(20, 41),
                time(21, 25),
                "A nearby dessert stop gives the outing a clear final milestone before heading back.",
            ),
        ],
    ),
]

CURATED_QUESTS: dict[str, list[Quest]] = {
    "hyderabad": _HYDERABAD_QUESTS,
    "secunderabad": _HYDERABAD_QUESTS,
    "gurgaon": _GURGAON_QUESTS,
    "gurugram": _GURGAON_QUESTS,
}
