"""The Mamas Network, whose events page is a picture of a calendar.

The fixture is the real document from their page on 2026-09-05: every text
box with its position, its lines, and its link, exactly as Canva ships it in
the HTML. Long body copy from the rest of the site is left out; the calendar
section is complete.
"""

import json
import os
from datetime import datetime

import pytest

from scraper import classify, geo, kidfilter
from scraper.sources import canva

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "mamas_network_bootstrap.json")
SITE = {
    "key": "mamas_network", "name": "The Mamas Network",
    "listing": "https://themamasnetwork.org/events",
    "url": "https://themamasnetwork.org/events",
    "venue": "Little Break Cowork", "city": "Ann Arbor",
    "address": "3909 Research Park Dr Suite 300, Ann Arbor, MI 48108",
}


@pytest.fixture(scope="module")
def document():
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def events(document):
    parsed = canva.build_from_document(document, SITE)
    for event in parsed:
        geo.locate(event)
        classify.enrich(event)
    return sorted(parsed, key=lambda e: (e.start, e.title))


# --- pulling the document out of the page --------------------------------

def test_the_bootstrap_blob_is_read_out_of_plain_html():
    """The whole point: no headless browser, no rendering, one GET."""
    payload = {"page": {"A": [{"a": {"C": {"A": ["hi\n"], "C": [{"Q": "https://x/y"}]}},
                               "A": 10.0, "B": 20.0}]}}
    literal = json.dumps(payload).replace("\\", "\\\\").replace("'", r"\'")
    html = ("<html><body><div id=\"root\"></div><script>window['bootstrap'] = "
            f"JSON.parse('{literal}');</script></body></html>")

    boxes = canva.text_boxes(canva.extract_document(html))
    assert boxes == [{"x": 10, "y": 20, "lines": ["hi"], "link": "https://x/y"}]


def test_a_page_with_no_blob_says_so_rather_than_returning_nothing():
    with pytest.raises(canva.ParseError):
        canva.extract_document("<html><body>nothing here</body></html>")


def test_an_apostrophe_in_the_copy_does_not_break_the_parse():
    """The blob is a single quoted JS literal, so every \\' has to come out
    before it is valid JSON. Their copy is full of them."""
    payload = {"page": {"A": [{"a": {"C": {"A": ["Ann Arbor Parks' fall tradition\n"],
                                           "C": []}}, "A": 1.0, "B": 2.0}]}}
    literal = json.dumps(payload).replace("\\", "\\\\").replace("'", r"\'")
    html = f"<script>window['bootstrap'] = JSON.parse('{literal}');</script>"
    boxes = canva.text_boxes(canva.extract_document(html))
    assert boxes[0]["lines"] == ["Ann Arbor Parks' fall tradition"]


# --- rebuilding the grid -------------------------------------------------

def test_the_day_numbers_are_not_pixel_aligned_and_still_cluster():
    """A row of day numbers can sit at 941, 942 and 943. Taking those as three
    separate rows produces a grid no event matches, and everything silently
    falls through. This was a real bug, and it cost eight of seventeen."""
    assert canva.cluster([941, 942, 943, 1114, 1115]) == {
        941: 941, 942: 941, 943: 941, 1114: 1114, 1115: 1114,
    }
    assert canva.cluster([100, 300]) == {100: 100, 300: 300}


def test_the_grid_is_read_off_the_page_not_assumed(document):
    """Their columns are weeks and their rows are days, which is the
    transpose of what you would guess. Nothing here assumes either way."""
    cells = canva.day_cells(canva.text_boxes(document), 9, 2026)
    dates = sorted(cells.values())
    assert str(dates[0]) == "2026-09-01"
    assert str(dates[-1]) == "2026-10-03", "the grid spills into October"
    assert len(dates) == len(set(dates)), "no day should appear twice"


def test_the_trailing_days_roll_into_the_next_month(document):
    """The last column runs 27, 28, 29, 30, then 1, 2, 3. Those threes are
    not September."""
    cells = canva.day_cells(canva.text_boxes(document), 9, 2026)
    october = [d for d in cells.values() if d.month == 10]
    assert [str(d) for d in sorted(october)] == [
        "2026-10-01", "2026-10-02", "2026-10-03",
    ]


def test_every_event_lands_on_the_day_the_calendar_shows(events):
    found = {(e.start[:10], e.title) for e in events}
    for day, title in [
        ("2026-09-05", "DADaS & LITTLES"),
        ("2026-09-12", "mamas & littles"),
        ("2026-09-19", "DADaS & LITTLES"),
        ("2026-09-26", "expecting & NEW Mamas & BABIES"),
        ("2026-10-03", "ann arbor BIRTH & BABY FAIR"),
    ]:
        assert (day, title) in found, f"{title} should be on {day}"


