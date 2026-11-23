# Decisions

The non-obvious calls, and why. Newest last.

**The repo is public; the data isn't.** Only code and generic rules are committed. Exports, record-specific analysis overrides and notebooks live in the gitignored `Claude outputs/` folder; on the server, overrides come from an environment variable. Demo data and screenshots are made up.

**Retire, don't delete** (categories, situations, medications). Old entries keep their tags and stay filterable; deleting would rewrite history.

**A dose change is a new medication** ("Methylphenidate 10mg" → "…18mg"), not a rename, so past doses stay accurate.

**Missing is not zero.** A blank sleep time, intensity or wake-up time means "not recorded" and is never filled in by the analysis. A skipped dose is logged explicitly; a day with no doses is missing data. Night wakings have an explicit "None" for the same reason.

**Times are when it happened, not when it was logged.** The entry time used to default to "now"; it no longer does, and older entries saved within a few minutes of their logged time are flagged in analysis. Wetting times say whether they're when it happened or when it was noticed; unknown is treated as "noticed", which can only make an incident look later, never earlier.

**Copied times are unconfirmed.** "Same as previous day" copies yesterday's dose times, so they're marked "~" until someone confirms them. Dose-timing analysis needs to know which times were actually observed.

**A "good day" check-in counts as a 4**, because dropping those days would tilt everything toward bad days. Every average is shown both with and without them.

**A rated day with no behavior entries is a real zero** (2026-11). The chart marks it, so it looks different from a day nobody logged. The "nothing more to add" button means something else (stop flagging missing sleep or meds) and isn't used for this.

**Sleep belongs to the day after.** The night shown on a day is the one before it (bedtime the evening before → waking that morning), so a rough night lines up with the day it affected.

**Leaving days out is decided by reason, never by the numbers** (2026-11). Only days covered by a context event marked "leave out of Insights" (a trip abroad, say) are excluded, decided when the event is logged. Left-out days stay on the calendar as a gap, so rolling averages never join across it.

**Fix wrong records in the app; use overrides for right records that shouldn't count** (2026-11). A wrong date gets edited. An overnight accident, or a day summary logged as an entry, stays in the log and is left out of the analysis by an override, which is reversible and leaves the record alone. Nothing is edited directly in the database.

**Insights says how much data it has.** A counter tracks days with a real rating and the night before's sleep within one medication regimen, against roughly 60 before a sleep comparison is worth trying (a planning number, not a power calculation). Melatonin changes don't restart it: they move the sleep side, which is the variation the comparison needs. Weeks that weren't fully logged are drawn faded.

**One analysis package for the app and the notebooks.** The Insights tab runs `analysis/` on the server against the same CSVs an export produces, so the two can't disagree.

**The read-only login is enforced in one place.** The middleware refuses every non-GET request from it, so a route added later can't forget the check. The page hiding its edit buttons is only tidiness.

**The app fails closed.** With no household password set, every request gets an error instead of an open app.

**Free hosting, on purpose.** Render and Neon free tiers: Neon because its free Postgres doesn't expire. The cost is a slow first load after idle.
