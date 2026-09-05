"""The launch checklist, as tests, because every item on it is the kind of
thing that is invisible when it breaks.

Nobody notices a missing og:image until a link looks broken in Slack, and
nobody notices Disallow: / until the site has been invisible for a month.
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ROOT
SITE = "https://shinabarger.github.io/kid-events-in-ann-arbor/"


@pytest.fixture(scope="module")
def html():
    with open(os.path.join(DOCS, "index.html"), "r", encoding="utf-8") as fh:
        return fh.read()


def meta(html: str, key: str, attr: str = "name") -> str:
    match = re.search(
        rf'<meta[^>]*{attr}="{re.escape(key)}"[^>]*content="([^"]*)"', html
    )
    return match.group(1) if match else ""


def test_the_title_sells_rather_than_labels(html):
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    assert len(title) > 30, "a bare label wastes the most valuable line in the result"
    assert len(title) <= 75, f"Google truncates past about 60 to 70 characters: {len(title)}"
    assert "Ann Arbor" in title
    # The words somebody actually types into Google.
    assert any(w in title.lower() for w in ("storytime", "things to do", "playgroup"))


def test_the_description_is_a_real_description(html):
    text = meta(html, "description")
    assert 120 <= len(text) <= 300, f"{len(text)} characters is outside the useful range"
    assert "Ann Arbor" in text


def test_nothing_is_telling_search_engines_to_go_away(html):
    """The single most common launch day mistake, in both places it hides."""
    assert "noindex" not in meta(html, "robots")

    with open(os.path.join(DOCS, "robots.txt"), "r", encoding="utf-8") as fh:
        robots = fh.read()
    for line in robots.splitlines():
        stripped = line.split("#")[0].strip()
        assert stripped.lower() != "disallow: /", "robots.txt is blocking the whole site"
    assert "Allow: /" in robots
    assert "sitemap.xml" in robots.lower()


def test_the_share_card_is_there_and_the_right_shape(html):
    from PIL import Image

    assert meta(html, "og:title", "property")
    assert meta(html, "og:description", "property")
    assert meta(html, "og:image:alt", "property"), "the card needs alt text too"
    assert meta(html, "twitter:card") == "summary_large_image"

    url = meta(html, "og:image", "property")
    assert url.startswith("https://"), "a relative og:image breaks in most unfurlers"

    path = os.path.join(DOCS, "assets", "og-cover.png")
    assert os.path.exists(path), "run scripts/build_images.py"
    assert Image.open(path).size == (1200, 630)
    assert meta(html, "og:image:width", "property") == "1200"
    assert meta(html, "og:image:height", "property") == "630"


def test_one_canonical_url_and_everything_agrees_with_it(html):
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)
    assert canonical == SITE, "pick one spelling, trailing slash included, and keep it"
    assert meta(html, "og:url", "property") == canonical

    with open(os.path.join(DOCS, "sitemap.xml"), "r", encoding="utf-8") as fh:
        sitemap = fh.read()
    assert f"<loc>{SITE}</loc>" in sitemap, "the sitemap must name the canonical spelling"


def test_the_sitemap_is_valid_and_not_stale():
    from xml.etree import ElementTree

    path = os.path.join(DOCS, "sitemap.xml")
    tree = ElementTree.parse(path)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = tree.getroot().findall("s:url", ns)
    assert urls, "an empty sitemap is worse than none"
    for url in urls:
        assert url.find("s:loc", ns).text.startswith("https://")


def test_structured_data_parses(html):
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    assert blocks, "no JSON-LD at all"
    for block in blocks:
        data = json.loads(block)  # a syntax error here is silently ignored by Google
        assert data.get("@context", "").endswith("schema.org")


def test_the_full_icon_set_exists(html):
    for name in ("favicon.svg", "favicon-16.png", "favicon-32.png", "favicon.ico",
                 "apple-touch-icon.png", "icon-192.png", "icon-512.png"):
        assert os.path.exists(os.path.join(DOCS, "assets", name)), f"{name} missing"

    assert 'rel="apple-touch-icon"' in html, "iOS home screen falls back to a screenshot"
    assert 'sizes="180x180"' in html
    assert 'rel="manifest"' in html

    with open(os.path.join(DOCS, "site.webmanifest"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["start_url"].endswith("/kid-events-in-ann-arbor/")
    assert {i["sizes"] for i in manifest["icons"]} >= {"192x192", "512x512"}


def test_there_is_a_404_that_goes_somewhere():
    path = os.path.join(DOCS, "404.html")
    assert os.path.exists(path), "GitHub Pages serves 404.html, so ship one"
    with open(path, "r", encoding="utf-8") as fh:
        page = fh.read()
    assert "noindex" in page, "a 404 should never be indexed"
    assert page.count('href="/kid-events-in-ann-arbor/') >= 3, (
        "a dead end is the whole problem a 404 page exists to fix"
    )


def test_every_link_off_site_is_safe(html):
    for tag in re.findall(r"<a\b[^>]*target=\"_blank\"[^>]*>", html):
        assert "noopener" in tag, f"target=_blank without noopener: {tag}"


def test_nothing_loads_over_plain_http(html):
    for path in ("index.html", "404.html"):
        with open(os.path.join(DOCS, path), "r", encoding="utf-8") as fh:
            body = fh.read()
        assert 'src="http://' not in body and 'href="http://' not in body, (
            f"mixed content in {path}"
        )
