"""Opening hours against a quest's schedule, on hand-written data in the shape
of the Places API (New) `regularOpeningHours`. No network."""

from datetime import time

import pytest

from curated.builders import place, stop
from curated.hours import check_closed_days, open_spans, week_of_visits
from models import ClosedDay, CostEstimate, Occasion, Quest, StopCategory

# Google counts days from Sunday = 0.
SUN, MON, TUE, WED, THU, FRI, SAT = range(7)
ALL_WEEK = (MON, TUE, WED, THU, FRI, SAT, SUN)
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def period(day: int, opens: str, closes: str) -> dict:
    """One period. A closing time at or before the opening one is next day."""
    open_h, open_m = map(int, opens.split(":"))
    close_h, close_m = map(int, closes.split(":"))
    close_day = day if (close_h, close_m) > (open_h, open_m) else (day + 1) % 7
    return {
        "open": {"day": day, "hour": open_h, "minute": open_m},
        "close": {"day": close_day, "hour": close_h, "minute": close_m},
    }


def daily(*sessions: tuple[str, str], days=ALL_WEEK) -> dict:
    return {"periods": [period(d, o, c) for d in days for o, c in sessions]}


ALWAYS_OPEN = {"periods": [{"open": {"day": SUN, "hour": 0, "minute": 0}}]}


def days_with(verdict: str, week: dict) -> list[str]:
    return [day for day, v in week.items() if v == verdict]


# ── One visit, every weekday ──


def test_open_all_week_covers_a_visit_over_sunday_midnight() -> None:
    week = week_of_visits(ALWAYS_OPEN, time(23, 30), time(1, 0))
    assert days_with("open", week) == list(WEEKDAY_NAMES)


@pytest.mark.parametrize("hours", [None, {}, {"periods": []}, {"openNow": True}])
def test_no_hours_is_not_a_verdict(hours) -> None:
    assert open_spans(hours) is None
    assert week_of_visits(hours, time(10, 0), time(11, 0)) is None


def test_a_weekly_closed_day_is_found() -> None:
    hours = daily(("12:00", "22:00"), days=(TUE, WED, THU, FRI, SAT, SUN))
    week = week_of_visits(hours, time(18, 0), time(19, 0))
    assert days_with("shut", week) == ["monday"]


def test_a_visit_must_fit_one_of_the_lunch_and_dinner_sessions() -> None:
    hours = daily(("12:00", "15:30"), ("19:00", "23:30"))
    assert set(week_of_visits(hours, time(19, 0), time(20, 40)).values()) == {"open"}
    # Starts before dinner service: open for part of it only.
    assert set(week_of_visits(hours, time(18, 30), time(20, 0)).values()) == {"part"}
    # Spans the gap between them.
    assert set(week_of_visits(hours, time(15, 0), time(19, 30)).values()) == {"part"}
    # Inside the gap, and touching its edges.
    assert set(week_of_visits(hours, time(15, 30), time(19, 0)).values()) == {"shut"}


def test_closing_exactly_when_the_visit_ends_counts_as_open() -> None:
    hours = daily(("09:00", "17:30"))
    assert set(week_of_visits(hours, time(16, 30), time(17, 30)).values()) == {"open"}
    assert set(week_of_visits(hours, time(16, 30), time(17, 31)).values()) == {"part"}


def test_overnight_hours_cover_a_late_visit_and_belong_to_the_opening_day() -> None:
    # Open 6pm to 1am, Friday and Saturday only.
    hours = daily(("18:00", "01:00"), days=(FRI, SAT))
    late = week_of_visits(hours, time(23, 0), time(0, 30))
    assert days_with("open", late) == ["friday", "saturday"]
    # A stop reached after midnight on Friday's quest is on Saturday's date.
    after = week_of_visits(hours, time(0, 10), time(0, 50), days_later=1)
    assert days_with("open", after) == ["friday", "saturday"]


def test_saturday_night_into_sunday_wraps_googles_week() -> None:
    hours = daily(("20:00", "02:00"), days=(SAT,))
    assert days_with("open", week_of_visits(hours, time(23, 0), time(1, 0))) == ["saturday"]


