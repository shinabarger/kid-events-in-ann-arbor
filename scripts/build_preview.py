"""Squash the whole site into one double-clickable HTML file.

    python scripts/build_preview.py preview.html

The site itself is the repo root, and a browser will not let a page at a
file:// URL fetch data/events.json, so opening index.html directly shows an
empty page. This inlines the CSS, the JavaScript and the data so you can look
at the thing offline without running a server.

Not committed. The front end tests build it on the fly to load the real page
into jsdom, which is the other reason it exists.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = ROOT


def read(*parts) -> str:
    with open(os.path.join(SITE, *parts), "r", encoding="utf-8") as fh:
        return fh.read()


def build(body_only: bool = False) -> str:
    html = read("index.html")
    css = read("assets", "style.css")
    nlq = read("assets", "nlq.js")
    js = read("assets", "app.js")

    data = json.dumps({
        "events": json.loads(read("data", "events.json")),
        "feeds": json.loads(read("data", "feeds.json")),
    }, ensure_ascii=False)

    island = (
        '<script type="application/json" id="inline-data">'
        + data.replace("</", "<\\/")
        + "</script>"
    )

    html = html.replace(
        '<link rel="stylesheet" href="assets/style.css">',
        "<style>\n" + css + "\n</style>",
    )
    html = re.sub(r'\s*<link rel="(?:apple-touch-)?icon"[^>]*>', "", html)
    html = html.replace(
        '<script src="assets/nlq.js"></script>\n<script src="assets/app.js"></script>',
        island + "\n<script>\n" + nlq + "\n</script>\n<script>\n" + js + "\n</script>",
    )

    if not body_only:
        return html

    title = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    style = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    body = re.search(r"<body>(.*?)</body>", html, re.DOTALL)
    if not (title and style and body):
        raise SystemExit("could not slice the page apart, did index.html change shape?")

    return (
        f"<title>{title.group(1)}</title>\n"
        f"<style>{style.group(1)}</style>\n"
        f"{body.group(1).strip()}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="preview.html")
    parser.add_argument("--body-only", action="store_true")
    args = parser.parse_args()

    text = build(args.body_only)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)

    print(f"Wrote {args.out} ({len(text) // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
