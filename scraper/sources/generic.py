"""Generic harvester for every site that publishes standard event markup.

Three strategies, tried in this order per site:

  tribe   The Events Calendar REST API, the best case when a site has it
  jsonld  crawl a listing page for detail links, read schema.org Event blocks
  ical    parse an .ics feed directly
  rss     parse an RSS feed and fall back to the detail page for the specifics

Most modern event calendars emit schema.org JSON-LD (Simpleview, Squarespace,
The Events Calendar, Eventbrite embeds), which is why this one adapter covers
Destination Ann Arbor, the museums, the Metroparks, and the rest. Adding a new
site is a few lines in config/sources.yaml, not new code.
"""

from __future__ import annotations

import html as htmllib
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..models import Event


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _normalize_dt(value: str) -> str:
    """schema.org dates come in as date only or full ISO. Normalize both."""
    if not value:
        return ""
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        month = int(value[5:7])
        offset = "-04:00" if 3 <= month <= 11 else "-05:00"
        return f"{value}T00:00:00{offset}"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset
    return dt.isoformat()


def _text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("@value") or "")
    if isinstance(value, list):
        return ", ".join(_text(v) for v in value if v)
    return str(value or "")


def _location(node) -> tuple:
    loc = node.get("location")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return _text(loc), "", "", None, None

    name = _text(loc.get("name"))
    addr = loc.get("address")
    city = ""
    street = ""
    if isinstance(addr, dict):
        city = _text(addr.get("addressLocality"))
        street = ", ".join(
            p for p in [
                _text(addr.get("streetAddress")),
                city,
                _text(addr.get("addressRegion")),
                _text(addr.get("postalCode")),
            ] if p
        )
    elif addr:
        street = _text(addr)

    geo = loc.get("geo") or {}
    lat = geo.get("latitude") if isinstance(geo, dict) else None
    lon = geo.get("longitude") if isinstance(geo, dict) else None
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None

    return name, street, city, lat, lon


def _offers(node):
    offers = _as_list(node.get("offers"))
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price = offer.get("price")
        if price in (0, "0", "0.00"):
            return "free", "Free"
        if price:
            return "paid", f"${price}"
    return "unknown", ""


