"""Series that publish a schedule in words instead of a feed.

The Mamas Network is the reason this exists. Their calendar is a designed
graphic: event names positioned on a picture of a month, no dates attached to
the text, no feed, no JSON-LD, one link on the entire page. But further down
they state the rule the way a person needs it, "1st & 3rd Saturday 9-11am",
and a rule survives a redesign.
"""

import os
from datetime import date

import pytest

from scraper import classify, geo
from scraper.sources import recurring
from scraper.sources.recurring import RuleError, occurrences, parse_rule

TODAY = date(2026, 9, 5)


# --- the rule language ---------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("every wednesday", ([], 2)),
    ("weekly on Tuesdays", ([], 1)),
    ("2nd Saturday", ([2], 5)),
    ("1st & 3rd Saturday", ([1, 3], 5)),
    ("1st and 3rd saturday of the month", ([1, 3], 5)),
    ("first, third and fifth Monday", ([1, 3, 5], 0)),
    ("4th Saturday", ([4], 5)),
    ("last Friday", ([-1], 4)),
])
def test_the_ways_people_write_a_recurrence(text, expected):
    assert parse_rule(text) == expected


@pytest.mark.parametrize("text", ["", "every so often", "3rd", "monthly"])
def test_a_rule_it_cannot_read_is_an_error_not_a_guess(text):
    with pytest.raises(RuleError):
        parse_rule(text)


def test_a_bad_rule_only_costs_that_one_entry(tmp_path, capsys):
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n"
        "  - key: x\n    name: X\n    events:\n"
        "      - {title: Broken, rule: sometimes, time: '09:00'}\n"
        "      - {title: Fine, rule: 2nd saturday, time: '09:00'}\n"
    )
    events = recurring.fetch(str(path), days=60, today=TODAY)
    assert {e.title for e in events} == {"Fine"}
    assert len(events) == 2, "60 days covers two second Saturdays"


# --- turning a rule into dates -------------------------------------------

def test_first_and_third_saturday_lands_where_a_calendar_says_it_should():
    weeks, weekday = parse_rule("1st & 3rd saturday")
    got = occurrences(weeks, weekday, date(2026, 9, 1), date(2026, 10, 31))
    assert [str(d) for d in got] == [
        "2026-09-05", "2026-09-19", "2026-10-03", "2026-10-17",
    ]


def test_last_friday_is_the_last_one_not_the_fourth():
    """October 2026 has five Fridays, so fourth and last are different days."""
    weeks, weekday = parse_rule("last friday")
    got = occurrences(weeks, weekday, date(2026, 10, 1), date(2026, 10, 31))
    assert [str(d) for d in got] == ["2026-10-30"]


def test_a_series_can_be_given_an_end_date(tmp_path):
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n"
        "  - key: x\n    name: X\n    events:\n"
        "      - title: Summer only\n        rule: every saturday\n"
        "        time: '10:00'\n        until: 2026-09-20\n"
    )
    events = recurring.fetch(str(path), days=120, today=TODAY)
    assert [e.start[:10] for e in events] == ["2026-09-05", "2026-09-12", "2026-09-19"]


def test_times_come_out_in_eastern_with_the_right_offset(tmp_path):
    """September is daylight time and December is not. Getting this wrong
    slides a 9am playgroup to 8am for half the year."""
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n  - key: x\n    name: X\n    events:\n"
        "      - {title: T, rule: 1st saturday, time: '09:00-11:00'}\n"
    )
    events = recurring.fetch(str(path), days=120, today=date(2026, 9, 1))
    summer = next(e for e in events if e.start.startswith("2026-09"))
    winter = next(e for e in events if e.start.startswith("2026-12"))
    assert summer.start.endswith("-04:00")
    assert winter.start.endswith("-05:00")
    assert summer.end.startswith(summer.start[:11] + "11:00")


def test_an_entry_with_no_end_time_gets_none_rather_than_a_made_up_one(tmp_path):
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n  - key: x\n    name: X\n    events:\n"
        "      - {title: T, rule: 1st saturday, time: '09:00'}\n"
    )
    assert recurring.fetch(str(path), days=40, today=TODAY)[0].end is None


def test_entries_inherit_the_series_venue_but_can_override_it(tmp_path):
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n  - key: x\n    name: X\n    venue: Home Base\n    city: Ann Arbor\n"
        "    events:\n"
        "      - {title: Usual, rule: 1st saturday, time: '09:00'}\n"
        "      - {title: Away, rule: 2nd saturday, time: '09:00', venue: Somewhere Else}\n"
    )
    by_title = {e.title: e for e in recurring.fetch(str(path), days=40, today=TODAY)}
    assert by_title["Usual"].venue == "Home Base"
    assert by_title["Away"].venue == "Somewhere Else"
    assert by_title["Away"].city == "Ann Arbor", "city should still be inherited"


