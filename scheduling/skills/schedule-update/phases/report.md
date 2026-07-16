# Phase: `report` — Colleague Post-Meeting Flow (Steps 9–12)

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `report` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, `_render_graphs.md`, and `procore.md`.

End-to-end conversational flow that takes a colleague from "meeting is done" to "a reviewed `.eml` draft + files in Procore." Covers steps 9–12 of the full pipeline: it opens by auto-pulling the meeting transcript (step 9), builds the seed and hands off the editor URL (step 10), waits while the colleague edits (step 11), then finalizes — `.eml` + Procore (step 12). Step 13 (open the `.eml`, review, Send) stays with the human.

## The goal in one sentence

Drive the colleague to one MCP call — `generate_weekly_schedule_update_email_draft` — with a v2 seed built by [build_seed_dict](../references/build_seed.py). Everything between "meeting done" and that POST is gathering its inputs.

## Lead with the data

When this phase starts, get the week-over-week deltas before anything else. The MCP call tells you what the conversation should be about; project-context + transcript fill in context around it. Do not paraphrase last week's XER changes by hand — `weekly_update_review` already did it.

Order of operations:

1. **Resolve** (Bash/Glob, no LLM thinking) — find today's dated folder, last week's dated folder, `{current_xer}` (newest `.xer` in today's folder), `{prev_xer}` (newest `.xer` in last week's folder).

2. **Fetch in parallel** — fire these in one message:
   - **`weekly_update_review(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)`** — the data call. Bundles activity changes, milestone slip, critical-path changes, gain/loss attribution, expected updates. Capture the returned dict; you'll reuse it in `draft.md` step 3.
   - **`get_project(job_number=<job_number>)`** MCP tool — the project **bindings** row (`project_name`, SmartPM URLs + project name, Procore ids). On a hit, map the row via `project_context_db_mapping.project_row_to_context(row)` to get the `ctx` bindings dict. On a miss (`null`), lazy-migrate (Step 1b). `ctx` no longer carries recipients / signer / graph_order / contractual_completion — those come from carry-forward / Procore / Q&A (see Step 3).
   - **`list_prime_contracts(project_id=ctx['procore_project_id'])`** (Procore MCP) — fetch the prime contract's **Substantial Completion** date for `contractual_completion`. (Can also be deferred to Step 3 when you build the seed.)
   - **Recipe A (`_m365_inputs.md`)** — `outlook_calendar_search(...)` to locate + pull this week's transcript.
   - **Recipe B (`_m365_inputs.md`)** — `outlook_email_search(...)` for last week's project mail (enrichment; and Sent-Items recovery if the prior `-email.json` is missing).
   - **Read transcript** via the `*transcript*.md` glob in `{dated_folder}` (newest wins) — auto-pulled by `_m365_inputs.md` Recipe A or manually dropped.

   This batch is the `_m365_inputs.md` Fast path — fire it in one message.

3. **Read what came back; only then decide what to ask the colleague.** If the review dict shows no SC slip and no completed tasks, you don't need to drive a Q&A — the email is essentially "stable week." If it shows a 12-day slip with three critical-path activities flipping, that's where the conversation goes.

The Worker schema at <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema> is the contract — fetch it any time you're unsure about a field, but it is not required before POST.

## Step 1: Resolve Folder + Load Project Bindings

Apply folder resolution from **Shared Setup**, including **Dated-folder selection**.
- Work in the **most recent** dated folder under the Schedules root — not necessarily one named for today. `copy` (step 1) is optional and usually already done by the scheduler.
- If the newest folder is today or within the last couple of working days → **just use it, no prompt.** Running the email the business day after the meeting is normal — don't make a big deal of there being no folder for today.
- Only if the newest folder is **≥ 3 working days old or more than a week stale** → confirm first: "The most recent schedule folder is `{folder}` ({N} working days ago). Send that update, or set up a fresh folder with `copy`?"
- If the chosen folder is missing its `.xer`, note what's missing and ask whether to proceed or wait for the export.

Parse `{job_number}` from the Schedules-root folder name (e.g. `W1177 - Project Name` → `W1177`).

**Load project bindings from Supabase, not HTML.** Project state now lives in `wnd_projects` (via the `get_project` / `upsert_project` MCP tools). `project-context.html` is **retired** — the parser remains only for the one-time lazy migration below.

Call **`get_project(job_number=<job_number>)`** (fired in the parallel block above):

- **Hit** (a row comes back) → `ctx = project_context_db_mapping.project_row_to_context(row)`. `ctx` holds only bindings (`project_name`, `smartpm_url/trends/changelog/project_name`, `procore_company_id/project_id/documents_folder_id`).
- **Miss** (`null`) → **lazy-migrate** (Step 1b).

