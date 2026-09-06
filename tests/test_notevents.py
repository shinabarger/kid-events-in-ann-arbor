"""Things that sit on event calendars without being events.

"Kids Eat Free" is the one that started this. Ann Arbor with Kids publishes it
as an all-day listing that repeats every day, so it was taking 13 of the 103
rows on the calendar: a running list of restaurants running a promotion, with
no time, no place, and nothing to turn up to.
"""

import json
import os

import pytest

from scraper import notevents
from scraper.models import Event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ev(title, venue="", source="aawk"):
    return Event(title=title, start="2026-09-05T09:00:00-04:00",
                 source=source, venue=venue)


@pytest.fixture(scope="module")
def rules():
    return notevents.load_rules()


def keeps(rules, title, venue=""):
    return notevents.verdict(ev(title, venue), rules)[0]


# --- the restaurant promotions -------------------------------------------

@pytest.mark.parametrize("title,venue", [
    ("Kids Eat Free", "Various restaurants"),
    ("Kids Eat Free Wednesdays", "Applebee's"),
    ("Kids eat free with adult entree", "Red Robin"),
    ("Kid Eats Free Tuesday", "A local diner"),
    ("Kids eat cheap", "Somewhere"),
    ("Kids eat for $1", "Somewhere"),
    ("Free kids meal with purchase", "Somewhere"),
    ("Kids Meal Deal", "Somewhere"),
])
def test_a_restaurant_promotion_is_not_an_event(rules, title, venue):
    """Marketing for the restaurant, not programming for a child."""
    assert not keeps(rules, title, venue), title


def test_the_one_from_the_real_calendar_is_gone(rules):
    assert not keeps(rules, "Kids Eat Free", "Various restaurants")
    reason = notevents.verdict(ev("Kids Eat Free", "Various restaurants"), rules)[1]
    assert "not an event" in reason


# --- deadlines and announcements -----------------------------------------

@pytest.mark.parametrize("title", [
    "CALL FOR ART: Disability Pride Art Exhibition",
    "Call for vendors",
    "Registration opens for fall soccer",
    "Submissions close Friday",
    "Application deadline",
    "Deadline to apply for camp",
    "Tickets on Sale Now for the Nutcracker",
    "Now Enrolling for Preschool",
    "Save the Date",
])
def test_an_announcement_is_not_an_outing(rules, title):
    assert not keeps(rules, title), title


# --- and everything real survives ----------------------------------------

@pytest.mark.parametrize("title,venue", [
    ("Baby Playgroup", "Downtown Library"),
    ("Free Family Movie Night", "Ann Arbor District Library"),
    ("Toddler Time at Launch", "Launch Trampoline Park"),
    ("FREE Nature Play for Kids", "Allmendinger Park"),
    ("Kids Craft Hour", "Chelsea District Library"),
    ("Free Kids Concert", "Top of the Park"),
    ("Registration required for storytime", "Downtown Library"),
    ("Family Dinner Night", "Community Center"),
    ("Free Community Meal", "Church basement"),
    ("Pancake Breakfast", "Fire station"),
])
def test_real_events_are_untouched(rules, title, venue):
    """The patterns are narrow on purpose. A free meal that is a real event,
    at a real place, at a real time, has to come through."""
    assert keeps(rules, title, venue), title


# --- how it is applied ---------------------------------------------------

def test_it_applies_to_every_source_not_just_the_general_calendars():
    """kidfilter only judges sources marked audience: mixed, because whether
    something is for children depends on the source. Whether it is an event
    at all does not."""
    kept, dropped = notevents.apply([
        ev("Kids Eat Free", "Various restaurants", source="aawk"),
        ev("Kids Eat Free", "A diner", source="a2family"),
        ev("Baby Playgroup", "Library", source="aadl"),
    ])
    assert [e.title for e in kept] == ["Baby Playgroup"]
    assert len(dropped) == 2
    assert all(e.drop_reason for e in dropped)


def test_the_reason_never_reaches_the_page():
    _, dropped = notevents.apply([ev("Kids Eat Free", "Various restaurants")])
    assert "drop_reason" not in dropped[0].to_dict()


def test_a_missing_config_file_is_not_a_crash(tmp_path):
    """A typo in the filename should cost the filter, not the whole run."""
    rules = notevents.load_rules(str(tmp_path / "nope.yaml"))
    assert notevents.apply([ev("Kids Eat Free")], rules)[0]


def test_the_shipped_file_parses():
    rules = notevents.load_rules()
    assert rules["titles"], "no rules at all, so nothing is being filtered"


# --- and it is actually wired in -----------------------------------------

def test_nothing_like_this_survives_into_the_built_calendar():
    with open(os.path.join(ROOT, "data", "events.json"), "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    rules = notevents.load_rules()
    for row in payload["events"]:
        event = ev(row["title"], row.get("venue", ""))
        ok, why = notevents.verdict(event, rules)
        assert ok, f"{row['title']!r} should have been filtered out ({why})"
