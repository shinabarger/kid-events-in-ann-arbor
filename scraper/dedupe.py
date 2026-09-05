"""Collapse the same event showing up on three different sites.

Ann Arbor with Kids republishes a lot of AADL programming, Destination Ann
Arbor republishes the festivals, and the Observer republishes both. The rule
is: same day, same start hour, and a close enough title means one event, and
the copy that tells you the most wins.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

TITLE_NOISE = re.compile(
    r"\b(free|family|kids?|children'?s?|all ages|drop[- ]in|weekly|annual|"
    r"presented by|the|a|an|at|in|of|and|with|for)\b"
)

# When two records tie on quality, prefer the source closest to the organizer.
SOURCE_PRIORITY = {
    "manual": 0,
    "mamas_network": 1,          # their own page, scraped
    "mamas_network_repeat": 8,   # a projection, so it loses to the real thing
    "aadl": 1,
    "a2observer_kids": 1,
    "umich": 2,
    "discover_science": 2,
    "metroparks": 2,
    "ypsi_library": 2,
    "reced": 2,
    "a2_parks_rec": 2,
    "chelsea_library": 2,
    "saline_library": 2,
    "dexter_library": 2,
    "washtenaw_parks": 3,
    "a2sf": 3,
    "destination_a2": 4,
    "a2observer": 5,
    "aawk": 6,
    "a2family": 7,
}


def normalize_title(title: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower())
    text = TITLE_NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.95
    return SequenceMatcher(None, a, b).ratio()


def bucket_key(event) -> str:
    """Events only get compared inside the same day and hour."""
    start = event.start or ""
    return f"{start[:10]}|{start[11:13]}"


def merge(keep, drop):
    """Fold anything the loser knows that the winner does not into the winner."""
    for field in (
        "description", "venue", "address", "city", "audience_raw", "image",
        "price", "end",
    ):
        if not getattr(keep, field, None) and getattr(drop, field, None):
            setattr(keep, field, getattr(drop, field))

    if keep.lat is None and drop.lat is not None:
        keep.lat, keep.lon = drop.lat, drop.lon
    if keep.cost == "unknown" and drop.cost != "unknown":
        keep.cost, keep.price = drop.cost, drop.price or keep.price
    if keep.setting == "unknown" and drop.setting != "unknown":
        keep.setting = drop.setting
    if not keep.ages and drop.ages:
        keep.ages = drop.ages
        keep.age_min, keep.age_max, keep.all_ages = drop.age_min, drop.age_max, drop.all_ages
    keep.registration = keep.registration or drop.registration

    for category in drop.categories:
        if category not in keep.categories:
            keep.categories.append(category)

    seen_sources = set(keep.also_seen_on or [])
    seen_sources.add(drop.source_name or drop.source)
    keep.also_seen_on = sorted(s for s in seen_sources if s and s != keep.source_name)
    return keep


def rank(event) -> tuple:
    """Higher is better. Completeness first, then how close to the organizer."""
    return (event.completeness(), -SOURCE_PRIORITY.get(event.source, 9))


def dedupe(events: list, threshold: float = 0.82) -> list:
    buckets = {}
    for event in events:
        buckets.setdefault(bucket_key(event), []).append(event)

    kept = []
    for group in buckets.values():
        group.sort(key=rank, reverse=True)
        winners = []
        for candidate in group:
            name = normalize_title(candidate.title)
            match = None
            for winner in winners:
                if similar(name, normalize_title(winner.title)) >= threshold:
                    match = winner
                    break
            if match is not None:
                merge(match, candidate)
            else:
                winners.append(candidate)
        kept.extend(winners)

    kept.sort(key=lambda e: (e.start or "", e.title))
    return kept
