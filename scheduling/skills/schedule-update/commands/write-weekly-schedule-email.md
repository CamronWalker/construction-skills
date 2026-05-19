# Write Weekly Schedule Email (Cowork drop-in)

> Bundled launcher for cowork sessions. Lands in a dated `YYYY-MM-DD` folder where steps 1–5 (folder copy, schedule update, export) have already been done by a human, then runs the `report` flow for steps 6–10.

## How this differs from `/schedule-update report`

Just one thing: this entry point assumes the CWD is already the dated folder (or will resolve to one immediately). Pre-meeting setup is out of scope.

## What to do

Read these phase files in full **before** taking any action — same set as `/schedule-update report`:

1. `phases/report.md`
2. `phases/_carry_forward.md`
3. `phases/_attachments.md`
4. `phases/draft.md`
5. `phases/procore.md`

Then execute the `report` flow as documented in `phases/report.md`, starting from Step 1 (Resolve Folder). Folder resolution will default to CWD/parent — no human pre-prompt needed.

## What NOT to do

- Do not `Read` the underlying Python scripts. Phase files inline every signature you need.
- Do not skip the Procore publish unless the user has the **⏭ Skip Procore this week** toggle ticked in the preview.
- Do not re-prompt for Procore project ID or documents folder ID — `procore.md`'s preflight handles auto-resolution and write-back to `project-context.html`.

## Launcher (for reference)

The `Write Weekly Schedule Email.bat` at the Schedules root invokes Claude Code in the dated folder and pastes `/write-weekly-schedule-email`. Phase files load automatically per the matrix above.
