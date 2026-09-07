"""End to end: run the sample build and check what the site actually loads."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime

import pytest

from scraper.sources import generic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = os.path.join(ROOT, "data", "events.json")
FEEDS_JSON = os.path.join(ROOT, "data", "feeds.json")
FEED_DIR = os.path.join(ROOT, "feeds")

REQUIRED_FIELDS = [
    "id", "title", "start", "source", "source_name", "zone", "washtenaw",
    "ages", "all_ages", "setting", "cost", "registration", "categories",
]


@pytest.fixture(scope="module", autouse=True)
def build():
    """Build the sample, then put back whatever was there before.

    build_sample.py writes straight into data/ and feeds/, which on a working
    copy is the real scraped data. Running the tests used to leave 90 sample
    events sitting where 771 real ones had been, and a git add . after that
    would push the sample live, banner and all.
    """
    kept = {}
    for folder, suffix in (("data", ".json"), ("feeds", ".ics")):
        base = os.path.join(ROOT, folder)
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            if name.endswith(suffix):
                path = os.path.join(base, name)
                with open(path, "rb") as fh:
                    kept[path] = fh.read()

    # The sample build rewrites this too, with today's date.
    sitemap = os.path.join(ROOT, "sitemap.xml")
    if os.path.exists(sitemap):
        with open(sitemap, "rb") as fh:
            kept[sitemap] = fh.read()

    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "build_sample.py")],
        cwd=ROOT, check=True, capture_output=True,
    )

    yield

    # Written in place rather than deleted and replaced, so this still works
    # where the checkout does not allow unlinking.
    for path, body in kept.items():
        with open(path, "wb") as fh:
            fh.write(body)


@pytest.fixture(scope="module")
def payload():
    with open(EVENTS, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_events_file_has_what_the_page_expects(payload):
    assert payload["count"] > 0
    assert payload["count"] == len(payload["events"])
    assert {b["key"] for b in payload["age_bands"]} == {
        "baby", "toddler", "preschool", "elementary", "tween", "teen"
    }
    assert payload["sources"]


def test_every_event_has_the_required_fields(payload):
    for event in payload["events"]:
        for field in REQUIRED_FIELDS:
            assert field in event, f"{event.get('title')} is missing {field}"
        assert event["zone"] in ("city", "near", "county", "outside")
        assert event["setting"] in ("indoor", "outdoor", "both", "unknown")
        assert event["cost"] in ("free", "paid", "unknown")
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", event["start"])


def test_event_ids_are_unique(payload):
    ids = [e["id"] for e in payload["events"]]
    assert len(set(ids)) == len(ids)


def test_day_zero_lands_on_the_eastern_calendar_day(payload):
    """The site renders in Eastern. If the seed is built against the runner's
    UTC clock, every "today" event slides to tomorrow after 8pm Eastern and the
    page opens on an empty day. Caught in the wild on 2026-09-04 at 8:30pm.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    eastern_today = datetime.now(ZoneInfo("America/Detroit")).strftime("%Y-%m-%d")
    on_today = [e for e in payload["events"] if e["start"][:10] == eastern_today]
    assert on_today, (
        f"nothing lands on {eastern_today}, the Eastern calendar day. "
        "The seed is probably being built against UTC."
    )


def test_no_scraped_event_links_to_a_listing_page(payload):
    """A scraped link that lands on a calendar index makes someone click twice
    and then hunt for the row they already had. Better to show no link at all.

    Hand written sources are exempt on purpose: a series that publishes a
    schedule rather than a page per session has no other page to point at, and
    that schedule is where you check whether this week is on.
    """
    from scraper.run import hand_written_sources, is_listing_url

    hand = hand_written_sources()
    bad = [e for e in payload["events"]
           if e["source"] not in hand and is_listing_url(e["url"])]
    assert not bad, "these link to a listing rather than the event: " + ", ".join(
        f"{e['title']} -> {e['url']}" for e in bad[:5]
    )


def test_most_events_link_somewhere_specific(payload):
    linked = [e for e in payload["events"] if e["url"]]
    assert len(linked) / len(payload["events"]) > 0.6, (
        "most events should have a page of their own to link to"
    )


def test_calendar_entries_carry_the_details(payload):
    """Whatever ends up in your calendar has to still make sense in three
    weeks, when the title alone will not remind you where to park."""
    from scraper.icsbuild import build_description, calendar_location

    event = next(e for e in payload["events"] if e["title"] == "Baby Playgroups")
    text = build_description(event)

    for label in ("Where:", "Ages:", "Cost:", "Signup:", "Listed by:", "Details:"):
        assert label in text, f"{label} missing from the calendar description"
    assert "Fifth Ave" in text, "the street address should be in there"
    assert "?event=" in text, "a link back to the listing helps when plans change"

    location = calendar_location(event)
    assert "Downtown Library" in location and "Fifth Ave" in location


