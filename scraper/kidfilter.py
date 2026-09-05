"""Deciding whether an event from a general calendar belongs on a kids calendar.

Some sources only ever publish children's programming: the library, Ann Arbor
with Kids, the Observer's kids page. Those come through untouched.

Others are general community calendars. The city's calendar is mostly planning
commission work sessions. Destination Ann Arbor sells brewery tours. Even
Ann Arbor Family's calendar, which sounds like it would be safe, carries EMU
football and Friday Night Euchre, because it is drawing on a regional pool.

For those, the question has to be asked per event, and the answer has to lean
strict. The rule I want is: if I would not consider taking a five year old,
it does not belong here. A coin flip counts as a no, because the cost of a
wrong yes is a parent scrolling past a zoning hearing, and the cost of a wrong
no is one missing event that three other sources probably also carry.
"""

from __future__ import annotations

import re

# --- things that settle it on their own ----------------------------------

# Programming built for small children. Any one of these is enough.
STRONG = [
    r"\bstory ?times?\b", r"\bstory hour\b", r"\bread(?:ing)? to (?:a )?(?:dog|therapy)",
    r"\bplay ?groups?\b", r"\bplay ?dates?\b", r"\bopen play\b", r"\bfree play\b",
    r"\btoddlers?\b", r"\bpre-?schoolers?\b", r"\bpre-?school\b", r"\bbabies\b",
    r"\bbaby\b", r"\binfants?\b", r"\bnewborns?\b", r"\blittle ones\b",
    r"\bmommy (?:and|&) me\b", r"\bparent (?:and|&) (?:child|tot|baby)\b",
    r"\blittles\b", r"\bwee ones\b", r"\btiny tots\b",
    r"\bcaregiver\b", r"\bstroller\b", r"\bdiaper\b", r"\bnursing\b",
    r"\bkids?\b", r"\bchildren'?s?\b", r"\bkiddos\b", r"\byouth\b",
    r"\bpuppet\b", r"\bpetting zoo\b", r"\bbounce house\b", r"\bsplash pad\b",
    r"\bplaygrounds?\b", r"\bsensory[- ]friendly\b", r"\bsensory play\b",
    r"\bmessy play\b", r"\bmusic (?:and|&) movement\b", r"\bsing[- ]?along\b",
    r"\bkinder(?:garten|garteners)?\b", r"\belementary\b", r"\bgrades? [k1-8]\b",
    r"\bages? \d{1,2}\s*(?:-|to|–)\s*\d{1,2}\b", r"\bunder \d\b",
    r"\bmonths?\s*(?:-|to|–)\s*\d+\s*(?:years?|yrs?)\b",
    r"\bfamily\s+(?:\w+\s+)?(?:day|fun|night|storytime|story time|concert|film|"
    r"movie|festival|workshop|game|craft|dance|hour|hike|walk)\b",
    r"\bkid[- ]friendly\b", r"\bfor the whole family\b", r"\ball ages welcome\b",
    r"\bstem for\b", r"\blego\b", r"\bcraft(?:s|ing)? for\b", r"\bstorybook\b",
    r"\bnature (?:play|detectives|explorers)\b", r"\bjunior\b", r"\btot ?lot\b",
    r"\bhomeschool\b", r"\bsummer camp\b", r"\bday camp\b",
]

# Seasonal things that are unambiguously for children, and often described in
# two words with no age anywhere ("Boo Bash").
STRONG += [
    r"\btrick[- ]or[- ]treat\b", r"\bboo bash\b", r"\begg hunt\b",
    r"\bbreakfast with santa\b", r"\bsanta\b", r"\bpumpkin (?:patch|carving)\b",
    r"\bcostume (?:parade|contest)\b", r"\btouch[- ]a[- ]truck\b",
    r"\bnature play\b",
]

# Adult by default, but rescued by an explicit family or kid word, because
# "Free Family Trivia Night" is a real family event and "Trivia Night" is not.
# Checked after the strong signals, so the rescue happens on its own.
SOFT_VETO = [
    r"\btrivia night\b", r"\bbingo night\b", r"\bkaraoke\b", r"\byoga\b",
    r"\bmovie night\b", r"\bbook club\b", r"\bopen mic\b", r"\bgame night\b",
    r"\bforest therapy\b", r"\bpaint (?:and|&) sip\b",
]

