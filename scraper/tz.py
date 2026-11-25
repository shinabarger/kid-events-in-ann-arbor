"""Eastern time, done properly.

Every source used to guess the offset from the month: -04:00 for March through
November, -05:00 otherwise. Daylight time actually ends on the first Sunday in
November and starts on the second Sunday in March, so for most of November and
the first part of March every event was stamped an hour wrong, and the site
showed a 10:30 storytime at 9:30. Ask the tz database instead.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/Detroit")


def eastern_offset(dt: datetime) -> str:
    """The UTC offset for a wall clock time in Ann Arbor, as "-04:00" or "-05:00".

    dt is read as Eastern wall clock time. Any tzinfo on it is ignored, because
    the callers are all stamping a time the source printed for Ann Arbor.
    """
    local = dt.replace(tzinfo=EASTERN)
    seconds = int(local.utcoffset().total_seconds())
    sign = "-" if seconds < 0 else "+"
    hours, minutes = divmod(abs(seconds) // 60, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def as_eastern(value) -> str:
    """A hand typed time, read as Ann Arbor wall clock, with the right offset.

    Takes "2026-11-14T10:00", "2026-11-14T10:00:00-04:00" or a datetime (YAML
    parses an unquoted timestamp into one). Whatever offset was typed is
    replaced, because the clock time is what the organizer published and the
    offset is the part people guess wrong.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        dt, is_utc = value, value.tzinfo is not None and value.utcoffset().total_seconds() == 0
    else:
        text = str(value).strip()
        is_utc = text.endswith(("Z", "+00:00"))
        dt = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    if is_utc:
        # A real UTC time, not a guessed offset: convert rather than relabel.
        return dt.astimezone(EASTERN).isoformat(timespec="seconds")
    wall = dt.replace(tzinfo=None)
    return wall.strftime("%Y-%m-%dT%H:%M:%S") + eastern_offset(wall)
