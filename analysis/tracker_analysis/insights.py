"""Summaries for the app's Insights tab, built from a transform Result.

These live here (not in the app) so the app and the notebooks compute the
same thing from the same cleaned tables. Output is plain JSON-safe dicts:
NaN becomes None, dates are ISO strings.
"""
from __future__ import annotations

import math

import pandas as pd

from .transform import Result

# Phase line: same definition as the notebook -- a centred 7-day mean of the
# day rating, needing at least 4 rated days in the window, computed both with
# and without the imputed good-day-only days (decision D02).
WINDOW = 7
MIN_DAYS = 4

# Data sufficiency: days with a real rating (not a good-day check-in) AND the
# previous night's sleep, counted within one medication regimen. About 60 is
# where a day-level sleep/behavior comparison inside one regimen starts to be
# worth trying; it is a rough planning number, not a power calculation.
SUFFICIENCY_TARGET = 60
# A drug started and stopped within this many days is a one-off trial (e.g. a
# single dose), not a new regimen, so it doesn't split the stretch.
TRIAL_MAX_DAYS = 2
# Changes to these don't start a new regimen for this count: they move the
# sleep side of a sleep -> next-day comparison (the variation it needs) rather
# than acting on daytime behavior directly. The page says so.
SUFFICIENCY_IGNORE_DRUGS = ("melatonin",)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar -> python
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _round(v, n=2):
    v = _clean(v)
    return round(v, n) if isinstance(v, float) else v


