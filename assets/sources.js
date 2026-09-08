/* The source table on the about page.

   Two numbers per source, because they answer different questions. "Found" is
   what the site handed over this morning, so a zero there means the scrape
   itself is broken. "On the calendar" is what survived dedupe, the kid filter,
   the venue gate and the 120 day horizon, so a healthy "found" next to a zero
   "on the calendar" means the source is working fine and simply losing every
   duplicate to a copy somewhere else. */
(function () {
  "use strict";

  var TZ = "America/Detroit";
  var table = document.getElementById("source-table");
  if (!table) return;

  function cell(row, text, className) {
    var td = document.createElement("td");
    td.textContent = text;
    if (className) td.className = className;
    row.appendChild(td);
    return td;
  }

  function render(payload) {
    var sources = (payload.sources || []).slice().sort(function (a, b) {
      return (b.kept || 0) - (a.kept || 0) || a.name.localeCompare(b.name);
    });

    var tbody = document.createElement("tbody");
    sources.forEach(function (source) {
      var row = document.createElement("tr");
      var kept = source.kept || 0;
      var found = source.count || 0;

      cell(row, source.name);
      cell(row, source.ok ? String(found) : "failed", "num");
      cell(row, String(kept), "num");

      var note = "";
      if (!source.ok) note = "the fetch itself failed";
      else if (found === 0) note = "nothing published right now";
      else if (kept === 0) note = "all of it already covered elsewhere";
      cell(row, note, "note");

      if (!source.ok || (found > 0 && kept === 0)) row.className = "needs-a-look";
      tbody.appendChild(row);
    });

    var head = document.createElement("thead");
    var hr = document.createElement("tr");
    ["Source", "Found", "On the calendar", ""].forEach(function (label) {
      var th = document.createElement("th");
      th.textContent = label;
      th.scope = "col";
      hr.appendChild(th);
    });
    head.appendChild(hr);

    var caption = document.createElement("caption");
    var when = new Date(payload.generated);
    caption.textContent = "Checked " + (isNaN(when.getTime()) ? "recently"
      : when.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: TZ }))
      + ". " + (payload.count || 0) + " events across the next "
      + (payload.horizon_days || 120) + " days.";

    table.replaceChildren(caption, head, tbody);
  }

  // Same cache dodge the calendar uses: the data changes every morning and
  // this page does not.
  var stamp = new Date().toLocaleDateString("en-CA", { timeZone: TZ });
  fetch("data/events.json?d=" + stamp, { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("events.json came back " + r.status);
      return r.json();
    })
    .then(render)
    .catch(function () {
      table.replaceChildren();
      var p = document.createElement("caption");
      p.textContent = "Could not load the source list just now.";
      table.appendChild(p);
    });
})();
