"""Tests for the parts that decide what a filter shows you."""

import pytest

from scraper import classify, geo, icsbuild
from scraper.dedupe import dedupe, normalize_title
from scraper.models import Event


def make(title="Thing", start="2026-09-04T10:30:00-04:00", **kwargs):
    return Event(title=title, start=start, source=kwargs.pop("source", "test"), **kwargs)


# --- Age parsing -----------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("Babies Up To 24 Months", (0, 2)),
        ("Age 2-5 Years", (2, 5)),
        ("Ages 3 to 5", (3, 5)),
        ("Grade K-5", (5, 11)),
        ("Grade 6-12", (11, 18)),
        ("Grade 2-5", (7, 11)),
        ("age 6 & up", (6, 18)),
        ("Ages 8 and older", (8, 18)),
        ("under 5", (0, 5)),
        ("6 months to 3 years", (0, 3)),
        ("Preschool storytime", (3, 5)),
        ("Teen advisory board", (13, 18)),
        ("Toddler time", (1, 3)),
    ],
)
def test_age_ranges(text, expected):
    lo, hi, _ = classify.parse_age_range(text)
    assert (lo, hi) == expected


def test_all_ages_is_flagged_and_lands_in_every_band():
    lo, hi, all_ages = classify.parse_age_range("All ages welcome")
    assert all_ages is True
    bands = classify.bands_for(lo, hi, all_ages)
    assert set(bands) == {"baby", "toddler", "preschool", "elementary", "tween", "teen"}


def test_bands_overlap_correctly():
    assert classify.bands_for(0, 2, False) == ["baby", "toddler"]
    assert "preschool" in classify.bands_for(3, 5, False)
    assert "teen" in classify.bands_for(11, 18, False)
    assert "baby" not in classify.bands_for(5, 10, False)


def test_unknown_age_gets_no_bands():
    lo, hi, all_ages = classify.parse_age_range("Board of trustees meeting")
    assert classify.bands_for(lo, hi, all_ages) == []


# --- Indoor / outdoor ------------------------------------------------------

def test_setting_detection():
    assert classify.detect_setting("Gallup Park") == "outdoor"
    assert classify.detect_setting("Downtown Library: Kids Story Corner") == "indoor"
    assert classify.detect_setting("Nature hike at the library garden") == "both"
    assert classify.detect_setting("Zoom") == "unknown"


# --- Cost and registration -------------------------------------------------

def test_cost_detection():
    assert classify.detect_cost("Free and open to all")[0] == "free"
    assert classify.detect_cost("Tickets are $12.00")[0] == "paid"
    assert classify.detect_cost("Come on by")[0] == "unknown"


def test_registration_detection():
    assert classify.detect_registration("Registration required, space is limited") is True
    assert classify.detect_registration("Drop in any time, no registration") is False
    assert classify.detect_registration("Just show up") is False


# --- Location --------------------------------------------------------------

def test_downtown_library_is_inside_the_city():
    event = make(venue="Downtown Library: Kids Story Corner")
    geo.locate(event)
    assert event.city == "Ann Arbor"
    assert event.zone == "city"
    assert event.washtenaw is True
    assert event.drive_minutes == 3


def test_rolling_hills_is_county_not_city():
    event = make(venue="Rolling Hills County Park")
    geo.locate(event)
    assert event.city == "Ypsilanti"
    assert event.zone == "near"
    assert event.washtenaw is True


def test_kensington_is_outside_the_29_minute_ring():
    event = make(venue="Kensington Metropark")
    geo.locate(event)
    assert event.drive_minutes == 35
    assert event.zone == "outside"
    assert event.washtenaw is False


def test_the_29_minute_filter_behaves():
    downtown = make(venue="Downtown Library")
    hudson = make(venue="Hudson Mills Metropark")
    kensington = make(venue="Kensington Metropark")
    for event in (downtown, hudson, kensington):
        geo.locate(event)

    assert geo.matches_zone_filter(downtown, "city") is True
    assert geo.matches_zone_filter(hudson, "city") is False
    assert geo.matches_zone_filter(hudson, "near") is True
    assert geo.matches_zone_filter(kensington, "near") is False
    assert geo.matches_zone_filter(kensington, "county") is False
    assert geo.matches_zone_filter(hudson, "county") is True
    assert geo.matches_zone_filter(kensington, "anywhere") is True


def test_drive_estimate_is_sane_for_an_unknown_venue():
    # Roughly Chelsea, about 20 miles out.
    minutes = geo.estimate_drive_minutes(42.3151, -84.0207)
    assert 20 <= minutes <= 45


# --- Dedupe ----------------------------------------------------------------

def test_same_event_from_two_sources_collapses():
    rich = make(
        title="Cardboard Monkey Puppets",
        venue="Pittsfield Branch: Program Room",
        audience_raw="Grade K-5",
        description="Build a monkey puppet out of cardboard and string." * 3,
        end="2026-09-04T11:30:00-04:00",
        source="aadl",
        source_name="Ann Arbor District Library",
    )
    thin = make(
        title="Cardboard Monkey Puppets (Free!)",
        source="aawk",
        source_name="Ann Arbor with Kids",
        url="https://annarborwithkids.com/events/cardboard-monkey-puppets-2/",
    )

    kept = dedupe([thin, rich])
    assert len(kept) == 1
    assert kept[0].source == "aadl"
    assert "Ann Arbor with Kids" in kept[0].also_seen_on


