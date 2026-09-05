"""The City of Ann Arbor Parks & Rec feed.

The fixture is the real calendar, captured 2026-09-05. Descriptions are
trimmed for readability but every quirk is verbatim: the 75 octet line
folding, Trumba's doubled entity escaping, the inline HTML, the custom fields,
and the split between URL and X-TRUMBA-LINK.
"""

import os

import pytest

from scraper import classify, kidfilter
from scraper.sources import trumba

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "trumba_parks_and_rec.ics")
SITE = {"key": "a2_parks_rec", "name": "Ann Arbor Parks & Rec",
        "feed": "https://www.trumba.com/calendars/"
                "city-of-ann-arbor-events-parks-and-recreation.rss"}


@pytest.fixture(scope="module")
def events():
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        parsed = trumba.parse(fh.read(), SITE)
    for event in parsed:
        classify.enrich(event)
    return {e.title: e for e in parsed}


def test_the_rss_link_is_read_as_ical():
    """The city hands out the .rss URL, but that one puts the date in a
    sentence of prose and nothing else machine readable."""
    assert trumba.feed_url(SITE).endswith(
        "city-of-ann-arbor-events-parks-and-recreation.ics"
    )
    assert trumba.feed_url({"feed": "https://x/y.ics"}) == "https://x/y.ics"


def test_start_and_end_times_survive_the_timezone(events):
    story = events["FREE Outdoor Story Time for Kids"]
    assert story.start == "2026-09-15T10:30:00-04:00"
    assert story.end == "2026-09-15T11:30:00-04:00"


def test_the_address_comes_off_the_custom_field(events):
    market = events["Ann Arbor Farmers Market Saturday Market Regular Hours"]
    assert market.venue == "Ann Arbor Farmers Market"
    assert market.address.startswith("315 Detroit Street")


def test_trumbas_doubled_escaping_is_undone(events):
    r"""It HTML escapes, then escapes the semicolon again for iCal, so a
    right single quote arrives as &#8217\; and has to be unwound twice."""
    fair = next(e for t, e in events.items() if "Green Fair" in t)
    assert "&#" not in fair.title and r"\;" not in fair.title
    assert "Kid's Zone" in fair.title
    assert "²" in fair.title or "A2" in fair.title

    river = events["Trick or Treat on the River"]
    assert "&#8217" not in river.description
    assert "<strong>" not in river.description


def test_the_repeated_header_is_stripped_from_the_description(events):
    """Every description opens with the venue and address, which are already
    their own fields. Left in, the card reads them back at you twice."""
    boo = events["Boo Bash"]
    assert boo.description == "Details to be announced. Stay tuned."
    assert not boo.description.startswith("Location:")


def test_the_link_goes_to_the_event_page_not_the_signup_form(events):
    """URL is wherever you register. X-TRUMBA-LINK is the event's own page,
    which is what belongs behind View on Website."""
    yoga = events["FREE Adult Outdoor Yoga"]
    assert "a2gov.org" in yoga.url
    assert "rec1.com" not in yoga.url


def test_a_signup_link_marks_the_event_as_registration(events):
    assert events["FREE Nature Play for Kids"].registration is True
    assert events["Boo Bash"].registration is False


def test_volunteer_shifts_are_recognised(events):
    """Half this calendar is volunteer work. The reliable signal is not the
    wording, it is that the signup link points at volunteerhub."""
    for title in ("Litter Cleanup at Argo Cascades",
                  "Playground Maintenance at Kilburn Park",
                  "Trick or Treat on the River"):
        assert events[title].volunteer is True, title
    assert events["Free Family Trivia Night"].volunteer is False


def test_no_images_are_carried_over(events):
    """Two of these have IMAGE;VALUE=URI. Somebody else's photo, so no."""
    assert all(e.image == "" for e in events.values())


# --- what actually reaches the page --------------------------------------

def kept(events):
    keep, _ = kidfilter.filter_mixed(list(events.values()), {"a2_parks_rec"})
    return {e.title for e in keep}


def test_the_storytimes_and_the_halloween_party_get_through(events):
    surviving = kept(events)
    assert "FREE Nature Play for Kids" in surviving
    assert "FREE Outdoor Story Time for Kids" in surviving
    assert "Boo Bash" in surviving


def test_the_volunteer_workdays_do_not(events):
    surviving = kept(events)
    for title in ("Litter Cleanup at Argo Cascades",
                  "Playground Maintenance at Kilburn Park"):
        assert title not in surviving, f"{title} is a shift, not an outing"


def test_spreading_woodchips_under_a_playground_is_not_a_playground_visit(events):
    """The title says Playground, which is a strong kid signal everywhere
    else on the site. Here it is a volunteer workday with pitchforks."""
    event = events["Playground Maintenance at Kilburn Park"]
    keep, why = kidfilter.verdict(event)
    assert keep is False
    assert "volunteer" in why


def test_a_kids_zone_staffed_by_volunteers_is_still_a_volunteer_shift(events):
    event = next(e for t, e in events.items() if "Green Fair" in t)
    assert kidfilter.verdict(event)[0] is False


def test_adult_yoga_is_dropped_on_the_title_alone(events):
    keep, why = kidfilter.verdict(events["FREE Adult Outdoor Yoga"])
    assert keep is False and "title" in why


def test_and_a_kid_event_that_says_bring_a_grown_up_is_not(events):
    """"For children 2-5 years of age and an adult" is the opposite of an
    adults only event, which is why that word is only judged in the title."""
    story = events["FREE Outdoor Story Time for Kids"]
    assert "adult" in story.description.lower()
    assert kidfilter.verdict(story)[0] is True


def test_the_ages_come_out_of_the_parks_and_rec_phrasing(events):
    """They never write the word "ages", so "For kids 0-5" used to land in
    the elementary band and miss every parent it was written for."""
    assert (events["FREE Nature Play for Kids"].age_min,
            events["FREE Nature Play for Kids"].age_max) == (0, 5)
    assert set(events["FREE Nature Play for Kids"].ages) >= {"baby", "toddler", "preschool"}
    assert (events["FREE Outdoor Story Time for Kids"].age_min,
            events["FREE Outdoor Story Time for Kids"].age_max) == (2, 5)
