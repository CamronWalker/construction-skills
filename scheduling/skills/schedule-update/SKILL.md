---
name: schedule-update
description: >
  Full weekly schedule update pipeline for Westland Construction. Handles all post-meeting
  steps: folder setup, SmartPM screenshot capture, email draft generation, editable HTML
  preview, and Outlook draft creation. Progressively disclosed -- routes by command arg or
  detects current phase from file system. Use for: "schedule update", "weekly update",
  "update email", "weekly schedule report email", "weekly report email", "schedule report
  email", "prep the update email", "help me with the email", "take screenshots", "smartpm
  screenshots", "schedule email", "draft the email", "copy schedule folder", "update status",
  "where are we in the update", "generate email", "create draft", or any schedule update
  workflow. Two main entry points: `copy` for pre-meeting folder setup, and `report` for
  the colleague-friendly post-meeting flow (steps 6-10 as a guided conversation with an
  editable HTML email preview). Absorbs schedule-update-email and schedule-screenshots.
---

# Schedule Update Pipeline

## ⚠️ Absolute rule — XER files are immutable

**Every `.xer` in dated Schedules folders is an immutable project record.** Policy applies to every sub-command below:

- **READ** any `.xer` freely.
- **MODIFY** by writing a **new versioned file** alongside the existing one, incrementing the suffix each time (`...xer` → `...-v2.xer` → `...-v3.xer`).
- **NEVER** edit in place (Edit / MultiEdit / overwriting Write).
- **NEVER** delete.

Enforced at the tool layer by `hooks/check_xer_write.py` (PreToolUse matcher: `Edit|Write|MultiEdit|NotebookEdit|Bash`), which blocks in-place edits, overwrites of existing `.xer` files, and Bash delete commands (`rm`, `del`, `Remove-Item`, `find -delete`) targeting `.xer` paths.

---

Unified skill for the Westland weekly schedule update workflow. One entry point covers the full
post-meeting pipeline: folder setup, SmartPM screenshots, email draft, and Outlook draft creation.

## Commands

Invoke with an optional command argument:

| Invocation | What it does |
|------------|-------------|
| `/schedule-update` | No arg -- detect current phase and guide to the next step |
| `/schedule-update copy` | Copy schedule folder for today's date (pre-meeting step) |
| `/schedule-update screenshots` | Capture SmartPM graphs via Playwright |
| `/schedule-update email` | Generate the weekly update email and open an **editable HTML preview** in the dated folder |
| `/schedule-update report` | **Colleague-friendly end-to-end:** screenshots → Q&A or transcript → editable HTML preview → Outlook draft. Runs steps 6–10 as one guided conversation. |
| `/schedule-update draft` | Create Outlook draft from the approved email (reads the edited HTML preview) |
| `/schedule-update status` | Show where the project is in the pipeline |
| `/write-weekly-schedule-email` | **Cowork drop-in** — dedicated slash command that lands in a dated `YYYY-MM-DD` folder (steps 1–5 already done by human) and runs the `report` flow for steps 6–10. See `commands/write-weekly-schedule-email.md`. |

**Picking a command:** Camron uses `copy` then the individual steps (`screenshots` → `email` → `draft`). Colleagues who just need help after the meeting should use `report` — it bundles screenshots, content-gathering (with or without a meeting transcript), the HTML preview, and the Outlook draft into one guided conversation. Cowork sessions that fire automatically in a dated folder use `/write-weekly-schedule-email` as the dedicated entry point (same `report` flow, just with the starting assumptions baked in). All three flows share the same editable HTML preview as the review artifact.

Every command reads `project-context.html` first. If it is missing, stop with:
> "No project-context.html found in the Schedules root. Run the `schedule-project-init` skill first."

---

## Shared Setup

### Folder Resolution

All commands use this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** (`../`)
2. If CWD basename is `Schedules` → root is CWD
3. If CWD contains a `Schedules/` child directory → root is that child
4. Otherwise → ask the user for the Schedules folder path

The grandparent of the Schedules root should match `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`).

### project-context.html

Lives in the **root Schedules folder** (not inside dated subfolders). Created and maintained by the `schedule-project-init` skill. It's an editable HTML file with Westland branding, contenteditable fields, drag-reorder recipient/graph rows, and a project log.

**Reading it.** Use the helper in the schedule-project-init skill:

```python
from parse_project_context_html import load_project_context
ctx, html_path = load_project_context(schedules_root)
```

Returns `(None, None)` if the file doesn't exist — in that case, stop and tell the user to run `schedule-project-init`. The dict shape:

```python
{
  'project_name': str, 'job_number': str,
  'contractual_completion': str,
  'smartpm_url': str, 'smartpm_trends_url': str, 'smartpm_changelog_url': str,
  'signer_name': str, 'signer_title': str, 'signer_mobile': str,
  'procore_company_id': str,   # locked in the UI (always Westland = '11093')
  'procore_project_id': str,
  'graph_screenshots': list[str],      # filenames in display order
  'to_recipients': list[{'name': str, 'email': str}],
  'cc_recipients': list[{'name': str, 'email': str}],
  'to_recipients_str': str,   # legacy "Name <email>; …" form for generate_email_msg
  'cc_recipients_str': str,
  'project_log': list[{'date': 'YYYY-MM-DD', 'body': str}],
}
```

