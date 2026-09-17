"""LocalHop calendar API.

LocalHop (getlocalhop.com) is a Parse Server platform used by several Michigan
libraries including Saline District Library. The calendar widget ships a public
application ID and hits a REST API for event instances. This module makes the
same call, one GET per run, no browser needed.

The application ID is not a secret. It is embedded in every page that loads the
widget and is required by the Parse Server protocol for all requests, public or
authenticated. An empty session token (which is what the widget sends) returns
only the public read view.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import requests as req

from .. import http
from ..models import Event

API = "https://api.getlocalhop.com/1/classes/EventInstance"
APP_ID = "zesqKJEzK7ncFXe57x4uWc4Moow3I2wGCq7zFcqI"

HEADERS = {
    "X-Parse-Application-Id": APP_ID,
    "X-Parse-Session-Token": "",
    "Accept": "application/json",
    "User-Agent": http.USER_AGENT,
}

# Include enough related objects to avoid a second round trip.
INCLUDE = ",".join([
    "event",
    "event.eventCategories",
    "event.ticketingConfig",
    "event.ticketingConfig.ticketTypes",
    "event.organizationAgeGroups",
    "event.organizationAgeGroups.ageGroups",
    "event.organization",
])


def _eastern_offset(dt: datetime) -> str:
    """EDT or EST, the rough way. Good enough for event display."""
    return "-04:00" if 3 <= dt.month <= 11 else "-05:00"


def _parse_api_dt(iso_str: str) -> str:
    """Convert a UTC ISO timestamp from the API to an Eastern local string."""
    if not iso_str:
        return ""
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(cleaned)
        offset_hours = -4 if 3 <= dt_utc.month <= 11 else -5
        dt_local = dt_utc + timedelta(hours=offset_hours)
        return dt_local.strftime("%Y-%m-%dT%H:%M:%S") + _eastern_offset(dt_local)
    except (ValueError, TypeError):
        return ""


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


def _parse_event(instance: dict, site: dict) -> Event | None:
    """Turn one EventInstance result into an Event, or None if unusable."""
    ev = instance.get("event")
    if not isinstance(ev, dict):
        return None

    title = (ev.get("name") or "").strip()
    if not title:
        return None

    # actualStartDate/actualEndDate carry the timezone-aware times.
    start_raw = (instance.get("actualStartDate") or {}).get("iso", "")
    end_raw = (instance.get("actualEndDate") or {}).get("iso", "")
    start = _parse_api_dt(start_raw)
    if not start:
        return None
    end = _parse_api_dt(end_raw) or None

    all_day = bool(instance.get("allDay", False))

    # Location
    addr = ev.get("address") or {}
    venue = addr.get("place", "") if isinstance(addr, dict) else ""
    address_parts = []
    if isinstance(addr, dict):
        for key in ("address1", "city", "state", "postalCode"):
            val = addr.get(key, "")
            if val:
                address_parts.append(val)
    address = ", ".join(address_parts)
    city = addr.get("city", "") if isinstance(addr, dict) else ""

    geo = ev.get("addressLatLng") or {}
    lat = geo.get("latitude") if isinstance(geo, dict) else None
    lon = geo.get("longitude") if isinstance(geo, dict) else None
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None

    description = _strip_html(ev.get("description", ""))

    # Categories from the embedded eventCategories objects.
    cats = ev.get("eventCategories") or []
    categories = [
        c.get("name", "") for c in cats
        if isinstance(c, dict) and c.get("name")
    ]

    # Age groups
    age_groups = ev.get("organizationAgeGroups") or []
    audience_parts = []
    for ag in age_groups:
        if isinstance(ag, dict) and ag.get("name"):
            audience_parts.append(ag["name"])
    audience = ", ".join(audience_parts)

    # Cost from ticket types
    cost = "unknown"
    price = ""
    tc = ev.get("ticketingConfig") or {}
    if isinstance(tc, dict):
        for tt in (tc.get("ticketTypes") or []):
            if not isinstance(tt, dict):
                continue
            cents = tt.get("costInCents")
            if cents == 0:
                cost = "free"
                price = "Free"
            elif cents and int(cents) > 0:
                cost = "paid"
                price = f"${int(cents) / 100:.2f}"
            break

    registration = bool(tc.get("url")) if isinstance(tc, dict) else False

    # Build a detail URL from the event slug and object id.
    slug = ev.get("slug", "")
    obj_id = ev.get("objectId", "")
    url = ""
    if slug and obj_id:
        url = f"https://events.getlocalhop.com/{slug}/event/{obj_id}/"
    elif isinstance(tc, dict) and tc.get("url"):
        url = tc["url"]

    photo = ev.get("photo") or {}
    image = photo.get("url", "") if isinstance(photo, dict) else ""

    return Event(
        title=title,
        start=start,
        end=end,
        all_day=all_day,
        description=description,
        url=url,
        venue=venue,
        address=address,
        city=city,
        lat=lat,
        lon=lon,
        audience_raw=audience,
        cost=cost,
        price=price,
        registration=registration,
        categories=categories,
        image=image,
        source=site["key"],
        source_name=site["name"],
    )


def harvest(site: dict) -> list[Event]:
    """Fetch events from a LocalHop calendar via the Parse REST API."""
    org_id = site["organization_id"]
    days = site.get("days", 120)

    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(days=days)

    where = json.dumps({
        "type": {"$in": ["event", "class", "camp"]},
        "organization": {"$in": [{
            "__type": "Pointer",
            "className": "Organization",
            "objectId": org_id,
        }]},
        "standardStartDate": {
            "$gte": {"__type": "Date", "iso": now.strftime("%Y-%m-%dT00:00:00.000Z")},
            "$lte": {"__type": "Date", "iso": end_dt.strftime("%Y-%m-%dT23:59:59.999Z")},
        },
    }, separators=(",", ":"))

    response = req.get(
        API,
        params={
            "order": "standardStartDate",
            "limit": "501",
            "skip": "0",
            "include": INCLUDE,
            "where": where,
        },
        headers={**HEADERS, "User-Agent": http.USER_AGENT},
        timeout=http.TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    events = []
    for result in data.get("results", []):
        event = _parse_event(result, site)
        if event:
            events.append(event)
    return events
