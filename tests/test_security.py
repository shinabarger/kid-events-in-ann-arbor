"""The security audit, as tests.

Every one of these is something that was checked by hand once and would go
back to being wrong the moment somebody edited the file it lives in. The
content security policy is the sharpest of them: it carries hashes of the
inline scripts, so editing an inline script without recomputing the hash
silently stops that script from running in every browser.
"""

import base64
import hashlib
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ("index.html", "about.html", "404.html")

# A <script> with no src that is not a JSON-LD data block, or a <style>.
INLINE = r"<%s(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>(.*?)</%s>"


def read(name: str) -> str:
    with open(os.path.join(ROOT, name), "r", encoding="utf-8") as fh:
        return fh.read()


def policy(html: str) -> str:
    m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
    assert m, "the page has no content security policy"
    return m.group(1)


def directive(text: str, name: str) -> list:
    for part in text.split(";"):
        bits = part.split()
        if bits and bits[0] == name:
            return bits[1:]
    return []


def inline_hashes(html: str, tag: str) -> list:
    out = []
    for m in re.finditer(INLINE % (tag, tag), html, re.S):
        digest = hashlib.sha256(m.group(1).encode("utf-8")).digest()
        out.append("'sha256-%s'" % base64.b64encode(digest).decode())
    return out


@pytest.mark.parametrize("page", PAGES)
def test_every_page_has_a_policy(page):
    text = policy(read(page))
    assert "default-src 'none'" in text, "start from nothing and allow back in"
    assert directive(text, "base-uri") == ["'none'"], \
        "without base-uri, one injected <base> tag repoints every relative script"


@pytest.mark.parametrize("page", PAGES)
def test_the_inline_hashes_still_match(page):
    """Edit an inline script and this fails, which is the whole point.

    Recompute with:
        python -c "import base64,hashlib,sys; \\
          print(base64.b64encode(hashlib.sha256(sys.stdin.buffer.read()).digest()).decode())"
    """
    html = read(page)
    text = policy(html)
    for tag, name in (("script", "script-src"), ("style", "style-src")):
        allowed = directive(text, name)
        for digest in inline_hashes(html, tag):
            assert digest in allowed, (
                f"{page}: an inline <{tag}> changed but {name} still carries the old "
                f"hash, so the browser will refuse to run it. Expected {digest}")


@pytest.mark.parametrize("page", PAGES)
def test_no_unsafe_escape_hatches(page):
    text = policy(read(page))
    for name in ("script-src", "style-src", "default-src"):
        allowed = directive(text, name)
        assert "'unsafe-inline'" not in allowed, f"{page}: {name} allows any inline code"
        assert "'unsafe-eval'" not in allowed, f"{page}: {name} allows eval"


@pytest.mark.parametrize("page", PAGES)
def test_external_links_cannot_reach_back(page):
    html = read(page)
    for tag in re.findall(r"<a\b[^>]*>", html):
        if 'href="http' not in tag:
            continue
        assert "noopener" in tag, f"{page}: external link without noopener: {tag[:90]}"


def test_the_scraper_never_uses_an_unsafe_yaml_loader():
    bad = []
    for base, _, files in os.walk(ROOT):
        if "node_modules" in base or ".git" in base:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            with open(path, "r", encoding="utf-8") as fh:
                body = fh.read()
            if re.search(r"yaml\.(load|unsafe_load|full_load)\b(?!er)", body):
                bad.append(os.path.relpath(path, ROOT))
    assert not bad, f"yaml.safe_load only, these use something else: {bad}"


def test_the_workflows_do_not_ask_for_more_than_they_need():
    with open(os.path.join(ROOT, ".github/workflows/tests.yml"), "r", encoding="utf-8") as fh:
        assert re.search(r"permissions:\s*\n\s*contents: read", fh.read()), \
            "running tests never needs write access to the repo"


def test_a_broken_source_does_not_publish_the_path_it_broke_on():
    """The footer shows this text in a tooltip, so it goes out to the public."""
    from scraper.run import scrub_error

    text = scrub_error(FileNotFoundError(
        2, "No such file or directory",
        "/home/runner/work/kid-events-in-ann-arbor/config/venues.yaml"))
    assert "venues.yaml" in text, "still has to say what was missing"
    assert "/home/runner" not in text
    assert "/config/" not in text

    text = scrub_error(ValueError("bad json from https://example.org/private/api?key=abc"))
    assert "example.org" in text, "the host is the useful part"
    assert "key=abc" not in text, "query strings can carry credentials"
