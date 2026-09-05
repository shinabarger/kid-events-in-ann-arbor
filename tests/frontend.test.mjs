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

async function load() {
  const dom = new JSDOM(HTML, {
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

  const before = cards(window).length;
  pick(window, "age", "baby");
  assert.ok(cards(window).length < before);
  assert.ok(titles(window).includes("Baby Playgroups"));
  assert.ok(!titles(window).includes("Silent Disco Dance Party"));
  assert.equal(summary(window, "age"), "Babies");
});

test("picking two ages shows events for either one", async () => {
  const window = await load();
  pick(window, "age", "baby");
  const babyOnly = new Set(titles(window));
  pick(window, "age", "teen");
  const both = titles(window);

  assert.ok(both.length > babyOnly.size, "adding a second age should widen the list");
  assert.ok(both.includes("Baby Playgroups"));
  assert.ok(both.includes("Silent Disco Dance Party"));
  assert.equal(summary(window, "age"), "Babies +1");
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

test("all day repeats are in the list by default", async () => {
  const window = await load();
  assert.ok(titles(window).includes("Kids Eat Free"),
    "the sample data should carry a daily repeat");
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
  const window = await load();
  const everything = cards(window).length;

  pick(window, "repeats", "hide");
  const shown = titles(window);
  assert.ok(!shown.includes("Kids Eat Free"), "the daily repeat should be hidden");
  assert.ok(shown.length < everything);
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
  const card = cards(window).find(
    (c) => c.querySelector(".card-name").textContent === "Baby Playgroups");
  card.querySelector(".card-open").click();

  const labels = [...card.querySelectorAll(".detail-list dt")].map((d) => d.textContent);
  const values = [...card.querySelectorAll(".detail-list dd")].map((d) => d.textContent);

  for (const label of ["When", "Where", "Ages", "Cost", "Signup", "Listed by"]) {
    assert.ok(labels.includes(label), `missing "${label}" from ${labels.join(", ")}`);
  }
  assert.match(values[labels.indexOf("When")], /\w+day.*\d/);
  assert.match(values[labels.indexOf("Where")], /Fifth Ave/);
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
    assert.equal(button.textContent, "Copy link");
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

test("every card says Add to Google Calendar and links correctly", async () => {
  const window = await load();
  for (const card of cards(window)) {
    const link = card.querySelector(".card-google");
    assert.equal(link.textContent, "Add to Google Calendar");
    const params = new URL(link.getAttribute("href")).searchParams;
    assert.equal(params.get("action"), "TEMPLATE");
    assert.ok(params.get("text"));
    assert.match(params.get("dates"), /^\d{8}T\d{6}Z\/\d{8}T\d{6}Z$/);
    assert.equal(params.get("ctz"), "America/Detroit");
  }
});

test("every card says Add to Apple Calendar and produces a file", async () => {
  const window = await load();
  const button = window.document.querySelector(".card-apple");
  assert.equal(button.textContent, "Add to Apple Calendar");

  let downloaded = null;
  window.URL.createObjectURL = (blob) => { downloaded = blob; return "blob:fake"; };
  window.URL.revokeObjectURL = () => {};
  button.click();
  assert.ok(downloaded, "clicking Apple Calendar did not produce a file");
  assert.equal(downloaded.type, "text/calendar;charset=utf-8");
});

test("the source button says View on Website", async () => {
  const window = await load();
  for (const card of cards(window)) {
    const link = card.querySelector(".card-source");
    if (link) assert.equal(link.textContent, "View on Website");
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
