"""Gurgaon — eight hand-authored quests against real venues.

Three date, three friends, one solo, one family; no venue appears twice. Place
names, addresses and coordinates are accurate, ratings and review counts
reflect each venue's Google Maps profile at the time of writing, and every
provider_id is a real Google Place ID (checked by scripts/verify_curated.py).

A quest that does not work every day of the week says so in `closed_days`.
"""

import uuid
from datetime import time

from curated.builders import CREATED_AT, place, stop
from models import ClosedDay, CostEstimate, Occasion, Quest, StopCategory, TravelMode

QUESTS: list[Quest] = [
    # ── DATE ──
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000011"),
        title="CyberHub, in the Right Order",
        audience_line="For a date that wants a plan, not a queue.",
        occasion=Occasion.date,
        total_duration_minutes=200,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "CyberHub is easy to do badly: wander in at eight, join a queue, settle for whichever "
            "chain has a table. Do it in this order instead. A drink first at Olly, because dinner "
            "is dry — Burma Burma is vegetarian and pours no alcohol, and it's still one of the "
            "best tables in the complex. Split the samosa soup, the tea leaf salad and a khow "
            "suey, then walk it off across the courtyard to The Big Chill's dessert counter for a "
            "slice of something you'll pretend to share."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJt7k-XjgZDTkRz4b0XF5ozDk",
                    "Olly",
                    "First Floor, DLF CyberHub, DLF Cyber City, Gurugram 122002",
                    28.4947,
                    77.0882,
                    4.3,
                    ["cafe", "italian_restaurant"],
                    user_ratings_total=1007,
                ),
                StopCategory.bar,
                time(18, 0),
                time(19, 5),
                "The Olive group's all-day cafe-bar, upstairs and a notch calmer than the ground-floor chains. Get the drink in now — the next stop doesn't pour.",
                travel_to_next_minutes=3,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJF6QrXDgZDTkRXOymqHJU35o",
                    "Burma Burma Restaurant & Tea Room",
                    "Ground Floor, DLF CyberHub, DLF Cyber City, Gurugram 122002",
                    28.4946,
                    77.0885,
                    4.6,
                    ["burmese_restaurant", "tea_house", "restaurant"],
                    user_ratings_total=3782,
                ),
                StopCategory.restaurant,
                time(19, 8),
                time(20, 40),
                "Nothing like the menus around it: samosa soup, tea leaf salad, khow suey, and a tea list worth reading. Dinner service starts at 6:30 and tables go fast, so book.",
                travel_to_next_minutes=3,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ_6-KOpwfDTkRd-BEi_zLNfM",
                    "The Big Chill Cakery & Creamery",
                    "Ground Floor, DLF CyberHub, DLF Cyber City, Gurugram 122002",
                    28.4949,
                    77.0885,
                    4.3,
                    ["bakery", "food_store"],
                    user_ratings_total=595,
                ),
                StopCategory.cafe,
                time(20, 43),
                time(21, 20),
                "Dessert only, which is the point — the blueberry cheesecake or the Mississippi mud pie, taken out into the courtyard while the amphitheatre crowd does its thing.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000012"),
        title="Golf Course Road, Dressed Up",
        audience_line="For the night you both agreed to make an effort.",
        occasion=Occasion.date,
        total_duration_minutes=240,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "The night you both agreed to make an effort. Start slow at Quill and Canvas in South "
            "Point Mall — a bookshop with an art gallery attached, and the quickest way to find "
            "out what the other person actually likes. Then cross Golf Course Road to Two Horizon "
            "Center for dinner at Comorin: regional Indian comfort food from the people behind "
            "Indian Accent, with a fraction of the ceremony. Whisky Samba is a few doors down for "
            "the nightcap, so the car stays parked until you leave."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJO4lOY9wYDTkR1eNa4RQG2E8",
                    "Quill and Canvas",
                    "South Point Mall, Golf Course Road, DLF Phase 5, Gurugram 122011",
                    28.4483,
                    77.0993,
                    4.9,
                    ["book_store", "art_gallery"],
                    user_ratings_total=269,
                ),
                StopCategory.activity,
                time(18, 15),
                time(19, 0),
                "Books and a gallery under one roof, open till 8:30 — half an hour of browsing tells you more about a person than an hour of small talk over a menu.",
                travel_to_next_minutes=7,
            ),
            stop(
                place(
                    "ChIJPdvhrs0ZDTkRJQws-tJOEKw",
                    "Comorin",
                    "First Floor, Two Horizon Center, Golf Course Road, DLF Phase 5, Gurugram 122009",
                    28.4513,
                    77.0967,
                    4.5,
                    ["indian_restaurant", "restaurant"],
                    user_ratings_total=3850,
                ),
                StopCategory.restaurant,
                time(19, 7),
                time(20, 50),
                "Order across the menu and share: the Champaran meat with sattu paratha, then the cheeni malai toast for dessert. The bar here is serious too, so don't save all your drinking for next door.",
                travel_to_next_minutes=2,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJbTc5i7UYDTkRSEKSd63it4U",
                    "Whisky Samba",
                    "Two Horizon Center, Golf Course Road, DLF Phase 5, Gurugram 122009",
                    28.4514,
                    77.0969,
                    4.3,
                    ["cocktail_bar", "bar_and_grill"],
                    user_ratings_total=4649,
                ),
                StopCategory.bar,
                time(20, 52),
                time(22, 15),
                "One of the longest whisky lists in the city and open till 2 AM. Tell the bartender what you usually drink and let them choose — it beats pretending to know the menu.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000023"),
        title="On Ice, Then Lunch",
        audience_line="For a daytime date that would rather wobble before it sits.",
        occasion=Occasion.date,
        total_duration_minutes=200,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "A daytime date that stays under one roof. Be at ISKATE, on the sixth floor of Ambience Mall, "
            "as it opens at noon, and get on the ice before lunch. Whoever finds their feet first does "
            "the steadying. Then head down to Punjab Grill for a long North Indian lunch with the dal "
            "makhani in the middle, and finish on the ground floor at PAUL, a French bakery, with "
            "something sweet and coffee while you argue over who fell more gracefully."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJbVcEG0wZDTkR1YJDC2d-Ijs",
                    "ISKATE by Roseate",
                    "6th Floor, Ambience Mall, NH 48, Gurugram 122010",
                    28.5033,
                    77.0975,
                    4.4,
                    ["ice_skating_rink"],
                    user_ratings_total=4501,
                ),
                StopCategory.activity,
                time(12, 0),
                time(13, 5),
                "An indoor rink, so the weather doesn't come into it. Skating is sold in time slots: book the first you can, and bring a warm layer, because a rink is a cold room. Hold the rail as long as you like.",
                travel_to_next_minutes=5,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJD-UYiE4ZDTkRxSzteYNsIk4",
                    "Punjab Grill",
                    "Level 3, Ambience Mall, NH 48, Gurugram 122010",
                    28.5031,
                    77.0975,
                    4.7,
                    ["north_indian_restaurant", "restaurant"],
                    user_ratings_total=9051,
                ),
                StopCategory.restaurant,
                time(13, 15),
                time(14, 35),
                "Order the dal makhani for the table, with garlic naan and a plate of kebabs to start, and share all of it. Your legs will be glad of the sit, so don't rush the second naan.",
                travel_to_next_minutes=8,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJDZn_h_sZDTkR1xJSxz18B7E",
                    "PAUL",
                    "Ground Floor, Ambience Mall, NH 48, Gurugram 122010",
                    28.5058,
                    77.0961,
                    4.1,
                    ["cafe", "bakery"],
                    user_ratings_total=3252,
                ),
                StopCategory.cafe,
                time(14, 45),
                time(15, 20),
                "A French bakery and cafe on the ground floor, on your way out. Choose one pastry each, swap halfway through, and decide who picked better.",
            ),
        ],
    ),
    # ── FRIENDS ──
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000013"),
        title="Sector 29, Two Breweries Deep",
        audience_line="For beer drinkers who want the whole night on foot.",
        occasion=Occasion.friends,
        total_duration_minutes=300,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "Sector 29 is Gurgaon's brewery strip, and the names on it change faster than anyone "
            "can keep up with — these two haven't needed to. Line your stomach first at Roots, "
            "the cafe in the park on the edge of Leisure Valley, because nobody makes good "
            "decisions on an empty one. Then Downtown for the first round of fresh beer and a "
            "proper dinner, and Open Tap a few doors along for the comparison round. The whole "
            "night is on foot, which matters by the third pint."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJ0WNzy-IYDTkRmSJmV7yXnPw",
                    "Roots - Cafe in the Park",
                    "Leisure Valley Road, near Rajiv Gandhi Park, Sector 29, Gurugram 122009",
                    28.4695,
                    77.0683,
                    4.3,
                    ["cafe", "breakfast_restaurant", "coffee_shop"],
                    user_ratings_total=6206,
                ),
                StopCategory.cafe,
                time(17, 30),
                time(18, 30),
                "Outdoor tables under the trees and a kitchen that shuts at nine. Chai and a plate of something here is the cheapest insurance you'll buy all night.",
                travel_to_next_minutes=8,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJ-yw62ZgZDTkRU2-mfRo2OGc",
                    "Downtown Diner & Fresh Beer Cafe",
                    "34, Leisure Valley Road, Sector 29, Gurugram 122009",
                    28.4681,
                    77.0630,
                    4.5,
                    ["brewery", "brewpub", "pub"],
                    user_ratings_total=10994,
                ),
                StopCategory.bar,
                time(18, 38),
                time(20, 30),
                "One of the best-rated breweries on the strip, and it has stayed that way while neighbours opened and closed. Get a sampler of the house beers for the table, pick a favourite, and eat dinner here rather than at the next stop.",
                travel_to_next_minutes=2,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJg8Bhyv0YDTkRhp9dG7jYfBo",
                    "Open Tap 29",
                    "38, Sector 29, Gurugram 122009",
                    28.4683,
                    77.0634,
                    4.4,
                    ["brewpub", "pub", "brewery"],
                    user_ratings_total=4550,
                ),
                StopCategory.bar,
                time(20, 32),
                time(22, 30),
                "Close enough to Downtown that the walk takes a minute, which is the point: order the same style you just had and argue about which brewery does it better. Open till 2 AM, so nobody has to watch the clock.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000014"),
        title="Speakeasy, Pizza, Piano",
        audience_line="For friends who want serious cocktails, then live music.",
        occasion=Occasion.friends,
        total_duration_minutes=285,
        total_cost_estimate=CostEstimate.splurge,
        narrative=(
            "A night with a plot. Start in the Sector 15 market at Cocktails and Dreams "
            "Speakeasy, Yangdup Lama's bar and still the one other Gurgaon bars get measured "
            "against — sit at the counter and let them make what they want to make. Walk ten "
            "minutes to 32nd Avenue, split pizzas at COMO, and be at The Piano Man next door "
            "before the band starts. It's the one room on the strip where people stop talking to "
            "listen."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJIbYc908YDTkRT6nYkAzAAzc",
                    "Cocktails and Dreams Speakeasy",
                    "SCO 23, Sector 15 Part 2 Market, Gurugram 122001",
                    28.4577,
                    77.0444,
                    4.5,
                    ["cocktail_bar", "tibetan_restaurant"],
                    user_ratings_total=2308,
                ),
                StopCategory.bar,
                time(18, 30),
                time(19, 40),
                "One of the city's oldest cocktail bars and still its most serious. Skip the menu, name a spirit and a mood, and order momos to go with whatever arrives.",
                travel_to_next_minutes=10,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJkTk5C-EZDTkR4xVMNDKDWaU",
                    "COMO Pizzeria & Cafe",
                    "32nd Avenue, Sector 15 Part 2, Gurugram 122001",
                    28.4617,
                    77.0497,
                    4.1,
                    ["pizza_restaurant", "restaurant"],
                    user_ratings_total=1957,
                ),
                StopCategory.restaurant,
                time(19, 50),
                time(21, 5),
                "Pizza is the right dinner between two bars: quick, shareable, and nobody has to negotiate a menu. It sits right beside The Piano Man, so you can linger until the last minute — order one more than you think you need.",
                travel_to_next_minutes=2,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJM_anaxQZDTkR9VXoQw3rakU",
                    "The Piano Man Gurugram",
                    "32nd Avenue, Sector 15 Part 2, Gurugram 122001",
                    28.4615,
                    77.0498,
                    4.4,
                    ["live_music_venue", "night_club"],
                    user_ratings_total=2922,
                ),
                StopCategory.bar,
                time(21, 7),
                time(23, 15),
                "The only room on 32nd Avenue built around a stage, with a crowd that actually listens. Check the night's line-up and set time before you go, and book a table — walk-ins end up at the bar.",
            ),
        ],
    ),
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000022"),
        title="Puzzle Room, Then Dosas",
        audience_line="For friends who'd rather argue over dosas than another round.",
        occasion=Occasion.friends,
        total_duration_minutes=240,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A friends plan that never needs a pitcher. Start at Mystery Rooms on Golf Course Road and "
            "spend an hour finding out who reads the clues and who just rattles the furniture. Then drive "
            "across to 32nd Avenue for dinner at Carnatic Cafe: South Indian, all vegetarian, and easy to "
            "order for a crowd. When the plates are cleared, step outside and walk the open-air lane, "
            "picking up something sweet on the way."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJT3qGkQgZDTkR-eyLhGnwK_Q",
                    "Mystery Rooms Golf Course Road",
                    "Golf Course Road, DLF Phase 1, Gurugram 122002",
                    28.4647,
                    77.0954,
                    4.7,
                    ["amusement_center"],
                    user_ratings_total=3018,
                ),
                StopCategory.activity,
                time(16, 30),
                time(17, 45),
                "Book ahead for a start around half past four. Games run about an hour, which leaves a few minutes to compare theories before the slow evening drive to dinner.",
                travel_to_next_minutes=30,
            ),
            stop(
                place(
                    "ChIJGZNNBuYZDTkRL5JX3k88-kE",
                    "Carnatic Cafe",
                    "32nd Avenue, Sector 15, Gurugram 122001",
                    28.4624,
                    77.0505,
                    4.3,
                    ["south_indian_restaurant", "vegetarian_restaurant", "cafe"],
                    user_ratings_total=5878,
                ),
                StopCategory.restaurant,
                time(18, 20),
                time(19, 35),
                "Order dosas and a few things to pass around, with filter coffee to finish. It fills up in the evening and there can be a wait, so don't linger on the way over.",
                travel_to_next_minutes=3,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJYxeFb08YDTkRDNXoZQqcpVU",
                    "32nd Avenue",
                    "NH 48, Sector 15, Gurugram 122001",
                    28.4617,
                    77.0501,
                    4.6,
                    ["tourist_attraction"],
                    user_ratings_total=28900,
                ),
                StopCategory.attraction,
                time(19, 40),
                time(20, 30),
                "An open-air street of cafes and shops that's free to wander. Pick up a dessert and do a slow lap — it stays open late, so the evening ends when the group does.",
            ),
        ],
    ),
    # ── SOLO ──
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000015"),
        title="Aravali Trails, Then Cameras",
        audience_line="For going alone: quiet trails, slow breakfast, old cameras.",
        occasion=Occasion.solo,
        total_duration_minutes=300,
        total_cost_estimate=CostEstimate.cheap,
        narrative=(
            "The Gurgaon most people drive past. Be at Aravali Biodiversity Park by half past "
            "seven — an old mining site replanted with the native forest that used to cover "
            "these hills, with trails long enough that the city noise actually drops out. Walk "
            "over to Fig on MG Road for coffee and a slow breakfast with whatever you're reading. "
            "Then Museo Camera when it opens at eleven: a museum of cameras and photography that "
            "rewards going alone, at your own pace, with nobody asking if you're done yet."
        ),
        closed_days=[
            ClosedDay(day="monday", stop_index=2),
        ],
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJ8beaD9YfDTkRLQF3QzM6QyY",
                    "Aravali Biodiversity Park",
                    "Acharya Shree Tulsi Marg, DLF Phase 3, Gurugram 122002",
                    28.4818,
                    77.1116,
                    4.6,
                    ["park", "nature_preserve"],
                    user_ratings_total=2944,
                ),
                StopCategory.attraction,
                time(7, 30),
                time(9, 0),
                "The morning session runs six to eleven, and early is when the birds are out and the trails are empty. Carry water and wear real shoes — these are trails, not a jogging track.",
                travel_to_next_minutes=10,
                travel_mode=TravelMode.walking,
            ),
            stop(
                place(
                    "ChIJjZ5VkrsZDTkR0Y3IHIU8yAE",
                    "Fig at MG",
                    "Global Gateway Towers, MG Road, Sikanderpur, Gurugram 122002",
                    28.4815,
                    77.1043,
                    4.4,
                    ["cafe"],
                    user_ratings_total=1049,
                ),
                StopCategory.cafe,
                time(9, 10),
                time(10, 47),
                "Open from 7:30 and the closest good coffee to the park. Nobody hurries a single table with a book, and after ninety minutes on the trails you've earned a proper breakfast.",
                travel_to_next_minutes=13,
            ),
            stop(
                place(
                    "ChIJEy4Nq-IZDTkR-S0-YZmI7jU",
                    "Museo Camera",
                    "Shri Ganesh Mandir Marg, DLF Phase 4, Gurugram 122009",
                    28.4697,
                    77.0804,
                    4.7,
                    ["museum"],
                    user_ratings_total=1872,
                ),
                StopCategory.attraction,
                time(11, 0),
                time(12, 30),
                "A not-for-profit museum built around a huge collection of vintage cameras, with changing photography exhibitions alongside. Opens at eleven, closed Mondays — an hour and a half alone here goes quickly.",
            ),
        ],
    ),
    # ── FAMILY ──
    Quest(
        id=uuid.UUID("20000000-0000-4000-8000-000000000016"),
        title="Sohna Road: Jump, Bowl, Pizza",
        audience_line="For families with kids who need to bounce before they sit.",
        occasion=Occasion.family,
        total_duration_minutes=270,
        total_cost_estimate=CostEstimate.mid,
        narrative=(
            "A family evening that keeps moving, so nobody ends up bored in a food court. Start at "
            "SkyJumper on Sohna Road, where more than a hundred trampolines take the edge off the "
            "kids before anyone asks them to sit still. A short drive south, Airia Mall settles "
            "the family rivalry over a game of bowling at Smaaash — the one sport grandparents and "
            "eight-year-olds lose at equally. Then across to Joy Street for pizza at Tossin, and "
            "one last stop at Dach & Nona, because an evening like this is supposed to end with "
            "ice cream."
        ),
        created_at=CREATED_AT,
        stops=[
            stop(
                place(
                    "ChIJrWQPWEXnDDkR9Qs0C1tJd_4",
                    "SkyJumper Trampoline Park",
                    "Ground Floor, ILD Trade Centre, Sohna Road, Sector 47, Gurugram 122018",
                    28.4251,
                    77.0391,
                    4.8,
                    ["amusement_park", "amusement_center"],
                    user_ratings_total=55065,
                ),
                StopCategory.activity,
                time(15, 30),
                time(16, 45),
                "The big one on Sohna Road — wall-to-wall trampolines and enough side activities that an hour disappears. Going here first means the kids burn their energy before dinner, not during it.",
                travel_to_next_minutes=15,
            ),
            stop(
                place(
                    "ChIJN_co5HMjDTkRp6zmZGWOKCg",
                    "Smaaash Airia Mall",
                    "2nd Floor, Airia Mall, Sohna Road, Sector 68, Gurugram 122101",
                    28.3825,
                    77.0528,
                    4.6,
                    ["bowling_alley", "sports_complex"],
                    user_ratings_total=4634,
                ),
                StopCategory.activity,
                time(17, 0),
                time(18, 0),
                "Bowling is the rare activity the whole family can play together, including whoever sat out the trampolines. One game is enough — the arcade machines are there if someone wants a rematch.",
                travel_to_next_minutes=7,
            ),
            stop(
                place(
                    "ChIJ86Qv_wkjDTkRxLAEP8grZl0",
                    "Tossin Pizza",
                    "Ground Floor, AIPL Joy Street, Sector 66, Gurugram 122101",
                    28.3922,
                    77.0591,
                    4.6,
                    ["pizza_restaurant", "restaurant"],
                    user_ratings_total=617,
                ),
                StopCategory.restaurant,
                time(18, 7),
                time(19, 20),
                "Pizza is the dinner nobody at the table argues with, and after two activities nobody wants a long menu. Order for sharing and get one more than seems sensible.",
                travel_to_next_minutes=5,
            ),
            stop(
                place(
                    "ChIJqVkfl3IjDTkRwxZ8KoHXRZ0",
                    "Dach & Nona, The Ice Cream Factory",
                    "Ramgarh Road, opposite M3M Urbana Premium, Gurugram 122101",
                    28.3912,
                    77.0677,
                    4.8,
                    ["ice_cream_shop", "dessert_shop"],
                    user_ratings_total=460,
                ),
                StopCategory.cafe,
                time(19, 25),
                time(20, 0),
                "A proper ice-cream shop a few minutes from Joy Street, not a mall kiosk, and open till midnight. Let everyone choose their own and call it a night.",
            ),
        ],
    ),
]
