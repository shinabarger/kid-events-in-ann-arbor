"""Tests for the CitySpark Ann Arbor Family adapter."""

import json

import pytest

from scraper.sources.cityspark import event_from_row, _normalize_dt, _strip_html
from scraper.kidfilter import verdict


# --- sample API rows --------------------------------------------------------

def _row(**overrides):
    """A realistic CitySpark event row with sensible defaults."""
    base = {
        "PId": 12345,
        "Name": "Fall Family Fun Day",
        "Description": "<p>Bring the whole family for crafts, games, and fun!</p>",
        "Summary": "Fun for all ages at the park.",
        "Venue": "Gallup Park",
        "CityState": "Ann Arbor, MI",
        "Address": "3000 Fuller Rd",
        "Zip": "48105",
        "DateStart": "2026-09-20T14:00:00Z",
        "DateEnd": "2026-09-20T17:00:00Z",
        "AllDay": False,
        "HasTime": True,
        "Free": True,
        "Price": "Free",
        "PriceHigh": None,
        "Tags": [101, 202],
        "Labels": [],
        "Url": "/Calendar/#!/event/12345",
        "latitude": 42.2830,
        "longitude": -83.7160,
        "SmallImg": "https://example.com/small.jpg",
        "MediumImg": "https://example.com/medium.jpg",
        "Images": [],
        "Links": [],
        "ct": {"name": "", "email": "", "phone": "", "org": "Parks Dept"},
        "Tickets": None,
    }
    base.update(overrides)
    return base


# --- datetime normalization --------------------------------------------------

def test_normalize_utc():
    assert _normalize_dt("2026-09-20T14:00:00Z") == "2026-09-20T10:00:00-04:00"


def test_normalize_empty():
    assert _normalize_dt("") == ""
    assert _normalize_dt(None) == ""


def test_normalize_already_offset():
    result = _normalize_dt("2026-09-20T10:00:00-04:00")
    assert result == "2026-09-20T10:00:00-04:00"


# --- HTML stripping ----------------------------------------------------------

def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_handles_entities():
    assert _strip_html("A &amp; B") == "A & B"


# --- event_from_row ----------------------------------------------------------

def test_basic_event():
    event = event_from_row(_row())
    assert event is not None
    assert event.title == "Fall Family Fun Day"
    assert event.source == "cityspark_a2family"
    assert event.venue == "Gallup Park"
    assert event.city == "Ann Arbor"
    assert event.cost == "free"
    assert event.lat == pytest.approx(42.283, abs=0.01)
    assert event.lon == pytest.approx(-83.716, abs=0.01)
    assert event.all_day is False
    assert "crafts" in event.description


def test_event_url():
    event = event_from_row(_row())
    assert event.url == "https://annarborfamily.com/Calendar/#!/event/12345"


def test_all_day_event():
    event = event_from_row(_row(AllDay=True, HasTime=False, DateEnd=None))
    assert event.all_day is True
    assert event.end is None


def test_no_time_marks_all_day():
    event = event_from_row(_row(HasTime=False))
    assert event.all_day is True


def test_paid_event():
    event = event_from_row(_row(Free=False, Price="$15 - $25"))
    assert event.cost == "paid"
    assert event.price == "$15 - $25"


def test_missing_title_returns_none():
    assert event_from_row(_row(Name="")) is None
    assert event_from_row(_row(Name=None)) is None


def test_missing_date_returns_none():
    assert event_from_row(_row(DateStart="")) is None
    assert event_from_row(_row(DateStart=None)) is None


def test_missing_lat_lon():
    event = event_from_row(_row(latitude=None, longitude=None))
    assert event.lat is None
    assert event.lon is None


def test_image_prefers_medium():
    event = event_from_row(_row())
    assert event.image == "https://example.com/medium.jpg"


def test_image_falls_back_to_small():
    event = event_from_row(_row(MediumImg="", SmallImg="https://example.com/small.jpg"))
    assert event.image == "https://example.com/small.jpg"


def test_stable_ids():
    """The same event data produces the same id every time."""
    a = event_from_row(_row())
    b = event_from_row(_row())
    assert a.id == b.id


def test_different_events_different_ids():
    a = event_from_row(_row(Name="Event A"))
    b = event_from_row(_row(Name="Event B"))
    assert a.id != b.id


# --- kidfilter integration ---------------------------------------------------
# These test that the existing kidfilter correctly handles events shaped like
# what the CitySpark adapter produces.

def test_kidfilter_keeps_family_fun_day():
    event = event_from_row(_row(
        Name="Fall Family Fun Day",
        Description="<p>Bring the kids for crafts, bounce houses, and face painting!</p>",
    ))
    keep, reason = verdict(event)
    assert keep is True


def test_kidfilter_keeps_storytime():
    event = event_from_row(_row(
        Name="Storytime at the Library",
        Description="<p>Join us for stories and songs for toddlers and preschoolers.</p>",
    ))
    keep, reason = verdict(event)
    assert keep is True


def test_kidfilter_drops_brewery():
    event = event_from_row(_row(
        Name="Craft Beer Tasting Night",
        Description="<p>Sample local brews at the taproom. 21+ only.</p>",
    ))
    keep, reason = verdict(event)
    assert keep is False


def test_kidfilter_drops_council_meeting():
    event = event_from_row(_row(
        Name="City Council Work Session",
        Description="<p>Regular meeting of the Ann Arbor City Council.</p>",
    ))
    keep, reason = verdict(event)
    assert keep is False


def test_kidfilter_drops_euchre():
    event = event_from_row(_row(
        Name="Friday Night Euchre",
        Description="<p>Weekly euchre tournament at the community center.</p>",
    ))
    keep, reason = verdict(event)
    assert keep is False


def test_kidfilter_drops_football():
    event = event_from_row(_row(
        Name="Wolverines vs Penn State",
        Description="<p>Michigan football at the Big House.</p>",
    ))
    keep, reason = verdict(event)
    assert keep is False


def test_kidfilter_keeps_pumpkin_patch():
    event = event_from_row(_row(
        Name="Pumpkin Patch & Hayride",
        Description="<p>Pick your own pumpkins and enjoy a hayride through the orchard.</p>",
    ))
    keep, reason = verdict(event)
    assert keep is True
