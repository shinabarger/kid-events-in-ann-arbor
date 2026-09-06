"""Build the seed dataset so a fresh clone shows a real looking calendar.

Reads config/snapshot/seed.json, which is a snapshot of what the sources were
actually publishing on the day it was captured. Day offsets rather than fixed
dates, so it always lands on today and never rots into the past.

The daily Action overwrites data/events.json with live data on its first
run. This is only the starting state, and a way to work on the CSS offline.

    python scripts/build_sample.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import (classify, courtesy, geo, icsbuild, kidfilter,  # noqa: E402
                     notevents, seo)
from scraper.dedupe import dedupe  # noqa: E402
from scraper.sources import canva, recurring  # noqa: E402
from scraper.models import AGE_BANDS, AGE_BAND_LABELS, ZONE_LABELS, Event  # noqa: E402
from scraper.run import (HORIZON_DAYS, defer_projections,  # noqa: E402
                        drop_listing_links, load_sites, mark_recurring,
                        mixed_sources)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = ROOT
SEED = os.path.join(ROOT, "config", "snapshot", "seed.json")

SOURCE_NAMES = {
    "aadl": "Ann Arbor District Library",
    "aawk": "Ann Arbor with Kids",
    "a2observer_kids": "Ann Arbor Observer Kids Calendar",
    "umich": "U-M Happening",
    "discover_science": "Hands-On Museum & Leslie Science",
    "metroparks": "Huron-Clinton Metroparks",
    "washtenaw_parks": "Washtenaw County Parks",
    "a2_parks": "Ann Arbor Parks & Rec",
    "reced": "Ann Arbor Rec & Ed",
}

# Deliberately no per-source fallback URL. A link that lands on a calendar
# index makes someone click twice and then hunt for the row they already had,
# so a row with no specific page of its own simply gets no link.


# The site renders in Eastern. Building the seed against the container's UTC
# clock puts every "day 0" event on tomorrow between 8pm and midnight Eastern,
# which makes the page open on an empty "today". Always build in local time.
EASTERN = ZoneInfo("America/Detroit")


def today() -> datetime:
    return datetime.now(EASTERN).replace(tzinfo=None)


def stamp(day: str, clock: str | None) -> str:
    """The date the source actually said, not one shifted to look current.

    This used to store day offsets and re-stamp them against whatever day the
    build ran, so the sample always looked fresh. It also meant every date was
    wrong by however long it had been since the snapshot: a Saturday cider
    mill event showed up on Sunday, then Monday. On a calendar people plan
    around, that is the worst possible failure, so the snapshot now carries
    real dates and goes stale visibly instead.
    """
    hour, minute = (0, 0)
    if clock:
        hour, minute = (int(p) for p in clock.split(":"))
    when = datetime.fromisoformat(day).replace(hour=hour, minute=minute)
    offset = "-04:00" if 3 <= when.month <= 11 else "-05:00"
    return when.strftime("%Y-%m-%dT%H:%M:%S") + offset


def to_event(row: dict) -> Event:
    times = (row.get("t") or "").split("-")
    start_clock = times[0] if times[0] else None
    end_clock = times[1] if len(times) > 1 and times[1] else None

    return Event(
        title=row["title"],
        start=stamp(row["d"], start_clock),
        end=stamp(row["d"], end_clock) if end_clock else None,
        all_day=bool(row.get("allday")),
        description=row.get("desc", ""),
        url=row.get("url", ""),
        venue=row.get("venue", ""),
        city=row.get("city", ""),
        lat=row.get("lat"),
        lon=row.get("lon"),
        audience_raw=row.get("ages", ""),
        setting=row.get("set", "unknown"),
        cost=row.get("cost", "unknown"),
        price=row.get("price", "Free" if row.get("cost") == "free" else ""),
        registration=bool(row.get("reg")),
        source=row["src"],
        source_name=SOURCE_NAMES.get(row["src"], row["src"]),
    )


MAMAS_FIXTURE = os.path.join(ROOT, "tests", "fixtures",
                             "mamas_network_bootstrap.json")


def sample_canva() -> list:
    """The Mamas Network month, from the captured copy of their page.

    Same idea as the seed snapshot: a real capture so a fresh clone is not
    empty. The site config is the real one from config/sources.yaml, so the
    sample gets the same age hints and venue the daily job would.
    """
    if not os.path.exists(MAMAS_FIXTURE):
        return []
    site = next((s for s in load_sites() if s.get("strategy") == "canva"), None)
    if not site:
        return []
    with open(MAMAS_FIXTURE, "r", encoding="utf-8") as fh:
        return canva.build_from_document(json.load(fh), site)


def main() -> int:
    with open(SEED, "r", encoding="utf-8") as fh:
        snapshot = json.load(fh)

    # The snapshot is a capture of what the scrapers found on one day. The
    # published schedules are generated from rules, so they belong in the
    # sample too, and unlike the snapshot they are correct on any date.
    raw = [to_event(row) for row in snapshot["events"]]
    raw += recurring.fetch(days=HORIZON_DAYS, today=today().date())
    raw += sample_canva()

    events = []
    for event in raw:
        geo.locate(event)
        classify.enrich(event)
        event.bus = geo.reachable_by_bus(event)
        event.updated = today().isoformat(timespec="seconds")
        events.append(event)

    events = defer_projections(events)
    events, _ = notevents.apply(events)
    events, _ = kidfilter.filter_mixed(events, mixed_sources())
    events = dedupe(events)
    events = courtesy.apply(events)
    events = mark_recurring(events)
    events = drop_listing_links(events)

    by_source = {}
    for event in events:
        by_source[event.source] = by_source.get(event.source, 0) + 1

    display_names = {}
    for event in events:
        if event.source and event.source_name:
            display_names.setdefault(event.source, event.source_name)

    payload = {
        "generated": today().isoformat(timespec="seconds"),
        "count": len(events),
        "horizon_days": 120,
        "sample": True,
        "snapshot_date": snapshot.get("captured", ""),
        "age_bands": [{"key": k, "label": AGE_BAND_LABELS[k], "range": list(v)}
                      for k, v in AGE_BANDS.items()],
        "zones": [{"key": k, "label": v} for k, v in ZONE_LABELS.items()],
        "sources": [
            {"key": key, "name": display_names.get(key) or SOURCE_NAMES.get(key, key),
             "count": count,
             "ok": True, "error": "", "seconds": 0}
            for key, count in sorted(by_source.items(), key=lambda kv: -kv[1])
        ],
        "events": [e.to_dict() for e in events],
    }

    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    with open(os.path.join(SITE, "data", "events.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)

    seo.write_sitemap(SITE, payload["generated"])

    feeds = icsbuild.write_feeds(payload["events"], os.path.join(SITE, "feeds"))
    with open(os.path.join(SITE, "data", "feeds.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": payload["generated"], "feeds": feeds}, fh, indent=1)

    stamp_today = today().strftime("%Y-%m-%d")
    today_count = sum(1 for e in payload["events"] if e["start"][:10] == stamp_today)
    linked = sum(1 for e in payload["events"] if e["url"])
    print(f"Seed build: {len(events)} events, {today_count} on {stamp_today}, "
          f"{linked} with a direct link, {len(feeds)} feeds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
