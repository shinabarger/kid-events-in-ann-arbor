"""Hand added events.

This is the escape hatch for anything with no feed: Facebook group posts,
a flyer at the library, a school newsletter. Add it to config/manual_events.yaml
or open a "Add an event" issue on the repo and the next run picks it up.

Manual entries win every dedupe tie, so this is also how to correct a listing
a source got wrong.
"""

from __future__ import annotations

import os

import yaml

from ..models import Event

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
PATH = os.path.join(CONFIG_DIR, "manual_events.yaml")

SOURCE = "manual"
SOURCE_NAME = "Added by hand"


def fetch(path: str = PATH) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}

    events = []
    for row in payload.get("events", []) or []:
        if not row.get("title") or not row.get("start"):
            continue
        events.append(
            Event(
                title=row["title"],
                start=row["start"],
                end=row.get("end"),
                all_day=bool(row.get("all_day")),
                description=row.get("description", ""),
                url=row.get("url", ""),
                venue=row.get("venue", ""),
                address=row.get("address", ""),
                city=row.get("city", ""),
                lat=row.get("lat"),
                lon=row.get("lon"),
                audience_raw=row.get("ages_text", ""),
                setting=row.get("setting", "unknown"),
                cost=row.get("cost", "unknown"),
                price=row.get("price", ""),
                registration=bool(row.get("registration")),
                categories=row.get("categories", []) or [],
                source=SOURCE,
                source_name=row.get("source_name") or SOURCE_NAME,
            )
        )
    return events
