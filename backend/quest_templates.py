"""
What goes into a quest, and in what order.

Three layers, each built from the one before:

  TypeFamily    – which places belong in a kind of stop, judged by the one type
                  Google says a place mainly is (its primary type).
  TemplateStop  – one kind of stop: what to search for and which family the
                  result should belong to.
  DayPlan       – the stops of an outing in the order they happen, for one
                  occasion at one time of day.

All values in places_types must be in ALLOWED_NEARBY_TYPES (models.py).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from models import DayPart, Occasion, StopCategory


# ── Type families ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TypeFamily:
    """The primary types that belong in a kind of stop.

    A search for `bar` returns every place *tagged* bar, and a pizzeria that
    serves beer is tagged bar. Its primary type is still `pizza_restaurant`,
    which is what this checks.
    """

    primary: frozenset[str]
    # Also accept any primary type with this ending. Restaurants come in about
    # 150 cuisine types and Google keeps adding more.
    suffix: str | None = None
    # Never accepted, even when the suffix matches.
    excluded: frozenset[str] = frozenset()
    # Primary types that count only when the place also carries one of
    # `counter_tags`: a bakery or cake shop is somewhere to sit down only if
    # Google also calls it a cafe. Otherwise it is a counter, or a shop that
    # takes cake orders.
    counter: frozenset[str] = frozenset()
    counter_tags: frozenset[str] = frozenset()

    def accepts(self, primary_type: str | None, types: Iterable[str] | None) -> bool:
        """True when a place belongs. A place with no primary type has only
        its tags to go by, and it was found by one of them, so it is accepted."""
        if not primary_type:
            return True
        primary = primary_type.casefold()
        if primary in self.excluded:
            return False
        if primary in self.primary:
            return True
        if self.suffix and primary.endswith(self.suffix):
            return True
        if primary in self.counter:
            return bool(self.counter_tags & {t.casefold() for t in (types or [])})
        return False


# Somewhere to sit down over a coffee.
_CAFE_TYPES = frozenset({
    "cafe", "coffee_shop", "coffee_roastery", "tea_house", "cat_cafe",
    "dog_cafe", "pastry_shop",
})
# Somewhere to have something sweet.
_SWEET_TYPES = frozenset({
    "dessert_shop", "dessert_restaurant", "ice_cream_shop", "chocolate_shop",
    "donut_shop", "juice_shop", "acai_shop",
})
# Sells baked or sweet things over a counter, with or without anywhere to sit.
_COUNTER_TYPES = frozenset({"bakery", "cake_shop", "confectionery", "candy_store"})

_OUTDOORS = frozenset({
    "park", "city_park", "national_park", "state_park", "garden",
    "botanical_garden", "lake", "river", "beach", "woods", "nature_preserve",
    "hiking_area", "scenic_spot", "picnic_ground", "plaza", "marina",
    "wildlife_park", "wildlife_refuge", "observation_deck", "bridge",
    "fountain", "zoo",
})
_CULTURE = frozenset({
    "tourist_attraction", "museum", "art_museum", "history_museum",
    "art_gallery", "cultural_center", "cultural_landmark", "historical_place",
    "historical_landmark", "monument", "sculpture", "castle", "planetarium",
    "aquarium", "performing_arts_theater", "amphitheatre", "visitor_center",
})
# A temple or church that Google tags as an attraction counts as a sight.
# The generator's mood rule keeps them out of date and friends evenings.
_WORSHIP = frozenset({
    "hindu_temple", "buddhist_temple", "church", "mosque", "synagogue",
    "shinto_shrine",
})
_PLAY = frozenset({
    "bowling_alley", "amusement_center", "video_arcade", "go_karting_venue",
    "miniature_golf_course", "paintball_center", "adventure_sports_center",
    "ice_skating_rink", "karaoke", "comedy_club", "amusement_park",
    "water_park", "roller_coaster", "ferris_wheel", "skateboard_park",
    "cycling_park", "off_roading_area", "sports_activity_location",
    "sports_complex",
})

# A sit-down meal. Fast food is a meal, but not a sit-down one; a bar, a cafe
# or a food court tagged `restaurant` is none of these.
_MEAL_PRIMARY = frozenset({"restaurant", "steak_house", "bistro", "diner", "gastropub"})
_NOT_A_MEAL = frozenset({"fast_food_restaurant", "dessert_restaurant"})
MEAL_FAMILY = TypeFamily(
    primary=_MEAL_PRIMARY,
    suffix="_restaurant",
    excluded=_NOT_A_MEAL,
)
# Dinner: the same, minus the places that are mainly about breakfast.
DINNER_FAMILY = TypeFamily(
    primary=_MEAL_PRIMARY,
    suffix="_restaurant",
    excluded=_NOT_A_MEAL | frozenset({"breakfast_restaurant", "brunch_restaurant"}),
)
CAFE_FAMILY = TypeFamily(
    primary=_CAFE_TYPES,
    counter=frozenset({"bakery", "cake_shop"}),
    counter_tags=frozenset({"cafe", "coffee_shop", "tea_house"}),
)
DESSERT_FAMILY = TypeFamily(
    primary=_CAFE_TYPES | _SWEET_TYPES,
    counter=frozenset({"bakery", "cake_shop"}),
    counter_tags=frozenset({
        "cafe", "coffee_shop", "tea_house", "dessert_restaurant", "ice_cream_shop",
    }),
)
# A treat on a family outing: any bakery will do, and so will a mall.
TREAT_FAMILY = TypeFamily(
    primary=_CAFE_TYPES | _SWEET_TYPES | _COUNTER_TYPES | frozenset({"shopping_mall"}),
)
_BAR_TYPES = frozenset({
    "bar", "pub", "wine_bar", "cocktail_bar", "lounge_bar", "irish_pub",
    "beer_garden", "brewery", "brewpub", "gastropub", "bar_and_grill", "winery",
})
DRINKS_FAMILY = TypeFamily(
    primary=_BAR_TYPES | frozenset({
        "night_club", "sports_bar", "hookah_bar", "karaoke", "live_music_venue",
    }),
)
NIGHTCAP_FAMILY = TypeFamily(primary=_BAR_TYPES)
SIGHT_FAMILY = TypeFamily(primary=_OUTDOORS | _CULTURE | _WORSHIP)
QUIET_FAMILY = TypeFamily(
    primary=_OUTDOORS | _CULTURE | _WORSHIP | frozenset({"library", "book_store"}),
)
PLAY_FAMILY = TypeFamily(
    primary=_PLAY | _OUTDOORS | _CULTURE | _WORSHIP | frozenset({
        "movie_theater", "shopping_mall",
    }),
)
# Indoors and open late: what is still open after dinner. No parks, sights or
# malls, which are shut or shutting by then.
_LATE_PLAY = frozenset({
    "bowling_alley", "amusement_center", "video_arcade", "karaoke",
    "comedy_club", "ice_skating_rink", "movie_theater",
})
NIGHT_PLAY_FAMILY = TypeFamily(primary=_LATE_PLAY)
FILM_FAMILY = TypeFamily(primary=frozenset({"movie_theater"}))
FAMILY_FUN_FAMILY = TypeFamily(
    primary=_PLAY | _OUTDOORS | _CULTURE | _WORSHIP | frozenset({
        "playground", "indoor_playground", "shopping_mall",
    }),
)


# ── Kinds of stop ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TemplateStop:
    # Our internal StopCategory label (drives dwell time).
    category: StopCategory
    # Ordered fallback list of Google Places `type` values to search.
    # The first that yields a place wins; later entries broaden the search.
    places_types: tuple[str, ...]
    # What the stop is for in the plan.
    role: str
    # Places are preferred when their primary type belongs here. When nothing
    # in the whole fallback list does, any place carrying the tag is taken.
    family: TypeFamily
    # Places whose name matches are passed over in the same way: for what the
    # primary type cannot tell (Google files a children's park under `park`).
    avoid_names: re.Pattern[str] | None = None

    def suits(self, name: str, primary_type: str | None, types: Iterable[str] | None) -> bool:
        """True when a place is the kind this stop is for."""
        if self.avoid_names is not None and self.avoid_names.search(name):
            return False
        return self.family.accepts(primary_type, types)


# A park or play area for small children is a fine family stop and an odd one
# for a date, a night out with friends or a day alone.
_FOR_CHILDREN_RE = re.compile(
    r"\bchildren'?s?\b|\bkids?\b|\bplay\s?(?:ground|area|zone|park)\b",
    re.IGNORECASE,
)


MEAL = TemplateStop(
    category=StopCategory.restaurant,
    # No "meal_takeaway" here: the quality filter deny-lists that type, so
    # searching it spent three paid calls per quest to return nothing.
    places_types=("restaurant", "cafe"),
    role="meal",
    family=MEAL_FAMILY,
)
DINNER = TemplateStop(
    category=StopCategory.restaurant,
    places_types=("restaurant", "cafe"),
    role="meal",
    family=DINNER_FAMILY,
)
CAFE = TemplateStop(
    category=StopCategory.cafe,
    places_types=("cafe", "bakery"),
    role="coffee",
    family=CAFE_FAMILY,
)
# A dessert stop is a bakery, a dessert shop or a cafe, so it reads as a café
# on the site, the label the site gives a bakery anyway. ("other" showed as
# "Spot".)
DESSERT = TemplateStop(
    category=StopCategory.cafe,
    places_types=("bakery", "cafe"),
    role="dessert",
    family=DESSERT_FAMILY,
)
TREAT = TemplateStop(
    category=StopCategory.cafe,
    places_types=("bakery", "cafe", "shopping_mall"),
    role="dessert",
    family=TREAT_FAMILY,
)
DRINKS = TemplateStop(
    category=StopCategory.bar,
    places_types=("bar", "night_club", "restaurant"),
    role="drinks",
    family=DRINKS_FAMILY,
)
# The bar on a date: somewhere to talk, so no clubs.
NIGHTCAP = TemplateStop(
    category=StopCategory.bar,
    places_types=("bar",),
    role="drinks",
    family=NIGHTCAP_FAMILY,
)
# Outdoors when there is any; a sight or a gallery when there is not.
STROLL = TemplateStop(
    category=StopCategory.attraction,
    places_types=("park", "tourist_attraction", "art_gallery", "museum"),
    role="walk",
    family=SIGHT_FAMILY,
    avoid_names=_FOR_CHILDREN_RE,
)
SIGHT = TemplateStop(
    category=StopCategory.attraction,
    places_types=("tourist_attraction", "park", "art_gallery", "museum"),
    role="sight",
    family=SIGHT_FAMILY,
    avoid_names=_FOR_CHILDREN_RE,
)
SOLO_SIGHT = TemplateStop(
    category=StopCategory.attraction,
    places_types=("tourist_attraction", "museum", "park"),
    role="sight",
    family=SIGHT_FAMILY,
    avoid_names=_FOR_CHILDREN_RE,
)
QUIET = TemplateStop(
    category=StopCategory.other,
    # Order matters: try the high-signal categories first (galleries, parks,
    # libraries) and fall through to book_store last. Google's `book_store`
    # type is noisy in India (stationery shops self-tag as bookstores).
    places_types=("art_gallery", "park", "library", "book_store"),
    role="quiet",
    family=QUIET_FAMILY,
    avoid_names=_FOR_CHILDREN_RE,
)
PLAY = TemplateStop(
    category=StopCategory.activity,
    places_types=(
        "bowling_alley",
        "movie_theater",
        "amusement_park",
        "shopping_mall",
        "tourist_attraction",
    ),
    role="activity",
    family=PLAY_FAMILY,
    avoid_names=_FOR_CHILDREN_RE,
)
# Something to do after dinner: bowling or an arcade first, a late film when
# there is neither.
NIGHT_PLAY = TemplateStop(
    category=StopCategory.activity,
    places_types=("bowling_alley", "movie_theater"),
    role="activity",
    family=NIGHT_PLAY_FAMILY,
    avoid_names=_FOR_CHILDREN_RE,
)
# The same for a family: a play area for children is the point here.
FAMILY_NIGHT_PLAY = TemplateStop(
    category=StopCategory.activity,
    places_types=("bowling_alley", "movie_theater"),
    role="activity",
    family=NIGHT_PLAY_FAMILY,
)
# A night out alone: a film.
LATE_SHOW = TemplateStop(
    category=StopCategory.activity,
    places_types=("movie_theater",),
    role="activity",
    family=FILM_FAMILY,
)
FAMILY_FUN = TemplateStop(
    category=StopCategory.activity,
    places_types=(
        "park",
        "zoo",
        "aquarium",
        "amusement_park",
        "museum",
        "tourist_attraction",
    ),
    role="activity",
    family=FAMILY_FUN_FAMILY,
)
FAMILY_MORE = TemplateStop(
    category=StopCategory.activity,
    places_types=("park", "museum", "tourist_attraction", "shopping_mall"),
    role="activity",
    family=FAMILY_FUN_FAMILY,
)

# What a dessert stop's place mainly is, when it is not a cafe. Used to tell a
# dessert stop from a coffee stop once both read as a café.
SWEET_PRIMARY_TYPES = _SWEET_TYPES | _COUNTER_TYPES

# Roles that involve eating or drinking. A plan has at most one "meal", and
# the only food after it is dessert or drinks.
FOOD_ROLES = frozenset({"meal", "coffee", "dessert", "drinks"})
AFTER_MEAL_FOOD_ROLES = frozenset({"dessert", "drinks"})


# ── Plans ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DayPlan:
    """The stops of an outing at one time of day.

    `sequence` is the order they happen in when all four are asked for.
    `keep` says which survive as the outing gets shorter: a plan of n stops is
    the first n of `keep`, visited in `sequence` order.
    `short` replaces that for the stop counts it names, when a short outing is
    a different shape rather than a cut-down long one: an evening date of one
    stop is dinner, while three stops are a walk, a coffee, then dinner. Each
    entry is (stops in order, spares in order).
    """

    sequence: tuple[TemplateStop, ...]
    keep: tuple[TemplateStop, ...]
    short: dict[int, tuple[tuple[TemplateStop, ...], tuple[TemplateStop, ...]]] = field(
        default_factory=dict
    )

    def stops(self, count: int) -> tuple[TemplateStop, ...]:
        if count in self.short:
            return self.short[count][0]
        chosen = self.keep[:count]
        return tuple(stop for stop in self.sequence if stop in chosen)

    def spares(self, count: int) -> tuple[TemplateStop, ...]:
        """What to try, in order, when a planned stop cannot be filled."""
        if count in self.short:
            return self.short[count][1]
        return self.keep[count:]


def _plan(
    *sequence: TemplateStop,
    keep: tuple[TemplateStop, ...] | None = None,
    short: dict[int, tuple[tuple[TemplateStop, ...], tuple[TemplateStop, ...]]] | None = None,
) -> DayPlan:
    return DayPlan(
        sequence=sequence,
        keep=keep if keep is not None else sequence,
        short=short or {},
    )


# Ordered by the clock, not by the occasion:
#   morning    a walk first, then breakfast or coffee
#   afternoon  lunch first
#   evening    something to do, a walk or a coffee first; dinner once it is
#              dinner time (the generator holds it to about 7pm). A one- or
#              two-stop date, and a one-stop family outing, are dinner-led
#              instead and start at 7pm (the owner's call, 27 Nov 2026).
#   night      dinner first, then dessert or drinks. Nothing that keeps
#              daylight hours: no parks, sights, galleries, museums or
#              libraries after dinner, only places open late (bars, dessert,
#              cafes, bowling, a film). A family night is three stops at most.
#
# The rule behind every shape: a stop kind is only scheduled at an hour when
# the places it searches for are usually open. Parks, sights and galleries
# keep to the day and early evening (start by about 18:00), restaurants serve
# from late morning, and after 20:00 only food, drink and late indoor play
# remain. tests/test_plan_hours.py checks every shape against that.
PLANS: dict[Occasion, dict[DayPart, DayPlan]] = {
    Occasion.date: {
        DayPart.morning: _plan(
            STROLL, CAFE, SIGHT, MEAL,
            keep=(CAFE, STROLL, SIGHT, MEAL),
        ),
        DayPart.afternoon: _plan(MEAL, DESSERT, SIGHT, STROLL),
        DayPart.evening: _plan(
            STROLL, CAFE, DINNER, DESSERT,
            keep=(CAFE, STROLL, DINNER, DESSERT),
            short={
                1: ((DINNER,), (STROLL,)),
                2: ((DINNER, DESSERT), (STROLL,)),
            },
        ),
        DayPart.night: _plan(
            DINNER, DESSERT, NIGHT_PLAY, NIGHTCAP,
            keep=(DINNER, DESSERT, NIGHTCAP, NIGHT_PLAY),
        ),
    },
    Occasion.friends: {
        DayPart.morning: _plan(
            STROLL, CAFE, PLAY, MEAL,
            keep=(CAFE, STROLL, PLAY, MEAL),
        ),
        DayPart.afternoon: _plan(
            MEAL, PLAY, DESSERT, DRINKS,
            keep=(MEAL, PLAY, DRINKS, DESSERT),
        ),
        DayPart.evening: _plan(
            PLAY, DINNER, DESSERT, DRINKS,
            keep=(DRINKS, PLAY, DINNER, DESSERT),
            # Two stops in the evening: something to do, then dinner at 19:00.
            # Activity-then-drinks left an evening out with no meal in it.
            short={2: ((PLAY, DINNER), (DRINKS,))},
        ),
        # After dinner, bowling or a film: not the mall, theme park or sight
        # the daytime activity falls back to, which are shut by 21:00.
        DayPart.night: _plan(
            DINNER, NIGHT_PLAY, DESSERT, DRINKS,
            keep=(DRINKS, DINNER, NIGHT_PLAY, DESSERT),
        ),
    },
    Occasion.solo: {
        DayPart.morning: _plan(
            STROLL, CAFE, QUIET, SOLO_SIGHT,
            keep=(CAFE, STROLL, QUIET, SOLO_SIGHT),
        ),
        DayPart.afternoon: _plan(CAFE, QUIET, SOLO_SIGHT, STROLL),
        DayPart.evening: _plan(
            # The fourth stop is dinner, not a sight: a sight reached at 18:30
            # is closing or shut.
            STROLL, QUIET, CAFE, DINNER,
            keep=(CAFE, STROLL, QUIET, DINNER),
        ),
        # A late café or dessert place, dinner, a film, a bar: what is open.
        # (It was a coffee, then a park, gallery or library at 20:40.)
        DayPart.night: _plan(
            DINNER, LATE_SHOW, DESSERT, NIGHTCAP,
            keep=(DESSERT, DINNER, LATE_SHOW, NIGHTCAP),
        ),
    },
    Occasion.family: {
        DayPart.morning: _plan(
            FAMILY_FUN, FAMILY_MORE, MEAL, TREAT,
            keep=(MEAL, FAMILY_FUN, TREAT, FAMILY_MORE),
        ),
        DayPart.afternoon: _plan(
            MEAL, FAMILY_FUN, FAMILY_MORE, TREAT,
            keep=(MEAL, FAMILY_FUN, TREAT, FAMILY_MORE),
        ),
        DayPart.evening: _plan(
            FAMILY_FUN, FAMILY_MORE, DINNER, TREAT,
            keep=(FAMILY_FUN, DINNER, TREAT, FAMILY_MORE),
            short={1: ((DINNER,), (FAMILY_FUN,))},
        ),
        # Shorter and indoors: dinner, a treat, then bowling or a film. A park
        # or zoo is shut after dinner, and a fourth stop would run a family
        # out past 23:00.
        DayPart.night: _plan(DINNER, TREAT, FAMILY_NIGHT_PLAY),
    },
}

MAX_STOPS = 4
