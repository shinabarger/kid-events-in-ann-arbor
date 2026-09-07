"""Parser tests against saved copies of the real pages.

Fixtures are trimmed but the markup is verbatim, so when a site redesigns and
these start failing that is the signal to go look.
"""

import json
import os

import pytest

from scraper.sources import aadl, annarborwithkids, generic, observer, umich

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return fh.read()


# --- AADL ------------------------------------------------------------------

@pytest.fixture(scope="module")
def aadl_events():
    return aadl.parse_listing(fixture("aadl_listing.html"))


def test_aadl_finds_every_row(aadl_events):
    assert len(aadl_events) == 5


def test_aadl_playgroup_parses_completely(aadl_events):
    playgroup = next(e for e in aadl_events if e.title == "Baby Playgroups")
    assert playgroup.start == "2026-09-04T10:30:00-04:00"
    assert playgroup.end == "2026-09-04T11:30:00-04:00"
    assert playgroup.venue == "Downtown Library: Kids Story Corner"
    assert playgroup.audience_raw == "Babies Up To 24 Months"
    assert playgroup.url == "https://aadl.org/node/646111"
    assert playgroup.cost == "free"
    assert playgroup.all_day is False


def test_aadl_keeps_the_grade_string(aadl_events):
    puppets = next(e for e in aadl_events if e.title == "Cardboard Monkey Puppets")
    assert puppets.audience_raw == "Grade K–5"
    assert puppets.venue == "Pittsfield Branch: Program Room"


def test_aadl_evening_teen_event(aadl_events):
    disco = next(e for e in aadl_events if "Silent Disco" in e.title)
    assert disco.start == "2026-09-19T19:00:00-04:00"
    assert disco.audience_raw == "Grade 6–12"


def test_aadl_ids_are_stable_and_unique(aadl_events):
    ids = [e.id for e in aadl_events]
    assert len(set(ids)) == len(ids)
    again = aadl.parse_listing(fixture("aadl_listing.html"))
    assert [e.id for e in again] == ids


def test_aadl_detail_description():
    text = aadl.parse_detail(fixture("aadl_detail.html"))
    assert "babies up to 24 months" in text.lower()
    assert "No older siblings" in text
    assert "Subjects" not in text


# --- Ann Arbor with Kids ---------------------------------------------------

@pytest.fixture(scope="module")
def aawk_events():
    return annarborwithkids.parse_feed(fixture("aawk_events.ics"))


def test_aawk_reads_every_event_in_the_feed(aawk_events):
    assert len(aawk_events) == 4


def test_aawk_pulls_ages_out_of_their_categories(aawk_events):
    disco = next(e for e in aawk_events if "Silent Disco" in e.title)
    assert disco.age_min == 10 and disco.age_max == 18
    assert disco.ages == ["tween", "teen"]
    assert "High Schoolers" in disco.audience_raw


def test_aawk_survives_categories_folded_mid_word(aawk_events):
    """Their iCal folds "Indoor Activities" into "IndoorActivities"."""
    disco = next(e for e in aawk_events if "Silent Disco" in e.title)
    assert disco.setting == "indoor"

    critters = next(e for e in aawk_events if "Critter" in e.title)
    assert critters.registration is True, "Registration Required was folded and missed"
    assert critters.setting == "outdoor"


def test_aawk_reads_the_free_flag(aawk_events):
    disco = next(e for e in aawk_events if "Silent Disco" in e.title)
    assert disco.cost == "free"
    fair = next(e for e in aawk_events if e.title == "Saline Fair")
    assert fair.cost == "unknown"


def test_aawk_keeps_coordinates_and_splits_the_venue(aawk_events):
    fair = next(e for e in aawk_events if e.title == "Saline Fair")
    assert fair.venue == "Washtenaw Farm Council Fairgrounds"
    assert "5055 Ann Arbor Saline Rd" in fair.address
    assert fair.lat == pytest.approx(42.2124, abs=0.001)
    assert fair.lon == pytest.approx(-83.7947, abs=0.001)
    # The last piece of their LOCATION is "United States", never the city.
    assert fair.city != "United States"


def test_aawk_handles_all_day_events(aawk_events):
    free_food = next(e for e in aawk_events if e.title == "Kids Eat Free")
    assert free_food.all_day is True
    assert free_food.start == "2026-09-04T00:00:00-04:00"


def test_aawk_cleans_up_html_entities_in_descriptions(aawk_events):
    fair = next(e for e in aawk_events if e.title == "Saline Fair")
    assert "&amp;" not in fair.description
    assert "ages 6 & up" in fair.description
    assert "\\n" not in fair.description


def test_aawk_drops_their_internal_tags(aawk_events):
    free_food = next(e for e in aawk_events if e.title == "Kids Eat Free")
    assert "Exclude" not in free_food.categories
    assert "Food" in free_food.categories