def test_sunday_night_into_monday_wraps_our_week() -> None:
    hours = daily(("20:00", "02:00"), days=(SUN,))
    assert days_with("open", week_of_visits(hours, time(23, 0), time(1, 0))) == ["sunday"]


def test_periods_that_meet_at_midnight_are_one_stretch() -> None:
    hours = {"periods": [period(MON, "18:00", "00:00"), period(TUE, "00:00", "03:00")]}
    week = week_of_visits(hours, time(23, 0), time(1, 0))
    assert days_with("open", week) == ["monday"]


# ── A whole quest ──


def a_quest(*times: tuple[time, time], closed_days=None) -> Quest:
    stops = [
        stop(
            place(f"ChIJplace-{i:04d}", f"Place {i}", "Somewhere", 17.4, 78.4, 4.5, ["cafe"]),
            StopCategory.cafe,
            start,
            end,
            "A good one.",
        )
        for i, (start, end) in enumerate(times)
    ]
    return Quest(
        title="t",
        occasion=Occasion.solo,
        stops=stops,
        total_duration_minutes=120,
        total_cost_estimate=CostEstimate.cheap,
        narrative="n",
        closed_days=closed_days,
    )


TWO_STOPS = ((time(17, 0), time(18, 0)), (time(18, 10), time(19, 0)))
SHUT_MONDAYS = daily(("12:00", "22:00"), days=(TUE, WED, THU, FRI, SAT, SUN))


def test_an_undeclared_closed_day_is_a_problem() -> None:
    problems, notes = check_closed_days(a_quest(*TWO_STOPS), [ALWAYS_OPEN, SHUT_MONDAYS])
    assert problems == [(1, "Mondays: shut for the 18:10-19:00 visit, and the quest does not declare it")]
    assert notes == []


def test_a_part_open_day_is_a_problem_too() -> None:
    closes_early = daily(("12:00", "18:30"))
    problems, _ = check_closed_days(a_quest(*TWO_STOPS), [ALWAYS_OPEN, closes_early])
    assert len(problems) == 7
    assert "open for only part of" in problems[0][1]


def test_a_declared_closed_day_passes() -> None:
    quest = a_quest(*TWO_STOPS, closed_days=[ClosedDay(day="monday", stop_index=1)])
    assert check_closed_days(quest, [ALWAYS_OPEN, SHUT_MONDAYS]) == ([], [])


def test_declaring_the_wrong_stop_fails_twice_over() -> None:
    quest = a_quest(*TWO_STOPS, closed_days=[ClosedDay(day="monday", stop_index=0)])
    problems, _ = check_closed_days(quest, [ALWAYS_OPEN, SHUT_MONDAYS])
    assert [index for index, _ in problems] == [0, 1]
    assert "declared closed, but open" in problems[0][1]


def test_a_declared_day_that_is_no_longer_true_is_a_problem() -> None:
    quest = a_quest(*TWO_STOPS, closed_days=[ClosedDay(day="friday", stop_index=1)])
    problems, _ = check_closed_days(quest, [ALWAYS_OPEN, ALWAYS_OPEN])
    assert problems == [(1, "Fridays: declared closed, but open for the whole 18:10-19:00 visit")]


def test_a_place_with_no_hours_is_reported_not_failed() -> None:
    quest = a_quest(*TWO_STOPS, closed_days=[ClosedDay(day="monday", stop_index=1)])
    problems, notes = check_closed_days(quest, [ALWAYS_OPEN, None])
    assert problems == []
    assert notes == [(1, "no opening hours on Google: check by hand (declared closed on Mondays)")]


def test_a_stop_after_midnight_is_checked_on_the_next_date() -> None:
    quest = a_quest((time(22, 0), time(23, 45)), (time(0, 5), time(1, 0)))
    # Shut early on Tuesday morning, which is Monday's quest.
    after_midnight = daily(("00:00", "02:00"), days=(SUN, MON, WED, THU, FRI, SAT))
    problems, _ = check_closed_days(quest, [ALWAYS_OPEN, after_midnight])
    assert [message.split(":")[0] for _, message in problems] == ["Mondays"]