# These override everything, including an explicit mention of children, because
# "Kids Eat Free at the Brewery" is not what somebody with a toddler is after
# and "Kid's Zone Volunteers" is a shift, not an outing.
VETO = [
    # Volunteer and stewardship work. The city files these on the same
    # calendar as its family programming, and they are the bulk of it.
    r"\bvolunteers?\b", r"\bworkday\b", r"\bstewardship\b", r"\bwork ?party\b",
    r"\binvasive\b", r"\bshrub cutting\b", r"\blitter cleanup\b",
    r"\briver cleanup\b", r"\badopt[- ]a[- ]park\b", r"\blove a park\b",
    r"\bmaintenance\b", r"\btrail work\b", r"\bgardening at\b",
    r"\bcleanup at\b", r"\bwoodchips\b",

    # Government process
    r"\bcity council\b", r"\bcouncil meeting\b", r"\bboard (?:of|meeting)\b",
    r"\bcommission(?:ers)? (?:meeting|work session|hearing)?\b", r"\bwork session\b",
    r"\bpublic hearing\b", r"\bzoning\b", r"\bplanning commission\b",
    r"\bcaucus\b", r"\bmillage\b", r"\bbudget (?:hearing|session|forum)\b",
    r"\bsubcommittee\b", r"\btask force\b", r"\bcity administrator\b",
    r"\badvisory (?:board|committee|commission)\b", r"\bannual meeting\b",
    r"\bward \d\b", r"\bboard of (?:review|education|trustees)\b",
    # Adults only, or effectively so
    r"\b21\+", r"\b18\+", r"\bages 21\b", r"\badults? only\b", r"\bfor adults\b",
    r"\bhappy hour\b", r"\bbar crawl\b", r"\bpub (?:crawl|quiz|night)\b",
    r"\bwine (?:tasting|night|down|walk)\b", r"\bbeer (?:tasting|garden|fest)\b",
    r"\bbrewery\b", r"\bbrewing (?:co|company)\b", r"\btap ?room\b",
    r"\bdistiller", r"\bcocktail\b", r"\bspeakeasy\b", r"\bcannabis\b",
    r"\bdispensary\b", r"\bcasino\b", r"\bpoker\b",
    r"\bburlesque\b", r"\bdrag brunch\b",
    r"\bnightclub\b", r"\bafter dark\b", r"\bspeed dating\b", r"\bsingles\b",
    r"\beuchre\b", r"\bpoetry slam\b",
    # Professional and academic
    r"\bnetworking\b", r"\bjob fair\b", r"\bcareer fair\b", r"\bhiring event\b",
    r"\bprofessional development\b", r"\bcontinuing education\b",
    r"\bdissertation\b", r"\bcolloquium\b", r"\bsymposium\b", r"\bkeynote\b",
    r"\bguest lecture\b", r"\bseminar\b", r"\bfaculty\b", r"\bpostdoc\b",
    r"\bgrand rounds\b", r"\bthesis defense\b", r"\bconference\b",
    r"\bchamber of commerce\b", r"\bcity ?wide cleanup\b",
    # Grown-up social and health
    r"\bsupport group\b", r"\bgrief\b", r"\bcaregiver support\b",
    r"\bblood drive\b", r"\bfundraiser (?:dinner|gala)\b", r"\bgala\b",
    r"\bauction\b", r"\bsilent auction\b",
    r"\bcall for (?:art|artists|entries|submissions)\b", r"\bapplication deadline\b",
    r"\bregistration (?:opens|deadline)\b", r"\baudition\b",
    # College sport is not a toddler outing
    r"\bfootball\b", r"\bwolverines\b", r"\bnittany\b", r"\btailgate\b",
    r"\bhockey vs\b", r"\bbasketball vs\b", r"\bvs\.? [A-Z]",
]

STRONG_RE = [re.compile(p, re.I) for p in STRONG]
VETO_RE = [re.compile(p, re.I) for p in VETO]
SOFT_VETO_RE = [re.compile(p, re.I) for p in SOFT_VETO]

# Checked against the title only. "For children 2-5 years of age and an adult"
# means a grown-up has to come with them, which is the opposite of an adults
# only event, so this word can never be judged from the description.
TITLE_VETO_RE = [re.compile(p, re.I) for p in (
    r"\badults?\b", r"\bgrown[- ]ups?\b", r"\bseniors?\b", r"\b55\+",
    r"\bmeeting\b", r"\bwebinar\b", r"\bopen house\b", r"\bforum\b",
)]