**Attachments are NOT in the context.** Earlier versions had an `expected_attachments` glob list; that's been removed because the weekly preview HTML carries attachments forward week-over-week via `transition_attachments` (date-normalized fuzzy match). First week bootstrap: glob all `.pdf` / `.xlsm` / `.xer` in the dated folder as the initial set — the user curates from there in the preview.

**Project log.** The context HTML includes a project-level log (scope changes, EOT filings, contract amendments, major decisions — distinct from the per-week status narrative). Entries dated before today render locked; today's entry is editable. The `draft` sub-command appends to today's entry when a weekly update contains notable events — see Step 9 below.

### Weekly email file

Each dated folder gets a `YYYY-MM-DD-update-email.md` with two sections:

1. **Update Email** -- the email content (successes, red flags, key items, etc.)
2. **Project Log** -- cumulative delay notes for claims and delay analysis

---

## `copy` -- Pre-Meeting Folder Setup

Creates a new dated folder for today's schedule update.

### Step 1: Resolve root

Apply folder resolution above. Identify the Schedules root.

### Step 2: Find most recent dated folder

List all `YYYY-MM-DD` subdirectories in the Schedules root, sort descending, and take the most recent. This is the template folder.

If no dated folders exist, create the folder structure from scratch (ask the user what files/subfolders to include).

### Step 3: Create today's folder

Create `{root}/{YYYY-MM-DD}/` using today's date. Copy the **folder structure** (not file contents) from the most recent dated folder:
- Create matching subdirectories (`screenshots/`, `meeting/`, etc.)
- Do NOT copy schedule files, XER files, or PDFs -- those are project deliverables
- Copy any batch scripts (`.bat`, `.ps1`) from the template folder -- these are reusable tools

### Step 4: Report

List the created folder and its contents. Tell the user what's next:
> "Folder created at `{path}`. When you're ready to update the schedule, remind the team to send their Excel update file."

---

## `screenshots` -- Capture SmartPM Graphs

Captures 17 screenshots from SmartPM: 1 Summary Report + 16 individual trend graphs.

### Step 0: Pre-Flight — pick a browser backend

