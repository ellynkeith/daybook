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
    return out
