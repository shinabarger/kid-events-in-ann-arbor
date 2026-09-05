"""Polite HTTP with a disk cache so reruns do not hammer anybody's server."""

from __future__ import annotations

import hashlib
import os
import time

import requests

from . import robots

CACHE_DIR = os.environ.get("SCRAPE_CACHE", ".cache")
CACHE_TTL = int(os.environ.get("SCRAPE_CACHE_TTL", "3600"))
DELAY = float(os.environ.get("SCRAPE_DELAY", "0.4"))
TIMEOUT = int(os.environ.get("SCRAPE_TIMEOUT", "30"))
OFFLINE = os.environ.get("SCRAPE_OFFLINE") == "1"

# A real name, a link to the source, and a way to reach a person. If we are
# ever doing something a site does not want, they should be able to say so in
# one email instead of one letter from a lawyer.
CONTACT = os.environ.get(
    "SCRAPE_CONTACT",
    "https://github.com/shinabarger/kid-events-in-ann-arbor/issues",
)
USER_AGENT = (
    f"kid-events-in-ann-arbor/1.0 (+{CONTACT}) "
    "non-commercial family events aggregator, one pass per day, obeys robots.txt"
)

_last_call = {"t": 0.0}


class FetchError(RuntimeError):
    pass


class Disallowed(FetchError):
    """robots.txt said no. Not an error to retry, an answer to respect."""


def _cache_path(url: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha1(url.encode("utf-8")).hexdigest() + ".txt")


def get(url: str, *, retries: int = 2) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)

    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if OFFLINE or age < CACHE_TTL:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()

    if OFFLINE:
        raise FetchError(f"offline and nothing cached for {url}")

    # Ask permission before every single request, not once per site, because a
    # site can disallow one path and welcome another.
    if not robots.allowed(url):
        raise Disallowed(f"robots.txt disallows {url}")

    last_error = None
    for attempt in range(retries + 1):
        gap = time.time() - _last_call["t"]
        if gap < DELAY:
            time.sleep(DELAY - gap)
        robots.wait_for_host(url)
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            _last_call["t"] = time.time()
            robots.note_fetch(url)
            if response.status_code in (401, 403):
                # Locked or unwelcome. Retrying is how a polite crawler turns
                # into a rude one, so stop here.
                raise Disallowed(f"{response.status_code} from {url}")
            if response.status_code >= 500:
                raise FetchError(f"{response.status_code} from {url}")
            response.raise_for_status()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(response.text)
            return response.text
        except Disallowed:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad source should not kill the run
            last_error = exc
            time.sleep(1.5 * (attempt + 1))

    raise FetchError(f"could not fetch {url}: {last_error}")


def get_json(url: str):
    import json

    return json.loads(get(url))
