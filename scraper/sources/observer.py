"""Ann Arbor Observer.

Two very different things live on this site.

1. /kids-calendar/ is hand written by an editor. It is not a database, it is
   prose, one paragraph per event, in a house style that has not changed in
   years:

       ★ Sept. 4 (1-2 p.m.): "Tech Take-Apart": AADL Downtown. Kids grade 2 &
       up invited to take apart toasters, keyboards, and other small devices.

   A star means free. One paragraph can carry several dates and several time
   windows ("Sept. 14 & 16 (10:30-11 a.m.) and Sept. 15 (1:30-2 p.m.)"), and
   each combination becomes its own event. Lines that start with "Every" are
   the recurring library programs, which AADL already gives me with real dates,
   so those get skipped rather than guessed at.

   This is the best editorial filter of any source. Somebody chose these.

2. The rest of the site runs The Events Calendar, which has a proper REST API.
   That is handled by the "tribe" strategy in generic.py.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .. import http
from ..classify import parse_age_range
from ..models import Event

BASE = "https://annarborobserver.com"
KIDS_URL = f"{BASE}/kids-calendar/"
SOURCE = "a2observer_kids"
SOURCE_NAME = "Ann Arbor Observer Kids Calendar"

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "Sept. 14 & 16 (10:30-11 a.m.)" or just "12, 22, & 29 (3-4 p.m.)"
DATE_GROUP_RE = re.compile(
    r"(?:(?P<month>[A-Z][a-z]{2,4})\.?\s+)?"
    r"(?<!\$)(?P<days>\d{1,2}(?:(?:\s*[,&]\s*|\s+and\s+)+\d{1,2})*)\s*"
    r"\((?P<time>[^)]{2,40})\)",
)

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|noon)?", re.IGNORECASE)

# The editor's abbreviations, expanded so the venue lookup can find them.
VENUE_EXPANSIONS = {
    "AADL Downtown": "Downtown Library",
    "AADL Westgate": "Westgate Branch",
    "AADL Traverwood": "Traverwood Branch",
    "AADL Malletts Creek": "Malletts Creek Branch",
    "AADL Pittsfield": "Pittsfield Branch",
    "AADL": "Ann Arbor District Library",
    "HSHV": "Humane Society of Huron Valley",
    "AAHOM": "Ann Arbor Hands-On Museum",
}

REGISTRATION_RE = re.compile(r"preregistration required|registration required|tickets", re.IGNORECASE)
MONEY_RE = re.compile(r"\$\s?(\d+(?:\.\d{2})?)")


def month_year(text: str, fallback_year: int) -> tuple:
    """The page carries a "September 2026" heading above the listings."""
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(20\d{2})\b", text)
    if match:
        return MONTHS[match.group(1)[:3].lower()], int(match.group(2))
    return datetime.now().month, fallback_year


def parse_clock(token: str, is_pm_hint: bool):
    """"10:30", "1", "noon" plus an am/pm that may only appear at the end."""
    token = token.strip().lower()
    if "noon" in token:
        return 12, 0
    match = TIME_RE.match(token)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").replace(".", "")
    if meridiem.startswith("p") or (not meridiem and is_pm_hint):
        if hour != 12:
            hour += 12
    elif meridiem.startswith("a") and hour == 12:
        hour = 0
    return hour, minute


def split_time_window(window: str):
    """"1-2 p.m." -> ((13, 0), (14, 0)). Returns (start, end), either may be None."""
    window = window.replace("–", "-").replace("—", "-").strip()
    if "different times" in window.lower() or not window:
        return None, None

    is_pm = bool(re.search(r"p\.?m\.?", window, re.IGNORECASE))
    parts = [p.strip() for p in window.split("-", 1)]

    # In "10 a.m.-noon" the first half carries its own meridiem, so only let
    # the trailing p.m. bleed backwards when the first half has none.
    first_has_meridiem = bool(re.search(r"[ap]\.?m\.?|noon", parts[0], re.IGNORECASE))
    start = parse_clock(parts[0], is_pm and not first_has_meridiem)
    end = parse_clock(parts[1], is_pm) if len(parts) > 1 else None
    return start, end


def _iso(year: int, month: int, day: int, clock) -> str:
    hour, minute = clock if clock else (0, 0)
    try:
        dt = datetime(year, month, day, hour, minute)
    except ValueError:
        return ""
    offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset


def split_title_venue(rest: str) -> tuple:
    """"Title": Venue. Description  ->  (title, venue, description)

    The title is often in curly quotes and can contain its own colon, as in
    "Little Story Party: Dino Party", so quotes win over the first colon.
    """
    rest = rest.strip()
    quoted = re.match(r'^[“"‘\']([^”"’]+)[”"’]\s*:?\s*(.*)$', rest, re.DOTALL)
    if quoted:
        title = quoted.group(1).strip()
        tail = quoted.group(2).strip()
    elif ":" in rest:
        title, tail = rest.split(":", 1)
        title, tail = title.strip(), tail.strip()
    else:
        title, tail = rest, ""

    venue, description = "", tail
    if tail:
        # Venue runs to the first sentence break. A period only ends the venue
        # when a capital follows, so "220 E. Ann St." stays in one piece.
        match = re.match(r"^(.{2,140}?)\.\s+(?=[A-Z“\"])(.*)$", tail, re.DOTALL)
        if match:
            venue, description = match.group(1).strip(), match.group(2).strip()
        elif ". " in tail:
            head, description = tail.split(". ", 1)
            venue, description = head.strip(), description.strip()
        else:
            venue = tail.rstrip(". ").strip()
            description = ""
    venue = venue[:120]

    for short, long in VENUE_EXPANSIONS.items():
        if venue == short or venue.startswith(short + " "):
            venue = venue.replace(short, long, 1)
            break

    return title, venue, description


def parse_paragraph(text: str, month: int, year: int) -> list:
    """One editorial paragraph in, zero or more events out."""
    text = re.sub(r"\s+", " ", text).replace(" ", " ").strip()
    if len(text) < 30:
        return []

    free = text.startswith("★")
    body = text.lstrip("★ ").strip()

    # "Every Mon.-Fri." has no real dates. AADL supplies those occurrences.
    if re.match(r"^every\b", body, re.IGNORECASE):
        return []

    # A real time window always carries a meridiem (a.m./p.m.) or 'noon'.
    # Phone numbers like '(734) 764-9304' and parenthetical asides like
    # 'ages 4-8 (accompanied by an adult)' match the regex shape but have
    # no meridiem, so drop them before computing the tail.
    groups = [
        g for g in DATE_GROUP_RE.finditer(body)
        if re.search(r'a\.?m\.?|p\.?m\.?|noon', g.group('time'), re.IGNORECASE)
    ]
    if not groups:
        return []

    # Everything after the last date group is the title, venue, description.
    tail = body[groups[-1].end():].lstrip(": ").strip()
    if not tail:
        return []

    title, venue, description = split_title_venue(tail)
    if not title:
        return []

    # A real title starts with a letter, digit, or opening quote. Anything
    # else is debris from a date group landing inside a description.
    if not re.match(r'^[A-Za-z0-9"“‘'']', title):
        return []

    money = MONEY_RE.search(body)
    cost = "free" if free and not money else ("paid" if money else "unknown")
    price = "Free" if cost == "free" else ("$" + money.group(1) if money else "")

    events = []
    for group in groups:
        group_month = month
        if group.group("month"):
            key = group.group("month")[:4].lower().rstrip(".")
            group_month = MONTHS.get(key, MONTHS.get(key[:3], month))

        start_clock, end_clock = split_time_window(group.group("time"))

        for day_text in re.split(r"\s*(?:,|&|and)\s*", group.group("days")):
            if not day_text.strip().isdigit():
                continue
            day = int(day_text)
            start = _iso(year, group_month, day, start_clock)
            if not start:
                continue

            events.append(
                Event(
                    title=title,
                    start=start,
                    end=_iso(year, group_month, day, end_clock) if end_clock else None,
                    all_day=start_clock is None,
                    description=description[:1500],
                    url=KIDS_URL,
                    venue=venue,
                    # The whole page is headed "Kids Calendar (age 12 & under)",
                    # which is a fine floor for a listing that names no age.
                    # It must not be set when the listing does name one:
                    # classify reads audience_raw before it reads the words,
                    # so the blanket header was burying every stated range and
                    # filing a 6-11 reading group under Babies.
                    audience_raw=page_audience(title, description),
                    cost=cost,
                    price=price,
                    registration=bool(REGISTRATION_RE.search(body)),
                    categories=["Observer pick"],
                    source=SOURCE,
                    source_name=SOURCE_NAME,
                )
            )
    return events


# A genuine listing has a bracketed clock time in it.
ENTRY_SHAPE_RE = re.compile(r"\([^)]*(?:a\.?m\.?|p\.?m\.?|noon)[^)]*\)", re.IGNORECASE)

# An entry starts with an optional star and then a month and a day. Used to
# carve entries out of the raw text when the markup is not cooperating.
ENTRY_START_RE = re.compile(
    r"(?=(?:\u2605\s*)?(?:Jan|Feb|Mar|Apr|May|Jun|July?|Aug|Sept?|Oct|Nov|Dec)\.?\s+\d{1,2}\b)")


def page_audience(title: str, description: str) -> str:
    """The page level "age 12 & under" only when the listing is silent."""
    low, high, _all_ages = parse_age_range(title, description)
    if low is not None or high is not None:
        return ""
    # "all ages" or "the whole family" is not a number, and this page still
    # tops out at twelve, so the header stays and caps it.
    return "age 12 & under"


def parse_page(html: str, fallback_year: int | None = None) -> list:
    fallback_year = fallback_year or datetime.now().year
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup
    text = main.get_text(" ", strip=True)
    month, year = month_year(text, fallback_year)

    # The happy path: one entry per block element.
    events = []
    for block in main.find_all(["p", "li"]):
        events.extend(parse_paragraph(block.get_text(" ", strip=True), month, year))
    if events:
        return events

    # Nothing came back, which has happened before when the site moved the
    # listings out of <p> tags. Fall back to the page's own text and cut it up
    # on the date markers, so the shape of the markup stops mattering.
    whole = soup.get_text(" ", strip=True)
    month, year = month_year(whole, fallback_year)

    seen = set()
    for chunk in ENTRY_START_RE.split(whole):
        chunk = chunk.strip()
        # A real entry always carries a clock time in brackets. Without this
        # the "Key to Locations" block, which lists opening hours, gets carved
        # up into events with no start time.
        if not chunk or not ENTRY_SHAPE_RE.search(chunk):
            continue
        for event in parse_paragraph(chunk, month, year):
            if not event.title or not event.title[0].isalnum():
                continue
            key = (event.title, event.start)
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    return events


def fetch() -> list:
    # Deliberately not catching FetchError. Swallowing it returned an empty
    # list, which the run reports as "0 events" and reads exactly like a
    # quiet week. The Observer was down for weeks looking like a quiet week.
    # run.py catches per source, so a raise here costs nothing and says why.
    return parse_page(http.get(KIDS_URL))
