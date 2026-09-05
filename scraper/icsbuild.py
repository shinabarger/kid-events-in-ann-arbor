"""Write the .ics subscription feeds that Google and Apple Calendar read.

One feed per useful slice. Apple and Google both poll a plain https URL, so
these are just files sitting in feeds/ that the daily run rewrites.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .models import AGE_BANDS, AGE_BAND_LABELS

PRODID = "-//kid-events-in-ann-arbor//EN"
LINE_LIMIT = 74


def _escape(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 says wrap at 75 octets with a leading space on continuations."""
    if len(line) <= LINE_LIMIT:
        return line
    chunks = [line[:LINE_LIMIT]]
    rest = line[LINE_LIMIT:]
    while rest:
        chunks.append(" " + rest[: LINE_LIMIT - 1])
        rest = rest[LINE_LIMIT - 1:]
    return "\r\n".join(chunks)


def _stamp(value: str) -> str:
    """ISO string in, UTC iCal timestamp out."""
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


SITE = "https://shinabarger.github.io/kid-events-in-ann-arbor"


def calendar_location(event: dict) -> str:
    """Venue plus street address, so the calendar app can map it."""
    parts = []
    if event.get("venue"):
        parts.append(event["venue"])
    address = event.get("address") or ""
    if address and address != event.get("venue"):
        parts.append(address)
    elif event.get("city"):
        parts.append(event["city"] + ", MI")
    return ", ".join(parts) or "Ann Arbor, MI"


def build_description(event: dict) -> str:
    """Everything worth having on the calendar three weeks from now, when the
    title alone will not remind you what this was or where to park."""
    lines = []
    if event.get("description"):
        lines.extend([event["description"], ""])

    place = event.get("address") or event.get("venue")
    if place:
        where = f"Where: {place}"
        city = event.get("city") or ""
        if city and city not in place:
            where += f", {city}"
        lines.append(where)

    if event.get("drive_minutes") is not None and event.get("zone") != "city":
        lines.append(f"Drive: about {event['drive_minutes']} minutes from downtown Ann Arbor")

    if event.get("audience_raw"):
        lines.append(f"Ages: {event['audience_raw']}")
    elif event.get("all_ages"):
        lines.append("Ages: all ages")

    if event.get("cost") == "free":
        cost = "Free"
    elif event.get("price"):
        cost = event["price"]
    elif event.get("cost") == "paid":
        cost = "Paid"
    else:
        cost = "Not listed"
    lines.append(f"Cost: {cost}")

    lines.append("Signup: " + ("Registration required, book before you go"
                               if event.get("registration")
                               else "Drop in, no signup needed"))

    if event.get("setting") == "indoor":
        lines.append("Indoors")
    elif event.get("setting") == "outdoor":
        lines.append("Outdoors, dress for the weather")

    if event.get("source_name"):
        lines.append(f"Listed by: {event['source_name']}")
    if event.get("url"):
        lines.append(f"Details: {event['url']}")
    lines.append(f"Found on: {SITE}/?event={event['id']}")
    lines.extend(["", "Double check the time with the organizer before you go."])

    return "\n".join(lines)


def event_to_vevent(event: dict) -> list:
    start = _stamp(event.get("start", ""))
    if not start:
        return []

    end = _stamp(event.get("end") or "") or start
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    description = build_description(event)

    lines = [
        "BEGIN:VEVENT",
        f"UID:{event['id']}@kid-events-in-ann-arbor",
        f"DTSTAMP:{now}",
        f"DTSTART:{start}",
        f"DTEND:{end}",
        f"SUMMARY:{_escape(event.get('title', ''))}",
    ]
    lines.append(f"LOCATION:{_escape(calendar_location(event))}")
    if event.get("lat") is not None and event.get("lon") is not None:
        lines.append(f"GEO:{event['lat']};{event['lon']}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if event.get("url"):
        lines.append(f"URL:{event['url']}")
    categories = [c for c in event.get("categories", []) if c][:6]
    if categories:
        lines.append(f"CATEGORIES:{_escape(','.join(categories))}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(events: list, name: str, description: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        f"X-WR-CALDESC:{_escape(description)}",
        "X-WR-TIMEZONE:America/Detroit",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for event in events:
        lines.extend(event_to_vevent(event))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def feed_definitions() -> list:
    """Every .ics file the site offers, as (filename, label, predicate)."""
    feeds = [
        ("all.ics", "Kid Events in Ann Arbor", "Everything on the calendar", lambda e: True),
        (
            "free.ics",
            "Kid Events in Ann Arbor: Free",
            "Free events only",
            lambda e: e.get("cost") == "free",
        ),
        (
            "drop-in.ics",
            "Kid Events in Ann Arbor: Drop-in",
            "No registration needed",
            lambda e: not e.get("registration"),
        ),
        (
            "outdoor.ics",
            "Kid Events in Ann Arbor: Outdoor",
            "Outdoor events",
            lambda e: e.get("setting") in ("outdoor", "both"),
        ),
        (
            "indoor.ics",
            "Kid Events in Ann Arbor: Indoor",
            "Indoor events",
            lambda e: e.get("setting") in ("indoor", "both"),
        ),
        (
            "ann-arbor-city.ics",
            "Kid Events: Ann Arbor city limits",
            "Inside the Ann Arbor city limits",
            lambda e: e.get("zone") == "city",
        ),
        (
            "within-30-minutes.ics",
            "Kid Events: within a 30 minute drive",
            "About a 30 minute drive from downtown or less",
            lambda e: e.get("zone") in ("city", "near"),
        ),
        (
            "bus-reachable.ics",
            "Kid Events: within an hour bus ride",
            "Plausibly an hour or less on TheRide, walking included",
            lambda e: bool(e.get("bus")),
        ),
        (
            "washtenaw-county.ics",
            "Kid Events: Washtenaw County",
            "Anywhere in Washtenaw County",
            lambda e: bool(e.get("washtenaw")),
        ),
    ]

    for band in AGE_BANDS:
        feeds.append(
            (
                f"age-{band}.ics",
                f"Kid Events: {AGE_BAND_LABELS[band]}",
                f"Events suitable for {AGE_BAND_LABELS[band].lower()}",
                (lambda b: lambda e: b in (e.get("ages") or []))(band),
            )
        )
    return feeds


def write_feeds(events: list, out_dir: str) -> list:
    """Write every feed, and clear out any that no longer exist.

    Renaming a feed used to leave the old file sitting there being served
    forever, which is worse than a 404: anybody already subscribed keeps
    getting a calendar that quietly stops updating.
    """
    os.makedirs(out_dir, exist_ok=True)
    current = {name for name, _, _, _ in feed_definitions()}
    for stale in os.listdir(out_dir):
        if stale.endswith(".ics") and stale not in current:
            os.remove(os.path.join(out_dir, stale))

    written = []
    for filename, name, description, keep in feed_definitions():
        subset = [e for e in events if keep(e)]
        text = build_calendar(subset, name, description)
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        written.append({"file": filename, "name": name, "description": description,
                        "count": len(subset)})
    return written
