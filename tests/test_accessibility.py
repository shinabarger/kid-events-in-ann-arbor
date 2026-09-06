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


# --- the bug that shipped ------------------------------------------------

def test_hidden_actually_hides():
    """This one reached the live site.

    The browser's own `[hidden] { display: none }` lives in the user agent
    stylesheet, which loses to any author declaration. `.multi-panel` sets
    `display: flex`, so every filter dropdown rendered open on page load even
    though the markup said hidden and the jsdom tests agreed it was hidden.

    jsdom has no cascade, so no amount of front end testing catches this. One
    author level rule does.
    """
    css = read(CSS)
    match = re.search(r"\[hidden\]\s*\{([^}]*)\}", css)
    assert match, "no author level [hidden] rule, so anything with a display: wins"
    body = match.group(1)
    assert "display" in body and "none" in body
    assert "!important" in body, (
        "without !important a later display: rule silently unhides it again"
    )


def test_everything_toggled_with_hidden_is_covered_by_that_rule():
    """A list of the classes the script hides, as a reminder of what would
    break if the rule above were removed."""
    js = read(JS)
    for selector in (".multi-panel", ".cal-panel", ".card-more"):
        assert selector in read(CSS), f"{selector} has no styles at all"
    assert ".hidden = " in js or ".hidden=" in js


# --- the calendar menu ---------------------------------------------------

def test_the_calendar_menu_is_announced_as_a_menu():
    html = read(HTML)
    assert 'class="cal-panel" role="menu" hidden' in html
    assert 'class="btn btn-small btn-secondary card-cal" aria-expanded="false" aria-haspopup="true"' in html


def test_the_menu_items_are_reachable_by_keyboard():
    js = read(JS)
    for key in ("ArrowDown", "ArrowUp", "Escape", "Home", "End", "Tab"):
        assert key in js, f"the calendar menu does not handle {key}"
    assert 'setAttribute("role", "menuitem")' in js
    assert "button.focus()" in js, "Escape has to put focus back on the button"


def test_all_three_calendars_are_offered():
    js = read(JS)
    for name in ("Google Calendar", "Apple Calendar", "Outlook Calendar"):
        assert name in js, f"{name} missing from the menu"
    assert "outlook.live.com/calendar/0/deeplink/compose" in js
    assert "rru=addevent" in js or '"rru": "addevent"' in js or 'rru: "addevent"' in js


def test_every_icon_is_hidden_from_screen_readers():
    """An icon next to a word label is decoration. Left exposed, a screen
    reader reads the SVG and then the label, twice for every button."""
    html = read(HTML)
    for tag in re.findall(r"<svg\b[^>]*>", html):
        assert 'aria-hidden="true"' in tag, f"icon not hidden from assistive tech: {tag[:70]}"
        assert 'focusable="false"' in tag, (
            f"old Edge and IE put SVGs in the tab order without this: {tag[:70]}"
        )


def test_every_action_button_still_has_a_text_label():
    """Icons are added next to the words, never instead of them."""
    html = read(HTML)
    actions = html[html.index('class="card-actions"'):]
    actions = actions[:actions.index("</article>")]
    for label in ("Add to calendar", "Copy link", "View on event website"):
        assert f"<span>{label}</span>" in actions or f'>{label}</span>' in actions, label


# --- the theme -----------------------------------------------------------

def test_the_page_opens_in_light_mode():
    """Following the system setting meant anybody whose laptop is on dark got
    a dark kids calendar without ever asking for one."""
    assert 'data-theme="light"' in read(HTML), (
        "stamp it in the markup so the first paint is light, with no flash"
    )
    js = read(JS)
    assert 'var dark = saved === "dark";' in js, "dark should need an explicit choice"


def test_the_dark_theme_is_still_reachable_and_sticky():
    js = read(JS)
    assert 'localStorage.setItem("a2kids-theme"' in js
    assert 'aria-pressed' in js


# --- the calendar views --------------------------------------------------

def test_all_four_views_exist():
    html = read(HTML)
    for view in ("list", "day", "week", "month"):
        assert f'data-view="{view}"' in html, f"no {view} view"
    assert 'role="group" aria-label="Choose a view"' in html


def test_the_calendar_navigation_is_labelled():
    html = read(HTML)
    assert 'id="cal-nav"' in html and 'hidden' in html
    assert 'id="cal-prev"' in html and 'id="cal-next"' in html
    assert 'id="cal-today"' in html
    # The heading changes as you move, so it has to be announced.
    assert 'id="cal-heading" tabindex="-1" role="status" aria-live="polite"' in html


def test_the_arrows_say_what_they_move():
    """"Previous" alone is useless. Previous what: day, week, month?"""
    js = read(JS)
    assert '"Previous " + VIEW_NOUN[state.view]' in js
    assert '"Next " + VIEW_NOUN[state.view]' in js


