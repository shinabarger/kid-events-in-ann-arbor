"""WCAG 2.2 AA checks that can be run instead of eyeballed.

Contrast is computed straight off the tokens in style.css, so changing a color
and breaking a pair fails the build rather than shipping. The markup checks
cover the success criteria you can actually assert statically: names on
controls, labels on inputs, one h1, correct heading order, language, and the
state attributes the multi selects depend on.

The things a machine cannot check (screen reader flow, reflow at 320px, real
keyboard order in a browser) are written up in ACCESSIBILITY.md.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "assets", "style.css")
HTML = os.path.join(ROOT, "index.html")
JS = os.path.join(ROOT, "assets", "app.js")

AA_TEXT = 4.5          # 1.4.3 normal text
AA_LARGE = 3.0         # 1.4.3 large text, 18.66px bold or 24px
AA_NON_TEXT = 3.0      # 1.4.11 UI components and borders


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# --- Color math -------------------------------------------------------------

def hex_to_rgb(value: str):
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def relative_luminance(rgb):
    channels = []
    for raw in rgb:
        c = raw / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a = relative_luminance(hex_to_rgb(fg))
    b = relative_luminance(hex_to_rgb(bg))
    light, dark = max(a, b), min(a, b)
    return (light + 0.05) / (dark + 0.05)


def blend(fg: str, bg: str, alpha: float) -> str:
    """Flatten a translucent foreground onto its background."""
    f, b = hex_to_rgb(fg), hex_to_rgb(bg)
    mixed = tuple(round(alpha * f[i] + (1 - alpha) * b[i]) for i in range(3))
    return "#%02x%02x%02x" % mixed


def tokens(scope: str) -> dict:
    """Pull the custom properties out of one block of style.css."""
    css = read(CSS)
    start = css.index(scope)
    block = css[start:css.index("}", start)]
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{3,6})\s*;", block))


LIGHT = tokens(":root {")
DARK = tokens('[data-theme="dark"] {')


# --- 1.4.3 Contrast (Minimum) ----------------------------------------------

def pairs(theme):
    """(name, foreground, background, minimum ratio) for every real pair."""
    t = theme
    return [
        ("body text", t["--text"], t["--bg"], AA_TEXT),
        ("body text on a card", t["--text"], t["--surface"], AA_TEXT),
        ("muted text on a card", t["--text-soft"], t["--surface"], AA_TEXT),
        ("muted text on the alt surface", t["--text-soft"], t["--surface-2"], AA_TEXT),
        ("muted text on the page", t["--text-soft"], t["--bg"], AA_TEXT),
        ("links", t["--brand-blue-dark"], t["--surface"], AA_TEXT),
        ("event subtitle", t["--brand-blue-dark"], t["--surface"], AA_TEXT),
        ("card time", t["--brand-blue-dark"], t["--surface"], AA_TEXT),
        ("day heading", t["--brand-green-dark"], t["--brand-green-soft"], AA_TEXT),
        ("age badge", t["--brand-blue-dark"], t["--brand-blue-soft"], AA_TEXT),
        ("free badge", t["--brand-green-dark"], t["--brand-green-soft"], AA_TEXT),
        ("registration badge", t["--warn-text"], t["--warn-bg"], AA_TEXT),
        ("plain badge", t["--text-soft"], t["--surface-2"], AA_TEXT),
        ("month chip", t["--brand-blue-dark"], t["--brand-blue-soft"], AA_TEXT),
        ("selected when chip", t["--brand-green-dark"], t["--brand-green-soft"], AA_TEXT),
        ("set filter button", t["--brand-green-dark"], t["--surface"], AA_TEXT),
        ("clear filter link", t["--brand-blue-dark"], t["--surface"], AA_TEXT),
        # Non text: borders, focus rings, and the outline of a control.
        ("input border", t["--line-strong"], t["--surface"], AA_NON_TEXT),
        ("focus ring on a card", t["--focus"], t["--surface"], AA_NON_TEXT),
        ("focus ring on the page", t["--focus"], t["--bg"], AA_NON_TEXT),
        ("active control border", t["--brand-green"], t["--surface"], AA_NON_TEXT),
    ]


@pytest.mark.parametrize("theme_name,theme", [("light", LIGHT), ("dark", DARK)])
def test_every_color_pair_meets_aa(theme_name, theme):
    failures = []
    for name, fg, bg, minimum in pairs(theme):
        ratio = contrast(fg, bg)
        if ratio < minimum:
            failures.append(f"{theme_name} {name}: {fg} on {bg} is {ratio:.2f}:1, needs {minimum}:1")
    assert not failures, "\n".join(failures)


def test_primary_button_text_meets_aa():
    # White on green in light, near black on mint in dark.
    assert contrast("#ffffff", LIGHT["--brand-green"]) >= AA_TEXT
    assert contrast("#0b1a13", DARK["--brand-green"]) >= AA_TEXT


def test_masthead_text_meets_aa():
    """The header is a gradient, so check both ends of it."""
    for stop in ("#14563a", "#12506a"):
        assert contrast("#ffffff", stop) >= AA_TEXT, f"title on {stop}"
        # The tagline is white at 88 percent, which has to be flattened first.
        tagline = blend("#ffffff", stop, 0.88)
        assert contrast(tagline, stop) >= AA_TEXT, f"tagline on {stop}"
        # The ghost button border is white at 70 percent, a non text element.
        border = blend("#ffffff", stop, 0.70)
        assert contrast(border, stop) >= AA_NON_TEXT, f"button border on {stop}"
    # The masthead subscribe button flips to a white pill with dark green text.
    assert contrast("#0f4530", "#ffffff") >= AA_TEXT


# --- 2.5.8 Target Size (Minimum), 24 by 24 CSS pixels ----------------------

def test_interactive_targets_are_at_least_44px():
    css = read(CSS)
    targets = {
        ".btn": r"\.btn\s*\{[^}]*min-height:\s*(\d+)px",
        ".btn-small": r"\.btn-small\s*\{[^}]*min-height:\s*(\d+)px",
        ".icon-btn": r"\.icon-btn\s*\{[^}]*min-height:\s*(\d+)px",
        ".opt": r"\.opt\s*\{[^}]*min-height:\s*(\d+)px",
        ".chip span": r"\.chip span\s*\{[^}]*min-height:\s*(\d+)px",
        ".multi-clear": r"\.multi-clear\s*\{[^}]*min-height:\s*(\d+)px",
        ".ask-example": r"\.ask-example\s*\{[^}]*min-height:\s*(\d+)px",
        ".read-clear": r"\.read-clear\s*\{[^}]*min-height:\s*(\d+)px",
    }
    for name, pattern in targets.items():
        match = re.search(pattern, css, re.DOTALL)
        assert match, f"{name} has no min-height, so its target size is unchecked"
        assert int(match.group(1)) >= 24, f"{name} target is only {match.group(1)}px"


def test_form_controls_are_a_comfortable_height():
    css = read(CSS)
    match = re.search(r'\.field input\[type="search"\],[^{]*\{[^}]*height:\s*(\d+)px', css, re.DOTALL)
    assert match and int(match.group(1)) >= 44


# --- 1.4.1 Use of Color -----------------------------------------------------

def test_state_is_never_carried_by_color_alone():
    js = read(JS)
    html = read(HTML)
    # Selected view is announced with aria-pressed, not just a green pill.
    assert 'aria-pressed' in html and 'setAttribute("aria-pressed"' in js
    # A source that is down says "no data" as well as changing color.
    assert '"(no data)"' in js or '(no data)' in js
    # Free and registration are words in a badge, not a color swatch.
    assert '"Free"' in js and '"Registration required"' in js


# --- 2.4.x, 4.1.2 Names, roles, structure -----------------------------------

def test_page_has_one_h1_and_a_language():
    html = read(HTML)
    assert 'lang="en"' in html
    assert html.count("<h1") == 1


def test_headings_do_not_skip_levels():
    html = read(HTML)
    levels = [int(m) for m in re.findall(r"<h([1-6])[ >]", html)]
    assert levels, "no headings at all"
    assert levels[0] == 1
    for previous, current in zip(levels, levels[1:]):
        assert current <= previous + 1, f"jumped from h{previous} to h{current}"


def test_every_form_control_has_a_label():
    html = read(HTML)
    for control_id in re.findall(r'<(?:input|select)[^>]*\bid="([\w-]+)"', html):
        labelled = (
            f'for="{control_id}"' in html
            or f'aria-label' in _tag_for(html, control_id)
            or "aria-labelledby" in _tag_for(html, control_id)
        )
        assert labelled, f"{control_id} has no label"


def _tag_for(html: str, control_id: str) -> str:
    match = re.search(r"<[^>]*\bid=\"" + re.escape(control_id) + r"\"[^>]*>", html)
    return match.group(0) if match else ""


def test_every_button_in_the_markup_has_an_accessible_name():
    """Buttons inside <template> get their text from JS, so they are checked
    after rendering by the jsdom suite instead."""
    html = read(HTML)
    html = re.sub(r"<template.*?</template>", "", html, flags=re.DOTALL)
    for tag, inner in re.findall(r"(<button[^>]*>)(.*?)</button>", html, re.DOTALL):
        text = re.sub(r"<[^>]+>", "", inner).strip()
        named = text or "aria-label" in tag or "aria-labelledby" in tag
        assert named, f"button with no name: {tag}"


def test_multi_selects_expose_their_state():
    """4.1.2: a disclosure has to say whether it is open and what it controls."""
    html = read(HTML)
    for name in ("age", "where", "setting", "cost", "signup", "repeats"):
        tag = _tag_for(html, f"btn-{name}")
        assert 'aria-expanded="false"' in tag, f"btn-{name} is missing aria-expanded"
        assert f'aria-controls="panel-{name}"' in tag, f"btn-{name} is missing aria-controls"
        assert f'aria-labelledby="lbl-{name} val-{name}"' in tag, \
            f"btn-{name} does not name itself with its label and value"
        panel = _tag_for(html, f"panel-{name}")
        assert 'role="group"' in panel and f'aria-labelledby="lbl-{name}"' in panel

    js = read(JS)
    assert 'setAttribute("aria-expanded"' in js, "aria-expanded is never updated"
    assert '"Escape"' in js, "Escape does not close the panel"
    assert '"ArrowDown"' in js, "Arrow Down does not open the panel"


def test_expanding_a_card_is_announced():
    """4.1.2: a disclosure has to report its own state."""
    html = read(HTML)
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert 'class="card-open" aria-expanded="false"' in html
    assert 'class="card-more" hidden' in html
    assert 'setAttribute("aria-expanded", open ? "true" : "false")' in js


def test_the_sync_dialog_is_a_labelled_checkbox_group():
    html = read(HTML)
    assert "Sync to my calendar" in html
    assert html.count("<fieldset class=\"feed-group\">") == 2
    assert "<legend>Ages</legend>" in html
    assert 'id="feed-picked" role="status" aria-live="polite"' in html


def test_copy_link_has_a_fallback_and_a_name():
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert "function copyLink(" in js
    assert "function fallbackCopy(" in js, "older Safari needs the execCommand path"
    assert '"Copy a link to "' in js


def test_focus_returns_after_a_dialog_closes():
    js = read(JS)
    assert "state.lastFocus" in js
    assert "lastFocus.focus()" in js


def test_status_region_is_live():
    html = read(HTML)
    assert 'role="status"' in html and 'aria-live="polite"' in html


def test_the_search_bar_is_a_labelled_landmark():
    """The plain language box is the main control, so it gets the full set."""
    html = read(HTML)
    assert '<form class="ask"' in html
    assert 'role="search"' in html
    assert 'aria-label="Search events in plain language"' in html
    assert '<label class="ask-label" for="ask">' in html
    # The placeholder carries the affordance instead of a paragraph of prose.
    assert "year old" in html
    # What is filtering right now is announced, not just shown.
    assert 'id="active-bar" role="status" aria-live="polite"' in html


def test_the_parser_never_silently_guesses():
    """1.4.1 and 3.3.1: say what is filtering, in words, every time."""
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert "renderActive" in js
    assert "Nothing in that search matched" in js, "an unparsed query has to say so"
    assert "active-chip" in js
    assert "syncCheckboxes" in js, "the dropdowns must move to match the query"


# --- Nielsen Norman heuristics that map onto real code ----------------------

def test_users_can_undo(html_and_js=None):
    """H3, user control and freedom. Every filter change is reversible."""
    html = read(HTML)
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert 'id="undo"' in html, "there is no undo control"
    assert 'id="empty-undo"' in html, "the dead end has no way back"
    assert "function undo(" in js
    assert "state.history" in js
    assert "remember()" in js, "nothing is being recorded to undo"


def test_there_is_a_show_everything_escape_hatch():
    html = read(HTML)
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert html.count("Show everything") >= 2, "reset should be reachable from more than one place"
    assert "function showEverything(" in js


def test_active_filters_are_visible_and_removable():
    """H6, recognition rather than recall."""
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert "function activeChips(" in js
    assert 'setAttribute("aria-label", "Remove filter: "' in js


def test_the_empty_state_says_what_to_change():
    """H9, help users recognize and recover from a dead end."""
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert "function emptyAdvice(" in js
    assert "would show" in js, "the empty state should name a filter worth dropping"


def test_there_is_a_keyboard_shortcut_to_search():
    """H7, flexibility and efficiency of use."""
    js = read(os.path.join(ROOT, "assets", "app.js"))
    assert 'e.key !== "/"' in js, "slash should focus the search box"
    assert "el.ask.focus()" in js


def test_skip_link_points_at_the_results():
    html = read(HTML)
    assert 'class="skip" href="#results"' in html
    assert 'id="results" tabindex="-1"' in html


def test_decorative_svg_is_hidden_from_screen_readers():
    html = read(HTML)
    for tag in re.findall(r"<svg[^>]*>", html):
        assert 'aria-hidden="true"' in tag, f"decorative svg is not hidden: {tag}"


def test_external_links_are_safe_and_labelled():
    html = read(HTML)
    for tag in re.findall(r'<a[^>]*target="_blank"[^>]*>', html):
        assert 'rel="noopener"' in tag, f"target=_blank without rel=noopener: {tag}"


# --- 1.4.12 Text Spacing, 1.4.10 Reflow, 2.3.3 Animation --------------------

def test_reduced_motion_is_respected():
    assert "@media (prefers-reduced-motion: reduce)" in read(CSS)


def test_forced_colors_mode_keeps_borders():
    assert "@media (forced-colors: active)" in read(CSS)


def test_nothing_forces_a_horizontal_scroll():
    css = read(CSS)
    # Fixed pixel widths on containers are what break reflow at 320px.
    assert "width: 1120px" not in css
    assert "min-width: 100%" in css  # the filter panels grow, they do not fix


def test_line_height_leaves_room_for_text_spacing():
    css = read(CSS)
    match = re.search(r"body\s*\{[^}]*line-height:\s*([\d.]+)", css, re.DOTALL)
    assert match and float(match.group(1)) >= 1.5


def test_the_description_clamp_is_two_lines():
    css = read(CSS)
    match = re.search(r"\.card-desc\s*\{[^}]*line-clamp:\s*(\d+)", css, re.DOTALL)
    assert match and int(match.group(1)) == 2
    # Clamped text has to be reachable, which is what expanding the card does.
    assert "line-clamp: unset" in css, "expanding a card must unclamp the text"
    assert 'class="card-more"' in read(HTML)
    assert 'aria-expanded="false"' in read(HTML)
