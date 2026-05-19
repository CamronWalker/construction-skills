# Phase: `report` — Colleague Post-Meeting Flow (Steps 6–10)

> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, and `procore.md`.

End-to-end conversational flow that takes a colleague from "meeting is done" to "Outlook draft in Drafts folder + files in Procore." Covers steps 6–10 of the full pipeline.

## Step 1: Resolve Folder

Apply folder resolution from **Shared Setup**.
- Default target folder: `{Schedules root}/{today's date in YYYY-MM-DD}/`
- If today's folder does not exist, list the most recent 3 dated folders and ask: "I don't see a folder for today. Is this week's update in `{most_recent}` or should I create today's folder first? (Run `copy` to create today's folder.)"
- If today's folder exists but is empty or missing the XER, note what's missing and ask whether to proceed or wait for the human steps (5–9) to finish.

Read `project-context.html`. If missing, stop with the standard error.

## Step 2: Run Screenshots If Needed

Check for all required PNGs in `{dated_folder}/screenshots/`:
- `smartpm-summary-report.png`
- every file listed in `graph_screenshots` from `project-context.html`

If any are missing, say: "I need to capture SmartPM graphs first — running screenshots now." Then execute the `screenshots` workflow (above) before continuing.

If SmartPM was uploaded less than ~30 minutes ago, warn the colleague it may still be processing and offer to wait.

## Step 3: Transcript Or Q&A?

Ask the colleague:
> "Do you have the meeting transcript? Drop it in `{dated_folder}/meeting/` and I'll mine it for successes, red flags, and key items. Otherwise I'll compare this week's XER to last week's and ask you questions instead."

Branch based on response:

### 3a. **Has transcript** — Transcript-driven fill

1. Read the transcript from `{dated_folder}/meeting/` (`.txt`, `.md`, `.docx`).
2. Extract successes, issues, recovery efforts, red flags using the `email` workflow's "Mine Meeting Transcript" logic.
3. Present extracted items for confirmation before accepting them.

### 3b. **No transcript** — XER-driven Q&A

1. Find the two most recent XER files: current-week XER in `{dated_folder}/*.xer`, previous-week XER in the most recent prior dated folder.
2. Parse both using `schedule-toolbox` and compute the delta:
   - **SC date change** — "Substantial Completion moved from `{prev}` to `{current}` ({delta} days). What's the story?"
   - **Activities completed this week** — "These finished since the last update: `{list}`. Which should I call out as successes?"
   - **Activities that slipped** — "These moved later: `{name}` ({days_slipped} days). Red flag, slipping task, or expected?"
   - **Activities that started late / didn't start** — "These were planned to start but haven't: `{list}`. Still blocked, or will they start soon?"
   - **Logic/scope changes** — activity adds, deletes, relationship changes (count summary, then "Any scope changes worth mentioning?")
   - **Near-critical/critical path movement** — "Critical path changed in these areas: `{list}`. Anything to highlight?"
3. After the XER-driven round, ask the open-ended round:
   - "Anything else going great that I should add to Successes?"
   - "Any red flags coming from the field — material, trade performance, weather, owner decisions?"
   - "What are the 2–3 key items the team needs to focus on this coming week?"
   - "Is there an EOT/recovery update? What changed with trade performance?"
4. Keep the conversation tight — ask 2–4 questions per turn, not a long wall. Confirm each answer before moving on.

## Step 4: Carry Forward From Previous Email

> See `_carry_forward.md`.

## Step 5: Calculate Metrics From XER

Using `schedule-toolbox`, compute:
- Days behind/ahead (vs. `contractual_completion`)
- Gain/loss vs. last week's days-behind figure

These populate the colored status lines in the email. They come from the XER — do not ask the colleague for them.

## Step 6: Generate Editable HTML Preview

Run the shared preview generation step. See `_carry_forward.md` for the recipe and `_attachments.md` for the new Procore controls.

Tell the colleague:
> "Preview at `{path}`. Open it in your browser, edit any section in place, and when you're happy click **Save Edits** -> save the download on top of the file (same name, same folder) -> tell me `done`. I'll then create the Outlook draft and push the selected files to Procore. Tip: wrap a list item in `**double asterisks**` to make it bold + red in the email. Use the **P** toggle next to each attachment to control which files go to Procore. If you already had the preview open in another tab, **hard-refresh (Ctrl+F5)** -- Chrome caches it aggressively."

#### JSON-paste regeneration (escape hatch)

If the colleague has already iterated on the content in their head and just wants the preview rendered to match, they may paste a JSON snapshot -- same shape as the preview's "Copy for Claude" button output, or what `parse_preview_html()` returns. Pipe that JSON straight back through `generate_preview_html(output_path, **kwargs)` -- do not re-run carry-forward, the JSON is already the curated state. This is also the right path when the user is correcting a regeneration mistake or has compiled the desired content offline. After regenerating, point them at the same file with a Ctrl+F5 reminder.

## Step 7: Wait For "done", Then Draft + Procore Publish

When the colleague says `done`:

1. Read the (now-edited) preview HTML via `parse_email_html.py:parse_preview_html(preview_path)`. The returned dict includes `attachments` (with `share_to_procore` per item) and the top-level `skip_procore` toggle.

2. **Write the `.eml`** by following `draft.md`. (Phase file already loaded per the command matrix.)

3. **Procore publish** (unless `parsed['skip_procore'] == True`) by following `procore.md`. (Also already loaded.)

4. **Write the archive markdown** `{dated_folder}/{YYYY-MM-DD}-update-email.md` from the parsed dict.

5. Report a unified summary:

   > "Done. `.eml` written to `{path}`. Procore: XER imported - Dated folder `{folder_id}` - {N} files uploaded - {M} skipped or failed. Open the `.eml` to review and send. (Or use `/schedule-update procore` to retry the Procore part if anything failed.)"

If the colleague set `Skip Procore this week`, the Procore line of the summary reads: `"Procore: skipped this week."`

If the HTML file looks unchanged (no edits detected) or fails to parse, surface the problem and ask whether to proceed with the unedited draft.