Two supported paths; **prefer the MCP path**. The Node path stays as a fallback for environments (e.g., Camron's workstation) where the MCP isn't available but Node is.

**MCP path (preferred — no local dependencies):**

Check for Playwright MCP tools in this session — look for `mcp__*playwright*__browser_navigate`, `browser_take_screenshot`, `browser_snapshot`, etc. If present, use them directly. This is the only supported path when invoked via `/write-weekly-schedule-email` (the colleague-facing flow — colleagues won't have Node).

**Node fallback:**

If the MCP tools aren't available, fall back to the bundled script:
1. Verify Node.js: `node --version`.
2. Check `node_modules/playwright` in `{skill_dir}/references/`. If missing, run `npm install` in `{skill_dir}/references/`.
3. If Chromium is missing, run `npx playwright install chromium` in `{skill_dir}/references/`.

### Step 1: Read Project Context

Apply folder resolution. Read `project-context.html`. Extract:
- `smartpm_url` (Workspace URL, ends with `/workspace`)
- Derive Trends URL: replace `/workspace` with `/trends?tab=Graphs`

Determine the output directory: `{dated_folder}/screenshots/`

If `project-context.html` is missing, stop with the error above.
If the user provides a SmartPM URL directly, use it and proceed without project-context.html.

### Step 2: Write Checklist

Create `{dated_folder}/screenshots/` if it does not exist.
Write `screenshots/checklist.md` from the template at `{skill_dir}/references/checklist-template.md`,
filling in project name, date, and SmartPM URLs.

Print the checklist.

### Step 3a: Capture via Playwright MCP (preferred)

Drive the browser through the MCP tools. Target the same 17 files the Node script produces (table below). Sequence:

1. **Navigate to Workspace.** `browser_navigate({workspace_url})`. Resize to a desktop viewport (e.g., `browser_resize(1920, 1080)`) so charts render at full width.
2. **Handle login if needed.** The first run each session will land on SmartPM's login page. Call `browser_snapshot` — if you see login fields, stop and tell the user:
   > "SmartPM wants you to log in. Complete the login in the browser window, then tell me `logged in` and I'll continue." Resume on that signal. Subsequent captures in the same session should reuse the login.
3. **Summary Report.** On the Workspace page, find the "View Summary" button via `browser_snapshot` and `browser_click` it. Wait for the modal (`browser_wait_for`). Take a screenshot **of the modal content only** (use the `element`/`ref` form of `browser_take_screenshot` so you don't capture the dimmed overlay edges) and save as `{dated_folder}/screenshots/smartpm-summary-report.png`. Close the modal (press Escape or click the close button).
4. **Trends graphs.** `browser_navigate({trends_url})`. Wait for the first `APP-CHART-*` element to render. For each of the 16 components in the order below, scroll the element into view, snapshot it, and save to the listed filename via element-scoped `browser_take_screenshot`. If an element isn't returned by `browser_snapshot` (lazy-rendered), use `browser_evaluate` to scroll it into view first — `document.querySelector('APP-CHART-SPI-OVER-TIME').scrollIntoView({behavior: 'instant', block: 'center'})`.
5. **Wide charts.** `APP-DELAY-WATERFALL` and `APP-END-DATE-VARIANCE` extend past the viewport — scroll the chart's internal container to the right-most position before capturing so the latest data points are visible. `browser_evaluate` with `el.scrollLeft = el.scrollWidth` on the chart's inner scroll container handles this.
6. **Verify after each capture.** Between screenshots, re-check `browser_snapshot` to confirm the chart actually loaded (no spinner, no "no data" empty state). If empty, wait a few seconds and retry once before moving on.

### Step 3b: Capture via Node fallback

Only when MCP tools are absent:

```bash
node "{skill_dir}/references/capture-smartpm.js" \
  "{workspace_url}" "{trends_url}" "{dated_folder}/screenshots"
```

The script:
- Launches Chromium with a persistent profile at `~/.smartpm-playwright-profile/`
- On first run: opens a browser window, waits up to 5 min for manual SmartPM login
- Summary Report: navigates to Workspace, opens "View Summary" modal, captures as `smartpm-summary-report.png`
- Trend graphs: navigates to Trends > Graphs tab, captures each `.highcharts-container` individually:

| # | File | Chart |
|---|------|-------|
| 1 | `01-planned-vs-actual-percent-complete.png` | Planned VS Actual Percent Complete |
| 2 | `02-schedule-quality-grade-over-time.png` | Schedule Quality Grade Over Time |
| 3 | `03-project-health-index-over-time.png` | Project Health Index Over Time |
| 4 | `04-schedule-changes-over-time.png` | Schedule Changes Over Time |
| 5 | `05-schedule-delay-over-time.png` | Schedule Delay Over Time *(wide -- scroll right for latest)* |
| 6 | `06-end-date-variance.png` | End Date Variance *(wide -- scroll right for latest)* |
| 7 | `07-schedule-compression-index-over-time.png` | Schedule Compression Index Over Time |
| 8 | `08-velocity.png` | Velocity |
| 9 | `09-spi-over-time.png` | SPI Over Time |
| 10 | `10-activity-hit-rate.png` | Activity Hit Rate |
| 11 | `11-window-start-accuracy.png` | Window Start Accuracy |
| 12 | `12-window-finish-accuracy.png` | Window Finish Accuracy |
| 13 | `13-missing-logic.png` | Missing Logic |
| 14 | `14-average-total-float.png` | Average Total Float |
| 15 | `15-high-total-float.png` | High Total Float |
| 16 | `16-critical-path-percentage.png` | Critical Path Percentage |

Angular component tags (DOM order): `APP-CHART-PROGRESS-CURVE`, `APP-CHART-SCHEDULE-QUALITY-OVER-TIME`,
`APP-CHART-PROJECT-HEALTH`, `APP-CHART-SCHEDULE-CHANGES`, `APP-DELAY-WATERFALL`, `APP-END-DATE-VARIANCE`,
`APP-CHART-SCHEDULE-COMPRESSION`, `APP-CHART-VELOCITY`, `APP-CHART-SPI-OVER-TIME`, `APP-CHART-HIT-RATE`,
`APP-CHART-WINDOW-START-ACCURACY`, `APP-CHART-WINDOW-FINISH-ACCURACY`, `APP-MISSING-LOGIC`,
`APP-AVERAGE-TOTAL-FLOAT`, `APP-HIGH-TOTAL-FLOAT`, `APP-CRITICAL-PATH`

**Errors:** Timeout = network or wrong URL. 0 charts = page didn't render fully (retry). Missing Playwright = run `npx playwright install chromium` in references/.

### Step 4: Verify

Read the captured PNGs visually. Confirm:
- `smartpm-summary-report.png` shows the Summary Report modal with milestones, health index, and S-curve
- Each graph file shows the correct chart with data points

If any screenshot looks wrong (blank, login page, wrong project), inform the user and offer to retry that capture.

**SmartPM processing warning:** If this command is called within 30 minutes of XER upload, SmartPM may still be processing. Check the Workspace page status. If processing is still running, warn the user and offer to wait.

### Step 5: Report

Mark checklist complete. Report:
- Total screenshots captured (17)
- File paths and sizes
- SmartPM URLs used

---

## `email` -- Generate Update Email Draft

Generates the Westland schedule update email from XER data, previous email, and meeting transcript.

### Step 0: Read Project Context & Previous Update

Apply folder resolution. Read `project-context.html` for all config.

To find the previous update email: list all `YYYY-MM-DD` sibling folders, sort descending, skip the current folder, check each for `*-update-email.md`. Use the first match.

### Step 1: Check Inputs

Before proceeding, verify which inputs are present:

| Input | Location | Required |
|-------|----------|----------|
| Current XER | `{dated_folder}/*.xer` | REQUIRED -- cannot generate without it |
| Previous email | Previous `YYYY-MM-DD-update-email.md` | Recommended -- carry forward red flags/stalled tasks |
| Meeting transcript | `{dated_folder}/meeting/*.txt` or `.md` or `.docx` | Recommended -- mine for successes/issues |
| Screenshots | `{dated_folder}/screenshots/*.png` | Needed for sections 3 and 12 |

If XER is missing, stop: "No XER file found in `{dated_folder}`. Export the updated schedule and place the XER here before running `email`."

If any recommended input is missing, list what's absent and ask whether to proceed without it or locate it. Do not auto-proceed without telling the user.

### Step 2: Check Screenshots

Check for `screenshots/` folder with at least `smartpm-summary-report.png` and the files listed in `graph_screenshots` from project-context.html.

If screenshots are missing or incomplete, ask: "Screenshots are missing. Run `/schedule-update screenshots` now, or should I proceed without them?" If the user asks to run screenshots first, do so (run the `screenshots` workflow above), then continue.

### Step 3: Parse XER & Extract Metrics

Parse the XER using the `schedule-toolbox` skill. Calculate:

- **Days behind/ahead:** Compare projected Substantial Completion date to contractual completion. Use SC milestone early finish if present; otherwise use project end date from PROJECT table.
- **Gain/loss since last update:** Compare to previous email's days-behind figure.
- **Critical path items:** Activities with total float = 0 or near-zero.
- **Stalled tasks:** `TK_NotStart` status with early start before data date.
- **Slipping tasks:** Started but remaining duration suggests late finish.

### Step 4: Carry Forward from Previous Email

If a previous email exists, extract:
- Red flags list
- Stalled/slipping tasks
- Key items & issues

Ask the user: "These items were on last week's list. Which should carry forward?" Present as a multi-select (keep / remove / update each item).

### Step 5: Mine Meeting Transcript

If a transcript is provided, extract:
- **Successes** (completions, deliveries, milestones hit)
- **Issues/concerns** (delays, material problems, trade performance)
- **Recovery efforts** (acceleration plans, added crews, revised sequences)
- **New red flags or risks**

Present extracted items for confirmation: "I found these items in the meeting transcript. Which should go in the email?" Do not include without user confirmation.

### Step 6: Assemble Draft Email

Build using `{skill_dir}/references/email-template.md` for structure. The 12 sections in order:

1. **Project Info Header** -- project name, job number, contractual completion, projected SC date. Labels teal, values black.
2. **Days Behind/Ahead** -- from XER. Full line red (`#C94444`) if behind, green (`#3A9E6B`) if ahead.
3. **SmartPM Summary Report** -- embed `screenshots/smartpm-summary-report.png`. If missing, invoke `screenshots` workflow.
4. **Successes** -- from transcript extraction + user additions.
5. **Gain/Loss Narrative** -- calculated figure + user narrative. Full line colored.
6. **EOT/Recovery Status** -- from transcript + previous email + user input.
7. **Significant Logic Changes** -- prompt user for summary of changes made during update.
8. **SmartPM Changelog Link** -- from project-context.html `smartpm_changelog_url`.
9. **Red Flags** -- carried forward + new from transcript + user additions. Items in `**bold**` render bold + red.
10. **Stalled/Slipping Tasks** -- from XER analysis + carried forward + user additions. `**bold**` = red.
11. **Key Items & Issues** -- from transcript + previous email + user additions. `**bold**` = red.
12. **Performance Graphs** -- graph screenshots from `screenshots/`, in order from `graph_screenshots` in project-context.html.

Include closing paragraphs about Schedule Compliance Report and procurement spreadsheets as applicable.

### Step 7: Generate Editable HTML Preview

Instead of presenting the draft inline for section-by-section edits in chat, generate an editable HTML preview file. This is the canonical review artifact for both `email` and `report` — it's easier to edit than markdown and it renders exactly like the final email.

#### Carry forward from last week

**You are going back in time to last week's preview HTML** to carry state forward. Do this before generating this week's preview.

1. **Find last week's preview.** List every sibling `YYYY-MM-DD/` folder in the Schedules root, sort descending, skip the current dated folder. The most recent one that contains a `{PREV_DATE}-email-preview.html` is last week's preview. (If it only has a `.md` archive and no preview HTML — e.g. this project started using `report`/`email` only recently — treat it as "first update" and skip carry-forward.)

2. **Parse it.** `last = parse_email_html.parse_preview_html(prev_preview_path)`. The returned dict includes everything you need:
   - `last['days_behind']`, `last['gain_loss']` — pass as `previous_days_behind=` / `previous_gain_loss=` so metrics show the week-over-week strikethrough.
   - `last['gain_loss_narrative']`, `last['eot_recovery']`, `last['logic_changes']` — pass these (as a dict) as `previous_narratives=` so changed narrative fields render inline diffs.
   - `last['successes_full']`, `last['red_flags_full']`, `last['stalled_tasks_full']`, `last['key_items_full']` — full item dicts with status/date_archived.
   - `last['attachments']` — full attachment dicts with status/date_archived.
   - `last['custom_paragraphs']` — closing paragraphs and their checked state.
   - `last['changes_report']` — whether last week had the changelog toggled on (useful default for this week).

3. **Reconcile list items.** For each list field (`successes`, `red_flags`, `stalled_tasks`, `key_items`), generate this week's plain-text list (from the transcript, XER, or Claude's own revision), then call:
   ```python
   red_flags_new = carry_forward.reconcile_items(
       last['red_flags_full'], this_week_red_flag_texts, today_iso
   )
   ```
   This fuzzy-matches (via `difflib` + word-overlap, so `"SPD continues to add scope."` still matches `"SPD continues to add scope. Another note..."`), attaches `previous_text` where text differs, and marks dropped items `removed`/`archived` appropriately.

4. **Reconcile attachments.** Build `fresh_filenames` by globbing this week's dated folder for `*.pdf`, `*.xlsm`, and `*.xer` (skip Office temp lock files starting with `~$`), then:
   ```python
   attachments_new = carry_forward.transition_attachments(
       last['attachments'], fresh_filenames, today_iso
   )
   ```
   This normalizes filenames by stripping ISO dates (`YYYY-MM-DD` etc.) so `Report 01 ... 2026-04-08.pdf` matches `Report 01 ... 2026-04-15.pdf` as the same recurring attachment — not a wall of new items each week.

5. **Carry paragraphs forward directly.** `custom_paragraphs=last['custom_paragraphs']`. Closing paragraphs are toggle-only (no diff semantics, no age pruning). The user re-edits / re-toggles them in this week's preview.

6. **Default the changes-report toggle.** If `last['changes_report']['include']` was True, default this week to True as well. Filename defaults to the date-prefixed form (`{date} Schedule Update Email (Change Report).pdf`) unless the user had customized it.

If no prior preview exists, omit the `previous_*` kwargs — the generator falls back to no-diff rendering, all items start as `active` / `new`, and the changes-report toggle defaults to off.

On save, the parser drops `<del>` content (phantom deletions) and unwraps `<ins>` (keeps the new text), so the archive markdown stays clean and `generate_email_msg.py` receives plain strings.

If there is no prior preview, the generator falls back to defaults: no list items, and the two default custom paragraphs (Schedule Compliance Report and Procurement/Progress Update Sheets) driven by `include_compliance_report` / `include_procurement_sheets`. Attachments bootstrap from a fresh glob of `*.pdf`, `*.xlsm`, and `*.xer` in the dated folder.

#### Changed narrative fields

Narrative blocks (`gain_loss_narrative`, `eot_recovery`, `logic_changes`) often get rewritten each week. Diff each one against last week's value from the parser — if the text changed (trim + case-insensitive compare), add the field name to a set and pass it to the generator as `changed_narrative_fields`. Those fields render with a **green dashed outline + light green background** so the reviewer sees at a glance what Claude touched. Any live in-browser edit also flips the field to green via a JS input listener, so the "touched this week" state stays visible as the colleague iterates.

#### State transitions (git-diff semantics)

Each list item and attachment tracks `status ∈ {active, new, removed, archived}` plus `date_archived`. The visual in the preview matches:

| Status   | Dashed outline | Background   | Meaning |
|----------|----------------|--------------|---------|
| active   | gray           | off-white    | Normal — in this email |
| active + `previous_text` | **amber** | light amber | **Edited** — text was tweaked this update; renders inline diff (`<ins>` green-underline, `<del>` red-strikethrough) |
| new      | green          | light green  | Added this update |
| removed  | red            | light red    | Unchecked this update; was included previously |
| archived | gray           | (collapsed sub-list) | Still removed after another update — hidden under a caret |

`transition_items()` applies these rules week-over-week:

- `new`      + checked      → `active`   (settles after one update)
- `new`      + unchecked    → `removed`  (added then cancelled)
- `active`   + unchecked    → `removed`
- `removed`  + still unchecked → `archived` (set `date_archived` = today)
- `removed`  + re-checked   → `active`   (user put it back — treated as a revert, no green badge)
- `archived` + re-checked   → `active`   (un-archived — also a revert, no green badge)
- `archived` + still unchecked → `archived` (date_archived preserved)

**90-day archive prune:** archived items with `date_archived` older than 90 days are dropped entirely on transition. Applies to list items (`red_flags`, `successes`, `stalled_tasks`, `key_items`) and attachments. `custom_paragraphs` are NOT age-pruned — they're a curated list. Override via the `max_archived_days` kwarg on `transition_items()` / `transition_attachments()` if needed.

Same rules apply to attachments. The archived date is shown inside the item's card when the user expands it. Archived items render in a **separate sub-list** below the main list (own numbering) so they don't merge back into the main numbering when the caret is opened.

#### Output file

Run `references/generate_email_preview_html.py` with the assembled data. Output: `{dated_folder}/{YYYY-MM-DD}-email-preview.html`.

The preview is a self-contained HTML file with:

- **Production styling** for every email section (Days Behind label teal, value colored red/green).
- **Per-item cards:** click into any list item (red flag, success, etc.) and a card expands below with Include checkbox, Bold/Italic/Priority buttons, ↑/↓ reorder, × Remove. Unchecked items stay in the list (carry to next week) but are excluded from this email.
- **Git-diff colors** on the dashed edit outline: green for new, red for removed, gray for archived (see table above).
- **Archived caret:** items unchecked for more than one update collapse under a "▶ N archived" caret at the bottom of each list.
- **Sticky WYSIWYG toolbar** for narrative blocks (Bold / Italic / Priority); keyboard shortcuts Ctrl+B, Ctrl+I, Ctrl+Shift+P. Markdown shortcuts `**bold**` and `==priority==` still work.
- **Custom closing paragraphs:** editable list with add / remove / reorder, each with its own include checkbox and editable label + body.
- **Attachments section** below the email body: checkbox + editable filename + reorder/remove. "+ Browse files" opens a file picker (defaults to the folder the HTML lives in, so browsers open in the dated folder). "+ Add by name" for typing a filename.
- **Save Edits** button downloads the edited HTML — the user saves it back over the same file.
- **Copy for Claude** button copies a JSON snapshot to the clipboard as a fallback.
- Embeds screenshots as **relative file paths** so the browser and the parser both resolve to `{dated_folder}/screenshots/`.

Tell the user:
> "Preview at `{path}`. Click into any list item to see its card (Include / B / I / ! / ↑ / ↓ / × Remove). Items turn **green** when newly added, **red** when unchecked (they carry to next week), and collapse under a caret after another update. Use the attachments card at the bottom to add or remove files. When you're done: click **Save Edits**, save the download over this file, then tell me `done`."

When the user says `done`, read the (now-edited) HTML via `references/parse_email_html.py` and continue to Step 8. The parser returns both:
- Filtered lists (strings of checked, non-archived items) and `attachment_paths` — ready for `generate_email_msg.py`.
- Full dicts (`red_flags_full`, `attachments`, etc.) — persisted into next week's preview via `carry_forward`.

### Step 8: Save Archive Markdown

Save `{dated_folder}/YYYY-MM-DD-update-email.md` from the parsed HTML values:

```yaml
---
date: YYYY-MM-DD
days_behind: {number}
gain_loss: {+/- days}
projected_completion: {date}
screenshots_captured: true/false
---
```

Followed by:
- **## Update Email** -- the full 12-section email content
- **## Project Log** -- cumulative notes on delays, late starts, impacts, decisions. Each week adds a dated entry. Do not overwrite previous entries.

The markdown is the archive/audit record and powers next week's carry-forward logic. The HTML preview is the review artifact. Keep them in sync.

Update `project-context.html` if any config changed (recipients, attachments, graphs).

Then offer to run the `draft` workflow to push the approved content to Outlook.

#### Email changelog PDF attachment

If the parsed preview has `changes_report.include=True`, the `draft` workflow (and the `report` command) must also:

1. Call `references/generate_changes_report_html.generate_changes_report_attachment(...)` with:
   - `output_path` = `{dated_folder}/{changes_report.filename}` — default filename is `"{YYYY-MM-DD} Schedule Update Email (Change Report).pdf"`. The ".pdf" extension triggers HTML generation followed by headless-Chromium PDF conversion (via `references/html-to-pdf.js`); the intermediate HTML is deleted on success so only the PDF remains in the dated folder (`keep_html=True` overrides for debugging, and HTML is always preserved if PDF conversion fails). A ".html" filename skips the PDF step. The "Email (Change Report)" wording is deliberate — distinct from the SmartPM **schedule** changelog, this tracks what changed in the email's content (new items, edited items, removed items).
   - The same lists (with `previous_text` carried via the parser), narratives, and attachments passed to the preview.
   - `previous_narratives` = dict of last week's narrative values (so the report renders narrative-level diffs).
   - `changed_narrative_fields` = same set passed to the generator.
2. Append the resulting PDF's absolute path to `attachment_paths` before calling `generate_email_msg.generate_update_email_msg(...)`.
3. Pre-flight: if `references/node_modules/playwright` is missing, run `npm install` in `references/` first (same pre-flight as `screenshots`). On PDF-conversion failure (missing Node, no Chromium, timeout), fall back to attaching the `.html` alongside — the HTML is still saved, and a warning is surfaced to the user.

The PDF uses the same visual vocabulary as the preview — green for new, red strikethrough for removed, amber dashed outline on edited items with inline word-level diff that preserves bold/italic/priority formatting. It's read-only, paginated Letter-size, and safe to forward.

---

## `report` -- Colleague Post-Meeting Flow (Steps 6–10)

End-to-end conversational flow that takes a colleague from "meeting is done" to "Outlook draft in Drafts folder." This is the preferred entry point for anyone who is not Camron. It covers steps 6–10 of the full pipeline, with an **editable HTML preview** (not markdown) as the review artifact.

### Step 1: Resolve Folder

Apply folder resolution from **Shared Setup**.
- Default target folder: `{Schedules root}/{today's date in YYYY-MM-DD}/`
- If today's folder does not exist, list the most recent 3 dated folders and ask: "I don't see a folder for today. Is this week's update in `{most_recent}` or should I create today's folder first? (Run `copy` to create today's folder.)"
- If today's folder exists but is empty or missing the XER, note what's missing and ask whether to proceed or wait for the human steps (5–9) to finish.

Read `project-context.html`. If missing, stop with the standard error.

### Step 2: Run Screenshots If Needed

Check for all required PNGs in `{dated_folder}/screenshots/`:
- `smartpm-summary-report.png`
- every file listed in `graph_screenshots` from `project-context.html`

If any are missing, say: "I need to capture SmartPM graphs first — running screenshots now." Then execute the `screenshots` workflow (above) before continuing.

If SmartPM was uploaded less than ~30 minutes ago, warn the colleague it may still be processing and offer to wait.

### Step 3: Transcript Or Q&A?

Ask the colleague:
> "Do you have the meeting transcript? Drop it in `{dated_folder}/meeting/` and I'll mine it for successes, red flags, and key items. Otherwise I'll compare this week's XER to last week's and ask you questions instead."

Branch based on response:

#### 3a. **Has transcript** — Transcript-driven fill

1. Read the transcript from `{dated_folder}/meeting/` (`.txt`, `.md`, `.docx`).
2. Extract successes, issues, recovery efforts, red flags using the `email` workflow's "Mine Meeting Transcript" logic.
3. Present extracted items for confirmation before accepting them.

#### 3b. **No transcript** — XER-driven Q&A

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

### Step 4: Carry Forward From Previous Email

Find the previous `*-update-email.md` (same lookup as the `email` workflow). Show the colleague last week's Red Flags / Stalled Tasks / Key Items and ask which carry forward, which resolve, which update.

### Step 5: Calculate Metrics From XER

Using `schedule-toolbox`, compute:
- Days behind/ahead (vs. `contractual_completion`)
- Gain/loss vs. last week's days-behind figure

These populate the colored status lines in the email. They come from the XER — do not ask the colleague for them.

### Step 6: Generate Editable HTML Preview

Run the shared preview generation step — same as `email` Step 7. Output: `{dated_folder}/{YYYY-MM-DD}-email-preview.html`.

Tell the colleague:
> "Preview at `{path}`. Open it in your browser, edit any section in place, and when you're happy click **Save Edits** → save the download on top of the file (same name, same folder) → tell me `done`. I'll then create the Outlook draft. Tip: wrap a list item in `**double asterisks**` to make it bold + red in the email."

### Step 7: Wait For "done", Then Draft

When the colleague says `done`, read the edited HTML via `references/parse_email_html.py`, call `references/generate_email_msg.py` to create the Outlook draft, write the archive markdown (`{dated_folder}/{YYYY-MM-DD}-update-email.md`), and report:

> "Draft saved to Outlook Drafts — open Drafts in classic or new Outlook, review one more time, and click Send."

If the HTML file looks unchanged (no edits detected) or fails to parse, surface the problem and ask whether to proceed with the unedited draft.

---

## `draft` -- Create Outlook Draft

Creates the Outlook draft from the approved email content. Requires the edited HTML preview (and/or the archive markdown) for the current dated folder to already exist (run `email` or `report` first).

### Step 1: Locate Source File

Prefer the edited HTML preview: `{dated_folder}/{YYYY-MM-DD}-email-preview.html`. Read it via `references/parse_email_html.py` to extract the reviewed values.

If the HTML preview is missing, fall back to `{dated_folder}/{YYYY-MM-DD}-update-email.md` (the archive markdown). If both are missing:
> "No update email file found for today's folder. Run `/schedule-update email` or `/schedule-update report` first."

### Step 2: Generate Draft

Read `{skill_dir}/references/generate_email_msg.py`. The script:
- Builds an HTML email body (Arial font, inline styles, Outlook Word-renderer compatible)
- Embeds screenshots as inline CID images hyperlinked to SmartPM URLs
- Attaches the files listed in the preview's Attachments card (parser returns `attachment_paths` — checked & non-archived only)
- Includes the Westland email signature (logo, name, title, office phone, optional mobile)
- Saves the draft to Outlook Drafts via COM automation

**Pre-conditions:**
- Classic Outlook must be open (not just installed -- open it from Start menu for Exchange sync)
- `pywin32` must be installed (`pip install pywin32`)

Run the script. If `pywin32` is missing, prompt: "Install pywin32 with `pip install pywin32`, then retry." If COM fails entirely, fall back to `generate_email_docx.py` and inform the user.

### Step 3: Confirm

Tell the user: "Draft saved to your Outlook Drafts folder -- open Drafts in new Outlook, review, and click Send."

---

## `status` -- Pipeline Status

Shows where the project is in the weekly update pipeline based on what files exist.

### Detection Logic

| Check | Indicates |
|-------|-----------|
| Today's dated folder exists | Step 1 (copy) done |
| `{dated_folder}/*.xer` exists | Export done (step 5) |
| `{dated_folder}/meeting/` has files | Transcript copied (step 7) |
| `{dated_folder}/screenshots/` has all required PNGs | Screenshots done (step 10) |
| `{dated_folder}/YYYY-MM-DD-email-preview.html` exists | Email preview generated (step 11) |
| `{dated_folder}/YYYY-MM-DD-update-email.md` exists | Email archived after review |
| Outlook draft exists | Draft created (step 13) |

Report each phase as DONE / PENDING / NOT STARTED, and name the recommended next step.

---

## No-Arg Entry -- Phase Detection

When invoked without a command:

1. Resolve the Schedules root and read `project-context.html`
2. Determine the current dated folder (today's date or most recent existing)
3. Run the detection logic from `status` above
4. Based on the phase, route automatically:
   - If no dated folder for today → "Looks like you haven't started the update yet. Run `/schedule-update copy` to set up today's folder."
   - If folder exists but no XER → "Folder is set up. Export the schedule and drop the XER in `{path}`."
   - If XER exists but no screenshots → "XER is here. Run `/schedule-update screenshots` to capture SmartPM graphs."
   - If screenshots exist but no email → "Screenshots are ready. Run `/schedule-update email` to generate the markdown draft, or `/schedule-update report` for the guided colleague flow with an editable HTML preview."
   - If email exists but no Outlook draft → "Email draft is saved. Run `/schedule-update draft` to create the Outlook draft."
   - If draft created → "Draft is in Outlook. Send when ready."

---

## Full Pipeline Reference

| # | Step | Owner | Command |
|---|------|-------|---------|
| 1 | Copy schedule folder for today's date | Agent | `copy` |
| 2 | Email reminder to get Excel update file | Human | -- |
| 3 | Update schedule using Excel file | Human | -- |
| 4 | Make corrections, discussion, complete update | Human | (in meeting) |
| 5 | Export schedule files | Human | -- |
| 6 | Upload XER to SmartPM | Human | -- |
| 7 | Copy meeting transcript to meeting folder | Human | -- |
| 8 | Export PDF attachments from schedule software | Human | -- |
| 9 | Create next week's Excel files | Human | -- |
| 10 | Capture SmartPM graphs for email | Agent | `screenshots` |
| 11 | Generate update email draft | Agent | `email` |
| 12 | Review email draft | Human | -- |
| 13 | Create Outlook draft | Agent | `draft` |
| 14 | Send email | Human | -- |

Colleague-friendly shortcut: `report` covers rows 10–13 in a single guided conversation (with HTML preview for step 12 instead of markdown).

---

## Reference Files

All reference files live in `references/` within this skill directory.

| File | Purpose |
|------|---------|
| `references/email-template.md` | Full email template -- 12 sections, formatting rules, attachment list |
| `references/generate_email_msg.py` | Outlook draft via COM automation. Requires `pywin32` and classic Outlook open. |
| `references/generate_email_docx.py` | Fallback: .docx output if Outlook unavailable. Requires `python-docx`. |
| `references/generate_email_preview_html.py` | Builds the **editable HTML preview**. Self-contained file with per-item cards (git-diff states), attachments picker, custom closing paragraphs, WYSIWYG toolbar, Save Edits download, Copy for Claude clipboard export. Includes an HTML-aware live diff on blur so bold/italic/priority formatting survives edits. |
| `references/parse_email_html.py` | Reads an edited preview HTML back into a Python dict. Returns both filtered (email-ready strings) and full (carry-forward dicts with status/date_archived) shapes. Also extracts the `changes_report` option (include + filename). |
| `references/carry_forward.py` | Helpers `transition_items()`, `transition_attachments()`, and `reconcile_items()` — apply week-over-week state transitions (active → removed → archived, etc.) and compute previous_text for edited items via fuzzy match. |
| `references/generate_changes_report_html.py` | Builds the **Schedule Update Email Changelog** as HTML (metrics + narrative diffs + list diffs with inline word-level diff + attachment deltas). Entrypoint `generate_changes_report_attachment(output_path, ...)` handles both `.html` and `.pdf` outputs — the latter triggers `html-to-pdf.js` for Chromium-based conversion. Attached to the Outlook draft when `changes_report.include=True`. |
| `references/html-to-pdf.js` | Playwright/Node script that renders a local HTML file as a Letter-size PDF with `print` CSS media emulated. Reuses the same `node_modules/playwright` install as `capture-smartpm.js`. |
| `references/westland-logo.png` | Email signature logo (229x108 RGBA) |
| `references/capture-smartpm.js` | Playwright script -- captures 17 SmartPM screenshots. Run with Node.js. |
| `references/package.json` | Node.js dependencies for Playwright. Run `npm install` in `references/` on first use. |
| `references/checklist-template.md` | Template for the progress checklist written to each project's screenshots/ folder. |
| `references/Master Schedule Update Email Example.docx` | Original Westland email example (Neiafu Tonga Temple) for reference |
| `references/Schedule Update Email Procedure.docx` | Original Westland procedure document for reference |
