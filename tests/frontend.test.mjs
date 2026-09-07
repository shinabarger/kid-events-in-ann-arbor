/* Front end tests. Loads the real page into jsdom with the sample data baked
   in, then drives the filters the way a person would and checks what renders.

   node --test tests/frontend.test.mjs
   (needs jsdom: npm install) */

import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function buildPage() {
  const out = join(mkdtempSync(join(tmpdir(), "a2kids-")), "preview.html");
  execFileSync("python3", [join(ROOT, "scripts", "build_preview.py"), out], { cwd: ROOT });
  return readFileSync(out, "utf8");
}

const HTML = buildPage();

async function load() { return loadPage(HTML); }

async function loadPage(html) {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "https://shinabarger.github.io/kid-events-in-ann-arbor/",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  // jsdom ships none of these yet.
  if (!window.matchMedia) {
    window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  }
  window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  window.HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
    this.dispatchEvent(new window.Event("close"));
  };
  await new Promise((r) => window.addEventListener("load", r));
  await new Promise((r) => window.setTimeout(r, 60));
  return window;
}

/* --- helpers -------------------------------------------------------------- */

function cards(window) {
  return [...window.document.querySelectorAll("#list-view .card")];
}

function titles(window) {
  return cards(window).map((c) => c.querySelector(".card-name").textContent);
}

function openFilter(window, name) {
  window.document.getElementById(`btn-${name}`).click();
  return window.document.getElementById(`panel-${name}`);
}

function pick(window, name, ...values) {
  const panel = window.document.getElementById(`panel-${name}`);
  for (const value of values) {
    const box = panel.querySelector(`input[value="${value}"]`);
    assert.ok(box, `no option "${value}" in the ${name} filter`);
    box.checked = true;
    box.dispatchEvent(new window.Event("change", { bubbles: true }));
  }
}

function unpick(window, name, value) {
  const box = window.document.querySelector(`#panel-${name} input[value="${value}"]`);
  box.checked = false;
  box.dispatchEvent(new window.Event("change", { bubbles: true }));
}

function summary(window, name) {
  return window.document.getElementById(`val-${name}`).textContent;
}

function showAll(window) {
  const radio = window.document.querySelector('input[name="when"][value="all"]');
  radio.checked = true;
  radio.dispatchEvent(new window.Event("change", { bubbles: true }));
}

/* --- rendering ------------------------------------------------------------ */

test("the page renders every sample event on load", async () => {
  const window = await load();
  assert.ok(cards(window).length >= 10, "expected the sample events to render");
  assert.match(window.document.getElementById("count").textContent, /\d+ events found/);
  assert.equal(window.document.getElementById("empty").hidden, true);
});

test("the page opens on today and tomorrow", async () => {
  const window = await load();
  const checked = window.document.querySelector('input[name="when"]:checked');
  assert.equal(checked.value, "next2");
  assert.equal(checked.parentElement.textContent.trim(), "Today & tomorrow");

  const headings = [...window.document.querySelectorAll(".day-heading")]
    .map((h) => h.textContent);
  assert.equal(headings.length, 2, "only today and tomorrow should be on screen");
  assert.match(headings[0], /Today/);
  assert.match(headings[1], /Tomorrow/);

  // And it says so, with one click to see the rest.
  const chips = readAs(window);
  assert.ok(chips.includes("Today & tomorrow"), chips.join(" / "));
  assert.ok(window.document.querySelector("#active-bar .active-clear"));
});

test("widening to everything shows the whole horizon", async () => {
  const window = await load();
  const twoDays = cards(window).length;
  showAll(window);
  assert.ok(cards(window).length > twoDays);
  assert.equal(window.location.search, "?when=all");
});

test("events are grouped into day headings, today first", async () => {
  const window = await load();
  showAll(window);
  const headings = [...window.document.querySelectorAll(".day-heading")];
  assert.ok(headings.length > 2);
  assert.match(headings[0].textContent, /Today/);
});

test("the card puts the description directly under the subtitle", async () => {
  const window = await load();
  const card = cards(window).find((c) => c.querySelector(".card-desc"));
  const order = [...card.querySelector(".card-body").children].map((n) => n.className || n.tagName);

  const title = order.findIndex((c) => c.includes("card-title"));
  const where = order.findIndex((c) => c.includes("card-where"));
  const desc = order.findIndex((c) => c.includes("card-desc"));
  const badges = order.findIndex((c) => c.includes("badges"));

  assert.ok(title < where, "subtitle should follow the title");
  assert.ok(where < desc, "description should sit right under the subtitle");
  assert.ok(desc < badges, "badges come after the description");
  assert.equal(desc, where + 1, "nothing should come between the subtitle and description");
});

test("the subtitle is styled apart from the description", async () => {
  await load();
  // Anchor to the start of a line so ".card-desc" does not match
  // ".card.is-open .card-desc", which deliberately says the opposite.
  const rule = (selector) => {
    const match = new RegExp("^\\" + selector + " \\{([^}]*)\\}", "m").exec(HTML);
    assert.ok(match, `no rule for ${selector}`);
    return match[1];
  };
  assert.match(rule(".card-where"), /font-weight:\s*700/, "subtitle is not bolded");
  assert.match(rule(".card-where"), /color:\s*var\(--brand-blue-dark\)/, "subtitle is not colored");
  assert.match(rule(".card-desc"), /line-clamp:\s*2/, "description is not clamped to 2 lines");
});

test("the subtitle reads venue, city, and drive time", async () => {
  const window = await load();
  const fair = cards(window).find((c) => c.querySelector(".card-name").textContent === "Saline Fair");
  const where = fair.querySelector(".card-where").textContent;
  assert.match(where, /Washtenaw Farm Council Fairgrounds/);
  assert.match(where, /min/);
});

/* --- multi select filters ------------------------------------------------- */

test("every filter is a multi select that starts empty", async () => {
  const window = await load();
  assert.equal(summary(window, "age"), "All ages");
  assert.equal(summary(window, "where"), "Anywhere");
  assert.equal(summary(window, "setting"), "Either");
  assert.equal(summary(window, "cost"), "Any");
  assert.equal(summary(window, "signup"), "Any");

  for (const name of ["age", "where", "setting", "cost", "signup"]) {
    const panel = window.document.getElementById(`panel-${name}`);
    assert.ok(panel.querySelectorAll('input[type="checkbox"]').length >= 2,
      `${name} is not a checkbox group`);
  }
});

test("the age filter offers every band and picking one narrows the list", async () => {
  const window = await load();
  const values = [...window.document.querySelectorAll("#panel-age input")].map((b) => b.value);
  assert.deepEqual(values, ["baby", "toddler", "preschool", "elementary", "tween", "teen"]);

  // Widen first: the snapshot carries real dates now, so which events fall in
  // the default two day window depends on the day the suite runs.
  showAll(window);
  const before = cards(window).length;
  pick(window, "age", "baby");
  assert.ok(cards(window).length < before);
  assert.ok(titles(window).includes("Baby Playgroups"));
  assert.ok(!titles(window).includes("Silent Disco Dance Party"));
  assert.equal(summary(window, "age"), "Babies");
});

test("picking two ages shows events for either one", async () => {
  // Data driven on purpose. Pinning specific titles here is what broke when
  // the snapshot moved to real dates, and the thing being tested is the union,
  // not which events happen to be in the sample this week.
  const window = await load();
  showAll(window);

  pick(window, "age", "baby");
  const babyOnly = cards(window).length;

  window.document.querySelector('#panel-age input[value="baby"]').checked = false;
  window.document.querySelector('#panel-age input[value="baby"]')
    .dispatchEvent(new window.Event("change", { bubbles: true }));
  pick(window, "age", "teen");
  const teenOnly = cards(window).length;

  pick(window, "age", "baby");
  const both = cards(window).length;

  assert.ok(babyOnly > 0 && teenOnly > 0, "the sample needs both bands");
  assert.ok(both >= Math.max(babyOnly, teenOnly), "a union cannot be smaller than either side");
  assert.ok(both <= babyOnly + teenOnly, "and cannot exceed the sum");
  assert.equal(summary(window, "age"), "Babies +1");

  for (const card of cards(window)) {
    const badges = card.querySelector(".badges").textContent;
    // An all-ages event legitimately answers to both, and says so that way.
    assert.match(badges, /Bab|Teen|All ages/,
      "every card should match one of the two bands");
  }
});

