# Kid Events in Ann Arbor

Every kids event in and around Ann Arbor, pulled from a dozen sites once a day
and put on one page you can filter and subscribe to.

**Live site:** https://shinabarger.github.io/kid-events-in-ann-arbor

## Open it right now

The site is the repo. `index.html` at the top level is the whole thing, and
GitHub Pages serves it straight from `main`.

Locally it needs a server, because a browser will not let a page opened from
`file://` fetch `data/events.json`, so double clicking `index.html` shows an
empty page:

```bash
python -m http.server 8000
# then open http://localhost:8000
```

If you want it offline with no server at all, build the single file version:

```bash
python scripts/build_preview.py preview.html
```

That inlines everything into one double-clickable file. It is deliberately not
committed, because the repo is already the site.

## Why

Finding something to do with a kid on a Saturday morning meant checking AADL,
then Ann Arbor with Kids, then the Observer, then a couple of Facebook groups,
and every one of them was missing something the others had. This pulls them
together, drops the duplicates, and puts the whole thing on my phone calendar.

## What it does

- Pulls from AADL, Ann Arbor with Kids, both Observer calendars, the U-M events
  API, Destination Ann Arbor, city Parks & Rec, the city calendar, the museums,
  the Metroparks, Rec & Ed, and the county and district libraries. Full list in
  `config/sources.yaml`.
- Takes a question in plain English. "Events in Ann Arbor for my 1.5 year old
  tomorrow afternoon" sets the age, day, time of day, and location filters, and
  shows you what it understood so you can correct it.
- Normalizes the age wording. AADL says "Babies Up To 24 Months", somebody else
  says "Grade K-5", another says nothing at all. All of it comes out the other
  side as age bands you can filter on.
- Drops duplicates. The same storytime shows up on four sites. It keeps the
  listing with the most detail and notes where else it appeared.
- Tags each event indoor or outdoor, free or paid, drop-in or registration
  required.
- Works out how far each venue is from downtown, so the location filter can do
  "city limits only", "within a 30 minute drive", or "anywhere in Washtenaw",
  plus a rough "within an hour bus ride" for anyone without a car that day.
- Writes 14 `.ics` feeds you can subscribe to from Google or Apple Calendar,
  plus per-event add buttons.

## Filters

Every dropdown takes more than one value. Pick babies and toddlers and you get
both, pick indoor and outdoor and you get both. Nothing checked means no filter,
which is why they read "All ages" and "Anywhere" at rest.

| Filter | Options |
| --- | --- |
| Age | Babies (0-2), toddlers (1-3), preschool (3-5), elementary (5-10), tweens (10-13), teens (13-18) |
| Location | Ann Arbor city limits, within a 30 minute drive, Washtenaw County, within an hour bus ride |
| Indoor or outdoor | Indoor, outdoor |
| Cost | Free, paid |
| Signup | Drop in, registration required |
| Repeats | Show or hide all-day repeats, one or the other |
| When | Today & tomorrow (default), today, tomorrow, this weekend, next 7 days, next 30 days, everything |

Repeats is the one single choice filter. A few sources carry standing all-day
listings like "Kids Eat Free" that show up every single day. Anything on five
or more separate days gets flagged, and only the all-day ones are hidden, so a
weekly storytime with a real start time stays put.

The page opens on **today and tomorrow**, because that is what people are
actually looking for, and 30-odd events reads better than 2,000. The chip above
the results says so, and one click widens it.

Every filter that is on shows as a chip above the results. Click the chip to
take that one off, hit Undo to walk back a step, or Show everything to clear
the lot.

Filters go into the URL, so a link to "free outdoor toddler stuff this weekend"
is shareable.

## The search bar

It is a rules parser, not a model. That is deliberate: it runs in the browser
with no API key, costs nothing, works offline, never invents an answer, and
every rule is one you can read in `assets/nlq.js`.

| You type | It sets |
| --- | --- |
| "for my 1.5 year old" | Babies and toddlers |
| "my 5 year old", "kindergartener" | Preschool and elementary |
| "18 month old", "7yo", "2 and a half" | The matching bands |
| "today", "tonight", "tomorrow", "this weekend", "on Saturday" | The date |
| "morning", "afternoon", "evening", "after nap" | The time of day |
| "in Ann Arbor", "near me", "in the area", "Washtenaw" | The location |
| "free", "indoor", "rainy day", "drop in" | Cost, setting, signup |

Anything it does not recognize becomes a keyword search, so a query is never
worse than typing the words in a plain search box. Whatever it did understand
comes back as chips under the box, and the dropdowns move to match, so it never
filters behind your back. If it understood nothing, it says so and filters
nothing.

## The event card

Title, then the subtitle in bold blue (venue, city, drive time), then the
description clamped to two lines so the list stays skimmable.

Clicking the title expands the card in place: the description unclamps and a
detail list appears with when, where, drive time, ages, cost, signup, setting,
and which source it came from. Clicking again shrinks it back.

