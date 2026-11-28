"""Bangalore — eight hand-authored quests against real venues.

Three date, three friends, one solo, one family; no venue appears twice. Place
IDs, coordinates, ratings and review counts come from Google Places. A quest
that does not work every day of the week says so in `closed_days`. Checked by
scripts/verify_curated.py.
"""

import uuid
from datetime import time

from curated.builders import CREATED_AT, place, stop
from models import ClosedDay, CostEstimate, Occasion, Quest, StopCategory, StopRef, TravelMode

QUESTS: list[Quest] = [
    # ── DATE ──
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000001"),
        title="Lalbagh Light, Food Street Night",
        audience_line="For two who'd share vegetarian plates, stall to stall.",
        occasion=Occasion.date,
        total_duration_minutes=210,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "South Bangalore, the way the city did date night before the breweries arrived. Walk "
            "Lalbagh in the last hour of light — the Glass House loop, then up the rock for the "
            "view — and come out by the main gate to MTR, where the coffee arrives in a silver "
            "tumbler and the rava idli is the house invention. Split one dosa, not two, because "
            "the real eating is ten minutes away at VV Puram: a single all-vegetarian lane where "
            "you graze stall to stall and argue about who found the better holige."
        ),
        closed_days=[
            ClosedDay(day="monday", stop_index=1),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJHdPykcEVrjsRIr4v35kLEY4",
                    "Lalbagh Botanical Garden",
                    "Lalbagh Main Gate, Mavalli, Bengaluru 560004",
                    12.9494,
                    77.5847,
                    4.4,
                    ["botanical_garden", "garden", "tourist_attraction"],
                    user_ratings_total=179724,
                ),
                StopCategory.attraction,
                time(16, 45),
                time(18, 0),
                "Do the Glass House loop first, then climb the rock with the old watchtower for sunset — the one view in the city worth timing an evening around. Gates close at seven, so don't start late.",
                travel_to_next_minutes=10,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJaaWjpN0VrjsRAsmfiafDlN4",
                    "MTR (Mavalli Tiffin Rooms)",
                    "14 Lalbagh Road, Mavalli, Bengaluru 560027",
                    12.9552,
                    77.5856,
                    4.3,
                    ["vegetarian_restaurant", "south_indian_restaurant"],
                    user_ratings_total=40071,
                ),
                StopCategory.restaurant,
                time(18, 10),
                time(19, 0),
                "The original Mavalli Tiffin Rooms, not a mall branch — filter coffee in silver tumblers and the rava idli this kitchen is credited with inventing. Order light; you're eating again in twenty minutes.",
                travel_to_next_minutes=7,
            ),
            stop(
                place(
                    "ChIJH-raknwVrjsRoJppMsw-y2U",
                    "V. V. Puram Food Street",
                    "Sajjan Rao Circle, VV Puram, Bengaluru 560004",
                    12.9509,
                    77.5777,
                    4.2,
                    ["food_court", "restaurant"],
                    user_ratings_total=23669,
                ),
                StopCategory.restaurant,
                time(19, 7),
                time(20, 15),
                "A whole street of vegetarian stalls beats any single restaurant for a date — you share everything and nobody commits to a menu. Butter-soaked dosas, hot holige, and gulkand over ice cream to finish.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000002"),
        title="Church Street, One Book Each",
        audience_line="For bookish couples who want the whole evening on foot.",
        occasion=Occasion.date,
        total_duration_minutes=270,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "A date with a built-in conversation starter: give yourselves an hour in Blossom and "
            "one rule — each of you buys the other a book. Carry them five minutes up to MG Road "
            "for dinner at Lupa, Manu Chandra's big, grown-up European room, where the menu "
            "rewards ordering slowly and sharing everything. Then walk it off down to Lavelle Road "
            "for Bar Spirit Forward, a bar that takes its cocktails more seriously than its "
            "lighting. The whole evening is walkable end to end, so nobody has to open a cab app."
        ),
        closed_days=[
            ClosedDay(day="monday", stop_index=2),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJq6qa730WrjsRuZg7TTRYPow",
                    "Blossom Book House",
                    "Church Street, Ashok Nagar, Bengaluru 560001",
                    12.9743,
                    77.6069,
                    4.7,
                    ["book_store"],
                    user_ratings_total=17844,
                ),
                StopCategory.activity,
                time(18, 0),
                time(19, 5),
                "Floors of secondhand and new books stacked to the ceiling, priced so you can say yes to anything. Deeper than the other Church Street shops — an hour disappears here, and it's open late.",
                travel_to_next_minutes=6,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJwWzHW5cXrjsRSUYk6pvrsjU",
                    "Lupa",
                    "Spencer's Towers, 86 MG Road, Bengaluru 560001",
                    12.9757,
                    77.6046,
                    4.3,
                    ["european_restaurant", "restaurant"],
                    user_ratings_total=1609,
                ),
                StopCategory.restaurant,
                time(19, 11),
                time(21, 0),
                "The one room on MG Road that feels like an occasion without feeling stiff. Book ahead for a Saturday table, order to share, and take your time — dinner service starts at seven.",
                travel_to_next_minutes=10,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJk1UT0hoXrjsRnVPEieFPPfQ",
                    "Bar Spirit Forward",
                    "Hotel Southern Star, 40/2 Lavelle Road, Bengaluru 560001",
                    12.9746,
                    77.5993,
                    4.4,
                    ["bar"],
                    user_ratings_total=390,
                ),
                StopCategory.bar,
                time(21, 10),
                time(22, 30),
                "A cocktail bar first and everything else second — tell the bartender what you like and let them build around it. Quieter than the Church Street pubs, which is the point at this hour.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000011"),
        title="Modern Art, Then a Long Lunch",
        audience_line="For a daytime date with time to look, eat and linger.",
        occasion=Occasion.date,
        total_duration_minutes=255,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A daytime date with room to linger. Start at eleven at the National Gallery of Modern Art, a "
            "white mansion with sculpture standing in its garden — walk the galleries, then the lawn, and "
            "tell each other what you'd take home. Ride across town to The Only Place, an old-school "
            "steakhouse whose story goes back to 1965, for a lunch nobody needs to rush. Then stroll up "
            "to MG Road and finish at Lakeview Milk Bar, which has been serving ice cream since the "
            "1930s."
        ),
        closed_days=[
            ClosedDay(day="monday", stop_index=0),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJqZQybIEWrjsRezNLL4Ju2Gk",
                    "National Gallery of Modern Art",
                    "49 Palace Road, Vasanth Nagar, Bengaluru 560001",
                    12.9894,
                    77.5881,
                    4.4,
                    ["art_museum", "art_gallery", "tourist_attraction"],
                    user_ratings_total=2229,
                ),
                StopCategory.attraction,
                time(11, 0),
                time(12, 35),
                "Give the garden as much time as the galleries; the sculptures outside are worth it. Open by eleven from Tuesday to Sunday, and closed on Mondays.",
                travel_to_next_minutes=25,
            ),
            stop(
                place(
                    "ChIJhUwCoH4WrjsRXHFQjoJQxzQ",
                    "The Only Place",
                    "Museum Road, Ashok Nagar, Bengaluru 560025",
                    12.9716,
                    77.6127,
                    4.2,
                    ["steak_house", "american_restaurant", "restaurant"],
                    user_ratings_total=8883,
                ),
                StopCategory.restaurant,
                time(13, 0),
                time(14, 20),
                "Known for its steaks and apple pie, so order one big thing each and share the pie. Lunch stops a little after three and the doors don't reopen until seven.",
                travel_to_next_minutes=17,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJXxn4iXwWrjsR7mjtEslOP8I",
                    "Lakeview Milk Bar",
                    "89 MG Road, Bengaluru 560001",
                    12.9759,
                    77.6038,
                    4.1,
                    ["ice_cream_shop", "dessert_shop"],
                    user_ratings_total=12407,
                ),
                StopCategory.cafe,
                time(14, 40),
                time(15, 15),
                "Order one sundae and two spoons. It stays open late into the night, so there's no clock on the end of this one.",
            ),
        ],
    ),
    # ── FRIENDS ──
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000003"),
        title="Indiranagar: Tacos, Toit, Death by Chocolate",
        audience_line="For friends who want tacos, beer and dessert, in that order.",
        occasion=Occasion.friends,
        total_duration_minutes=240,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "The Indiranagar loop every Bangalore friend group ends up running eventually, in the "
            "right order. Start with tacos at Chinita while you can still hear each other, then "
            "walk five minutes to Toit — floors of house beer and the loudest good mood on 100 "
            "Feet Road. When the table starts negotiating one more pitcher, call it and head down "
            "to Corner House, because a Death by Chocolate split four ways is how nights here are "
            "supposed to end."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJGe0PTrsWrjsRwiOUSdxHiq0",
                    "Chinita Real Mexican Food",
                    "218 Paramahansa Yogananda Road (Double Road), Indiranagar, Bengaluru 560038",
                    12.9810,
                    77.6371,
                    4.3,
                    ["mexican_restaurant", "restaurant"],
                    user_ratings_total=4546,
                ),
                StopCategory.restaurant,
                time(18, 30),
                time(19, 45),
                "Tacos and burritos done properly, in a room small enough that the whole table stays in one conversation. Eat here first — Toit's kitchen is fine, but this is better, and you'll want a base.",
                travel_to_next_minutes=6,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJc0JAFaUWrjsRRXSXJPX7YFo",
                    "Toit",
                    "100 Feet Road, Indiranagar, Bengaluru 560038",
                    12.9795,
                    77.6407,
                    4.5,
                    ["brewpub", "pub"],
                    user_ratings_total=62972,
                ),
                StopCategory.bar,
                time(19, 51),
                time(21, 45),
                "The brewpub that made Bangalore a beer city. Get a sampler, then commit — the Tintin Toit wheat and the Basmati Blonde are the easy crowd-pleasers — and take whichever floor has a free table.",
                travel_to_next_minutes=7,
            ),
            stop(
                place(
                    "ChIJcUFZIqcXrjsRgmngcu1QQVk",
                    "Corner House",
                    "3283, 8th Cross Road, Indiranagar, Bengaluru 560008",
                    12.9701,
                    77.6374,
                    4.5,
                    ["ice_cream_shop", "dessert_shop"],
                    user_ratings_total=10058,
                ),
                StopCategory.cafe,
                time(21, 52),
                time(22, 30),
                "Bangalore's own ice cream parlour, and the Death by Chocolate is not a suggestion. Open late enough to be the last stop, and nobody has ever regretted it.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000004"),
        title="Koramangala: Burgers, Locked Rooms, Beer",
        audience_line="For the group that gets bored of just sitting.",
        occasion=Occasion.friends,
        total_duration_minutes=270,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A plan for the group that gets bored of just sitting. Get to Truffles early, before "
            "the queue becomes the evening, and eat burgers the size of a decision. Then drive "
            "across to Breakout and let them lock you in a room for an hour — you'll learn who "
            "panics, who hoards clues, and who was secretly useful all along. The Bier Library is "
            "a seven-minute walk from the exit, which is exactly how long it takes to finish "
            "arguing about the last puzzle."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJdz4L2VEUrjsRvSsPGCwDl2I",
                    "Truffles Koramangala",
                    "93/A, 4th B Cross Road, 5th Block, Koramangala, Bengaluru 560095",
                    12.9335,
                    77.6143,
                    4.5,
                    ["hamburger_restaurant", "cafe"],
                    user_ratings_total=51149,
                ),
                StopCategory.restaurant,
                time(18, 15),
                time(19, 30),
                "The burger Bangalore measures other burgers against, at prices that still make sense for a table of four. There's always a wait after seven; arriving at 6:15 is the whole trick.",
                travel_to_next_minutes=12,
            ),
            stop(
                place(
                    "ChIJO87U12kUrjsRNiANLOxsCdo",
                    "Breakout Escape Rooms, Koramangala",
                    "100 Feet Road (Intermediate Ring Road), Koramangala, Bengaluru 560047",
                    12.9384,
                    77.6306,
                    4.7,
                    ["amusement_center", "tourist_attraction"],
                    user_ratings_total=11748,
                ),
                StopCategory.activity,
                time(19, 42),
                time(21, 0),
                "Book a slot ahead and pick a room to match the group's patience. Games run about an hour and you actually have to talk to each other — a better use of a Saturday than a mall arcade.",
                travel_to_next_minutes=7,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJsaosImcVrjsRPP5rNvYTmLc",
                    "The Bier Library",
                    "14, 80 Feet Road, 6th Block, Koramangala, Bengaluru 560095",
                    12.9386,
                    77.6262,
                    4.4,
                    ["brewpub", "pub", "bar"],
                    user_ratings_total=23727,
                ),
                StopCategory.bar,
                time(21, 7),
                time(22, 45),
                "A big brewery with house beers on tap and enough room that a group usually finds a table. Order a round of the wheat and something fried, and let the post-mortem begin.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000012"),
        title="Malleshwaram: Dosa, Lake, Ice Cream",
        audience_line="For friends who'd rather walk and eat than settle into a bar.",
        occasion=Occasion.friends,
        total_duration_minutes=195,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "An evening for friends who'd rather walk and eat than settle into a bar. Be at CTR as the "
            "doors reopen at four, for a benne masala dosa from a kitchen that has been at it since the "
            "1920s. Then walk it off up to Sankey Tank and take the path by the water while the day "
            "cools, which is when the good conversations happen. Come back down Margosa Road to Naturals "
            "for ice cream, and argue over whose flavour won."
        ),
        photo_stop=StopRef(stop_index=1),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJ82NqvCUWrjsRC33A4yTYQWk",
                    "CTR (Central Tiffin Room)",
                    "7th Cross Road, Malleshwaram, Bengaluru 560003",
                    12.9982,
                    77.5695,
                    4.3,
                    ["south_indian_restaurant", "vegetarian_restaurant", "restaurant"],
                    user_ratings_total=37912,
                ),
                StopCategory.restaurant,
                time(16, 0),
                time(16, 50),
                "The benne masala dosa is the order: crisp, with butter doing the heavy lifting. The room is small and the queue is part of it, so arrive as it reopens at four.",
                travel_to_next_minutes=22,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJzVAUlTIWrjsRJgrhXgyf-Gs",
                    "Sankey Tank",
                    "Sankey Tank, Malleshwaram, Bengaluru 560080",
                    13.0093,
                    77.5741,
                    4.5,
                    ["lake", "park"],
                    user_ratings_total=4217,
                ),
                StopCategory.attraction,
                time(17, 15),
                time(18, 15),
                "Take the waterside path at an easy pace and find somewhere to stop where the view opens up. Get there while it's still light — that's when the lake earns the walk.",
                travel_to_next_minutes=15,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJmYCoOioWrjsR9NYCA-BbgPY",
                    "Naturals Ice Cream",
                    "Margosa Road, Malleshwaram, Bengaluru 560003",
                    13.0036,
                    77.5695,
                    4.5,
                    ["ice_cream_shop", "dessert_shop"],
                    user_ratings_total=2760,
                ),
                StopCategory.cafe,
                time(18, 35),
                time(19, 15),
                "A scoop each, plus one flavour for the table that nobody has tried. Start with the fruit ones. It's open till eleven, so nobody has to eat on the move.",
            ),
        ],
    ),
    # ── SOLO ──
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000005"),
        title="Cubbon Park, Then a Bookshop",
        audience_line="For an early riser who wants a morning to themselves.",
        occasion=Occasion.solo,
        total_duration_minutes=255,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "A morning for nobody but you. Cubbon Park before nine is the city at its best — "
            "bamboo groves, joggers, dogs, and the red library building glowing through the "
            "trees. Walk out towards Lavelle Road for a dosa and filter coffee under the banyan "
            "at Airlines Hotel, where no one will hurry you. Then take a short ride up to "
            "Champaca, the kind of bookshop that chooses its shelves carefully, and stay until "
            "you've read the first chapter of something."
        ),
        closed_days=[
            ClosedDay(day="monday", stop_index=0),
            ClosedDay(day="monday", stop_index=2),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJL2fQ53MWrjsRuN9D6aalLMY",
                    "Cubbon Park",
                    "Kasturba Road, Sampangi Rama Nagar, Bengaluru 560001",
                    12.9752,
                    77.5929,
                    4.4,
                    ["park"],
                    user_ratings_total=143335,
                ),
                StopCategory.attraction,
                time(7, 30),
                time(9, 0),
                "Go early, while the light is still slanting through the bamboo and the paths belong to walkers. No route needed — loop past the Central Library and sit wherever looks good.",
                travel_to_next_minutes=12,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ1Wpce3kWrjsRnJRhLAVNM4M",
                    "Airlines Hotel",
                    "4 SBI Road, off Lavelle Road, Bengaluru 560001",
                    12.9729,
                    77.5999,
                    4.0,
                    ["restaurant", "hotel"],
                    user_ratings_total=21431,
                ),
                StopCategory.restaurant,
                time(9, 12),
                time(10, 15),
                "Open-air tables under an old banyan, filter coffee in a steel tumbler, and a masala dosa that arrives fast. A table for one is the most normal thing in the world here, which is not true of the cafes nearby.",
                travel_to_next_minutes=10,
            ),
            stop(
                place(
                    "ChIJIYetAv0XrjsRxgT8FROZk_o",
                    "Champaca Bookstore",
                    "7/1 Edward Road, off Queens Road, Vasanth Nagar, Bengaluru 560001",
                    12.9872,
                    77.5960,
                    4.5,
                    ["book_store", "cafe"],
                    user_ratings_total=1848,
                ),
                StopCategory.activity,
                time(10, 25),
                time(11, 45),
                "An independent bookshop with a small cafe, picked over the Church Street giants because someone has clearly read what's on the shelves. Strong on Indian writing and translations; easy to lose an hour.",
            ),
        ],
    ),
    # ── FAMILY ──
    Quest(
        id=uuid.UUID("30000000-0000-4000-8000-000000000006"),
        title="Basavanagudi: Bull Temple to Butter Dosa",
        audience_line="For families up early who'd rather walk than drive.",
        occasion=Occasion.family,
        total_duration_minutes=165,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "Old Bangalore in one easy morning, and nobody has to get in a car between stops. "
            "Start at the Bull Temple, where the Nandi is carved from a single enormous boulder "
            "and the kids will want to walk all the way around it. Bugle Rock is next door — "
            "ancient rock, big trees, room to run — and it shuts at ten, so go before breakfast, "
            "not after. Then walk down to Gandhi Bazaar for the reason half the city crosses "
            "town: Vidyarthi Bhavan's thick, crisp masala dosa, delivered by waiters carrying a "
            "stack of plates up one arm."
        ),
        closed_days=[
            ClosedDay(day="friday", stop_index=2),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJX9XqWswVrjsRRH3ymQ8yCDQ",
                    "Bull Temple (Dodda Basavana Gudi)",
                    "Bull Temple Road, Basavanagudi, Bengaluru 560004",
                    12.9420,
                    77.5681,
                    4.7,
                    ["hindu_temple", "place_of_worship", "tourist_attraction"],
                    user_ratings_total=4668,
                ),
                StopCategory.attraction,
                time(7, 45),
                time(8, 25),
                "One of the largest Nandi statues anywhere, in a temple small enough that children don't get restless. The Dodda Ganapathi shrine is right beside it — do both in one visit.",
                travel_to_next_minutes=3,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJmwJpvowVrjsR0JVGQxxLHms",
                    "Bugle Rock Park",
                    "Bull Temple Road, Basavanagudi, Bengaluru 560004",
                    12.9427,
                    77.5694,
                    4.5,
                    ["park", "tourist_attraction"],
                    user_ratings_total=25967,
                ),
                StopCategory.attraction,
                time(8, 28),
                time(9, 15),
                "A park built around a massive rock outcrop — shaded paths, an old watchtower on top, and space for kids to burn energy before sitting still at breakfast. Morning hours end at 10am.",
                travel_to_next_minutes=6,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJNdCK6PIVrjsR3I4feeftf-0",
                    "Vidyarthi Bhavan",
                    "32 Gandhi Bazaar Main Road, Basavanagudi, Bengaluru 560004",
                    12.9450,
                    77.5714,
                    4.2,
                    ["south_indian_restaurant", "breakfast_restaurant", "vegetarian_restaurant"],
                    user_ratings_total=58997,
                ),
                StopCategory.restaurant,
                time(9, 21),
                time(10, 30),
                "The masala dosa here is thicker, crisper and more buttery than anywhere else in the city, and the room hasn't changed in decades. Expect a weekend wait that moves quickly; add a kesari bath. Closed Fridays.",
            ),
        ],
    ),
]