test("all ages events land under every band picked", async () => {
  const window = await load();
  showAll(window);
  for (const band of ["baby", "preschool", "teen"]) {
    pick(window, "age", band);
    assert.ok(titles(window).includes("Monarch Migration Festival"),
      `all ages event missing from ${band}`);
    unpick(window, "age", band);
  }
});

test("unchecking the last option returns the filter to its empty state", async () => {
  const window = await load();
  const before = cards(window).length;
  pick(window, "age", "teen");
  assert.ok(cards(window).length < before);

  unpick(window, "age", "teen");
  assert.equal(cards(window).length, before);
  assert.equal(summary(window, "age"), "All ages");
});

test("the location filter can combine city limits with the county", async () => {
  const window = await load();
  pick(window, "where", "city");
  const city = cards(window).length;

  pick(window, "where", "county");
  const both = cards(window).length;
  assert.ok(both >= city, "adding a wider zone should not shrink the list");
  assert.equal(summary(window, "where"), "City limits +1");
});

test("indoor and outdoor can both be selected", async () => {
  const window = await load();
  showAll(window);
  pick(window, "setting", "outdoor");
  const outdoor = titles(window);
  assert.ok(outdoor.includes("Monarch Migration Festival"), outdoor.join(" / "));
  assert.ok(!outdoor.includes("Baby Playgroups"));

  pick(window, "setting", "indoor");
  const both = titles(window);
  assert.ok(both.includes("Baby Playgroups"));
  assert.ok(both.includes("Monarch Migration Festival"));
});

test("cost and signup filters work", async () => {
  const window = await load();
  pick(window, "cost", "free");
  assert.ok(cards(window).every((c) =>
    [...c.querySelectorAll(".badge")].some((b) => b.textContent === "Free")));

  unpick(window, "cost", "free");
  pick(window, "signup", "register");
  assert.ok(cards(window).every((c) =>
    [...c.querySelectorAll(".badge")].some((b) => b.textContent === "Registration required")));
});

test("clear this filter empties just that one", async () => {
  const window = await load();
  pick(window, "age", "baby", "toddler");
  pick(window, "cost", "free");

  window.document.querySelector("#panel-age .multi-clear").click();
  assert.equal(summary(window, "age"), "All ages");
  assert.equal(summary(window, "cost"), "Free");
});

/* --- multi select keyboard and state ------------------------------------- */

test("the filter button reports open and closed", async () => {
  const window = await load();
  const button = window.document.getElementById("btn-age");
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(window.document.getElementById("panel-age").hidden, true);

  button.click();
  assert.equal(button.getAttribute("aria-expanded"), "true");
  assert.equal(window.document.getElementById("panel-age").hidden, false);

  button.click();
  assert.equal(button.getAttribute("aria-expanded"), "false");
});

test("opening one panel closes the others", async () => {
  const window = await load();
  openFilter(window, "age");
  openFilter(window, "where");
  assert.equal(window.document.getElementById("panel-age").hidden, true);
  assert.equal(window.document.getElementById("panel-where").hidden, false);
});

test("arrow down opens the panel and escape closes it", async () => {
  const window = await load();
  const button = window.document.getElementById("btn-where");
  const panel = window.document.getElementById("panel-where");

  button.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  assert.equal(panel.hidden, false);
  assert.equal(window.document.activeElement, panel.querySelector("input"));

  panel.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(panel.hidden, true);
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(window.document.activeElement, button);
});

test("clicking outside closes an open panel", async () => {
  const window = await load();
  openFilter(window, "cost");
  window.document.body.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  assert.equal(window.document.getElementById("panel-cost").hidden, true);
});

/* --- search, dates, reset, URL ------------------------------------------- */

/* --- the plain language search bar ---------------------------------------- */

function ask(window, text) {
  const box = window.document.getElementById("ask");
  box.value = text;
  window.document.getElementById("ask-form")
    .dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
}

function readAs(window) {
  return [...window.document.querySelectorAll("#active-bar .active-chip")]
    .map((c) => c.querySelector("span").textContent);
}

test("a bare keyword search still works", async () => {
  const window = await load();
  showAll(window);
  const everything = cards(window).length;

  ask(window, "playgroup");
  // Several sources run playgroups now, so the contract is that it narrows
  // and finds the obvious one, not that exactly one listing matches.
  assert.ok(cards(window).length > 0);
  assert.ok(cards(window).length < everything, "a keyword search should narrow");
  assert.ok(titles(window).includes("Baby Playgroups"));

  ask(window, "metropark");
  assert.ok(titles(window).includes("Family Campfire Night"));
});

test("it understands an age, a day, and a time of day together", async () => {
  const window = await load();
  ask(window, "events in Ann Arbor for my 1.5 year old tomorrow afternoon");

  // The chips show what is filtering, in the site's own words.
  const chips = readAs(window);
  assert.ok(chips.includes("Babies"), chips.join(" / "));
  assert.ok(chips.includes("Toddlers"));
  assert.ok(chips.includes("Tomorrow"));
  assert.ok(chips.includes("Afternoon"));
  assert.ok(chips.includes("City limits"));

  // And the dropdowns move to match, so nothing is hidden from the user.
  assert.equal(summary(window, "age"), "Babies +1");
  assert.equal(summary(window, "where"), "City limits");
});

test("it understands the area and a five year old today", async () => {
  const window = await load();
  ask(window, "events in the area for my 5 year old today");

  const chips = readAs(window);
  assert.ok(chips.includes("Preschool"), chips.join(" / "));
  assert.ok(chips.includes("Elementary"));
  assert.ok(chips.includes("Today"));
  assert.ok(chips.includes("30 min drive"));

  // A five year old should read as preschool and elementary, not one or other.
  const boxes = [...window.document.querySelectorAll("#panel-age input:checked")]
    .map((b) => b.value);
  assert.deepEqual(boxes.sort(), ["elementary", "preschool"]);

  for (const card of cards(window)) {
    assert.match(card.querySelector(".card-day").textContent, /\w{3}/);
  }
});

test("months, tonight, and free all parse", async () => {
  const window = await load();

  ask(window, "what can I do with my 18 month old tonight");
  let chips = readAs(window);
  assert.ok(chips.includes("Babies"), chips.join(" / "));
  assert.ok(chips.includes("Today"));
  assert.ok(chips.includes("Evening"));

  ask(window, "free indoor events for my 2 year old today");
  chips = readAs(window);
  assert.ok(chips.includes("Free"));
  assert.ok(chips.includes("Indoor"));
  assert.equal(summary(window, "cost"), "Free");
  assert.equal(summary(window, "setting"), "Indoor");
});

test("time of day actually narrows the list", async () => {
  const window = await load();
  ask(window, "morning");
  const morning = cards(window).length;
  ask(window, "evening");
  const evening = cards(window).length;
  ask(window, "");
  const everything = cards(window).length;

  assert.ok(morning < everything, "morning should be a subset");
  assert.ok(evening < everything, "evening should be a subset");
});

test("an unrecognized word falls through to a keyword search", async () => {
  const window = await load();
  ask(window, "qqzz");
  assert.ok(readAs(window).some((c) => c.includes("qqzz")),
    "it should say it is searching for the word");
  assert.equal(cards(window).length, 0);
});

