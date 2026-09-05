"""Series that publish a schedule in words instead of a feed.

Some of the best small-group programming in town lives on a page that was
designed rather than generated: a picture of a month with the event names
positioned on it, no dates attached to the text, no feed, no JSON-LD, one link
on the whole page. Scraping that is a losing game. One design tweak and it
breaks, and even when it works you cannot reliably tell which day a given
label belongs to.

But those same pages almost always state the rule in plain English further
down, because that is what a human needs to know:

    Dadas & Littles     1st & 3rd Saturday 9-11am
    Mamas & Littles     2nd Saturday 9-11am

A rule is better than a scrape. It survives redesigns, it costs the
organization nothing because we never touch their server, and it is honest
about what it is. The cost is that it can go stale, which is what the
`checked` date and the `until` field are for, and why every entry links back
to the page it came from.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml

from ..models import Event

TZ = ZoneInfo("America/Detroit")
CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config"
)
PATH = os.path.join(CONFIG_DIR, "recurring.yaml")

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
ORDINALS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3,
            "4th": 4, "fourth": 4, "5th": 5, "fifth": 5, "last": -1}


class RuleError(ValueError):
    pass


def parse_rule(text: str) -> tuple:
    """"1st & 3rd saturday" -> ([1, 3], 5). "every saturday" -> ([], 5)."""
    blob = re.sub(r"\s+", " ", (text or "")).strip().lower()
    blob = re.sub(r"\b(?:of|the|month|each|every month)\b", " ", blob)

    weekday = next((d for name, d in WEEKDAYS.items() if name in blob), None)
    if weekday is None:
        raise RuleError(f"no weekday in {text!r}")

    if "every" in blob or "weekly" in blob:
        return [], weekday

    weeks = [ORDINALS[t] for t in re.findall(r"\b(1st|2nd|3rd|4th|5th|first|second|third|fourth|fifth|last)\b", blob)]
    if not weeks:
        raise RuleError(f"no ordinal or 'every' in {text!r}")
    return sorted(set(weeks), key=lambda w: (w == -1, w)), weekday


def occurrences(weeks: list, weekday: int, start: date, end: date) -> list:
    """Every date matching the rule between start and end, inclusive."""
    out = []
    day = start
    while day <= end:
        if day.weekday() == weekday:
            nth = (day.day - 1) // 7 + 1
            is_last = (day + timedelta(days=7)).month != day.month
            if not weeks or nth in weeks or (-1 in weeks and is_last):
                out.append(day)
        day += timedelta(days=1)
    return out


def _split_time(value: str) -> tuple:
    """"09:00-11:00" -> ("09:00", "11:00"). "09:00" -> ("09:00", None)."""
    parts = [p.strip() for p in re.split(r"\s*(?:-|–|to)\s*", str(value or "")) if p.strip()]
    if not parts:
        raise RuleError("no time given")
    return parts[0], (parts[1] if len(parts) > 1 else None)


def _stamp(day: date, clock: str) -> str:
    hour, minute = (int(x) for x in clock.split(":")[:2])
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).isoformat()


def expand(series: dict, entry: dict, start: date, end: date) -> list:
    weeks, weekday = parse_rule(entry.get("rule", ""))

    window_end = end
    if entry.get("until"):
        stop = entry["until"]
        stop = stop if isinstance(stop, date) else datetime.fromisoformat(str(stop)).date()
        window_end = min(window_end, stop)

    begin, finish = _split_time(entry.get("time"))

    def inherit(field, default=""):
        return entry.get(field, series.get(field, default))

    events = []
    for day in occurrences(weeks, weekday, start, window_end):
        events.append(
            Event(
                title=entry["title"],
                start=_stamp(day, begin),
                end=_stamp(day, finish) if finish else None,
                description=entry.get("description", ""),
                url=inherit("url"),
                venue=inherit("venue"),
                address=inherit("address"),
                city=inherit("city"),
                lat=inherit("lat", None),
                lon=inherit("lon", None),
                audience_raw=entry.get("ages_text", ""),
                setting=inherit("setting", "unknown"),
                cost=inherit("cost", "unknown"),
                price=inherit("price", ""),
                registration=bool(inherit("registration", False)),
                categories=entry.get("categories", []) or [],
                source=series["key"],
                source_name=series["name"],
            )
        )
    return events


def load_series(path: str = PATH) -> list:
    """Every enabled series in the file, so the run can report each one by
    name rather than lumping them into one anonymous row in the footer."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    return [s for s in (payload.get("series") or []) if s.get("enabled") is not False]


def fetch_series(series: dict, days: int = 120, today: date | None = None) -> list:
    start = today or datetime.now(TZ).date()
    end = start + timedelta(days=days)

    events = []
    for entry in series.get("events", []) or []:
        try:
            events.extend(expand(series, entry, start, end))
        except (RuleError, KeyError) as exc:
            # One bad rule should not cost us the rest of the file.
            print(f"  recurring: skipped {entry.get('title')!r}: {exc}")
    return events


def fetch(path: str = PATH, days: int = 120, today: date | None = None) -> list:
    events = []
    for series in load_series(path):
        events.extend(fetch_series(series, days=days, today=today))
    return events
