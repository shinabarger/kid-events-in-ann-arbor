"""Trumba calendars, which the City of Ann Arbor uses for Parks & Rec.

The city links people to the RSS version, but the RSS buries the date in a
sentence of prose ("Saturday, September 5, 2026, 7am - 3pm") and gives you
nothing else machine readable. The same calendar is published as iCal at the
same path with a different extension, and that one carries real DTSTART and
DTEND with a timezone, the address as a custom field, and a link to the event's
own page. So that is the one we read.

Two Trumba specific things worth knowing:

- It escapes HTML entities and then escapes the semicolon again for iCal, so
  a non-breaking space arrives as "&#160\;". Decoding has to undo both.
- URL and X-TRUMBA-LINK mean different things. URL is wherever you go to sign
  up, often rec1.com or volunteerhub. X-TRUMBA-LINK is the event's page on the
  city site. The second is what belongs on a "View on Website" button, and the
  first tells us whether the thing needs registration at all.
"""

from __future__ import annotations

import html
import re

from .. import http
from .generic import parse_ics

# Signing up to spread woodchips at a playground is a different activity from
# taking a four year old to the playground, and the city files both here.
VOLUNTEER_HOSTS = ("volunteerhub.com",)
REGISTRATION_HOSTS = ("rec1.com", "volunteerhub.com", "activenet", "eventbrite")


def feed_url(site: dict) -> str:
    """Accept either extension in the config and always read the iCal one."""
    url = site.get("feed") or ""
    return re.sub(r"\.rss(\?|$)", r".ics\1", url) if url.endswith(".rss") else url


# Trumba stamps the venue, the address and the signup link at the top of every
# description, all of which we already have as their own fields. Stripped while
# the <br> delimiters are still there, because once they are spaces there is no
# way to tell where the boilerplate ends and the real copy begins.
BOILERPLATE = re.compile(
    r"^\s*(?:(?:Location|Address|Link)\s*:\s*[^<]*(?:<br\s*/?>\s*)+)+",
    re.I,
)


def clean(text: str) -> str:
    """Trumba's doubled escaping, then the boilerplate, then the HTML."""
    if not text:
        return ""
    text = text.replace("\\;", ";")
    text = html.unescape(text)
    text = BOILERPLATE.sub("", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"</?(?:li|ul|ol|p|div)[^>]*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\bLink:\s*https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def custom_fields(block: str) -> dict:
    """X-TRUMBA-CUSTOMFIELD;NAME="Address";ID=..;TYPE=..:1055 Longshore Drive"""
    found = {}
    for match in re.finditer(
        r'X-TRUMBA-CUSTOMFIELD;NAME="([^"]+)"[^:]*:(.*)', block
    ):
        found.setdefault(match.group(1).strip().lower(), match.group(2).strip())
    return found


def _host_in(url: str, hosts) -> bool:
    return any(h in (url or "").lower() for h in hosts)


def parse(text: str, site: dict) -> list:
    events = parse_ics(text, site)

    # parse_ics does not know about Trumba's extras, so walk the raw blocks
    # again in the same order and fill them in.
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfolded, re.DOTALL)
    by_uid = {}
    for block in blocks:
        uid = re.search(r"^UID:(.*)$", block, re.M)
        if uid:
            by_uid[uid.group(1).strip()] = block

    keyed = list(by_uid.values())
    for index, event in enumerate(events):
        block = keyed[index] if index < len(keyed) else ""
        fields = custom_fields(block)

        event.title = clean(event.title)
        event.description = clean(event.description)
        event.venue = clean(event.venue) or fields.get("location", "")
        event.address = fields.get("address", "")
        if event.address and event.venue and event.address != event.venue:
            event.address = f"{event.address}, Ann Arbor, MI"

        signup = event.url or ""
        page = re.search(r"^X-TRUMBA-LINK:(.*)$", block, re.M)
        event.url = page.group(1).strip() if page else signup
        if signup and _host_in(signup, REGISTRATION_HOSTS):
            event.registration = True

        # Recorded so kidfilter can tell a volunteer shift from an outing.
        if signup and _host_in(signup, VOLUNTEER_HOSTS):
            event.volunteer = True

        event.categories = [clean(c) for c in event.categories if c]
        event.image = ""

    return events


def harvest(site: dict) -> list:
    return parse(http.get(feed_url(site)), site)