test("a query of nothing but filler says so instead of filtering blindly", async () => {
  const window = await load();
  showAll(window);
  const before = cards(window).length;
  ask(window, "something to do for the kids");
  assert.equal(readAs(window).length, 0);
  assert.match(window.document.querySelector("#active-bar .ask-note").textContent,
    /Nothing in that search matched/);
  assert.equal(cards(window).length, before, "nothing understood should mean nothing filtered");
});

test("show everything puts it all back", async () => {
  const window = await load();
  showAll(window);
  const everything = cards(window).length;

  ask(window, "free events for my 2 year old today");
  assert.ok(cards(window).length < everything);

  window.document.querySelector("#active-bar .active-clear").click();
  assert.equal(cards(window).length, everything, "show everything means the whole range too");
  assert.equal(window.document.getElementById("ask").value, "");
  assert.equal(summary(window, "age"), "All ages");
});

test("the search box explains itself with its placeholder, not a paragraph", async () => {
  const window = await load();
  assert.equal(window.document.querySelectorAll(".ask-help").length, 0,
    "the explanatory line should be gone");
  assert.match(window.document.getElementById("ask").getAttribute("placeholder"),
    /year old/, "the placeholder has to carry the affordance on its own");
});

test("an impossible combination shows the empty state", async () => {
  const window = await load();
  pick(window, "age", "baby");
  ask(window, "zzzznotathing");

  assert.equal(cards(window).length, 0);
  assert.equal(window.document.getElementById("empty").hidden, false);
  assert.match(window.document.getElementById("count").textContent, /No events match/);
});

test("filters go into the URL, several values at once", async () => {
  const window = await load();
  pick(window, "age", "baby", "toddler");
  pick(window, "where", "city");
  assert.match(window.location.search, /age=baby%2Ctoddler|age=baby,toddler/);
  assert.match(window.location.search, /where=city/);
});

test("reset clears everything", async () => {
  const window = await load();
  showAll(window);
  const everything = cards(window).length;

  pick(window, "age", "teen");
  pick(window, "cost", "free");
  ask(window, "disco");
  assert.ok(cards(window).length < everything);

  window.document.getElementById("reset").click();
  assert.equal(cards(window).length, everything);
  assert.equal(summary(window, "age"), "All ages");
  assert.equal(summary(window, "cost"), "Any");
  assert.equal(window.document.getElementById("ask").value, "");
  // Show everything widens the dates too, which is not the landing default.
  assert.equal(window.location.search, "?when=all");
});

/* --- repeating all day listings ------------------------------------------- */


/* The repeats filter needs an all-day recurring listing to act on, and the
   sample has none since the Kids Eat Free promo was filtered out upstream.
   Real ones do exist, a multi-day fair for instance, so rather than invent a
   row in the captured snapshot this injects one into the page's inlined data. */
function pageWith(extraEvents) {
  return HTML.replace(
    /(<script type="application\/json" id="inline-data">)([\s\S]*?)(<\/script>)/,
    (_all, open, json, close) => {
      // The inlined blob is { events: <the whole payload>, feeds: ... }.
      const blob = JSON.parse(json);
      const payload = blob.events;
      payload.events = payload.events.concat(extraEvents);
      payload.events.sort((a, b) => (a.start || "").localeCompare(b.start || ""));
      payload.count = payload.events.length;
      return open + JSON.stringify(blob) + close;
    }
  );
}

function allDayRepeat(overrides) {
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/Detroit" });
  return Object.assign({
    id: "fixture-allday-repeat",
    title: "County Fair Week",
    start: `${today}T00:00:00-04:00`,
    end: null,
    all_day: true,
    recurring: true,
    repeat_count: 7,
    description: "Runs all week.",
    url: "",
    venue: "Washtenaw Farm Council Grounds",
    address: "",
    city: "Ann Arbor",
    lat: null, lon: null,
    zone: "city", washtenaw: true, bus: true, drive_minutes: 5,
    ages: ["preschool", "elementary"], all_ages: true, age_min: 0, age_max: 18,
    audience_raw: "All ages", setting: "outdoor", cost: "free", price: "Free",
    registration: false, categories: [], also_seen_on: [],
    source: "fixture", source_name: "Fixture", image: "", updated: ""
  }, overrides || {});
}

test("all day repeats are in the list by default", async () => {
  const window = await loadPage(pageWith([allDayRepeat()]));
  showAll(window);
  assert.ok(titles(window).includes("County Fair Week"),
    "an all-day repeat should show unless you ask to hide it");
});

test("repeats is one choice of two, never both, and never only-repeats", async () => {
  const window = await load();
  const boxes = [...window.document.querySelectorAll("#panel-repeats input")];

  assert.equal(boxes.length, 2, "there should be exactly two options");
  assert.deepEqual(boxes.map((b) => b.value), ["show", "hide"]);
  assert.ok(boxes.every((b) => b.type === "radio"), "they have to be radios, not checkboxes");
  assert.deepEqual(boxes.map((b) => b.parentElement.textContent.trim()),
    ["Show all-day repeats", "Hide all-day repeats"]);
  assert.equal(boxes[0].checked, true, "showing them is the default");
  assert.equal(summary(window, "repeats"), "Show all-day repeats");

  // No "clear" link, because one of the two is always on.
  assert.equal(window.document.querySelectorAll("#panel-repeats .multi-clear").length, 0);
});

test("hiding all day repeats drops them and keeps everything else", async () => {
  const window = await loadPage(pageWith([allDayRepeat()]));
  showAll(window);
  const everything = cards(window).length;

  pick(window, "repeats", "hide");
  const shown = titles(window);
  assert.ok(!shown.includes("County Fair Week"), "the daily repeat should be hidden");
  assert.equal(shown.length, everything - 1, "and nothing else should go with it");
  assert.equal(summary(window, "repeats"), "No all-day repeats");

  pick(window, "repeats", "show");
  assert.equal(cards(window).length, everything, "picking show puts them back");
});

test("a timed event is never hidden as a repeat", async () => {
  const window = await load();
  pick(window, "repeats", "hide");
  const shown = titles(window);
  assert.ok(shown.includes("Saline Fair"),
    "only all day repeats should be hidden, not everything that recurs");
});

/* --- tomorrow ------------------------------------------------------------- */

test("the tomorrow chip is there and works", async () => {
  const window = await load();
  const radio = window.document.querySelector('input[name="when"][value="tomorrow"]');
  assert.ok(radio, "no tomorrow chip");
  radio.checked = true;
  radio.dispatchEvent(new window.Event("change", { bubbles: true }));

  const headings = [...window.document.querySelectorAll(".day-heading")];
  assert.equal(headings.length, 1, "tomorrow should be a single day");
  assert.match(headings[0].textContent, /Tomorrow/);
});

/* --- month view ----------------------------------------------------------- */

test("the month view draws a grid", async () => {
  const window = await load();
  window.document.querySelector('[data-view="month"]').click();
  assert.equal(window.document.getElementById("month-view").hidden, false);
  assert.equal(window.document.getElementById("list-view").hidden, true);
  assert.ok(window.document.querySelectorAll(".month-cell").length >= 28);
  assert.equal(window.document.querySelectorAll(".month-dow").length % 7, 0);
});

/* --- expanding a card ------------------------------------------------------ */

function firstCard(window) { return cards(window)[0]; }

test("a card starts collapsed and says so", async () => {
  const window = await load();
  const card = firstCard(window);
  const button = card.querySelector(".card-open");

  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(card.querySelector(".card-more").hidden, true);
  assert.equal(card.classList.contains("is-open"), false);
});

