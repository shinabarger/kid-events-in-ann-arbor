/* Turn "events in Ann Arbor for my 1.5 year old tomorrow afternoon" into
   filters.

   No API and no model. It is a rules parser, which for this job beats a model:
   it runs offline, costs nothing, never invents an answer, and every rule is
   one you can read. It also has to be honest about what it understood, which
   is why parse() reports the phrases it matched. The page shows those back as
   chips you can remove.

   Anything it does not recognize falls through to a plain keyword search, so a
   query is never worse than typing the words in a search box. */

(function (root) {
  "use strict";

  // Same bands as the scraper. An exact age lands in a band when it falls
  // inside the band's range, ends included, so a 5 year old reads as both
  // preschool and elementary and a 1.5 year old as both baby and toddler.
  var AGE_BANDS = {
    baby: [0, 2], toddler: [1, 3], preschool: [3, 5],
    elementary: [5, 10], tween: [10, 13], teen: [13, 18]
  };

  var NAMED_AGES = [
    [/\b(newborn|infants?|babies|baby)\b/, ["baby"]],
    [/\btoddlers?\b/, ["toddler"]],
    [/\b(preschool(?:ers?)?|pre-?k)\b/, ["preschool"]],
    [/\b(kindergart(?:e?n|ner|ener)s?)\b/, ["preschool", "elementary"]],
    [/\b(grade ?school(?:ers?)?|elementary|school ?age(?:d)?)\b/, ["elementary"]],
    [/\btweens?\b/, ["tween"]],
    [/\b(teens?|teenagers?|high ?school(?:ers?)?)\b/, ["teen"]],
    [/\bmiddle ?school(?:ers?)?\b/, ["tween", "teen"]]
  ];

  var WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];

  // Words that carry no meaning once the filters are pulled out.
  var STOP = new Set((
    "a an and any anything are around at be can do doing events event find for from " +
    "get go going good have here i i'm im in into is it kid kids child children " +
    "looking me my near of old on or our out show some something stuff take the there " +
    "these things this to today's up want we what where which who with year years yr " +
    "yrs yo month months old olds please would like need got does day"
  ).split(" "));

  function bandsForAge(age) {
    var out = [];
    Object.keys(AGE_BANDS).forEach(function (band) {
      if (age >= AGE_BANDS[band][0] && age <= AGE_BANDS[band][1]) out.push(band);
    });
    // A number outside every band, say 19, still gets the nearest one.
    if (!out.length) out.push(age < 1 ? "baby" : "teen");
    return out;
  }

  function parse(text, today) {
    var result = {
      age: [], where: [], setting: [], cost: [], signup: [], repeats: [],
      when: null, date: null, timeOfDay: null, keywords: [], understood: []
    };
    if (!text || !text.trim()) return result;

    var s = " " + text.toLowerCase().replace(/[‘’]/g, "'") + " ";
    var eaten = [];

    function eat(pattern, label) {
      var match = s.match(pattern);
      if (!match) return null;
      s = s.replace(match[0], " ");
      eaten.push(match[0].trim());
      if (label) result.understood.push(label);
      return match;
    }

    /* --- age ------------------------------------------------------------ */

    // "18 month old", "18 months"
    var months = eat(/\b(\d{1,2})[\s-]*months?(?:[\s-]*old)?\b/, null);
    if (months) {
      var inYears = Number(months[1]) / 12;
      result.age = bandsForAge(inYears);
      result.understood.push(months[1] + " months old");
    }

    // "1.5 year old", "1 1/2 year old", "2 and a half", "5yo", "5 y/o"
    if (!result.age.length) {
      var years =
        eat(/\b(\d{1,2})\s*(?:and\s*a\s*half|1\/2)\s*(?:years?|yrs?)?[\s-]*old?\b/, null);
      if (years) {
        result.age = bandsForAge(Number(years[1]) + 0.5);
        result.understood.push(years[1] + " and a half years old");
      }
    }
    if (!result.age.length) {
      var plain =
        eat(/\b(\d{1,2}(?:\.\d)?)[\s-]*(?:year|yr)s?[\s-]*old\b/, null) ||
        eat(/\b(\d{1,2}(?:\.\d)?)\s*(?:yo|y\/o)\b/, null) ||
        eat(/\bmy\s+(\d{1,2}(?:\.\d)?)\b(?!\s*(?:pm|am|:))/, null);
      if (plain) {
        result.age = bandsForAge(Number(plain[1]));
        result.understood.push(plain[1] + " year old");
      }
    }

    if (!result.age.length) {
      for (var i = 0; i < NAMED_AGES.length; i++) {
        var named = eat(NAMED_AGES[i][0], null);
        if (named) {
          result.age = NAMED_AGES[i][1].slice();
          result.understood.push(named[0].trim());
          break;
        }
      }
    }

    /* --- when ------------------------------------------------------------ */

    if (eat(/\btonight\b/, "tonight")) {
      result.when = "today";
      result.timeOfDay = "evening";
    } else if (eat(/\btoday\b/, "today")) {
      result.when = "today";
    } else if (eat(/\btomorrow\b/, "tomorrow")) {
      result.when = "tomorrow";
    } else if (eat(/\b(this\s+)?weekend\b/, "this weekend")) {
      result.when = "weekend";
    } else if (eat(/\bnext\s+week\b/, "next week")) {
      result.when = "week";
    } else if (eat(/\b(this\s+week|next\s+(?:7|seven)\s+days)\b/, "next 7 days")) {
      result.when = "week";
    } else if (eat(/\b(this\s+month|next\s+30\s+days)\b/, "next 30 days")) {
      result.when = "month";
    } else {
      for (var d = 0; d < WEEKDAYS.length; d++) {
        var hit = eat(new RegExp("\\b(?:this |next |on )?" + WEEKDAYS[d] + "\\b"), null);
        if (hit) {
          result.date = nextWeekday(today || new Date(), d);
          result.when = "date";
          result.understood.push(WEEKDAYS[d][0].toUpperCase() + WEEKDAYS[d].slice(1));
          break;
        }
      }
    }

    /* --- time of day ------------------------------------------------------ */

    if (!result.timeOfDay) {
      if (eat(/\bmornings?\b/, "morning")) result.timeOfDay = "morning";
      else if (eat(/\b(afternoons?|midday|after\s*lunch|after\s*nap)\b/, "afternoon")) result.timeOfDay = "afternoon";
      else if (eat(/\b(evenings?|nights?|after\s*dinner)\b/, "evening")) result.timeOfDay = "evening";
    }

    /* --- where ------------------------------------------------------------ */

    // Checked first, because "on the bus in Ann Arbor" is a bus question and
    // the city pattern would otherwise swallow it.
    if (eat(/\b(?:on\s+the\s+)?(?:bus|the\s?ride|transit)\b|\bwithout\s+(?:a|the)\s+car\b|\bno\s+car\b|\bcar\s?less\b|\bcan'?t\s+drive\b|\btake\s+the\s+bus\b/, "Bus ride")) {
      result.where = ["bus"];
    } else if (eat(/\b(?:in\s+|around\s+)?(?:downtown\s+)?ann\s*arbor(?:\s+city)?(?:\s+limits)?\b/, "City limits")) {
      result.where = ["city"];
    } else if (eat(/\b(near\s*(?:me|by|us)|nearby|close\s*(?:by|to\s*(?:me|home))|in\s+the\s+area|around\s+here|a\s*short\s*drive)\b/, "30 min drive")) {
      result.where = ["near"];
    } else if (eat(/\b(washtenaw(?:\s+county)?|the\s+county|anywhere)\b/, "Washtenaw")) {
      result.where = ["county"];
    }

    /* --- cost, setting, signup, repeats ----------------------------------- */

    if (eat(/\b(free|no\s*cost|cheap|budget)\b/, "Free")) result.cost = ["free"];
    else if (eat(/\b(paid|ticketed|worth\s*paying)\b/, "Paid")) result.cost = ["paid"];

    if (eat(/\b(indoors?|inside|rainy\s*day|out\s*of\s*the\s*(?:rain|cold|heat))\b/, "Indoor")) {
      result.setting = ["indoor"];
    } else if (eat(/\b(outdoors?|outside|fresh\s*air)\b/, "Outdoor")) {
      result.setting = ["outdoor"];
    }

    if (eat(/\b(drop[\s-]*in|no\s*(?:registration|signup|sign[\s-]*up)|without\s*signing\s*up|walk[\s-]*in)\b/, "Drop in, no signup")) {
      result.signup = ["dropin"];
    } else if (eat(/\b(registration|sign[\s-]*up|tickets?)\b/, "Registration required")) {
      result.signup = ["register"];
    }

    if (eat(/\b(one[\s-]*off|not\s*recurring|no\s*repeats?|skip\s*the\s*repeats?)\b/, "One-off events")) {
      result.repeats = ["oneoff"];
    }

    /* --- whatever is left is a keyword search ------------------------------ */

    result.keywords = s
      .replace(/[^a-z0-9'\s-]/g, " ")
      .split(/\s+/)
      .map(function (w) { return w.trim(); })
      .filter(function (w) { return w.length > 2 && !STOP.has(w) && !/^\d+$/.test(w); });

    return result;
  }

  function nextWeekday(from, weekday) {
    var d = new Date(from.getFullYear(), from.getMonth(), from.getDate());
    var delta = (weekday - d.getDay() + 7) % 7;
    d.setDate(d.getDate() + delta);
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  root.NLQ = { parse: parse, bandsForAge: bandsForAge, AGE_BANDS: AGE_BANDS };
})(typeof window !== "undefined" ? window : globalThis);