def test_aawk_day_page_fallback_still_parses():
    html = """<main><table><tr><td>September 10
    10:30am-11:30am</td><td>Little Play Date! at Westgate Branch of AADL, Ann Arbor</td></tr>
    <tr><td>September 10
    All Day</td><td>Kids Eat Free at Various Restaurants</td></tr></table></main>"""
    events = annarborwithkids.parse_day_page(html, 2026)
    assert len(events) >= 1
    play = next(e for e in events if "Little Play Date" in e.title)
    assert play.start == "2026-09-10T10:30:00-04:00"


# --- Generic JSON-LD -------------------------------------------------------

def test_jsonld_event_extraction():
    site = {"key": "discover_science", "name": "Hands-On Museum & Leslie Science"}
    nodes = list(generic.iter_jsonld_events(fixture("jsonld_event.html")))
    assert len(nodes) == 1

    event = generic.event_from_jsonld(nodes[0], site)
    assert event.title == "Monarch Migration Festival"
    assert event.start == "2026-09-13T11:00:00-04:00"
    assert event.venue == "Leslie Science & Nature Center"
    assert event.city == "Ann Arbor"
    assert event.lat == pytest.approx(42.3041)
    assert event.cost == "paid"
    assert event.price == "$12.00"
    assert event.audience_raw == "All ages"


def test_jsonld_date_only_start_gets_an_offset():
    assert generic._normalize_dt("2026-07-04") == "2026-07-04T00:00:00-04:00"
    assert generic._normalize_dt("2026-01-04") == "2026-01-04T00:00:00-05:00"


def test_jsonld_ignores_broken_blocks():
    html = '<script type="application/ld+json">{not json}</script>'
    assert list(generic.iter_jsonld_events(html)) == []


def test_ics_reader_round_trips():
    site = {"key": "x", "name": "X"}
    text = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
        "SUMMARY:Storytime at the park\r\n"
        "DTSTART:20260904T103000\r\nDTEND:20260904T113000\r\n"
        "LOCATION:Gallup Park\r\nURL:https://example.org/e/1\r\n"
        "DESCRIPTION:Bring a blanket\\, snacks provided\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    events = generic.parse_ics(text, site)
    assert len(events) == 1
    assert events[0].title == "Storytime at the park"
    assert events[0].start == "2026-09-04T10:30:00-04:00"
    assert events[0].venue == "Gallup Park"
    assert "snacks provided" in events[0].description


# --- Ann Arbor Observer kids calendar --------------------------------------

@pytest.fixture(scope="module")
def observer_events():
    return observer.parse_page(fixture("observer_kids.html"))


def test_observer_reads_the_editorial_prose(observer_events):
    titles = [e.title for e in observer_events]
    assert "Tech Take-Apart" in titles
    assert "Little Story Party: Dino Party" in titles, "a colon inside the title broke the split"
    assert "Fall Open House" in titles, "an unquoted title was missed"


def test_observer_takes_the_month_from_the_page_heading(observer_events):
    tech = next(e for e in observer_events if e.title == "Tech Take-Apart")
    assert tech.start == "2026-09-04T13:00:00-04:00"
    assert tech.end == "2026-09-04T14:00:00-04:00"


def test_observer_expands_one_paragraph_into_several_dates(observer_events):
    art = sorted(e.start[:10] for e in observer_events if e.title == "Preschool ArtStart")
    assert art == ["2026-09-14", "2026-09-15", "2026-09-16"]

    story = sorted(e.start[:10] for e in observer_events if e.title == "Outdoor Story Time")
    assert story == ["2026-09-15", "2026-09-22", "2026-09-29"], \
        "the list \"15, 22, & 29\" should become three events"


def test_observer_keeps_each_time_window_with_its_own_dates(observer_events):
    art = {e.start[:10]: e.start[11:16] for e in observer_events if e.title == "Preschool ArtStart"}
    assert art["2026-09-14"] == "10:30"
    assert art["2026-09-16"] == "10:30"
    assert art["2026-09-15"] == "13:30", "the second time window went to the wrong day"


def test_observer_reads_the_star_as_free_and_a_dollar_sign_as_paid(observer_events):
    tech = next(e for e in observer_events if e.title == "Tech Take-Apart")
    assert tech.cost == "free"

    pets = next(e for e in observer_events if "Pajamas" in e.title)
    assert pets.cost == "paid"
    assert pets.price == "$35"
    assert pets.registration is True


def test_observer_expands_their_venue_abbreviations(observer_events):
    tech = next(e for e in observer_events if e.title == "Tech Take-Apart")
    assert tech.venue == "Downtown Library"
    pets = next(e for e in observer_events if "Pajamas" in e.title)
    assert pets.venue == "Humane Society of Huron Valley"