test("clicking the title expands it, clicking again shrinks it back", async () => {
  const window = await load();
  const card = firstCard(window);
  const button = card.querySelector(".card-open");

  button.click();
  assert.equal(button.getAttribute("aria-expanded"), "true");
  assert.equal(card.querySelector(".card-more").hidden, false);
  assert.ok(card.classList.contains("is-open"));

  button.click();
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(card.querySelector(".card-more").hidden, true);
  assert.equal(card.classList.contains("is-open"), false);
});

test("the expanded panel carries the details worth having", async () => {
  const window = await load();
  showAll(window);
  const card = cards(window).find(
    (c) => c.querySelector(".card-name").textContent === "Baby Playgroups");
  assert.ok(card, "Baby Playgroups is not in the snapshot any more");
  card.querySelector(".card-open").click();

  const labels = [...card.querySelectorAll(".detail-list dt")].map((d) => d.textContent);
  const values = [...card.querySelectorAll(".detail-list dd")].map((d) => d.textContent);

  for (const label of ["When", "Where", "Ages", "Cost", "Signup", "Listed by"]) {
    assert.ok(labels.includes(label), `missing "${label}" from ${labels.join(", ")}`);
  }
  assert.match(values[labels.indexOf("When")], /\w+day.*\d/);
  assert.match(values[labels.indexOf("Where")], /\d+ [A-Z].*Ann Arbor/,
    "Where should carry a street address, not just a venue name");
  assert.equal(values[labels.indexOf("Cost")], "Free");
});

test("expanding twice does not duplicate the detail rows", async () => {
  const window = await load();
  const card = firstCard(window);
  const button = card.querySelector(".card-open");
  button.click();
  const first = card.querySelectorAll(".detail-list dt").length;
  button.click();
  button.click();
  assert.equal(card.querySelectorAll(".detail-list dt").length, first);
});

test("a month chip jumps to the card and opens it", async () => {
  const window = await load();
  window.document.querySelector('[data-view="month"]').click();
  window.document.querySelector(".month-item").click();

  assert.equal(window.document.getElementById("list-view").hidden, false);
  const open = window.document.querySelector(".card.is-open");
  assert.ok(open, "the chip should open the matching card");
});

/* --- copy link ------------------------------------------------------------- */

test("every card has a copy link button", async () => {
  const window = await load();
  for (const card of cards(window)) {
    const button = card.querySelector(".card-copy");
    assert.ok(button, "no copy button");
    assert.equal(button.querySelector(".card-copy-label").textContent, "Copy link");
    assert.ok(button.querySelector("svg.icon"), "no copy icon");
    assert.match(button.getAttribute("aria-label"), /^Copy a link to /);
  }
});

test("copy link puts a shareable permalink on the clipboard", async () => {
  const window = await load();
  let copied = null;
  window.navigator.clipboard = { writeText: (t) => { copied = t; return Promise.resolve(); } };

  const card = firstCard(window);
  card.querySelector(".card-copy").click();
  await new Promise((r) => window.setTimeout(r, 10));

  assert.match(copied,
    /^https:\/\/shinabarger\.github\.io\/kid-events-in-ann-arbor\/\?event=[0-9a-f]{16}$/);
  assert.equal(card.querySelector(".card-copy").textContent, "Link copied");
});

test("opening a shared link expands that event and widens the dates", async () => {
  const window = await load();
  const target = window.document.querySelector("#list-view .card");
  const id = target.id.replace("e-", "");

  const dom = new JSDOM(HTML, {
    runScripts: "dangerously",
    url: `https://shinabarger.github.io/kid-events-in-ann-arbor/?event=${id}`,
    pretendToBeVisual: true,
  });
  const w = dom.window;
  if (!w.matchMedia) w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  w.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  w.HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  w.Element.prototype.scrollIntoView = function () {};
  await new Promise((r) => w.addEventListener("load", r));
  await new Promise((r) => w.setTimeout(r, 80));

  const card = w.document.getElementById("e-" + id);
  assert.ok(card, "the shared event should be on the page");
  assert.ok(card.classList.contains("is-open"), "it should arrive expanded");
  assert.ok(card.classList.contains("is-shared"));
  assert.equal(w.document.querySelector('input[name="when"]:checked').value, "all",
    "a shared link must not be hidden by the default date range");
});

/* --- calendar buttons ------------------------------------------------------ */

test("one Add to calendar button, three calendars behind it", async () => {
  const window = await load();
  for (const card of cards(window)) {
    const button = card.querySelector(".card-cal");
    assert.ok(button, "no calendar button");
    assert.equal(button.querySelector("span").textContent, "Add to calendar");
    assert.ok(button.querySelector("svg.icon"), "no calendar icon");
    assert.equal(button.getAttribute("aria-expanded"), "false");
    assert.equal(button.getAttribute("aria-haspopup"), "true");

    const panel = card.querySelector(".cal-panel");
    assert.equal(panel.hidden, true, "the menu must start closed");
    assert.equal(panel.getAttribute("role"), "menu");
    assert.deepEqual(
      [...panel.querySelectorAll(".cal-item span")].map((s) => s.textContent),
      ["Google Calendar", "Apple Calendar", "Outlook Calendar"]
    );
  }
});

test("the Google item carries the whole event", async () => {
  const window = await load();
  const item = window.document.querySelectorAll(".cal-item")[0];
  const params = new URL(item.getAttribute("href")).searchParams;
  assert.equal(params.get("action"), "TEMPLATE");
  assert.ok(params.get("text"));
  assert.match(params.get("dates"), /^\d{8}T\d{6}Z\/\d{8}T\d{6}Z$/);
  assert.equal(params.get("ctz"), "America/Detroit");
  assert.ok(params.get("location"), "no address, so the calendar cannot map it");
});

test("the Apple item downloads a real calendar file", async () => {
  const window = await load();
  const item = window.document.querySelectorAll(".cal-item")[1];

  let downloaded = null;
  window.URL.createObjectURL = (blob) => { downloaded = blob; return "blob:fake"; };
  window.URL.revokeObjectURL = () => {};
  item.click();
  assert.ok(downloaded, "clicking Apple Calendar did not produce a file");
  assert.equal(downloaded.type, "text/calendar;charset=utf-8");
});

test("the Outlook item opens the compose deeplink", async () => {
  const window = await load();
  const item = window.document.querySelectorAll(".cal-item")[2];
  const url = new URL(item.getAttribute("href"));
  assert.equal(url.host, "outlook.live.com");
  assert.equal(url.searchParams.get("rru"), "addevent");
  assert.ok(url.searchParams.get("subject"));
  assert.ok(url.searchParams.get("startdt"));
});

test("the calendar menu opens, closes, and hands focus back", async () => {
  const window = await load();
  const card = cards(window)[0];
  const button = card.querySelector(".card-cal");
  const panel = card.querySelector(".cal-panel");

  button.click();
  assert.equal(panel.hidden, false);
  assert.equal(button.getAttribute("aria-expanded"), "true");
  assert.equal(window.document.activeElement, panel.querySelector(".cal-item"),
    "opening should land focus on the first item");

  panel.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.equal(panel.hidden, true);
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(window.document.activeElement, button, "Escape should return focus");
});

test("arrow keys walk the calendar menu and wrap", async () => {
  const window = await load();
  const card = cards(window)[0];
  const panel = card.querySelector(".cal-panel");
  const items = [...panel.querySelectorAll(".cal-item")];

  card.querySelector(".card-cal").click();
  const down = () => panel.dispatchEvent(
    new window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));

  down();
  assert.equal(window.document.activeElement, items[1]);
  down();
  assert.equal(window.document.activeElement, items[2]);
  down();
  assert.equal(window.document.activeElement, items[0], "should wrap around");
});

test("opening one card's calendar menu closes another's", async () => {
  const window = await load();
  const [first, second] = cards(window);
  first.querySelector(".card-cal").click();
  second.querySelector(".card-cal").click();
  assert.equal(first.querySelector(".cal-panel").hidden, true);
  assert.equal(second.querySelector(".cal-panel").hidden, false);
});

