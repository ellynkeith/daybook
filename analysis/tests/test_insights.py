"""Tests on synthetic data only -- this repo is public, never put real export rows here."""
import json
import unittest

import pandas as pd

from tracker_analysis import Overrides, Params, build, load_tables, phase_line
from test_transform import C_COLS, D_COLS, E_COLS, M_COLS, W_COLS, df


def raw(ratings, doses=(), sleep=None):
    """Days from 2026-03-01 with the given ratings ("" = unrated, "g" = good-day only).
    sleep: {day_index: (wake, bedtime, fell_asleep)} as "HH:MM:SS" or ""."""
    days = []
    for i, r in enumerate(ratings):
        d = f"2026-03-{i + 1:02d}"
        wk, bed, fell = (sleep or {}).get(i, ("", "", ""))
        days.append([d, "true" if r == "g" else "", "" if r in ("", "g") else r, "", wk, bed, fell, "", "", "", ""])
    return {
        "entries": df([["1", "2026-03-02", "09:00:00", "defiant", "home", "", "3", "", "", "A",
                        "2026-03-02 14:00:00+00:00"]], E_COLS),
        "daily": df(days, D_COLS),
        "wetting_incidents": df([], W_COLS),
        "context_events": df([["1", "2026-03-03", "2026-03-04", "illness", "cold", "2026-03-03 00:00:00+00:00"],
                              ["2", "2026-02-01", "", "illness", "", "2026-02-01 00:00:00+00:00"]], C_COLS),
        "medication_doses": df(list(doses), M_COLS),
    }


class PhaseLineTests(unittest.TestCase):
    def phase(self, ratings, through, partial=None, doses=(), sleep=None):
        res = build(raw(ratings, doses, sleep), Overrides(), Params(through=through))
        return phase_line(res, partial_day=partial)

    def test_matches_centred_rolling_mean(self):
        ratings = ["2", "3", "g", "5", "1", "", "4", "3"]
        out = self.phase(ratings, "2026-03-08")
        filled = pd.Series([2, 3, 4, 5, 1, None, 4, 3], dtype=float)
        expect = filled.rolling(7, center=True, min_periods=4).mean().round(2)
        got = [d["mean"] for d in out["days"]]
        self.assertEqual(got, [None if pd.isna(v) else v for v in expect])

    def test_with_and_without_imputed(self):
        out = self.phase(["g", "g", "g", "2", "g", "g", "g"], "2026-03-07")
        mid = out["days"][3]
        self.assertEqual(mid["mean"], round((4 * 6 + 2) / 7, 2))
        self.assertIsNone(mid["mean_rated"])  # one real rating < 4 needed
        self.assertTrue(out["days"][0]["imputed"])
        self.assertEqual(out["summary"], {"rated_days": 1, "imputed_days": 6, "excluded_days": 0,
                                          "first_day": "2026-03-01", "last_day": "2026-03-07"})

    def test_starts_at_first_rating_and_clips_events(self):
        out = self.phase(["", "", "3", "3"], "2026-03-04")
        self.assertEqual(out["days"][0]["date"], "2026-03-03")
        self.assertEqual(out["events"], [{"start": "2026-03-03", "end": "2026-03-04",
                                          "category": "illness", "description": "cold", "exclude": False}])

    def test_no_ratings_is_empty_not_error(self):
        out = self.phase(["", ""], "2026-03-02")
        self.assertEqual(out["days"], [])
        json.dumps(out)

    def test_partial_day_drops_spurious_stop(self):
        doses = [["1", "2026-03-01", "08:00:00", "", "drugA 1mg", "false", "", "2026-03-01 13:00:00+00:00"],
                 ["2", "2026-03-02", "08:00:00", "", "drugA 1mg", "false", "", "2026-03-02 13:00:00+00:00"]]
        out = self.phase(["3", "3", "3"], "2026-03-03", partial="2026-03-03", doses=doses)
        self.assertEqual(out["med_changes"], [])  # today's dose just isn't logged yet
        self.assertTrue(out["days"][-1]["partial"])
        out = self.phase(["3", "3", "3"], "2026-03-03", doses=doses)
        self.assertEqual([m["change"] for m in out["med_changes"]], ["stopped"])

    def test_sleep_is_the_night_before(self):
        sleep = {0: ("", "21:00:00", "21:30:00"),          # evening of day 1
                 1: ("07:00:00", "00:30:00", ""),          # wake day 2; bed after midnight, no fell-asleep
                 2: ("06:00:00", "", "")}                  # wake day 3
        out = self.phase(["3", "3", "3"], "2026-03-03", sleep=sleep)
        d1, d2, d3 = out["days"]
        self.assertIsNone(d1["sleep"])                    # nothing logged the night before day 1
        self.assertEqual(d2["sleep"], {"bed": 1260, "asleep": 1290, "wake": 1860, "hours": 9.5,
                                       "latency": 30, "flagged": False, "onset_is_bedtime": False})
        self.assertEqual(d3["sleep"]["bed"], 1470)          # 00:30 sits after midnight
        self.assertTrue(d3["sleep"]["onset_is_bedtime"])
        self.assertEqual(d3["sleep"]["hours"], 5.5)        # 00:30 -> 06:00

    def test_counts_and_json_safe(self):
        out = self.phase(["3", "3"], "2026-03-02")
        self.assertEqual(out["days"][1]["n_negative"], 1)
        self.assertEqual(out["days"][1]["max_intensity"], 3)
        json.dumps(out)


