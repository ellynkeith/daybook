# Using the log

Three tabs: **Log**, **History** and **Insights**. The tab is in the URL, so refresh, bookmarks and the back button keep your place.

## Log

### Behavior entries
- **Categories:** pick one or more. Seeded from this kid's evaluated profile: DSM-5 ODD's three clusters (angry/irritable, argumentative/defiant, vindictive) and the three ADHD presentations (impulsive, inattentive, hyperactive/restless), plus "good behavior". Add your own on the fly.
- **Situation / demand** (optional): what was going on right before (told no, a non-preferred task, sibling conflict, an unexpected change of plans…), from a list that grows, so situations can be compared instead of living in free text.
- **Details:** date, the time it *happened* (required, never filled in with the time you're logging), setting, duration, 1–5 intensity (n/a for good-behavior entries), notes, and who logged it (required).
- **Retire, don't delete:** categories and situations that no longer fit can be retired. They leave the picker but stay on the entries that used them, stay filterable, and can be restored.
- A note about the whole day belongs in the day's comments, not in a behavior entry; the link under Notes takes you there.

### Daily context
Once per day:
- **How the day went:** a one-tap "had a good day", an optional 1–5 rating, and comments.
- **Sleep:** wake time, bedtime, when she actually fell asleep, night wakings (with an explicit "None", so a blank means "not recorded").

Any number per day:
- **Wetting incidents:** time, marked as when it *happened* or, approximately, when it was *noticed*; where; how she responded to changing (compliant / noncompliant / not observed / other; the charts call these "changed without a fight", "resisted changing" and "not seen"); details.
- **Medication doses:** time and one or more medications taken together. The dose lives in the medication's name ("Methylphenidate 10mg"), so a dose change is a new medication, not a rename. A dose can be logged as **skipped**; a day with nothing logged means missing data, not a skipped dose. "Same as previous day" copies yesterday's doses, marked unconfirmed ("~8:30 AM") until someone confirms or edits the time. Medications no longer used can be hidden without losing their history.

**Which day you're saving to:** when the Daily Context date isn't today (after filling in an earlier day, or in a tab left open overnight), the add buttons say so: "Add to Sun Nov 15".

### Context log
Dated events for slow-moving things nothing else captures: illness, school breaks and days off, schedule changes, visitors and travel, medication changes. Events can span several days and show on each day they cover ("day 2 of 4"). An event can be marked **Leave these days out of Insights** (say, a trip abroad): the data is kept, but those days don't count in any average.

## History
- Everything grouped by day, newest first, in collapsible months and past years.
- **What's missing:** a 14-day strip and per-day chips flag anything expected but not logged (wake-up time, bedtime, a rating, usual medications), including days with nothing at all. Tap a chip to fill it in, mark a dose skipped, or mark the day "nothing more to add". Complete days look the same as ever.
- **Filter** by category, or **go to a date** to show just that day.
- **Edit** any entry, incident or dose. Changing the date while editing moves it, and the button says so ("Update and move to Sun Nov 15").
- **Export:** the behavior log (or a filtered slice) as CSV, or everything as a zip with one CSV per table. That opens in Excel, loads straight into pandas, and doubles as a backup.

## Insights
One timeline, recomputed every time the tab opens. Tap or hover over a day (or use the arrow keys) for its details; "Show as table" gives the same thing as rows. Each chart can be shown or hidden, and the choice is remembered in that browser.

- **Day rating:** dots for each day's rating (hollow = "good day" only, counted as 4) and the **7-day average** (teal; the gray line leaves out good-day-only days). The average covers 3 days either side and needs 4 of those 7 rated, so the most recent days fill in later. Shaded bands are context events; triangles are medication changes worked out from the dose log.
- **Behavior:** entries per day, darker for higher intensity. A short mark on the baseline means the day was rated with nothing logged: a **real zero**, not a forgotten day.
- **Wetting:** one dot per incident, filled by how changing went.
- **Wetting by week:** Monday–Sunday totals, split the same way. **Faded** weeks weren't fully logged, so a gap never reads as a dry week.
- **Sleep:** the night *before* each day (bedtime → fell asleep → woke up), so a rough night sits under the day that followed. A warning color marks a suspiciously long time to fall asleep.
- **Left-out days** show as a hatched gap rather than being joined across; "Show left-out days" brings them back.
- **Sleep vs next-day rating: N of ~60 days.** Days with both a real rating and the night before's sleep, counted within the current medication regimen. Around 60 is when comparing sleep with the next day starts to be worth trying. Until then, treat any pattern you spot as a hunch.

## Logins
- **Household:** sees and changes everything.
- **Read-only** (optional): sees and exports the real log, can't change anything.
- **Demo:** made-up data, fully clickable, never touches the real log. Resets whenever the server restarts.