test("the source button says View on event website", async () => {
  const window = await load();
  for (const card of cards(window)) {
    const link = card.querySelector(".card-source");
    if (link) {
      assert.equal(link.querySelector("span").textContent, "View on event website");
      assert.ok(link.querySelector("svg.icon"), "no website icon");
    }
  }
});

function openSync(window) {
  window.document.getElementById("subscribe-open").click();
  return window.document.getElementById("subscribe");
}

function tickFeed(window, file) {
  const box = window.document.querySelector(`.feed-options input[value="${file}"]`);
  assert.ok(box, `no feed checkbox for ${file}`);
  box.checked = true;
  box.dispatchEvent(new window.Event("change", { bubbles: true }));
}

test("the header button says sync, not subscribe", async () => {
  const window = await load();
  const button = window.document.getElementById("subscribe-open");
  assert.match(button.textContent.trim(), /^Sync to my calendar$/);
  assert.equal(window.document.getElementById("subscribe-title").textContent,
    "Sync to my calendar");
});

test("every feed is offered as a checkbox, ages grouped separately", async () => {
  const window = await load();
  openSync(window);

  const all = [...window.document.querySelectorAll(".feed-options input")];
  assert.equal(all.length, 15, "expected all 15 feeds");
  assert.ok(all.every((b) => b.type === "checkbox"), "they have to be checkboxes");

  const ageValues = [...window.document.querySelectorAll("#feed-ages input")]
    .map((b) => b.value);
  assert.deepEqual(ageValues, ["age-baby.ics", "age-toddler.ics", "age-preschool.ics",
    "age-elementary.ics", "age-tween.ics", "age-teen.ics"]);
});

test("nothing ticked tells you what to do", async () => {
  const window = await load();
  openSync(window);
  assert.match(window.document.getElementById("feed-picked").textContent, /Tick one or more/);
});

test("a 14 month old can take Babies and Toddlers together", async () => {
  const window = await load();
  openSync(window);

  tickFeed(window, "age-baby.ics");
  tickFeed(window, "age-toddler.ics");

  const picked = window.document.getElementById("feed-picked");
  assert.match(picked.textContent, /2 calendars to add/);

  const rows = [...picked.querySelectorAll(".feed-row")];
  assert.equal(rows.length, 2);

  const names = rows.map((r) => r.querySelector(".feed-name").textContent);
  assert.ok(names.some((n) => /Babies/.test(n)), names.join(" / "));
  assert.ok(names.some((n) => /Toddlers/.test(n)));

  // Each row carries its own Google, Apple and Copy.
  for (const row of rows) {
    const google = row.querySelector("a.btn-primary").getAttribute("href");
    const apple = row.querySelector("a.btn-secondary").getAttribute("href");
    assert.match(google, /calendar\.google\.com\/calendar\/r\/settings\/addbyurl\?cid=/);
    assert.match(apple, /^webcal:\/\/shinabarger\.github\.io\/kid-events-in-ann-arbor\/feeds\/age-/);
    assert.ok(row.querySelector("button").textContent === "Copy");
  }

  const googles = rows.map((r) => decodeURIComponent(r.querySelector("a.btn-primary").href));
  assert.ok(googles.some((g) => g.includes("/feeds/age-baby.ics")));
  assert.ok(googles.some((g) => g.includes("/feeds/age-toddler.ics")));
});

test("unticking removes that calendar again", async () => {
  const window = await load();
  openSync(window);
  tickFeed(window, "age-baby.ics");
  tickFeed(window, "age-toddler.ics");
  assert.equal(window.document.querySelectorAll("#feed-picked .feed-row").length, 2);

  const box = window.document.querySelector('.feed-options input[value="age-toddler.ics"]');
  box.checked = false;
  box.dispatchEvent(new window.Event("change", { bubbles: true }));

  assert.equal(window.document.querySelectorAll("#feed-picked .feed-row").length, 1);
  assert.match(window.document.getElementById("feed-picked").textContent, /One calendar to add/);
});

/* --- chrome ---------------------------------------------------------------- */

test("the footer reports the build and its sources", async () => {
  const window = await load();
  assert.match(window.document.getElementById("build-info").textContent, /Last updated/);
  assert.ok(window.document.querySelectorAll(".source-pill").length > 0);
});

test("the theme toggle flips and remembers", async () => {
  const window = await load();
  const button = window.document.getElementById("theme-toggle");
  const first = window.document.documentElement.getAttribute("data-theme");
  button.click();
  const second = window.document.documentElement.getAttribute("data-theme");

  assert.notEqual(first, second);
  assert.equal(button.getAttribute("aria-pressed"), second === "dark" ? "true" : "false");
  assert.equal(window.localStorage.getItem("a2kids-theme"), second);
});

/* --- accessibility, checked on the rendered page --------------------------- */

test("every rendered control has an accessible name", async () => {
  const window = await load();
  const doc = window.document;

  for (const button of doc.querySelectorAll("button")) {
    const named = button.textContent.trim() ||
      button.getAttribute("aria-label") ||
      button.getAttribute("aria-labelledby");
    assert.ok(named, `button with no name: ${button.outerHTML.slice(0, 90)}`);
  }
  for (const link of doc.querySelectorAll("a[href]")) {
    const named = link.textContent.trim() || link.getAttribute("aria-label");
    assert.ok(named, `link with no name: ${link.outerHTML.slice(0, 90)}`);
  }
  for (const box of doc.querySelectorAll('#filters input[type="checkbox"]')) {
    assert.ok(box.closest("label"), "a filter checkbox is not wrapped in a label");
    assert.ok(box.closest("label").textContent.trim(), "a filter checkbox label is empty");
  }
});

test("the filter buttons name themselves with their label and current value", async () => {
  const window = await load();
  for (const name of ["age", "where", "setting", "cost", "signup"]) {
    const button = window.document.getElementById(`btn-${name}`);
    const ids = button.getAttribute("aria-labelledby").split(/\s+/);
    const spoken = ids.map((id) => window.document.getElementById(id).textContent).join(" ");
    assert.ok(spoken.trim().length > 3, `btn-${name} announces nothing useful`);
  }
});

test("the live region announces the result count", async () => {
  const window = await load();
  const count = window.document.getElementById("count");
  assert.equal(count.getAttribute("aria-live"), "polite");
  assert.equal(count.getAttribute("role"), "status");

  const before = count.textContent;
  pick(window, "age", "teen");
  assert.notEqual(count.textContent, before, "the count did not update for screen readers");
});

test("headings on the rendered page stay in order", async () => {
  const window = await load();
  const levels = [...window.document.querySelectorAll("h1,h2,h3")]
    .map((h) => Number(h.tagName[1]));
  assert.equal(levels[0], 1);
  for (let i = 1; i < levels.length; i++) {
    assert.ok(levels[i] <= levels[i - 1] + 1, `jumped from h${levels[i - 1]} to h${levels[i]}`);
  }
});

/* --- typing, undo, and the things Safari does differently ----------------- */

test("typing a question is one undo step, not one per pause", async () => {
  const window = await load();
  const ask = window.document.getElementById("ask");
  const before = titles(window).length;

  // The debounce fires on every pause, which is what a slow typist produces.
  for (const text of ["tod", "toddler", "toddler story", "toddler storytime"]) {
    ask.value = text;
    ask.dispatchEvent(new window.Event("input", { bubbles: true }));
    await new Promise((r) => window.setTimeout(r, 400));
  }
  assert.notEqual(titles(window).length, before, "the search should have narrowed things");

  window.document.getElementById("undo").click();
  await new Promise((r) => window.setTimeout(r, 30));

  assert.equal(
    titles(window).length, before,
    "one press of Undo should get back to before I started typing, not back one keystroke"
  );
});

