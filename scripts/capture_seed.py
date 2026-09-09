"""Refresh config/snapshot/seed.json from a real run's data/events.json.

The seed is what build_sample.py turns into the offline sample the tests and
the local preview run against. It stores real dates on purpose, because a
sample that silently restamps itself onto today is how a Saturday cider mill
event ended up showing on a Sunday.

The cost of real dates is that the snapshot ages: every morning another day of
it falls into the past, and eventually the tests are filtering an empty set.
So it needs recapturing every so often, and this is the script that does it.

    python scripts/capture_seed.py data/events.json

Takes a spread rather than the lot: a few hundred events would make the front
end suite crawl for no extra coverage.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "config", "snapshot", "seed.json")

TARGET = 90
PER_SOURCE_CAP = 22


def clock(event: dict) -> str:
    if event.get("all_day"):
        return ""
    start = event["start"][11:16]
    end = (event.get("end") or "")[11:16]
    return f"{start}-{end}" if end and end != start else start


def row(event: dict) -> dict:
    return {
        "d": event["start"][:10],
        "t": clock(event),
        "title": event["title"],
        "venue": event.get("venue", ""),
        "city": event.get("city", ""),
        "lat": event.get("lat"),
        "lon": event.get("lon"),
        "src": event.get("source", ""),
        "ages": ", ".join(event.get("ages") or []),
        "cost": event.get("cost", "unknown"),
        "price": event.get("price", ""),
        "set": event.get("setting", "unknown"),
        "desc": (event.get("description") or "")[:280],
        "url": event.get("url", ""),
    }


def pick(events: list) -> list:
    """A spread across sources and days, not the first ninety in the file."""
    by_source = defaultdict(list)
    for event in sorted(events, key=lambda e: e["start"]):
        by_source[event.get("source", "")].append(event)

    chosen, seen = [], set()
    # Round robin, so a source with 300 events cannot crowd out one with 4.
    while len(chosen) < TARGET:
        added = False
        for key in sorted(by_source):
            bucket = by_source[key]
            if not bucket:
                continue
            taken = sum(1 for e in chosen if e.get("source") == key)
            if taken >= PER_SOURCE_CAP:
                continue
            event = bucket.pop(0)
            if event["id"] in seen:
                continue
            seen.add(event["id"])
            chosen.append(event)
            added = True
            if len(chosen) >= TARGET:
                break
        if not added:
            break

    return sorted(chosen, key=lambda e: e["start"])


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "events.json")
    with open(source, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if payload.get("sample"):
        sys.exit("that is the sample, not a real run. Point this at a scraped events.json.")

    chosen = pick(payload["events"])
    seed = {
        "captured": payload["generated"][:10],
        "note": ("A real morning's scrape, trimmed to a spread across sources. "
                 "Real dates on purpose: see scripts/capture_seed.py. Recapture "
                 "when the tests start failing on an empty window."),
        "events": [row(e) for e in chosen],
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(seed, fh, indent=1, ensure_ascii=False)

    spread = defaultdict(int)
    for event in chosen:
        spread[event.get("source_name") or event.get("source")] += 1
    print(f"Captured {len(chosen)} events from {payload['generated'][:10]}, "
          f"{chosen[0]['start'][:10]} to {chosen[-1]['start'][:10]}")
    for name, count in sorted(spread.items(), key=lambda kv: -kv[1]):
        print(f"  {count:3}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
