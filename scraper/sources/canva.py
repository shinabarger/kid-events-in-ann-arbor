"""Calendars published as a Canva Sites page.

The Mamas Network is the reason this exists, and the shape of the problem is
worth writing down because it is not obvious from looking at the page.

Their events page renders as a picture of a month: event names floating on a
grid, no dates attached to the text, no feed, no JSON-LD, and in the rendered
DOM a pile of unclassed <p> tags at absolute positions. It looks unscrapeable.

It is not. Canva ships the whole document as JSON inside the HTML, in a
window['bootstrap'] = JSON.parse('...') blob, so a plain GET gets everything
and no browser is needed. Every text box in there carries its x and y on the
canvas, its lines of text, and any link attached to it. That is enough to
rebuild the calendar, because the day numbers are text boxes too.

The grid is transposed from what you would expect: each column is a week and
each row is a day of the week, running down the page. None of that has to be
assumed though. The day numbers say which cell is which date, so the mapping
is read off the page rather than guessed, and it survives a rearrangement.

An event box sits slightly down and to the right of its day number, always by
less than one cell. So each one is assigned to the last column whose x is at
or before it, and the last row whose y is at or before it.
"""

from __future__ import annotations

import codecs
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import http
from ..models import Event

TZ = ZoneInfo("America/Detroit")

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

TITLE_RE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\b.*calendar of events", re.I)
DAY_RE = re.compile(r"^\d{1,2}$")
TIME_RE = re.compile(
    r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:-|–|—|to)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
START_ONLY_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)

BOOTSTRAP_RE = re.compile(r"window\[['\"]bootstrap['\"]\]\s*=\s*JSON\.parse\('")

# A link on the box tells us whether you have to book. A ticketing host means
# yes; a link to their own page about the event does not.
TICKETING_HOSTS = ("zeffy.com", "eventbrite.", "docs.google.com/forms",
                   "ticketleap", "givebutter", "rec1.com")


class ParseError(RuntimeError):
    pass


# --- getting the document out of the page --------------------------------