def phase_line(result: Result, partial_day: str | None = None, include_excluded: bool = False) -> dict:
    """Daily ratings, the 7-day phase line, context events and med changes.

    partial_day: a day still in progress (the app passes today). Its counts are
    incomplete, and a medication "stopped" on it only means today's doses
    aren't logged yet, so those are dropped.

    include_excluded: days inside events marked "leave out of insights" (C02)
    are blanked by default -- treated like days with nothing logged, so the
    average neither uses them nor bridges across them. They stay on the
    calendar. True plots them like any other day (for a look at what's hidden).
    """
    D = result.tables["days"].copy()
    if "day_excluded" not in D:
        D["day_excluded"] = False
        D["day_exclude_reason"] = None
    excl = D["day_excluded"].astype(bool)
    hide = excl if not include_excluded else pd.Series(False, index=D.index)
    for c in ("rating", "rating_filled"):
        D.loc[hide, c] = float("nan")
    D.loc[hide, "rating_imputed"] = False
    mean_all = D["rating_filled"].rolling(WINDOW, center=True, min_periods=MIN_DAYS).mean()
    mean_rated = D["rating"].rolling(WINDOW, center=True, min_periods=MIN_DAYS).mean()
    D["mean"] = mean_all
    D["mean_rated"] = mean_rated
    # Sleep shown on day D is the night BEFORE D (bedtime D-1 -> wake D), the
    # same alignment as transform's sleep_prev_night_hr, so a rough night sits
    # under the day that followed it. Clock values are minutes after midnight
    # of D-1: bedtime/onset are already in that frame (D03), wake gets +1440.
    # Days are consecutive, so shift(1) is "the previous evening".
    prev = D[["bedtime_min", "fell_asleep_min", "sleep_latency_min", "night_sleep_hr",
              "sleep_implausible", "night_onset_from_bedtime"]].shift(1)
    for c in ("n_entries", "n_skipped_doses"):
        if c not in D:
            D[c] = 0
    wake = D["wake_min"] + 1440

    rated = D["rating_filled"].notna()
    out = {
        "window": WINDOW, "min_days": MIN_DAYS, "partial_day": partial_day,
        "days": [], "events": [], "med_changes": [],
        "include_excluded": include_excluded,
        "summary": {"rated_days": int(D["rating"].notna().sum()),
                    "imputed_days": int(D["rating_imputed"].sum()),
                    "excluded_days": int(excl.sum()),
                    "first_day": None, "last_day": None},
    }
    if not rated.any():
        return out

    # Start at the first day with a rating: earlier rows have nothing to plot.
    D = D.loc[rated.idxmax():]
    first, last = D["date"].iloc[0], D["date"].iloc[-1]
    out["summary"].update(first_day=first, last_day=last)

    # wetting incidents by day (cleaned responses, W01/W02; excluded incidents left out, W03)
    # skipped doses by day, by name (the readout lists them)
    Z = result.tables.get("doses", pd.DataFrame())
    skipped_by_day = {}
    if len(Z) and "skipped" in Z:
        for z in Z[Z["skipped"].astype(bool)].itertuples(index=False):
            skipped_by_day.setdefault(z.entry_date, []).append(z.medication)

    W = result.tables["wetting"]
    wet_by_day = {}
    if len(W):
        W = W[~W["excluded"]].sort_values(["entry_date", "time_min"], na_position="last")
        for w in W.itertuples(index=False):
            wet_by_day.setdefault(w.entry_date, []).append({
                "time": w.incident_time[:5] or None,
                "basis": w.time_basis,                    # "happened" or "noticed"
                "basis_assumed": bool(w.time_basis_assumed),
                "response": w.response or None,
                "setting": w.setting or None,
            })

    prev = prev.loc[D.index]
    wake = wake.loc[D.index]
    # the night before a hidden day, or after one (its bedtime belongs to it), is hidden too
    hide_night = (hide | hide.shift(1, fill_value=False)).loc[D.index]
    hide = hide.loc[D.index]
    for (r, (_, p), w, h, hn) in zip(D.itertuples(index=False), prev.iterrows(), wake, hide, hide_night):
        sleep = None
        if not hn and (pd.notna(p["bedtime_min"]) or pd.notna(p["fell_asleep_min"]) or pd.notna(w)):
            sleep = {
                "bed": _clean(p["bedtime_min"]),
                "asleep": _clean(p["fell_asleep_min"]),
                "wake": _clean(w),
                "hours": _round(p["night_sleep_hr"]),
                "latency": _clean(p["sleep_latency_min"]),
                "flagged": bool(p["sleep_implausible"]) if pd.notna(p["sleep_implausible"]) else False,
                "onset_is_bedtime": bool(p["night_onset_from_bedtime"]) if pd.notna(p["night_onset_from_bedtime"]) else False,
            }
        rated_day = pd.notna(r.rating_filled) and not h
        n_neg = int(r.n_negative) if "n_negative" in D else 0
        out["days"].append({
            "date": r.date,
            "rating": _clean(r.rating_filled),
            "imputed": bool(r.rating_imputed),
            # no average ON a hidden day either: it would draw the line straight across the gap
            "mean": None if h else _round(r.mean),
            "mean_rated": None if h else _round(r.mean_rated),
            "n_negative": None if h else (int(r.n_negative) if "n_negative" in D else 0),
            "n_positive": None if h else (int(r.n_positive) if "n_positive" in D else 0),
            "max_intensity": None if h else _clean(getattr(r, "max_intensity", None)),
            "partial": r.date == partial_day,
            "excluded": bool(r.day_excluded),
            "excluded_reason": _clean(r.day_exclude_reason) if r.day_excluded else None,
            "sleep": sleep,  # the night before this day; None if nothing logged
            "sleep_left_out": bool(hn and not h),  # the night before belongs to a left-out stretch
            "wetting": None if h else wet_by_day.get(r.date, []),
            # A rated day (or good-day check-in) with no behavior entries is a
            # real zero, not a missing day (Ellyn, 2026-11-23). Today can't be.
            "zero_confirmed": bool(rated_day and n_neg == 0 and r.date != partial_day),
            "notes": None if h or not isinstance(getattr(r, "day_notes", None), str) else (r.day_notes.strip() or None),
            # logged on D with the wake time, so it describes the night before D (same as "sleep")
            "night_awakenings": None if hn else _clean(getattr(r, "night_awakenings", None)),
            "skipped_doses": None if h else skipped_by_day.get(r.date, []),
            # counts toward sufficiency: a real rating and the night before's sleep hours
            "paired": bool(not h and not hn and r.date != partial_day and pd.notna(r.rating)
                           and sleep is not None and sleep["hours"] is not None),
        })

    cd = result.tables["context_days"]
    if len(cd):
        if "exclude" not in cd:
            cd = cd.assign(exclude=False)
        ev = (cd.groupby("event_id")
                .agg(start=("date", "min"), end=("date", "max"),
                     category=("category", "first"), description=("description", "first"),
                     exclude=("exclude", "first"))
                .reset_index().sort_values(["start", "event_id"]))
        ev = ev[(ev["end"] >= first) & (ev["start"] <= last)]
        out["events"] = [{"start": r.start, "end": r.end, "category": r.category,
                          "description": _clean(r.description), "exclude": bool(r.exclude)}
                         for r in ev.itertuples(index=False)]

    mc = result.tables["med_changes"]
    if len(mc):
        mc = mc[(mc["date"] >= first) & (mc["date"] <= last)]
        if partial_day:
            mc = mc[~((mc["change"] == "stopped") & (mc["date"] >= partial_day))]
        out["med_changes"] = [{"date": r.date, "drug": r.drug, "change": r.change,
                               "from": r[3] or None, "to": r[4] or None}
                              for r in mc.itertuples(index=False)]
    out["sufficiency"] = sufficiency(out["days"], result.tables["med_changes"], partial_day)
    out["wetting_weeks"] = wetting_weeks(out["days"])
    return out