test("a search that matches nothing keeps what I typed", async () => {
  const window = await load();
  const ask = window.document.getElementById("ask");

  ask.value = "qzzx nonsense that matches nothing";
  ask.form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => window.setTimeout(r, 30));

  assert.equal(
    ask.value, "qzzx nonsense that matches nothing",
    "wiping the box on a bad result makes people retype the whole thing"
  );
});

test("an unparseable search says so instead of silently filtering", async () => {
  const window = await load();
  const ask = window.document.getElementById("ask");

  ask.value = "zzzzq";
  ask.form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => window.setTimeout(r, 30));

  const active = window.document.getElementById("active-bar");
  assert.ok(active.textContent.trim().length > 0, "silence is the worst answer here");
  assert.equal(active.getAttribute("aria-live"), "polite",
    "a screen reader should hear the correction without being interrupted");
});

test("no form control is small enough to make iOS zoom on focus", async () => {
  // Safari on iPhone zooms the whole page when you tap anything under 16px,
  // and then leaves you scrolled sideways. It is the single most common
  // mobile bug on a form and it never shows up on a desktop browser.
  const css = readFileSync(join(ROOT, "assets", "style.css"), "utf8");
  const block = css.slice(css.indexOf('.field input[type="search"]'));
  const size = block.match(/font-size:\s*([\d.]+)rem/);
  assert.ok(size, "could not find the form control font size");
  assert.ok(
    parseFloat(size[1]) >= 1,
    `form controls are ${size[1]}rem, which is under the 16px iOS zoom threshold`
  );
});

test("search inputs turn off the native WebKit styling", async () => {
  const css = readFileSync(join(ROOT, "assets", "style.css"), "utf8");
  assert.ok(
    css.includes("-webkit-appearance: none"),
    "Safari draws its own pill and inset shadow on search inputs otherwise"
  );
  assert.ok(
    css.includes("::-webkit-search-cancel-button"),
    "the native clear button is unstyleable and looks wrong against the design"
  );
});

test("the dialog cannot grow taller than the visible viewport on iOS", async () => {
  const css = readFileSync(join(ROOT, "assets", "style.css"), "utf8");
  const block = css.slice(css.indexOf("dialog {"), css.indexOf("dialog::backdrop"));
  assert.ok(
    block.includes("dvh"),
    "vh on iOS counts the address bar you cannot see, so the buttons end up unreachable"
  );
});

