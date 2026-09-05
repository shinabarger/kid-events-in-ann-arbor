"""The rules that keep this a pointer rather than a copy, and the robots.txt
obedience that keeps it welcome. Both exist to make sure a nonprofit's first
contact with this project is a thank you and not a letter."""

import os
import textwrap

import pytest

from scraper import courtesy, robots
from scraper.models import Event


def make(**kw):
    base = dict(title="Storytime", start="2026-09-05T10:30:00-04:00",
                source="aadl", venue="Downtown Library", url="https://aadl.org/node/1")
    base.update(kw)
    return Event(**base)


# --- excerpts ------------------------------------------------------------

def test_a_short_description_is_left_exactly_as_written():
    text = "Songs, bubbles, and twenty minutes of chaos."
    assert courtesy.excerpt(text) == text


def test_a_long_description_is_cut_at_a_sentence():
    text = ("Join us for stories and songs. " * 20).strip()
    out = courtesy.excerpt(text)
    assert len(out) <= courtesy.EXCERPT_LIMIT
    assert out.endswith("."), "cutting mid sentence reads like a bug"
    assert not out.endswith("...")


def test_a_wall_of_text_with_no_sentence_breaks_still_cuts_on_a_word():
    out = courtesy.excerpt("word " * 200)
    assert len(out) <= courtesy.EXCERPT_LIMIT + 3
    assert out.endswith("...")
    assert " wor..." not in out, "never cut mid word"


def test_the_excerpt_is_short_enough_to_not_substitute_for_the_original():
    assert courtesy.EXCERPT_LIMIT <= 400, (
        "past a few sentences this stops being a pointer and starts being a copy"
    )


def test_images_are_never_carried_over():
    events = courtesy.apply([make(image="https://example.org/photo.jpg")],
                            courtesy.load_optout())
    assert events[0].image == "", "somebody else's photograph is the clearest thing we do not own"


# --- opt out -------------------------------------------------------------

@pytest.fixture
def rules(tmp_path):
    path = tmp_path / "optout.yaml"
    path.write_text(textwrap.dedent("""
        sources: [reced]
        domains: [example.org]
        venues: ["Quiet Place"]
        titles: ["^Private "]
    """))
    return courtesy.load_optout(str(path))


def test_a_whole_source_can_opt_out(rules):
    assert courtesy.is_opted_out(make(source="reced"), rules)
    assert not courtesy.is_opted_out(make(source="aadl"), rules)


def test_a_domain_opt_out_covers_subdomains(rules):
    assert courtesy.is_opted_out(make(url="https://www.example.org/a"), rules)
    assert courtesy.is_opted_out(make(url="https://events.example.org/a"), rules)
    assert not courtesy.is_opted_out(make(url="https://notexample.org/a"), rules)


def test_a_venue_and_a_title_pattern_both_work(rules):
    assert courtesy.is_opted_out(make(venue="Quiet Place"), rules)
    assert courtesy.is_opted_out(make(title="Private birthday party"), rules)
    assert not courtesy.is_opted_out(make(title="Very private joke"), rules)


def test_apply_drops_the_opted_out_and_keeps_the_rest(rules):
    kept = courtesy.apply([make(source="reced"), make(source="aadl")], rules)
    assert [e.source for e in kept] == ["aadl"]


def test_the_shipped_optout_file_parses():
    """It is empty on purpose, but it has to be readable or the run dies."""
    loaded = courtesy.load_optout()
    assert set(loaded) == {"sources", "venues", "domains", "titles"}


# --- robots --------------------------------------------------------------

class FakeParser:
    def __init__(self, allow=True, delay=None):
        self.allow, self.delay = allow, delay

    def can_fetch(self, agent, url):
        return self.allow

    def crawl_delay(self, agent):
        return self.delay


def test_a_disallowed_url_is_not_fetched(monkeypatch):
    robots.reset()
    monkeypatch.setattr(robots, "_parser", lambda url: FakeParser(allow=False))
    assert robots.allowed("https://example.org/events") is False


def test_no_robots_file_means_allowed(monkeypatch):
    robots.reset()
    monkeypatch.setattr(robots, "_parser", lambda url: None)
    assert robots.allowed("https://example.org/events") is True


def test_a_crawl_delay_is_honored_but_capped(monkeypatch):
    robots.reset()
    monkeypatch.setattr(robots, "_parser", lambda url: FakeParser(delay=3))
    assert robots.crawl_delay("https://example.org/") == 3.0
    robots.reset()
    monkeypatch.setattr(robots, "_parser", lambda url: FakeParser(delay=600))
    assert robots.crawl_delay("https://example.org/") == 10.0, (
        "one site asking for ten minutes should not stall the whole run"
    )


def test_the_fetcher_refuses_a_disallowed_url(monkeypatch, tmp_path):
    from scraper import http

    monkeypatch.setenv("SCRAPE_CACHE", str(tmp_path))
    monkeypatch.setattr(http, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(http.robots, "allowed", lambda url: False)

    def explode(*a, **kw):
        raise AssertionError("a disallowed URL must never reach the network")

    monkeypatch.setattr(http.requests, "get", explode)
    with pytest.raises(http.Disallowed):
        http.get("https://example.org/nope")


def test_the_user_agent_says_who_we_are_and_how_to_reach_us():
    from scraper import http

    agent = http.USER_AGENT
    assert "kid-events-in-ann-arbor" in agent
    assert "http" in agent, "a contact link means they can email instead of lawyer up"
    assert "robots.txt" in agent


# --- the source list itself ----------------------------------------------

def test_every_source_declares_how_we_are_allowed_to_read_it():
    """A source with no stated basis is a source nobody thought about."""
    import yaml

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "sources.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        sites = yaml.safe_load(fh)["sites"]

    allowed = {"feed", "public-api", "crawl"}
    for site in sites:
        basis = (site.get("access") or "").split()[0] if site.get("access") else ""
        assert basis in allowed, (
            f"{site['key']} has no access basis. Pick one of {sorted(allowed)}, "
            "or take the source out."
        )


def test_no_source_points_at_a_login_or_an_internal_api():
    import yaml

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "sources.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        # Comments explain the rule, so only the actual config is scanned.
        raw = "\n".join(line.split("#")[0] for line in fh).lower()

    for needle in ("facebook.com", "login", "graph.", "/internal/", "api_key", "apikey"):
        assert needle not in raw, (
            f"{needle} in sources.yaml, which is the shape of a source we do not take"
        )