def test_the_playgroups_land_on_the_saturdays_their_own_rule_predicts(events):
    """1st & 3rd, 2nd, and 4th Saturday. If the geometry were wrong these
    would scatter across the week."""
    for event in events:
        if "littles" in event.title.lower() or "BABIES" in event.title:
            assert datetime.fromisoformat(event.start).weekday() == 5, event.title


def test_start_and_end_times_both_come_through(events):
    play = next(e for e in events if e.title == "mamas & littles")
    assert play.start.endswith("09:00:00-04:00")
    assert play.end.endswith("11:00:00-04:00")


def test_an_am_only_start_inherits_the_pm_from_the_end():
    """"12:00-2:00pm" has the meridiem on the end only."""
    block = canva.parse_block(["12:00-2:00pm", "NO PREP BOOK CLUB", "Little Break"])
    assert block["start"] == (12, 0) and block["end"] == (14, 0)


def test_a_title_wrapped_over_two_lines_is_rejoined(events):
    assert any(e.title == "expecting & NEW Mamas & BABIES" for e in events)
    assert any(e.title == "Life Insurance & Estate Planning Workshop" for e in events)


def test_the_last_line_of_a_block_is_the_venue(events):
    off_site = next(e for e in events if e.title == "MAMAS DANCE NIGHT")
    assert off_site.venue == "studiostudio"
    assert off_site.address == "", "somewhere else is not the house address"

    at_home = next(e for e in events if e.title == "mamas & littles")
    assert at_home.venue == "Little Break Cowork"
    assert "Research Park" in at_home.address


def test_each_event_keeps_its_own_signup_link(events):
    play = next(e for e in events if e.title == "mamas & littles")
    assert "zeffy.com" in play.url and "mamas-and-littles" in play.url
    assert play.registration is True


def test_a_link_to_their_own_page_is_not_a_signup(events):
    fair = next(e for e in events if "BIRTH & BABY" in e.title)
    assert fair.url == "https://themamasnetwork.org/a2bbfair"
    assert fair.registration is False


def test_the_same_event_is_not_returned_twice(events):
    """The document carries one copy per layout breakpoint."""
    keys = [(e.start, e.title) for e in events]
    assert len(keys) == len(set(keys))


def test_the_whole_month_comes_through(events):
    assert len(events) == 17


# --- what reaches the page -----------------------------------------------

def test_the_playgroups_and_the_baby_fair_survive_the_gate(events):
    keep, _ = kidfilter.filter_mixed(list(events), {"mamas_network"})
    titles = {e.title for e in keep}
    assert titles == {
        "DADaS & LITTLES", "mamas & littles",
        "expecting & NEW Mamas & BABIES", "ann arbor BIRTH & BABY FAIR",
    }


@pytest.mark.parametrize("title", [
    "SINGLE MOMS SUPPORT GROUP",
    "SOBER / CURIOUS SUPPORT GROUP",
    "NAVIGATING CANCER & PARENTHOOD",
    "smoke & flow",
    "MOMS NIGHT INN",
    "MOM BOSS Networking",
    "NO PREP BOOK CLUB",
    "MAMAS DANCE NIGHT",
    "Life Insurance & Estate Planning Workshop",
    "SH*TTY CRAFT CLUB",
])
def test_the_adult_half_of_their_calendar_never_reaches_a_kids_page(events, title):
    """Most of what they run is for parents on their own, and some of it is
    nobody's business but the people attending. None of it belongs here."""
    event = next(e for e in events if e.title == title)
    assert kidfilter.verdict(event)[0] is False, title


def test_the_ages_come_from_the_config_because_the_grid_has_no_room(document):
    """A cell fits a time, a name and a venue. The age is written further down
    the same page, in the description of each group, so it lives in the site
    config instead."""
    site = dict(SITE, ages=[
        {"match": "littles|playgroup", "text": "Babies and toddlers with a grown-up"},
        {"match": "babies|birth & baby", "text": "Newborns and babies, and anyone expecting"},
    ])
    events = {e.title: e for e in canva.build_from_document(document, site)}
    for event in events.values():
        classify.enrich(event)

    play = events["mamas & littles"]
    assert "baby" in play.ages and "toddler" in play.ages
    assert events["MOMS NIGHT INN"].audience_raw == "", "no hint should match this"


def test_the_shipped_config_gives_the_playgroups_an_age():
    """Without this the Saturday playgroups sit under no age band at all,
    which means a parent filtering for a toddler never sees them."""
    import yaml

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "sources.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        sites = yaml.safe_load(fh)["sites"]

    site = next(s for s in sites if s["key"] == "mamas_network")
    assert site.get("ages"), "no age hints, so the playgroups will be unfiltered"

    with open(FIXTURE, "r", encoding="utf-8") as fh:
        events = canva.build_from_document(json.load(fh), site)
    for event in events:
        classify.enrich(event)
    play = next(e for e in events if e.title == "DADaS & LITTLES")
    assert {"baby", "toddler"} <= set(play.ages)
