"""Does a quest's schedule fit its places' opening hours, weekday by weekday?

Pure functions over the `regularOpeningHours` object of the Places API (New):
no network, no files, so they are tested on hand-written data and can be run
over saved responses. `scripts/verify_curated.py` uses them.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Literal, get_args

from models import Quest, Weekday

WEEKDAYS: tuple[Weekday, ...] = get_args(Weekday)  # Monday first

Verdict = Literal["open", "part", "shut"]

_DAY = 24 * 60
_WEEK = 7 * _DAY

# Minutes from Monday 00:00, as (opens, closes) pairs.
Spans = list[tuple[int, int]]


def _week_minute(point: dict[str, Any]) -> int:
    """Google counts days from Sunday = 0; we count from Monday."""
    day = (point["day"] - 1) % 7
    return day * _DAY + point.get("hour", 0) * 60 + point.get("minute", 0)


def _merged(spans: Spans) -> Spans:
    """Sorted, with spans that overlap or touch joined: a place open either
    side of midnight can be listed as two periods."""
    out: Spans = []
    for opens, closes in sorted(spans):
        if out and opens <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], closes))
        else:
            out.append((opens, closes))
    return out


def open_spans(hours: dict[str, Any] | None) -> Spans | None:
    """When the place is open, over two weeks so that a visit running from
    Sunday night into Monday is one stretch. None when Google lists no hours."""
    periods = (hours or {}).get("periods")
    if not periods:
        return None
    spans: Spans = []
    for period in periods:
        if "close" not in period:  # how Google writes "never closes"
            return [(0, 2 * _WEEK)]
        opens = _week_minute(period["open"])
        closes = _week_minute(period["close"])
        if closes <= opens:  # runs past the end of Sunday
            closes += _WEEK
        spans += [(opens + shift, closes + shift) for shift in (-_WEEK, 0, _WEEK)]
    return _merged(spans)


def _visit(spans: Spans, day: int, start: time, end: time) -> Verdict:
    begins = (day % 7) * _DAY + start.hour * 60 + start.minute
    length = (end.hour * 60 + end.minute - start.hour * 60 - start.minute) % _DAY
    ends = begins + length
    if any(opens <= begins and closes >= ends for opens, closes in spans):
        return "open"
    if any(opens < ends and closes > begins for opens, closes in spans):
        return "part"
    return "shut"


def week_of_visits(
    hours: dict[str, Any] | None, start: time, end: time, *, days_later: int = 0
) -> dict[Weekday, Verdict] | None:
    """For each day a quest could be run: is the place open for the whole
    visit, part of it, or none of it? None when Google lists no hours.
    `days_later` is 1 for a stop the quest only reaches after midnight."""
    spans = open_spans(hours)
    if spans is None:
        return None
    return {
        day: _visit(spans, index + days_later, start, end)
        for index, day in enumerate(WEEKDAYS)
    }


def _days_after_start(quest: Quest) -> list[int]:
    """A stop whose clock time is earlier than the one before it is past
    midnight, so it falls on the next day."""
    later, previous, out = 0, None, []
    for stop in quest.stops:
        if previous is not None and stop.time_block_start < previous:
            later += 1
        previous = stop.time_block_start
        out.append(later)
    return out


def _plural(day: Weekday) -> str:
    return f"{day.capitalize()}s"


def check_closed_days(
    quest: Quest, hours_by_stop: list[dict[str, Any] | None]
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Compare the days a quest declares closed with each stop's hours.

    Returns (problems, notes), each a list of (stop index, message). A problem
    is a stop that is not open for its whole visit on a day the quest does not
    declare for it, or a declared day on which it is open. A stop with no
    hours on Google cannot be judged either way, so it is only noted.
    """
    problems: list[tuple[int, str]] = []
    notes: list[tuple[int, str]] = []
    declared = {(entry.day, entry.stop_index) for entry in quest.closed_days or []}
    later = _days_after_start(quest)

    for index, (stop, hours) in enumerate(zip(quest.stops, hours_by_stop, strict=True)):
        visit = f"{stop.time_block_start:%H:%M}-{stop.time_block_end:%H:%M}"
        week = week_of_visits(
            hours, stop.time_block_start, stop.time_block_end, days_later=later[index]
        )
        if week is None:
            unchecked = [_plural(d) for d in WEEKDAYS if (d, index) in declared]
            claim = f" (declared closed on {', '.join(unchecked)})" if unchecked else ""
            notes.append((index, f"no opening hours on Google: check by hand{claim}"))
            continue
        for day, verdict in week.items():
            if verdict != "open" and (day, index) not in declared:
                how = "shut for" if verdict == "shut" else "open for only part of"
                problems.append(
                    (index, f"{_plural(day)}: {how} the {visit} visit, and the quest does not declare it")
                )
            elif verdict == "open" and (day, index) in declared:
                problems.append(
                    (index, f"{_plural(day)}: declared closed, but open for the whole {visit} visit")
                )
    return problems, notes
