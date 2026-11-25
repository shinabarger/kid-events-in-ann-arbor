# Kid Events in Ann Arbor

Every kids event in and around Ann Arbor, pulled from a dozen sites once a day
and put on one page you can filter and subscribe to.

Always double check with the organizer before you head out, especially for
anything outdoors. Times come straight from the source.

**Live site:** https://kideventsinannarbor.com

## Why

Finding something to do with a kid on a Saturday morning meant checking a
handful of different sites, and every one of them was missing something the
others had. This pulls them together, drops the duplicates, and puts the whole
thing on my phone calendar.

## What it does

- Pulls from various AA Data Sources and adds them to the calendar, scraping 1x
  a day overnight.
- Takes a question in plain English. "Events for my 1.5 year old tomorrow
  afternoon" sets the age, day, time of day, and location filters, and shows
  you what it understood so you can correct it.
- Normalizes age wording across sources into filterable age bands. One source
  says "Babies Up To 24 Months", another says "Grade K-5", another says
  nothing at all. All of it comes out as consistent age bands you can filter on.
- Drops duplicates. The same storytime shows up on four sites. It keeps the
  listing with the most detail and notes where else it appeared.
- Tags each event indoor or outdoor, free or paid, drop-in or registration
  required.
- Estimates drive time from downtown for location filtering, so you can do
  "city limits only", "within a 30 minute drive", or "anywhere in Washtenaw".
- Writes `.ics` feeds you can subscribe to from Google or Apple Calendar,
  plus per-event add buttons.

## How it Works

```
scraper/           the pipeline: collect, normalize, dedupe, write
config/            sources, venues, recurring schedules, manual events
assets/            frontend JS including the plain language search parser
data/events.json   what the page loads, rewritten every morning
feeds/             the .ics calendar feeds
tests/             parser and frontend tests
```

Adding a source is usually a few lines in `config/sources.yaml`. Most event
calendars publish schema.org JSON-LD, which the generic adapter already reads.

## Tests

`python -m pytest -q` covers the parsers, classifiers, dedupe, and generated
feeds against saved copies of real markup and data. `npm test` covers the
search parser and full frontend interactions in jsdom.

None of them touch the network.

## If you run one of these sites

Open an issue or email me, and I will take you out. You do not have to explain
why. It takes one line in `config/optout.yaml` and takes effect on the next
morning's run. There is a link to that in the site footer too.

If you would rather stay in but want something fixed (wrong times, a listing
linked differently, a source name spelled properly), that works too.

---

MIT licensed. The event data belongs to whoever published it, this just points
at it.