Four buttons on every card: **Add to Google Calendar**, **Add to Apple
Calendar**, **Copy link**, and **View on Website**. Copy link gives you a
permalink like `?event=abc123` that opens the site with that one event expanded
and highlighted, which is the thing to paste into a text or a Discord channel.

Whatever lands in your calendar carries the full address, coordinates so the
app can map it, the ages, the cost, whether you have to register, and a link
back. Not just a title and a time.

View on Website goes to the event's own page, never to a calendar index. If a
source only gave us a listing URL, the button is hidden instead, because
sending someone to an index to hunt for the row they already had is worse than
no link.

## Calendar subscriptions

Every feed lives in `feeds/` and is served from GitHub Pages. Both
Google and Apple poll them on their own schedule, so you set one up once and it
keeps itself current.

| Feed | What is in it |
| --- | --- |
| `all.ics` | Everything |
| `age-baby.ics` through `age-teen.ics` | One per age band |
| `ann-arbor-city.ics` | Inside the city limits |
| `within-30-minutes.ics` | About a 30 minute drive or less |
| `bus-reachable.ics` | Plausibly an hour or less on TheRide |
| `washtenaw-county.ics` | Anywhere in the county |
| `free.ics`, `drop-in.ics`, `indoor.ics`, `outdoor.ics` | The obvious ones |

**On the bus filter.** It is deliberately coarse. Working out a real trip needs
the live GTFS feed, the time of day, and the stop you are starting from, none
of which this site knows. What it does know is the city, the zone, and the
drive time, so the answer it gives is "plausibly reachable on TheRide in about
an hour, walking included" rather than a promise. Individual venues can be
corrected with a `bus: true` or `bus: false` line in `config/venues.yaml`, which
beats the guess. Check theride.org before you rely on it.

**Sync to my calendar** on the site lets you tick as many as you like. Each one
becomes its own calendar in your app, which you can colour separately. A 14
month old wants Babies and Toddlers both, so ticking two is normal. Google gets an
`https://` URL through its add-by-URL screen, Apple gets the same URL as
`webcal://` so the Calendar app picks it up.

## Where the data comes from, and how

Short version: this is a signpost. It reads what sites already publish, keeps
the facts, keeps a couple of sentences so you can tell whether to go, and then
sends you to them for the rest. It is not a mirror of anybody's calendar.

Every source in `config/sources.yaml` has to declare one of three bases, and a
test fails the build if one does not:

| `access` | What it means |
| --- | --- |
| `feed` | The site publishes RSS or iCal. A feed is an invitation. |
| `public-api` | A documented, unauthenticated API meant to be called. |
| `crawl` | Ordinary pages, read one request at a time, robots.txt obeyed. |
| `schedule` | Nothing is fetched at all. A published recurrence, transcribed by hand into `config/recurring.yaml`. |

Anything that needs a login, an undocumented internal API, or a user agent
pretending to be a browser does not go in. That is why Facebook is not here
even though plenty of events only live there, and why
`config/manual_events.yaml` exists instead.

### What the code does on every run

- **Obeys robots.txt, per URL, automatically.** `scraper/robots.py` checks
  before every single request and honors `Crawl-delay`. A site can shut this
  off entirely by naming `kid-events-in-ann-arbor` in its robots.txt, and never
  has to contact anybody to do it.
- **Stops on a 401 or 403 instead of retrying.** Retrying past a closed door is
  how a polite crawler turns into a rude one.
- **One pass a day, one request at a time,** with a 0.4 second gap and a six
  hour cache. This is less traffic than one person browsing the site.
- **Says who it is.** The user agent carries the project name, a link to this
  repo, and a way to reach me, so anybody who wants this to stop can send one
  email instead of one letter.
- **Keeps facts, excerpts prose.** A date, a time, an address, a price and an
  age range are facts, and facts are nobody's property. The paragraph somebody
  wrote is theirs, so `scraper/courtesy.py` trims it to about 280 characters at
  a sentence break and links out.
- **Never copies images.** Photographs are the most clearly owned thing on an
  event page, so none are copied or hotlinked.
- **Links back on every single card,** and never to a calendar index. If a
  source did not give a specific page, the button is hidden rather than
  guessing.
- **Honors an opt-out list** in `config/optout.yaml`, read fresh every run.

### Pages that look like pictures

The Mamas Network publish their month as a Canva Sites page: event names
floating on a grid, no dates attached to the text, no feed, and in the rendered
DOM a pile of unclassed `<p>` tags at absolute positions. It looks
unscrapeable, and the first version of this only took their stated rules.

It is not unscrapeable. Canva ships the whole document as JSON inside the HTML,
so one plain GET gets every text box with its position, its lines, and its
link. `scraper/sources/canva.py` rebuilds the grid from that. No headless
browser, no rendering, no JavaScript.