def iter_jsonld_events(html: str):
    """Yield every schema.org Event node found on a page, nesting included."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                stack.extend(v for v in node.values() if isinstance(v, (list, dict)))
                types = [str(t).lower() for t in _as_list(node.get("@type"))]
                if any("event" in t for t in types) and node.get("name"):
                    yield node


def event_from_jsonld(node: dict, site: dict, fallback_url: str = "") -> Event | None:
    start = _normalize_dt(_text(node.get("startDate")))
    if not start:
        return None

    venue, address, city, lat, lon = _location(node)
    cost, price = _offers(node)

    audience = ""
    aud = node.get("audience")
    if isinstance(aud, dict):
        audience = _text(aud.get("audienceType") or aud.get("name"))
    elif aud:
        audience = _text(aud)

    return Event(
        title=_text(node.get("name")).strip(),
        start=start,
        end=_normalize_dt(_text(node.get("endDate"))) or None,
        description=re.sub(r"\s+", " ", _text(node.get("description")))[:1500],
        url=_text(node.get("url")) or fallback_url,
        venue=venue,
        address=address,
        city=city,
        lat=lat,
        lon=lon,
        audience_raw=audience,
        cost=cost,
        price=price,
        image=_text(node.get("image")) if not isinstance(node.get("image"), dict)
        else _text(node.get("image", {}).get("url")),
        categories=[c for c in _as_list(node.get("keywords")) if isinstance(c, str)],
        source=site["key"],
        source_name=site["name"],
    )


def harvest_jsonld(site: dict) -> list:
    """Crawl the configured listing pages, then read each detail page."""
    detail_pattern = re.compile(site["detail_pattern"])
    links = set()
    events = []

    for listing in site.get("listings", []):
        try:
            html = http.get(listing)
        except http.FetchError:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(listing, a["href"])
            if detail_pattern.search(href):
                links.add(href.split("#")[0])
        # Some calendars put the whole list in JSON-LD on the listing page.
        # Take those directly and skip the detail fetch for them.
        for node in iter_jsonld_events(html):
            event = event_from_jsonld(node, site, listing)
            if event:
                events.append(event)
                links.discard(event.url)

    for url in sorted(links)[: site.get("max_details", 250)]:
        try:
            html = http.get(url)
        except http.FetchError:
            continue
        for node in iter_jsonld_events(html):
            event = event_from_jsonld(node, site, url)
            if event:
                events.append(event)
    return events


def parse_ics(text: str, site: dict) -> list:
    """Small iCal reader. Enough for VEVENT summary, dates, location, url."""
    events = []
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold continuation lines
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.DOTALL):
        fields = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            name = key.split(";")[0].upper()
            fields.setdefault(name, value.strip())
            if name in ("DTSTART", "DTEND"):
                fields[name + "_PARAMS"] = key

        start = _ics_dt(fields.get("DTSTART", ""), fields.get("DTSTART_PARAMS", ""))
        if not start or not fields.get("SUMMARY"):
            continue

        events.append(
            Event(
                title=_ics_unescape(fields["SUMMARY"]),
                start=start,
                end=_ics_dt(fields.get("DTEND", ""), fields.get("DTEND_PARAMS", "")) or None,
                all_day="VALUE=DATE" in fields.get("DTSTART_PARAMS", ""),
                description=_ics_unescape(fields.get("DESCRIPTION", ""))[:1500],
                url=fields.get("URL", "") or site.get("url", ""),
                venue=_ics_unescape(fields.get("LOCATION", "")),
                categories=[c for c in _ics_unescape(fields.get("CATEGORIES", "")).split(",") if c],
                source=site["key"],
                source_name=site["name"],
            )
        )
    return events


def _ics_unescape(value: str) -> str:
    return (
        value.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    ).strip()


def _ics_dt(value: str, params: str) -> str:
    if not value:
        return ""
    value = value.strip()
    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
        if "T" in value:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        else:
            dt = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return ""
    offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset


def harvest_ical(site: dict) -> list:
    events = []
    for url in site.get("feeds", []):
        try:
            events.extend(parse_ics(http.get(url), site))
        except http.FetchError:
            continue
    return events


def harvest_rss(site: dict) -> list:
    """RSS gives titles and links. Detail pages give everything else."""
    links = set()
    for url in site.get("feeds", []):
        try:
            xml = http.get(url)
        except http.FetchError:
            continue
        for link in re.findall(r"<link>(.*?)</link>", xml, re.DOTALL):
            link = link.strip()
            if re.search(site["detail_pattern"], link):
                links.add(link)

    events = []
    for url in sorted(links)[: site.get("max_details", 250)]:
        try:
            html = http.get(url)
        except http.FetchError:
            continue
        for node in iter_jsonld_events(html):
            event = event_from_jsonld(node, site, url)
            if event:
                events.append(event)
    return events


def harvest_tribe(site: dict) -> list:
    """The Events Calendar (WordPress) ships a REST API at
    /wp-json/tribe/events/v1/events with dates, venue, geo, cost and
    categories already structured. Always prefer this over scraping.
    """
    base = site["base"].rstrip("/")
    start = datetime.now().date()
    end = start + timedelta(days=site.get("days", 120))
    per_page = 50
    events = []

    for page in range(1, site.get("max_pages", 12) + 1):
        url = (f"{base}/wp-json/tribe/events/v1/events"
               f"?start_date={start}&end_date={end}&per_page={per_page}&page={page}")
        try:
            payload = json.loads(http.get(url))
        except Exception:  # noqa: BLE001
            break

        batch = payload.get("events") or []
        if not batch:
            break

        for row in batch:
            event = event_from_tribe(row, site)
            if event:
                events.append(event)

        if page >= int(payload.get("total_pages") or 1):
            break

    return events


def event_from_tribe(row: dict, site: dict) -> Event | None:
    title = _strip_tags(row.get("title", ""))
    start = _tribe_dt(row.get("start_date", ""))
    if not title or not start:
        return None

    venue = row.get("venue") or {}
    lat = lon = None
    try:
        if venue.get("geo_lat") not in (None, ""):
            lat = float(venue["geo_lat"])
            lon = float(venue["geo_lng"])
    except (TypeError, ValueError):
        lat = lon = None

    address = ", ".join(str(p) for p in [
        venue.get("address"), venue.get("city"), venue.get("state"), venue.get("zip")
    ] if p)

    cost_text = _strip_tags(row.get("cost", ""))
    cost = "unknown"
    if cost_text:
        cost = "free" if re.search(r"free", cost_text, re.IGNORECASE) else "paid"

    categories = [c.get("name", "") for c in (row.get("categories") or []) if isinstance(c, dict)]
    categories += [t.get("name", "") for t in (row.get("tags") or []) if isinstance(t, dict)]

    return Event(
        title=title,
        start=start,
        end=_tribe_dt(row.get("end_date", "")) or None,
        all_day=bool(row.get("all_day")),
        description=_strip_tags(row.get("description") or row.get("excerpt") or "")[:1500],
        url=row.get("url", ""),
        venue=_strip_tags(venue.get("venue", "")),
        address=address,
        city=_strip_tags(venue.get("city", "")),
        lat=lat,
        lon=lon,
        cost=cost,
        price=cost_text,
        image=(row.get("image") or {}).get("url", "") if isinstance(row.get("image"), dict) else "",
        categories=[c for c in categories if c],
        source=site["key"],
        source_name=site["name"],
    )


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = htmllib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _tribe_dt(value: str) -> str:
    """Their dates come as "2026-09-04 16:30:00", local to the site."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        dt = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset


def harvest_canva(site: dict) -> list:
    from . import canva

    return canva.harvest(site)


def harvest_trumba(site: dict) -> list:
    # Imported here rather than at the top because trumba imports parse_ics
    # from this module, and a top level import would be circular.
    from . import trumba

    return trumba.harvest(site)


STRATEGIES = {
    "tribe": harvest_tribe,
    "jsonld": harvest_jsonld,
    "ical": harvest_ical,
    "rss": harvest_rss,
    "trumba": harvest_trumba,
    "canva": harvest_canva,
}


def fetch(site: dict) -> list:
    handler = STRATEGIES.get(site.get("strategy", "jsonld"))
    if handler is None:
        return []
    return handler(site)
