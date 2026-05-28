# Phase: `report` — Colleague Post-Meeting Flow (Steps 10–12)

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `report` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, `_render_graphs.md`, and `procore.md`.

End-to-end conversational flow that takes a colleague from "meeting is done" to "Outlook draft in Drafts folder + files in Procore." Covers steps 10–12 of the full pipeline.

## The goal in one sentence

Drive the colleague to one MCP call — `generate_weekly_schedule_update_email_draft` — with a v2 seed built by [build_seed_dict](../references/build_seed.py). Everything between "meeting done" and that POST is gathering its inputs.

## Lead with the data

When this phase starts, get the week-over-week deltas before anything else. The MCP call tells you what the conversation should be about; project-context + transcript fill in context around it. Do not paraphrase last week's XER changes by hand — `weekly_update_review` already did it.

Order of operations:

1. **Resolve** (Bash/Glob, no LLM thinking) — find today's dated folder, last week's dated folder, `{current_xer}` (newest `.xer` in today's folder), `{prev_xer}` (newest `.xer` in last week's folder).

2. **Fetch in parallel** — fire these in one message:
   - **`weekly_update_review(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)`** — the data call. Bundles activity changes, milestone slip, critical-path changes, gain/loss attribution, expected updates. Capture the returned dict; you'll reuse it in `draft.md` step 3.
   - **`load_project_context(schedules_root)`** — recipients, signer, SmartPM URLs.
   - **Read transcript** at `{dated_folder}/meeting-transcript.md` if it exists.

3. **Read what came back; only then decide what to ask the colleague.** If the review dict shows no SC slip and no completed tasks, you don't need to drive a Q&A — the email is essentially "stable week." If it shows a 12-day slip with three critical-path activities flipping, that's where the conversation goes.

The Worker schema at <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema> is the contract — fetch it any time you're unsure about a field, but it is not required before POST.

## Step 1: Resolve Folder