def _js_string(html: str, start: int) -> str:
    """Read a single quoted JS literal from `start`, honouring backslashes."""
    out = []
    i, escaped = start, False
    while i < len(html):
        ch = html[i]
        if escaped:
            out.append("\\" + ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == "'":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def extract_document(html: str) -> dict:
    match = BOOTSTRAP_RE.search(html)
    if not match:
        raise ParseError("no Canva bootstrap blob on the page")
    literal = _js_string(html, match.end())
    # It is a JS string literal, so \' and \uXXXX have to come out before it
    # is valid JSON.
    decoded = codecs.decode(literal.replace(r"\'", "'"), "unicode_escape")
    decoded = decoded.encode("latin-1", "ignore").decode("utf-8", "ignore")
    try:
        return json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ParseError(f"bootstrap blob did not parse: {exc}") from exc


def text_boxes(node, out=None, depth=0):
    """Every positioned text box in the document."""
    if out is None:
        out = []
    if depth > 60 or not isinstance(node, (dict, list)):
        return out
    if isinstance(node, list):
        for item in node:
            text_boxes(item, out, depth + 1)
        return out

    body = node.get("a")
    if (isinstance(body, dict) and isinstance(body.get("C"), dict)
            and isinstance(body["C"].get("A"), list) and body["C"]["A"]
            and isinstance(node.get("A"), (int, float))
            and isinstance(node.get("B"), (int, float))):
        spans = body["C"].get("C") or []
        link = next((s.get("Q") for s in spans
                     if isinstance(s, dict) and s.get("Q")), "")
        lines = [str(line).replace("\n", "").strip() for line in body["C"]["A"]]
        out.append({
            "x": round(float(node["A"])), "y": round(float(node["B"])),
            "lines": [line for line in lines if line], "link": link or "",
        })

    for value in node.values():
        if isinstance(value, (dict, list)):
            text_boxes(value, out, depth + 1)
    return out


# --- rebuilding the grid -------------------------------------------------

def cluster(values, tolerance: int = 14) -> dict:
    """Snap near identical coordinates onto one tick.

    The day numbers are not pixel aligned: a row of them can sit at 941, 942
    and 943, and a column at 432 and 436. Left alone that produces a grid of
    ticks that no cell actually matches, and every event falls through.
    """
    ordered = sorted(set(values))
    canonical, group = {}, []
    for value in ordered:
        if group and value - group[0] > tolerance:
            for member in group:
                canonical[member] = group[0]
            group = []
        group.append(value)
    for member in group:
        canonical[member] = group[0] if group else member
    return canonical


def _floor_to(value: int, ticks: list, slack: int = 10):
    """The last tick at or before value, allowing a little overshoot upward."""
    best = None
    for tick in ticks:
        if tick <= value + slack and (best is None or tick > best):
            best = tick
    return best


def day_cells(boxes: list, month: int, year: int) -> dict:
    """(column x, row y) -> date, read off the day numbers themselves.

    The grid usually spills into the next month at the end, where the numbers
    restart at 1. Walking them in calendar order makes that obvious.
    """
    numbers = [b for b in boxes
               if len(b["lines"]) == 1 and DAY_RE.fullmatch(b["lines"][0])]
    if not numbers:
        raise ParseError("no day numbers in the grid")

    # Columns are weeks and rows are days, so calendar order is column by
    # column, top to bottom.
    columns = cluster(b["x"] for b in numbers)
    rows = cluster(b["y"] for b in numbers)
    numbers.sort(key=lambda b: (columns[b["x"]], rows[b["y"]]))

    cells, previous = {}, 0
    for box in numbers:
        day = int(box["lines"][0])
        if day < previous:
            month += 1
            if month > 12:
                month, year = 1, year + 1
        previous = day
        try:
            cells[(columns[box["x"]], rows[box["y"]])] = datetime(year, month, day).date()
        except ValueError:
            continue
    return cells


def _clock(hour: int, minute, suffix, fallback_suffix) -> tuple:
    suffix = (suffix or fallback_suffix or "").lower()
    hour = hour % 12
    if suffix == "pm":
        hour += 12
    return hour, int(minute or 0)


def parse_block(lines: list):
    """["9:00am - 11:00am", "DADaS & LITTLES", "Little Break Cowork"]"""
    if len(lines) < 2:
        return None
    match = TIME_RE.match(lines[0])
    if match:
        start_h, start_m, start_ap, end_h, end_m, end_ap = match.groups()
        start = _clock(int(start_h), start_m, start_ap, end_ap)
        end = _clock(int(end_h), end_m, end_ap, end_ap)
    else:
        match = START_ONLY_RE.match(lines[0])
        if not match:
            return None
        start = _clock(int(match.group(1)), match.group(2), match.group(3), None)
        end = None

    rest = lines[1:]
    venue = rest[-1] if len(rest) > 1 else ""
    title_lines = rest[:-1] if len(rest) > 1 else rest
    title = " ".join(part.strip() for part in title_lines if part.strip())
    if not title:
        return None
    return {"start": start, "end": end, "title": title, "venue": venue.strip()}


def build(html: str, site: dict) -> list:
    return build_from_document(extract_document(html), site)


def build_from_document(document: dict, site: dict) -> list:
    boxes = text_boxes(document)

    title = next((b for b in boxes
                  if b["lines"] and TITLE_RE.search(" ".join(b["lines"]))), None)
    if not title:
        raise ParseError("no '<Month> <Year> Calendar of Events' heading")
    heading = TITLE_RE.search(" ".join(title["lines"]))
    month, year = MONTHS[heading.group(1).lower()], int(heading.group(2))

    cells = day_cells(boxes, month, year)
    columns = sorted({x for x, _ in cells})
    rows = sorted({y for _, y in cells})

    events, seen = [], set()
    for box in boxes:
        block = parse_block(box["lines"])
        if not block:
            continue
        column = _floor_to(box["x"], columns)
        row = _floor_to(box["y"], rows)
        day = cells.get((column, row)) if column is not None and row is not None else None
        if day is None:
            continue

        start = datetime(day.year, day.month, day.day, *block["start"], tzinfo=TZ)
        end = (datetime(day.year, day.month, day.day, *block["end"], tzinfo=TZ)
               if block["end"] else None)
        if end and end <= start:
            end = None

        # The page is emitted once per layout breakpoint, so the same event
        # turns up twice at different coordinates.
        key = (start.isoformat(), block["title"].lower())
        if key in seen:
            continue
        seen.add(key)

        # A grid cell has room for a time, a name and a venue, and nothing
        # else, so there is never an age on the page. The config supplies it
        # by title, which is the only place that knowledge exists.
        audience = ""
        for hint in site.get("ages", []) or []:
            if re.search(hint["match"], block["title"], re.I):
                audience = hint["text"]
                break

        house = block["venue"] in ("", site.get("venue", ""))
        events.append(Event(
            title=block["title"],
            start=start.isoformat(),
            end=end.isoformat() if end else None,
            venue=block["venue"] or site.get("venue", ""),
            address=site.get("address", "") if house else "",
            city=site.get("city", "") if house else "",
            url=box["link"] or site.get("url", ""),
            audience_raw=audience,
            registration=any(h in box["link"] for h in TICKETING_HOSTS),
            source=site["key"],
            source_name=site["name"],
        ))
    return events


def harvest(site: dict) -> list:
    return build(http.get(site["listing"]), site)
