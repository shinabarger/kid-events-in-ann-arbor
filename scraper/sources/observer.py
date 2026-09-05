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
    r"(?P<days>\d{1,2}(?:(?:\s*[,&]\s*|\s+and\s+)+\d{1,2})*)\s*"
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

    groups = list(DATE_GROUP_RE.finditer(body))
    if not groups:
        return []

    # Everything after the last date group is the title, venue, description.
    tail = body[groups[-1].end():].lstrip(": ").strip()
    if not tail:
        return []

    title, venue, description = split_title_venue(tail)
    if not title:
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
                    # so that is the floor when a listing does not say an age.
                    audience_raw="age 12 & under",
                    cost=cost,
                    price=price,
                    registration=bool(REGISTRATION_RE.search(body)),
                    categories=["Observer pick"],
                    source=SOURCE,
                    source_name=SOURCE_NAME,
                )
            )
    return events


def parse_page(html: str, fallback_year: int | None = None) -> list:
    fallback_year = fallback_year or datetime.now().year
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("main") or soup
    text = main.get_text(" ", strip=True)
    month, year = month_year(text, fallback_year)

    events = []
    for para in main.find_all("p"):
        events.extend(parse_paragraph(para.get_text(" ", strip=True), month, year))
    return events


def fetch() -> list:
    try:
        return parse_page(http.get(KIDS_URL))
    except http.FetchError:
        return []
