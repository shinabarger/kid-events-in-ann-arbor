"""Daily pipeline: pull every source, normalize, dedupe, write the site data.

    python -m scraper.run                 full run
    python -m scraper.run --only aadl     one source, for debugging
    python -m scraper.run --offline       reuse the disk cache, no network

One source failing never kills the run. It gets logged and reported in the
build summary on the site so I can see when something has gone stale.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone

import yaml

from . import classify, courtesy, geo, icsbuild, kidfilter, seo
from .dedupe import dedupe
from .models import AGE_BANDS, AGE_BAND_LABELS, ZONE_LABELS
from .sources import (aadl, annarborwithkids, generic, manual, observer,
                      recurring, umich)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The repo root is the published site. The scraper's own settings live in
# config/ so they do not collide with the site's data/ folder.
CONFIG_DIR = os.path.join(ROOT, "config")
SITE_DIR = ROOT

HORIZON_DAYS = 120
KEEP_PAST_DAYS = 1


def load_sites() -> list:
    with open(os.path.join(CONFIG_DIR, "sources.yaml"), "r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    return [s for s in payload.get("sites", []) if s.get("enabled", True)]


def mixed_sources() -> set:
    """Sources that publish for everybody, so every event has to be judged."""
    return {site["key"] for site in load_sites() if site.get("audience") == "mixed"}


def collect(only: str | None = None) -> tuple:
    """Returns (events, report). The report is what the site shows as status."""
    events = []
    report = []

    def run(key, name, fn):
        if only and only != key:
            return
        started = datetime.now(timezone.utc)
        try:
            batch = fn()
            events.extend(batch)
            report.append({"key": key, "name": name, "count": len(batch), "ok": True,
                           "error": "", "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1)})
            print(f"  {name}: {len(batch)}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - a dead source must not stop the run
            report.append({"key": key, "name": name, "count": 0, "ok": False,
                           "error": f"{type(exc).__name__}: {exc}"[:300], "seconds": 0})
            print(f"  {name}: FAILED {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    run("manual", "Added by hand", manual.fetch)
    for series in recurring.load_series():
        run(series["key"], series["name"],
            (lambda s: lambda: recurring.fetch_series(s, days=HORIZON_DAYS))(series))
    run("aadl", "Ann Arbor District Library", aadl.fetch)
    run("aawk", "Ann Arbor with Kids", annarborwithkids.fetch)
    run("umich", "U-M Happening", umich.fetch)
    run("a2observer_kids", "Ann Arbor Observer Kids Calendar", observer.fetch)

    for site in load_sites():
        run(site["key"], site["name"], (lambda s: lambda: generic.fetch(s))(site))

    events = defer_projections(events)
    return events, report


def defer_projections(events: list) -> list:
    """Drop a projected occurrence where the real calendar already covers it.

    A rule is a guess about a month nobody has published yet. Where the
    organizer has actually posted a month, their page wins, even when the two
    disagree, because a rule going stale is exactly the failure this is here
    to avoid.
    """
    by_source = {}
    for event in events:
        if event.start:
            by_source.setdefault(event.source, []).append(event.start[:10])

    windows = {}
    for series in recurring.load_series():
        target = series.get("defer_to")
        days = by_source.get(target) if target else None
        if days:
            windows[series["key"]] = (min(days), max(days))

    if not windows:
        return events

    from .dedupe import normalize_title

    published = {}
    for event in events:
        published.setdefault(event.source, set()).add(
            ((event.start or "")[:10], normalize_title(event.title))
        )

    defer_target = {s["key"]: s.get("defer_to")
                    for s in recurring.load_series() if s.get("defer_to")}

    kept, superseded, drifted = [], 0, []
    for event in events:
        window = windows.get(event.source)
        if window and window[0] <= (event.start or "")[:10] <= window[1]:
            superseded += 1
            key = ((event.start or "")[:10], normalize_title(event.title))
            if key not in published.get(defer_target[event.source], set()):
                drifted.append(event)
            continue
        kept.append(event)

    if superseded:
        print(f"  Projections superseded by a published calendar: {superseded}",
              file=sys.stderr)
    if drifted:
        # The rule said this would happen and their own calendar does not show
        # it. Either they skipped a week or the rule in config/recurring.yaml has
        # gone stale, and both are worth a human looking.
        print(f"  Rules that no longer match the published calendar: {len(drifted)}",
              file=sys.stderr)
        for event in drifted[:6]:
            print(f"    check config/recurring.yaml: {event.title} on "
                  f"{event.start[:10]} is not on their page", file=sys.stderr)
    return kept


# Sources that only ever cover Washtenaw County. If one of these gives us an
# event with no venue at all, it is still local, so do not bury it under
# "farther out" where every location filter hides it.
LOCAL_SOURCES = {
    "manual", "aadl", "aawk", "a2family", "a2observer", "a2observer_kids",
    "destination_a2",
    "reced", "a2_parks_rec", "washtenaw_parks", "ypsi_library", "chelsea_library",
    "mamas_network", "mamas_network_repeat",
    "saline_library", "dexter_library", "a2sf",
}


def normalize(events: list) -> list:
    """Fill in geography and the filter fields, then drop the junk."""
    cleaned = []
    horizon = (datetime.now(timezone.utc) + timedelta(days=HORIZON_DAYS)).isoformat()
    floor = (datetime.now(timezone.utc) - timedelta(days=KEEP_PAST_DAYS)).isoformat()

    for event in events:
        if not event.title or not event.start:
            continue
        if event.start < floor[:19] or event.start > horizon:
            continue

        event.title = " ".join(event.title.split())[:180]
        geo.locate(event)
        classify.enrich(event)

        if event.zone == "outside" and event.lat is None and event.source in LOCAL_SOURCES:
            event.zone = "county"
            event.washtenaw = True

        # Whether you could get here on TheRide. Has to come after locate,
        # because it reads the zone and the drive time it works out.
        event.bus = geo.reachable_by_bus(event)

        # U-M is the whole university and is not in sources.yaml, so it keeps
        # its own gate. Everything else marked audience: mixed goes through
        # kidfilter further down, in one place.
        if event.source == "umich" and not umich.is_family_sponsored(event):
            if not classify.is_kid_relevant(event):
                continue

        if not event.updated:
            event.updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cleaned.append(event)

    return cleaned


# How many separate days a listing has to appear on before it counts as a
# standing fixture rather than an event. "Kids Eat Free" is on every single
# day; a storytime that runs four Tuesdays is not the same kind of thing.
RECURRING_THRESHOLD = 5


def mark_recurring(events: list) -> list:
    """Flag the listings that repeat, so the site can offer to hide them.

    Only all-day repeats get hidden by the filter. A weekly storytime with a
    real start time is still worth putting on your calendar.
    """
    from .dedupe import normalize_title

    groups = {}
    for event in events:
        key = (event.source, normalize_title(event.title), normalize_title(event.venue))
        groups.setdefault(key, set()).add((event.start or "")[:10])

    for event in events:
        key = (event.source, normalize_title(event.title), normalize_title(event.venue))
        days = len(groups.get(key, ()))
        event.repeat_count = days
        event.recurring = days >= RECURRING_THRESHOLD

    return events


# A link that lands on a source's listing page is worse than no link. It makes
# someone click twice and then hunt for the row they already had. If an adapter
# could only manage the listing URL, drop it and let the button disappear.
LISTING_URLS = {
    "https://aadl.org/events",
    "https://annarborwithkids.com/events/",
    "https://annarborobserver.com/kids-calendar/",
    "https://annarborobserver.com/events/",
    "https://www.annarbor.org/events/",
    "https://events.umich.edu/",
    "https://discoverscienceandnature.org/",
    "https://discoverscienceandnature.org/events/",
    "https://www.metroparks.com/",
    "https://www.metroparks.com/events/",
    "https://www.washtenaw.org/",
    "https://reced.a2schools.org/",
    "https://www.a2gov.org/",
    "https://www.annarborfamily.com/events/",
    "https://www.ypsilibrary.org/events/",
}


def is_listing_url(url: str) -> bool:
    """True when the URL is a calendar index rather than one event."""
    if not url:
        return False
    normalized = url.rstrip("/") + "/"
    if normalized in {u.rstrip("/") + "/" for u in LISTING_URLS}:
        return True
    # A bare domain, or a domain plus one generic section, is not an event.
    tail = re.sub(r"^https?://[^/]+", "", url).strip("/")
    return tail in ("", "events", "calendar", "event", "kids-calendar", "events/list")


def hand_written_sources() -> set:
    """Sources where somebody chose the URL on purpose.

    The listing rule exists because a scraped event that fell back to a
    calendar index makes you click twice and then hunt. A hand entered link is
    a different thing: for a series that publishes a schedule rather than a
    page per session, the schedule page is the event page, and it is the only
    place to check whether this week is on.
    """
    return {"manual"} | {s["key"] for s in recurring.load_series()}


def drop_listing_links(events: list, keep: set | None = None) -> list:
    keep = hand_written_sources() if keep is None else keep
    for event in events:
        if event.source not in keep and is_listing_url(event.url):
            event.url = ""
    return events


def build_payload(events: list, report: list) -> dict:
    rows = [e.to_dict() for e in events]
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(rows),
        "horizon_days": HORIZON_DAYS,
        "age_bands": [{"key": k, "label": AGE_BAND_LABELS[k], "range": list(v)}
                      for k, v in AGE_BANDS.items()],
        "zones": [{"key": k, "label": v} for k, v in ZONE_LABELS.items()],
        "sources": report,
        "events": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single source by key")
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    parser.add_argument("--out", default=SITE_DIR)
    args = parser.parse_args()

    if args.offline:
        os.environ["SCRAPE_OFFLINE"] = "1"

    print("Collecting...", file=sys.stderr)
    raw, report = collect(args.only)
    print(f"Raw: {len(raw)}", file=sys.stderr)

    events = normalize(raw)
    print(f"After filtering: {len(events)}", file=sys.stderr)

    events = dedupe(events)
    print(f"After dedupe: {len(events)}", file=sys.stderr)

    events, not_for_kids = kidfilter.filter_mixed(events, mixed_sources())
    print(f"Dropped as not for children: {len(not_for_kids)}", file=sys.stderr)
    for event in not_for_kids[:8]:
        print(f"    {event.source}: {event.title[:56]}  ({event.drop_reason})",
              file=sys.stderr)

    events = courtesy.apply(events)
    print(f"After the opt-out list and excerpt trim: {len(events)}", file=sys.stderr)

    events = mark_recurring(events)
    events = drop_listing_links(events)
    without_link = sum(1 for e in events if not e.url)
    if without_link:
        print(f"Events with no specific page to link to: {without_link}", file=sys.stderr)
    repeats = sum(1 for e in events if e.recurring and e.all_day)
    print(f"All day repeats flagged: {repeats}", file=sys.stderr)

    payload = build_payload(events, report)

    data_dir = os.path.join(args.out, "data")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "events.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)

    seo.write_sitemap(args.out, payload["generated"])

    feeds = icsbuild.write_feeds(payload["events"], os.path.join(args.out, "feeds"))
    with open(os.path.join(data_dir, "feeds.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": payload["generated"], "feeds": feeds}, fh, indent=1)

    print(f"Wrote {len(payload['events'])} events and {len(feeds)} calendar feeds",
          file=sys.stderr)

    failed = [r["name"] for r in report if not r["ok"]]
    if failed:
        print(f"Sources that failed this run: {', '.join(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
