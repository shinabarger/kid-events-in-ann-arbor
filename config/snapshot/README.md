# Snapshot

`seed.json` is a real snapshot of what the sources were publishing on
**September 4, 2026**, captured so a fresh clone shows a full, believable
calendar instead of a handful of made up events.

It is not live data. The daily Action overwrites `data/events.json` with
the real thing on its first run, and after that this file is only used by
`scripts/build_sample.py` when you want to work on the CSS offline.

Dates in `seed.json` are stored as day offsets from whenever you build, so the
snapshot always lands on today, tomorrow, and so on rather than drifting into
the past.