Their grid is transposed, columns are weeks and rows are days of the week, but
nothing in the adapter assumes that. The day numbers are text boxes too, so the
cell-to-date mapping is read off the page rather than guessed, and it survives
them rearranging it. An event box sits slightly down and right of its day
number, so it snaps to the last column and row at or before it.

The one thing the grid cannot carry is an age, because a cell fits a time, a
name and a venue and nothing else. Those come from `ages:` in
`config/sources.yaml`, matched on the title, taken from the descriptions further
down their own page.

### Schedules, for the months nobody has published yet

A site that publishes one month at a time leaves the other three months of the
horizon empty. Most of them also state their recurring rule in the words a
person needs, "1st & 3rd Saturday 9-11am", so `config/recurring.yaml` holds the
rule and `scraper/sources/recurring.py` projects it forward.

A projection is a guess about a month nobody has published. So a series can
name a `defer_to` source, and any projected occurrence falling inside the range
that source actually returned is dropped. Their page always wins over the rule,
even when the two disagree.

When they disagree, the run says so:

```
Rules that no longer match the published calendar: 1
  check config/recurring.yaml: DADaS & Littles on 2026-10-03 is not on their page
```

That one is real. The rule says 1st Saturday, and their October page has the
Birth & Baby Fair in that slot instead. A hand written rule would have quietly
shown a playgroup that is not happening.

Projected occurrences are labelled as such on the card, and every series
carries a `checked` date saying when a human last read the source page. Tests
fail the build if a series has no `checked` date or no link back.

### If you run one of these sites

Open an issue, or email me, and I will take you out. You do not have to explain
why and I will not ask. It takes one line in `config/optout.yaml` and it takes
effect on the next morning's run. There is a link to that in the site footer
too, so it is findable without reading this file.

If you would rather stay in but want something fixed, that is a smaller issue
and I would rather do that: wrong times, a listing you would like linked
differently, a source name spelled properly.


## How it is put together

```
scraper/
  run.py          the pipeline: collect, normalize, dedupe, write
  models.py       the Event record and the age band definitions
  classify.py     age, indoor/outdoor, cost, registration, from free text
  geo.py          venue to city, coordinates, drive time, zone
  dedupe.py       collapse the same event from multiple sources
  icsbuild.py     write the .ics feeds
  http.py         cached, rate limited fetching
  sources/
    aadl.py               custom, their listing markup is the best age data
    trumba.py             Trumba calendars, read as iCal not RSS
    annarborwithkids.py   their published iCal feed, categories and all
    observer.py           the hand written Observer kids calendar, parsed from prose
    umich.py              their JSON API
    generic.py            schema.org JSON-LD, RSS, and iCal for everything else
    manual.py             config/manual_events.yaml
    recurring.py          expands the rules in config/recurring.yaml
    canva.py              rebuilds a calendar from a Canva Sites document
config/
  sources.yaml       what to scrape and how
  venues.yaml        venue lookup, coordinates, drive times
  recurring.yaml     published schedules, as rules rather than scrapes
  manual_events.yaml hand added events
  optout.yaml        organizers who asked to be left out
  snapshot/seed.json a real snapshot, so a fresh clone is not empty

index.html           the site itself, served from the repo root
assets/nlq.js        the plain language search parser
data/events.json     what the page loads, rewritten every morning
feeds/               the .ics calendar feeds
tests/               parser tests against saved copies of the real pages
```

Adding a site is usually a few lines in `config/sources.yaml`. Most event
calendars publish schema.org JSON-LD, which `generic.py` already reads. Only
write a new module when a site does something weird.

## Tests

349 tests, none of them touch the network.

`python -m pytest -q` covers the parsers against saved copies of the real
markup and feeds, the age and location classifiers, dedupe, the generated
`.ics` files, and a full WCAG AA audit computed off the CSS tokens.

`npm test` runs two suites. `tests/nlq.test.mjs` exercises the search parser on
its own, every age phrasing and date phrasing it claims to handle.
`tests/frontend.test.mjs` loads the actual page into jsdom with the sample data
baked in, then drives the search bar, the multi selects, the keyboard
interactions, the month grid, the detail dialog, the calendar buttons, and the
subscribe dialog the way a person would.

[BROWSERS.md](BROWSERS.md) covers what the Safari checks catch and the ten
minute manual pass on a real iPhone that they cannot replace.

Accessibility gets its own writeup in [ACCESSIBILITY.md](ACCESSIBILITY.md),
including what the tests cover and the four things that still need a human.
[USABILITY.md](USABILITY.md) walks the Nielsen Norman heuristics one by one.

## When something breaks

The footer lists every source with its event count. A source showing "no data"
means its adapter needs a look, usually because the site redesigned. The
parser tests in `tests/` run against saved copies of the real markup, so when
those fail that is the same signal.

One bad source never kills the run. It gets logged, reported in the footer, and
everything else still publishes.

## Notes

Times come straight from the source. Always double check with the organizer
before you load the car, especially for anything outdoors in Michigan.

MIT licensed. The event data belongs to whoever published it, this just points
at it.
