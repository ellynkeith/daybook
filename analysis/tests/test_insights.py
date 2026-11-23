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

    def test_wetting_by_day(self):
        r = raw(["3", "3", "3"])
        r["wetting_incidents"] = df([
            ["1", "2026-03-02", "15:30:00", "true", "school", "noncompliant", "", "2026-03-02 21:00:00+00:00"],
            ["2", "2026-03-02", "09:00:00", "", "home", "compliant", "", "2026-03-02 15:00:00+00:00"],
            ["3", "2026-03-03", "", "", "home", "not observed", "", "2026-03-03 15:00:00+00:00"],
            ["4", "2026-03-03", "10:00:00", "false", "home", "compliant", "", "2026-03-03 15:00:00+00:00"]], W_COLS)
        res = build(r, Overrides(wetting_exclude={"4": "overnight"}), Params(through="2026-03-03"))
        d = {x["date"]: x for x in phase_line(res)["days"]}
        self.assertEqual(d["2026-03-01"]["wetting"], [])
        self.assertEqual([w["time"] for w in d["2026-03-02"]["wetting"]], ["09:00", "15:30"])  # in time order
        self.assertEqual(d["2026-03-02"]["wetting"][1],
                         {"time": "15:30", "basis": "noticed", "basis_assumed": False,
                          "response": "noncompliant", "setting": "school"})
        self.assertTrue(d["2026-03-02"]["wetting"][0]["basis_assumed"])     # unknown -> noticed (W02)
        self.assertEqual(len(d["2026-03-03"]["wetting"]), 1)                 # id 4 excluded (W03)
        self.assertIsNone(d["2026-03-03"]["wetting"][0]["time"])

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
            self.assertIsNone(d[day]["wetting"])
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
        self.assertTrue(d["2026-03-08"]["sleep_left_out"])  # so the readout can say why
        self.assertFalse(d["2026-03-09"]["sleep_left_out"])
        self.assertIsNotNone(d["2026-03-09"]["sleep"])
        self.assertIsNone(d["2026-03-05"]["sleep"])     # ends on the trip's first morning
        self.assertIsNotNone(d["2026-03-04"]["sleep"])  # last night before the trip


def dose(i, day, meds, skipped="false"):
    return [str(i), day, "08:00:00", "", meds, skipped, "", f"{day} 13:00:00+00:00"]


class DayExtrasTests(unittest.TestCase):
    def test_zero_confirmed(self):
        # 03-02 has the one behavior entry; 03-03 good-day only; 03-04 unrated; 03-05 today
        res = build(raw(["3", "3", "g", "", "3"]), Overrides(), Params(through="2026-03-05"))
        d = phase_line(res, partial_day="2026-03-05")["days"]
        self.assertEqual([x["zero_confirmed"] for x in d], [True, False, True, False, False])

    def test_notes_awakenings_and_skipped(self):
        r = raw(["3", "3", "3"])
        r["daily"].loc[0, "day_notes"] = "  quiet day "
        r["daily"].loc[1, "day_notes"] = "   "
        r["daily"].loc[1, "night_awakenings"] = "2"
        r["medication_doses"] = df([dose(1, "2026-03-01", "drugA 1mg"),
                                    dose(2, "2026-03-02", "drugA 1mg", skipped="true"),
                                    dose(3, "2026-03-03", "drugA 1mg")], M_COLS)
        d = phase_line(build(r, Overrides(), Params(through="2026-03-03")))["days"]
        self.assertEqual([x["notes"] for x in d], ["quiet day", None, None])
        self.assertEqual([x["night_awakenings"] for x in d], [None, 2, None])
        self.assertEqual(d[1]["skipped_doses"], ["drugA 1mg"])
        self.assertEqual(d[0]["skipped_doses"], [])
        json.dumps(d)


