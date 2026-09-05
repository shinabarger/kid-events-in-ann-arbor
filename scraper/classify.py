"""Read the messy audience and description text and pull out the filters.

Every source words this differently. AADL says "Babies Up To 24 Months" and
"Grade K-5", Ann Arbor with Kids uses category slugs, the U-M feed says nothing
at all. This is where all of that gets normalized.
"""

from __future__ import annotations

import re

from .models import AGE_BANDS

GRADE_TO_AGE = {"pk": 4, "k": 5}

# Deliberately narrow. "kids ages 5-18 & their families" is a range with a
# note about grown-ups tagging along, not an all ages event, so a bare
# "families" does not count.
ALL_AGES_PATTERNS = [
    r"\ball ages\b",
    r"\bfamily[- ]friendly\b",
    r"\bfor the whole family\b",
    r"\bfun for the whole family\b",
    r"\bkids of all ages\b",
    r"\bfamilies welcome\b",
    r"\bfor families\b",
    r"\ball are welcome\b",
]

OUTDOOR_WORDS = [
    "park", "trail", "hike", "hiking", "nature walk", "garden", "farm",
    "outdoor", "outdoors", "campfire", "canoe", "kayak", "beach", "playground",
    "splash pad", "fairgrounds", "festival grounds", "arboretum", "pond",
    "orchard", "cider mill", "picnic", "camping", "campout", "field",
    "farmers market", "parade", "pool", "metropark", "star party", "stargazing",
]

INDOOR_WORDS = [
    "library", "museum", "theater", "theatre", "gallery", "studio", "gym",
    "classroom", "auditorium", "story corner", "program room", "secret lab",
    "planetarium", "indoor", "ice arena", "rink", "community center",
    "story time", "storytime", "playgroup", "workshop", "lab",
]

FREE_WORDS = ["free", "no charge", "no cost", "complimentary", "donation", "$0"]

REGISTRATION_WORDS = [
    "registration required", "register", "registration opens", "sign up",
    "signup", "tickets required", "pre-register", "preregister", "rsvp",
    "advance registration", "limited spots", "must register", "enroll",
]