def test_observer_splits_venue_from_description(observer_events):
    tales = next(e for e in observer_events if "Tales" in e.title)
    assert tales.venue.startswith("Flying Cardboard Theater")
    assert "puppet" in tales.description.lower()


def test_observer_skips_the_every_week_lines():
    """Those recurring library programs come from AADL with real dates."""
    events = observer.parse_paragraph(
        "★ Every Mon.-Fri. (different times): Preschool Storytimes: AADL. Half-hour program.",
        9, 2026)
    assert events == []


def test_observer_time_parsing():
    assert observer.split_time_window("1-2 p.m.") == ((13, 0), (14, 0))
    assert observer.split_time_window("10 a.m.-noon") == ((10, 0), (12, 0))
    assert observer.split_time_window("5:30-8:30 p.m.") == ((17, 30), (20, 30))
    assert observer.split_time_window("11 a.m.") == ((11, 0), None)
    assert observer.split_time_window("different times") == (None, None)


# --- U-M -------------------------------------------------------------------

def test_umich_payload_parses():
    payload = json.loads(fixture("umich_day.json"))
    events = umich.parse_payload(payload)
    assert len(events) == 2

    lab = next(e for e in events if "Fossils" in e.title)
    assert lab.start == "2026-09-10T10:00:00-04:00"
    assert lab.end == "2026-09-10T14:00:00-04:00"
    assert lab.url.startswith("https://")
    assert "Museum of Natural History" in " ".join(lab.categories) + lab.venue
    assert umich.is_family_sponsored(lab) is True


def test_umich_adult_event_is_not_family_sponsored():
    payload = json.loads(fixture("umich_day.json"))
    events = umich.parse_payload(payload)
    mixer = next(e for e in events if "Wine" in e.title)
    assert umich.is_family_sponsored(mixer) is False


# --- schema.org dates without a time ---------------------------------------

def test_a_date_with_no_time_is_all_day_not_midnight():
    """Several calendars put the date in startDate and the time in their own
    markup. Stamping midnight on those published a 6:30pm author talk as 12am.
    """
    from scraper.sources.generic import event_from_jsonld

    site = {"key": "destination_a2", "name": "Destination Ann Arbor"}
    node = {"name": "Martin Sorge: Great Bakes", "startDate": "2026-09-08",
            "endDate": "2026-09-08"}

    event = event_from_jsonld(node, site, "https://example.org/e/1", "")
    assert event.all_day is True, "no time anywhere, so say all day"
    assert event.end is None, "an end equal to the start is worse than no end"


def test_a_time_on_the_page_beats_a_bare_date_in_the_feed():
    from scraper.sources.generic import event_from_jsonld

    site = {"key": "destination_a2", "name": "Destination Ann Arbor"}
    node = {"name": "Martin Sorge: Great Bakes", "startDate": "2026-09-08"}

    event = event_from_jsonld(node, site, "https://example.org/e/1",
                              "<div><span>Time:</span> 6:30 PM</div>")
    assert event.start == "2026-09-08T18:30:00-04:00"
    assert event.all_day is False


def test_a_real_datetime_in_the_feed_is_left_alone():
    from scraper.sources.generic import event_from_jsonld

    site = {"key": "destination_a2", "name": "Destination Ann Arbor"}
    node = {"name": "Storytime", "startDate": "2026-09-08T10:30:00-04:00",
            "endDate": "2026-09-08T11:15:00-04:00"}

    event = event_from_jsonld(node, site, "https://example.org/e/1",
                              "<p>Time: 6:30 PM</p>")
    assert event.start == "2026-09-08T10:30:00-04:00", "the page must not override the feed"
    assert event.end == "2026-09-08T11:15:00-04:00"
    assert event.all_day is False


def test_time_recovery_reads_a_range_and_ignores_loose_times():
    from scraper.sources.generic import recover_time

    assert recover_time("<p>Time: 6:30 PM - 8:00 PM</p>", "2026-09-08") == (
        "2026-09-08T18:30:00-04:00", "2026-09-08T20:00:00-04:00")

    # January, so the offset has to follow.
    assert recover_time("Starts at 10 am", "2026-01-14")[0] == "2026-01-14T10:00:00-05:00"

    # A time buried in a description is far more likely to belong to something
    # else than to be this event's start.
    assert recover_time("<p>Doors 7 pm. Bring a book.</p>", "2026-09-08") == ("", "")
    assert recover_time("", "2026-09-08") == ("", "")


def test_nothing_published_starts_at_midnight_unless_it_says_all_day():
    """The guard that would have caught this in the first place."""
    import json
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "data", "events.json"), "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    bad = [e for e in payload["events"]
           if "T00:00:00" in (e.get("start") or "") and not e.get("all_day")]
    assert not bad, ("a timed event at midnight is almost always a date with the "
                     "time lost: " + ", ".join(f"{e['source_name']}/{e['title']}" for e in bad[:5]))
