/* Kid Events in Ann Arbor
   Reads data/events.json, filters it, and draws either a list or a month
   grid. No framework, no build step. The daily GitHub Action rewrites the JSON
   and the .ics feeds, this file just renders whatever is there. */

(function () {
  "use strict";

  var SITE = "https://shinabarger.github.io/kid-events-in-ann-arbor";
  var TZ = "America/Detroit";

  /* Every filter except the search box and the date chips takes a set of
     values. Empty set means no filter, which is why the buttons read
     "All ages" and "Anywhere" when nothing is picked. */
  var FILTERS = {
    age: {
      empty: "All ages",
      options: [],           // filled from events.json age_bands
      test: function (event, values) {
        return (event.ages || []).some(function (band) { return values.has(band); });
      }
    },
    where: {
      label: "Location",
      empty: "Anywhere",
      options: [
        { value: "city", label: "Ann Arbor city limits", short: "City limits" },
        { value: "near", label: "Within a 30 minute drive", short: "30 min drive" },
        { value: "county", label: "Washtenaw County", short: "Washtenaw" },
        {
          value: "bus", label: "Within an hour bus ride", short: "Bus ride",
          note: "Rough guess from TheRide's service area. Check theride.org for the real trip."
        }
      ],
      test: function (event, values) {
        if (values.has("city") && event.zone === "city") return true;
        if (values.has("near") && (event.zone === "city" || event.zone === "near")) return true;
        if (values.has("county") && event.washtenaw) return true;
        if (values.has("bus") && event.bus) return true;
        return false;
      }
    },
    setting: {
      empty: "Either",
      options: [
        { value: "indoor", label: "Indoor" },
        { value: "outdoor", label: "Outdoor" }
      ],
      test: function (event, values) {
        if (event.setting === "both") return true;
        return values.has(event.setting);
      }
    },
    cost: {
      empty: "Any",
      options: [
        { value: "free", label: "Free" },
        { value: "paid", label: "Paid" }
      ],
      test: function (event, values) { return values.has(event.cost); }
    },
    signup: {
      empty: "Any",
      options: [
        { value: "dropin", label: "Drop in, no signup" },
        { value: "register", label: "Registration required" }
      ],
      test: function (event, values) {
        return values.has(event.registration ? "register" : "dropin");
      }
    },
    repeats: {
      // One or the other, never both, so this one renders as radios.
      single: true,
      fallback: "show",
      empty: "Show all-day repeats",
      options: [
        { value: "show", label: "Show all-day repeats" },
        { value: "hide", label: "Hide all-day repeats", short: "No all-day repeats" }
      ],
      test: function (event, values) {
        if (!values.has("hide")) return true;
        // A standing all-day listing like Kids Eat Free is the thing worth
        // hiding. A weekly storytime with a real start time is not.
        return !(event.recurring && event.all_day);
      }
    }
  };

  // What the page opens on. Most people are looking for today, then tomorrow.
  var DEFAULT_WHEN = "next2";

  var AGE_LABELS = {
    baby: "Babies", toddler: "Toddlers", preschool: "Preschool",
    elementary: "Elementary", tween: "Tweens", teen: "Teens"
  };

  var state = {
    events: [],
    byId: {},
    meta: null,
    view: "list",
    feeds: [],
    when: DEFAULT_WHEN,
    q: "",
    keywords: [],
    picked: {
      age: new Set(), where: new Set(), setting: new Set(),
      cost: new Set(), signup: new Set(), repeats: new Set()
    },
    timeOfDay: "",
    date: "",
    understood: [],
    qTyping: false,
    shared: "",
    history: [],
    lastFocus: null
  };

  var MAX_HISTORY = 25;

  function snapshot() {
    var picked = {};
    Object.keys(state.picked).forEach(function (name) {
      picked[name] = Array.from(state.picked[name]);
    });
    return {
      picked: picked, when: state.when, date: state.date,
      timeOfDay: state.timeOfDay, q: state.q,
      keywords: state.keywords.slice(), understood: state.understood.slice()
    };
  }

  function sameAs(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  /* Every change that a person could regret pushes the state they were in.
     That is what the Undo button and the empty state's escape hatch use. */
  function remember() {
    var now = snapshot();
    var last = state.history[state.history.length - 1];
    if (last && sameAs(last, now)) return;
    state.history.push(now);
    if (state.history.length > MAX_HISTORY) state.history.shift();
  }

  function undo() {
    endTypingRun();
    var previous = state.history.pop();
    if (!previous) return;

    Object.keys(state.picked).forEach(function (name) {
      state.picked[name] = new Set(previous.picked[name] || []);
    });
    state.when = previous.when;
    state.date = previous.date;
    state.timeOfDay = previous.timeOfDay;
    state.q = previous.q;
    state.keywords = previous.keywords.slice();
    state.understood = previous.understood.slice();
    if (el.ask) el.ask.value = state.q;

    syncCheckboxes();
    apply({ keepHistory: true });
  }

  var el = {};

  function $(id) { return document.getElementById(id); }

  /* ---------- dates ----------------------------------------------------- */

  function parseDate(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function fmtTime(iso) {
    var d = parseDate(iso);
    if (!d) return "";
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ })
      .replace(":00", "").toLowerCase().replace(/\s/g, "");
  }

  function dayKey(iso) {
    var d = parseDate(iso);
    // en-CA gives YYYY-MM-DD, which sorts correctly as a plain string.
    return d ? d.toLocaleDateString("en-CA", { timeZone: TZ }) : "";
  }

  function todayKey() {
    return new Date().toLocaleDateString("en-CA", { timeZone: TZ });
  }

  function fromKey(key) {
    var p = key.split("-");
    return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  }

  function addDays(key, n) {
    var d = fromKey(key);
    d.setDate(d.getDate() + n);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
      "-" + String(d.getDate()).padStart(2, "0");
  }

  function fmtDayLong(key) {
    var label = fromKey(key).toLocaleDateString("en-US", {
      weekday: "long", month: "long", day: "numeric"
    });
    var today = todayKey();
    if (key === today) return "Today, " + label;
    if (key === addDays(today, 1)) return "Tomorrow, " + label;
    return label;
  }

  function fmtDayShort(iso) {
    var d = parseDate(iso);
    return d ? d.toLocaleDateString("en-US", { weekday: "short", timeZone: TZ }) : "";
  }

  function fmtWhen(event) {
    var start = parseDate(event.start);
    if (!start) return "";
    var day = start.toLocaleDateString("en-US", {
      weekday: "long", month: "long", day: "numeric", timeZone: TZ
    });
    if (event.all_day) return day + ", all day";
    var text = day + ", " + fmtTime(event.start);
    if (event.end) text += " to " + fmtTime(event.end);
    return text;
  }

  /* ---------- filtering ------------------------------------------------- */

  var TIME_WINDOWS = {
    morning: [0, 11],      // anything starting before noon
    afternoon: [12, 16],
    evening: [17, 23]
  };

  function whenRange(when) {
    var start = todayKey();
    if (when === "date" && state.date) return [state.date, state.date];
    if (when === "next2") return [start, addDays(start, 1)];
    if (when === "today") return [start, start];
    if (when === "tomorrow") return [addDays(start, 1), addDays(start, 1)];
    if (when === "week") return [start, addDays(start, 7)];
    if (when === "month") return [start, addDays(start, 30)];
    if (when === "weekend") {
      // Friday through Sunday. On a Saturday or Sunday that means this one.
      var dow = fromKey(start).getDay();
      var toFriday = (5 - dow + 7) % 7;
      if (dow === 6) toFriday = -1;
      if (dow === 0) toFriday = -2;
      var friday = addDays(start, toFriday);
      if (friday < start) friday = start;
      return [friday, addDays(friday, 2)];
    }
    return [start, "9999-12-31"];
  }

  function matches(event) {
    var key = dayKey(event.start);
    var range = whenRange(state.when);
    if (key < range[0] || key > range[1]) return false;

    if (state.timeOfDay) {
      // An all day listing is not morning or afternoon, so it drops out here.
      if (event.all_day) return false;
      var window = TIME_WINDOWS[state.timeOfDay];
      var hour = Number(parseDate(event.start)
        .toLocaleTimeString("en-GB", { hour: "2-digit", hour12: false, timeZone: TZ })
        .slice(0, 2));
      if (hour < window[0] || hour > window[1]) return false;
    }

    for (var name in FILTERS) {
      var picked = state.picked[name];
      if (picked.size && !FILTERS[name].test(event, picked)) return false;
    }

    if (state.keywords.length) {
      var hay = (event.title + " " + event.venue + " " + event.description + " " +
        event.city + " " + (event.categories || []).join(" ") + " " +
        event.source_name).toLowerCase();
      for (var i = 0; i < state.keywords.length; i++) {
        if (hay.indexOf(state.keywords[i]) === -1) return false;
      }
    }
    return true;
  }

  function visible() { return state.events.filter(matches); }

  /* ---------- calendar links -------------------------------------------- */

  function stamp(iso) {
    var d = parseDate(iso);
    return d ? d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "") : "";
  }

  function endOrGuess(event) {
    if (event.end) return event.end;
    var d = parseDate(event.start);
    if (!d) return event.start;
    d.setHours(d.getHours() + 1);
    return d.toISOString();
  }

  /* Everything worth having in your calendar three weeks from now, when the
     title alone will not remind you what this was or where to park. */
  function blurb(event) {
    var lines = [];
    if (event.description) lines.push(event.description, "");

    lines.push("When: " + fmtWhen(event));

    var place = event.address || event.venue;
    if (place) {
      var where = "Where: " + place;
      if (event.city && place.indexOf(event.city) === -1) where += ", " + event.city;
      lines.push(where);
    }
    if (event.drive_minutes != null && event.zone !== "city") {
      lines.push("Drive: about " + event.drive_minutes + " minutes from downtown Ann Arbor");
    }

    if (event.audience_raw) lines.push("Ages: " + event.audience_raw);
    else if (event.all_ages) lines.push("Ages: all ages");

    lines.push("Cost: " + (event.cost === "free" ? "Free"
      : (event.price || (event.cost === "paid" ? "Paid" : "Not listed"))));
    lines.push("Signup: " + (event.registration
      ? "Registration required, book before you go"
      : "Drop in, no signup needed"));

    if (event.setting === "indoor") lines.push("Indoors");
    else if (event.setting === "outdoor") lines.push("Outdoors, dress for the weather");

    if (event.source_name) lines.push("Listed by: " + event.source_name);
    if (event.url) lines.push("Details: " + event.url);
    lines.push("Found on: " + SITE + "/?event=" + event.id);
    lines.push("", "Double check the time with the organizer before you go.");

    return lines.join("\n");
  }

  function calendarLocation(event) {
    var parts = [];
    if (event.venue) parts.push(event.venue);
    if (event.address && event.address !== event.venue) parts.push(event.address);
    else if (event.city) parts.push(event.city + ", MI");
    return parts.join(", ") || "Ann Arbor, MI";
  }

  function googleLink(event) {
    return "https://calendar.google.com/calendar/render?" + new URLSearchParams({
      action: "TEMPLATE",
      text: event.title,
      dates: stamp(event.start) + "/" + stamp(endOrGuess(event)),
      details: blurb(event),
      location: calendarLocation(event),
      ctz: TZ
    }).toString();
  }

  function icsEscape(value) {
    return String(value || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;")
      .replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  }

  function singleIcs(event) {
    var lines = [
      "BEGIN:VCALENDAR", "VERSION:2.0",
      "PRODID:-//kid-events-in-ann-arbor//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
      "BEGIN:VEVENT",
      "UID:" + event.id + "@kid-events-in-ann-arbor",
      "DTSTAMP:" + stamp(new Date().toISOString()),
      "DTSTART:" + stamp(event.start),
      "DTEND:" + stamp(endOrGuess(event)),
      "SUMMARY:" + icsEscape(event.title),
      "LOCATION:" + icsEscape(calendarLocation(event)),
      "DESCRIPTION:" + icsEscape(blurb(event))
    ];
    if (event.lat != null && event.lon != null) {
      lines.push("GEO:" + event.lat + ";" + event.lon);
    }
    if (event.categories && event.categories.length) {
      lines.push("CATEGORIES:" + icsEscape(event.categories.slice(0, 6).join(",")));
    }
    if (event.url) lines.push("URL:" + event.url);
    lines.push("END:VEVENT", "END:VCALENDAR");
    return lines.join("\r\n") + "\r\n";
  }

  function downloadIcs(event) {
    var blob = new Blob([singleIcs(event)], { type: "text/calendar;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = (event.title || "event").replace(/[^a-z0-9]+/gi, "-").toLowerCase() + ".ics";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* ---------- rendering ------------------------------------------------- */

  function whereLine(event) {
    var parts = [];
    if (event.venue) parts.push(event.venue);
    if (event.city && event.city !== event.venue) parts.push(event.city);
    if (event.drive_minutes != null && event.zone !== "city") {
      parts.push("about " + event.drive_minutes + " min");
    }
    return parts;
  }

  function fillWhere(node, event) {
    var parts = whereLine(event);
    node.replaceChildren();
    if (!parts.length) {
      node.textContent = "Location to be announced";
      return;
    }
    parts.forEach(function (part, i) {
      if (i) {
        var dot = document.createElement("span");
        dot.className = "dot";
        dot.setAttribute("aria-hidden", "true");
        dot.textContent = "·";
        node.appendChild(dot);
      }
      node.appendChild(document.createTextNode(part));
    });
  }

  function badgeList(event) {
    var out = [];
    if (event.all_ages) {
      out.push(["All ages", "badge-age"]);
    } else if (event.ages && event.ages.length) {
      if (event.ages.length > 3) {
        out.push([AGE_LABELS[event.ages[0]] + " to " + AGE_LABELS[event.ages[event.ages.length - 1]], "badge-age"]);
      } else {
        event.ages.forEach(function (a) { out.push([AGE_LABELS[a] || a, "badge-age"]); });
      }
    }
    if (event.cost === "free") out.push(["Free", "badge-free"]);
    else if (event.price) out.push([event.price, ""]);
    if (event.registration) out.push(["Registration required", "badge-register"]);
    if (event.setting === "outdoor") out.push(["Outdoor", ""]);
    else if (event.setting === "indoor") out.push(["Indoor", ""]);
    if (event.source_name) out.push([event.source_name, ""]);
    return out;
  }

  function fillBadges(list, event) {
    list.replaceChildren();
    badgeList(event).forEach(function (pair) {
      var li = document.createElement("li");
      li.className = "badge " + pair[1];
      li.textContent = pair[0];
      list.appendChild(li);
    });
  }

  function buildCard(event) {
    var node = el.tpl.content.cloneNode(true);
    node.querySelector(".card").id = "e-" + event.id;

    node.querySelector(".card-day").textContent = fmtDayShort(event.start);
    node.querySelector(".card-hour").textContent = event.all_day ? "All day" : fmtTime(event.start);

    var until = node.querySelector(".card-until");
    if (!event.all_day && event.end && fmtTime(event.end) !== fmtTime(event.start)) {
      until.textContent = "to " + fmtTime(event.end);
    } else {
      until.remove();
    }

    var card = node.querySelector(".card");
    var open = node.querySelector(".card-open");
    open.querySelector(".card-name").textContent = event.title;
    open.setAttribute("aria-label", "More about " + event.title);
    open.addEventListener("click", function () { toggleCard(card, event); });

    fillWhere(node.querySelector(".card-where"), event);

    var desc = node.querySelector(".card-desc");
    if (event.description) desc.textContent = event.description;
    else desc.remove();

    fillBadges(node.querySelector(".badges"), event);

    var google = node.querySelector(".card-google");
    google.href = googleLink(event);
    google.setAttribute("aria-label", "Add " + event.title + " to Google Calendar");

    var apple = node.querySelector(".card-apple");
    apple.setAttribute("aria-label", "Add " + event.title + " to Apple Calendar");
    apple.addEventListener("click", function () { downloadIcs(event); });

    var copy = node.querySelector(".card-copy");
    copy.setAttribute("aria-label", "Copy a link to " + event.title);
    copy.addEventListener("click", function () { copyLink(event, copy); });

    var source = node.querySelector(".card-source");
    if (event.url) {
      source.href = event.url;
      source.setAttribute("aria-label", "View " + event.title + " on " + event.source_name);
    } else {
      // No specific page to send anyone to, so do not send them to a listing.
      source.remove();
    }

    return node;
  }

  /* ---------- expand, collapse, share ----------------------------------- */

  function detailRows(event) {
    var rows = [["When", fmtWhen(event)]];

    var place = [event.venue, event.address !== event.venue ? event.address : ""]
      .filter(Boolean).join(", ");
    if (!place && event.city) place = event.city;
    if (place) rows.push(["Where", place]);

    if (event.drive_minutes != null && event.zone !== "city") {
      rows.push(["Drive", "About " + event.drive_minutes + " minutes from downtown"]);
    }
    if (event.audience_raw) rows.push(["Ages", event.audience_raw]);
    else if (event.all_ages) rows.push(["Ages", "All ages"]);

    rows.push(["Cost", event.cost === "free" ? "Free"
      : (event.price || (event.cost === "paid" ? "Paid" : "Not listed"))]);
    rows.push(["Signup", event.registration
      ? "Registration required" : "Drop in, no signup needed"]);

    if (event.setting === "indoor") rows.push(["Setting", "Indoors"]);
    else if (event.setting === "outdoor") rows.push(["Setting", "Outdoors"]);

    var credit = event.source_name || "an unknown source";
    if (event.also_seen_on && event.also_seen_on.length) {
      credit += ", also on " + event.also_seen_on.join(", ");
    }
    rows.push(["Listed by", credit]);
    return rows;
  }

  function fillDetails(card, event) {
    var list = card.querySelector(".detail-list");
    if (list.childElementCount) return;   // already built
    detailRows(event).forEach(function (row) {
      var dt = document.createElement("dt");
      dt.textContent = row[0];
      var dd = document.createElement("dd");
      dd.textContent = row[1];
      list.appendChild(dt);
      list.appendChild(dd);
    });
  }

  function toggleCard(card, event, force) {
    var open = force !== undefined ? force : !card.classList.contains("is-open");
    if (open) fillDetails(card, event);
    card.classList.toggle("is-open", open);
    card.querySelector(".card-more").hidden = !open;
    card.querySelector(".card-open").setAttribute("aria-expanded", open ? "true" : "false");
  }

  function shareLink(event) { return SITE + "/?event=" + event.id; }

  function copyLink(event, button) {
    var url = shareLink(event);
    var was = button.textContent;

    function done(message) {
      button.textContent = message;
      setTimeout(function () { button.textContent = was; }, 1800);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { done("Link copied"); },
        function () { fallbackCopy(url, done); });
    } else {
      fallbackCopy(url, done);
    }
  }

  function fallbackCopy(text, done) {
    // Older Safari, and any browser that refuses the async clipboard.
    var box = document.createElement("textarea");
    box.value = text;
    box.setAttribute("readonly", "");
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.appendChild(box);
    box.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
    document.body.removeChild(box);
    done(ok ? "Link copied" : "Press Ctrl+C");
  }

  function renderList(events) {
    var groups = {};
    events.forEach(function (e) {
      var key = dayKey(e.start);
      (groups[key] = groups[key] || []).push(e);
    });

    var frag = document.createDocumentFragment();
    Object.keys(groups).sort().forEach(function (key) {
      var section = document.createElement("section");
      section.className = "day-group";

      var heading = document.createElement("h2");
      heading.className = "day-heading";
      heading.appendChild(document.createTextNode(fmtDayLong(key)));

      var counter = document.createElement("span");
      counter.className = "day-count";
      counter.textContent = groups[key].length + (groups[key].length === 1 ? " event" : " events");
      heading.appendChild(counter);

      section.appendChild(heading);
      groups[key].forEach(function (e) { section.appendChild(buildCard(e)); });
      frag.appendChild(section);
    });

    el.list.replaceChildren(frag);
  }

  function renderMonth(events) {
    var byDay = {};
    events.forEach(function (e) {
      var key = dayKey(e.start);
      (byDay[key] = byDay[key] || []).push(e);
    });

    var months = {};
    Object.keys(byDay).forEach(function (k) { months[k.slice(0, 7)] = true; });

    var frag = document.createDocumentFragment();
    var today = todayKey();

    Object.keys(months).sort().slice(0, 4).forEach(function (mk) {
      var year = Number(mk.slice(0, 4));
      var month = Number(mk.slice(5, 7)) - 1;

      var wrap = document.createElement("section");
      wrap.className = "month";

      var head = document.createElement("div");
      head.className = "month-head";
      var h2 = document.createElement("h2");
      h2.textContent = new Date(year, month, 1)
        .toLocaleDateString("en-US", { month: "long", year: "numeric" });
      head.appendChild(h2);
      wrap.appendChild(head);

      var grid = document.createElement("div");
      grid.className = "month-grid";

      ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach(function (d) {
        var cell = document.createElement("div");
        cell.className = "month-dow";
        cell.textContent = d;
        grid.appendChild(cell);
      });

      var first = new Date(year, month, 1).getDay();
      var days = new Date(year, month + 1, 0).getDate();

      for (var i = 0; i < first; i++) {
        var blank = document.createElement("div");
        blank.className = "month-cell is-empty";
        grid.appendChild(blank);
      }

      for (var day = 1; day <= days; day++) {
        var key = mk + "-" + String(day).padStart(2, "0");
        var cell = document.createElement("div");
        cell.className = "month-cell" + (key === today ? " is-today" : "");

        var num = document.createElement("span");
        num.className = "month-date";
        num.textContent = day;
        cell.appendChild(num);

        var list = byDay[key] || [];
        list.slice(0, 3).forEach(function (e) {
          var button = document.createElement("button");
          button.type = "button";
          button.className = "month-item";
          button.textContent = (e.all_day ? "" : fmtTime(e.start) + " ") + e.title;
          button.addEventListener("click", (function (row) {
            return function () {
              setView("list");
              var card = document.getElementById("e-" + row.id);
              if (!card) return;
              toggleCard(card, row, true);
              card.scrollIntoView({ behavior: "smooth", block: "center" });
              var opener = card.querySelector(".card-open");
              if (opener) opener.focus();
            };
          })(e));
          cell.appendChild(button);
        });

        if (list.length > 3) {
          var more = document.createElement("span");
          more.className = "month-more";
          more.textContent = "+" + (list.length - 3) + " more";
          cell.appendChild(more);
        }
        grid.appendChild(cell);
      }

      wrap.appendChild(grid);
      frag.appendChild(wrap);
    });

    el.month.replaceChildren(frag);
  }

  function render() {
    var events = visible();

    el.count.textContent = events.length === 0
      ? "No events match"
      : events.length + (events.length === 1 ? " event" : " events") + " found";
    el.empty.hidden = events.length > 0;
    if (!events.length) {
      $("empty-text").textContent = emptyAdvice();
      $("empty-undo").hidden = state.history.length === 0;
    }

    if (state.view === "list") {
      renderList(events);
      el.list.hidden = false;
      el.month.hidden = true;
    } else {
      renderMonth(events);
      el.list.hidden = true;
      el.month.hidden = false;
    }
  }

  function setView(view) {
    state.view = view;
    document.querySelectorAll("[data-view]").forEach(function (b) {
      var on = b.dataset.view === view;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    render();
  }

  /* ---------- the event detail dialog ----------------------------------- */

  function openDialog(dialog, focusBack) {
    state.lastFocus = focusBack || document.activeElement;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
  }

  /* ---------- multi selects --------------------------------------------- */

  function summarize(name) {
    var config = FILTERS[name];
    var picked = state.picked[name];
    if (!picked.size) return config.empty;
    var labels = config.options
      .filter(function (o) { return picked.has(o.value); })
      .map(function (o) { return o.short || o.label; });
    if (labels.length === 1) return labels[0];
    return labels[0] + " +" + (labels.length - 1);
  }

  function refreshMulti(name) {
    var button = $("btn-" + name);
    $("val-" + name).textContent = summarize(name);
    button.classList.toggle("is-set", state.picked[name].size > 0);
  }

  function closeAllPanels(except) {
    Object.keys(FILTERS).forEach(function (name) {
      if (name === except) return;
      var panel = $("panel-" + name);
      if (panel && !panel.hidden) {
        panel.hidden = true;
        $("btn-" + name).setAttribute("aria-expanded", "false");
      }
    });
  }

  function buildMulti(name) {
    var config = FILTERS[name];
    var panel = $("panel-" + name);
    var button = $("btn-" + name);

    panel.replaceChildren();
    config.options.forEach(function (option) {
      var label = document.createElement("label");
      label.className = "opt";

      var box = document.createElement("input");
      box.type = config.single ? "radio" : "checkbox";
      if (config.single) box.name = "filter-" + name;
      box.value = option.value;
      box.checked = config.single
        ? (state.picked[name].has(option.value) ||
           (!state.picked[name].size && option.value === config.fallback))
        : state.picked[name].has(option.value);
      box.addEventListener("change", function () {
        endTypingRun();
        remember();
        if (config.single) {
          state.picked[name].clear();
          if (option.value !== config.fallback) state.picked[name].add(option.value);
        } else if (box.checked) {
          state.picked[name].add(option.value);
        } else {
          state.picked[name].delete(option.value);
        }
        refreshMulti(name);
        apply();
      });

      var text = document.createElement("span");
      text.textContent = option.label;

      // An option can carry a caveat. Better under the checkbox, where you
      // read it before ticking, than in a footnote nobody scrolls to.
      if (option.note) {
        var note = document.createElement("small");
        note.className = "opt-note";
        note.textContent = option.note;
        text.appendChild(note);
      }

      label.appendChild(box);
      label.appendChild(text);
      panel.appendChild(label);
    });

    if (!config.single) {
      var clear = document.createElement("button");
      clear.type = "button";
      clear.className = "multi-clear";
      clear.textContent = "Clear this filter";
      clear.addEventListener("click", function () {
        endTypingRun();
        remember();
        state.picked[name].clear();
        panel.querySelectorAll("input").forEach(function (b) { b.checked = false; });
        refreshMulti(name);
        apply();
        button.focus();
      });
      panel.appendChild(clear);
    }

    button.addEventListener("click", function () {
      var open = panel.hidden;
      closeAllPanels(name);
      panel.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });

    button.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        closeAllPanels(name);
        panel.hidden = false;
        button.setAttribute("aria-expanded", "true");
        var firstBox = panel.querySelector("input");
        if (firstBox) firstBox.focus();
      }
    });

    panel.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      panel.hidden = true;
      button.setAttribute("aria-expanded", "false");
      button.focus();
    });

    refreshMulti(name);
  }

  /* ---------- the plain language search ---------------------------------- */

  var CHIP_LABELS = {
    age: "Age", where: "Where", setting: "Setting",
    cost: "Cost", signup: "Signup", repeats: "Repeats"
  };

  function syncCheckboxes() {
    Object.keys(FILTERS).forEach(function (name) {
      var panel = $("panel-" + name);
      if (!panel) return;
      var config = FILTERS[name];
      panel.querySelectorAll("input").forEach(function (box) {
        box.checked = config.single
          ? (state.picked[name].has(box.value) ||
             (!state.picked[name].size && box.value === config.fallback))
          : state.picked[name].has(box.value);
      });
      refreshMulti(name);
    });
    var radio = el.form.querySelector('input[name="when"][value="' + state.when + '"]');
    el.form.querySelectorAll('input[name="when"]').forEach(function (r) {
      r.checked = r === radio;
    });
  }

  function runAsk(text, opts) {
    // A run of keystrokes is one action, not one per pause. Without this,
    // typing a five word question buries the previous state five presses deep.
    var typing = opts && opts.typing;
    if (!(typing && state.qTyping)) remember();
    state.qTyping = !!typing;
    state.q = text;
    var parsed = window.NLQ.parse(text, new Date());

    Object.keys(FILTERS).forEach(function (name) {
      state.picked[name].clear();
      (parsed[name] || []).forEach(function (v) { state.picked[name].add(v); });
    });

    state.when = parsed.when || "all";
    state.date = parsed.date || "";
    state.timeOfDay = parsed.timeOfDay || "";
    state.keywords = parsed.keywords;
    state.understood = parsed.understood.slice();
    if (parsed.keywords.length) {
      state.understood.push("matching \u201c" + parsed.keywords.join(" ") + "\u201d");
    }

    syncCheckboxes();
    apply();
  }

  /* The search box mirrors state.q, except while it has focus, because
     rewriting an input somebody is typing into moves their caret. */
  function syncAskBox() {
    if (!el.ask) return;
    if (document.activeElement === el.ask) return;
    if (el.ask.value !== state.q) el.ask.value = state.q;
  }

  function clearAsk() {
    state.q = "";
    state.keywords = [];
    state.understood = [];
    state.timeOfDay = "";
    state.date = "";
    el.ask.value = "";
  }

  var WHEN_LABELS = {
    next2: "Today & tomorrow",
    today: "Today", tomorrow: "Tomorrow", weekend: "This weekend",
    week: "Next 7 days", month: "Next 30 days", date: "A chosen day"
  };

  var TOD_LABELS = { morning: "Morning", afternoon: "Afternoon", evening: "Evening" };

  function endTypingRun() { state.qTyping = false; }

  function restoreSnapshot(snap) {
    Object.keys(state.picked).forEach(function (name) {
      state.picked[name] = new Set(snap.picked[name] || []);
    });
    state.when = snap.when;
    state.date = snap.date;
    state.timeOfDay = snap.timeOfDay;
    state.q = snap.q;
    state.keywords = snap.keywords.slice();
    state.understood = snap.understood.slice();
  }

  /* Every filter that is doing something, shown as a chip you can take off.
     Recognition rather than recall: the state of the page is on the page, and
     each piece of it is one click from being undone. */
  function activeChips() {
    var chips = [];

    Object.keys(FILTERS).forEach(function (name) {
      var config = FILTERS[name];
      state.picked[name].forEach(function (value) {
        if (config.single && value === config.fallback) return;
        var option = config.options.filter(function (o) { return o.value === value; })[0];
        chips.push({
          label: (option && (option.short || option.label)) || value,
          remove: function () {
            state.picked[name].delete(value);
            syncCheckboxes();
          }
        });
      });
    });

    if (state.when !== "all") {
      chips.push({
        label: state.when === "date" && state.date
          ? new Date(state.date + "T12:00:00").toLocaleDateString("en-US",
              { weekday: "long", month: "short", day: "numeric" })
          : WHEN_LABELS[state.when] || state.when,
        remove: function () {
          state.when = "all";
          state.date = "";
          syncCheckboxes();
        }
      });
    }

    if (state.timeOfDay) {
      chips.push({
        label: TOD_LABELS[state.timeOfDay],
        remove: function () { state.timeOfDay = ""; }
      });
    }

    if (state.keywords.length) {
      chips.push({
        label: "\u201c" + state.keywords.join(" ") + "\u201d",
        remove: function () {
          state.keywords = [];
          state.q = "";
        }
      });
    }

    return chips;
  }

  function renderActive() {
    var box = el.active;
    box.replaceChildren();

    var chips = activeChips();
    var unread = state.q && !state.understood.length && !state.keywords.length;

    if (!chips.length && !unread) return;

    if (unread) {
      var note = document.createElement("p");
      note.className = "ask-note";
      note.textContent = "Nothing in that search matched a filter, so nothing is narrowed down. " +
        "Naming an age, a day, or a place works best.";
      box.appendChild(note);
      return;
    }

    var lead = document.createElement("span");
    lead.className = "active-lead";
    lead.textContent = "Showing";
    box.appendChild(lead);

    chips.forEach(function (chip) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "active-chip";
      button.setAttribute("aria-label", "Remove filter: " + chip.label);

      var text = document.createElement("span");
      text.textContent = chip.label;
      button.appendChild(text);

      var cross = document.createElement("span");
      cross.className = "active-x";
      cross.setAttribute("aria-hidden", "true");
      cross.textContent = "\u00d7";
      button.appendChild(cross);

      button.addEventListener("click", function () {
        endTypingRun();
        remember();
        chip.remove();
        apply();
      });
      box.appendChild(button);
    });

    var clear = document.createElement("button");
    clear.type = "button";
    clear.className = "active-clear";
    clear.textContent = "Show everything";
    clear.addEventListener("click", showEverything);
    box.appendChild(clear);
  }

  function showEverything() {
    endTypingRun();
    remember();
    clearAsk();
    state.when = "all";
    state.date = "";
    Object.keys(FILTERS).forEach(function (name) { state.picked[name].clear(); });
    syncCheckboxes();
    apply();
  }

  /* When a combination returns nothing, say which filter is most likely the
     problem instead of shrugging. */
  function emptyAdvice() {
    var chips = activeChips();
    if (!chips.length) {
      return "There is nothing on the calendar right now. The daily update may not have run yet.";
    }

    var before = snapshot();
    var counts = chips.map(function (chip) {
      chip.remove();
      var n = visible().length;
      restoreSnapshot(before);
      return { label: chip.label, n: n };
    }).filter(function (c) { return c.n > 0; })
      .sort(function (a, b) { return b.n - a.n; });
    restoreSnapshot(before);
    syncCheckboxes();

    if (!counts.length) {
      return "Nothing matches that combination. Try taking a filter off.";
    }
    return "Nothing matches all of that. Dropping " + counts[0].label +
      " would show " + counts[0].n + (counts[0].n === 1 ? " event." : " events.");
  }

  /* ---------- URL state -------------------------------------------------- */

  function writeUrl() {
    var params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    Object.keys(FILTERS).forEach(function (name) {
      if (state.picked[name].size) {
        params.set(name, Array.from(state.picked[name]).join(","));
      }
    });
    if (state.when !== DEFAULT_WHEN) params.set("when", state.when);
    if (state.date) params.set("date", state.date);
    if (state.timeOfDay) params.set("tod", state.timeOfDay);
    var query = params.toString();
    history.replaceState(null, "", query ? "?" + query : location.pathname);
  }

  function readUrl() {
    var params = new URLSearchParams(location.search);
    if (params.has("q")) {
      state.q = params.get("q");
      el.ask.value = state.q;
      state.keywords = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    }
    if (params.has("date")) state.date = params.get("date");
    if (params.has("tod")) state.timeOfDay = params.get("tod");
    if (params.has("event")) state.shared = params.get("event");
    Object.keys(FILTERS).forEach(function (name) {
      if (!params.has(name)) return;
      params.get(name).split(",").filter(Boolean).forEach(function (v) {
        state.picked[name].add(v);
      });
    });
    if (params.has("when")) {
      state.when = params.get("when");
      var radio = el.form.querySelector('input[name="when"][value="' + state.when + '"]');
      if (radio) radio.checked = true;
    }
  }

  /* A link someone was texted points at one event. Widen the dates so it is
     definitely on screen, then open it. */
  function openShared(id) {
    var event = state.byId[id];
    if (!event) return;
    state.when = "all";
    state.date = "";
    syncCheckboxes();
    apply();

    var card = document.getElementById("e-" + id);
    if (!card) return;
    toggleCard(card, event, true);
    card.classList.add("is-shared");
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    var button = card.querySelector(".card-open");
    if (button) button.focus();
  }

  function apply() {
    syncAskBox();
    writeUrl();
    renderActive();
    render();
    var undoButton = $("undo");
    if (undoButton) undoButton.disabled = state.history.length === 0;
  }

  /* ---------- theme ------------------------------------------------------ */

  function setupTheme() {
    var button = $("theme-toggle");
    var saved = null;
    try { saved = localStorage.getItem("a2kids-theme"); } catch (err) { saved = null; }
    var prefersDark = typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    var dark = saved ? saved === "dark" : prefersDark;

    function paint() {
      document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
      button.setAttribute("aria-pressed", dark ? "true" : "false");
      button.querySelector(".theme-label").textContent = dark ? "Light" : "Dark";
    }
    paint();

    button.addEventListener("click", function () {
      dark = !dark;
      try { localStorage.setItem("a2kids-theme", dark ? "dark" : "light"); } catch (err) { /* private mode */ }
      paint();
    });
  }

  /* ---------- subscribe -------------------------------------------------- */

  function feedUrl(file) { return SITE + "/feeds/" + file; }

  var AGE_FEEDS = ["age-baby.ics", "age-toddler.ics", "age-preschool.ics",
                   "age-elementary.ics", "age-tween.ics", "age-teen.ics"];

  function feedCheckbox(feed) {
    var label = document.createElement("label");
    label.className = "opt";

    var box = document.createElement("input");
    box.type = "checkbox";
    box.value = feed.file;
    box.addEventListener("change", renderPickedFeeds);

    var text = document.createElement("span");
    text.textContent = feed.label + " (" + feed.count + ")";

    label.appendChild(box);
    label.appendChild(text);
    return label;
  }

  function pickedFeeds() {
    return Array.from(el.subscribe.querySelectorAll(".feed-options input:checked"))
      .map(function (box) {
        return state.feeds.filter(function (f) { return f.file === box.value; })[0];
      })
      .filter(Boolean);
  }

  function renderPickedFeeds() {
    var box = $("feed-picked");
    box.replaceChildren();

    var picked = pickedFeeds();
    if (!picked.length) {
      var hint = document.createElement("p");
      hint.className = "dialog-note";
      hint.textContent = "Tick one or more above and the buttons appear here.";
      box.appendChild(hint);
      return;
    }

    var heading = document.createElement("p");
    heading.className = "feed-count";
    heading.textContent = picked.length === 1
      ? "One calendar to add"
      : picked.length + " calendars to add, one at a time";
    box.appendChild(heading);

    picked.forEach(function (feed) {
      var https = feedUrl(feed.file);
      var row = document.createElement("div");
      row.className = "feed-row";

      var name = document.createElement("span");
      name.className = "feed-name";
      name.textContent = feed.label;
      row.appendChild(name);

      var google = document.createElement("a");
      google.className = "btn btn-small btn-primary";
      google.target = "_blank";
      google.rel = "noopener";
      google.href = "https://calendar.google.com/calendar/r/settings/addbyurl?cid=" +
        encodeURIComponent(https);
      google.textContent = "Google";
      google.setAttribute("aria-label", "Add " + feed.label + " to Google Calendar");
      row.appendChild(google);

      var apple = document.createElement("a");
      apple.className = "btn btn-small btn-secondary";
      apple.href = https.replace(/^https?:/, "webcal:");
      apple.textContent = "Apple";
      apple.setAttribute("aria-label", "Add " + feed.label + " to Apple Calendar");
      row.appendChild(apple);

      var copy = document.createElement("button");
      copy.type = "button";
      copy.className = "btn btn-small btn-ghost";
      copy.textContent = "Copy";
      copy.setAttribute("aria-label", "Copy the link for " + feed.label);
      copy.addEventListener("click", function () {
        var was = copy.textContent;
        function done(message) {
          copy.textContent = message;
          setTimeout(function () { copy.textContent = was; }, 1800);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(https).then(function () { done("Copied"); },
            function () { fallbackCopy(https, done); });
        } else {
          fallbackCopy(https, done);
        }
      });
      row.appendChild(copy);

      box.appendChild(row);
    });
  }

  function buildFeedPicker(feeds) {
    state.feeds = feeds.map(function (feed) {
      return {
        file: feed.file,
        count: feed.count,
        label: feed.name.replace(/^Kid Events(:| in Ann Arbor:?)?\s*/, "") || "Everything"
      };
    });

    var ages = $("feed-ages");
    var other = $("feed-other");
    ages.replaceChildren();
    other.replaceChildren();

    state.feeds.forEach(function (feed) {
      (AGE_FEEDS.indexOf(feed.file) !== -1 ? ages : other).appendChild(feedCheckbox(feed));
    });

    renderPickedFeeds();
  }

  function setupSubscribe() {
    $("subscribe-open").addEventListener("click", function (e) {
      openDialog(el.subscribe, e.currentTarget);
      var first = el.subscribe.querySelector(".feed-options input");
      if (first) first.focus();
    });
  }

  /* ---------- footer ------------------------------------------------------ */

  function renderFooter(meta) {
    var when = parseDate(meta.generated);
    el.build.textContent = "Last updated " + (when
      ? when.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: TZ })
      : "recently") + ". " + meta.count + " events across the next " + meta.horizon_days + " days.";

    var frag = document.createDocumentFragment();
    frag.appendChild(document.createTextNode("Pulled from: "));
    (meta.sources || []).forEach(function (source) {
      var pill = document.createElement("span");
      pill.className = "source-pill" + (source.ok ? "" : " is-down");
      pill.textContent = source.name + (source.ok ? " (" + source.count + ")" : " (no data)");
      if (!source.ok && source.error) pill.title = source.error;
      frag.appendChild(pill);
    });
    el.sources.replaceChildren(frag);
  }

  /* ---------- boot -------------------------------------------------------- */

  function boot(payload, feeds) {
    state.events = (payload.events || []).sort(function (a, b) {
      return (a.start || "").localeCompare(b.start || "");
    });
    state.events.forEach(function (e) { state.byId[e.id] = e; });
    state.meta = payload;

    FILTERS.age.options = (payload.age_bands || []).map(function (band) {
      return { value: band.key, label: band.label, short: AGE_LABELS[band.key] || band.label };
    });

    readUrl();
    Object.keys(FILTERS).forEach(buildMulti);

    buildFeedPicker(feeds.feeds || []);

    renderFooter(payload);
    apply();

    if (state.shared) openShared(state.shared);
  }

  function init() {
    el = {
      list: $("list-view"),
      month: $("month-view"),
      count: $("count"),
      empty: $("empty"),
      form: $("filters"),
      askForm: $("ask-form"),
      ask: $("ask"),
      active: $("active-bar"),
      build: $("build-info"),
      sources: $("source-list"),
      subscribe: $("subscribe"),
      results: $("results"),
      tpl: $("event-card")
    };

    setupTheme();
    setupSubscribe();

    el.askForm.addEventListener("submit", function (e) {
      e.preventDefault();
      endTypingRun();
      runAsk(el.ask.value.trim());
      el.results.focus();
    });

    // Typing without hitting the button should still work, just calmly.
    var typingTimer = null;
    el.ask.addEventListener("input", function () {
      clearTimeout(typingTimer);
      typingTimer = setTimeout(function () {
        var text = el.ask.value.trim();
        if (text) runAsk(text, { typing: true });
        else { clearAsk(); apply(); }
      }, 350);
    });


    el.form.querySelectorAll('input[name="when"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        endTypingRun();
        remember();
        state.when = radio.value;
        state.date = "";
        apply();
      });
    });

    el.form.addEventListener("submit", function (e) { e.preventDefault(); });

    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.addEventListener("click", function () { setView(button.dataset.view); });
    });


    $("reset").addEventListener("click", showEverything);
    $("empty-reset").addEventListener("click", showEverything);
    $("undo").addEventListener("click", undo);
    $("empty-undo").addEventListener("click", undo);

    // Slash focuses the search box, the way every search-first site works.
    document.addEventListener("keydown", function (e) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      var tag = (document.activeElement && document.activeElement.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      e.preventDefault();
      el.ask.focus();
      el.ask.select();
    });

    document.querySelectorAll("[data-close-dialog]").forEach(function (button) {
      button.addEventListener("click", function () {
        closeDialog(button.closest("dialog"));
      });
    });

    [el.subscribe].forEach(function (dialog) {
      dialog.addEventListener("click", function (e) {
        // Clicking the backdrop lands on the dialog element itself.
        if (e.target === dialog) closeDialog(dialog);
      });
      dialog.addEventListener("close", function () {
        if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
      });
    });

    document.addEventListener("click", function (e) {
      if (!e.target.closest || !e.target.closest(".multi")) closeAllPanels();
    });

    el.list.innerHTML = '<p class="loading">Loading events...</p>';

    // Single file mode. scripts/build_preview.py bakes the data into the page
    // so it works from a file:// URL with no server behind it.
    var inline = $("inline-data");
    if (inline) {
      var baked = JSON.parse(inline.textContent);
      boot(baked.events, baked.feeds);
      return;
    }

    Promise.all([
      fetch("data/events.json").then(function (r) { return r.json(); }),
      fetch("data/feeds.json").then(function (r) { return r.json(); })
        .catch(function () { return { feeds: [] }; })
    ]).then(function (results) {
      boot(results[0], results[1]);
    }).catch(function (err) {
      el.list.innerHTML = '<p class="loading">Could not load the events file. ' +
        'If this is a fresh checkout, run the scraper once to build it.</p>';
      console.error(err);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