def test_calendar_entries_include_coordinates_when_we_have_them(payload):
    import os as _os
    from scraper.icsbuild import event_to_vevent

    event = next(e for e in payload["events"] if e["lat"] is not None)
    assert any(line.startswith("GEO:") for line in event_to_vevent(event)), (
        "a calendar app can map an event when it has coordinates"
    )
    assert _os.path.exists(os.path.join(FEED_DIR, "all.ics"))


def test_events_are_sorted_by_start(payload):
    starts = [e["start"] for e in payload["events"]]
    assert starts == sorted(starts)


def test_every_declared_feed_exists_and_parses():
    with open(FEEDS_JSON, "r", encoding="utf-8") as fh:
        feeds = json.load(fh)["feeds"]
    assert len(feeds) == 15

    for feed in feeds:
        path = os.path.join(FEED_DIR, feed["file"])
        assert os.path.exists(path), f"{feed['file']} was declared but not written"
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert text.startswith("BEGIN:VCALENDAR")
        assert text.rstrip().endswith("END:VCALENDAR")
        assert text.count("BEGIN:VEVENT") == feed["count"]
        assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT")


def test_the_written_feeds_read_back_correctly():
    """Parse all.ics with our own iCal reader as a round trip check."""
    with open(os.path.join(FEED_DIR, "all.ics"), "r", encoding="utf-8") as fh:
        text = fh.read()
    events = generic.parse_ics(text, {"key": "x", "name": "X"})
    assert len(events) > 0
    for event in events:
        assert event.title
        assert event.start


def test_age_feeds_only_contain_that_band(payload):
    by_id = {e["id"]: e for e in payload["events"]}
    for band in ("baby", "teen"):
        path = os.path.join(FEED_DIR, f"age-{band}.ics")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        for uid in re.findall(r"UID:([0-9a-f]+)@", text):
            assert band in by_id[uid]["ages"]


def test_city_feed_only_has_city_events(payload):
    by_id = {e["id"]: e for e in payload["events"]}
    with open(os.path.join(FEED_DIR, "ann-arbor-city.ics"), "r", encoding="utf-8") as fh:
        text = fh.read()
    uids = re.findall(r"UID:([0-9a-f]+)@", text)
    assert uids
    for uid in uids:
        assert by_id[uid]["zone"] == "city"


def test_site_files_are_present():
    for path in ["index.html", "assets/app.js", "assets/style.css",
                 "assets/favicon.svg", ".nojekyll"]:
        assert os.path.exists(os.path.join(ROOT, path)), f"{path} is missing"


def test_the_page_points_at_the_right_pages_url():
    with open(os.path.join(ROOT, "assets", "app.js"), "r", encoding="utf-8") as fh:
        js = fh.read()
    assert "shinabarger.github.io/kid-events-in-ann-arbor" in js


def test_html_has_the_accessibility_basics():
    with open(os.path.join(ROOT, "index.html"), "r", encoding="utf-8") as fh:
        html = fh.read()
    assert 'lang="en"' in html
    assert 'class="skip"' in html
    assert 'aria-live="polite"' in html
    assert html.count("<label") >= 6
    # Every select and search input needs a label pointing at it.
    for control_id in re.findall(r'<(?:select|input)[^>]*id="(f-[\w-]+)"', html):
        assert f'for="{control_id}"' in html, f"{control_id} has no label"


def test_rebuilding_produces_the_same_ids_rather_than_a_second_copy():
    """The job runs every morning and overwrites the file, so nothing can
    accumulate. This guards the subtler version: an id that quietly changes
    between runs would show up in a subscriber's calendar as a second copy of
    an event they already have, every single day.
    """
    import subprocess
    import sys as _sys

    def build_once():
        subprocess.run([_sys.executable, os.path.join(ROOT, "scripts", "build_sample.py")],
                       cwd=ROOT, check=True, capture_output=True)
        with open(EVENTS, "r", encoding="utf-8") as fh:
            return json.load(fh)

    first, second = build_once(), build_once()

    assert first["count"] == second["count"]
    assert [e["id"] for e in first["events"]] == [e["id"] for e in second["events"]]