def test_a_disabled_series_produces_nothing(tmp_path):
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n  - key: x\n    name: X\n    enabled: false\n    events:\n"
        "      - {title: T, rule: every saturday, time: '09:00'}\n"
    )
    assert recurring.fetch(str(path), days=40, today=TODAY) == []


# --- the file we actually ship -------------------------------------------

@pytest.fixture(scope="module")
def mamas():
    events = [e for e in recurring.fetch(days=120, today=TODAY)
              if e.source == "mamas_network_repeat"]
    for event in events:
        geo.locate(event)
        classify.enrich(event)
        event.bus = geo.reachable_by_bus(event)
    return events


def test_the_three_saturday_playgroups_are_there(mamas):
    assert {e.title for e in mamas} == {
        "DADaS & Littles", "Mamas & Littles", "Expecting & New Mamas & Babies",
    }
    assert all(e.start[11:16] == "09:00" for e in mamas)
    assert all(e.end[11:16] == "11:00" for e in mamas)


def test_they_all_land_on_a_saturday(mamas):
    from datetime import datetime

    for event in mamas:
        assert datetime.fromisoformat(event.start).weekday() == 5, event.title


def test_they_come_out_as_baby_and_toddler_events(mamas):
    """This is the whole reason the source is worth having: three recurring
    under-two playgroups that appear on no feed anywhere."""
    for event in mamas:
        assert "baby" in event.ages and "toddler" in event.ages, event.title


def test_the_venue_resolves_to_a_real_place_in_the_city(mamas):
    event = mamas[0]
    assert event.venue == "Little Break Cowork"
    assert "Research Park" in event.address
    assert event.zone == "city"
    assert event.bus is True


def test_every_occurrence_links_back_to_their_page(mamas):
    """A rule can go stale. Their page is always right, so the card has to
    take you there rather than leaving you to find it."""
    assert all(e.url == "https://themamasnetwork.org/events" for e in mamas)


def test_the_adult_support_programming_is_not_in_the_file():
    """Most of their calendar is adult: single parent groups, a cancer and
    parenthood group, a sober curious group, moms nights, a book club. None
    of it belongs on a kids calendar, and a curated file is how we make sure
    a scraper never quietly picks it up."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "recurring.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        raw = "\n".join(line.split("#")[0] for line in fh).lower()

    for phrase in ("support group", "cancer", "sober", "book club",
                   "dance night", "networking", "moms night", "smoke"):
        assert phrase not in raw, f"{phrase!r} is adult programming"


def test_the_projection_defers_to_the_scraped_calendar():
    """A rule is a guess about a month nobody has published yet. Where their
    own page covers the date, their page wins."""
    series = next(s for s in recurring.load_series()
                  if s["key"] == "mamas_network_repeat")
    assert series["defer_to"] == "mamas_network"


def test_every_series_records_when_a_human_last_checked_it():
    """A rule is only as good as the last time somebody read the source page."""
    for series in recurring.load_series():
        assert series.get("checked"), f"{series['key']} has no checked date"
        assert series.get("url"), f"{series['key']} has nowhere to link back to"


# --- projections give way to the real thing ------------------------------

def _at(source, day, title="DADaS & Littles"):
    from scraper.models import Event

    return Event(title=title, start=f"{day}T09:00:00-04:00", source=source)


def test_a_projection_inside_a_published_month_is_dropped():
    from scraper.run import defer_projections

    events = [
        _at("mamas_network", "2026-09-05"),
        _at("mamas_network", "2026-09-19"),
        _at("mamas_network_repeat", "2026-09-05"),
        _at("mamas_network_repeat", "2026-11-07"),
    ]
    kept = defer_projections(events)
    assert [(e.source, e.start[:10]) for e in kept] == [
        ("mamas_network", "2026-09-05"),
        ("mamas_network", "2026-09-19"),
        ("mamas_network_repeat", "2026-11-07"),
    ]


def test_with_nothing_scraped_the_projection_stands():
    """If their page is down or the adapter breaks, the rules still fill in
    rather than the calendar going quiet."""
    from scraper.run import defer_projections

    events = [_at("mamas_network_repeat", "2026-09-05")]
    assert defer_projections(events) == events


def test_a_rule_that_no_longer_matches_gets_reported(capsys):
    """The rules say 1st Saturday, their October page shows the Birth & Baby
    Fair that day instead. Silently dropping that is how a stale rule lives
    forever, so it gets printed."""
    from scraper.run import defer_projections

    defer_projections([
        _at("mamas_network", "2026-10-03", "ann arbor BIRTH & BABY FAIR"),
        _at("mamas_network_repeat", "2026-10-03", "DADaS & Littles"),
    ])
    err = capsys.readouterr().err
    assert "no longer match" in err
    assert "recurring.yaml" in err
