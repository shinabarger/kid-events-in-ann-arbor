"""The gate on general calendars.

Every case in here is a real listing I pulled off one of these sites while
deciding whether to add it, which is why some of them look so specific.
"""

import pytest

from scraper import kidfilter
from scraper.models import Event


def ev(title, description="", audience="", venue="", categories=None,
       age_min=None, age_max=None, source="a2gov_calendar"):
    return Event(
        title=title, start="2026-09-05T10:00:00-04:00", source=source,
        description=description, audience_raw=audience, venue=venue,
        categories=categories or [], age_min=age_min, age_max=age_max,
    )


def keep(event):
    return kidfilter.verdict(event)[0]


# --- the city calendar, which is why the gate exists ---------------------

@pytest.mark.parametrize("title", [
    "Planning Commission Work Session",
    "City Council Regular Session",
    "Housing and Human Services Advisory Board",
    "Public Hearing on the FY27 Budget",
    "Zoning Board of Appeals",
    "Board of Review",
    "Energy Commission Meeting",
])
def test_government_business_never_gets_through(title):
    assert not keep(ev(title)), f"{title} is a meeting, not an outing"


def test_a_committee_with_youth_in_its_name_is_still_a_committee():
    assert not keep(ev("Youth Services Advisory Board Meeting"))


def test_real_city_family_programming_does_get_through():
    assert keep(ev("Family Fun Night at Leslie Park",
                   "Games, crafts and a bounce house for kids."))


# --- Ann Arbor Family, which is not as safe as the name suggests ---------

@pytest.mark.parametrize("title,desc,venue", [
    ("Friday Night Euchre!", "", "HOMES Campus Beer Garden"),
    ("EMU Football vs San Jose State", "", "Rynearson Stadium"),
    ("Fiction at Literati: Ayendy Bonifacio", "A reading", "Literati Bookstore"),
    ("CALL FOR ART: Disability Pride Art Exhibition", "Juried market", ""),
])
def test_the_grown_up_half_of_a_family_calendar_is_turned_away(title, desc, venue):
    assert not keep(ev(title, desc, venue=venue, source="a2family"))


@pytest.mark.parametrize("title,desc,venue", [
    ("Mamas & Littles Outside", "A walk for parents and little ones", "White Lotus Farms"),
    ("Open Play", "Drop in play", "We Rock The Spectrum - Ann Arbor"),
    ("Toddler Time at Launch Trampoline", "", "Launch Trampoline Park"),
    ("Ann Arbor District Library Storytimes", "", "Various Branches"),
    ("Puppet Shows at Dreamland Theater", "", "Dreamland Theater"),
])
def test_the_actual_kid_half_gets_through(title, desc, venue):
    assert keep(ev(title, desc, venue=venue, source="a2family"))


# --- the cases that decide how strict this is ---------------------------

def test_a_stated_age_range_beats_everything_else():
    assert keep(ev("Nature Walk", audience="Ages 3-5", age_min=3, age_max=5))


def test_family_on_its_own_is_not_enough():
    """A brewery calls itself family friendly. Half a signal is a no."""
    assert not keep(ev("Live Music on the Patio", "A family friendly atmosphere."))


def test_but_a_family_signal_at_a_kid_venue_is_enough():
    assert keep(ev("Fall Festival", "Family fun all afternoon.",
                   venue="Ann Arbor Hands-On Museum"))


def test_alcohol_vetoes_even_when_the_word_kids_is_present():
    assert not keep(ev("Kids Eat Free at the Brewery",
                       "Every Tuesday at the taproom.", venue="Wolverine Brewing"))


def test_an_adults_only_note_vetoes_a_kid_sounding_title():
    assert not keep(ev("Storytime for Grown-Ups", "21+ only, wine served."))


def test_a_bare_listing_with_nothing_to_go_on_is_dropped():
    """When it is a coin flip, the answer is no. That is the whole rule."""
    assert not keep(ev("Downtown Market Day"))


# --- what the gate applies to -------------------------------------------

def test_kid_only_sources_are_never_gated():
    """AADL's age band feeds are already filtered at the source. Running them
    through this would only lose things, like a silent disco for teens."""
    kept, dropped = kidfilter.filter_mixed(
        [ev("Silent Disco Dance Party", source="aadl")], {"a2gov_calendar"}
    )
    assert len(kept) == 1 and not dropped


def test_a_mixed_source_is_gated_and_the_reason_is_recorded():
    kept, dropped = kidfilter.filter_mixed(
        [ev("City Council Regular Session", source="a2gov_calendar")],
        {"a2gov_calendar"},
    )
    assert not kept and len(dropped) == 1
    assert "veto" in dropped[0].drop_reason


def test_the_reason_never_reaches_the_page():
    event = ev("City Council Regular Session")
    event.drop_reason = "veto: council"
    assert "drop_reason" not in event.to_dict()


def test_every_general_calendar_in_the_config_is_marked_mixed():
    """The trap is adding a noisy source and forgetting the flag, at which
    point planning commission agendas quietly appear on a toddler calendar."""
    from scraper.run import mixed_sources

    flagged = mixed_sources()
    for key in ("a2gov_calendar", "destination_a2", "a2observer", "a2family",
                "metroparks", "reced", "ypsi_library"):
        assert key in flagged, f"{key} is a general calendar and needs audience: mixed"


# --- getting there on the bus --------------------------------------------

def test_the_bus_rule_covers_the_two_cities_the_buses_actually_serve():
    from scraper import geo

    def place(city, zone="near", minutes=12, venue=""):
        e = ev("Something", venue=venue)
        e.city, e.zone, e.drive_minutes = city, zone, minutes
        return e

    assert geo.reachable_by_bus(place("Ann Arbor", zone="city"))
    assert geo.reachable_by_bus(place("Ypsilanti"))
    assert geo.reachable_by_bus(place("Pittsfield Township"))

    assert not geo.reachable_by_bus(place("Chelsea", minutes=25))
    assert not geo.reachable_by_bus(place("Dexter", minutes=22))
    assert not geo.reachable_by_bus(place("Brighton", zone="outside", minutes=40))


def test_downtown_ypsilanti_counts_however_long_the_drive_is():
    """Route 4 runs between the two downtowns every fifteen minutes. A drive
    time cutoff used to exclude the best served destination on the map."""
    from scraper import geo

    e = ev("Something")
    e.city, e.zone, e.drive_minutes = "Ypsilanti", "near", 24
    assert geo.reachable_by_bus(e)


def test_but_the_far_edge_of_a_township_does_not():
    """Ypsilanti Township has service, but it is partial, so out there the
    drive time still has to be short."""
    from scraper import geo

    e = ev("Something")
    e.city, e.zone, e.drive_minutes = "Ypsilanti Township", "near", 27
    assert not geo.reachable_by_bus(e)


def test_the_known_transit_deserts_are_excluded_by_name():
    from scraper import geo

    e = ev("Fall hike", venue="Hudson Mills Metropark")
    e.city, e.zone, e.drive_minutes = "Ann Arbor", "city", 5
    assert not geo.reachable_by_bus(e), (
        "inside the city limits by coordinates, but no bus goes there"
    )


def test_thirty_minutes_is_what_the_near_zone_means_now():
    from scraper import geo
    from scraper.models import ZONE_LABELS

    assert geo.NEAR_LIMIT_MINUTES == 30
    assert "30 minute" in ZONE_LABELS["near"]