# "Family" on its own is the weakest possible signal. A brewery calls itself
# family friendly. It is worth something, but never enough by itself.
WEAK = [re.compile(p, re.I) for p in (
    r"\bfamil(?:y|ies)\b", r"\ball ages\b", r"\bfree admission\b",
    r"\bfestival\b", r"\bfarmers.? market\b", r"\bparade\b", r"\bcraft\b",
    r"\bmuseum\b", r"\bnature\b", r"\blibrary\b", r"\bstory\b", r"\bpumpkin\b",
    r"\bpetting\b", r"\bzoo\b", r"\bhayride\b", r"\bice cream\b",
)]

# Venues where practically everything on offer is for small children, which
# rescues a thinly described listing that would otherwise fall through.
KID_VENUE = [re.compile(p, re.I) for p in (
    r"\blibrary\b", r"\bhands[- ]on museum\b", r"\bleslie science\b",
    r"\bnature center\b", r"\bchildren'?s\b", r"\bwe rock the spectrum\b",
    r"\blaunch trampoline\b", r"\bjump\b", r"\bplay ?place\b", r"\bkindermusik\b",
    r"\bcosto (?:nature|farm)\b", r"\bdomino'?s farms\b", r"\bpetting farm\b",
    r"\btoy\b", r"\bpreschool\b", r"\belementary school\b",
)]


def blob(event) -> str:
    return " ".join(str(x or "") for x in (
        getattr(event, "title", ""),
        getattr(event, "audience_raw", ""),
        getattr(event, "description", ""),
        " ".join(getattr(event, "categories", []) or []),
    ))


def verdict(event) -> tuple:
    """Return (keep, why). The why is for the log, not the page.

    Order matters. Hard vetoes go first so no amount of kid vocabulary rescues
    a beer garden. Strong signals go next so they can rescue something from a
    soft veto. Soft vetoes come after that, and the weak signals last.
    """
    text = blob(event)
    venue = str(getattr(event, "venue", "") or "")

    # Signing up to spread woodchips at a playground is a different activity
    # from taking a four year old to the playground, and only one of them has
    # a "Choose Your Shift" section.
    if getattr(event, "volunteer", False):
        return False, "volunteer signup, not an outing"

    title = str(getattr(event, "title", "") or "")
    titled = next((p.pattern for p in TITLE_VETO_RE if p.search(title)), None)
    if titled:
        return False, f"the title says who it is for: {titled}"

    vetoed = next((p.pattern for p in VETO_RE if p.search(text)), None)
    if vetoed:
        return False, f"veto: {vetoed}"

    # An explicit age range that reaches children is the best evidence there is.
    age_min = getattr(event, "age_min", None)
    age_max = getattr(event, "age_max", None)
    if age_min is not None and age_min <= 12:
        return True, f"stated ages from {age_min}"
    if age_max is not None and age_max <= 12:
        return True, f"stated ages up to {age_max}"

    strong = next((p.pattern for p in STRONG_RE if p.search(text)), None)
    if strong:
        return True, f"kid programming: {strong}"

    soft = next((p.pattern for p in SOFT_VETO_RE if p.search(text)), None)
    if soft:
        return False, f"adult by default and nothing said otherwise: {soft}"

    # A weak signal at a venue that only does kid programming is enough.
    # A weak signal on its own is a coin flip, and a coin flip is a no.
    weak = sum(1 for p in WEAK if p.search(text))
    if weak and any(p.search(venue) for p in KID_VENUE):
        return True, "kid venue plus a family signal"
    if weak >= 3:
        return True, f"{weak} family signals"

    return False, "no clear signal that this is for children"


def filter_mixed(events: list, mixed_sources: set) -> tuple:
    """Keep everything from kid-only sources, gate everything else.

    Returns (kept, dropped) so the run can report how much a noisy source is
    actually contributing before its noise.
    """
    kept, dropped = [], []
    for event in events:
        if getattr(event, "source", "") not in mixed_sources:
            kept.append(event)
            continue
        ok, why = verdict(event)
        (kept if ok else dropped).append(event)
        if not ok:
            event.drop_reason = why
    return kept, dropped
