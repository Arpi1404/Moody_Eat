"""Hyderabad — eight hand-authored quests against real venues.

Three date, three friends, one solo, one family; no venue appears twice. Every
provider_id is a real Google Place ID, and the coordinates, ratings, review
counts and opening hours were read from each venue's Google listing in
November 2026 (re-check with `python -m scripts.verify_curated --city hyderabad`).
"""

import uuid
from datetime import time

from curated.builders import CREATED_AT, place, stop
from models import ClosedDay, CostEstimate, Occasion, Quest, StopCategory, StopRef, TravelMode

QUESTS: list[Quest] = [
    # ── DATE ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        title="Charminar to Chai: Old City Wander",
        audience_line="For two who'd rather wander the old city than book a table.",
        occasion=Occasion.date,
        total_duration_minutes=230,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "The old city after work, before the rush. Climb Charminar in the last hour before "
            "it closes, when the stone goes amber, then come down for Irani chai and Osmania "
            "biscuits at Nimrah, standing a few steps from the monument you have just climbed. "
            "Take your time walking up towards Madina, and finish with biryani at Shadab — the "
            "un-gentrified one, shared tables, and you'll understand why Hyderabadis argue about "
            "which place is best."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJm5MaboqXyzsR-xPxquRpWss",
                    "Charminar",
                    "Char Kaman, Ghansi Bazaar, Hyderabad 500002",
                    17.3616,
                    78.4747,
                    4.5,
                    ["monument", "tourist_attraction"],
                    user_ratings_total=276134,
                ),
                StopCategory.attraction,
                time(16, 30),
                time(17, 30),
                "Go up before the 5:30 close — from the first-floor gallery you look straight down the four roads the monument was built to anchor. An hour is plenty.",
                travel_to_next_minutes=3,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ1Z7b5_mXyzsR_6g6Az9fWjk",
                    "Nimrah Cafe & Bakery",
                    "Charminar Road, Ghansi Bazaar, Hyderabad 500002",
                    17.3611,
                    78.4742,
                    4.0,
                    ["bakery", "cafe"],
                    user_ratings_total=1712,
                ),
                StopCategory.cafe,
                time(17, 35),
                time(18, 25),
                "Stand at the counter for Irani chai and Osmania biscuits — the tables are the slower way to do it. You drink it looking straight at Charminar. Go easy on the biscuits; dinner is next.",
                travel_to_next_minutes=16,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJKyxGIoiXyzsRPY8PASGdTW0",
                    "Hotel Shadab",
                    "Madina Circle, High Court Road, Ghansi Bazaar, Hyderabad 500002",
                    17.3689,
                    78.4755,
                    4.0,
                    ["indian_restaurant", "restaurant"],
                    user_ratings_total=91246,
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 20),
                "The Old City's default answer for biryani — crowded, quick, and unbothered by trends. Order the mutton biryani and share it; portions are built for two.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000002"),
        title="Jubilee Hills, Slow Burn",
        audience_line="For a date night that doesn't try too hard.",
        occasion=Occasion.date,
        total_duration_minutes=220,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "The version of date night that doesn't try too hard. Start on the Durgam Cheruvu "
            "lakefront as the evening settles in and the cable bridge lights up across the water. "
            "Olive is a few minutes around the lake — whitewashed walls and a terrace over the "
            "water; order the wood-fired pizza and a glass of wine because that's what the place "
            "is for. Then Conçu, where the desserts are the reason you skipped tiramisu earlier."
        ),
        # The lakefront's first photo on Google is a board of walking-pass
        # prices; Olive's is its terrace.
        photo_stop=StopRef(stop_index=1),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJzaa0JS2RyzsR1O23hu3H7dU",
                    "Durgam Cheruvu Lake Front Park",
                    "Kavuri Hills, Madhapur, Hyderabad 500081",
                    17.4363,
                    78.3887,
                    4.3,
                    ["park", "tourist_attraction"],
                    user_ratings_total=11816,
                ),
                StopCategory.attraction,
                time(18, 0),
                time(18, 52),
                "The lakefront walkway faces the cable bridge head-on — walk it as the evening settles in and stay until the bridge is lit up across the water. Evening entry runs 4 to 8pm.",
                travel_to_next_minutes=8,
            ),
            stop(
                place(
                    "ChIJBdTHClGRyzsRjU5SWqXEeJk",
                    "Olive Bistro & Bar",
                    "Durgam Cheruvu, Road 46, Jubilee Hills, Hyderabad 500033",
                    17.4295,
                    78.3927,
                    4.3,
                    ["bistro", "italian_restaurant", "restaurant"],
                    user_ratings_total=9142,
                ),
                StopCategory.restaurant,
                time(19, 0),
                time(20, 40),
                "The terrace is the actual asset — ask for a table on the lake side when you book; the indoor room misses the view. Dinner service starts at 7.",
                travel_to_next_minutes=8,
            ),
            stop(
                place(
                    "ChIJZ3mAREiRyzsRIxCCJu8JwzU",
                    "Conçu Jubilee Hills",
                    "Road 37, Jubilee Hills, Hyderabad 500033",
                    17.4367,
                    78.3996,
                    4.5,
                    ["cafe", "bakery"],
                    user_ratings_total=8308,
                ),
                StopCategory.cafe,
                time(20, 48),
                time(21, 40),
                "The neighbourhood's most reliable patisserie counter — pick two desserts from the display and split them. Open till midnight, so there's no need to rush dinner.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000021"),
        title="White Marble to Noon Clock",
        audience_line="For a date that starts early and is done soon after noon.",
        occasion=Occasion.date,
        total_duration_minutes=255,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "A date that's done soon after noon. Start early at Birla Mandir, white marble on a hill, and "
            "look out over Hussain Sagar before the day heats up. Come down to Himayatnagar for dosas and "
            "coffee at Minerva, long enough to sit and talk. Then Salar Jung, which opens at ten: wander "
            "the galleries without trying to see them all, but be at the musical clock before noon, when "
            "a little figure comes out to strike the hour and the whole hall stops to watch."
        ),
        closed_days=[
            ClosedDay(day="friday", stop_index=2),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJBcAk0V2XyzsRjing1vqfQ1k",
                    "Birla Mandir",
                    "Naubat Pahad, Khairtabad, Hyderabad 500004",
                    17.4062,
                    78.4691,
                    4.7,
                    ["hindu_temple", "place_of_worship", "tourist_attraction"],
                    user_ratings_total=57837,
                ),
                StopCategory.attraction,
                time(8, 0),
                time(9, 0),
                "A white marble temple above the lake. Shoes come off at the entrance and phones go into the free lockers, so it is an hour of actually looking. Go early, before the stone warms up underfoot.",
                travel_to_next_minutes=15,
            ),
            stop(
                place(
                    "ChIJybdPGt2ZyzsRhnkXr9gvKcM",
                    "Minerva Coffee Shop",
                    "3-6-199/1, Himayatnagar, Hyderabad 500029",
                    17.4012,
                    78.4854,
                    4.2,
                    ["south_indian_restaurant", "vegetarian_restaurant", "coffee_shop"],
                    user_ratings_total=12050,
                ),
                StopCategory.restaurant,
                time(9, 15),
                time(10, 5),
                "A dependable South Indian vegetarian kitchen, open from seven. Share a dosa and a plate of idli with your coffee and take your time — the museum is a couple of hours on your feet.",
                travel_to_next_minutes=25,
            ),
            stop(
                place(
                    "ChIJu9dj4oeXyzsRQaBpm0uTOzU",
                    "Salar Jung Museum",
                    "Darulshifa, Hyderabad 500002",
                    17.3716,
                    78.4802,
                    4.4,
                    ["art_museum", "museum", "tourist_attraction"],
                    user_ratings_total=78577,
                ),
                StopCategory.attraction,
                time(10, 30),
                time(12, 15),
                "Find the Veiled Rebecca on the ground floor, then head for the musical clock well before noon, because the crowd gathers early. Leave bags at the cloakroom. Closed Fridays.",
            ),
        ],
    ),
    # ── FRIENDS ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000004"),
        title="HITEC City Game Night",
        audience_line="For the group that can never agree on what to do.",
        occasion=Occasion.friends,
        total_duration_minutes=270,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "For the group that says 'let's just hang' but never agrees on what. Smaaash takes "
            "care of the first hour and a half — bowling, arcade machines, VR; whoever loses pays "
            "for the first round. Am Aha is one floor down: Telugu food done properly, with a bar, "
            "which settles the where-do-we-eat argument before it starts. Finish a short walk from "
            "the mall at Akan, a brewpub with house beers and enough room that nobody has to stand."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJj9g7iFeRyzsRbTszJRXfmk8",
                    "Smaaash Hyderabad",
                    "Level 5, Inorbit Mall, HITEC City, Madhapur, Hyderabad 500081",
                    17.4346,
                    78.3871,
                    4.3,
                    ["amusement_center", "bowling_alley", "video_arcade"],
                    user_ratings_total=9408,
                ),
                StopCategory.activity,
                time(18, 0),
                time(19, 30),
                "Bowling, arcade and VR under one roof on the mall's top floor — it gives a mixed group something to do with their hands before anyone has to make conversation.",
                travel_to_next_minutes=4,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ9VO8kviRyzsRGOR_Ak74IA8",
                    "Am Aha Telugu Kitchen and Bar",
                    "4th Floor, Inorbit Mall, HITEC City, Madhapur, Hyderabad 500081",
                    17.4338,
                    78.3863,
                    4.7,
                    ["south_indian_restaurant", "indian_restaurant", "restaurant"],
                    user_ratings_total=4419,
                ),
                StopCategory.restaurant,
                time(19, 34),
                time(21, 10),
                "One of the highest-rated tables in the mall, and for once it's regional — Telugu staples built for sharing, plus a bar, so nobody has to compromise.",
                travel_to_next_minutes=6,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJAXLLciCRyzsROQZN8vHIprw",
                    "Akan Brewing Co",
                    "Opposite Durgam Cheruvu, Madhapur, Hyderabad 500081",
                    17.4335,
                    78.3879,
                    4.4,
                    ["brewpub", "bar"],
                    user_ratings_total=5266,
                ),
                StopCategory.bar,
                time(21, 16),
                time(22, 30),
                "A proper brewpub a couple of minutes from the mall doors, open till midnight and till 1am on Fridays and Saturdays — order a tasting flight for the table instead of arguing over pints.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000006"),
        title="Paradise, Promenade, Repeat",
        audience_line="For friends after the classics on a budget.",
        occasion=Occasion.friends,
        total_duration_minutes=220,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "The Hyderabad starter pack, on a budget. Paradise's Secunderabad flagship is the one "
            "— go early and you skip the worst of the queue. Order the biryani and come hungry. "
            "Then Lumbini Park for the walk you owe yourself after that quantity of rice, with the "
            "Buddha statue lit up out on the water and boats running to it. End at Mozamjahi "
            "Market, where Famous has been scooping hand-churned fruit ice cream under the clock "
            "tower for decades."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJG_3xjA-ayzsRFh3aJZ-Rbjg",
                    "Paradise Biryani — Secunderabad",
                    "Sarojini Devi Road, Secunderabad 500003",
                    17.4417,
                    78.4872,
                    4.0,
                    ["indian_restaurant", "restaurant"],
                    user_ratings_total=105558,
                ),
                StopCategory.restaurant,
                time(17, 45),
                time(19, 0),
                "The original — Paradise started here in 1953, and the newer branches across town are tidier but not the same. Order the mutton biryani, not the chicken.",
                travel_to_next_minutes=25,
            ),
            stop(
                place(
                    "ChIJpeyxLF-XyzsRXBhk5vcfEmU",
                    "Lumbini Park",
                    "Opposite Secretariat Road, Hussain Sagar, Hyderabad 500004",
                    17.4094,
                    78.4720,
                    4.1,
                    ["park", "tourist_attraction"],
                    user_ratings_total=78327,
                ),
                StopCategory.attraction,
                time(19, 30),
                time(20, 30),
                "The lakeside park closest to the Buddha statue — take the boat out if the queue is short, otherwise the promenade does the job. Closes at 9, so don't linger over the biryani.",
                travel_to_next_minutes=12,
            ),
            stop(
                place(
                    "ChIJ____P32XyzsRr9xZqE9F7RU",
                    "Famous Ice Cream",
                    "Mozamjahi Market, Abids, Hyderabad 500001",
                    17.3844,
                    78.4749,
                    4.1,
                    ["ice_cream_shop", "cafe"],
                    user_ratings_total=19258,
                ),
                StopCategory.cafe,
                time(20, 42),
                time(21, 25),
                "Hand-churned fruit flavours — sitaphal or mango when they're in season — eaten standing in the market courtyard. Open past midnight, and cheap enough that everyone gets two.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000022"),
        title="Locked In on Road 36",
        audience_line="For friends who'd rather crack a puzzle than sit at a bar.",
        occasion=Occasion.friends,
        total_duration_minutes=195,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A late start for friends who'd rather do something than sit over drinks. Begin at Mystery "
            "Rooms, where you get about an hour to work your way out of a locked room and everyone finds "
            "out who takes charge. Head along Road 36 to Chutneys for steamed dosas and the row of "
            "chutneys the place is named for, which gives you a table to argue about the last clue. Then "
            "Cream Stone, close by, for ice cream before it shuts at eleven."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJo4s60UmRyzsRKYZvlISkk3s",
                    "Mystery Rooms",
                    "SVM Mall, Road 36, Jubilee Hills, Hyderabad 500033",
                    17.4316,
                    78.4066,
                    4.7,
                    ["amusement_center"],
                    user_ratings_total=4588,
                ),
                StopCategory.activity,
                time(19, 15),
                time(20, 30),
                "Book your slot before you go, and pick a room the least patient person can live with. Games run about an hour; arrive a few minutes early for the briefing. Look for it on the third floor.",
                travel_to_next_minutes=7,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ_T_4fjaRyzsRzEy4bqcxFsM",
                    "Chutneys",
                    "Road 36, Jubilee Hills, Hyderabad 500033",
                    17.4296,
                    78.4096,
                    4.1,
                    ["south_indian_restaurant", "vegetarian_restaurant", "restaurant"],
                    user_ratings_total=14279,
                ),
                StopCategory.restaurant,
                time(20, 40),
                time(21, 40),
                "All vegetarian, and the steamed dosa is the thing to try. Order a few plates for the middle of the table and taste every chutney before anyone picks a favourite.",
                travel_to_next_minutes=5,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ91yvFUiRyzsRu0xxJudkYGI",
                    "Cream Stone",
                    "Sami Complex, Jubilee Hills, Hyderabad 500033",
                    17.4307,
                    78.4079,
                    4.3,
                    ["ice_cream_shop", "dessert_restaurant", "cafe"],
                    user_ratings_total=2641,
                ),
                StopCategory.cafe,
                time(21, 45),
                time(22, 30),
                "One each, or two to fight over. It closes at eleven, so don't let dinner run long, and finish the post-mortem on the way out.",
            ),
        ],
    ),
    # ── SOLO ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-000000000007"),
        title="Banjara Quiet Hours",
        audience_line="For time alone with good coffee, green paths and chai.",
        occasion=Occasion.solo,
        total_duration_minutes=230,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A solo route built around the small luxuries Hyderabad does well: good coffee, public "
            "greenery, neighbourhood chai. Roastery for an hour with a book — the garden tables are "
            "forgiving and nobody rushes you out. KBR is actual forest in the middle of the city; "
            "peacocks if you're lucky. Niloufer's tea is the unfussy reward — you stand at the "
            "counter, you don't sit, you watch the city do its evening commute."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJWUl-wiqXyzsRud1hDiZM0aM",
                    "Roastery Coffee House",
                    "Road 14, Banjara Hills, Hyderabad 500034",
                    17.4234,
                    78.4316,
                    4.4,
                    ["coffee_shop", "cafe"],
                    user_ratings_total=15499,
                ),
                StopCategory.cafe,
                time(15, 30),
                time(16, 30),
                "A converted bungalow with garden tables and coffee roasted in-house — the rare Banjara cafe where a single cup buys you an unhurried hour.",
                travel_to_next_minutes=8,
            ),
            stop(
                place(
                    "ChIJZe78QtKWyzsRA7_hetcQNG4",
                    "KBR National Park",
                    "Road 2, Jubilee Hills, Hyderabad 500034",
                    17.4204,
                    78.4203,
                    4.5,
                    ["national_park", "park", "tourist_attraction"],
                    user_ratings_total=20887,
                ),
                StopCategory.attraction,
                time(16, 38),
                time(18, 0),
                "A walking loop through real forest, peacocks included. Evening entry runs 4 to 6:30pm, so this is the one stop with a clock on it.",
                travel_to_next_minutes=35,
            ),
            stop(
                place(
                    "ChIJVy0-aGiXyzsRWMiIWZ1fC30",
                    "Cafe Niloufer",
                    "Red Hills Road, Lakdikapul, Hyderabad 500004",
                    17.4007,
                    78.4628,
                    4.4,
                    ["cafe", "bakery"],
                    user_ratings_total=25611,
                ),
                StopCategory.cafe,
                time(18, 35),
                time(19, 20),
                "Stand at the counter for Irani chai and Osmania biscuits — the standing crowd is the regulars. Open till 1am, so there's no hurry getting across town.",
            ),
        ],
    ),
    # ── FAMILY ──
    Quest(
        id=uuid.UUID("10000000-0000-4000-8000-00000000000a"),
        title="Golconda Afternoon, Tolichowki Dinner",
        audience_line="For families, from kids who run to grandparents who sit.",
        occasion=Occasion.family,
        total_duration_minutes=300,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "Two halves of the same dynasty in one afternoon. Start at the Qutb Shahi tombs, where "
            "the domes sit in gardens wide enough for kids to run and grandparents to find a "
            "bench. Then Golconda itself: clap under the entrance portico and the sound carries to "
            "the top of the hill — the one piece of history children remember. Climb while the "
            "light softens; the gates shut at five. Dinner is a short drive away in Tolichowki, at "
            "Pista House, with biryani sized for a hungry table."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJEadvQpeWyzsR9dHNyw6hS4A",
                    "Qutub Shahi Tombs",
                    "Qutub Shahi Tombs, Hyderabad 500104",
                    17.3955,
                    78.3968,
                    4.4,
                    ["monument", "tourist_attraction"],
                    user_ratings_total=22571,
                ),
                StopCategory.attraction,
                time(13, 45),
                time(15, 5),
                "The kings who built Golconda are buried here, a few minutes from the fort — quiet, shaded and mostly flat, which makes it the easy half of the day. It closes at 4:30, so it has to come first.",
                travel_to_next_minutes=8,
            ),
            stop(
                place(
                    "ChIJj6mupo6WyzsRWjNa1t_sdms",
                    "Golconda Fort",
                    "Khair Complex, Ibrahim Bagh, Hyderabad 500008",
                    17.3833,
                    78.4011,
                    4.5,
                    ["historical_landmark", "tourist_attraction"],
                    user_ratings_total=145113,
                ),
                StopCategory.attraction,
                time(15, 13),
                time(17, 0),
                "Climb to Bala Hisar for the best skyline view in the city. Allow ninety minutes at a family pace and start down by 4:45 — the fort closes at 5.",
                travel_to_next_minutes=13,
            ),
            stop(
                place(
                    "ChIJkb1NjRCXyzsR3qnUdAZWi-0",
                    "Pista House Tolichowki",
                    "Yousuf Tekri, Toli Chowki, Hyderabad 500008",
                    17.3968,
                    78.4242,
                    4.6,
                    ["indian_restaurant", "restaurant"],
                    user_ratings_total=25393,
                ),
                StopCategory.restaurant,
                time(17, 13),
                time(18, 45),
                "The name the city associates with haleem, with a full biryani-and-kebab menu the rest of the year. Big tables, fast service, and one of the best-rated dinners in Tolichowki.",
            ),
        ],
    ),
]