# how a wetting incident went, collapsed for the weekly bars
WET_GROUPS = {"noncompliant": "resisted", "compliant": "no_fight"}   # anything else -> "other"


def wetting_weeks(days: list[dict]) -> list[dict]:
    """Wetting incidents per Monday-Sunday week, split by response.

    A day is "logged" when it isn't left out and something was recorded for it
    (a rating or good-day check-in, a behavior entry, or a wetting incident):
    on a day nobody logged, zero incidents means nothing. Each week carries its
    logged-day count so a part-logged week isn't read as a dry one. Weeks are
    clipped to the days in `days`; today counts as not yet complete.
    """
    weeks: dict[str, dict] = {}
    for d in days:
        day = pd.Timestamp(d["date"])
        start = (day - pd.Timedelta(days=day.weekday())).date().isoformat()
        w = weeks.setdefault(start, {"start": start, "end": d["date"], "days": 0, "logged_days": 0,
                                     "excluded_days": 0, "partial": False,
                                     "resisted": 0, "no_fight": 0, "other": 0, "total": 0})
        w["end"] = d["date"]
        w["days"] += 1
        if d.get("excluded") and d.get("wetting") is None:
            w["excluded_days"] += 1
            continue
        if d.get("partial"):
            w["partial"] = True
        wet = d.get("wetting") or []
        logged = d.get("rating") is not None or bool(d.get("n_negative")) or bool(d.get("n_positive")) or bool(wet)
        if logged and not d.get("partial"):
            w["logged_days"] += 1
        for inc in wet:
            g = WET_GROUPS.get(inc.get("response") or "", "other")
            w[g] += 1
            w["total"] += 1
    for w in weeks.values():
        w["complete"] = w["days"] == 7 and w["logged_days"] == 7 and not w["partial"]
        w["per_logged_day"] = round(w["total"] / w["logged_days"], 2) if w["logged_days"] else None
    return list(weeks.values())


def sufficiency(days: list[dict], med_changes: pd.DataFrame, partial_day: str | None = None,
                target: int = SUFFICIENCY_TARGET,
                ignore_drugs: tuple[str, ...] = SUFFICIENCY_IGNORE_DRUGS) -> dict:
    """Paired days (real rating + the night before's sleep) per medication regimen.

    A regimen is the stretch between two medication-change dates. Every change
    splits it, melatonin included, except one-off trials (started and stopped
    within TRIAL_MAX_DAYS) and drugs in ignore_drugs. Left-out days count
    toward neither.
    """
    # only name ignored drugs that actually change in this data (the page mentions them)
    present = set(med_changes["drug"]) if len(med_changes) else set()
    out = {"target": target, "ignored_drugs": [d for d in ignore_drugs if d in present],
           "segments": [], "current": None, "longest": None}
    if not days:
        return out
    first, last = days[0]["date"], days[-1]["date"]
    mc = med_changes
    if len(mc):
        mc = mc[~mc["drug"].isin(ignore_drugs)]
        if partial_day:
            mc = mc[~((mc["change"] == "stopped") & (mc["date"] >= partial_day))]
        trials = set()
        for drug, g in mc.groupby("drug"):
            st = g[g["change"] == "started"]["date"]
            sp = g[g["change"] == "stopped"]["date"]
            for a in st:
                b = sp[sp >= a]
                if len(b) and (pd.Timestamp(b.min()) - pd.Timestamp(a)).days <= TRIAL_MAX_DAYS:
                    trials |= {(drug, a), (drug, b.min())}
        mc = mc[[(d, t) not in trials for d, t in zip(mc["drug"], mc["date"])]]
    cuts = sorted({d for d in mc["date"] if first < d <= last}) if len(mc) else []
    bounds = [first] + cuts
    for k, start in enumerate(bounds):
        end_excl = bounds[k + 1] if k + 1 < len(bounds) else None
        seg = [d for d in days if d["date"] >= start and (end_excl is None or d["date"] < end_excl)]
        changes = mc[mc["date"] == start] if len(mc) and k > 0 else mc.iloc[0:0] if len(mc) else None
        out["segments"].append({
            "start": start, "end": seg[-1]["date"] if seg else start,
            "days": len(seg),
            "paired": sum(1 for d in seg if d["paired"]),
            "changes": [] if changes is None else
                       [{"drug": r.drug, "change": r.change, "from": r[3] or None, "to": r[4] or None}
                        for r in changes.itertuples(index=False)],
        })
    out["current"] = out["segments"][-1]
    out["longest"] = max(out["segments"], key=lambda s: (s["paired"], s["start"]))
    return out
