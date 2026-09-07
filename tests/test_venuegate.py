"""A bookshop's author talks are not children's events.

Ann Arbor with Kids republishes Literati's whole calendar and tags every entry
with kid age bands. Dedupe then merges those tags onto the copy that wins, and
kidfilter passes it on "stated ages from 0". A 6:30pm baking book launch ends
up on a calendar aimed at the under-threes.
"""

import os

import pytest

from scraper import venuegate
from scraper.models import Event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make(title, description="", venue="Literati Bookstore", **kw):
    return Event(title=title, start="2026-09-08T18:30:00-04:00",
                 source="destination_a2", source_name="Destination Ann Arbor",
                 venue=venue, description=description, **kw)


def keeps(event) -> bool:
    kept, _ = venuegate.apply([event])
    return bool(kept)


def test_the_event_that_started_this():
    event = make("Martin Sorge: Great Bakes",
                 "Literati is thrilled to welcome Martin Sorge to celebrate the "
                 "release of Great Bakes. About the Book: Martin Sorge, winner of "
                 "The Great American Baking Show.",
                 ages=["babies", "toddler", "preschoolers", "elementary"],
                 age_min=0, age_max=12)
    assert not keeps(event), "an author talk with borrowed age tags"


def test_borrowed_age_tags_do_not_count_as_saying_so():
    """The tags are the thing we do not trust, so they must not be the reason."""
    bare = make("An Evening with the Author")
    tagged = make("An Evening with the Author", ages=["babies"], age_min=0, age_max=3,
                  all_ages=True)
    assert not keeps(bare)
    assert not keeps(tagged), "age tags must not rescue it"


@pytest.mark.parametrize("title,description", [
    ("Storytime at Literati", "Picture books and songs."),
    ("Literati Family Day", "A family friendly morning downtown."),
    ("Teen Book Club", "For teens in grades 7 and up."),
    ("Toddler Story Hour", ""),
    ("Author Visit", "A picture book reading for kids ages 3 to 6."),
])
def test_a_real_childrens_event_still_comes_through(title, description):
    assert keeps(make(title, description)), f"{title} should survive"


def test_the_gate_only_covers_the_listed_venues():
    """Everywhere else is judged the way it always was."""
    elsewhere = make("An Evening with the Author", venue="Ann Arbor District Library")
    assert keeps(elsewhere), "the library is not gated"


def test_a_venue_name_matches_on_word_boundaries():
    """"The Ark" must not gate an event in Clark Park."""
    assert not venuegate.is_gated(make("Playgroup", venue="Clark Park"),
                                  venuegate.load_venues())
    assert not venuegate.is_gated(make("Playgroup", venue="Arkansas Hall"),
                                  venuegate.load_venues())
    assert venuegate.is_gated(make("Concert", venue="The Ark"),
                              venuegate.load_venues())


def test_a_dropped_event_says_why():
    event = make("Martin Sorge: Great Bakes", "A baking book launch.")
    _, dropped = venuegate.apply([event])
    assert dropped and dropped[0].drop_reason, "the run log needs a reason"


def test_the_config_is_readable_and_not_empty():
    venues = venuegate.load_venues()
    assert venues, "config/venue-gates.yaml should list at least one venue"
    assert any("literati" in v.lower() for v in venues)


def test_no_config_means_no_gate():
    """A missing file must not quietly empty the calendar."""
    kept, dropped = venuegate.apply([make("Anything")], venues=[])
    assert len(kept) == 1 and not dropped
