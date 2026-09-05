"""Ann Arbor with Kids.

They publish their entire calendar as iCal at /events.ics and link to it on
every day page, so there is no reason to scrape the HTML. One request gets
every event they have, roughly 650 at a time, with coordinates and their own
category tags.

Their categories are better metadata than anything I could infer from the copy:

    Babies, Toddler, Preschoolers, Elementary, Middle Schoolers, High Schoolers
    Free, Indoor Activities, Outdoor
    Advance Registration, Registration Required

Two quirks worth knowing. Their iCal folds long CATEGORIES lines mid-word and
eats the space, so "Indoor Activities" can arrive as "IndoorActivities". I
normalize by stripping spaces and punctuation before matching. And the HTML
scrape is still here as a fallback in case the feed ever goes away.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .. import http
from ..models import Event

BASE = "https://annarborwithkids.com"
ICS_URL = f"{BASE}/events.ics"
SOURCE = "aawk"
SOURCE_NAME = "Ann Arbor with Kids"

# Their category -> (min age, max age). Keys are normalized: lowercase, no
# spaces, no apostrophes, which makes the folding damage harmless.
CATEGORY_AGES = {
    "babies": (0, 2),
    "toddler": (1, 3),
    "toddlers": (1, 3),
    "preschoolers": (3, 5),
    "preschool": (3, 5),
    "elementary": (5, 11),
    "middleschoolers": (10, 14),
    "highschoolers": (14, 18),
    "teens": (13, 18),
    "tweens": (10, 13),
}

FREE_CATEGORIES = {"free"}
REGISTRATION_CATEGORIES = {"advanceregistration", "registrationrequired", "tickets"}
INDOOR_CATEGORIES = {"indooractivities", "indoor"}
OUTDOOR_CATEGORIES = {"outdoor", "outdooractivities", "farmersmarket", "nature"}

# Tags that describe the listing rather than the event. Dropped from display.
NOISE_CATEGORIES = {"exclude", "parents", "arboranniceshighlights", "arborannieshighlights"}


def normalize_category(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def unfold(text: str) -> str:
    """RFC 5545 line unfolding."""
    return re.sub(r"\r?\n[ \t]", "", text)


def _dt(value: str, params: str) -> tuple:
    """Returns (iso string, is_all_day)."""
    value = value.strip()
    all_day = "VALUE=DATE" in params or len(value) == 8
    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00", False
        if "T" in value:
            dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        else:
            dt = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return "", False
    offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset, all_day


def _unescape(value: str) -> str:
    """iCal escaping out, then the HTML entities they leave in the text."""
    text = (
        value.replace("\\n", " ").replace("\\N", " ")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    )
    text = htmllib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_feed(text: str) -> list:
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold(text), re.DOTALL):
        fields = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            head, value = line.split(":", 1)
            name = head.split(";")[0].upper()
            if name not in fields:
                fields[name] = value.strip()
                fields[name + "@"] = head

        title = _unescape(fields.get("SUMMARY", ""))
        start, all_day = _dt(fields.get("DTSTART", ""), fields.get("DTSTART@", ""))
        if not title or not start:
            continue
        end, _ = _dt(fields.get("DTEND", ""), fields.get("DTEND@", ""))

        raw_categories = [c.strip() for c in _unescape(fields.get("CATEGORIES", "")).split(",")]
        raw_categories = [c for c in raw_categories if c]
        keys = {normalize_category(c) for c in raw_categories}

        lows = [CATEGORY_AGES[k][0] for k in keys if k in CATEGORY_AGES]
        highs = [CATEGORY_AGES[k][1] for k in keys if k in CATEGORY_AGES]

        lat = lon = None
        if fields.get("GEO"):
            parts = fields["GEO"].replace(",", ";").split(";")
            try:
                lat, lon = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                lat = lon = None

        # Their LOCATION runs "Venue, Street, City, State, Zip, Neighborhood,
        # Country", so the last piece is "United States" and useless. Take the
        # first piece as the venue and let geo.py read the city out of the rest.
        venue = _unescape(fields.get("LOCATION", ""))
        pieces = [p.strip() for p in venue.split(",") if p.strip()]

        setting = "unknown"
        if keys & INDOOR_CATEGORIES and keys & OUTDOOR_CATEGORIES:
            setting = "both"
        elif keys & INDOOR_CATEGORIES:
            setting = "indoor"
        elif keys & OUTDOOR_CATEGORIES:
            setting = "outdoor"

        event = Event(
            title=title,
            start=start,
            end=end or None,
            all_day=all_day,
            description=_unescape(fields.get("DESCRIPTION", ""))[:1500],
            url=fields.get("URL", "") or BASE,
            venue=pieces[0] if pieces else venue,
            address=venue,
            lat=lat,
            lon=lon,
            image=fields.get("ATTACH", ""),
            setting=setting,
            cost="free" if keys & FREE_CATEGORIES else "unknown",
            price="Free" if keys & FREE_CATEGORIES else "",
            registration=bool(keys & REGISTRATION_CATEGORIES),
            categories=[c for c in raw_categories if normalize_category(c) not in NOISE_CATEGORIES],
            source=SOURCE,
            source_name=SOURCE_NAME,
        )

        if lows and highs:
            event.age_min, event.age_max = min(lows), max(highs)
            event.audience_raw = ", ".join(
                c for c in raw_categories if normalize_category(c) in CATEGORY_AGES
            )
            from ..classify import bands_for  # local import keeps the module graph flat
            event.ages = bands_for(event.age_min, event.age_max, False)

        events.append(event)

    return events


# --- Fallback: the HTML day pages ------------------------------------------
#
# Only used if the iCal feed stops answering. Each /events/YYYY-MM-DD/ page has
# a table of that day's events with the same symbols the site legend explains.

DAY_ROW_RE = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<day>\d{1,2})\s*\n?\s*(?P<time>All Day|[\d:apm\-\s]+?)\s*\n?"
    r"(?P<title>[^\n]+?)\s*at\s+(?P<venue>[^\n]+)",
    re.IGNORECASE,
)


def parse_day_page(html: str, year: int) -> list:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("main") or soup
    text = body.get_text("\n", strip=True)

    events = []
    for match in DAY_ROW_RE.finditer(text):
        try:
            day = datetime.strptime(
                f"{match.group('month')} {match.group('day')} {year}", "%B %d %Y"
            )
        except ValueError:
            continue

        time_text = match.group("time").strip()
        all_day = time_text.lower() == "all day"
        times = re.findall(r"\d{1,2}(?::\d{2})?\s*[ap]m", time_text, re.IGNORECASE)

        def stamp(token):
            d = day
            if token:
                token = token.lower().replace(" ", "")
                fmt = "%I:%M%p" if ":" in token else "%I%p"
                try:
                    t = datetime.strptime(token, fmt)
                    d = d.replace(hour=t.hour, minute=t.minute)
                except ValueError:
                    pass
            offset = "-04:00" if 3 <= d.month <= 11 else "-05:00"
            return d.strftime("%Y-%m-%dT%H:%M:%S") + offset

        events.append(
            Event(
                title=match.group("title").strip(),
                start=stamp(times[0] if times else None),
                end=stamp(times[1]) if len(times) > 1 else None,
                all_day=all_day,
                venue=match.group("venue").strip(),
                url=f"{BASE}/events/",
                source=SOURCE,
                source_name=SOURCE_NAME,
            )
        )
    return events


def fetch() -> list:
    try:
        return parse_feed(http.get(ICS_URL))
    except http.FetchError:
        pass

    # Feed is down. Walk the day pages instead.
    events = []
    today = datetime.now()
    for offset in range(60):
        day = today.fromordinal(today.toordinal() + offset)
        try:
            html = http.get(f"{BASE}/events/{day.strftime('%Y-%m-%d')}/")
        except http.FetchError:
            continue
        events.extend(parse_day_page(html, day.year))
    return events
