# Write Weekly Schedule Email (Cowork drop-in)

> Bundled launcher for cowork sessions. Lands in a dated `YYYY-MM-DD` folder where steps 1–5 (folder copy, schedule update, export) have already been done by a human, then runs the `report` flow for steps 10–12.

## The goal in one sentence

POST one MCP call — `generate_weekly_schedule_update_email_draft` — with a v2 seed built by [build_seed_dict](../references/build_seed.py). Hand the colleague the editor URL. Wait for "done." Finalize, build the .eml, publish to Procore. End.

## Lead with the data

Get the week-over-week deltas before doing anything else. Order:

1. **Resolve** (Bash/Glob) — find `dated_folder`, `prev_dated_folder`, `current_xer`, `prev_xer`. See `phases/report.md` step 1.
2. **Parallel fetch** — one turn, three calls overlapping:
   - `weekly_update_review(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)` — one MCP call that returns activity changes, milestone slip, expected updates, critical-path changes, and gain/loss attribution. Feeds `build_seed_dict`.
   - `get_project(job_number)` → `project_context_db_mapping.project_row_to_context(row)` — the SmartPM URLs + Procore id bindings (lazy-migrate a legacy `project-context.html` on a miss; see `phases/report.md` Step 1b). Recipients / signer come from carry-forward, not bindings.
   - Read transcript if present.
3. Read what came back; let the `review` dict pick what to ask the colleague.

If last week's `email.json` isn't there, see `phases/_carry_forward.md` "Fallback chain" — PDF / old preview HTML / archive markdown can each yield a usable `prev_draft`.

## How this differs from `/schedule-update report`

Just one thing: this entry point assumes the CWD is already the dated folder (or resolves to one immediately). Pre-meeting setup is out of scope.

## What to do

Read these phase files in full **before** taking any action — same set as `/schedule-update report`:

1. `phases/report.md`
2. `phases/_carry_forward.md` (reference only — `build_seed_dict` calls these helpers internally)
3. `phases/_attachments.md` (same)
4. `phases/draft.md`
5. `phases/procore.md`

Then execute the `report` flow as documented in `phases/report.md`, starting from step 1 (Resolve Folder). Folder resolution defaults to CWD/parent — no human pre-prompt needed.

## What NOT to do

- Do not `Read` the underlying Python scripts. The phase files inline every signature you need.
- Do not hand-construct the seed dict — call `build_seed_dict`. The Worker schema is rich and drift-prone; the helper is the single source of truth.
- Do not skip the Procore publish unless the colleague has the **⏭ Skip Procore this week** toggle ticked in the editor.
- Do not re-prompt for Procore project ID or documents folder ID — `procore.md`'s preflight handles auto-resolution and write-back via `upsert_project`.

## Launcher (for reference)

The `Write Weekly Schedule Email.bat` at the Schedules root invokes Claude Code in the dated folder and pastes `/write-weekly-schedule-email`. Phase files load automatically per the matrix above.