`project_context_db_mapping` lives in the sibling skill at `scheduling/skills/schedule-project-init/references/project_context_db_mapping.py` — resolve its path with Glob and import it (do not copy it).

### Step 1b: Lazy migration (only on a `get_project` miss)

If `get_project` returned `null`, check the Schedules root for a legacy `project-context.html`:

1. **HTML present** → migrate it:
   - `parsed = parse_project_context_html(html_path)` (the parser in `schedule-project-init/references/`).
   - `payload = parsed_context_to_project_row(parsed, job_number=<job_number>)` → `upsert_project(**payload, source='migrated')`.
   - For each `entry` in `parsed_context_to_log_entries(parsed)` → `append_project_log(job_number=<job_number>, body=entry['body'], category=entry['category'], created_at=entry['created_at'])` (pass `created_at` to preserve the historical log date).
   - `retire_context_html(html_path)` → renames it to `project-context-migrated.html` so it never re-migrates.
   - Set `ctx = project_row_to_context(<the upserted row>)` (or re-call `get_project`).
2. **No HTML** → stop with: "No project bindings found for `{job_number}` in Supabase and no `project-context.html` to migrate. Run the **schedule-project-init** skill to set up this project."

## Step 2: Read the review dict; pick a content source

You already have the `review` dict from `weekly_update_review` (fired in the parallel block above) and the `ctx` bindings. Now choose how to fill `successes` / `red_flags` / `stalled_tasks` / `key_items`:

- **If a transcript was present** → mine it for narrative, then cross-reference with `review` (transcript catches things the XER doesn't — owner decisions, weather, trade performance; the XER catches things the transcript misses — slips, completions).
- **If no transcript** → drive the colleague Q&A from `review`. The dict tells you what's worth asking about, so the conversation stays on the actual deltas instead of asking generic "anything new?" questions.
- Mail enrichment (Recipe B1) contributes candidate items the same way the transcript does — cross-check against `review`.

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

1. Load `prev_draft` (last week's `{prev_date}-email.json`) via `email_draft_io.load_draft`. If it's missing, walk the `_carry_forward.md` fallback chain (its **step 0** is `get_project` + `project_row_to_context`, already done in Step 1).
2. Glob `{dated_folder}` for attachment basenames.
3. Fetch `contractual_completion` from **Procore** — `list_prime_contracts(project_id=ctx['procore_project_id'])`, take the prime contract's `substantial_completion_date`. It is **not** in `ctx` anymore.
4. Compute `days_metric` from `sc_date_new` (from step 2) vs the Procore `contractual_completion`.
5. Compute `gain_loss` from `sc_slip_days` (from step 2).
6. Call `build_seed_dict(...)` with the content gathered in step 2 + the metrics above. **New args** the report flow must pass:
   - `job_number=<parsed from folder>`
   - `contractual_completion=<from Procore, step 3>`
   - On **week-1 only** (prev_draft is None), pass the recipients / signer / graph_order gathered in the Q&A: `to_recipients`, `cc_recipients`, `signer_name`, `signer_title`, `signer_mobile`, `graph_order`. Thereafter they carry forward from `prev_draft` and these args are ignored.
7. Write the seed to `{dated_folder}/{today}-email.seed.json`.
8. POST to `generate_weekly_schedule_update_email_draft`.
9. On 422, refetch the schema and apply the violation's fix (see draft.md §7b).

> **Week-1 recipient/signer Q&A.** When there is no `prev_draft`, the report flow must ask the colleague for: the TO recipients (name + email), any CC recipients, and the signer block (name / title / mobile). Add these to the open-ended round in Step 2. The chart `graph_order` defaults to the canonical order — only ask if the colleague wants a non-standard chart set.

> **Project-log appends.** When this week files an EOT, records a scope change, or publishes a schedule, append it to the project log via the **`append_project_log(job_number, body, category)`** MCP tool (categories e.g. `eot`, `scope_change`, `schedule_published`). Do **not** write it back into any HTML — the log lives in `wnd_project_log` now.

## Step 4: Hand the editor URL to the colleague

> "Editor at `{editor_url}`. Open it in your browser; edits autosave. Use the toolbar's **B** (bold) and the brand-red priority span to mark high-priority items — they render `<strong>` and a Westland-red span verbatim in the email. Use the **P** toggle next to each attachment to control which files go to Procore. When you're done, come back here and say `done` and I'll build the `.eml` draft + push the selected files to Procore."

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
