"""Ann Arbor District Library.

AADL runs Drupal and exposes taxonomy-filtered listings at /events-feed/<term>.
The listing rows already carry title, date, time, room, and the "For Whom"
line, which is the cleanest age data of any source I found, so I parse the
listing and only hit the detail page when I need the description.

Term ids (from the filter links on aadl.org/events):
  33780 All Ages      33781 Babies      33782 Preschool
  33783 Elementary    33784 Teen        119652 For Kids (rollup)
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .. import http
from ..models import Event

BASE = "https://aadl.org"
SOURCE = "aadl"
SOURCE_NAME = "Ann Arbor District Library"

# The rollup feed plus the individual age feeds. Overlap is fine, dedupe
# handles it, and running them all is how the babies-only programs get caught.
FEEDS = {
    "kids": "119652",
    "all_ages": "33780",
    "babies": "33781",
    "preschool": "33782",
    "elementary": "33783",
    "teen": "33784",
}

MAX_PAGES = 8

DATE_RE = re.compile(
    r"(?P<weekday>\w+day)\s+(?P<month>\w+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})"
    r"(?::\s*(?P<start>\d{1,2}:\d{2}\s*[ap]m)"
    r"(?:\s*to\s*(?P<end>\d{1,2}:\d{2}\s*[ap]m))?)?",
    re.IGNORECASE,
)


def _parse_time(day: datetime, token: str | None) -> datetime | None:
    if not token:
        return None
    token = token.strip().lower().replace(" ", "")
    try:
        t = datetime.strptime(token, "%I:%M%p")
    except ValueError:
        return None
    return day.replace(hour=t.hour, minute=t.minute)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    # AADL is always Eastern. Offset flips with DST.
    offset = "-04:00" if 3 <= dt.month <= 11 else "-05:00"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset


def parse_listing(html: str) -> list:
    """Pull events out of one /events-feed/ page."""
    soup = BeautifulSoup(html, "html.parser")
    events = []

    for row in soup.select(".views-row"):
        link = row.select_one("h2 a")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = link.get("href", "")
        url = href if href.startswith("http") else BASE + href

        body = row.select_one(".node-body")
        if not body:
            continue

        # The meta paragraph is "<date/time><br><room><br><for whom>". The
        # date itself wraps across a newline in the source, so split on the
        # <br> tags and not on whitespace.
        para = body.find("p")
        lines = []
        if para:
            buffer = []
            for node in para.children:
                if getattr(node, "name", None) == "br":
                    chunk = " ".join(" ".join(buffer).split())
                    if chunk:
                        lines.append(chunk)
                    buffer = []
                else:
                    text = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node)
                    if text.strip():
                        buffer.append(text)
            chunk = " ".join(" ".join(buffer).split())
            if chunk:
                lines.append(chunk)

        blob = " ".join(lines)
        match = DATE_RE.search(blob)
        if not match:
            continue

        try:
            day = datetime.strptime(
                f"{match.group('month')} {match.group('day')} {match.group('year')}", "%B %d %Y"
            )
        except ValueError:
            continue

        start = _parse_time(day, match.group("start")) or day
        end = _parse_time(day, match.group("end"))
        all_day = match.group("start") is None

        # Whatever follows the date line: room first, audience last.
        tail = [line for line in lines if not DATE_RE.search(line)]
        venue = tail[0] if tail else ""
        audience = tail[-1] if len(tail) > 1 else ""

        kind = row.select_one(".mat-type-icon p")

        events.append(
            Event(
                title=title,
                start=_iso(start),
                end=_iso(end),
                all_day=all_day,
                url=url,
                venue=venue,
                audience_raw=audience,
                source=SOURCE,
                source_name=SOURCE_NAME,
                cost="free",
                price="Free",
                categories=[kind.get_text(strip=True)] if kind else [],
                setting="indoor",
            )
        )

    return events


def parse_detail(html: str) -> str:
    """Just the description paragraph off an event node page."""
    soup = BeautifulSoup(html, "html.parser")
    for heading in soup.find_all(["h2", "h3", "strong"]):
        if heading.get_text(strip=True).lower() == "description":
            parts = []
            for sib in heading.find_all_next(["p", "h2", "h3"]):
                if sib.name in ("h2", "h3"):
                    break
                text = sib.get_text(" ", strip=True)
                if text:
                    parts.append(text)
            return " ".join(parts)[:1500]
    return ""


def fetch(with_descriptions: bool = True) -> list:
    seen = {}
    for term in FEEDS.values():
        for page in range(MAX_PAGES):
            url = f"{BASE}/events-feed/{term}?page={page}"
            try:
                html = http.get(url)
            except http.FetchError:
                break
            batch = parse_listing(html)
            if not batch:
                break
            for event in batch:
                seen.setdefault(event.id, event)

    events = list(seen.values())

    if with_descriptions:
        # One fetch per distinct node, not per occurrence.
        by_url = {}
        for event in events:
            by_url.setdefault(event.url, []).append(event)
        for url, group in by_url.items():
            try:
                text = parse_detail(http.get(url))
            except http.FetchError:
                continue
            for event in group:
                event.description = text

    return events
