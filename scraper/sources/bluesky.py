"""Pull event announcements from Bluesky accounts via the AT Protocol.

The AT Protocol public API (public.api.bsky.app) is documented, open, and
unauthenticated. It returns the same posts anyone sees in a browser.

This adapter reads a Bluesky feed looking for posts that contain dates and
times, which usually means an event announcement or a schedule change.
Posts that do not mention a date are skipped: they are library chat, not
calendar items.

Currently used for:
  ypsilibrary.org  — the Ypsi Library posts closures, program changes,
                     and one-off events that do not always reach their
                     website calendar.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import http
from ..models import Event

TZ = ZoneInfo("America/Detroit")
API = "https://public.api.bsky.app/xrpc"

# Loose date patterns that catch "September 21", "Sep 21", "9/21",
# "Sept. 21st", and similar. Not trying to be perfect: false positives
# are cheap (an extra event that dedupe or kidfilter drops), false
# negatives mean a missed announcement.
DATE_RE = re.compile(
    r"\b(?:"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|"
    r"july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?"
    r"|"
    r"\d{1,2}/\d{1,2}"
    r")\b",
    re.IGNORECASE,
)

TIME_RE = re.compile(
    r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))\b",
    re.IGNORECASE,
)

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}


def _parse_date(text: str) -> datetime | None:
    """Best effort date parse from a Bluesky post snippet."""
    match = DATE_RE.search(text)
    if not match:
        return None
    blob = match.group(0).lower().rstrip(".")

    # "September 21" style
    for name, num in MONTH_MAP.items():
        if blob.startswith(name):
            day_str = re.sub(r"[^0-9]", "", blob.split()[-1])
            if day_str:
                now = datetime.now(TZ)
                year = now.year
                candidate = datetime(year, num, int(day_str), tzinfo=TZ)
                # If the date is more than 30 days in the past, it's next year
                if candidate < now - timedelta(days=30):
                    candidate = candidate.replace(year=year + 1)
                return candidate
            break

    # "9/21" style
    slash = blob.split("/")
    if len(slash) == 2 and all(s.strip().isdigit() for s in slash):
        month, day = int(slash[0]), int(slash[1])
        if 1 <= month <= 12 and 1 <= day <= 31:
            now = datetime.now(TZ)
            candidate = datetime(now.year, month, day, tzinfo=TZ)
            if candidate < now - timedelta(days=30):
                candidate = candidate.replace(year=now.year + 1)
            return candidate

    return None


def _parse_time(text: str) -> tuple[str | None, str | None]:
    """Extract up to two time tokens from text."""
    matches = TIME_RE.findall(text)
    if not matches:
        return None, None
    times = []
    for raw in matches[:2]:
        clean = raw.lower().replace(" ", "").replace(".", "")
        try:
            t = datetime.strptime(clean, "%I:%M%p")
        except ValueError:
            try:
                t = datetime.strptime(clean, "%I%p")
            except ValueError:
                continue
        times.append(f"{t.hour:02d}:{t.minute:02d}")
    start = times[0] if times else None
    end = times[1] if len(times) > 1 else None
    return start, end


def _stamp(day: datetime, clock: str | None) -> str:
    if clock:
        h, m = (int(x) for x in clock.split(":"))
        day = day.replace(hour=h, minute=m)
    return day.isoformat()


def fetch_feed(actor: str, *, source_key: str, source_name: str,
               limit: int = 30) -> list[Event]:
    """Fetch recent posts from a Bluesky account and extract events."""
    url = f"{API}/app.bsky.feed.getAuthorFeed?actor={actor}&limit={limit}"
    raw = http.get(url, skip_robots=True)
    data = json.loads(raw)

    events = []
    for item in data.get("feed", []):
        record = item.get("post", {}).get("record", {})
        text = record.get("text", "")
        created = record.get("createdAt", "")

        # Only interested in posts that mention a date
        event_date = _parse_date(text)
        if not event_date:
            continue

        start_time, end_time = _parse_time(text)
        title = text.split("\n")[0][:120].strip()
        if not title:
            continue

        # Build the Bluesky post URL for linking back
        uri = item.get("post", {}).get("uri", "")
        rkey = uri.rsplit("/", 1)[-1] if "/" in uri else ""
        post_url = f"https://bsky.app/profile/{actor}/post/{rkey}" if rkey else ""

        events.append(Event(
            title=title,
            start=_stamp(event_date, start_time),
            end=_stamp(event_date, end_time) if end_time else None,
            all_day=start_time is None,
            description=text[:1500],
            url=post_url,
            source=source_key,
            source_name=source_name,
        ))

    return events


# Default configuration for the Ypsi Library Bluesky feed.
YPSI_ACTOR = "ypsilibrary.org"
YPSI_KEY = "ypsi_library"
YPSI_NAME = "Ypsilanti District Library"


def fetch() -> list[Event]:
    return fetch_feed(YPSI_ACTOR, source_key=YPSI_KEY, source_name=YPSI_NAME)