class LoadAndOverrideTests(unittest.TestCase):
    def test_load_tables_reads_bom_csv_as_strings(self):
        t = load_tables({"daily": "﻿entry_date,day_rating\n2026-03-01,\n".encode("utf-8")})
        self.assertEqual(list(t["daily"].columns), ["entry_date", "day_rating"])
        self.assertEqual(t["daily"].iloc[0]["day_rating"], "")
        self.assertTrue(t["entries"].empty)

    def test_from_dict(self):
        o = Overrides.from_dict({"_comment": "x", "exclude_entries": {7: "why"}}, source="env")
        self.assertEqual(o.exclude_entries, {"7": "why"})
        self.assertEqual(o.source, "env")
        with self.assertRaises(ValueError):
            Overrides.from_dict({"exclude_entry": {}})


if __name__ == "__main__":
    unittest.main()


class ExcludedPeriodTests(unittest.TestCase):
    """Context events marked "leave out of insights" (step C02)."""
    CX = C_COLS[:5] + ["exclude_from_insights", "created_at"]

    def build(self, ratings, sleep=None, flag="true"):
        r = raw(ratings, sleep=sleep)
        r["context_events"] = df([["1", "2026-03-05", "2026-03-07", "visitors/travel", "trip", flag,
                                   "2026-03-01 00:00:00+00:00"]], self.CX)
        return build(r, Overrides(), Params(through=f"2026-03-{len(ratings):02d}"))

    def test_transform_flags_but_keeps_data(self):
        res = self.build(["3"] * 10)
        days = res.tables["days"].set_index("date")
        self.assertEqual(days.index[days["day_excluded"]].tolist(), ["2026-03-05", "2026-03-06", "2026-03-07"])
        self.assertEqual(days.loc["2026-03-06", "day_exclude_reason"], "trip")
        self.assertEqual(days.loc["2026-03-06", "rating"], 3)  # kept in the table
        self.assertEqual(next(s for s in res.log if s.id == "C02").rows, 3)

    def test_unflagged_and_old_exports_exclude_nothing(self):
        self.assertFalse(self.build(["3"] * 10, flag="false").tables["days"]["day_excluded"].any())
        old = build(raw(["3"] * 5), Overrides(), Params(through="2026-03-05"))  # no exclude column at all
        self.assertFalse(old.tables["days"]["day_excluded"].any())

    def test_phase_line_blanks_days_and_never_bridges(self):
        # high before the trip, low after: a window must not average across the gap
        ratings = ["5", "5", "5", "5", "2", "2", "2", "1", "1", "1", "1"]
        out = phase_line(self.build(ratings))
        d = {x["date"]: x for x in out["days"]}
        for day in ("2026-03-05", "2026-03-06", "2026-03-07"):
            self.assertIsNone(d[day]["rating"])
            self.assertIsNone(d[day]["n_negative"])
            self.assertTrue(d[day]["excluded"])
            self.assertEqual(d[day]["excluded_reason"], "trip")
        # no average on the hidden days themselves, so the line can't cross the gap
        self.assertIsNone(d["2026-03-07"]["mean"])
        # 03-08's window (03-05..03-11) reaches back into the trip but only uses days after it
        self.assertEqual(d["2026-03-08"]["mean"], 1.0)
        self.assertEqual(d["2026-03-04"]["mean"], round((5 * 4) / 4, 2))
        self.assertEqual(out["summary"]["excluded_days"], 3)
        self.assertEqual(out["summary"]["rated_days"], 8)
        self.assertTrue(out["events"][0]["exclude"])

    def test_include_excluded_shows_everything(self):
        out = phase_line(self.build(["5"] * 4 + ["2"] * 3 + ["1"] * 4), include_excluded=True)
        d = {x["date"]: x for x in out["days"]}
        self.assertEqual(d["2026-03-06"]["rating"], 2)
        self.assertTrue(d["2026-03-06"]["excluded"])  # still marked, just plotted
        self.assertEqual(out["summary"]["rated_days"], 11)

    def test_night_after_excluded_day_is_hidden(self):
        sleep = {i: ("07:00:00", "21:00:00", "21:30:00") for i in range(10)}
        d = {x["date"]: x for x in phase_line(self.build(["3"] * 10, sleep=sleep))["days"]}
        self.assertIsNone(d["2026-03-06"]["sleep"])   # night inside the trip
        self.assertIsNone(d["2026-03-08"]["sleep"])   # bedtime on 03-07 was still on the trip
        self.assertIsNotNone(d["2026-03-09"]["sleep"])
        self.assertIsNone(d["2026-03-05"]["sleep"])     # ends on the trip's first morning
        self.assertIsNotNone(d["2026-03-04"]["sleep"])  # last night before the trip
