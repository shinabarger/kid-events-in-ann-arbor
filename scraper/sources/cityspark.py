"""Ann Arbor Family calendar via the CitySpark events API.

CitySpark powers the calendar at annarborfamily.com/Calendar. The API is
public, unauthenticated, and documented at:
    https://portal.cityspark.com/api/events/GetEvents/AnnArborFamily

It is a general community calendar. EMU football, Friday Night Euchre, and
brewery tours sit alongside story times and family festivals, so every event
from this source goes through kidfilter.py.

The API returns 25 events per page. Pagination works via the `skip` parameter.
"""

from __future__ import annotations

import html as htmllib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from ..models import Event

SOURCE = "cityspark_a2family"
SOURCE_NAME = "Ann Arbor Family"

API_URL = "https://portal.cityspark.com/api/events/GetEvents/AnnArborFamily"
PPID = 8349
PAGE_SIZE = 25
MAX_PAGES = 20  # 500 events max, plenty for a 120 day horizon

# Ann Arbor center. The API uses this for distance filtering.
LAT = 42.2821006774902
LNG = -83.7484664916992
DISTANCE_MILES = 50

TIMEOUT = int(os.environ.get("SCRAPE_TIMEOUT", "30"))
DELAY = float(os.environ.get("SCRAPE_DELAY", "0.4"))

# Reuse the project's contact header so site operators know who we are.
CONTACT = os.environ.get(
    "SCRAPE_CONTACT",
    "https://github.com/shinabarger/kid-events-in-ann-arbor/issues",
)
USER_AGENT = (
    f"kid-events-in-ann-arbor/1.0 (+{CONTACT}) "
    "non-commercial family events aggregator, one pass per day"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

_last_call = {"t": 0.0}


def _post_json(body: dict) -> dict:
    """POST to the CitySpark API with politeness delay and retries."""
    for attempt in range(3):
        gap = time.time() - _last_call["t"]
        if gap < DELAY:
            time.sleep(DELAY - gap)
        try:
            resp = requests.post(
                API_URL, headers=HEADERS, json=body, timeout=TIMEOUT,
            )
            _last_call["t"] = time.time()
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    text = htmllib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_dt(iso_str: str) -> str:
    """Turn the API's ISO datetime into our offset-aware format.

    Despite the trailing Z, the CitySpark API returns local Eastern times,
    not UTC. An AADL storytime at 10:30am Eastern comes back as
    "2026-09-10T10:30:00Z". Treating that as real UTC shifts every event
    four hours into the pre-dawn. So strip the Z and stamp the Eastern
    offset directly.
    """
    if not iso_str:
        return ""
    iso_str = iso_str.strip()

    # Already has a real offset like -04:00 -> keep it
    if iso_str[-1] != "Z" and ("+" in iso_str[10:] or iso_str[10:].count("-") > 1):
        try:
            dt = datetime.fromisoformat(iso_str)
            offset_str = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset_str
        except (ValueError, TypeError):
            return ""

    # Strip the fake Z and treat the time as Eastern
    bare = iso_str.rstrip("Z")
    try:
        dt = datetime.fromisoformat(bare)
    except (ValueError, TypeError):
        return ""
    offset_str = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset_str


def _event_url(row: dict) -> str:
    """Build the full event URL from the event's PId.

    The API does not return a Url field. The calendar site uses hash routing,
    so the link to an individual event is #!/event/<PId>.
    """
    path = row.get("Url") or ""
    if path and path.startswith("http"):
        return path
    if path and not path.startswith("http"):
        return f"https://annarborfamily.com{path}"
    pid = row.get("PId")
    if pid:
        return f"https://annarborfamily.com/Calendar/#!/event/{pid}"
    return ""


def event_from_row(row: dict) -> Event | None:
    """Map one CitySpark API record to our Event model."""
    title = (row.get("Name") or "").strip()
    start = _normalize_dt(row.get("DateStart") or "")
    if not title or not start:
        return None

    end = _normalize_dt(row.get("DateEnd") or "") or None
    all_day = bool(row.get("AllDay"))

    # If the event claims to have no specific time, mark it all-day
    if not row.get("HasTime"):
        all_day = True
        end = None

    description = _strip_html(row.get("Description") or "")[:1500]
    summary = (row.get("Summary") or "").strip()
    # Use summary as the description if the full description is empty
    if not description and summary:
        description = summary

    venue = (row.get("Venue") or "").strip()
    city_state = (row.get("CityState") or "").strip()
    address_parts = [row.get("Address") or "", city_state, row.get("Zip") or ""]
    address = ", ".join(p.strip() for p in address_parts if p.strip())
    city = city_state.split(",")[0].strip() if city_state else ""

    lat = row.get("latitude")
    lon = row.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None

    # Cost
    cost = "unknown"
    price = str(row.get("Price") or "").strip()
    if row.get("Free"):
        cost = "free"
        price = price or "Free"
    elif price and price.lower() != "free":
        cost = "paid"

    # Build the audience string from the description + summary for classify
    audience_raw = summary if summary else ""

    # Contact info can sometimes carry the organizer name
    ct = row.get("ct") or {}
    org = (ct.get("org") or "").strip()

    image = (row.get("MediumImg") or row.get("SmallImg") or "").strip()

    return Event(
        title=title,
        start=start,
        end=end,
        all_day=all_day,
        description=description,
        url=_event_url(row),
        venue=venue,
        address=address,
        city=city,
        lat=lat,
        lon=lon,
        audience_raw=audience_raw,
        cost=cost,
        price=price,
        image=image,
        source=SOURCE,
        source_name=SOURCE_NAME,
    )


def fetch(days: int = 120) -> list:
    """Pull events from the CitySpark API, paginating through all results."""
    start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end_date = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")
    events = []
    seen_ids = set()

    for page in range(MAX_PAGES):
        skip = page * PAGE_SIZE
        body = {
            "ppid": PPID,
            "start": start_date,
            "end": end_date,
            "labels": [],
            "pick": False,
            "tps": None,
            "sparks": False,
            "sort": "Time",
            "category": [],
            "distance": DISTANCE_MILES,
            "lat": LAT,
            "lng": LNG,
            "search": "",
            "skip": skip,
            "defFilter": "all",
        }

        data = _post_json(body)
        rows = data.get("Value") or []
        if not rows:
            break

        for row in rows:
            event = event_from_row(row)
            if event and event.id not in seen_ids:
                seen_ids.add(event.id)
                events.append(event)

            # Stop if we have gone past our end date
            ds = row.get("DateStart") or ""
            if ds and ds[:10] > end_date:
                return events

        if len(rows) < PAGE_SIZE:
            break

    return events
