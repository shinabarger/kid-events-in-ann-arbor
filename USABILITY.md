# Usability review

Against Nielsen and Norman's ten heuristics. Where a heuristic maps onto
something a test can assert, there is a test, in `tests/test_accessibility.py`
and `tests/frontend.test.mjs`. Where it does not, the reasoning is written down
so a later change has something to argue with.

## 1. Visibility of system status

- The result count updates on every change and lives in a polite live region,
  so it is announced, not just repainted.
- An **active filter strip** sits above the results listing every filter that
  is currently doing something. If a filter is on, it is on the screen.
- The footer says when the data was last updated, how many events it holds, and
  names every source with its event count. A source that failed says "no data"
  in words as well as color.
- The list shows a loading line before the data lands rather than an empty page.

## 2. Match between the system and the real world

- The search box takes the question the way a parent would say it: "events for
  my 1.5 year old tomorrow afternoon".
- Filters are named in parent language. "Within about 29 minutes", not a radius
  in miles. "Drop in, no signup", not "registration_required = false".
- Day headings say "Today" and "Tomorrow" before they say a date, and the page
  opens on those two days, because that is the question people actually arrive
  with. The chip above the results says so rather than leaving you to wonder
  why the list is short.
- Drive time is on the card, because "how far is it" is the real question.

## 3. User control and freedom

This is the one that needed the most work.

- **Undo.** Every filter change, search, and chip removal pushes the previous
  state onto a stack. The Undo button walks it back. It is disabled when there
  is nothing to undo, so it never lies about being available.
- **Every filter chip is a remove button.** One click takes off exactly the
  thing you did not mean, without touching the rest.
- **Show everything** clears the lot, and it appears in three places: the filter
  bar, the active filter strip, and the dead end state.
- The dialogs close on Escape, on the backdrop, and on the X, and focus goes
  back to whatever opened them.
- Filters live in the URL, so a link is a saved state you can return to.

## 4. Consistency and standards

- One button system, one chip system, one dialog pattern, used everywhere.
- Blue means a link or a place, green means the current selection, amber means
  "there is a catch" (registration required). Nothing else uses those roles.
- The date chips look like pills but are a real radio group, so arrow keys work
  the way the platform says they should.

## 5. Error prevention

- Almost nothing here is an error, because almost nothing is destructive. The
  worst outcome is a filter combination that shows nothing, and that is
  reversible in one click.
- Filters that are mutually exclusive are radios, not checkboxes, so an
  impossible combination cannot be selected. Repeats is either shown or hidden,
  never both, and there is no "only repeats" option because nobody wants that.
- The search never guesses. If it cannot read a query it says so and filters
  nothing, rather than quietly narrowing to zero.

## 6. Recognition rather than recall

- The active filter strip means you never have to open a dropdown to remember
  what is on.
- The search moves the dropdowns to match what it understood, so the plain
  language path and the manual path show the same state.
- Every dropdown button shows its current value, not just its name: "Age,
  Babies +1".
- Every card carries its badges, so you do not have to remember why it matched.

## 7. Flexibility and efficiency of use

- Two ways to do everything: type it, or use the dropdowns.
- `/` focuses the search box from anywhere on the page.
- Filters are multi select, so one pass sets up "babies or toddlers, indoor,
  free" instead of three separate visits.
- Shareable URLs, and 14 calendar feeds for people who would rather not visit
  the site at all.
- List view for reading, month view for planning ahead.

## 8. Aesthetic and minimalist design

- The search box explains itself with its placeholder. There is no paragraph
  of instructions, because a search box that needs a paragraph is the wrong
  search box.
- Descriptions clamp to two lines in the list. The full text is one click away
  in the detail dialog.
- The active filter strip is empty, and takes no space, when nothing is on.
- Badges are capped so a card never becomes a wall of chips.

## 9. Help users recognize, diagnose, and recover from errors

- The dead end state does arithmetic instead of apologizing. It works out which
  single filter is costing you the most results and says so: "Nothing matches
  all of that. Dropping Tomorrow would show 22 events."
- It offers both Undo and Show everything right there.
- If the whole calendar is empty it says the daily update may not have run,
  which is the actual likely cause on a fresh install.

## 10. Help and documentation

- Not much needed, which is the goal.
- The footer says where the data comes from and reminds you to confirm times
  with the organizer, which is the one piece of advice that actually matters.
- The subscribe dialog explains the Apple and Google difference in one sentence
  at the point where the difference matters, not in a help page.
- `README.md` covers setup, `ACCESSIBILITY.md` covers the WCAG work, and this
  file covers the reasoning.

## Still open

- The month view is a visual grid rather than a table. Fine to tab through, but
  the list is the better screen reader experience, which is why it is the
  default.
- There is no saved view. If someone finds themselves setting the same three
  filters every Saturday, a bookmarked URL does the job today, but a named
  saved search would do it better.
- No offline support. A service worker would make the calendar readable in a
  parking lot with no signal, which is exactly where it would get used.
