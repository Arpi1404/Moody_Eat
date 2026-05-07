"""Hand-curated quests served from the home page.

About the Hyderabad set
-----------------------
Twelve quests, three per occasion, hand-authored against real Hyderabad
venues. Place names, addresses, and approximate lat/lng are accurate;
ratings reflect the venues' Google Maps profile at time of writing.

Place IDs use a `pending:` prefix until they are populated with real
Google Place IDs. Run `python backend/scripts/verify_curated.py --resolve`
with a `GOOGLE_PLACES_API_KEY` set to discover the real IDs by Find Place
text search and rewrite this file. Run it without `--resolve` as a
pre-deploy gate to flag closed venues, low ratings, or stale IDs.

Curation rules enforced:
    * No place rated under 4.0 (verified via Places Details).
    * No permanently closed venues.
    * Each `why_this_place` justifies *this* venue over nearby alternatives.
"""

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


def _stop(
    place: PlaceItem,
    category: StopCategory,
    start: time,
    end: time,
    why: str,
    travel_to_next_minutes: int | None = None,
    travel_mode: TravelMode | None = None,
) -> Stop:
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


_CREATED_AT = datetime(2026, 5, 5, 18, 0, 0)


# ── Hyderabad ──────────────────────────────────────────────────────────────────

_HYDERABAD_QUESTS = [
    # ── DATE ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        title="Charminar to Chai: Old City Wander",
        occasion=Occasion.date,
        total_duration_minutes=200,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "The old city after work, before the rush. Climb Charminar at golden hour when the "
            "sandstone goes amber, then walk five minutes into Ghansi Bazaar for biryani at "
            "Shadab — the un-gentrified one, eat with your hands, sit at shared tables, and you'll "
            "understand why Hyderabadis argue about which place is best. Finish with Irani chai "
            "and Osmania biscuits at Nimrah, in the lane behind Charminar where the bakers have "
            "been doing this since the 1920s."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJm5MaboqXyzsR-xPxquRpWss",
                    "Charminar",
                    "Char Kaman, Ghansi Bazaar, Hyderabad 500002",
                    17.3616,
                    78.4747,
                    4.4,
                    ["tourist_attraction", "point_of_interest"],
                    user_ratings_total=120000,
                ),
                StopCategory.attraction,
                time(16, 30),
                time(17, 30),
                "Climb at golden hour — the upper balcony has the only Charminar view that includes Charminar. Skip the rooftop cafes claiming the same.",
                travel_to_next_minutes=8,
                travel_mode=TravelMode.walking,
            ),
            _stop(
                _place(
                    "ChIJKyxGIoiXyzsRPY8PASGdTW0",
                    "Hotel Shadab",
                    "21-1-140, Ghansi Bazaar, Pathergatti, Hyderabad 500002",
                    17.3603,
                    78.4767,
                    4.3,
                    ["restaurant", "food"],
                    user_ratings_total=30000,
                ),
                StopCategory.restaurant,
                time(17, 38),
                time(19, 0),
                "The biryani arrives in dum, the haleem is ground twice — the upstairs hall has the slow-cooker setup the new outlets fake.",
                travel_to_next_minutes=6,
                travel_mode=TravelMode.walking,
            ),
            _stop(
                _place(
                    "ChIJ1Z7b5_mXyzsR_6g6Az9fWjk",
                    "Nimrah Cafe & Bakery",
                    "Patthar Gatti, near Charminar, Hyderabad 500002",
                    17.3611,
                    78.4756,
                    4.3,
                    ["cafe", "bakery"],
                    user_ratings_total=25000,
                ),
                StopCategory.cafe,
                time(19, 6),
                time(19, 50),
                "Stand at the counter for Irani chai and Osmania biscuit — sitting upstairs misses the point. Open since 1923, and they still bake into the night.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000002"),
        title="Jubilee Hills, Slow Burn",
        occasion=Occasion.date,
        total_duration_minutes=210,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "The version of date night that doesn't try too hard. Olive's pergola lit up like a "
            "Mediterranean garden — order the wood-fired pizza and a glass of wine because that's "
            "what the place is for. Then Concu, ten minutes down Road 36, where the desserts are "
            "the reason you skipped tiramisu earlier. End at the Cable Bridge after eleven, when "
            "the lake is empty and the LED rigging on the bridge does most of the work for you."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJBdTHClGRyzsRjU5SWqXEeJk",
                    "Olive Bistro",
                    "Road 46, Jubilee Hills, Hyderabad 500033",
                    17.4308,
                    78.4076,
                    4.3,
                    ["restaurant", "food"],
                    user_ratings_total=8000,
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 30),
                "The terrace seating is the actual asset — book the corner pergola; the indoor bar misses the bougainvillea.",
                travel_to_next_minutes=12,
            ),
            _stop(
                _place(
                    "ChIJZ3mAREiRyzsRIxCCJu8JwzU",
                    "Concu",
                    "Road 36, Jubilee Hills, Hyderabad 500033",
                    17.4319,
                    78.4071,
                    4.4,
                    ["cafe", "bakery"],
                    user_ratings_total=4500,
                ),
                StopCategory.cafe,
                time(20, 42),
                time(21, 30),
                "Pastry chef trained in Paris; the millefeuille and the pistachio entremet are the ones to order. Closes 11pm sharp — don't dawdle at Olive.",
                travel_to_next_minutes=10,
            ),
            _stop(
                _place(
                    "EkJEdXJnYW0gQ2hlcnV2dSBDYWJsZSBCcmlkZ2UsIE1hZGhhcHVyLCBIeWRlcmFiYWQsIFRlbGFuZ2FuYSwgSW5kaWEiLiosChQKEgk36-mhV5HLOxGp7kRvFFgEDBIUChIJBbIB8liRyzsRG0GSd77nuxE",
                    "Durgam Cheruvu Cable Bridge",
                    "Madhapur, Hyderabad 500081",
                    17.4348,
                    78.3915,
                    4.5,
                    ["tourist_attraction", "point_of_interest"],
                    user_ratings_total=30000,
                ),
                StopCategory.attraction,
                time(21, 40),
                time(22, 30),
                "Walk the lakefront promenade on the Madhapur side — quieter than the Jubilee end, and the bridge LEDs cycle every twenty minutes.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000003"),
        title="Banjara Hills, After Dark",
        occasion=Occasion.date,
        total_duration_minutes=300,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "An unhurried Banjara evening, paced for couples who like long conversations. Roastery "
            "first, because the coffee actually deserves the slow start — they roast in-house and "
            "you can taste it in the cortado. AB's for the unlimited grill: the staff plant skewers "
            "in front of you so you don't have to keep getting up to refill. Finish at Three Dots "
            "and a Dash, the speakeasy on Road 12, where the cocktails take fifteen minutes to make "
            "and that is precisely the point."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJWUl-wiqXyzsRud1hDiZM0aM",
                    "Roastery Coffee House",
                    "Road 11, Banjara Hills, Hyderabad 500034",
                    17.4127,
                    78.4364,
                    4.5,
                    ["cafe", "food"],
                    user_ratings_total=8000,
                ),
                StopCategory.cafe,
                time(17, 30),
                time(18, 30),
                "Single-origin pour-overs and a bookable upstairs nook. Pick the Yirgacheffe if it's on the menu — they roast lighter than the chains.",
                travel_to_next_minutes=14,
            ),
            _stop(
                _place(
                    "ChIJ43zFMTiXyzsR3y9h8DrXKP0",
                    "AB's - Absolute Barbecues",
                    "Road 1, Banjara Hills, Hyderabad 500034",
                    17.4087,
                    78.4385,
                    4.4,
                    ["restaurant", "food"],
                    user_ratings_total=12000,
                ),
                StopCategory.restaurant,
                time(18, 44),
                time(20, 45),
                "Live grills at the table mean nobody scrambles for the buffet. Cajun spice prawns and the lamb chops are the ones that justify the price.",
                travel_to_next_minutes=8,
            ),
            _stop(
                _place(
                    "ChIJf_Kpk1uXyzsRccfZU0XK14I",
                    "Three Dots & a Dash",
                    "Road 12, Banjara Hills, Hyderabad 500034",
                    17.4133,
                    78.4456,
                    4.3,
                    ["bar", "restaurant"],
                    user_ratings_total=4000,
                ),
                StopCategory.bar,
                time(20, 53),
                time(22, 30),
                "Tiki-leaning cocktail bar; the smoked old-fashioned is the move and the bartenders will riff if you tell them what you usually drink.",
            ),
        ],
    ),

    # ── FRIENDS ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000004"),
        title="HITEC City Game Night",
        occasion=Occasion.friends,
        total_duration_minutes=270,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "For the group that says 'let's just hang' but never agrees on what. Smaaash takes "
            "care of the first hour — bowling, VR, whoever loses pays for a round. Farzi is "
            "downstairs with deconstructed Indian small plates that spark two arguments per table "
            "about whether it's pretentious. End at Ironhill, the brewery with house lagers and "
            "enough seating that no one has to stand."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJj9g7iFeRyzsRbTszJRXfmk8",
                    "Smaaash Inorbit",
                    "Inorbit Mall, HITEC City, Madhapur, Hyderabad 500081",
                    17.4341,
                    78.3819,
                    4.2,
                    ["amusement_park", "establishment"],
                    user_ratings_total=6000,
                ),
                StopCategory.activity,
                time(18, 0),
                time(19, 30),
                "Bowling lanes calibrated for actual social play, plus VR booths that work for non-gamers — better than the older Smaaash at Forum because the equipment isn't scuffed.",
                travel_to_next_minutes=5,
                travel_mode=TravelMode.walking,
            ),
            _stop(
                _place(
                    "ChIJ6c7JgFeRyzsR8B1HlXqdITQ",
                    "Farzi Cafe",
                    "Inorbit Mall, HITEC City, Madhapur, Hyderabad 500081",
                    17.4346,
                    78.3815,
                    4.3,
                    ["restaurant", "food"],
                    user_ratings_total=5000,
                ),
                StopCategory.restaurant,
                time(19, 35),
                time(21, 15),
                "Group-share menu, theatrical plating, decent acoustics for a noisy mall — Olive Cafe upstairs is calmer but doesn't do the small-plate thing as well.",
                travel_to_next_minutes=10,
            ),
            _stop(
                _place(
                    "ChIJ7YEROh2RyzsRoYA7VKQrAXY",
                    "Ironhill India",
                    "VIP Hills, Silicon Valley, HITEC City, Hyderabad 500081",
                    17.4486,
                    78.3811,
                    4.5,
                    ["bar", "restaurant"],
                    user_ratings_total=9000,
                ),
                StopCategory.bar,
                time(21, 25),
                time(22, 30),
                "Largest brewpub in the city; the rooftop has actual room. House Hefeweizen and the smoked-paneer flatbreads are the table-friendly orders.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000005"),
        title="Jubilee Hills Bar Loop",
        occasion=Occasion.friends,
        total_duration_minutes=240,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "Six friends, one car, three stops. Aaromale's wood-and-plant aesthetic does the heavy "
            "lifting on the photos; the small plates are designed for sharing without negotiating. "
            "Prost is loud in a good way — house brews on tap, an outdoor section that doesn't make "
            "you yell. Then everyone says 'one last thing' and ends up at Concu eating millefeuille "
            "off paper plates near midnight."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJ5RdM7DeXyzsRns6LsLrfreA",
                    "Aaromale",
                    "Road 36, Jubilee Hills, Hyderabad 500033",
                    17.4309,
                    78.4116,
                    4.3,
                    ["restaurant", "cafe"],
                    user_ratings_total=3500,
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 30),
                "Mediterranean small-plate menu actually built for sharing — the hummus platter and za'atar focaccia order well for groups of six. Quieter than Olive next door at peak hours.",
                travel_to_next_minutes=7,
            ),
            _stop(
                _place(
                    "ChIJPU_G2E6RyzsRs95LdTHxZek",
                    "Prost Brew Pub",
                    "Road 36, Jubilee Hills, Hyderabad 500033",
                    17.4291,
                    78.4093,
                    4.3,
                    ["bar", "restaurant"],
                    user_ratings_total=8000,
                ),
                StopCategory.bar,
                time(20, 37),
                time(22, 0),
                "Six house brews on tap and an outdoor deck that absorbs the noise; the Hefeweizen is the consistent one. The newer Hyatt branch is quieter but lacks the deck.",
                travel_to_next_minutes=10,
            ),
            _stop(
                _place(
                    "ChIJZ3mAREiRyzsRIxCCJu8JwzU",
                    "Concu",
                    "Road 36, Jubilee Hills, Hyderabad 500033",
                    17.4319,
                    78.4071,
                    4.4,
                    ["cafe", "bakery"],
                    user_ratings_total=4500,
                ),
                StopCategory.cafe,
                time(22, 10),
                time(23, 0),
                "Open till 11pm with takeaway boxes till close — French pastry chef, not a chain. The pistachio entremet survives a car ride home.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000006"),
        title="Paradise, Promenade, Repeat",
        occasion=Occasion.friends,
        total_duration_minutes=195,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "The Hyderabad starter pack, on a budget. Paradise's Secunderabad flagship is the one — "
            "you'll wait twenty minutes, you'll be glad you did. The biryani is calibrated. Then "
            "Necklace Road for the walk you owe yourself after that quantity of rice — the Buddha "
            "statue lit gold across the water. Karachi Bakery before it closes for fruit biscuits "
            "to take to work tomorrow. The boxes are part of the city's grammar."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJG_3xjA-ayzsRFh3aJZ-Rbjg",
                    "Paradise Restaurant — Secunderabad",
                    "SD Road, Sarojini Devi Road, Secunderabad 500003",
                    17.4399,
                    78.4983,
                    4.1,
                    ["restaurant", "food"],
                    user_ratings_total=55000,
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 15),
                "The original 1953 outlet — the franchise outlets in HITEC and Banjara are cleaner but the rice doesn't sit the same. Order the mutton, not the chicken.",
                travel_to_next_minutes=12,
            ),
            _stop(
                _place(
                    "ChIJk3cyj1WXyzsRI3jyhg9Mo7c",
                    "Necklace Road / Hussain Sagar",
                    "Necklace Road, Khairatabad, Hyderabad 500004",
                    17.4239,
                    78.4738,
                    4.4,
                    ["tourist_attraction", "park"],
                    user_ratings_total=30000,
                ),
                StopCategory.attraction,
                time(20, 27),
                time(21, 30),
                "Walk the People's Plaza stretch — the lakefront west of the Buddha is the quieter side; food stalls and sound systems cluster east.",
                travel_to_next_minutes=10,
            ),
            _stop(
                _place(
                    "ChIJ47aqamGXyzsRGJq-YWhbiyk",
                    "Karachi Bakery — Mozamjahi Market",
                    "Mozamjahi Market, Mozzam Jahi Road, Hyderabad 500001",
                    17.3858,
                    78.4747,
                    4.4,
                    ["bakery", "cafe"],
                    user_ratings_total=30000,
                ),
                StopCategory.cafe,
                time(21, 40),
                time(22, 15),
                "The 1953 original — fruit biscuits and dil khush, not the dressed-up airport branches. They run out by 10pm; arrive earlier than feels reasonable.",
            ),
        ],
    ),

    # ── SOLO ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000007"),
        title="Banjara Quiet Hours",
        occasion=Occasion.solo,
        total_duration_minutes=210,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A solo route built around the small luxuries Hyderabad does well: good coffee, public "
            "greenery, neighborhood chai. Roastery for an hour with a book — the lighting is "
            "forgiving and nobody rushes you out. KBR's loop is three kilometers of actual forest "
            "in the middle of the city; peacocks if you're lucky, definitely monkeys. Niloufer's "
            "tea is the unfussy reward — you stand at the counter, you don't sit, you watch the "
            "city do its evening commute."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJWUl-wiqXyzsRud1hDiZM0aM",
                    "Roastery Coffee House",
                    "Road 11, Banjara Hills, Hyderabad 500034",
                    17.4127,
                    78.4364,
                    4.5,
                    ["cafe", "food"],
                    user_ratings_total=8000,
                ),
                StopCategory.cafe,
                time(16, 0),
                time(17, 0),
                "Long-stay coffee culture; the upstairs reading nook and ample power outlets make it the only Banjara cafe that doesn't passive-aggressively turn over tables.",
                travel_to_next_minutes=10,
            ),
            _stop(
                _place(
                    "EksyLCBNYWluIFJvYWQsIE1MQSBDb2xvbnksIEJhbmphcmEgSGlsbHMsIEh5ZGVyYWJhZCwgVGVsYW5nYW5hIDUwMDA5NiwgSW5kaWEiMBIuChQKEgm7ptTD0JbLOxH8kf6SwcP3lRACKhQKEglnf5XG0JbLOxEEd4bvc9KGHQ",
                    "KBR National Park",
                    "Road 2, Banjara Hills, Hyderabad 500034",
                    17.4239,
                    78.4212,
                    4.5,
                    ["park", "tourist_attraction"],
                    user_ratings_total=17000,
                ),
                StopCategory.attraction,
                time(17, 10),
                time(18, 30),
                "Three-kilometer forest loop with actual peacocks; closes 7pm so the late-evening window is the calmer one. Avoid the Road 1 entrance — Road 2 has the shaded path.",
                travel_to_next_minutes=14,
            ),
            _stop(
                _place(
                    "ChIJk8izi1qXyzsRK50iW4oimEY",
                    "Cafe Niloufer",
                    "Lakdikapul, Hyderabad 500004",
                    17.4044,
                    78.4639,
                    4.3,
                    ["cafe", "bakery"],
                    user_ratings_total=7500,
                ),
                StopCategory.cafe,
                time(18, 44),
                time(19, 30),
                "Stand at the counter for Irani chai and Osmania biscuits — the seated section is for tourists, the standing one is for regulars.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000008"),
        title="Salar Jung Slow Looking",
        occasion=Occasion.solo,
        total_duration_minutes=290,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "An afternoon for one, in the city's deepest archive. Salar Jung holds the country's "
            "largest single-collector hoard — three rooms in, you stop trying to see everything "
            "and start picking favorites (mine: the veiled Rebecca, the Mughal daggers, the room "
            "of clocks at the top of the hour). Chowmahalla, twenty minutes by auto, is what the "
            "Nizams actually lived in — courtyards open to the sky, fewer crowds than you'd expect. "
            "End at Nimrah for the sugar pull-back: chai, biscuit, watch the bazaar."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJu9dj4oeXyzsRQaBpm0uTOzU",
                    "Salar Jung Museum",
                    "Salar Jung Marg, Darulshifa, Hyderabad 500002",
                    17.3713,
                    78.4801,
                    4.5,
                    ["museum", "tourist_attraction"],
                    user_ratings_total=50000,
                ),
                StopCategory.attraction,
                time(13, 0),
                time(15, 30),
                "Closed Fridays. The Eastern and Western blocks are the highlights — skip the founder's gallery if pressed for time. The veiled Rebecca and the musical clock are non-negotiable.",
                travel_to_next_minutes=9,
            ),
            _stop(
                _place(
                    "ChIJq6qq2oqXyzsR6Ovd2kXV2U0",
                    "Chowmahalla Palace",
                    "Khilwat, Motigalli, Hyderabad 500002",
                    17.3578,
                    78.4717,
                    4.5,
                    ["museum", "tourist_attraction"],
                    user_ratings_total=30000,
                ),
                StopCategory.attraction,
                time(15, 39),
                time(16, 45),
                "Closed Fridays. Smaller and quieter than Salar Jung; the durbar hall ceiling and the vintage car courtyard are the photographs nobody else's feed has.",
                travel_to_next_minutes=10,
                travel_mode=TravelMode.walking,
            ),
            _stop(
                _place(
                    "ChIJ1Z7b5_mXyzsR_6g6Az9fWjk",
                    "Nimrah Cafe & Bakery",
                    "Patthar Gatti, near Charminar, Hyderabad 500002",
                    17.3611,
                    78.4756,
                    4.3,
                    ["cafe", "bakery"],
                    user_ratings_total=25000,
                ),
                StopCategory.cafe,
                time(16, 55),
                time(17, 50),
                "Counter chai, fruit biscuit, and the bazaar at peak commute — solo seating is fine here, nobody minds.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000009"),
        title="Gachibowli Green Hours",
        occasion=Occasion.solo,
        total_duration_minutes=300,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "Hyderabad's tech triangle has more green than the brochures admit. Start at Kothaguda "
            "Botanical — actual forest cover, walking trails most office workers haven't found yet. "
            "Shilparamam afterward, where the rural artisan stalls feel like a slowed-down version "
            "of the metro: terracotta, ikat, dokra metalwork, no one upselling. Ironhill to close "
            "the loop — the kind of brewery that lets one person nurse a beer for an hour without "
            "making it weird."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJ-1FZALiTyzsR029wqV9TCNM",
                    "Hyderabad Botanical Garden",
                    "Kothaguda Reserve Forest, Kothaguda, Hyderabad 500084",
                    17.4631,
                    78.3661,
                    4.4,
                    ["park", "tourist_attraction"],
                    user_ratings_total=25000,
                ),
                StopCategory.attraction,
                time(15, 30),
                time(17, 0),
                "Closes 5pm; afternoon entry catches the peak butterfly hour at the bonsai pond. The bamboo loop trail is the quiet one — the rose garden is the crowded one.",
                travel_to_next_minutes=12,
            ),
            _stop(
                _place(
                    "ChIJnViW-duTyzsRATOZDbnTtdU",
                    "Shilparamam",
                    "Shilparamam Marg, Madhapur, Hyderabad 500081",
                    17.4519,
                    78.3812,
                    4.4,
                    ["tourist_attraction", "shopping_mall"],
                    user_ratings_total=75000,
                ),
                StopCategory.activity,
                time(17, 12),
                time(19, 0),
                "Crafts village, not a market — the artisan stalls actually make-on-site. Friday and Saturday evenings have live folk music in the amphitheatre, no extra ticket.",
                travel_to_next_minutes=8,
            ),
            _stop(
                _place(
                    "ChIJ7YEROh2RyzsRoYA7VKQrAXY",
                    "Ironhill India",
                    "VIP Hills, Silicon Valley, HITEC City, Hyderabad 500081",
                    17.4486,
                    78.3811,
                    4.5,
                    ["bar", "restaurant"],
                    user_ratings_total=9000,
                ),
                StopCategory.bar,
                time(19, 8),
                time(20, 30),
                "Solo-friendly: the bar counter has individual seating, the staff don't push group menus. House Hefeweizen + the cheese platter is the right one-person order.",
            ),
        ],
    ),

    # ── FAMILY ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-00000000000a"),
        title="Golconda Sunset, Tolichowki Dinner",
        occasion=Occasion.family,
        total_duration_minutes=360,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "Climb Golconda before the heat dies — kids will run ahead, the older folks will take "
            "the breaks they need on the stone benches. Bala Hisar at the top has the best skyline "
            "view in Hyderabad and the acoustics the queens supposedly used to hear court below. "
            "The Sound and Light show after dusk is theatrical in the way kids love and adults "
            "secretly enjoy too — Amitabh narrates the English version. Shah Ghouse for late dinner "
            "because it's open till 3am and serves haleem worth driving to Tolichowki for."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJj6mupo6WyzsRWjNa1t_sdms",
                    "Golconda Fort",
                    "Khair Complex, Ibrahim Bagh, Hyderabad 500008",
                    17.3833,
                    78.4011,
                    4.5,
                    ["tourist_attraction", "point_of_interest"],
                    user_ratings_total=100000,
                ),
                StopCategory.attraction,
                time(16, 0),
                time(18, 30),
                "Climb to Bala Hisar before sunset — the clap-stone at the entrance reaches the top, that's the one bit of hands-on history kids remember.",
                travel_to_next_minutes=15,
                travel_mode=TravelMode.walking,
            ),
            _stop(
                _place(
                    "ChIJNVsj-YuWyzsRtRwFMRQ7dNM",
                    "Golconda Sound & Light Show",
                    "Golconda Fort, Hyderabad 500008",
                    17.3829,
                    78.4006,
                    4.4,
                    ["tourist_attraction", "point_of_interest"],
                    user_ratings_total=12000,
                ),
                StopCategory.activity,
                time(18, 45),
                time(20, 0),
                "Wed–Sun only; English show on Wed, Sat, Sun. Buy tickets at the gate — the online site is unreliable. Sit centre, not the side benches.",
                travel_to_next_minutes=15,
            ),
            _stop(
                _place(
                    "ChIJNSA7fT-XyzsRrYhLnbu7KlQ",
                    "Shah Ghouse Cafe & Restaurant",
                    "Tolichowki, Hyderabad 500008",
                    17.3997,
                    78.4106,
                    4.3,
                    ["restaurant", "food"],
                    user_ratings_total=25000,
                ),
                StopCategory.restaurant,
                time(20, 15),
                time(22, 0),
                "Open till 3am, family hall on the first floor is the calmer section — the haleem at this branch is ground twice and the difference is real. Kid-friendly biryani portions on request.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-00000000000b"),
        title="Necklace Road Picnic",
        occasion=Occasion.family,
        total_duration_minutes=230,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "The walking-and-snacking version of a family outing. Lumbini Park has the speedboat "
            "to the Buddha statue mid-lake — kids will want to do it twice. The musical fountain "
            "at dusk is corny enough that everyone secretly likes it. Eat Street is one stretch of "
            "food stalls along the lake — let everyone pick their own dinner from a different "
            "counter. Karachi Bakery on the way home for fruit biscuits, because that's how "
            "Hyderabad family outings end."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJpeyxLF-XyzsRXBhk5vcfEmU",
                    "Lumbini Park",
                    "Tank Bund Road, Hussain Sagar, Hyderabad 500063",
                    17.4119,
                    78.4744,
                    4.3,
                    ["park", "tourist_attraction"],
                    user_ratings_total=100000,
                ),
                StopCategory.attraction,
                time(17, 0),
                time(18, 30),
                "Speedboat to the Buddha statue runs every twenty minutes — buy the combo ticket at the gate, not separately. The musical fountain show is at 7:15pm, plan accordingly.",
                travel_to_next_minutes=8,
                travel_mode=TravelMode.walking,
            ),
            _stop(
                _place(
                    "ChIJp1McUR2ayzsRVwo-Ww9MCak",
                    "Eat Street",
                    "Necklace Road, Khairatabad, Hyderabad 500004",
                    17.4203,
                    78.4737,
                    4.1,
                    ["restaurant", "food_court"],
                    user_ratings_total=25000,
                ),
                StopCategory.restaurant,
                time(18, 38),
                time(20, 0),
                "One open-air strip of stalls with shared seating along the lake — pick differently per person; the pani puri counter at the south end is the consistent one.",
                travel_to_next_minutes=12,
            ),
            _stop(
                _place(
                    "ChIJ47aqamGXyzsRGJq-YWhbiyk",
                    "Karachi Bakery — Mozamjahi Market",
                    "Mozamjahi Market, Mozzam Jahi Road, Hyderabad 500001",
                    17.3858,
                    78.4747,
                    4.4,
                    ["bakery", "cafe"],
                    user_ratings_total=30000,
                ),
                StopCategory.cafe,
                time(20, 12),
                time(20, 50),
                "The 1953 original — fruit biscuits and dil khush, not the dressed-up airport branches. Closes at 10pm; the take-home boxes survive a school lunch the next day.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-00000000000c"),
        title="HITEC Family Weekend",
        occasion=Occasion.family,
        total_duration_minutes=360,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "Hitec City does family weekends well because everything is climate-controlled and "
            "within a five-kilometer triangle. Smaaash inside Inorbit covers two hours easy — the "
            "bowling lanes are kid-friendly, the VR booths separate teenagers from parents. AB's "
            "for the buffet that earns its hype: skewers come to you, dessert is included, the "
            "kids never run out of things to try. Coffee Cup at the end for slow coffee and the "
            "kind of atmosphere that lets the older relatives wind down before the drive home."
        ),
        created_at=_CREATED_AT,
        stops=[
            _stop(
                _place(
                    "ChIJEUdt5i-XyzsRE1OhHGknLX8",
                    "Inorbit Mall Hyderabad",
                    "APIIC Software Layout, HITEC City, Madhapur, Hyderabad 500081",
                    17.4341,
                    78.3819,
                    4.4,
                    ["shopping_mall", "establishment"],
                    user_ratings_total=60000,
                ),
                StopCategory.activity,
                time(16, 0),
                time(18, 30),
                "Smaaash inside the mall handles 6–14 year-olds; the third-floor food court holds the fall-back if anyone gets hungry early. Less crawl-distance than Sarath City.",
                travel_to_next_minutes=10,
            ),
            _stop(
                _place(
                    "ChIJRRXO2kmRyzsRITDIrd8zHRk",
                    "AB's - Absolute Barbecues",
                    "Sarath City Capital Mall, HITEC City, Hyderabad 500081",
                    17.4584,
                    78.3672,
                    4.4,
                    ["restaurant", "food"],
                    user_ratings_total=8000,
                ),
                StopCategory.restaurant,
                time(18, 40),
                time(20, 45),
                "The HITEC branch is newer and quieter than Banjara — table grills mean nobody waits in buffet queues, kids choose their own skewers, dessert is included.",
                travel_to_next_minutes=8,
            ),
            _stop(
                _place(
                    "ChIJRSbJXL-RyzsRXGIJZMjF-Bs",
                    "Coffee Cup",
                    "Image Garden Road, Madhapur, Hyderabad 500081",
                    17.4498,
                    78.3893,
                    4.3,
                    ["cafe", "food"],
                    user_ratings_total=4000,
                ),
                StopCategory.cafe,
                time(20, 53),
                time(22, 0),
                "Late-evening cafe with comfortable family seating and an unrushed staff — the Belgian waffle and a pot of filter coffee land the older relatives in the right end-of-night mood.",
            ),
        ],
    ),
]


# ── Gurgaon (unchanged) ────────────────────────────────────────────────────────

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