def test_dedupe_fills_gaps_from_the_discarded_copy():
    winner = make(title="Fall Festival", description="x" * 400, venue="Gallup Park", source="aadl")
    loser = make(title="Fall Festival", source="aawk", image="https://example.org/f.jpg",
                 audience_raw="All ages", source_name="Ann Arbor with Kids")
    kept = dedupe([winner, loser])
    assert len(kept) == 1
    assert kept[0].image == "https://example.org/f.jpg"
    assert kept[0].audience_raw == "All ages"


def test_different_events_at_the_same_hour_are_kept_apart():
    a = make(title="Baby Playgroups", venue="Downtown Library")
    b = make(title="Tech Take-Apart", venue="Downtown Library: Secret Lab")
    assert len(dedupe([a, b])) == 2


def test_same_title_on_different_days_is_not_a_duplicate():
    a = make(title="Preschool Storytimes", start="2026-09-04T13:00:00-04:00")
    b = make(title="Preschool Storytimes", start="2026-09-11T13:00:00-04:00")
    assert len(dedupe([a, b])) == 2


def test_title_normalization_strips_the_filler():
    assert normalize_title("Free Family Storytime at the Library") == "storytime library"


# --- Calendar feeds --------------------------------------------------------

def _payload(**kwargs):
    base = {
        "id": "abc123",
        "title": "Baby Playgroups",
        "start": "2026-09-04T10:30:00-04:00",
        "end": "2026-09-04T11:30:00-04:00",
        "venue": "Downtown Library: Kids Story Corner",
        "address": "343 S Fifth Ave, Ann Arbor, MI 48104",
        "description": "Stories, rhymes, and open playtime.",
        "url": "https://aadl.org/node/646111",
        "audience_raw": "Babies Up To 24 Months",
        "price": "Free",
        "cost": "free",
        "registration": False,
        "categories": ["Playgroup"],
        "ages": ["baby", "toddler"],
        "zone": "city",
        "washtenaw": True,
        "setting": "indoor",
        "source_name": "Ann Arbor District Library",
    }
    base.update(kwargs)
    return base


def test_vevent_has_the_required_fields():
    lines = icsbuild.event_to_vevent(_payload())
    text = "\r\n".join(lines)
    assert "BEGIN:VEVENT" in text and "END:VEVENT" in text
    assert "UID:abc123@kid-events-in-ann-arbor" in text
    assert "DTSTART:20260904T143000Z" in text  # 10:30 Eastern is 14:30 UTC
    assert "DTEND:20260904T153000Z" in text
    assert "SUMMARY:Baby Playgroups" in text
    assert "URL:https://aadl.org/node/646111" in text


def test_ics_escapes_commas_and_semicolons():
    lines = icsbuild.event_to_vevent(_payload(title="Stories, songs; and snacks"))
    assert "SUMMARY:Stories\\, songs\\; and snacks" in "\r\n".join(lines)


def test_calendar_lines_are_folded_to_the_rfc_limit():
    long_title = "A really long event title that keeps going " * 5
    text = icsbuild.build_calendar([_payload(title=long_title)], "Test", "Test")
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75


def test_calendar_headers_tell_clients_to_refresh():
    text = icsbuild.build_calendar([], "Test", "Test")
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT12H" in text
    assert "X-WR-TIMEZONE:America/Detroit" in text
    assert text.endswith("END:VCALENDAR\r\n")


def test_every_feed_gets_written(tmp_path):
    events = [
        _payload(),
        _payload(id="def456", title="Hudson Mills Hike", zone="near", setting="outdoor",
                 cost="paid", registration=True, ages=["elementary"], washtenaw=True),
        _payload(id="ghi789", title="Kensington Campout", zone="outside", setting="outdoor",
                 washtenaw=False, ages=["teen"]),
    ]
    written = icsbuild.write_feeds(events, str(tmp_path))
    names = {f["file"]: f["count"] for f in written}

    assert names["all.ics"] == 3
    assert names["ann-arbor-city.ics"] == 1
    assert names["within-30-minutes.ics"] == 2
    assert names["bus-reachable.ics"] == 0, "nothing in this fixture is flagged"
    assert names["washtenaw-county.ics"] == 2
    assert names["outdoor.ics"] == 2
    assert names["free.ics"] == 2
    assert names["drop-in.ics"] == 2
    assert names["age-baby.ics"] == 1
    assert names["age-teen.ics"] == 1
    assert (tmp_path / "all.ics").read_text().startswith("BEGIN:VCALENDAR")


def test_a_renamed_feed_does_not_leave_the_old_one_being_served(tmp_path):
    """Renaming within-29-minutes to within-30-minutes left the old file in
    feeds, still published, quietly frozen. Anybody subscribed to it
    would have a calendar that never updated again and no way to tell."""
    stale = tmp_path / "within-29-minutes.ics"
    stale.write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    keeper = tmp_path / "notes.txt"
    keeper.write_text("not a feed, leave it alone")

    icsbuild.write_feeds([_payload()], str(tmp_path))

    assert not stale.exists(), "the old feed is still there"
    assert keeper.exists(), "only .ics files are ours to clean up"
    assert (tmp_path / "within-30-minutes.ics").exists()
