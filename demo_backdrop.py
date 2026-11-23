"""Generated backdrop for the demo login: about two months of made-up days
behind the hand-written demo rows in demo_store.py, so every Insights chart
has something to show.

Everything here is invented. A fixed random seed makes it the same on every
server start; dates are relative to today so it always looks recent. It
covers days FIRST_DAY..LAST_DAY ago (the hand-written rows own 0..8 and a few
older days) and never overwrites a day the hand-written seed already has.

What's planted, oldest first, so the charts have a story to show:
  70-50 days ago  a rough stretch (lower ratings, more entries, longer to fall asleep)
  56-52           fall break (no school)
  49-36           a good stretch, with some "good day"-only check-ins
  35-29           a trip, marked "leave out of insights" (good-day check-ins only)
  28              an afternoon medication added (a medication change)
  28-9            in between, drifting a little rougher, with a dip for the
                  hand-written cold (12-10 days ago)
Wetting clusters in the afternoon, mostly noticed at school pickup.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

FIRST_DAY, LAST_DAY = 70, 9
SEED = 20261123

ROUGH, BREAK, GOOD, TRIP, PM_MED_START = (70, 50), (56, 52), (49, 36), (35, 29), 28


def _in(d, span):
    hi, lo = span
    return lo <= d <= hi


def _phase_mean(d):
    if _in(d, ROUGH):
        return 2.7
    if _in(d, GOOD):
        return 3.9
    if 10 <= d <= 12:
        return 2.8                                # the hand-written "cold" context event
    if d <= PM_MED_START:
        return 3.6 - (PM_MED_START - d) * 0.025   # slow drift down toward the hand-written week
    return 3.3


def _poisson(rng, lam):
    """Small Poisson draw (Knuth); lam is at most ~3 here."""
    import math
    k, p, limit = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _clock(minutes):
    minutes = int(round(minutes)) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


NOTES = {
    "angry/irritable": ["Snapped at everyone after school, calmed down after a snack.",
                        "Melted down when the game ended; needed a few minutes alone."],
    "argumentative/defiant": ["Argued every step of the bedtime routine.",
                              "Refused to put shoes on; negotiated for ten minutes."],
    "impulsive": ["Blurted out answers and grabbed a sibling's toy.",
                  "Ran ahead in the parking lot despite reminders."],
    "inattentive": ["Needed many re-prompts to finish getting dressed.",
                    "Lost track of homework halfway through."],
    "hyperactive/restless": ["Bouncing off the furniture all evening.",
                             "Couldn't sit through dinner."],
    "vindictive": ["Knocked over a sibling's tower on purpose after losing a game."],
    "good behavior": ["Handled a change of plans calmly.", "Shared without being asked."],
}


def backdrop(today: date, taken_dates: set[str]) -> dict:
    """Rows in the demo store's own shapes, keyed by table. taken_dates: dates
    (ISO) the hand-written seed already has a daily log for -- left alone."""
    rng = random.Random(SEED)
    out = {"entries": [], "daily": [], "wetting": [], "doses": [], "events": []}
    for d in range(FIRST_DAY, LAST_DAY - 1, -1):
        day = today - timedelta(days=d)
        iso = day.isoformat()
        weekend = day.weekday() >= 5
        school = not weekend and not _in(d, BREAK) and not _in(d, TRIP)
        trip = _in(d, TRIP)
        mean = _phase_mean(d)
        # older days may have the odd gap; the last 30 stay complete so the
        # "what's missing" view only shows the hand-written gaps
        if d > 30 and not trip and rng.random() < 0.04:
            continue

        # ---- medications (taken on the trip too: meds don't stop for travel)
        am = 7 * 60 + 50 + rng.randint(-5, 15) if school else 8 * 60 + 20 + rng.randint(-10, 30)
        out["doses"].append(dict(entry_date=iso, taken_time=_clock(am), medications=["am meds", "vitamin d"],
                                 notes=None, skipped=False, time_confirmed=True))
        if d <= PM_MED_START:
            if rng.random() < 0.05:
                out["doses"].append(dict(entry_date=iso, taken_time=None, medications=["pm meds"],
                                         notes="Fell asleep in the car, skipped it.", skipped=True, time_confirmed=None))
            else:
                out["doses"].append(dict(entry_date=iso, taken_time=_clock(15 * 60 + 30 + rng.randint(-10, 15)),
                                         medications=["pm meds"], notes=None, skipped=False, time_confirmed=True))
        if iso in taken_dates:
            continue

        # ---- the day: trip days get only a "good day" check-in, like a parent away from the app
        if trip:
            out["daily"].append(dict(entry_date=iso, good_day=True, day_rating=None, day_notes=None,
                                     wake_time=None, bedtime=None, fell_asleep_time=None, night_awakenings=None))
            continue
        rating = max(1, min(5, round(rng.gauss(mean, 0.7))))
        good_only = rating >= 4 and rng.random() < 0.3
        rough = _in(d, ROUGH)
        bed = 20 * 60 + 40 + rng.randint(-15, 35) + (20 if weekend else 0)
        latency = max(5, rng.gauss(38 if rough else 24, 10))
        wake = (6 * 60 + 50 if school else 7 * 60 + 25) + rng.randint(-12, 20)
        out["daily"].append(dict(
            entry_date=iso, good_day=True if good_only else None, day_rating=None if good_only else rating,
            day_notes=rng.choice([None] * 9 + ["Busy day, but she rolled with it.", "Tired and teary by dinner."]),
            wake_time=_clock(wake), bedtime=_clock(bed),
            fell_asleep_time=_clock(bed + latency) if rng.random() < 0.85 else None,
            night_awakenings=rng.choice([0, 0, 0, 0, 1] + ([1, 2] if rough else []))))

        # ---- behavior entries: more, and more intense, on rougher days
        rate = {1: 2.4, 2: 1.7, 3: 0.9, 4: 0.3, 5: 0.1}[rating] + (0.4 if rough else 0)
        n = 0 if good_only else _poisson(rng, rate)
        for _ in range(n):
            cat = rng.choices(list(NOTES)[:-1], weights=[4, 5, 2, 2, 2, 1])[0]
            cats = [cat] + ([rng.choice(["argumentative/defiant", "angry/irritable"])] if rng.random() < 0.35 else [])
            cats = list(dict.fromkeys(cats))
            hour = rng.choices([7, 10, 15, 17, 19], weights=[2, 1 if school else 2, 4, 4, 3])[0]
            setting = ("school" if school and 9 <= hour < 15 else
                       "transitions" if hour in (7, 15) else rng.choice(["home", "home", "public"]))
            out["entries"].append(dict(
                entry_date=iso, entry_time=_clock(hour * 60 + rng.randint(0, 50)), categories=cats, setting=setting,
                duration_minutes=rng.choice([None, 5, 10, 15, 20, 30]),
                intensity=max(1, min(5, round(rng.gauss(4.2 - rating * 0.5 + (0.5 if rough else 0), 0.8)))),
                situations=rng.sample(["told no", "asked to transition off preferred activity", "non-preferred task demand",
                                       "sibling conflict", "unexpected change in plans", "waiting/turn-taking"],
                                      k=rng.choice([0, 1, 1])),
                notes=rng.choice(NOTES[cat]),
                logged_by="Demo Teacher" if setting == "school" else rng.choice(["Demo Parent", "Demo Parent", "Demo Babysitter"])))
        if rating >= 4 and rng.random() < 0.2:
            out["entries"].append(dict(
                entry_date=iso, entry_time=_clock(17 * 60 + rng.randint(0, 120)), categories=["good behavior"],
                setting="home", duration_minutes=None, intensity=None,
                situations=[rng.choice(["sibling conflict", "unexpected change in plans", "told no"])],
                notes=rng.choice(NOTES["good behavior"]), logged_by="Demo Parent"))

        # ---- wetting: mostly afternoons, often only noticed at school pickup
        for _ in range(sum(rng.random() < p for p in [0.45, 0.15] + ([0.15] if rough else []))):
            if school and rng.random() < 0.6:
                t, setting, approx = 15 * 60 + rng.randint(0, 40), "school", True
                response = rng.choice(["not observed", "not observed", "compliant"])
            else:
                t = rng.choice([10 * 60, 14 * 60, 16 * 60, 18 * 60]) + rng.randint(0, 59)
                setting, approx = rng.choice(["home", "home", "transitions", "public"]), rng.random() < 0.3
                response = rng.choices(["compliant", "noncompliant", "other"], weights=[5, 3 if rough else 1, 1])[0]
            out["wetting"].append(dict(entry_date=iso, incident_time=_clock(t), setting=setting,
                                       response=response, notes=None, time_approximate=approx))

    def ev(start, end, category, description, exclude=False):
        out["events"].append(dict(start_date=(today - timedelta(days=start)).isoformat(),
                                  end_date=(today - timedelta(days=end)).isoformat() if end is not None else None,
                                  category=category, description=description, exclude_from_insights=exclude))
    ev(*BREAK, "school break/day off", "Fall break")
    ev(*TRIP, "visitors/travel", "Visiting grandparents out of state", exclude=True)
    ev(PM_MED_START, None, "medication change", "Added an afternoon med")
    return out
