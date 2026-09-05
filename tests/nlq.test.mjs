/* Unit tests for the plain language parser, with no DOM in the way.

   node --test tests/nlq.test.mjs */

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const scope = {};
new Function("globalThis", readFileSync(join(ROOT, "assets/nlq.js"), "utf8"))(scope);
const NLQ = scope.NLQ;

// A fixed Friday so the weekday maths is checkable.
const FRIDAY = new Date(2026, 8, 4);

const parse = (text) => NLQ.parse(text, FRIDAY);

/* --- the two queries from the brief --------------------------------------- */

test("events in Ann Arbor for my 1.5 year old tomorrow afternoon", () => {
  const r = parse("events in Ann Arbor for my 1.5 year old tomorrow afternoon");
  assert.deepEqual(r.age, ["baby", "toddler"]);
  assert.equal(r.when, "tomorrow");
  assert.equal(r.timeOfDay, "afternoon");
  assert.deepEqual(r.where, ["city"]);
  assert.deepEqual(r.keywords, []);
});

test("events in the area for my 5 year old today", () => {
  const r = parse("events in the area for my 5 year old today");
  assert.deepEqual(r.age, ["preschool", "elementary"]);
  assert.equal(r.when, "today");
  assert.deepEqual(r.where, ["near"]);
});

/* --- ages ----------------------------------------------------------------- */

test("a plain age lands in every band it touches", () => {
  assert.deepEqual(NLQ.bandsForAge(0), ["baby"]);
  assert.deepEqual(NLQ.bandsForAge(1.5), ["baby", "toddler"]);
  assert.deepEqual(NLQ.bandsForAge(2), ["baby", "toddler"]);
  assert.deepEqual(NLQ.bandsForAge(3), ["toddler", "preschool"], "a 3 year old is both");
  assert.deepEqual(NLQ.bandsForAge(4), ["preschool"]);
  assert.deepEqual(NLQ.bandsForAge(5), ["preschool", "elementary"]);
  assert.deepEqual(NLQ.bandsForAge(11), ["tween"]);
  assert.deepEqual(NLQ.bandsForAge(15), ["teen"]);
});

test("ages written every which way", () => {
  const cases = [
    ["my 3 year old", ["toddler", "preschool"]],
    ["a 3-year-old", ["toddler", "preschool"]],
    ["7yo", ["elementary"]],
    ["8 y/o", ["elementary"]],
    ["18 month old", ["baby", "toddler"]],
    ["6 months old", ["baby"]],
    ["2 and a half year old", ["toddler"]],
    ["my toddler", ["toddler"]],
    ["for a baby", ["baby"]],
    ["preschooler", ["preschool"]],
    ["kindergartener", ["preschool", "elementary"]],
    ["my teenager", ["teen"]],
    ["tween", ["tween"]],
    ["middle schooler", ["tween", "teen"]],
  ];
  for (const [text, expected] of cases) {
    assert.deepEqual(parse(text).age, expected, `failed on "${text}"`);
  }
});

test("an age it cannot find leaves the filter alone", () => {
  assert.deepEqual(parse("something fun downtown").age, []);
});

/* --- dates ---------------------------------------------------------------- */

test("today, tomorrow, and the weekend", () => {
  assert.equal(parse("anything today").when, "today");
  assert.equal(parse("anything tomorrow").when, "tomorrow");
  assert.equal(parse("this weekend").when, "weekend");
  assert.equal(parse("next week").when, "week");
  assert.equal(parse("this month").when, "month");
  assert.equal(parse("no date here").when, null);
});

test("tonight means today plus the evening", () => {
  const r = parse("what is on tonight");
  assert.equal(r.when, "today");
  assert.equal(r.timeOfDay, "evening");
});

test("a weekday resolves to the next one", () => {
  // The fixed date is Friday September 4, 2026.
  assert.equal(parse("stuff on saturday").date, "2026-09-05");
  assert.equal(parse("stuff on monday").date, "2026-09-07");
  assert.equal(parse("friday").date, "2026-09-04", "today counts as the next Friday");
});

