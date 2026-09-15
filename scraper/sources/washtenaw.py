"""Washtenaw County Parks: two calendars on washtenaw.org.

The county runs CivicPlus Evolve. The parks & rec event calendar at
/parks-and-recreation-events loads from a public content API at
content.civicplus.com. The guest token is embedded in the page as
window.hcmsClientToken, and the category ID for Parks & Recreation is
01accfb7-97a3-46af-8757-396c4f213eb3. The API is OData-style JSON.

The special events page at /special-events is a plain HTML table with
event names, locations, and date text. No API, no schema.org, just a
<table> on the page.

Both run once per day through the daily scraper.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup

from .. import http
from ..models import Event


# The CivicPlus content API category for Parks & Recreation events.
PARKS_REC_CATEGORY = "01accfb7-97a3-46af-8757-396c4f213eb3"

CONTENT_API = "https://content.civicplus.com/api/content/mi-washtenawcounty/event"

# The special events page is a static HTML table.
SPECIAL_EVENTS_URL = "https://www.washtenaw.org/special-events"


def _eastern_offset(dt: datetime) -> str:
    """EDT or EST, the rough way. Good enough for event display."""
    return "-04:00" if 3 <= dt.month <= 11 else "-05:00"


def _parse_api_dt(iso_str: str) -> str:
    """Convert a UTC ISO timestamp from the API to Eastern local time."""
    if not iso_str:
        return ""
    try:
        # The API returns dates like "2026-09-20T13:00:00.000Z"
        cleaned = iso_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(cleaned)
        # Convert to Eastern (UTC-4 in summer, UTC-5 in winter)
        offset_hours = -4 if 3 <= dt_utc.month <= 11 else -5
        dt_local = dt_utc + timedelta(hours=offset_hours)
        offset = _eastern_offset(dt_local)
        return dt_local.strftime("%Y-%m-%dT%H:%M:%S") + offset
    except (ValueError, TypeError):
        return ""


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


def _token_from_page(html_text: str) -> str:
    """Pull the guest bearer token from window.hcmsClientToken."""
    match = re.search(r'window\.hcmsClientToken\s*=\s*["\']([^"\']+)', html_text)
    if not match:
        return ""
    token = match.group(1)
    if token.startswith("Bearer "):
        token = token[len("Bearer "):]
    return token


def _build_address(addr: dict) -> tuple[str, str]:
    """Return (full address string, city) from the API address block."""
    if not addr or not isinstance(addr, dict):
        return "", ""
    parts = [
        addr.get("address1", ""),
        addr.get("address2", ""),
        addr.get("city", ""),
        addr.get("state", ""),
        addr.get("zip", ""),
    ]
    city = addr.get("city", "")
    full = ", ".join(p for p in parts if p)
    return full, city


def fetch_parks_rec(site: dict) -> list[Event]:
    """Fetch events from the CivicPlus content API for Parks & Recreation."""
    # Step 1: get the guest token from the calendar page
    page_url = site.get("calendar_page", "https://www.washtenaw.org/parks-and-recreation-events")
    page_html = http.get(page_url)
    token = _token_from_page(page_html)
    if not token:
        raise http.FetchError("could not find CivicPlus guest token on the page")

    # Step 2: query the content API
    now = datetime.now(timezone.utc)
    filter_date = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    api_url = (
        f"{CONTENT_API}"
        f"?$top=200&$skip=0"
        f"&$orderby=data/eventdate/iv/startDate%20asc"
        f"&$filter=(categories/any(c:c/id%20eq%20{PARKS_REC_CATEGORY})"
        f"%20and%20data/eventdate/iv/endDate%20ge%20{quote(filter_date, safe='')})"
    )

    import requests as req
    resp = req.get(
        api_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            **http.HEADERS,
        },
        timeout=http.TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    events = []
    for item in data.get("items", []):
        d = item.get("data", {})
        title = (d.get("title", {}).get("en") or "").strip()
        if not title:
            continue

        eventdate = d.get("eventdate", {}).get("iv", {})
        start_str = _parse_api_dt(eventdate.get("startDate", ""))
        if not start_str:
            continue

        end_str = _parse_api_dt(eventdate.get("endDate", "")) or None
        all_day = bool(eventdate.get("allDay", False))

        addr_data = d.get("address", {}).get("en", {})
        address, city = _build_address(addr_data)
        venue = addr_data.get("address1", "") if isinstance(addr_data, dict) else ""

        lat = addr_data.get("latitude") if isinstance(addr_data, dict) else None
        lon = addr_data.get("longitude") if isinstance(addr_data, dict) else None
        try:
            lat = float(lat) if lat else None
            lon = float(lon) if lon else None
        except (TypeError, ValueError):
            lat = lon = None

        description = _strip_html(d.get("description", {}).get("en", ""))
        cost_raw = d.get("Cost", {}).get("iv", "")
        cost = "unknown"
        price = ""
        if cost_raw:
            price = str(cost_raw)
            cost = "free" if re.search(r"free|no\s+cost|\$0", price, re.I) else "paid"

        # Build a URL back to the county events page for this event
        slug = item.get("id", "")
        event_url = f"https://www.washtenaw.org/parks-and-recreation-events" if not slug else page_url

        events.append(Event(
            title=title,
            start=start_str,
            end=end_str,
            all_day=all_day,
            description=description,
            url=event_url,
            venue=venue,
            address=address,
            city=city or "Washtenaw County",
            lat=lat,
            lon=lon,
            cost=cost,
            price=price,
            source=site["key"],
            source_name=site["name"],
        ))

    return events


# Months as they appear in the date text on the special events page.
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

# Patterns for parsing the freeform date text on the special events page.
# Examples: "February 7, 2026", "July 31 - August 2, 2026",
#           "Fridays May 15 - September 25, 2026"
_SINGLE_DATE = re.compile(
    r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", re.I
)


def _parse_special_dates(date_text: str, year_fallback: int) -> list[tuple[str, str | None]]:
    """Parse freeform date text into a list of (start_iso, end_iso|None) tuples.

    Returns one entry per distinct event occurrence. Multi-day ranges become a
    single entry with both start and end. Comma-separated dates within the same
    month become separate entries.
    """
    if not date_text:
        return []

    results = []
    text = date_text.strip()

    # Try to find all "Month Day, Year" patterns
    matches = list(_SINGLE_DATE.finditer(text))
    if not matches:
        return []

    # Find the year (usually at the end)
    year = year_fallback
    for m in matches:
        try:
            year = int(m.group(3))
        except ValueError:
            pass

    # For each match, create an event
    for m in matches:
        month_name = m.group(1).lower()
        if month_name not in MONTHS:
            continue
        month = MONTHS[month_name]
        day = int(m.group(2))
        try:
            dt = datetime(int(m.group(3)), month, day)
        except ValueError:
            continue
        offset = _eastern_offset(dt)
        start = f"{dt.strftime('%Y-%m-%dT')}00:00:00{offset}"
        results.append((start, None))

    # Also look for comma-separated days within a month:
    # "June 12, July 10, August 14, 2026" or "February 6, March 6, October 23, ..."
    # These are already handled by the regex above since each "Month Day" has its own match.

    return results


def fetch_special_events(site: dict) -> list[Event]:
    """Scrape the static HTML table at /special-events."""
    url = site.get("special_events_url", SPECIAL_EVENTS_URL)
    html_text = http.get(url)
    soup = BeautifulSoup(html_text, "html.parser")

    # Find the events table. It has columns: Event, Location, Date
    table = soup.find("table")
    if not table:
        return []

    events = []
    now = datetime.now(timezone.utc)
    year_fallback = now.year

    rows = table.find_all("tr")
    for row in rows[1:]:  # skip header
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        title = cells[0].get_text(strip=True)
        location = cells[1].get_text(strip=True)
        date_text = cells[2].get_text(strip=True)

        if not title or not date_text:
            continue

        dates = _parse_special_dates(date_text, year_fallback)
        if not dates:
            # If we could not parse individual dates, create one all-day event
            # with the raw date text in the description.
            events.append(Event(
                title=title,
                start=f"{year_fallback}-01-01T00:00:00-05:00",
                all_day=True,
                description=f"Date: {date_text}",
                url=url,
                venue=location,
                city="Washtenaw County",
                source=site["key"],
                source_name=site["name"],
            ))
            continue

        for start, end in dates:
            events.append(Event(
                title=title,
                start=start,
                end=end,
                all_day=True,
                description="",
                url=url,
                venue=location,
                city="Washtenaw County",
                source=site["key"],
                source_name=site["name"],
            ))

    return events


def fetch(site: dict) -> list[Event]:
    """Entry point called by generic.py. Pulls from both calendars."""
    all_events = []

    # Parks & Recreation Events (CivicPlus API)
    if site.get("calendar_page"):
        all_events.extend(fetch_parks_rec(site))

    # Special Events (HTML table)
    if site.get("special_events_url"):
        all_events.extend(fetch_special_events(site))

    return all_events