Apply folder resolution from **Shared Setup**.
- Default target folder: `{Schedules root}/{today's date in YYYY-MM-DD}/`
- If today's folder does not exist, list the most recent 3 dated folders and ask: "I don't see a folder for today. Is this week's update in `{most_recent}` or should I create today's folder first? (Run `copy` to create today's folder.)"
- If today's folder exists but is empty or missing the XER, note what's missing and ask whether to proceed or wait for the human steps (5–9) to finish.

Read `project-context.html`. If missing, stop with the standard error.

## Step 2: Read the review dict; pick a content source

You already have the `review` dict from `weekly_update_review` (fired in the parallel block above) and project-context. Now choose how to fill `successes` / `red_flags` / `stalled_tasks` / `key_items`:

- **If a transcript was present** → mine it for narrative, then cross-reference with `review` (transcript catches things the XER doesn't — owner decisions, weather, trade performance; the XER catches things the transcript misses — slips, completions).
- **If no transcript** → drive the colleague Q&A from `review`. The dict tells you what's worth asking about, so the conversation stays on the actual deltas instead of asking generic "anything new?" questions.

**Don't write ad-hoc XER-parsing Python.** Everything you need is in `review`. If you need an additional slice (e.g. a specific trade's upcoming activities), call the windowed MCP tools — never read `.xer` bytes directly. If `ToolSearch select:<tool_name>` returns nothing, invoke the `westland-scheduler-mcp-troubleshoot` skill — do not fall back to reading `schedule-toolbox/lib/*.py` (the PreToolUse hook blocks that read).

#### Drive the Q&A from the `review` dict

- `review.milestone_slip.sc_date_old` / `.sc_date_new` / `.sc_slip_days` → "Substantial Completion moved from `{sc_date_old}` to `{sc_date_new}` (`{sc_slip_days}` days). What's the story?"
- `review.activity_changes.status_changes` (rows where new status is `TK_Complete`) → "These finished since the last update: `{list}`. Which should I call out as successes?"
- `review.activity_changes.status_changes` (rows still `TK_NotStart` past baseline early start) → "These were planned to start but haven't: `{list}`. Still blocked, or starting soon?"
- `review.activity_changes.added_tasks` + `removed_tasks` + `changed_durations` → count summary → "Any scope or duration changes worth mentioning?"
- `review.critical_path_changes` (when non-`None`) → if activities moved on/off the critical path → "Critical path shifted: `{summary}`. Worth calling out?"
- `review.gain_loss_attribution` (when non-`None`) → top-3 contributors to this week's slip → drives `gain_loss_narrative`.

If multi-terminal degrades `critical_path_changes` / `gain_loss_attribution` to `None`, that's expected — pass `milestone_id` to get them back.

#### Trade-specific upcoming work

`weekly_update_review` already returns `activities_to_start` / `activities_to_finish` (unfiltered, far-future). If the colleague asks "what does {trade} need to update by next week?" with a tight date window and a trade filter, re-call the windowed tools directly:

```text
get_activities_to_start(xer_path=<current_xer>, future_date=<YYYY-MM-DD>, resource_filter="<trade_code>")
get_activities_to_finish(xer_path=<current_xer>, future_date=<YYYY-MM-DD>, resource_filter="<trade_code>")
```

`resource_filter` is a case-insensitive substring against resource short names (e.g. `"ELEC"`).

#### Open-ended round

After the XER-driven round, ask the open-ended round:
- "Anything else going great that I should add to Successes?"
- "Any red flags from the field — material, trade performance, weather, owner decisions?"
- "What are the 2–3 key items the team needs to focus on this coming week?"
- "Is there an EOT/recovery update? What changed with trade performance?"

Keep it tight — 2–4 questions per turn. Confirm each answer before moving on.

## Step 3: Build seed and POST

The metrics (`days_metric`, `gain_loss`), carry-forward of last week's lists, attachment transitions, and default fields are all handled by `build_seed_dict`. Re-read [phases/draft.md](draft.md) §5–§7 — that's the recipe Claude follows here.

Short version:

1. Load `prev_draft` (last week's `{prev_date}-email.json`) via `email_draft_io.load_draft`.
2. Glob `{dated_folder}` for attachment basenames.
3. Compute `days_metric` from `sc_date_new` (from step 2) vs `ctx['contractual_completion']`.
4. Compute `gain_loss` from `sc_slip_days` (from step 2).
5. Call `build_seed_dict(...)` with the content gathered in step 2 + the metrics above.
6. Write the seed to `{dated_folder}/{today}-email.seed.json`.
7. POST to `generate_weekly_schedule_update_email_draft`.
8. On 422, refetch the schema and apply the violation's fix (see draft.md §7b).

## Step 4: Hand the editor URL to the colleague

> "Editor at `{editor_url}`. Open it in your browser; edits autosave. Use the toolbar's **B** (bold) and the brand-red priority span to mark high-priority items — they render `<strong>` and a Westland-red span verbatim in the email. Use the **P** toggle next to each attachment to control which files go to Procore. When you're done, come back here and say `done` and I'll build the Outlook draft + push the selected files to Procore."

### JSON-paste regeneration (escape hatch)

If the colleague has already iterated on the content offline and just wants the editor seeded with a specific state, they may paste a JSON snapshot — same shape as `{YYYY-MM-DD}-email.json` (see scheduling/CLAUDE.md "Email JSON shape"). Save it to `{dated_folder}/{YYYY-MM-DD}-email.seed.json` and re-POST `generate_weekly_schedule_update_email_draft` with that seed. Skip `build_seed_dict` — the pasted JSON is already the curated state.

## Step 5: Wait For "done", then finalize + Procore

When the colleague says `done`:

1. Finalize via `finalize_weekly_schedule_update_email`. Save the returned working JSON to `{dated_folder}/{YYYY-MM-DD}-email.json`. Load it locally via `email_draft_io.load_draft(path)`.

2. **Build the .eml** by following [draft.md](draft.md) §12.

3. **Procore publish** (unless `parsed['skip_procore'] == True`) by following [procore.md](procore.md).

4. **Write the archive markdown** `{dated_folder}/{YYYY-MM-DD}-update-email.md` from the parsed dict.

5. Report a unified summary:

   > "Done. `.eml` written to `{path}`. Procore: XER imported - Dated folder `{folder_id}` - {N} files uploaded - {M} skipped or failed. Open the `.eml` to review and send. (Or use `/schedule-update procore` to retry the Procore part if anything failed.)"

If the colleague set `Skip Procore this week`, the Procore line reads: `"Procore: skipped this week."`

If finalize fails or the JSON is empty (colleague hadn't actually edited), surface the problem and ask whether to proceed with the unedited draft or wait.
