# Browsers

## What is actually tested

`npm test` loads the real page into jsdom and drives it. jsdom is not a
browser: it has no layout, no paint, and no WebKit. So the suite covers
behaviour, and the Safari specific tests in it are static checks against the
handful of WebKit divergences that have historically broken this kind of site:

| Check | The bug it prevents |
| --- | --- |
| Form controls are at least 16px | iOS zooms the page when you tap anything smaller, then leaves you scrolled sideways |
| `-webkit-appearance: none` on search inputs | Safari draws its own pill and inset shadow over the design |
| `::-webkit-search-cancel-button` is reset | The native clear button is otherwise unstyleable and looks wrong |
| `dvh` on the dialog height | `vh` on iOS counts the address bar you cannot see, so the buttons end up unreachable |
| No `new Date("2026-09-05 10:30")` | Space separated dates parse in Chrome and return null in Safari |
| No regex lookbehind | A syntax error on iOS 16.3 and older, which takes the whole script down |
| Clipboard has a fallback | Safari only allows clipboard writes inside a real user gesture |

The last one matters more than it looks. A syntax error in Safari is not a
degraded feature, it is a blank page, because the whole file fails to parse.

## What still needs a person and a phone

Fifteen minutes on a real iPhone, ideally not the newest one.

1. **Tap the search box.** The page must not zoom. This is the one that gets
   shipped broken most often.
2. **Type a question, then rotate to landscape.** Text should not inflate.
3. **Open Sync to my calendar.** Scroll to the bottom of the dialog. Every
   button must be reachable above the browser chrome.
4. **Tap Apple on a feed.** It should hand off to the Calendar app. `webcal://`
   is the only thing that does this, and it is untestable anywhere else.
5. **Tap Copy link on a card, then paste into Messages.** Safari blocks
   clipboard writes outside a gesture, so this is the real check on the
   fallback path.
6. **Add to Home Screen.** Confirm the icon is the house mark and not a
   screenshot of the page, and that it opens without Safari chrome.
7. **Turn on Reduce Motion and Increase Contrast** in Accessibility settings
   and reload.
8. **VoiceOver on, swipe through the filter bar.** Each multi select should
   announce its name, its state, and how many are picked.
9. **Private Browsing.** `localStorage` throws in some Safari configurations
   rather than returning null. The theme toggle is wrapped in try/catch for
   exactly this, so confirm the page still loads.
10. **Paste a `?event=` link into Slack and into Messages.** The share card
    should render, not a bare URL.

## Known differences that are fine

- `text-wrap: balance` on card titles needs Safari 17.5. Older versions get
  ordinary wrapping, which looks slightly worse and works identically.
- `:has()` and `accent-color` need Safari 15.4. Below that the checkboxes are
  the system blue instead of the brand green.
- `<dialog>` needs Safari 15.4. That is March 2022, and below it the sync and
  detail dialogs will not open. If that ever matters, the fix is a polyfill,
  not a redesign.

## Forms

There is one form on the site, the plain language search, and two rules it
follows:

**It never wipes what you typed.** Not on a search that matches nothing, not
on a search it could not parse, not when the empty state runs its "which
filter is costing you the most" calculation. That last one was a real bug: the
calculation speculatively removed each active filter to count the results, and
the keyword filter's remover reached into the DOM and cleared the box, which
the rollback did not undo. Now the box mirrors `state.q` from one place, and
never while it has focus, because rewriting an input somebody is typing into
moves their caret.

**It tells you what it did and did not understand.** Whatever it recognised
comes back as chips, and the dropdowns move to match, so it never filters
behind your back. If it recognised nothing it says so in a live region and
filters nothing, rather than showing an empty list and letting you guess.