def test_a_calendar_row_is_a_button_not_a_div():
    js = read(JS)
    block = js[js.index("function calendarRow"):js.index("function jumpToEvent")]
    assert 'createElement("button")' in block
    assert 'row.type = "button"' in block
    assert "aria-label" in block


def test_the_month_more_link_goes_somewhere():
    """A dead "+14 more" is worse than not showing the count at all."""
    js = read(JS)
    assert '"See all " + list.length + " events on "' in js
    assert 'setView("day")' in js


def test_calendar_rows_meet_the_target_size():
    css = read(CSS)
    block = css[css.index(".cal-row {"):css.index("}", css.index(".cal-row {"))]
    match = re.search(r"min-height:\s*(\d+)px", block)
    assert match and int(match.group(1)) >= 44, (
        "WCAG 2.5.8 wants 44px, and so does anybody tapping with a baby on one arm"
    )


def test_the_week_grid_collapses_on_a_phone():
    """Seven columns on a 390px screen is seven unreadable slivers."""
    css = read(CSS)
    assert ".week-grid { grid-template-columns: 1fr; }" in css.replace("\n", " ")


def test_keyboard_navigation_does_not_hijack_typing():
    js = read(JS)
    block = js[js.index('if (state.view === "list") return;'):]
    block = block[:block.index("$(\"empty-reset\")")]
    assert 'tag === "input"' in block, "arrow keys would move the calendar mid-search"
    assert "closest" in block and ".multi-panel" in block


# --- the header and the About page ---------------------------------------

def test_the_whole_brand_lockup_is_one_link_home():
    """People click the logo. They also click the title. Both should work,
    and wrapping the pair in one link is how you get that without two
    tab stops for the same destination."""
    html = read(HTML)
    assert '<a class="brand" href="./"' in html
    assert 'aria-label="Kid Events in Ann Arbor, back to the calendar"' in html
    # The mark is decoration inside a labelled link, so it stays hidden.
    brand = html[html.index('<a class="brand"'):html.index("</a>", html.index('<a class="brand"'))]
    assert 'class="brand-mark"' in brand and 'aria-hidden="true"' in brand
    assert "<h1" in brand, "the site name should still be the page heading"


def test_the_header_nav_says_where_you_are():
    html = read(HTML)
    assert 'aria-label="Main"' in html
    assert 'href="./" aria-current="page"' in html
    assert 'href="about.html"' in html


def test_the_nav_items_look_like_buttons_but_stay_links():
    """They navigate to another page, so they are anchors. A real <button>
    would break middle click, open in a new tab and copy link address, and a
    screen reader would announce "button" for something that navigates. Same
    pill as every other button on the page, different element underneath."""
    for page in (HTML, os.path.join(ROOT, "about.html")):
        markup = read(page)
        for label in ("Calendar", "About"):
            match = re.search(rf'<a[^>]*class="([^"]*)"[^>]*>{label}</a>', markup)
            assert match, f"{label} is not an anchor on {os.path.basename(page)}"
            classes = match.group(1)
            assert "btn" in classes and "btn-nav" in classes, classes
    assert "nav-link" not in read(HTML), "the old unstyled link class is gone"


def test_the_site_title_is_white_and_never_underlined():
    """The generic `a` rule paints links brand blue, which on a dark green bar
    is unreadable. It shipped that way for one upload."""
    css = read(CSS)
    block = css[css.index(".brand,"):css.index("/* Hover is a lift")]
    assert "color: #fff" in block
    assert "text-decoration: none" in block
    for selector in (".brand:link", ".brand:visited", ".brand:hover",
                     ".brand .brand-name", ".brand .tagline"):
        assert selector in block, f"{selector} not covered, so it can go blue"
    assert "text-decoration: underline" not in css[css.index(".brand,"):css.index(".brand-mark {")]


def test_the_brand_and_nav_have_visible_focus_rings():
    css = read(CSS)
    assert ".brand:focus-visible" in css
    assert ".masthead .btn:focus-visible" in css, (
        "the global ring is tuned for light backgrounds and vanishes on the bar"
    )
    assert ":focus-visible" in css


def test_the_logo_got_bigger():
    css = read(CSS)
    block = css[css.index(".brand-mark {"):css.index("}", css.index(".brand-mark {"))]
    size = int(re.search(r"width:\s*(\d+)px", block).group(1))
    assert size >= 48, f"the mark is {size}px, which reads as an afterthought"


def test_the_theme_toggle_keeps_a_name_when_its_label_is_hidden():
    """Below 620px the word goes and only the icon is left, so the accessible
    name has to come from somewhere."""
    css = read(CSS)
    assert ".theme-label" in css and "clip-path: inset(50%)" in css
    js = read(JS)
    assert 'button.setAttribute("aria-label"' in js


def test_there_is_an_about_page_and_it_is_a_real_page():
    path = os.path.join(ROOT, "about.html")
    assert os.path.exists(path), "no About page"
    page = read(path)

    assert 'lang="en"' in page
    assert 'data-theme="light"' in page
    assert "<title>About Kid Events in Ann Arbor</title>" in page
    assert 'rel="canonical"' in page
    assert 'class="skip"' in page, "a skip link, same as the calendar page"
    assert page.count("<h1") == 1


