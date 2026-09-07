"""Venues that have to say who the event is for.

A bookshop runs fifty author talks and two storytimes. Ann Arbor with Kids
republishes the whole calendar and tags every entry with kid age bands, so by
the time dedupe has merged that copy into the one that wins, an adult author
talk is carrying age_min=0 and sails through kidfilter on "stated ages from 0".

That is how "Martin Sorge: Great Bakes", a baking book launch at 6:30pm, ended
up on a calendar for the under-threes.

So for a short list of venues, borrowed metadata is not enough. The event has
to say it in its own words.
"""

from __future__ import annotations

import os
import re

import yaml

from . import kidfilter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_ROOT, "config", "venue-gates.yaml")

# What counts as saying so. kidfilter's own strong list, plus the words a
# venue uses when it is putting on something for older children.
EXTRA = [
    r"\bteens?\b", r"\btweens?\b", r"\bfamily[- ]friendly\b",
    r"\bfor families\b", r"\ball[- ]ages\b", r"\bpicture books?\b",
    r"\bmiddle grade\b", r"\bya\b", r"\byoung adult\b",
    r"\bboard books?\b", r"\bearly readers?\b",
]

SIGNALS = [re.compile(p, re.I) for p in kidfilter.STRONG + EXTRA]


def load_venues(path: str = PATH) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return [v.strip() for v in (raw.get("venues") or []) if v and v.strip()]


def _matcher(name: str):
    # On word boundaries, so "The Ark" does not gate an event in Clark Park.
    return re.compile(r"\b" + re.escape(name.strip()) + r"\b", re.I)


def is_gated(event, venues: list) -> bool:
    place = " ".join(filter(None, [
        getattr(event, "venue", ""), getattr(event, "address", "")]))
    return any(_matcher(name).search(place) for name in venues)


def says_so(event) -> bool:
    """Only the event's own words. Age tags are exactly what we do not trust."""
    text = " ".join(filter(None, [
        getattr(event, "title", ""), getattr(event, "description", "")]))
    return any(rx.search(text) for rx in SIGNALS)


def apply(events: list, venues: list | None = None) -> tuple:
    """Returns (kept, dropped)."""
    venues = load_venues() if venues is None else venues
    if not venues:
        return list(events), []

    kept, dropped = [], []
    for event in events:
        if is_gated(event, venues) and not says_so(event):
            event.drop_reason = "venue programs for adults and this one never says otherwise"
            dropped.append(event)
        else:
            kept.append(event)
    return kept, dropped