test("times of day", () => {
  assert.equal(parse("tomorrow morning").timeOfDay, "morning");
  assert.equal(parse("saturday afternoon").timeOfDay, "afternoon");
  assert.equal(parse("friday evening").timeOfDay, "evening");
  assert.equal(parse("after nap").timeOfDay, "afternoon");
  assert.equal(parse("sometime").timeOfDay, null);
});

/* --- place ---------------------------------------------------------------- */

test("place phrasings", () => {
  assert.deepEqual(parse("in ann arbor").where, ["city"]);
  assert.deepEqual(parse("downtown ann arbor").where, ["city"]);
  assert.deepEqual(parse("near me").where, ["near"]);
  assert.deepEqual(parse("in the area").where, ["near"]);
  assert.deepEqual(parse("close by").where, ["near"]);
  assert.deepEqual(parse("washtenaw county").where, ["county"]);
  assert.deepEqual(parse("wherever").where, []);
});

/* --- the rest ------------------------------------------------------------- */

test("cost, setting, signup, and repeats", () => {
  assert.deepEqual(parse("free stuff").cost, ["free"]);
  assert.deepEqual(parse("indoor things").setting, ["indoor"]);
  assert.deepEqual(parse("rainy day ideas").setting, ["indoor"]);
  assert.deepEqual(parse("outside").setting, ["outdoor"]);
  assert.deepEqual(parse("drop in classes").signup, ["dropin"]);
  assert.deepEqual(parse("no registration").signup, ["dropin"]);
  assert.deepEqual(parse("one off events").repeats, ["oneoff"]);
});

test("leftover words become a keyword search", () => {
  assert.deepEqual(parse("lego club").keywords, ["lego", "club"]);
  assert.deepEqual(parse("storytime for a toddler").keywords, ["storytime"]);
  assert.deepEqual(parse("museum stuff for a 7 year old").keywords, ["museum"]);
});

test("filler on its own understands nothing, which is the honest answer", () => {
  const r = parse("something to do for the kids");
  assert.deepEqual(r.keywords, []);
  assert.deepEqual(r.understood, []);
  assert.equal(r.when, null);
});

test("it reports back every phrase it matched", () => {
  const r = parse("free indoor events for my 2 year old today in ann arbor");
  assert.ok(r.understood.includes("2 year old"));
  assert.ok(r.understood.includes("today"));
  assert.ok(r.understood.includes("Free"));
  assert.ok(r.understood.includes("Indoor"));
  assert.ok(r.understood.includes("City limits"));
});

test("an empty query is empty, not a crash", () => {
  const r = parse("");
  assert.deepEqual(r.age, []);
  assert.deepEqual(r.keywords, []);
  assert.equal(r.when, null);
});

test("age parsing does not swallow a time", () => {
  const r = parse("events at 2 pm tomorrow");
  assert.deepEqual(r.age, [], "2 pm is a time, not a two year old");
});

test("asking about the bus sets the bus filter, not the city one", () => {
  for (const q of [
    "storytime on the bus",
    "somewhere we can get to without a car",
    "free indoor thing, no car today",
    "toddler stuff we can take the bus to",
  ]) {
    const parsed = NLQ.parse(q, new Date("2026-09-05T09:00:00-04:00"));
    assert.deepEqual(parsed.where, ["bus"], `"${q}" should ask about the bus`);
  }
});

test("a bus question inside Ann Arbor is still a bus question", () => {
  // The city pattern used to swallow this one, which quietly answered a
  // different question than the one that was asked.
  const parsed = NLQ.parse("something in Ann Arbor we can get to on the bus",
    new Date("2026-09-05T09:00:00-04:00"));
  assert.deepEqual(parsed.where, ["bus"]);
});

test("plain Ann Arbor still means the city limits", () => {
  const parsed = NLQ.parse("free things in Ann Arbor tomorrow",
    new Date("2026-09-05T09:00:00-04:00"));
  assert.deepEqual(parsed.where, ["city"]);
});