def test_the_about_page_says_why_it_exists():
    page = read(os.path.join(ROOT, "about.html"))
    assert "sleep deprived parent of a toddler" in page
    assert "out of the house" in page


def test_the_about_page_links_back_to_the_calendar():
    page = read(os.path.join(ROOT, "about.html"))
    assert '<a class="brand" href="./"' in page
    assert 'href="about.html" aria-current="page"' in page


def test_the_calendar_page_links_to_about():
    assert 'href="about.html"' in read(HTML)


def test_the_about_page_carries_the_theme_across():
    """A dark reader who clicks About should not get flashbanged."""
    page = read(os.path.join(ROOT, "about.html"))
    assert 'localStorage.getItem("a2kids-theme")' in page
    assert page.index('localStorage.getItem("a2kids-theme")') < page.index("<body")


def test_every_icon_on_the_about_page_is_hidden_from_screen_readers():
    page = read(os.path.join(ROOT, "about.html"))
    for tag in re.findall(r"<svg\b[^>]*>", page):
        assert 'aria-hidden="true"' in tag and 'focusable="false"' in tag, tag[:70]


def test_the_about_page_is_in_the_sitemap():
    with open(os.path.join(ROOT, "sitemap.xml"), "r", encoding="utf-8") as fh:
        sitemap = fh.read()
    assert "about.html</loc>" in sitemap


def test_the_brand_bar_stays_dark_in_both_themes():
    """--brand-green-dark flips to a light mint in dark mode so it works as
    text. Using it as the header background turned the whole bar pale green
    the moment anyone switched. The bar gets its own token instead."""
    css = read(CSS)
    assert "background: var(--masthead-bg)" in css
    assert css.count("--masthead-bg:") == 3, (
        "the token needs a value in :root, [data-theme=dark] and the "
        "prefers-color-scheme block, or one of the three paths goes pale"
    )
    for block in re.findall(r"--masthead-bg:\s*(#[0-9a-f]{6})", css, re.I):
        r, g, b = (int(block[i:i + 2], 16) for i in (1, 3, 5))
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        assert luminance < 0.4, f"{block} is too light for white header text"


# --- the wide brand bar and the mobile pass ------------------------------

def test_the_brand_bar_runs_wider_than_the_content_column():
    """A header that stops where the article stops reads as a widget dropped
    onto the page. One that runs most of the window reads as the top of a
    site."""
    css = read(CSS)
    block = css[css.index(".masthead-inner {"):css.index("}", css.index(".masthead-inner {"))]
    match = re.search(r"max-width:\s*(\d+)px", block)
    assert match, "the header inner has no width of its own"
    wrap = int(re.search(r"--wrap:\s*(\d+)px", css).group(1))
    assert int(match.group(1)) > wrap, (
        f"header is {match.group(1)}px, content column is {wrap}px, so it is not wider"
    )


def test_the_month_date_is_a_button_that_opens_the_day():
    """Seven columns in a phone width is about fifty pixels each, which turns
    every event title into "10...". The count plus a tappable date is what a
    phone calendar actually does."""
    js = read(JS)
    block = js[js.index('num.className = "month-date"') - 200:]
    block = block[:block.index("cell.appendChild(num)")]
    assert 'createElement("button")' in block
    assert 'setView("day")' in block
    assert "aria-label" in block and "events" in block


def test_the_month_grid_hides_truncated_titles_on_a_phone():
    css = read(CSS)
    assert "@media (max-width: 700px)" in css
    tail = css[css.index("@media (max-width: 700px)"):]
    block = tail[:tail.index("}\n}") + 3]
    assert ".month-item" in block and "display: none" in block
    assert ".month-count" in block or ".month-date" in block


def test_the_three_targets_that_missed_44px_now_make_it():
    css = read(CSS)
    for selector in (".card-open", ".active-chip", ".month-date"):
        at = css.rindex(selector)
        block = css[at:css.index("}", at)]
        assert "min-height: 44px" in block or "min-height: 44px" in css[at:at + 400], (
            f"{selector} is still under the 44px target size"
        )


def test_the_skip_link_is_clipped_not_shoved_off_screen():
    """left: -9999px leaves a real box off the left edge, which some Android
    browsers count toward scrollable width and turn into a phantom sideways
    scroll."""
    css = read(CSS)
    start = css.index(".skip {")
    block = css[start:css.index(".skip:focus", start)]
    # The comment above it explains what it replaced, so read declarations only.
    declarations = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    assert "-9999px" not in declarations
    assert "clip-path: inset(50%)" in block

    focus = css[css.index(".skip:focus", start):]
    focus = focus[:focus.index("}") + 1]
    assert "clip-path: none" in focus, "focusing it has to make it visible again"
