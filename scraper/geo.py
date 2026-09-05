"""Turn a free text venue string into a city, coordinates, and a drive time.

Everything the location filter does hangs off this. The lookup table lives in
config/venues.yaml so I can add a venue without touching code.
"""

from __future__ import annotations

import math
import os
import re
from functools import lru_cache

import yaml

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")

# Rough box around the City of Ann Arbor. Good enough to separate "in the city"
# from "has an Ann Arbor mailing address but is really out in the township".
CITY_BOX = {"lat_min": 42.2270, "lat_max": 42.3330, "lon_min": -83.8180, "lon_max": -83.6700}

NEAR_LIMIT_MINUTES = 30


@lru_cache(maxsize=1)
def load_venues() -> dict:
    with open(os.path.join(CONFIG_DIR, "venues.yaml"), "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def estimate_drive_minutes(lat: float, lon: float) -> int:
    """Straight line distance padded out to something drive-like.

    Local roads average well under the posted limit once you count lights, so
    the short trips get a slower effective speed than the highway runs.
    """
    origin = load_venues()["origin"]
    miles = haversine_miles(origin["lat"], origin["lon"], lat, lon)
    road_miles = miles * 1.25  # roads are not straight lines
    speed = 22 if road_miles < 4 else (30 if road_miles < 12 else 42)
    return int(round(4 + (road_miles / speed) * 60))


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def match_venue(*texts: str) -> dict | None:
    """Find the first configured venue whose match strings appear in the text."""
    haystack = _norm(" | ".join(t for t in texts if t))
    if not haystack:
        return None
    for venue in load_venues()["venues"]:
        for needle in venue.get("match", []):
            if needle in haystack:
                return venue
    return None


def city_from_text(*texts: str) -> str:
    haystack = _norm(" | ".join(t for t in texts if t))
    for city in load_venues()["washtenaw_cities"]:
        if re.search(r"\b" + re.escape(city) + r"\b", haystack):
            return city.title()
    return ""


def in_city_limits(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    b = CITY_BOX
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


def is_washtenaw(city: str) -> bool:
    c = _norm(city)
    if not c:
        return False
    return any(c == w or c.startswith(w) for w in load_venues()["washtenaw_cities"])


def locate(event) -> None:
    """Fill in city, coordinates, drive time, and zone on an event, in place."""
    venue = match_venue(event.venue, event.address, event.title)
    if venue:
        event.city = event.city or venue.get("city", "")
        event.address = event.address or venue.get("address", "")
        if event.lat is None:
            event.lat = venue.get("lat")
            event.lon = venue.get("lon")
        if event.drive_minutes is None:
            event.drive_minutes = venue.get("drive_minutes")
        if event.setting == "unknown" and venue.get("setting"):
            event.setting = venue["setting"]

    if not event.city:
        event.city = city_from_text(event.venue, event.address)

    if event.drive_minutes is None and event.lat is not None:
        event.drive_minutes = estimate_drive_minutes(event.lat, event.lon)

    event.washtenaw = is_washtenaw(event.city)
    event.zone = classify_zone(event)


def classify_zone(event) -> str:
    if in_city_limits(event.lat, event.lon) and _norm(event.city) in ("", "ann arbor"):
        return "city"
    if _norm(event.city) == "ann arbor" and event.lat is None:
        return "city"
    if event.drive_minutes is not None and event.drive_minutes <= NEAR_LIMIT_MINUTES:
        return "near"
    if is_washtenaw(event.city):
        return "county"
    return "outside"


def matches_zone_filter(event, wanted: str) -> bool:
    """How the location dropdown on the site is meant to behave.

    city      -> inside the Ann Arbor city limits only
    near      -> anything roughly 30 minutes or less from downtown
    county    -> anywhere in Washtenaw County, however long the drive
    bus       -> plausibly reachable in an hour on TheRide
    anywhere  -> no filter
    """
    if wanted in ("", "anywhere", "all"):
        return True
    if wanted == "city":
        return event.zone == "city"
    if wanted == "near":
        return event.zone in ("city", "near")
    if wanted == "bus":
        return reachable_by_bus(event)
    if wanted == "county":
        return bool(event.washtenaw)
    return True


# --- getting there without a car ----------------------------------------

# TheRide is the bus system for Ann Arbor and Ypsilanti. An hour door to door
# is roughly one ride plus one transfer plus the walk at each end, which in
# practice means the two cities and the built up townships between them.
#
# Deliberately coarse, and honest about it. Working out a real trip needs the
# live GTFS feed, the time of day, and which stop you are starting from, none
# of which this site knows. So the filter answers "is this plausibly reachable
# by bus" and the page says to check theride.org for the actual trip.
# Two tiers, because the difference is real. Route 4 runs between downtown
# Ann Arbor and downtown Ypsilanti every fifteen minutes all day, so anything
# in either city is a bus ride. The surrounding townships have service, but it
# is partial, so out there the drive time still has to be short.
CORE_TRANSIT_CITIES = {"ann arbor", "ypsilanti"}

EDGE_TRANSIT_CITIES = {
    "ypsilanti township",
    "ypsilanti twp",
    "pittsfield",
    "pittsfield township",
    "superior township",
    "ann arbor township",
    "scio township",
}

TRANSIT_CITIES = CORE_TRANSIT_CITIES | EDGE_TRANSIT_CITIES

# Places inside those cities that the buses do not usefully reach: no route
# within a reasonable walk, or an hourly peak-only service.
TRANSIT_GAPS = [
    "airport",
    "delhi",
    "dexter-huron",
    "hudson mills",
    "independence lake",
    "north bay",
]


def reachable_by_bus(event) -> bool:
    """Plausibly an hour or less on TheRide, walk included."""
    city = (getattr(event, "city", "") or "").strip().lower()
    if city and city not in TRANSIT_CITIES:
        return False

    haystack = " ".join(
        str(getattr(event, f, "") or "").lower() for f in ("venue", "address")
    )
    if any(gap in haystack for gap in TRANSIT_GAPS):
        return False

    # A venue file entry always wins over everything below it.
    override = _transit_override(event)
    if override is not None:
        return override

    # The two cities the buses genuinely cover, end to end.
    if city in CORE_TRANSIT_CITIES or getattr(event, "zone", "") == "city":
        return True

    # Everywhere else, only when the drive is short enough that a bus could
    # plausibly do it inside an hour. Twenty minutes of driving is about an
    # hour of bus once you count the walk at both ends and one transfer.
    minutes = getattr(event, "drive_minutes", None)
    return minutes is not None and minutes <= 20


def _transit_override(event):
    """A `bus: true` or `bus: false` line in venues.yaml beats the guess."""
    name = (getattr(event, "venue", "") or "").strip().lower()
    if not name:
        return None
    for row in load_venues().get("venues", []) or []:
        if not isinstance(row, dict) or "bus" not in row:
            continue
        names = [row.get("name", "")] + list(row.get("match", []) or [])
        if any(n and n.strip().lower() in name for n in names):
            return bool(row["bus"])
    return None