DROP_IN_WORDS = ["drop in", "drop-in", "no registration", "no signup", "walk in"]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def parse_age_range(*texts: str):
    """Best guess at (min_age, max_age, is_all_ages) from any audience text."""
    blob = _clean(" | ".join(t for t in texts if t))
    if not blob:
        return None, None, False

    all_ages = any(re.search(p, blob) for p in ALL_AGES_PATTERNS)

    # "Babies Up To 24 Months" / "up to 18 months"
    m = re.search(r"up to (\d{1,2})\s*months?", blob)
    if m:
        return 0, max(1, round(int(m.group(1)) / 12)), all_ages

    # "6 months to 3 years"
    m = re.search(r"(\d{1,2})\s*months?\s*(?:to|-|through|and up)\s*(\d{1,2})\s*years?", blob)
    if m:
        return round(int(m.group(1)) / 12), int(m.group(2)), all_ages

    # "Age 2-5 Years" / "ages 3 to 5" / "2-5 years old"
    m = re.search(r"ages?\s*(\d{1,2})\s*(?:-|–|—|to|through)\s*(\d{1,2})", blob)
    if not m:
        m = re.search(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*years?\s*old", blob)
    if not m:
        # "For kids 0-5 and a caregiver" / "children 2-5 years of age".
        # Parks & Rec write it this way and never use the word "ages", which
        # used to send a 0-5 nature playgroup into the elementary band.
        m = re.search(
            r"\b(?:kids?|children|kiddos|youth|little ones)\s*"
            r"(?:aged?\s*)?(\d{1,2})\s*(?:-|–|—|to|through)\s*(\d{1,2})\b",
            blob,
        )
    if not m:
        m = re.search(
            r"\b(\d{1,2})\s*(?:-|–|—|to|through)\s*(\d{1,2})\s*years? of age\b", blob
        )
    if m:
        return int(m.group(1)), int(m.group(2)), all_ages

    # "Grade K-5" / "grades 2-8" / "Grade 6 and up"
    m = re.search(r"grades?\s*([k0-9]{1,2})\s*(?:-|–|—|to|through)\s*([k0-9]{1,2})", blob)
    if m:
        lo = _grade_to_age(m.group(1))
        hi = _grade_to_age(m.group(2))
        if lo is not None and hi is not None:
            return lo, hi + 1, all_ages

    m = re.search(r"grades?\s*([k0-9]{1,2})\s*(?:and up|\+|and older)", blob)
    if m:
        lo = _grade_to_age(m.group(1))
        if lo is not None:
            return lo, 18, all_ages

    # "age 6 & up" / "ages 8 and older" / "5+"
    m = re.search(r"ages?\s*(\d{1,2})\s*(?:&|and)?\s*(?:up|older|\+)", blob)
    if not m:
        m = re.search(r"\b(\d{1,2})\s*\+\s*(?:years?|yrs?)?\b", blob)
    if m:
        return int(m.group(1)), 18, all_ages

    # "under 5" / "under age 3" / "age 12 & under" / "12 and younger"
    m = re.search(r"under (?:age )?(\d{1,2})", blob)
    if not m:
        m = re.search(r"(?:ages?\s*)?(\d{1,2})\s*(?:&|and)?\s*(?:under|younger)\b", blob)
    if m:
        return 0, int(m.group(1)), all_ages

    # Named audiences. A source that lists several, like "Babies, Toddler,
    # Preschoolers, Elementary", means all of them, so take the union rather
    # than stopping at the first hit.
    named = [
        (r"\bnewborn|\binfant|\bbabies\b|\bbaby\b|\blapsit\b", (0, 2)),
        (r"\btoddler", (1, 3)),
        (r"\bpreschool|\bpre-k\b|\bprek\b", (3, 5)),
        (r"\bkindergarten\b", (5, 6)),
        (r"\belementary|\bschool age|\bschool-age|\bgrade school", (5, 10)),
        (r"\btween|\bmiddle school", (10, 13)),
        (r"\bteen|\bhigh school|\byoung adult\b", (13, 18)),
    ]
    hits = [(lo, hi) for pattern, (lo, hi) in named if re.search(pattern, blob)]
    if hits:
        return min(h[0] for h in hits), max(h[1] for h in hits), all_ages

    if re.search(r"\bkids?\b|\bchildren\b|\bchild\b|\byouth\b", blob):
        return 2, 12, all_ages

    if all_ages:
        return 0, 18, True
    return None, None, False


def _grade_to_age(token: str):
    token = token.strip().lower()
    if token in GRADE_TO_AGE:
        return GRADE_TO_AGE[token]
    if token.isdigit():
        return int(token) + 5
    return None


def bands_for(age_min, age_max, all_ages: bool) -> list:
    """Which age chips an event should show up under."""
    if all_ages:
        return list(AGE_BANDS.keys())
    if age_min is None and age_max is None:
        return []
    lo = 0 if age_min is None else age_min
    hi = 18 if age_max is None else age_max
    out = []
    for band, (blo, bhi) in AGE_BANDS.items():
        if lo < bhi and hi > blo:
            out.append(band)
    return out


def detect_setting(*texts: str) -> str:
    blob = _clean(" | ".join(t for t in texts if t))
    if not blob:
        return "unknown"
    outdoor = any(w in blob for w in OUTDOOR_WORDS)
    indoor = any(w in blob for w in INDOOR_WORDS)
    if outdoor and indoor:
        return "both"
    if outdoor:
        return "outdoor"
    if indoor:
        return "indoor"
    return "unknown"


def detect_cost(*texts: str):
    """Returns (cost, price_text)."""
    blob = _clean(" | ".join(t for t in texts if t))
    if not blob:
        return "unknown", ""
    money = re.search(r"\$\s?(\d+(?:\.\d{2})?)", blob)
    if money and float(money.group(1)) > 0:
        return "paid", "$" + money.group(1)
    if any(w in blob for w in FREE_WORDS):
        return "free", "Free"
    return "unknown", ""


def detect_registration(*texts: str) -> bool:
    blob = _clean(" | ".join(t for t in texts if t))
    if not blob:
        return False
    if any(w in blob for w in DROP_IN_WORDS):
        return False
    return any(w in blob for w in REGISTRATION_WORDS)


def enrich(event) -> None:
    """Fill in ages, setting, cost, and registration on an event, in place."""
    text = " | ".join([event.audience_raw, event.title, event.description, " ".join(event.categories)])

    if not event.ages:
        # The audience field is the source of truth when there is one. Falling
        # straight through to the copy is how "admission is $10 for ages 11 and
        # up" turns a toddler event into a teen event.
        lo, hi, all_ages = parse_age_range(event.audience_raw)
        if lo is None and hi is None:
            lo, hi, all_ages = parse_age_range(event.title, event.description)
        event.age_min, event.age_max, event.all_ages = lo, hi, all_ages
        event.ages = bands_for(lo, hi, all_ages)

    if event.setting == "unknown":
        event.setting = detect_setting(event.venue, event.title, event.description)

    if event.cost == "unknown":
        cost, price = detect_cost(event.price, event.description, event.title)
        event.cost = cost
        event.price = event.price or price

    if not event.registration:
        event.registration = detect_registration(text)


def is_kid_relevant(event) -> bool:
    """Filter out the adult-only noise that comes through the wide feeds."""
    if event.ages:
        return True
    if event.all_ages:
        return True
    blob = _clean(" | ".join([event.title, event.audience_raw, " ".join(event.categories)]))
    adult_only = re.search(r"\badults?\s*only\b|\b21\+|\bwine\b|\bbeer tasting\b|\bcocktail\b", blob)
    if adult_only:
        return False
    kid_hint = re.search(
        r"\bkid|\bchild|\bfamily|\bstorytime|\bstory time|\bplaygroup|\bteen\b|\btween\b"
        r"|\byouth\b|\bpuppet|\bpetting zoo\b|\bbounce\b|\bcraft\b|\bsensory\b",
        blob,
    )
    return bool(kid_hint)