test("no script uses a date format Safari refuses to parse", async () => {
  // new Date("2026-09-05 10:30") is null in Safari and fine in Chrome, which
  // is how a site ships working and is broken for every iPhone user.
  for (const file of ["app.js", "nlq.js"]) {
    const js = readFileSync(join(ROOT, "assets", file), "utf8");
    const bad = js.match(/new Date\(\s*["'][^"']*\d\s\d/);
    assert.equal(bad, null, `${file} builds a Date from a space separated string`);
  }
});

test("no script uses regex lookbehind, which older Safari throws on", async () => {
  for (const file of ["app.js", "nlq.js"]) {
    const js = readFileSync(join(ROOT, "assets", file), "utf8");
    assert.ok(!js.includes("(?<"), `${file} uses lookbehind, a syntax error on iOS 16.3 and older`);
  }
});

test("copying a link still works where the clipboard API is blocked", async () => {
  // Safari only allows clipboard writes inside a real user gesture, and refuses
  // outright over plain http. The fallback is what makes Copy link reliable.
  const window = await load();
  delete window.navigator.clipboard;

  const card = cards(window)[0];
  const copy = card.querySelector(".card-copy");
  assert.ok(copy, "no copy button on the card");
  copy.click();
  await new Promise((r) => window.setTimeout(r, 30));

  assert.notEqual(copy.textContent, "Copy link", "the button should report what happened");
});

/* --- the Location filter -------------------------------------------------- */

test("the filter is called Location, not Where", async () => {
  const window = await load();
  assert.equal(
    window.document.getElementById("lbl-where").textContent.trim(),
    "Location"
  );
});

test("Location offers city limits, a 30 minute drive, the county, and the bus", async () => {
  const window = await load();
  const panel = openFilter(window, "where");
  const labels = [...panel.querySelectorAll(".opt > span")].map(
    (s) => s.firstChild.textContent.trim()
  );
  assert.deepEqual(labels, [
    "Ann Arbor city limits",
    "Within a 30 minute drive",
    "Washtenaw County",
    "Within an hour bus ride",
  ]);
});

test("the bus option says out loud that it is an estimate", async () => {
  const window = await load();
  const panel = openFilter(window, "where");
  const note = panel.querySelector(".opt-note");
  assert.ok(note, "the bus option needs its caveat where you can read it");
  assert.match(note.textContent, /theride\.org/i);
});

test("filtering to the bus drops the places no bus goes", async () => {
  const window = await load();
  showAll(window);
  const before = titles(window).length;

  pick(window, "where", "bus");
  await new Promise((r) => window.setTimeout(r, 20));
  const after = titles(window).length;

  assert.ok(after > 0, "the bus filter should not empty the page");
  assert.ok(after < before, "and it should actually exclude somewhere");
});

test("Parks and Rec ships as its own source with its own feed", async () => {
  const window = await load();
  const feeds = [...window.document.querySelectorAll("#feed-other .opt input")]
    .map((b) => b.value);
  assert.ok(feeds.includes("bus-reachable.ics"), "no feed for the bus filter");
  assert.ok(feeds.includes("within-30-minutes.ics"));
  assert.ok(!feeds.includes("within-29-minutes.ics"), "the old name is gone");
});

test("The Mamas Network playgroups show up under babies and toddlers", async () => {
  const window = await load();
  showAll(window);
  pick(window, "age", "baby");
  await new Promise((r) => window.setTimeout(r, 20));

  const found = titles(window).filter((t) => /Dadas & Littles|Mamas & Littles/.test(t));
  assert.ok(found.length > 0, "the Saturday playgroups should be here for a baby");
});

test("a scraped playgroup carries its own signup link", async () => {
  const window = await load();
  showAll(window);
  const card = cards(window).find((c) =>
    /DADaS & LITTLES/i.test(c.querySelector(".card-name").textContent)
  );
  assert.ok(card, "no DADaS & LITTLES card");
  const link = card.querySelector(".card-source");
  assert.ok(link && !link.hidden, "the card should link somewhere");
  assert.match(link.href, /zeffy\.com|themamasnetwork\.org/);
});

test("a projected occurrence still links back to the schedule page", async () => {
  const window = await load();
  showAll(window);
  const card = cards(window).find((c) =>
    /Mamas & Littles/.test(c.querySelector(".card-name").textContent) &&
    /repeating/i.test(c.textContent)
  );
  assert.ok(card, "no projected occurrence rendered");
  const link = card.querySelector(".card-source");
  assert.match(link.href, /themamasnetwork\.org\/events/);
});

/* --- the bug that shipped ------------------------------------------------ */

test("every filter dropdown starts closed, with the real stylesheet applied", async () => {
  // jsdom has no cascade, so `panel.hidden` was true while the live site
  // rendered every dropdown open: `.multi-panel { display: flex }` in the
  // author stylesheet beats the browser's own `[hidden] { display: none }`.
  // This checks the stylesheet the way a browser would instead.
  const css = readFileSync(join(ROOT, "assets", "style.css"), "utf8");

  const hiddenRule = css.match(/\[hidden\]\s*\{([^}]*)\}/);
  assert.ok(hiddenRule, "no author level [hidden] rule");
  assert.match(hiddenRule[1], /display\s*:\s*none\s*!important/);

  const window = await load();
  for (const name of ["age", "where", "setting", "cost", "signup", "repeats"]) {
    const panel = window.document.getElementById(`panel-${name}`);
    assert.equal(panel.hidden, true, `${name} panel is open on load`);
  }
  for (const panel of window.document.querySelectorAll(".cal-panel")) {
    assert.equal(panel.hidden, true, "a calendar menu is open on load");
  }
});

test("nothing sets display on an element that is toggled with hidden", async () => {
  // The real guard: if a rule targets one of these and sets display without
  // the [hidden] override winning, it silently unhides on the live site.
  const css = readFileSync(join(ROOT, "assets", "style.css"), "utf8");
  const hiddenIndex = css.search(/\[hidden\]\s*\{/);
  assert.ok(hiddenIndex > -1);

  for (const selector of [".multi-panel", ".cal-panel", ".card-more"]) {
    const at = css.indexOf(`${selector} {`);
    if (at === -1) continue;
    const block = css.slice(at, css.indexOf("}", at));
    if (/display\s*:/.test(block)) {
      assert.ok(
        /!important/.test(css.slice(hiddenIndex, css.indexOf("}", hiddenIndex))),
        `${selector} sets display, so [hidden] needs !important to beat it`
      );
    }
  }
});

test("the page opens in light mode", async () => {
  const window = await load();
  assert.equal(window.document.documentElement.getAttribute("data-theme"), "light");
});

test("a saved dark choice is still honoured", async () => {
  const window = await load();
  const toggle = window.document.getElementById("theme-toggle");
  toggle.click();
  assert.equal(window.document.documentElement.getAttribute("data-theme"), "dark");
  assert.equal(toggle.getAttribute("aria-pressed"), "true");
  assert.match(toggle.getAttribute("aria-label"), /light theme/i);
});

/* --- day, week and month views ------------------------------------------- */

function setView(window, view) {
  window.document.querySelector(`[data-view="${view}"]`).click();
}

function heading(window) {
  return window.document.getElementById("cal-heading").textContent;
}

test("all four views are offered", async () => {
  const window = await load();
  const views = [...window.document.querySelectorAll("[data-view]")]
    .map((b) => b.dataset.view);
  assert.deepEqual(views, ["list", "day", "week", "month"]);
});

test("the day view opens on today and shows that day only", async () => {
  const window = await load();
  setView(window, "day");
  assert.match(heading(window), /^Today, /);

  const days = new Set(
    [...window.document.querySelectorAll(".cal-row")].map((r) =>
      r.closest(".day-view") ? "one" : "other")
  );
  assert.deepEqual([...days], ["one"], "the day view should render one day");
  assert.match(window.document.getElementById("count").textContent, /on this day$/);
});

test("the week view lays out seven days, Sunday first", async () => {
  const window = await load();
  setView(window, "week");
  const columns = [...window.document.querySelectorAll(".week-day")];
  assert.equal(columns.length, 7);
  assert.equal(columns[0].querySelector(".week-dow").textContent, "Sun");
  assert.equal(columns[6].querySelector(".week-dow").textContent, "Sat");
  assert.equal(
    window.document.querySelectorAll(".week-day.is-today").length, 1,
    "exactly one column should be marked today"
  );
});

test("the month view draws one month, the one you navigated to", async () => {
  const window = await load();
  setView(window, "month");
  assert.equal(window.document.querySelectorAll(".month-grid").length, 1);
  assert.match(heading(window), /^[A-Z][a-z]+ \d{4}$/);
});

test("the arrows move a day, a week and a month at a time", async () => {
  const window = await load();
  const next = window.document.getElementById("cal-next");

  setView(window, "day");
  const day1 = heading(window);
  next.click();
  assert.notEqual(heading(window), day1);

  setView(window, "week");
  const week1 = heading(window);
  next.click();
  assert.notEqual(heading(window), week1);

  setView(window, "month");
  const month1 = heading(window);
  next.click();
  assert.notEqual(heading(window), month1);
  window.document.getElementById("cal-prev").click();
  assert.equal(heading(window), month1, "back should land where it started");
});

test("Today is disabled while today is on screen, and works when it is not", async () => {
  const window = await load();
  setView(window, "day");
  const today = window.document.getElementById("cal-today");
  assert.equal(today.disabled, true, "already on today");

  window.document.getElementById("cal-next").click();
  assert.equal(today.disabled, false);
  today.click();
  assert.match(heading(window), /^Today, /);
  assert.equal(today.disabled, true);
});

test("arrow keys move the calendar but never while you are typing", async () => {
  const window = await load();
  setView(window, "week");
  const before = heading(window);

  window.document.dispatchEvent(
    new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  assert.notEqual(heading(window), before);

  // Typing a search must not skip the calendar sideways.
  const back = heading(window);
  const ask = window.document.getElementById("ask");
  ask.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  assert.equal(heading(window), back);
});

test("the When chips step aside in the calendar views", async () => {
  // Two controls for one job is how somebody ends up staring at an empty week
  // wondering which one is lying to them.
  const window = await load();
  const whenRow = window.document.getElementById("when-row");
  const active = window.document.getElementById("active-bar");

  assert.equal(whenRow.hidden, false);
  assert.match(active.textContent, /Today & tomorrow/);

  setView(window, "week");
  assert.equal(whenRow.hidden, true);
  assert.doesNotMatch(active.textContent, /Today & tomorrow/);

  setView(window, "list");
  assert.equal(whenRow.hidden, false, "and come back when you return to the list");
  assert.match(active.textContent, /Today & tomorrow/);
});

test("the other filters still apply in a calendar view", async () => {
  const window = await load();
  setView(window, "week");
  const before = window.document.querySelectorAll(".cal-row").length;

  pick(window, "cost", "free");
  await new Promise((r) => window.setTimeout(r, 20));
  const after = window.document.querySelectorAll(".cal-row").length;
  assert.ok(after > 0 && after < before, "a cost filter should still narrow the week");
});

test("clicking an event in a calendar view opens its card in the list", async () => {
  const window = await load();
  setView(window, "week");
  const row = window.document.querySelector(".cal-row");
  const title = row.querySelector(".cal-row-title").textContent;

  row.click();
  await new Promise((r) => window.setTimeout(r, 30));

  assert.equal(window.document.getElementById("list-view").hidden, false);
  const open = window.document.querySelector(".card.is-open");
  assert.ok(open, "nothing opened");
  assert.equal(open.querySelector(".card-name").textContent.trim(), title);
});

test("a calendar row is announced with its time and place", async () => {
  const window = await load();
  setView(window, "day");
  for (const row of window.document.querySelectorAll(".cal-row")) {
    assert.match(row.getAttribute("aria-label"), /Open the full listing\.$/);
  }
});

test("the day rail does not repeat the hour it is already showing", async () => {
  const window = await load();
  setView(window, "day");
  for (const slot of window.document.querySelectorAll(".day-slot")) {
    const hour = slot.querySelector(".day-hour").textContent;
    for (const time of slot.querySelectorAll(".cal-row-time")) {
      assert.notEqual(time.textContent, hour, "the rail already says this");
    }
  }
});

test("plus N more in the month grid opens that day", async () => {
  const window = await load();
  setView(window, "month");
  const more = window.document.querySelector(".month-more");
  assert.ok(more, "no busy day in the sample");
  assert.equal(more.tagName, "BUTTON", "a dead end otherwise");
  assert.match(more.getAttribute("aria-label"), /^See all \d+ events on /);

  more.click();
  await new Promise((r) => window.setTimeout(r, 30));
  assert.ok(window.document.querySelector(".day-view"), "should land in the day view");
});

/* --- the staleness notice ------------------------------------------------ */

function pageWithMeta(overrides) {
  return HTML.replace(
    /(<script type="application\/json" id="inline-data">)([\s\S]*?)(<\/script>)/,
    (_all, open, json, close) => {
      const blob = JSON.parse(json);
      Object.assign(blob.events, overrides);
      return open + JSON.stringify(blob) + close;
    }
  );
}

test("sample data says so, loudly", async () => {
  // Without this, a stale snapshot looks exactly like a working calendar,
  // which is how a Saturday event ended up on somebody's Sunday.
  const window = await loadPage(pageWithMeta({
    sample: true, snapshot_date: "2026-09-04",
  }));
  const box = window.document.getElementById("staleness");
  assert.equal(box.hidden, false, "the sample should announce itself");
  assert.match(box.textContent, /sample listings captured on September 4, 2026/);
  assert.match(box.textContent, /Update events/);
});

test("real and fresh data shows no notice at all", async () => {
  const window = await loadPage(pageWithMeta({
    sample: false, generated: new Date().toISOString(),
  }));
  assert.equal(window.document.getElementById("staleness").hidden, true);
});

test("a daily job that stopped running is called out", async () => {
  const threeDaysAgo = new Date(Date.now() - 3 * 24 * 36e5).toISOString();
  const window = await loadPage(pageWithMeta({
    sample: false, generated: threeDaysAgo,
  }));
  const box = window.document.getElementById("staleness");
  assert.equal(box.hidden, false, "three days without an update is worth saying");
  assert.match(box.textContent, /last ran 3 days ago/);
});

test("a run a few hours late is not worth a warning", async () => {
  const window = await loadPage(pageWithMeta({
    sample: false, generated: new Date(Date.now() - 20 * 36e5).toISOString(),
  }));
  assert.equal(window.document.getElementById("staleness").hidden, true,
    "the job runs daily, so 20 hours is normal");
});

test("the notice is announced but does not steal focus", async () => {
  const window = await loadPage(pageWithMeta({ sample: true, snapshot_date: "2026-09-04" }));
  const box = window.document.getElementById("staleness");
  assert.equal(box.getAttribute("role"), "status");
  assert.equal(box.getAttribute("aria-live"), null, "role=status already implies polite");
});

/* --- the header ----------------------------------------------------------- */

test("the logo and the title are one link home", async () => {
  const window = await load();
  const brand = window.document.querySelector(".brand");
  assert.equal(brand.tagName, "A");
  assert.equal(brand.getAttribute("href"), "./");
  assert.ok(brand.querySelector(".brand-mark"), "the mark should be inside the link");
  assert.ok(brand.querySelector("h1"), "and so should the title");

  // One destination, one tab stop.
  const homeLinks = [...window.document.querySelectorAll(".masthead a")]
    .filter((a) => a.getAttribute("href") === "./");
  assert.equal(homeLinks.length, 2, "the brand plus the Calendar nav link");
});

test("the header nav marks the page you are on", async () => {
  const window = await load();
  const current = window.document.querySelector(".masthead [aria-current='page']");
  assert.ok(current, "nothing marked as current");
  assert.equal(current.getAttribute("href"), "./");
  assert.ok(window.document.querySelector('.masthead a[href="about.html"]'));
});

test("Calendar and About wear the same pill as every other button", async () => {
  const window = await load();
  for (const label of ["Calendar", "About"]) {
    const item = [...window.document.querySelectorAll(".masthead a")]
      .find((a) => a.textContent.trim() === label);
    assert.ok(item, `no ${label} in the header`);
    assert.ok(item.classList.contains("btn"), `${label} is not styled as a button`);
    assert.ok(item.classList.contains("btn-nav"));
    // Still an anchor, so middle click and open-in-new-tab keep working.
    assert.equal(item.tagName, "A");
    assert.ok(item.getAttribute("href"));
  }
});

test("the site title is not painted like a body link", async () => {
  // It shipped blue and underlined on a dark green bar for one upload, which
  // was genuinely unreadable.
  const css = readFileSync(join(ROOT, "assets", "style.css"), "utf8");
  const block = css.slice(css.indexOf(".brand,"), css.indexOf("/* Hover is a lift"));
  assert.match(block, /color:\s*#fff/);
  assert.match(block, /text-decoration:\s*none/);
});

test("the theme toggle swaps its icon as well as its word", async () => {
  const window = await load();
  const toggle = window.document.getElementById("theme-toggle");
  assert.ok(toggle.querySelector(".theme-sun"), "no sun icon");
  assert.ok(toggle.querySelector(".theme-moon"), "no moon icon");
  assert.equal(toggle.querySelector(".theme-label").textContent, "Dark");

  toggle.click();
  assert.equal(toggle.querySelector(".theme-label").textContent, "Light");
  assert.match(toggle.getAttribute("aria-label"), /light theme/i);
});

/* --- stale data in the browser ------------------------------------------- */

test("the data fetch cannot be served from cache", async () => {
  // The JSON changes every morning and the page does not, so a cached
  // events.json is a calendar quietly showing yesterday. This is what made a
  // successful scrape still display the "sample listings" notice.
  const js = readFileSync(join(ROOT, "assets", "app.js"), "utf8");
  const block = js.slice(js.indexOf("function loadJson"), js.indexOf("function stalenessNote"));

  assert.match(block, /cache:\s*"no-cache"/, "no revalidation, so the browser may reuse it");
  assert.match(block, /\?d=/, "no per-day cache buster for proxies that ignore the header");
  assert.match(block, /toLocaleDateString/, "the buster should change daily, like the file");

  assert.doesNotMatch(
    js, /fetch\("data\/(events|feeds)\.json"\)/,
    "a bare fetch of the data files bypasses all of that"
  );
});

test("a failed data load is an error, not a blank page", async () => {
  const js = readFileSync(join(ROOT, "assets", "app.js"), "utf8");
  const block = js.slice(js.indexOf("function loadJson"), js.indexOf("function stalenessNote"));
  assert.match(block, /if \(!r\.ok\) throw/, "a 404 would otherwise parse as JSON and fail oddly");
});

/* --- untrusted input ------------------------------------------------------ */

test("a javascript: url from a source never reaches an href", async () => {
  // Event data is scraped from other people's sites, so every url on it is
  // untrusted until it has been parsed. javascript: and data: both run on
  // click, and an href is the one place they get to.
  const window = await loadPage(pageWith([{
    id: "hostile-1",
    title: "Storytime",
    start: new Date(Date.now() + 3600e3).toISOString(),
    venue: "Downtown Library",
    city: "Ann Arbor",
    url: "javascript:alert(document.domain)",
    source: "aadl",
    source_name: "Ann Arbor District Library",
  }]));
  showAll(window);

  const card = window.document.getElementById("e-hostile-1");
  assert.ok(card, "the event should still be listed");
  const link = card.querySelector(".card-source");
  if (link) {
    assert.doesNotMatch(link.getAttribute("href") || "", /^javascript:/i);
  }
});

test("an ordinary https url still gets through", async () => {
  const window = await loadPage(pageWith([{
    id: "ok-1",
    title: "Storytime",
    start: new Date(Date.now() + 3600e3).toISOString(),
    venue: "Downtown Library",
    city: "Ann Arbor",
    url: "https://aadl.org/node/668324",
    source: "aadl",
    source_name: "Ann Arbor District Library",
  }]));
  showAll(window);

  const link = window.document.getElementById("e-ok-1").querySelector(".card-source");
  assert.ok(link, "a real url should render a link");
  assert.equal(link.getAttribute("href"), "https://aadl.org/node/668324");
});

test("a hostile query string does not take the page down", async () => {
  // ?when=" used to be interpolated straight into a querySelector, where it
  // threw a SyntaxError out of readUrl and left the page blank.
  const js = readFileSync(join(ROOT, "assets", "app.js"), "utf8");

  assert.doesNotMatch(
    js, /querySelector\([^)]*\+\s*state\.when/,
    "state.when is a url parameter and must not be built into a selector"
  );
  assert.match(
    js, /hasOwnProperty\.call\(state\.byId/,
    "?event=__proto__ would otherwise hand back Object.prototype, which is truthy"
  );
});
