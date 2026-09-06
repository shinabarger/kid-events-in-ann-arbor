"""Things that sit on event calendars without being events.

The one that started this: "Kids Eat Free". Ann Arbor with Kids publishes it
as an all-day listing that repeats every single day, so it took thirteen of the
hundred and three rows on the calendar. It is a running list of restaurants
running a promotion. There is no time, no place, nothing to turn up to, and
nothing about it is programming for children. It is an advert with a date on it.

Different from kidfilter.py in two ways that matter:

  kidfilter asks "is this for children", and only asks it of general calendars
  where the answer could go either way.

  This asks "is this an event at all", and asks it of everything, because a
  standing promotion is not an event no matter how kid-focused the source is.
"""

from __future__ import annotations

import os
import re

import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_ROOT, "config", "not-events.yaml")


def load_rules(path: str = PATH) -> dict:
    empty = {"titles": [], "venues": [], "title_and_venue": []}
    if not os.path.exists(path):
        return empty
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return {
        "titles": [re.compile(p, re.I) for p in (raw.get("titles") or [])],
        "venues": [re.compile(p, re.I) for p in (raw.get("venues") or [])],
        "title_and_venue": [
            (re.compile(pair["title"], re.I), re.compile(pair["venue"], re.I))
            for pair in (raw.get("title_and_venue") or [])
            if pair.get("title") and pair.get("venue")
        ],
    }


def verdict(event, rules: dict) -> tuple:
    """(is_an_event, why_not)."""
    title = str(getattr(event, "title", "") or "")
    venue = str(getattr(event, "venue", "") or "")

    hit = next((p.pattern for p in rules["titles"] if p.search(title)), None)
    if hit:
        return False, f"not an event: {hit}"

    hit = next((p.pattern for p in rules["venues"] if p.search(venue)), None)
    if hit:
        return False, f"not a place you turn up to: {hit}"

    for title_pattern, venue_pattern in rules["title_and_venue"]:
        if title_pattern.search(title) and venue_pattern.search(venue):
            return False, f"not an event: {title_pattern.pattern} at {venue_pattern.pattern}"

    return True, ""


def apply(events: list, rules: dict | None = None) -> tuple:
    """Returns (kept, dropped). Dropped rows carry their reason for the log."""
    rules = load_rules() if rules is None else rules
    kept, dropped = [], []
    for event in events:
        ok, why = verdict(event, rules)
        if ok:
            kept.append(event)
        else:
            event.drop_reason = why
            dropped.append(event)
    return kept, dropped
