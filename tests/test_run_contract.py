"""Guards for the shape of the pipeline itself.

A helper got pasted into the middle of collect() during an edit. Because the
helper sat at the same indent as the function that followed it, Python read the
rest of collect's body as dead code inside the helper, collect fell off the end
returning None, and the Action died on

    raw, report = collect(args.only)
    TypeError: cannot unpack non-iterable NoneType object

Every unit test still passed, because not one of them called collect(). These
do.
"""

import ast
import json
import os
import sys

import pytest

from scraper import run as runner

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRAPER = os.path.join(ROOT, "scraper")


def test_collect_returns_a_pair():
    """The one line that would have caught it."""
    result = runner.collect("__no_such_source__")
    assert result is not None, "collect fell off the end of its body"
    raw, report = result
    assert isinstance(raw, list) and isinstance(report, list)


def python_files():
    for base, _, names in os.walk(SCRAPER):
        if "__pycache__" in base:
            continue
        for name in sorted(names):
            if name.endswith(".py"):
                yield os.path.join(base, name)


@pytest.mark.parametrize("path", list(python_files()), ids=lambda p: os.path.relpath(p, ROOT))
def test_no_code_hides_after_a_return(path):
    """Unreachable code in a function body is how the last one got in.

    A def or a statement sitting after the return at the same level never runs,
    and reads exactly like working code.
    """
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for i, stmt in enumerate(node.body[:-1]):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                nxt = node.body[i + 1]
                problems.append(
                    f"{node.name} line {node.lineno}: "
                    f"{type(nxt).__name__} on line {nxt.lineno} can never run")
    assert not problems, os.path.relpath(path, ROOT) + ": " + "; ".join(problems)


@pytest.mark.parametrize("name", ["collect", "normalize", "build_payload", "main"])
def test_the_pipeline_steps_are_module_level(name):
    """An edit that indents one of these hides it inside its neighbour."""
    with open(os.path.join(SCRAPER, "run.py"), "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    top = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert name in top, f"{name} is no longer a top level function in run.py"


def test_a_whole_run_writes_a_usable_site(tmp_path, monkeypatch):
    """End to end with the network stubbed out, the way the Action runs it."""
    from scraper.models import Event

    def fake_collect(only=None):
        events = [
            Event(title="Baby Storytime", start="2026-09-08T10:30:00-04:00",
                  end="2026-09-08T11:00:00-04:00", source="aadl",
                  source_name="Ann Arbor District Library",
                  venue="Downtown Library", city="Ann Arbor",
                  description="Songs and books for babies and their grown ups.",
                  url="https://aadl.org/node/1"),
            Event(title="Martin Sorge: Great Bakes", start="2026-09-08T18:30:00-04:00",
                  source="destination_a2", source_name="Destination Ann Arbor",
                  venue="Literati Bookstore", city="Ann Arbor",
                  description="A baking book launch.",
                  ages=["babies", "toddler"], age_min=0, age_max=12,
                  url="https://example.org/e/1"),
        ]
        report = [{"key": "aadl", "name": "Ann Arbor District Library", "count": 1,
                   "ok": True, "error": "", "seconds": 0.1}]
        return events, report

    monkeypatch.setattr(runner, "collect", fake_collect)
    monkeypatch.setattr(sys, "argv", ["scraper.run", "--out", str(tmp_path)])

    assert runner.main() == 0, "the run has to exit clean"

    with open(tmp_path / "data" / "events.json", "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    assert payload["sample"] is False
    assert payload["count"] == len(payload["events"])
    assert payload["count"] >= 1, "the storytime should have survived"

    titles = [e["title"] for e in payload["events"]]
    assert "Baby Storytime" in titles
    assert "Martin Sorge: Great Bakes" not in titles, "the venue gate should have caught it"

    assert (tmp_path / "data" / "feeds.json").exists()
    assert (tmp_path / "feeds" / "all.ics").exists()
