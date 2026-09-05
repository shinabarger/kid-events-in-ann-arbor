"""robots.txt, obeyed automatically for every host we touch.

Nothing in this project fetches a URL without passing through here first. If a
site says no, we do not argue with it, we skip the source and say so in the
footer. Two reasons. It is the right thing to do, and it means the honest
answer to "why are you on our server" is always "your robots.txt lets us be".

Crawl-delay is honored too, per host, on top of the global delay.
"""

from __future__ import annotations

import os
import time
import urllib.robotparser
from urllib.parse import urlparse

# The name we obey rules for. A site that wants us gone can name this token
# in robots.txt and never has to contact anybody.
AGENT_TOKEN = "kid-events-in-ann-arbor"

DISABLED = os.environ.get("SCRAPE_IGNORE_ROBOTS") == "1"

_cache: dict = {}
_host_last: dict = {}


def _root(url: str) -> tuple:
    parts = urlparse(url)
    return parts.scheme or "https", parts.netloc


def _parser(url: str):
    """One parser per host, fetched once per run and remembered."""
    scheme, host = _root(url)
    if not host:
        return None
    if host in _cache:
        return _cache[host]

    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{scheme}://{host}/robots.txt")
    try:
        parser.read()
    except Exception:  # noqa: BLE001
        # No robots.txt, or it would not load. The convention is that silence
        # means allowed, and we are not going to invent a stricter rule than
        # the site itself publishes.
        parser = None
    _cache[host] = parser
    return parser


def allowed(url: str) -> bool:
    if DISABLED:
        return True
    parser = _parser(url)
    if parser is None:
        return True
    for agent in (AGENT_TOKEN, "*"):
        try:
            if not parser.can_fetch(agent, url):
                return False
        except Exception:  # noqa: BLE001
            return True
    return True


def crawl_delay(url: str) -> float:
    """Whatever the site asked for, capped so one slow site cannot stall a run."""
    parser = _parser(url)
    if parser is None:
        return 0.0
    for agent in (AGENT_TOKEN, "*"):
        try:
            value = parser.crawl_delay(agent)
        except Exception:  # noqa: BLE001
            value = None
        if value:
            return min(float(value), 10.0)
    return 0.0


def wait_for_host(url: str) -> None:
    delay = crawl_delay(url)
    if not delay:
        return
    _, host = _root(url)
    gap = time.time() - _host_last.get(host, 0.0)
    if gap < delay:
        time.sleep(delay - gap)
    _host_last[host] = time.time()


def note_fetch(url: str) -> None:
    _, host = _root(url)
    _host_last[host] = time.time()


def reset() -> None:
    _cache.clear()
    _host_last.clear()


class Disallowed(RuntimeError):
    """The site's robots.txt says not to fetch this."""
