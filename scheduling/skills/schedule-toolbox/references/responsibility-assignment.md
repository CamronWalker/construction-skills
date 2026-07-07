# Assigning Responsibility (trade) codes by activity name

Westland tags every activity with a **Responsibility - Global** activity code
(the trade). This is the repeatable flow for doing a first pass by name and
assigning them, asking the human only on genuine ambiguity.

## The remembered code list

`references/responsibility-codes.json` holds the canonical global code list
(code + description) plus a keyword map that powers the name matcher. It ships
with the plugin, so it's available on every install. Edit it to add codes or
tune keywords — it's plain, human-editable JSON.

## Division of labor (why it's hybrid)

The keyword matcher alone tops out ~85% on real schedules — not because the
algorithm is weak, but because the historical labels disagree across projects
(the same activity name is coded differently on different jobs). So:

- **The tool** (`suggest_responsibility`) does the fast, obvious bulk and hands
  back a candidate shortlist for the rest. It's an accelerator, not the judge.
- **Claude** makes the actual call using the activity name + the shortlist +
  the full code list, which is far better than keyword matching.
- **The human** is asked only on the genuinely ambiguous few.

## Steps

1. **Suggest.** Call `suggest_responsibility(xer_path, only_unassigned=True)`.
   You get `assigned` (confident), `unsure` (each with `candidates`), and
   `all_codes`.
2. **Adjudicate.**
   - Spot-check `assigned` — accept the obvious ones.
   - For each `unsure` row, pick the right code from its `candidates` or from
     `all_codes` using the activity name and its WBS context (pull that with
     `get_activity` / `list_activities` if needed).
   - Anything still genuinely unclear (e.g. a bare "Rough-In" that could be
     MECH/HVAC/PLUM/ELEC depending on the job) → **ask the human**. Don't guess.
3. **Write.** Apply the finalized map with one `apply_xer_changes` call whose
   `changes` are `set_responsibility` records:
   ```json
   { "type": "set_responsibility", "activity_id": "A1050", "code": "ELEC", "name": "Electrical" }
   ```
   This writes the `ACTVTYPE → ACTVCODE → TASKACTV` chain, prefers the global
   code (never creates a project-scoped duplicate of a global code), and
   replaces any existing Responsibility on the activity.
4. **Verify.** `apply_xer_changes` writes a new `-modified.xer` (never
   overwrites) and re-validates. Re-run `list_activities(trade_filter=...)` or
   `suggest_responsibility(only_unassigned=True)` to confirm the blanks are
   filled.

## Notes

- `only_unassigned=True` is the normal "fill in the blanks" pass — it skips
  activities already coded. Use `False` to re-suggest across everything.
- WBS-summary (`TT_WBS`) and level-of-effort (`TT_LOE`) rows are skipped — they
  aren't real activities to code.
