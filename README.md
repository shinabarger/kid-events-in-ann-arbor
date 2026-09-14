# Kid Events in Ann Arbor

Every kids event in and around Ann Arbor, pulled from a dozen sites once a day
and put on one page you can filter and subscribe to.

Always double check with the organizer before you head out, especially for
anything outdoors. Times come straight from the source.

**Live site:** https://kideventsinannarbor.com

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
- Takes a question in plain English. "Events for my 1.5 year old tomorrow
  afternoon" sets the age, day, time of day, and location filters, and shows
  you what it understood so you can correct it.
- Normalizes age wording across sources into filterable age bands. AADL says
  "Babies Up To 24 Months", somebody else says "Grade K-5", another says
  nothing at all. All of it comes out as consistent age bands you can filter on.
- Drops duplicates. The same storytime shows up on four sites. It keeps the
  listing with the most detail and notes where else it appeared.
- Tags each event indoor or outdoor, free or paid, drop-in or registration
  required.
- Estimates drive time from downtown for location filtering, so you can do
  "city limits only", "within a 30 minute drive", or "anywhere in Washtenaw".
- Writes `.ics` feeds you can subscribe to from Google or Apple Calendar,
  plus per-event add buttons.

## The search bar

It is a rules parser, not a model. It runs in the browser with no API key,
costs nothing, and works offline.

| You type | It sets |
| --- | --- |
| "for my 1.5 year old" | Babies and toddlers |
| "my 5 year old", "kindergartener" | Preschool and elementary |
| "today", "tomorrow", "this weekend" | The date |
| "morning", "afternoon", "evening" | The time of day |
| "in Ann Arbor", "Washtenaw" | The location |
| "free", "indoor", "drop in" | Cost, setting, signup |

Anything it does not recognize becomes a keyword search, so a query is never
worse than typing the words in a plain search box. Whatever it understood comes
back as chips under the box, and the dropdowns move to match.

## Filters

Every dropdown takes more than one value. Pick babies and toddlers and you get
both. Nothing checked means no filter.

| Filter | Options |
| --- | --- |
| Age | Babies (0-2), toddlers (1-3), preschool (3-5), elementary (5-10), tweens (10-13), teens (13-18) |
| Location | Ann Arbor city limits, within a 30 minute drive, Washtenaw County, within an hour bus ride |
| Indoor or outdoor | Indoor, outdoor |
| Cost | Free, paid |
| Signup | Drop in, registration required |
| Repeats | Show or hide all-day repeats |

Filters go into the URL, so a filtered view is shareable. Every active filter
shows as a chip above the results. Click the chip to remove it, or hit
Show everything to clear them all.

The page opens on **today and tomorrow** by default, because that is what
people are actually looking for. One click widens it.

## Calendar subscriptions

Feeds live in `feeds/` and are served from GitHub Pages. Both Google and Apple
poll them on their own schedule, so you set one up once and it stays current.

| Feed | What is in it |
| --- | --- |
| `all.ics` | Everything |
| `age-baby.ics` through `age-teen.ics` | One per age band |
| `ann-arbor-city.ics` | Inside the city limits |
| `within-30-minutes.ics` | About a 30 minute drive or less |
| `free.ics`, `drop-in.ics`, `indoor.ics`, `outdoor.ics` | The obvious ones |

**Sync to my calendar** on the site lets you pick which feeds to subscribe to.
Each one becomes its own calendar in your app, which you can color separately.

## The event card

Clicking an event title expands the card in place with the full description,
venue, drive time, ages, cost, signup, and source.

Four buttons on every card: **Add to Google Calendar**, **Add to Apple
Calendar**, **Copy link**, and **View on Website**. Copy link gives you a
permalink that opens the site with that event expanded, good for sharing in a
text or a group chat.

Whatever lands in your calendar carries the full address, coordinates, ages,
cost, whether you have to register, and a link back.

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
