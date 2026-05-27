# Phase: `report` — Colleague Post-Meeting Flow (Steps 10–12)

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `report` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, `_render_graphs.md`, and `procore.md`.

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

If any are missing, say: "I need to capture SmartPM graphs first — running screenshots now." Then continue — graphs are fetched server-side after the seed POST; the stacked PNG is built locally during the .eml build step (see `phases/_render_graphs.md`).

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

**Don't write ad-hoc XER-parsing Python.** The Westland Scheduler Local MCP exposes everything needed here. Call MCP tools by name — `compare_activity_changes`, `compare_milestone_slip`, `compare_date_slips`, `get_activities_to_start`, `get_activities_to_finish`, `get_milestones`. If `ToolSearch select:<tool_name>` returns nothing, invoke the `westland-scheduler-mcp-troubleshoot` skill — do not fall back to reading `schedule-toolbox/lib/*.py` (the PreToolUse hook blocks that read).

#### Locate the two XERs

Current-week XER: the most recent `{dated_folder}/*.xer`. Previous-week XER: the most recent `*.xer` in the prior dated folder. Use absolute paths in MCP calls.

#### Resolve the terminal milestone (only if ambiguous)

```text
ToolSearch select:get_milestones,compare_activity_changes,compare_milestone_slip,compare_date_slips
```

`compare_milestone_slip` auto-resolves the terminal milestone on single-terminal schedules; on phased schedules with multiple terminal milestones it raises `MilestoneAmbiguousError`. If you hit that, call `get_milestones(xer_path=<current_xer>)` to list candidates, then re-call `compare_milestone_slip(milestone_id=<resolved_task_id_or_code>)`.

#### Compare this week's XER to last week's

Run the three compare tools against the same baseline/current pair. Defaults are correct for the weekly cadence (`match_by="task_code"` — robust to P6 task_id renumbering between exports).

```text
compare_milestone_slip(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>, milestone_id=<resolved>?)
compare_activity_changes(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)
compare_date_slips(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)
```

Use the returned dicts to drive the colleague Q&A:

- `compare_milestone_slip` → `sc_date_old` / `sc_date_new` / `sc_slip_days` → "Substantial Completion moved from `{sc_date_old}` to `{sc_date_new}` (`{sc_slip_days}` days). What's the story?"
- `compare_activity_changes.status_changes` → filter rows where the new status is `TK_Complete` → "These finished since the last update: `{list}`. Which should I call out as successes?"
- `compare_date_slips.date_slippage` → rows with positive `es_slip_days` or `ef_slip_days` → "These moved later: `{task_name}` (`{ef_slip_days}` days). Red flag, slipping task, or expected?"
- `compare_activity_changes.status_changes` → filter rows where new status is still `TK_NotStart` past the baseline early start → "These were planned to start but haven't: `{list}`. Still blocked, or will they start soon?"
- `compare_activity_changes.added_tasks` + `removed_tasks` + `changed_durations` → count summary → "Any scope or duration changes worth mentioning?"

Critical-path movement isn't surfaced in Plan 1 (Tier 1 `get_critical_path_changes` ships in Plan 2). If the colleague raises critical-path questions, fall back to comparing `get_critical_path(xer_path=<current_xer>)` vs the same against the prior XER and diff the activity lists by hand.

#### Trade-specific upcoming work

If the colleague asks "what does {trade} need to update by next week?", call the activity-window tools directly. No script invocation, no path resolution.

```text
get_activities_to_start(xer_path=<current_xer>, future_date=<YYYY-MM-DD>, resource_filter="<trade_code>")
get_activities_to_finish(xer_path=<current_xer>, future_date=<YYYY-MM-DD>, resource_filter="<trade_code>")
```

`resource_filter` is a case-insensitive substring against resource short names (e.g. `"ELEC"`). Each tool returns the data date, the future date, and the matching task list with name + early dates.

#### Open-ended round

After the XER-driven round, ask the open-ended round:
- "Anything else going great that I should add to Successes?"
- "Any red flags coming from the field — material, trade performance, weather, owner decisions?"
- "What are the 2–3 key items the team needs to focus on this coming week?"
- "Is there an EOT/recovery update? What changed with trade performance?"

Keep the conversation tight — ask 2–4 questions per turn. Confirm each answer before moving on.

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
> "Editor at `{editor_url}`. Open it in your browser; edits autosave. Use the toolbar's **B** (bold) and the brand-red priority span to mark high-priority items — they render `<strong>` and a Westland-red span verbatim in the email. Use the **P** toggle next to each attachment to control which files go to Procore. When you're done, come back here and say `done` and I'll build the Outlook draft + push the selected files to Procore."

#### JSON-paste regeneration (escape hatch)

If the colleague has already iterated on the content in their head and just wants the editor seeded with a specific state, they may paste a JSON snapshot — same shape as `{YYYY-MM-DD}-email.json` (see scheduling/CLAUDE.md "Email JSON shape"). Save it to `{dated_folder}/{YYYY-MM-DD}-email.seed.json` and re-run the MCP `generate_weekly_schedule_update_email_draft` call with that seed. Do not re-run carry-forward — the JSON is already the curated state. This is also the right path when the user is correcting a regeneration mistake or has compiled the desired content offline.

## Step 7: Wait For "done", Then Draft + Procore Publish

When the colleague says `done`:

1. Finalize the cloud editor's draft via `finalize_weekly_schedule_update_email` and write the result to `{dated_folder}/{YYYY-MM-DD}-email.json`. Load it locally via `email_draft_io.load_draft(path)`. The returned dict's `this_week` block includes `attachments` (with `procore` per item) and the `skip_procore` toggle.

2. **Write the `.eml`** by following `draft.md`. (Phase file already loaded per the command matrix.)

3. **Procore publish** (unless `parsed['skip_procore'] == True`) by following `procore.md`. (Also already loaded.)

4. **Write the archive markdown** `{dated_folder}/{YYYY-MM-DD}-update-email.md` from the parsed dict.

5. Report a unified summary:

   > "Done. `.eml` written to `{path}`. Procore: XER imported - Dated folder `{folder_id}` - {N} files uploaded - {M} skipped or failed. Open the `.eml` to review and send. (Or use `/schedule-update procore` to retry the Procore part if anything failed.)"

If the colleague set `Skip Procore this week`, the Procore line of the summary reads: `"Procore: skipped this week."`

If the HTML file looks unchanged (no edits detected) or fails to parse, surface the problem and ask whether to proceed with the unedited draft.
