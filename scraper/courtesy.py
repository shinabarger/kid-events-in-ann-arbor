"""The rules that keep this a pointer to other people's listings, not a copy of them.

Facts are not anybody's property. The date of a storytime, the address of the
library, the fact that it is free, all of that is fact. The paragraph somebody
wrote to describe it is theirs. So we keep enough of the paragraph to tell you
whether to go, and then we send you to them to read the rest.

Three rules, applied to every event before it is written out:

1. Descriptions are trimmed to a short excerpt at a sentence boundary.
2. Images are not copied or hotlinked at all.
3. Anything an organizer has asked us to drop is dropped.
"""

from __future__ import annotations

import os
import re

import yaml

# Long enough to be useful on a card, short enough that nobody would read this
# instead of the original. The site clamps to two lines anyway.
EXCERPT_LIMIT = int(os.environ.get("EXCERPT_LIMIT", "280"))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTOUT_FILE = os.path.join(_ROOT, "config", "optout.yaml")


def excerpt(text: str, limit: int = EXCERPT_LIMIT) -> str:
    """Trim to a whole sentence under the limit, or a whole word if there is no
    sentence break to use. Never mid-word."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text

    window = text[: limit + 1]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut > limit * 0.4:
        return window[: cut + 1].strip()

    cut = window.rfind(" ")
    return (window[:cut] if cut > 0 else window[:limit]).rstrip(" ,;:-") + "..."


def load_optout(path: str = OPTOUT_FILE) -> dict:
    """Organizers and sites that asked to be left out. Read fresh every run so
    taking somebody out is a one line edit and a push, not a code change."""
    empty = {"sources": set(), "venues": set(), "domains": set(), "titles": []}
    if not os.path.exists(path):
        return empty
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return {
        "sources": {s.strip().lower() for s in (raw.get("sources") or []) if s},
        "venues": {v.strip().lower() for v in (raw.get("venues") or []) if v},
        "domains": {d.strip().lower().lstrip(".") for d in (raw.get("domains") or []) if d},
        "titles": [re.compile(p, re.I) for p in (raw.get("titles") or [])],
    }


def _host(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url or "", re.I)
    if not match:
        return ""
    host = match.group(1).lower()
    return host[4:] if host.startswith("www.") else host


def is_opted_out(event, rules: dict) -> bool:
    if (getattr(event, "source", "") or "").lower() in rules["sources"]:
        return True
    if (getattr(event, "venue", "") or "").strip().lower() in rules["venues"]:
        return True
    host = _host(getattr(event, "url", ""))
    if host and any(host == d or host.endswith("." + d) for d in rules["domains"]):
        return True
    title = getattr(event, "title", "") or ""
    return any(pattern.search(title) for pattern in rules["titles"])


def apply(events: list, rules: dict | None = None) -> list:
    """Drop opted-out listings, trim descriptions, and strip images."""
    rules = load_optout() if rules is None else rules
    kept = []
    for event in events:
        if is_opted_out(event, rules):
            continue
        event.description = excerpt(event.description)
        event.image = ""
        kept.append(event)
    return kept