class SufficiencyTests(unittest.TestCase):
    def build(self, ratings, doses):
        sleep = {i: ("07:00:00", "21:00:00", "21:30:00") for i in range(len(ratings))}
        n = len(ratings)
        res = build(raw(ratings, doses, sleep), Overrides(), Params(through=f"2026-03-{n:02d}"))
        return phase_line(res)

    def test_paired_needs_real_rating_and_night_before(self):
        out = self.build(["3", "3", "g", "", "4"], [])
        # day 1 has no night before; day 3 is good-day only; day 4 unrated
        self.assertEqual([x["paired"] for x in out["days"]], [False, True, False, False, True])
        s = out["sufficiency"]
        self.assertEqual(s["target"], 60)
        self.assertEqual(s["ignored_drugs"], [])   # no melatonin in this data: nothing to mention
        self.assertEqual([(g["start"], g["paired"]) for g in s["segments"]], [("2026-03-01", 2)])

    def test_segments_split_on_changes_but_not_melatonin_or_trials(self):
        doses = []
        for i in range(1, 9):
            day = f"2026-03-{i:02d}"
            doses.append(dose(len(doses) + 1, day, "drugA 1mg" if i < 5 else "drugA 2mg"))   # change 03-05
            doses.append(dose(len(doses) + 1, day, "melatonin 1mg" if i < 3 else "melatonin 2mg"))  # ignored
        doses.append(dose(len(doses) + 1, "2026-03-07", "drugB 5mg"))  # one-day trial: started, stopped next day
        out = self.build(["3"] * 8, doses)
        drugs = {m["drug"] for m in out["med_changes"]}
        self.assertIn("melatonin", drugs)   # still shown on the chart
        self.assertIn("drugB", drugs)
        s = out["sufficiency"]
        self.assertEqual([(g["start"], g["end"], g["days"], g["paired"]) for g in s["segments"]],
                         [("2026-03-01", "2026-03-04", 4, 3), ("2026-03-05", "2026-03-08", 4, 4)])
        self.assertEqual([c["drug"] for c in s["segments"][1]["changes"]], ["drugA"])
        self.assertEqual(s["current"]["start"], "2026-03-05")
        self.assertEqual(s["longest"]["start"], "2026-03-05")
        self.assertEqual(s["ignored_drugs"], ["melatonin"])
        json.dumps(out)


class WettingWeeksTests(unittest.TestCase):
    def test_weeks_split_by_response_and_count_logged_days(self):
        # 2026-03-02 is a Monday. Ratings on 03-01..03-10, 03-05 unrated with nothing logged.
        r = raw(["3", "3", "3", "3", "", "3", "3", "3", "3", "3"])
        r["wetting_incidents"] = df([
            ["1", "2026-03-01", "10:00:00", "false", "home", "noncompliant", "", "2026-03-01 15:00:00+00:00"],
            ["2", "2026-03-03", "10:00:00", "false", "home", "compliant", "", "2026-03-03 15:00:00+00:00"],
            ["3", "2026-03-03", "15:00:00", "true", "school", "not observed", "", "2026-03-03 21:00:00+00:00"],
            ["4", "2026-03-09", "10:00:00", "false", "home", "compliant", "", "2026-03-09 15:00:00+00:00"],
            ["5", "2026-03-10", "10:00:00", "false", "home", "noncompliant", "", "2026-03-10 15:00:00+00:00"]], W_COLS)
        res = build(r, Overrides(wetting_exclude={"5": "overnight"}), Params(through="2026-03-10"))
        weeks = phase_line(res, partial_day="2026-03-10")["wetting_weeks"]
        self.assertEqual([w["start"] for w in weeks], ["2026-02-23", "2026-03-02", "2026-03-09"])
        sun, wk, last = weeks
        self.assertEqual((sun["days"], sun["resisted"], sun["total"]), (1, 1, 1))   # clipped to the one day shown
        self.assertEqual((wk["resisted"], wk["no_fight"], wk["other"], wk["total"]), (0, 1, 1, 2))
        self.assertEqual((wk["days"], wk["logged_days"]), (7, 6))                    # 03-05: nothing logged
        self.assertFalse(wk["complete"])
        self.assertEqual(wk["per_logged_day"], round(2 / 6, 2))
        self.assertEqual(last["total"], 1)        # id 5 excluded (W03)
        self.assertTrue(last["partial"])          # today is in it
        self.assertEqual(last["logged_days"], 1)  # today doesn't count yet

    def test_left_out_days_are_not_logged_days(self):
        r = raw(["3"] * 7 + ["3"] * 7)  # 03-01 (Sun) .. 03-14
        r["context_events"] = df([["1", "2026-03-03", "2026-03-05", "visitors/travel", "trip", "true",
                                   "2026-03-03 00:00:00+00:00"]], C_COLS[:5] + ["exclude_from_insights", "created_at"])
        weeks = phase_line(build(r, Overrides(), Params(through="2026-03-14")))["wetting_weeks"]
        wk = weeks[1]
        self.assertEqual((wk["excluded_days"], wk["logged_days"]), (3, 4))
        json.dumps(weeks)