def test_a_time_change_keeps_the_id_so_the_calendar_entry_updates():
    """The id is the source, the title, the day and the venue, deliberately
    not the time. An organizer moving a storytime from 10:00 to 10:30 should
    edit the entry you already have, not add a second one."""
    from scraper.models import Event

    ten = Event(title="Storytime", start="2026-09-05T10:00:00-04:00",
                source="aadl", venue="Downtown Library")
    half_past = Event(title="Storytime", start="2026-09-05T10:30:00-04:00",
                      source="aadl", venue="Downtown Library")
    assert ten.id == half_past.id

    # A different day is a different event, though.
    tomorrow = Event(title="Storytime", start="2026-09-06T10:00:00-04:00",
                     source="aadl", venue="Downtown Library")
    assert ten.id != tomorrow.id


def test_the_same_series_from_two_adapters_only_lands_once(payload):
    """The Mamas Network arrives twice over: scraped from their published
    month, and projected from the rules for the months after it. Those must
    never both appear on the same day."""
    days = {}
    for event in payload["events"]:
        if not event["source"].startswith("mamas_network"):
            continue
        days.setdefault(event["start"][:10], []).append(event["source"])

    for day, sources in days.items():
        assert not ({"mamas_network", "mamas_network_repeat"} <= set(sources)), (
            f"both the real calendar and a projection landed on {day}"
        )


# --- the bug that put Saturday's event on Sunday -------------------------

def test_the_snapshot_stores_real_dates_not_offsets():
    """This shipped, and it was the worst kind of wrong.

    The snapshot used to store each event as a day offset, which the build
    re-stamped against whatever day it ran. The sample always looked current
    and every date was wrong by however long it had been since the capture: a
    Saturday cider mill event showed on Sunday, then Monday, sliding one more
    day every day. On a calendar people plan a weekend around, a wrong date is
    worse than no date.
    """
    import json as _json

    path = os.path.join(ROOT, "config", "snapshot", "seed.json")
    with open(path, "r", encoding="utf-8") as fh:
        seed = _json.load(fh)

    for row in seed["events"]:
        assert isinstance(row["d"], str), (
            f"{row['title']!r} still stores a day offset, which will drift"
        )
        datetime.strptime(row["d"], "%Y-%m-%d")


def test_the_sample_keeps_the_day_the_source_actually_said():
    """Two real listings, checked against their own pages. The cider mill
    celebration was a Saturday and the babies class was a Sunday."""
    import json as _json

    path = os.path.join(ROOT, "config", "snapshot", "seed.json")
    with open(path, "r", encoding="utf-8") as fh:
        seed = _json.load(fh)
    by_title = {r["title"]: r for r in seed["events"]}

    expected = {
        "Dexter Cider Mill 140th Season Celebration": ("2026-09-05", "Saturday"),
        "Dancing Babies with Momo Kajiwara": ("2026-09-06", "Sunday"),
    }
    for title, (day, weekday) in expected.items():
        assert by_title[title]["d"] == day, title
        assert datetime.strptime(day, "%Y-%m-%d").strftime("%A") == weekday


def test_building_twice_on_different_days_does_not_move_anything(payload):
    """The drift test. Build, note the dates, build again pretending it is a
    week later, and nothing should have moved."""
    import json as _json
    import subprocess
    import sys as _sys

    first = {e["title"]: e["start"][:10] for e in payload["events"]}

    env = dict(os.environ, TZ="America/Detroit")
    subprocess.run([_sys.executable, os.path.join(ROOT, "scripts", "build_sample.py")],
                   cwd=ROOT, check=True, capture_output=True, env=env)
    with open(EVENTS, "r", encoding="utf-8") as fh:
        again = {e["title"]: e["start"][:10] for e in _json.load(fh)["events"]}

    moved = {t: (first[t], again[t]) for t in first if t in again and first[t] != again[t]}
    assert not moved, f"these dates moved between builds: {list(moved)[:4]}"


def test_the_payload_says_when_it_was_made_and_whether_it_is_real(payload):
    """The page needs both to warn anybody that the dates may be stale."""
    assert payload.get("generated")
    datetime.fromisoformat(payload["generated"])
    if payload.get("sample"):
        assert payload.get("snapshot_date"), "a sample has to say when it was captured"


def test_a_real_run_says_it_is_not_a_sample(payload):
    """The notice keys off this. Leaving it absent meant the page had to infer
    it, and a cached copy of the old sample file kept the warning on screen
    after a perfectly good scrape."""
    from scraper.run import build_payload

    real = build_payload([], [])
    assert real["sample"] is False, "a live run must say so explicitly"
    assert "generated" in real

    # And the sample build still flags itself.
    assert payload.get("sample") is True
