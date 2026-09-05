# Accessibility

Target: **WCAG 2.2 Level AA**. Most of it is enforced by
`tests/test_accessibility.py` and `tests/frontend.test.mjs` rather than checked
by hand, so a change that breaks a criterion fails the build.

## What is enforced automatically

| Criterion | How it is checked |
| --- | --- |
| 1.3.1 Info and Relationships | One `h1`, headings never skip a level, filters are a labelled `role="group"` of checkboxes, day groups are `section` with an `h2` |
| 1.4.1 Use of Color | Free, Registration required, and a dead source all say so in words, not just color. View state carries `aria-pressed` |
| 1.4.3 Contrast (Minimum) | Every foreground and background pair in the palette is computed from the tokens in `style.css` and asserted at 4.5:1, both themes. The masthead gradient is checked at both ends, and translucent text is flattened onto its background first |
| 1.4.10 Reflow | No fixed pixel container widths. Panels use `min-width: 100%` and grow, so the page works down to 320px without a sideways scroll |
| 1.4.11 Non-text Contrast | Input borders, focus rings, and active control outlines are asserted at 3:1 |
| 1.4.12 Text Spacing | Body `line-height` is 1.5 or more, nothing is sized to an exact text height |
| 2.1.1 Keyboard | Filter buttons open on Enter, Space, or Arrow Down. Escape closes and returns focus to the button. Every control is a real `button`, `input`, or `a` |
| 2.3.3 Animation from Interactions | `prefers-reduced-motion: reduce` turns off every transition |
| 2.4.1 Bypass Blocks | Skip link to `#results`, which is focusable |
| 2.4.7 Focus Visible | 3px `:focus-visible` outline with 2px offset, in an accent that clears 3:1 on every surface |
| 2.5.8 Target Size | Every button, chip, checkbox row, and input is at least 44px tall, well past the 24px minimum |
| 3.3.2 Labels or Instructions | Every input and select has a `label`, checked in the markup and again on the rendered page |
| 4.1.2 Name, Role, Value | Filter buttons carry `aria-expanded`, `aria-controls`, and an `aria-labelledby` pairing their label with their current value, so a screen reader hears "Age, Babies +1, collapsed" |
| 4.1.3 Status Messages | The result count is `role="status" aria-live="polite"` and is asserted to change when a filter changes |

Run them with:

```bash
python -m pytest tests/test_accessibility.py -q
npm test
```

## Decisions worth knowing

**The filters are a disclosure plus a checkbox group, not a listbox.** A custom
`role="listbox"` with `aria-multiselectable` is the fancier pattern and it is
also the one that breaks in real screen readers. A button that says whether it
is open, revealing plain checkboxes with real labels, uses only roles the
browser already implements.

**Nothing is clipped without a way to read it.** The card description is
clamped to two lines, so the full text lives in the detail dialog behind the
event title, which is a real button.

**Both themes are designed, not inverted.** Dark mode redefines the tokens
under `prefers-color-scheme` and under `[data-theme="dark"]`, so it works
whether or not the toggle has ever been touched, and it holds up if JavaScript
never runs.

**Forced colors mode keeps its borders.** Under `forced-colors: active` the
cards, buttons, and badges take system border colors instead of vanishing into
the background.

**The date chips are radio buttons.** They look like pills but they are a real
radio group, so arrow keys move between them the way they should.

## What still needs a human

Automated tests cannot cover these. Worth doing once before sharing the link
widely, and again after any big layout change:

- A pass with VoiceOver or NVDA, listening to whether the day headings and
  result count read in a sensible order.
- Keyboard only, no mouse, from the skip link through to closing the detail
  dialog.
- 320px wide at 200% zoom, checking that nothing overlaps.
- Windows high contrast mode.

## Known gaps

- Google Fonts is a third party request. If it is blocked the page falls back
  to the system stack, which is fine, but the first paint may shift.
- The month grid is a visual layout rather than a table. It is fine to tab
  through, but the list view is the better experience with a screen reader, and
  it is the default for that reason.
