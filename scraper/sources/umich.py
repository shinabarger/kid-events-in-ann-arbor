"""University of Michigan events (Happening @ Michigan).

This one is easy: events.umich.edu publishes JSON. It covers the Museum of
Natural History, UMMA, Matthaei, the planetarium, and the campus stuff that
turns out to be family friendly. The feed is the whole university though, so
the kid filter in classify.py does real work here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import http
from ..models import Event

BASE = "https://events.umich.edu"
SOURCE = "umich"
SOURCE_NAME = "U-M Happening"

DAYS_AHEAD = 60

# Sponsors worth keeping even when the copy does not say "kids".
FAMILY_SPONSORS = (
    "museum of natural history",
    "museum of art",
    "matthaei",
    "nichols arboretum",
    "planetarium",
    "kelsey museum",
    "detroit observatory",
)


def _iso(date_str: str, time_str: str) -> str:
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset


def parse_payload(payload) -> list:
    """The API returns a dict keyed by occurrence id, sometimes a list."""
    rows = payload.values() if isinstance(payload, dict) else payload
    events = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        title = row.get("combined_title") or row.get("event_title") or ""
        start = _iso(row.get("date_start", ""), row.get("time_start", "00:00:00"))
        if not title or not start:
            continue

        end = ""
        if row.get("has_end_time"):
            end = _iso(row.get("date_end", ""), row.get("time_end", "00:00:00"))

        sponsors = row.get("sponsors") or []
        if isinstance(sponsors, dict):
            sponsors = list(sponsors.values())
        sponsors = [str(s) for s in sponsors]

        tags = row.get("tags") or []
        if isinstance(tags, dict):
            tags = list(tags.values())

        venue = " ".join(
            part for part in [row.get("building_name", ""), row.get("room", "")] if part
        ).strip()

        cost_text = str(row.get("cost") or "")

        events.append(
            Event(
                title=title,
                start=start,
                end=end or None,
                all_day=row.get("time_start") == "00:00:00" and not row.get("has_end_time"),
                description=(row.get("description") or "")[:1500],
                url=(row.get("permalink") or "").replace("http://", "https://"),
                venue=venue or row.get("location_name", ""),
                city="Ann Arbor",
                image=row.get("image_url", "") or "",
                price=cost_text,
                categories=[str(t) for t in tags] + [row.get("event_type", "")],
                source=SOURCE,
                source_name=SOURCE_NAME,
            )
        )
        events[-1].categories = [c for c in events[-1].categories if c]
        events[-1].categories.extend(sponsors)

    return events


def is_family_sponsored(event) -> bool:
    blob = " ".join(event.categories).lower() + " " + event.venue.lower()
    return any(s in blob for s in FAMILY_SPONSORS)


def fetch(days: int = DAYS_AHEAD) -> list:
    events = []
    today = datetime.now().date()
    for offset in range(days):
        day = today + timedelta(days=offset)
        try:
            payload = http.get_json(f"{BASE}/day/{day.isoformat()}/json")
        except Exception:  # noqa: BLE001
            continue
        events.extend(parse_payload(payload))
    return events
