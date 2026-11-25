"""Daylight saving time.

Every source used to guess the offset from the month, -04:00 for March through
November. DST ends the first Sunday in November and starts the second Sunday
in March, so most of November and early March came out an hour wrong and the
site showed a 10:30 storytime at 9:30. These pin the switch dates and make
sure the guess does not come back.
"""

import os
import re
from datetime import date, datetime

import pytest

from scraper.sources import aadl, annarborwithkids, cityspark, generic, localhop, observer, umich, washtenaw
from scraper.sources import recurring
from scraper.tz import as_eastern, eastern_offset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("when, offset", [
    # Fall back: 2am on Sunday Nov 1, 2026.
    (datetime(2026, 10, 31, 10, 30), "-04:00"),
    (datetime(2026, 11, 1, 0, 30), "-04:00"),
    (datetime(2026, 11, 1, 10, 30), "-05:00"),
    (datetime(2026, 11, 25, 10, 30), "-05:00"),
    (datetime(2026, 12, 15, 10, 30), "-05:00"),
    # Spring forward: 2am on Sunday Mar 14, 2027.
    (datetime(2027, 3, 1, 10, 30), "-05:00"),
    (datetime(2027, 3, 13, 10, 30), "-05:00"),
    (datetime(2027, 3, 14, 10, 30), "-04:00"),
    (datetime(2027, 6, 1, 10, 30), "-04:00"),
    # Fall back moves to Nov 7 in 2027.
    (datetime(2027, 11, 6, 10, 30), "-04:00"),
    (datetime(2027, 11, 7, 10, 30), "-05:00"),
])
def test_offset_follows_the_switch_dates(when, offset):
    assert eastern_offset(when) == offset


def test_every_parser_stamps_late_november_as_standard_time():
    when = datetime(2026, 11, 15, 10, 30)
    assert aadl._iso(when).endswith("-05:00")
    assert observer._iso(2026, 11, 15, (10, 30)).endswith("-05:00")
    assert umich._iso("2026-11-15", "10:30:00").endswith("-05:00")
    assert annarborwithkids._dt("20261115T103000", "")[0].endswith("-05:00")
    assert generic._ics_dt("20261115T103000", "").endswith("-05:00")
    assert generic._normalize_dt("2026-11-15T10:30:00").endswith("-05:00")
    assert generic._normalize_dt("2026-11-15").endswith("-05:00")
    assert generic._tribe_dt("2026-11-15 10:30:00").endswith("-05:00")
    assert cityspark._normalize_dt("2026-11-15T10:30:00Z").endswith("-05:00")


def test_every_parser_stamps_early_march_as_standard_time():
    when = datetime(2027, 3, 5, 10, 30)
    assert aadl._iso(when).endswith("-05:00")
    assert umich._iso("2027-03-05", "10:30:00").endswith("-05:00")
    assert generic._ics_dt("20270305T103000", "").endswith("-05:00")


@pytest.mark.parametrize("module", [localhop, washtenaw])
def test_utc_from_an_api_lands_on_the_right_local_hour(module):
    # 15:30 UTC is 10:30 in November and 11:30 in October.
    assert module._parse_api_dt("2026-11-15T15:30:00.000Z") == "2026-11-15T10:30:00-05:00"
    assert module._parse_api_dt("2026-10-15T15:30:00.000Z") == "2026-10-15T11:30:00-04:00"


def test_a_hand_typed_offset_is_corrected():
    assert as_eastern("2026-11-14T10:00:00-04:00") == "2026-11-14T10:00:00-05:00"
    assert as_eastern("2027-03-14T10:00") == "2027-03-14T10:00:00-04:00"
    assert as_eastern("2026-11-14T15:00:00Z") == "2026-11-14T10:00:00-05:00"


def test_a_weekly_series_keeps_its_clock_time_across_both_switches(tmp_path):
    path = tmp_path / "recurring.yaml"
    path.write_text(
        "series:\n  - key: x\n    name: X\n    events:\n"
        "      - {title: T, rule: every sunday, time: '10:30-11:00'}\n"
    )
    events = recurring.fetch(str(path), days=200, today=date(2026, 10, 20))
    for event in events:
        when = datetime.fromisoformat(event.start)
        assert when.strftime("%H:%M") == "10:30", event.start
        assert event.start.endswith(eastern_offset(when.replace(tzinfo=None)))


def test_nobody_guesses_the_offset_from_the_month_again():
    guess = re.compile(r"""["']-0[45]:00["']\s+if|-[45]\s+if\s+3\s*<=""")
    offenders = []
    for folder in ("scraper", "scripts"):
        for base, _, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                if name.endswith(".py"):
                    path = os.path.join(base, name)
                    with open(path, encoding="utf-8") as fh:
                        if guess.search(fh.read()):
                            offenders.append(os.path.relpath(path, ROOT))
    assert not offenders, "use scraper.tz.eastern_offset in: " + ", ".join(offenders)
