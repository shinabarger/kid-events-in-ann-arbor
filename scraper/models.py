"""Event record + the vocabularies the site filters on."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# Age bands. An event lands in a band when its age range overlaps the band's
# range. Ranges deliberately overlap (a 3 year old is both toddler and
# preschool depending on who is running the program).
AGE_BANDS = {
    "baby": (0, 2),
    "toddler": (1, 3),
    "preschool": (3, 5),
    "elementary": (5, 10),
    "tween": (10, 13),
    "teen": (13, 18),
}

AGE_BAND_LABELS = {
    "baby": "Babies (0-2)",
    "toddler": "Toddlers (1-3)",
    "preschool": "Preschool (3-5)",
    "elementary": "Elementary (5-10)",
    "tween": "Tweens (10-13)",
    "teen": "Teens (13-18)",
}

ZONES = ("city", "near", "county", "outside")
ZONE_LABELS = {
    "city": "Ann Arbor city limits",
    "near": "Within a 30 minute drive",
    "county": "Washtenaw County",
    "outside": "Farther out",
}

SETTINGS = ("indoor", "outdoor", "both", "unknown")
COSTS = ("free", "paid", "unknown")


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return value[:80]


@dataclass
class Event:
    title: str
    start: str                      # ISO 8601 with offset
    source: str                     # short source key, e.g. "aadl"
    source_name: str = ""
    end: Optional[str] = None
    all_day: bool = False
    recurring: bool = False
    repeat_count: int = 0
    description: str = ""
    url: str = ""
    venue: str = ""
    address: str = ""
    city: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    zone: str = "outside"
    washtenaw: bool = False
    # Plausibly reachable in an hour on TheRide. See geo.reachable_by_bus.
    bus: bool = False
    drive_minutes: Optional[int] = None
    audience_raw: str = ""
    ages: list = field(default_factory=list)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    all_ages: bool = False
    setting: str = "unknown"
    cost: str = "unknown"
    price: str = ""
    registration: bool = False
    categories: list = field(default_factory=list)
    also_seen_on: list = field(default_factory=list)
    image: str = ""
    updated: str = ""

    # True when the listing is a volunteer shift rather than something to
    # turn up to with a child. The city files both on the same calendar.
    volunteer: bool = False

    # Set by kidfilter when an event from a general calendar is turned away.
    # Never written to the page, only to the run log, so I can see what a noisy
    # source is costing before I decide whether to keep it.
    drop_reason: str = ""

    @property
    def id(self) -> str:
        """Stable id so the same event keeps its identity between runs."""
        day = (self.start or "")[:10]
        seed = f"{self.source}|{slugify(self.title)}|{day}|{slugify(self.venue)}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]

    @property
    def start_dt(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self.start)
        except (TypeError, ValueError):
            return None

    def completeness(self) -> int:
        """Rough score for how much this record actually tells you.

        Used when two sources publish the same event and we keep one.
        """
        score = 0
        score += min(len(self.description or ""), 600) // 60
        if self.end:
            score += 2
        if self.venue:
            score += 3
        if self.address:
            score += 2
        if self.lat is not None:
            score += 1
        if self.audience_raw:
            score += 3
        if self.ages:
            score += 2
        if self.cost != "unknown":
            score += 2
        if self.setting != "unknown":
            score += 1
        if self.image:
            score += 1
        if self.url:
            score += 1
        return score

    # Internal bookkeeping that has no business on a public page.
    PRIVATE_FIELDS = ("drop_reason", "volunteer")

    def to_dict(self) -> dict:
        data = asdict(self)
        for name in self.PRIVATE_FIELDS:
            data.pop(name, None)
        data["id"] = self.id
        return data
