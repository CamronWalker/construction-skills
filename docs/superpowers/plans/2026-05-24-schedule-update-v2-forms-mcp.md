# Schedule-update v2 (Forms MCP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `scheduling/skills/schedule-update/` in lockstep with the deployed `westland-forms/weekly-schedule-update-email` v2 Worker schema, eliminate dead code from the cloud-editor migration, promote schedule-toolbox helpers into the colleague-facing flow, and add a phase-transition re-read rule. Single coherent PR; plugin version bumps to 6.0.0.

**Architecture:** Skill-side catch-up to the v2 Worker schema. No Worker changes. v2 introduces recipients arrays, `days_metric`/`gain_loss` objects, `closing_paragraphs`/`closing_salutation`, attachment `name`/`procore`, `include_changes_report`/`changes_report_filename`, item `edited` flag, `key_items_archived` as a separate list (archived state isolated). SmartPM fetching for the email pipeline moves entirely server-side (Worker enqueues async after seed POST; finalize payload returns `graphs.{slug}.html` SVG chunks). Local skill stacks chunks and rasterizes one PNG via `html_to_png.cjs`.

**Tech Stack:** Python 3 stdlib (no new deps), Node (existing `html_to_png.cjs` + Playwright for rasterization), unittest, JSON schema validation via Worker round-trip.

**Spec reference:** [docs/superpowers/specs/2026-05-24-schedule-update-v2-forms-mcp-design.md](docs/superpowers/specs/2026-05-24-schedule-update-v2-forms-mcp-design.md)

**Version bump strategy:** Task 1 bumps `scheduling/.claude-plugin/plugin.json` to `"6.0.0-dev"` (touches only that file — the pre-commit hook's "excluding plugin.json itself" exemption applies). Subsequent tasks can edit any `scheduling/` file freely because the `-dev` suffix exempts them. Task 24 strips `-dev` → `"6.0.0"` and bumps `marketplace.json` in lockstep (final commit touches only those two files, so the hook is again satisfied).

---

## File Structure

### Created
- `scheduling/skills/schedule-update/phases/_render_graphs.md` — internal phase doc; renamed-and-rewritten from `phases/screenshots.md`. Stacked-PNG rasterization recipe; no SmartPM MCP recipes.

### Modified
- `scheduling/CLAUDE.md` — "Email JSON shape" section replaced with v2 verbatim block; "Drive existing scripts" section gains cross-skill subsection.
- `scheduling/.claude-plugin/plugin.json` — version bump (twice: `5.6.2` → `6.0.0-dev` in Task 1, → `6.0.0` in Task 24).
- `.claude-plugin/marketplace.json` — scheduling entry version → `6.0.0` (Task 24).
- `scheduling/skills/schedule-update/SKILL.md` — re-read rule, command matrix (drops `screenshots`), pipeline reference table renumbered.
- `scheduling/skills/schedule-update/phases/copy.md`, `email.md`, `draft.md`, `report.md`, `procore.md`, `status.md`, `_carry_forward.md`, `_attachments.md` — each gains identical top-of-file preamble. Internal updates per v2 field names where the file references them.
- `scheduling/skills/schedule-update/references/carry_forward.py` — `reconcile_items` v2 rows; new `reconcile_key_items`; `transition_attachments` v2 fields; remove `transition_items`.
- `scheduling/skills/schedule-update/references/email_draft_io.py` — `SUPPORTED_VERSIONS = {2}`; v2-aware `editorial_to_kwargs`; helpers `_format_recipients`, `_join_closing_paragraphs`, `_attachment_names_for_email`.
- `scheduling/skills/schedule-update/references/generate_email_eml.py` — `_build_html_body` (in `generate_email_msg.py`) signature changes; docstring HTML tag canon updated.
- `scheduling/skills/schedule-update/references/generate_email_msg.py` — `_build_html_body` gains `closing_paragraphs_html` kwarg, drops `closing_line`/`custom_paragraphs`; docstring HTML tag canon updated.
- `scheduling/skills/schedule-update/references/generate_changes_report_html.py` — read v2 fields; exclude `key_items_archived`.
- `scheduling/skills/schedule-update/tests/test_carry_forward.py` — v2 row shapes + `reconcile_key_items` cases.
- `scheduling/skills/schedule-update/tests/test_email_draft_io.py` — v2 fixture loading + `editorial_to_kwargs` v2 cases.
- `scheduling/skills/schedule-update/tests/test_email_eml.py` — `closing_paragraphs_html` kwarg cases.
- `scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json` — regenerated as v2.

### Deleted
- `scheduling/skills/schedule-update/references/generate_email_docx.py` — orphaned (no phase references it).
- `scheduling/skills/schedule-update/references/Master Schedule Update Email Example.docx` — legacy reference doc.
- `scheduling/skills/schedule-update/references/Schedule Update Email Procedure.docx` — legacy reference doc.
- `scheduling/skills/schedule-update/phases/screenshots.md` — renamed to `_render_graphs.md`.

---

## Task 1: Version bump to 6.0.0-dev (exempts subsequent commits from the pre-commit hook bump check)

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json:3`

- [ ] **Step 1: Edit plugin.json version field**

Change line 3:
```json
"version": "5.6.2",
```
to:
```json
"version": "6.0.0-dev",
```

- [ ] **Step 2: Verify nothing else is staged**

Run: `git status`

Expected: only `scheduling/.claude-plugin/plugin.json` is modified. No other files. If other files are modified, do not include them in this commit — handle them in their own task.

- [ ] **Step 3: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json
git commit -m "$(cat <<'EOF'
chore(scheduling): bump version to 6.0.0-dev for v2 Forms MCP rewrite

Subsequent commits in this branch will edit scheduling/ files freely;
the -dev suffix exempts them from the pre-commit version-bump hook
until the final commit strips it back to 6.0.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds (only plugin.json changes, so the hook's "files outside plugin.json" check returns no offenders).

---

## Task 2: Rewrite scheduling/CLAUDE.md "Email JSON shape" section to v2

**Files:**
- Modify: `scheduling/CLAUDE.md:118-242`

- [ ] **Step 1: Read the current content of lines 118–242 to identify exact boundaries**

Run: `Read scheduling/CLAUDE.md offset=118 limit=125`

Identify the exact start (`## Email JSON shape — single source of truth`) and the exact end (the historical note paragraph ending `…there is no legacy HTML parser to fall back on.`).

- [ ] **Step 2: Replace the entire section**

Use the `Edit` tool with `old_string` = the entire current section (lines 118–242) and `new_string` = the v2 canonical-shape block below. Copy this block verbatim:

````markdown
## Email JSON shape — single source of truth

The weekly schedule email pipeline (`schedule-update` skill) round-trips through one JSON artifact: `{dated_folder}/{YYYY-MM-DD}-email.json`. Three places handle that JSON:

| Direction | Who | Where |
|-----------|-----|-------|
| Write | Worker (`westland-mcps`) | `finalize_weekly_schedule_update_email` MCP tool — emits the working JSON the cloud editor produced. |
| Read (local) | Python | [`email_draft_io.py`](skills/schedule-update/references/email_draft_io.py) `load_draft(path)` — validates top-level shape, raises `DraftError` on drift. |
| Read (browser) | SPA + Trix editor | Hydrated server-side from the same JSON; mutates `this_week.*` via `PUT /editorial`. |

**The Worker is the validator of record.** The canonical schema lives at:

- Human: <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema>
- Machine: <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema.json>

The skill emits this shape into its seed; the Worker validates on `generate_weekly_schedule_update_email_draft` and on every `PUT /editorial`. **If a `generate_weekly_schedule_update_email_draft` call returns 422 with a `violations[]` array, refetch the live schema from the URL above — the Worker is authoritative and this CLAUDE.md may have drifted.** Violations include `fuzzyHint` suggestions for typo fixes; surface them literally to the colleague.

### The canonical shape (v2)

```jsonc
{
  "version":     2,
  "report_date": "YYYY-MM-DD",
  "project_info": {
    "project_name": "...",
    "job_number":   "...",
    "contractual_completion": "...",
    "projected_completion":   "..."
  },

  "this_week": {
    "subject": "...",
    "to_recipients": [ { "name": "...", "email": "..." } ],
    "cc_recipients": [ { "name": "...", "email": "..." } ],

    "days_metric": { "direction": "behind" | "ahead", "value": int },
    "gain_loss":   {
      "direction": "loss" | "gain",
      "value":     int,
      "narrative": "...",
      "narrative_changed": bool
    },

    "successes":          [/* item rows */],
    "red_flags":          [/* item rows */],
    "stalled_tasks":      [/* item rows */],
    "key_items":          [/* item rows */],
    "key_items_archived": [/* item rows — status="archived" */],

    "eot_recovery":          "...",
    "logic_changes":         "...",
    "smartpm_changelog_url": "https://...",

    "closing_paragraphs": [
      { "label": "Questions", "checked": true, "text": "<div>Please let me know if you have any questions.</div>" }
    ],
    "closing_salutation": "Thanks,",

    "signer_name":  "...",
    "signer_title": "...",
    "signer_mobile": "...",

    "attachments": [
      {
        "name":     "Report 01 - Foo.pdf",
        "ext":      "pdf",
        "checked":  true,
        "procore":  false,
        "status":   "active",
        "prev_idx": 0
      }
    ],
    "skip_procore":            false,
    "include_changes_report":  true,
    "changes_report_filename": "...",

    "graph_order": [
      "01-planned-vs-actual-percent-complete",
      "06-end-date-variance",
      "07-schedule-compression-index-over-time",
      "08-velocity",
      "09-spi-over-time",
      "10-activity-hit-rate",
      "11-window-start-accuracy",
      "12-window-finish-accuracy",
      "smartpm-summary-report"
    ]
  },

  "last_week": { /* identical shape; frozen verbatim copy from prior week's this_week; null for week-1 of v2 */ },

  "graphs": {
    "01-planned-vs-actual-percent-complete": { "html": "<svg…>…", "data": { } },
    "06-end-date-variance":                   { "html": "<svg…>…", "data": { } }
  }
}
```

### Item row shape — used in `successes` / `red_flags` / `stalled_tasks` / `key_items` / `key_items_archived`

```jsonc
{
  "text":     "<div>Building slab pour complete; field has <b>moved past</b> the slab-prep front.</div>",
  "status":   "active",
  "checked":  true,
  "edited":   false,
  "prev_idx": 0
}
```

Three things to know about item rows:

1. **`status='archived'` belongs ONLY in `key_items_archived`.** The other four lists (`successes`, `red_flags`, `stalled_tasks`, `key_items`) follow active → removed → dropped lifecycle: items that fall out simply transition to `status='removed'` for one week and then drop entirely from the next week's seed. The 90-day archived-prune is `key_items`-only.
2. **`prev_idx` is an int|null.** Diff overlays in the editor and "strikethrough-previous-metric" badges in the `.eml` walk `this_week.<list>[i]` → `last_week.<list>[this_week.<list>[i].prev_idx]`. There is no denormalized `previous_text` field.
3. **`text` is HTML, not Markdown.** Four supported tags pass through verbatim into the email body:
   - `<b>...</b>` — bold
   - `<i>...</i>` — italic
   - `<span style="background-color: #FFF4B8">...</span>` — highlight (light yellow)
   - `<span style="color: #9B2C2C">...</span>` — important (Westland brand red)

   The Trix editor in the cloud surface emits these inline-style spans verbatim; the `.eml` builder passes them through without conversion.

### Attachment row shape

```jsonc
{
  "name":     "Report 01 - Foo.pdf",
  "ext":      "pdf",
  "checked":  true,
  "procore":  false,
  "status":   "active",
  "prev_idx": 0
}
```

Attachments have no `archived` status and no `date_archived` field. They follow active → removed → dropped, same as the four list types above.

### The Procore fields are load-bearing

`this_week.attachments[].procore` and `this_week.skip_procore` drive the Procore Documents upload via [`phases/procore.md`](skills/schedule-update/phases/procore.md). They are not cosmetic. Missing them in the JSON snapshot means the colleague's choice ("don't upload the owner summary to a public folder") is lost — that's a privacy bug, not a UX nit.

### `last_week` is frozen

When `phases/draft.md` builds this week's seed, it takes the *prior* week's `{prev_date}-email.json` and copies the entire `this_week` subtree into the new `last_week` slot — unchanged for the lifetime of this week's draft. The SPA renders strikethroughs on changed metrics, diff badges on changed item text, and visual chips on attachments that moved between weeks, all by reading `last_week`. The local `.eml` builder reads `last_week.days_metric` / `last_week.gain_loss` to render strikethrough-previous-metric badges on the colored status lines.

### Recipients arrays render to "Name <email>" strings

`this_week.to_recipients` / `cc_recipients` are arrays of `{name, email}` objects on disk and in the Worker. The local `.eml` builder and the COM-Outlook path both need the legacy `Name <email>; Other <email2@x>` string form. `email_draft_io.editorial_to_kwargs()` flattens the arrays at the seam.

### `days_metric` and `gain_loss` are objects, not signed ints

v1's signed `days_behind` int became `days_metric: {direction: "behind"|"ahead", value: int}`. Same pattern for `gain_loss`, which v2 merges with `gain_loss_narrative` and adds a `narrative_changed` bool to drive the editor's "changed since last week" highlight.

`editorial_to_kwargs()` collapses these to signed ints for the existing `.eml` / COM builder kwargs:

```python
days_behind = +days_metric.value if days_metric.direction == 'behind' else -days_metric.value
gain_loss   = -gain_loss.value   if gain_loss.direction   == 'loss'   else +gain_loss.value
```

### Closing paragraphs and salutation

v1's `closing_line` ("Please let me know if you have any questions.") and `custom_paragraphs` array merged into one v2 `closing_paragraphs` array. Each entry is `{label, checked, text}` and renders as HTML in the email body. The first entry (Westland default) is the "Questions" line above.

`closing_salutation` (v1: `salutation`) is rendered as-is above the signer block.

### When you change the shape

The Worker schema is the source of truth. To extend the shape:

1. **Bump `version`** in the Worker's schema + this doc + the Worker's validator. The skill's seed-emission code writes the new version.
2. **Update the Worker** — add the field to the validator, the editor SPA's render path, and the `PUT /editorial` ingest. Coordinate via a PR in `westland-mcps`.
3. **Update the skill in lockstep:**
   - `email_draft_io.editorial_to_kwargs` — pass the new field through to the `.eml` builder kwargs.
   - `generate_email_msg._build_html_body` — render the field if it affects the email body.
   - `carry_forward.reconcile_items` / `transition_attachments` — handle it across week boundaries if it's per-row state.
4. **Add a test** to `tests/test_email_draft_io.py` asserting the new field round-trips through `editorial_to_kwargs`.
5. **Run** `python -m unittest discover -s scheduling/skills/schedule-update/tests` before claiming done.

### Historical note

v1 of this shape (signed-int metrics, semicolon recipient strings, `custom_paragraphs` / `closing_line` / `salutation`, attachment `filename` + `share_to_procore`, four-list `archived` status, `date_archived` everywhere, `changes_report: {include, filename}` object) lived from 2026-05 until scheduling 6.0.0 landed. The Worker rejects v1 seeds with `SEED_VERSION_TOO_OLD` (422).

The pre-cloud-editor `*-email-preview.html` round-trip is gone since v1 (`generate_email_preview_html.py`, `parse_email_html.py`, and `tests/test_email_preview_html.py` were removed). The seed-emission path in `phases/draft.md` reads `{prev_date}-email.json` only — there is no legacy HTML parser to fall back on.
````

- [ ] **Step 3: Commit**

```bash
git add scheduling/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(scheduling): rewrite Email JSON shape section for v2 Forms MCP

Replace the v1 shape (signed-int metrics, semicolon recipients,
custom_paragraphs/closing_line/salutation, attachment filename+share_to_procore,
four-list archived status, date_archived everywhere) with the v2 canonical
shape from the deployed westland-forms Worker schema.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds (plugin.json version is `6.0.0-dev`, hook exempts).

---

## Task 3: Add cross-skill scripts discipline to scheduling/CLAUDE.md

**Files:**
- Modify: `scheduling/CLAUDE.md` (append a new subsection inside the existing "Drive the existing scripts — don't wrap them" section).

- [ ] **Step 1: Locate the insertion point**

Run: `Grep "Where the per-slug recipes live" scheduling/CLAUDE.md -n`

The new subsection is inserted **immediately before** the existing `### Where the per-slug recipes live` subsection (so the new content sits inside the "Drive the existing scripts" section).

- [ ] **Step 2: Insert the new subsection**

Use the `Edit` tool to insert this content immediately before `### Where the per-slug recipes live`:

````markdown
### Cross-skill scripts: same rule, with Glob for path resolution

The "drive existing scripts, don't wrap them" rule extends to scripts in **sibling skills** of the scheduling plugin. The week-over-week XER comparison helpers in `schedule-toolbox/references/` (`xer_compare.py`, `update_review.py`) are used by `schedule-update`'s `phases/report.md` and `phases/draft.md`.

**Resolve the path with Glob, then drive the script as-is.** Never:
- Hardcode `~/.claude/plugins/cache/...` (the version segment changes).
- Hardcode the repo path `C:\Users\camron\code\construction-skills\...` (only works on one machine).
- Copy the script into `schedule-update/references/` to avoid the cross-skill path (two copies drift).
- Write a one-off Python re-implementation of `compare_schedules` "because it's easier" (it isn't, and it diverges silently from the canonical implementation).

The recipe pattern in `phases/report.md` step 3b is the template. Apply it to any future cross-skill helper need.

````

(Note the trailing blank line in the insertion — keeps a blank line between the new subsection and `### Where the per-slug recipes live`.)

- [ ] **Step 3: Commit**

```bash
git add scheduling/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(scheduling): add cross-skill scripts discipline (Glob path resolution)

Names the anti-pattern of writing ad-hoc XER walkers when the
schedule-toolbox plugin already ships compare_schedules / expected_updates.
Locks in the Glob-resolved path pattern as the template for any future
cross-skill helper use.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update SKILL.md — re-read rule, command matrix, pipeline reference

**Files:**
- Modify: `scheduling/skills/schedule-update/SKILL.md`

- [ ] **Step 1: Replace the "Before invoking any sub-command" section's contents**

Use `Edit` to replace the block from `## ⚠️ Before invoking any sub-command — read the right phase files` through the end of the "Command Matrix" table (currently lines 21–38).

Old block (verify exact text in the file before editing):
```markdown
## ⚠️ Before invoking any sub-command — read the right phase files

Each sub-command names the phase files you MUST read in full before acting. **Do not Read the `.py` or HTML scripts those phase files reference** — every phase file inlines the signatures and dict shapes you need. Reading the underlying script is a sign you skipped the phase file.

### Command Matrix

| Invocation | Phase files to read first | Purpose |
|---|---|---|
| `/schedule-update copy` | `phases/copy.md` | Pre-meeting folder setup |
| `/schedule-update screenshots` | `phases/screenshots.md` | SmartPM trend data via MCP → HTML+SVG PNGs (JS CLI) |
| `/schedule-update email` | `phases/email.md`, `phases/_carry_forward.md`, `phases/_attachments.md` | Camron's email draft path |
| `/schedule-update report` | `phases/report.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/draft.md`, `phases/procore.md` | Colleague flow, steps 6–10 |
| `/schedule-update draft` | `phases/draft.md`, `phases/_attachments.md`, `phases/procore.md` | `.eml` / COM draft + Procore publish |
| `/schedule-update procore` | `phases/procore.md`, `phases/_attachments.md` | Retry / standalone Procore publish |
| `/schedule-update status` | `phases/status.md` | Phase detection |
| `/schedule-update` (no arg) | `phases/status.md` | Auto-detect, route to recommended step |
| `/write-weekly-schedule-email` | `commands/write-weekly-schedule-email.md` (thin shell) → same as `report` | Cowork drop-in |

Read **every file in the column** for your invocation, in full, before taking any action.
```

New block:
```markdown
## ⚠️ Before invoking any sub-command — read the right phase files

Each sub-command names the phase files you MUST read in full before acting. **Do not Read the `.py` or HTML scripts those phase files reference** — every phase file inlines the signatures and dict shapes you need. Reading the underlying script is a sign you skipped the phase file.

## ⚠️ Re-read phase files on every phase transition

A sub-command's full procedure lives in the phase files for that command (column 2 of the Command Matrix below). Reading them **once** at the start of the session is not enough — by the time you reach phase 3 of a multi-phase run, the earlier file's text is paraphrased in your working memory and lossy on details.

**Mechanical rule:**

When you build a `TaskCreate` list for any sub-command, the FIRST task for every phase the command pulls in must be `[re-read] phases/<file>.md`. The task description repeats the phase name in full. Example for `/schedule-update report`:

```
TaskCreate({
  subject: "[re-read] phases/report.md",
  description: "Re-read the full phases/report.md file. Do not start any step until it is loaded in current context."
})
TaskCreate({ subject: "Resolve folder + read project-context.html", ... })
TaskCreate({
  subject: "[re-read] phases/_carry_forward.md",
  description: "Re-read the full phases/_carry_forward.md file before invoking carry_forward.reconcile_items / transition_attachments."
})
TaskCreate({ subject: "Reconcile this week's items + attachments", ... })
TaskCreate({
  subject: "[re-read] phases/draft.md",
  description: "Re-read the full phases/draft.md file before building the v2 seed dict."
})
TaskCreate({ subject: "Assemble v2 seed and POST to generate_weekly_schedule_update_email_draft", ... })
```

Why this works: each re-read task forces the phase file's exact field names, function signatures, and ordering back into context just before the work that depends on them. After 100k+ of context the phase files' lemmas haven't drifted — just your recall of them.

Phase files all open with an identical preamble (next section) so when you hit one of these tasks you know exactly what to load.

### Command Matrix

| Invocation | Phase files (re-read each at phase entry) | Purpose |
|---|---|---|
| `/schedule-update copy` | `phases/copy.md` | Pre-meeting folder setup |
| `/schedule-update email` | `phases/email.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/_render_graphs.md` | Camron's email draft path |
| `/schedule-update report` | `phases/report.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/draft.md`, `phases/_render_graphs.md`, `phases/procore.md` | Colleague flow, steps 10–12 |
| `/schedule-update draft` | `phases/draft.md`, `phases/_attachments.md`, `phases/_render_graphs.md`, `phases/procore.md` | `.eml` / COM draft + Procore publish |
| `/schedule-update procore` | `phases/procore.md`, `phases/_attachments.md` | Retry / standalone Procore publish |
| `/schedule-update status` | `phases/status.md` | Phase detection |
| `/schedule-update` (no arg) | `phases/status.md` | Auto-detect, route to recommended step |
| `/write-weekly-schedule-email` | `commands/write-weekly-schedule-email.md` (thin shell) → same as `report` | Cowork drop-in |

**The `screenshots` sub-command is retired.** In v1 it captured 17 SmartPM graph PNGs locally; in v2 the Worker renders graphs server-side and returns them in the finalize payload. The local stacked-PNG rasterization step is internal to `phases/draft.md` (via `phases/_render_graphs.md`) and not a user-invocable command.

Read **every file in the column** for your invocation, in full, before taking any action.
```

- [ ] **Step 2: Replace the "Full Pipeline Reference" table**

Find the section starting `## Full Pipeline Reference` (currently around line 140+). Replace the entire table with:

```markdown
## Full Pipeline Reference

| # | Step | Owner | Command |
|---|------|-------|---------|
| 1 | Copy schedule folder for today's date | Agent | `copy` |
| 2 | Email reminder to get Excel update file | Human | — |
| 3 | Update schedule using Excel file | Human | — |
| 4 | Make corrections, discussion, complete update | Human | (in meeting) |
| 5 | Export schedule files | Human | — |
| 6 | Upload XER to SmartPM (Worker ingests it server-side after the seed POST) | Human | — |
| 7 | Copy meeting transcript to meeting folder | Human | — |
| 8 | Export PDF attachments from schedule software | Human | — |
| 9 | Create next week's Excel files | Human | — |
| 10 | Build seed, POST to MCP, hand editor URL to colleague | Agent | `report` (drives `draft`) |
| 11 | Colleague edits in browser; Worker renders graphs async | Human + Worker | — |
| 12 | Colleague says "done"; finalize draft, build `.eml`, publish Procore | Agent | `draft` (auto-fans into `procore`) |
| 13 | Open `.eml`, review, Send | Human | — |

Colleague-friendly shortcut: `report` covers rows 10–12 in a single guided conversation.
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/SKILL.md
git commit -m "$(cat <<'EOF'
feat(scheduling): SKILL.md re-read rule + retire screenshots sub-command

Adds the phase-transition re-read rule (every TaskCreate phase-entry
task is '[re-read] phases/<file>.md') so Claude reloads exact field
names / function signatures into recent context after long sessions.

Drops the screenshots sub-command from the command matrix and the
pipeline reference table. SmartPM data fetching for the email pipeline
is Worker-owned in v2; the local stacked-PNG rasterization is internal
to phases/draft.md via the new phases/_render_graphs.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add per-phase preamble to every phases/*.md file

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/copy.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/email.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/draft.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/report.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/procore.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/status.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/_carry_forward.md` (insert at top)
- Modify: `scheduling/skills/schedule-update/phases/_attachments.md` (insert at top)

(`phases/screenshots.md` is handled in Task 6.)

- [ ] **Step 1: Insert preamble at top of phases/copy.md**

The current top of `phases/copy.md` is:
```markdown
# Phase: `copy` — Pre-Meeting Folder Setup

> Loaded by SKILL.md's router when the user invokes `/schedule-update copy`.
```

Replace that with:
```markdown
# Phase: `copy` — Pre-Meeting Folder Setup

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `copy` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update copy`.
```

- [ ] **Step 2: Insert preamble at top of phases/email.md**

Current top:
```markdown
# Phase: `email` — Build the .eml from the finalized draft

> Loaded by SKILL.md's router when the user invokes `/schedule-update email`.
> Requires `phases/draft.md` to have already produced `{dated_folder}/{YYYY-MM-DD}-email.json`.
```

Replace with:
```markdown
# Phase: `email` — Build the .eml from the finalized draft

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `email` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update email`.
> Requires `phases/draft.md` to have already produced `{dated_folder}/{YYYY-MM-DD}-email.json`.
```

- [ ] **Step 3: Insert preamble at top of phases/draft.md**

Current top:
```markdown
# Phase: draft

## Goal
```

Replace with:
```markdown
# Phase: draft

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `draft` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update draft` (or when called as an internal dependency from another phase).

## Goal
```

- [ ] **Step 4: Insert preamble at top of phases/report.md**

Current top:
```markdown
# Phase: `report` — Colleague Post-Meeting Flow (Steps 6–10)

> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, and `procore.md`.
```

Replace with:
```markdown
# Phase: `report` — Colleague Post-Meeting Flow (Steps 10–12)

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `report` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, `_render_graphs.md`, and `procore.md`.
```

(Note: the "Steps 6–10" wording also updates to "Steps 10–12" to match the renumbered pipeline table.)

- [ ] **Step 5: Insert preamble at top of phases/procore.md**

Current top:
```markdown
# Phase: `procore` — Publish XER + Attachments to Procore

> Loaded by SKILL.md's router when the user invokes `/schedule-update procore`, and bundled into `report.md` and `draft.md` as the final step of the weekly "done" handler.
> Also requires `_attachments.md`.
```

Replace with:
```markdown
# Phase: `procore` — Publish XER + Attachments to Procore

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `procore` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update procore`, and bundled into `report.md` and `draft.md` as the final step of the weekly "done" handler.
> Also requires `_attachments.md`.
```

- [ ] **Step 6: Insert preamble at top of phases/status.md**

Current top:
```markdown
# Phase: `status` — Pipeline Status

> Loaded by SKILL.md's router when the user invokes `/schedule-update status` or no arg.
```

Replace with:
```markdown
# Phase: `status` — Pipeline Status

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `status` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update status` or no arg.
```

- [ ] **Step 7: Insert preamble at top of phases/_carry_forward.md**

Current top:
```markdown
# _carry_forward — week-over-week state propagation

> **Internal reference** (underscore-prefix). Loaded by `draft.md` and `report.md`.
```

Replace with:
```markdown
# _carry_forward — week-over-week state propagation

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `_carry_forward` phase; any divergence from it is a bug.
> **Internal reference** (underscore-prefix). Loaded by `draft.md` and `report.md` (called as an internal dependency from another phase).
```

- [ ] **Step 8: Insert preamble at top of phases/_attachments.md**

Current top:
```markdown
# _attachments — shared attachment data model

> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `report.md`, `draft.md`, and `procore.md` per the router command matrix.
```

Replace with:
```markdown
# _attachments — shared attachment data model

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `_attachments` phase; any divergence from it is a bug.
> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `report.md`, `draft.md`, and `procore.md` per the router command matrix (called as an internal dependency from another phase).
```

- [ ] **Step 9: Commit**

```bash
git add scheduling/skills/schedule-update/phases/copy.md scheduling/skills/schedule-update/phases/email.md scheduling/skills/schedule-update/phases/draft.md scheduling/skills/schedule-update/phases/report.md scheduling/skills/schedule-update/phases/procore.md scheduling/skills/schedule-update/phases/status.md scheduling/skills/schedule-update/phases/_carry_forward.md scheduling/skills/schedule-update/phases/_attachments.md
git commit -m "$(cat <<'EOF'
docs(scheduling): add identical phase-preamble to every phases/*.md

Each phase file now opens with the same re-read-on-entry preamble that
SKILL.md's command matrix references. The preamble names the phase
explicitly so the corresponding TaskCreate '[re-read]' task knows
exactly which file to load.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Rename and rewrite phases/screenshots.md → phases/_render_graphs.md

**Files:**
- Delete: `scheduling/skills/schedule-update/phases/screenshots.md`
- Create: `scheduling/skills/schedule-update/phases/_render_graphs.md`

- [ ] **Step 1: Create the new _render_graphs.md file**

Write the following content to `scheduling/skills/schedule-update/phases/_render_graphs.md`:

````markdown
# _render_graphs — stack and rasterize the Worker's graph chunks

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `_render_graphs` phase; any divergence from it is a bug.
> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `draft.md`, and `report.md` as an internal dependency.

## Why this is internal

In v1 of the schedule-update skill, capturing graphs meant fetching ~17 SmartPM trend payloads via the SmartPM MCP, writing per-slug JSON to `.chart-payload/`, and running `references/charts/cli.js` to render local PNGs — all client-side. That entire pipeline now lives server-side in the `westland-mcps` Worker. The skill POSTs a v2 seed and the Worker enqueues SmartPM ingest async; by the time `finalize_weekly_schedule_update_email` returns, the payload contains `graphs.{slug}.html` (server-rendered HTML+SVG) for every entry in `graph_order`.

The local job shrinks to one step: stack the Worker's HTML chunks in `graph_order` order into one tall HTML page, then rasterize to a single PNG via `html_to_png.cjs`. That's what this phase covers.

## Inputs

- `{dated_folder}/{YYYY-MM-DD}-email.json` — the finalized draft loaded via `email_draft_io.load_draft(path)`. Must contain:
  - `this_week.graph_order` — list of slugs, canonical render order.
  - `graphs` — dict keyed by slug, values `{html, data}` with server-rendered SVG.
- The `references/charts/html_to_png.cjs` rasterizer + `references/package.json`'s Playwright install.

## Outputs

- `{dated_folder}/screenshots/{job_number}-{YYYY-MM-DD}-all-graphs-stacked.png` — one PNG, ~1200×N px (tall), containing all 9 default chart cards stacked vertically. Embedded as a single inline image in the `.eml` body.

## Process

The orchestrator function in `email_draft_io.py` already does all of this. Drive it from `phases/draft.md`'s build step:

```python
import sys, os
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft, render_stacked_png

draft = load_draft(os.path.join(dated_folder, f'{report_date_iso}-email.json'))
stacked_png = render_stacked_png(draft, output_dir=os.path.join(dated_folder, 'screenshots'))
# stacked_png is the absolute path to the PNG; pass it as summary_screenshot_path
# kwarg to the .eml builder.
```

`render_stacked_png` internally:
1. Reads `draft['this_week']['graph_order']` (defaults to insertion order of `graphs` if missing).
2. Calls `build_stacked_chart_page(graphs, order)` to concatenate chunks into one HTML page (1200px viewport, no per-card width transforms — SVG scales crisply).
3. Writes a temp HTML file in the output dir.
4. Runs `node html_to_png.cjs <tmp_html> <png_path> --width=1200 --full-page` via subprocess (120s timeout).
5. Deletes the temp HTML, returns the absolute PNG path.

## What to do if graphs aren't ready

The Worker's `finalize_weekly_schedule_update_email` response includes `graphs_ready_count` and `graphs_total`. If `graphs_ready_count < graphs_total`, some chart cards in `graphs.{slug}.html` will be placeholder SVGs ("Data not yet available" or "Render failed"). Stacking and rasterizing still works — the PNG will contain placeholder cards alongside the ready ones.

Two options when this happens:
- **Wait and re-finalize.** SmartPM usually finishes within ~20 minutes of XER upload. Sleep, then call `finalize_weekly_schedule_update_email` again. Each finalize call returns a fresh snapshot — placeholders update to real cards as the Worker finishes them.
- **Ship with placeholders.** Rare, only if the data is truly unavailable (e.g. SmartPM project deleted). Warn the colleague before proceeding.

`phases/draft.md`'s build step is the right place to gate on this — it has the finalize response in scope.

## What this phase explicitly does NOT do

- Call SmartPM MCP endpoints directly (`smartpm_get_scenario_*`, `smartpm_post_project_summary`, etc.). Those are Worker concerns now.
- Write per-slug `.chart-payload/{slug}.json` files or run `charts/cli.js`. That pipeline is retired for the email use case. The `references/charts/` library survives in the skill for ad-hoc / future use but is not part of the email build.
- Render individual chart PNGs. One stacked PNG holds everything.

## Why one stacked PNG instead of per-slug PNGs

Pre-cloud-editor, the .eml embedded each chart as its own inline image (one `<img cid:slug>` per chart). That's ~10 inline images per email and Outlook's compose-mode loader handled them inconsistently when the recipient list was long. Stacking them into one PNG sidesteps that — one `Content-ID` reference, one image part, identical rendering on classic and new Outlook.

## Cross-references

- `phases/draft.md` — calls `render_stacked_png` after `finalize_weekly_schedule_update_email`.
- `phases/email.md` — the `.eml` build step that consumes `summary_screenshot_path`.
- `references/email_draft_io.py` — implementation of `render_stacked_png`, `build_stacked_chart_page`, `generate_email_from_draft`.
- `references/charts/html_to_png.cjs` — the Node rasterizer (Playwright-backed).
- scheduling/CLAUDE.md "Email JSON shape — single source of truth" — defines `graphs.{slug}.html` shape.
````

- [ ] **Step 2: Delete the old screenshots.md**

```bash
git rm scheduling/skills/schedule-update/phases/screenshots.md
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/_render_graphs.md
git commit -m "$(cat <<'EOF'
refactor(scheduling): retire phases/screenshots.md, add phases/_render_graphs.md

In v2 the Worker fetches SmartPM data and renders chart HTML+SVG
server-side; the finalize payload returns graphs.{slug}.html for every
entry in graph_order. The local skill's only graph job is stacking the
chunks and rasterizing to one PNG via html_to_png.cjs — that's now in
phases/_render_graphs.md as an internal phase (underscore-prefix).

The 17-slug SmartPM MCP recipe pipeline is gone from this skill;
references/charts/ stays in place for ad-hoc / future use.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: TDD — `carry_forward.reconcile_items` v2 row shape

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/test_carry_forward.py`
- Modify: `scheduling/skills/schedule-update/references/carry_forward.py`

- [ ] **Step 1: Add failing test for v2 row shape**

Append the following test class to `tests/test_carry_forward.py` (before the final `if __name__ == '__main__':` block if one exists):

```python
class ReconcileItemsV2RowShapeTests(unittest.TestCase):
    """v2: rows have no date_archived field. status='archived' is impossible
    in these four lists; lifecycle is active → removed → dropped."""

    def test_active_row_has_no_date_archived_key(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': True, 'status': 'active'}],
            ['Steel up.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows[0]['status'], 'active')
        self.assertNotIn('date_archived', rows[0])

    def test_removed_row_has_no_date_archived_key(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': True, 'status': 'active'}],
            [],  # nothing this week — last week's row drops
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertNotIn('date_archived', rows[0])

    def test_removed_does_not_transition_to_archived_in_these_four_lists(self):
        # Last week's row was already 'removed'. This week it's still
        # absent. In v1 it would transition to 'archived'; in v2 it just
        # drops entirely from the result.
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': False, 'status': 'removed'}],
            [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])

    def test_edited_flag_set_when_text_changed(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'MEP behind two weeks.', 'checked': True, 'status': 'active'}],
            ['MEP behind three weeks — see RFI 0142.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0].get('edited'), True)
        self.assertEqual(rows[0]['prev_idx'], 0)

    def test_edited_flag_absent_or_false_when_text_unchanged(self):
        rows, _ = cf.reconcile_items(
            [{'text': 'Steel up.', 'checked': True, 'status': 'active'}],
            ['Steel up.'],
            today_iso='2026-05-22',
        )
        self.assertFalse(rows[0].get('edited', False))

    def test_new_row_has_no_edited_no_date_archived(self):
        rows, _ = cf.reconcile_items(
            [],
            ['Brand new item.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows[0]['status'], 'new')
        self.assertIsNone(rows[0]['prev_idx'])
        self.assertNotIn('edited', rows[0])
        self.assertNotIn('date_archived', rows[0])
```

- [ ] **Step 2: Run the test and verify it fails**

Run from the repo root:
```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward.ReconcileItemsV2RowShapeTests -v
```

Or alternatively, working-dir relative:
```bash
cd scheduling/skills/schedule-update && python -m unittest tests.test_carry_forward.ReconcileItemsV2RowShapeTests -v
```

Expected: tests FAIL — `test_active_row_has_no_date_archived_key` fails because current `reconcile_items` returns rows with `date_archived: ''`. `test_edited_flag_set_when_text_changed` fails because `edited` is not emitted today. Other tests may also fail.

- [ ] **Step 3: Update `reconcile_items` in `carry_forward.py`**

Open `scheduling/skills/schedule-update/references/carry_forward.py`. Find the `reconcile_items` function. Modify it as follows:

In the **Match phase** (the loop that produces the `matched` list), replace each row-dict construction:

Old (matched, status='active'):
```python
matched.append({
    'text': text,
    'checked': True,
    'status': 'active',
    'date_archived': '',
    'prev_idx': best_idx,
})
```

New:
```python
row = {
    'text': text,
    'checked': True,
    'status': 'active',
    'prev_idx': best_idx,
}
prev_text = (last_items[best_idx].get('text') or '').strip()
if text != prev_text:
    row['edited'] = True
matched.append(row)
```

Old (matched, status='new' from resurrected removed/archived):
```python
matched.append({
    'text': text,
    'checked': True,
    'status': 'new',
    'date_archived': '',
    'prev_idx': None,
})
```

New:
```python
matched.append({
    'text': text,
    'checked': True,
    'status': 'new',
    'prev_idx': None,
})
```

Old (matched, status='new' from no-match):
```python
matched.append({
    'text': text,
    'checked': True,
    'status': 'new',
    'date_archived': '',
    'prev_idx': None,
})
```

New:
```python
matched.append({
    'text': text,
    'checked': True,
    'status': 'new',
    'prev_idx': None,
})
```

In the **Drop phase**, change the v1 lifecycle (active/new → removed, removed → archived) to the v2 lifecycle (active/new → removed, removed → drop, archived → drop). Replace the entire drop phase loop with:

```python
# --- Drop phase: last-week items Claude didn't include (v2 lifecycle) ---
dropped = []
for i, it in enumerate(last_items):
    if i in used:
        continue
    prev_text = (it.get('text') or '').strip()
    if not prev_text:
        continue
    prev_status = it.get('status', 'active')

    # v2: only 'active' or 'new' last week → 'removed' this week. Anything
    # already 'removed' last week drops entirely (no archived pile for
    # the four primary lists). 'archived' shouldn't appear here (it's
    # isolated to key_items_archived in v2) — treat defensively as drop.
    if prev_status in ('active', 'new'):
        dropped.append({
            'text': prev_text,
            'checked': False,
            'status': 'removed',
            'prev_idx': i,
        })
    # else: drop. Do not append.

this_week_rows = matched + dropped
return this_week_rows, last_week_baseline
```

Also update `last_week_baseline` construction (earlier in the function) to drop `date_archived`:

Old:
```python
last_week_baseline = [
    {
        'text': (it.get('text') or ''),
        'checked': bool(it.get('checked', True)),
        'status': it.get('status', 'active'),
        'date_archived': it.get('date_archived', '') or '',
    }
    for it in last_items
]
```

New:
```python
last_week_baseline = [
    {
        'text': (it.get('text') or ''),
        'checked': bool(it.get('checked', True)),
        'status': it.get('status', 'active'),
    }
    for it in last_items
]
```

Update the docstring to reflect v2 lifecycle (replace `Semantics (matched cases)` and `Semantics (unmatched last-week items)` blocks with v2 wording — the function-level behavior described above).

- [ ] **Step 4: Run the test and verify it passes**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward.ReconcileItemsV2RowShapeTests -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run the full carry_forward test module to check for regressions**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward -v
```

Expected: any previously passing v1-shape tests now FAIL (they assert `date_archived` presence). That's expected — those legacy tests will be updated in subsequent tasks as we expand the function's scope. Leave them failing for now; do not delete them. Note the failures and move on.

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/tests/test_carry_forward.py scheduling/skills/schedule-update/references/carry_forward.py
git commit -m "$(cat <<'EOF'
feat(scheduling): carry_forward.reconcile_items emits v2 row shape

v2 row shape drops date_archived (no archived state in these four lists)
and adds an optional 'edited' flag set when status='active' and text
differs from last_week[prev_idx].text.

Lifecycle change: items that fall out go to status='removed' for one
week only and then drop. No archived pile for successes / red_flags /
stalled_tasks / key_items.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: TDD — new `carry_forward.reconcile_key_items` function

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/test_carry_forward.py`
- Modify: `scheduling/skills/schedule-update/references/carry_forward.py`

- [ ] **Step 1: Add failing tests for `reconcile_key_items`**

Append to `tests/test_carry_forward.py`:

```python
class ReconcileKeyItemsTests(unittest.TestCase):
    """v2: key_items has a sibling key_items_archived list.
    reconcile_key_items returns (this_week_rows, this_week_archived_rows,
    last_week_baseline). Items that fall out transition active → removed
    → archived (with date_archived). Archived rows older than 90 days
    drop entirely."""

    def test_active_carries_forward_to_active(self):
        last_key = [
            {'text': 'Owner walkthrough 2026-05-28.', 'checked': True, 'status': 'active'},
        ]
        rows, archived, baseline = cf.reconcile_key_items(
            last_key, [], ['Owner walkthrough 2026-05-28.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'active')
        self.assertEqual(rows[0]['prev_idx'], 0)
        self.assertEqual(archived, [])
        self.assertEqual(baseline[0]['text'], 'Owner walkthrough 2026-05-28.')

    def test_dropped_item_goes_to_removed(self):
        last_key = [
            {'text': 'Will not happen again.', 'checked': True, 'status': 'active'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            last_key, [], [],
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertEqual(archived, [])

    def test_removed_last_week_archives_this_week(self):
        last_key = [
            {'text': 'Already removed last update.', 'checked': False, 'status': 'removed'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            last_key, [], [],
            today_iso='2026-05-22',
        )
        # No rows in active list (it dropped); one in archived list.
        self.assertEqual(rows, [])
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]['status'], 'archived')
        self.assertEqual(archived[0].get('date_archived'), '2026-05-22')

    def test_archived_in_last_week_stays_archived_with_original_date(self):
        last_archived = [
            {'text': 'Archived two weeks ago.', 'checked': False,
             'status': 'archived', 'date_archived': '2026-05-08'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            [], last_archived, [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]['date_archived'], '2026-05-08')

    def test_archived_past_90_days_prunes(self):
        last_archived = [
            {'text': 'Archived too long ago.', 'checked': False,
             'status': 'archived', 'date_archived': '2026-01-01'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            [], last_archived, [],
            today_iso='2026-05-22',
        )
        self.assertEqual(rows, [])
        self.assertEqual(archived, [])

    def test_resurrected_archived_item_becomes_new(self):
        last_archived = [
            {'text': 'Old key item resurrected.', 'checked': False,
             'status': 'archived', 'date_archived': '2026-05-08'},
        ]
        rows, archived, _ = cf.reconcile_key_items(
            [], last_archived, ['Old key item resurrected.'],
            today_iso='2026-05-22',
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'new')
        self.assertIsNone(rows[0]['prev_idx'])
        # No longer in archived list — moved back to active.
        self.assertEqual(archived, [])
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward.ReconcileKeyItemsTests -v
```

Expected: all tests FAIL with `AttributeError: module 'carry_forward' has no attribute 'reconcile_key_items'`.

- [ ] **Step 3: Implement `reconcile_key_items` in `carry_forward.py`**

Add this function to `scheduling/skills/schedule-update/references/carry_forward.py`, immediately after `reconcile_items`:

```python
def reconcile_key_items(last_week_key_items, last_week_key_items_archived,
                        this_week_texts, today_iso=None,
                        similarity_threshold=0.6,
                        max_archived_days=MAX_ARCHIVED_DAYS):
    """v2 key_items reconciliation — splits output into active + archived.

    Unlike `reconcile_items`, key_items maintains an archived pile in a
    separate sibling list (`key_items_archived`) for delay-claim evidence.
    Archived rows older than `max_archived_days` drop entirely.

    Args:
        last_week_key_items: prior week's `this_week.key_items` rows
            (active/new/removed status).
        last_week_key_items_archived: prior week's
            `this_week.key_items_archived` rows (archived status,
            with `date_archived`).
        this_week_texts: HTML strings Claude wrote for this update's
            key items.
        today_iso: 'YYYY-MM-DD' for transitions & pruning.
        similarity_threshold: fuzzy-match cutoff.
        max_archived_days: prune archived items older than this.

    Returns:
        (this_week_rows, this_week_archived_rows, last_week_baseline):
            - this_week_rows: active/new/removed for seed.this_week.key_items.
              Carries `prev_idx`, optional `edited`.
            - this_week_archived_rows: archived for
              seed.this_week.key_items_archived. Each row has
              `date_archived` set.
            - last_week_baseline: pass-through copy of last_week_key_items
              (active key_items only) for seed.last_week.key_items.

    Lifecycle:
        active/new in last_week.key_items → matched this week: active.
                                          → unmatched this week: removed.
        removed in last_week.key_items   → unmatched: archived (date_archived=today).
        archived in last_week.key_items_archived
                                        → matched this week: new (resurrection).
                                        → unmatched: stays archived (original date).
                                        → past max_archived_days: dropped.
    """
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    last_active = list(last_week_key_items or [])
    last_archived = list(last_week_key_items_archived or [])

    last_week_baseline = [
        {
            'text': (it.get('text') or ''),
            'checked': bool(it.get('checked', True)),
            'status': it.get('status', 'active'),
        }
        for it in last_active
    ]

    # Build combined search space for fuzzy matching: active items first,
    # then archived. Track which list each index belongs to.
    search = [(i, 'active', it) for i, it in enumerate(last_active)] + \
             [(i, 'archived', it) for i, it in enumerate(last_archived)]
    used_active = set()
    used_archived = set()

    matched = []
    for raw in (this_week_texts or []):
        text = (raw or '').strip()
        if not text:
            continue
        best = None  # (ratio, idx_in_search)
        for s_idx, (orig_idx, kind, it) in enumerate(search):
            if kind == 'active' and orig_idx in used_active:
                continue
            if kind == 'archived' and orig_idx in used_archived:
                continue
            prev_text = (it.get('text') or '').strip()
            if not prev_text:
                continue
            if prev_text == text:
                best = (1.0, s_idx)
                break
            r = _similarity(prev_text, text)
            if best is None or r > best[0]:
                best = (r, s_idx)

        if best is not None and best[0] >= similarity_threshold:
            orig_idx, kind, it = search[best[1]]
            prev_text = (it.get('text') or '').strip()
            if kind == 'active':
                used_active.add(orig_idx)
                prev_status = it.get('status', 'active')
                if prev_status in ('removed',):
                    matched.append({
                        'text': text,
                        'checked': True,
                        'status': 'new',
                        'prev_idx': None,
                    })
                else:
                    row = {
                        'text': text,
                        'checked': True,
                        'status': 'active',
                        'prev_idx': orig_idx,
                    }
                    if text != prev_text:
                        row['edited'] = True
                    matched.append(row)
            else:  # kind == 'archived' — resurrection
                used_archived.add(orig_idx)
                matched.append({
                    'text': text,
                    'checked': True,
                    'status': 'new',
                    'prev_idx': None,
                })
        else:
            matched.append({
                'text': text,
                'checked': True,
                'status': 'new',
                'prev_idx': None,
            })

    # Drop phase for active items: unmatched last-week active/new → 'removed' this week.
    dropped_active = []
    new_archived = []
    for i, it in enumerate(last_active):
        if i in used_active:
            continue
        prev_text = (it.get('text') or '').strip()
        if not prev_text:
            continue
        prev_status = it.get('status', 'active')
        if prev_status in ('active', 'new'):
            dropped_active.append({
                'text': prev_text,
                'checked': False,
                'status': 'removed',
                'prev_idx': i,
            })
        elif prev_status == 'removed':
            # removed last week, still gone this week → archive now
            new_archived.append({
                'text': prev_text,
                'checked': False,
                'status': 'archived',
                'date_archived': today_iso,
                'prev_idx': i,
            })

    # Drop phase for archived items: unmatched archives stay archived
    # (original date), prune anything older than max_archived_days.
    for i, it in enumerate(last_archived):
        if i in used_archived:
            continue
        prev_text = (it.get('text') or '').strip()
        if not prev_text:
            continue
        date_archived = it.get('date_archived', today_iso) or today_iso
        if _too_old(date_archived, today, max_archived_days):
            continue
        new_archived.append({
            'text': prev_text,
            'checked': False,
            'status': 'archived',
            'date_archived': date_archived,
            # prev_idx for archived rows references the archived baseline,
            # which is its own list — leave None to avoid ambiguity. The
            # editor uses date_archived to render the row, not prev_idx.
            'prev_idx': None,
        })

    this_week_rows = matched + dropped_active
    return this_week_rows, new_archived, last_week_baseline
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward.ReconcileKeyItemsTests -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/tests/test_carry_forward.py scheduling/skills/schedule-update/references/carry_forward.py
git commit -m "$(cat <<'EOF'
feat(scheduling): add carry_forward.reconcile_key_items for v2

Splits the key_items reconciliation into a two-list output: active
(seed.this_week.key_items) and archived (seed.this_week.key_items_archived).

Archived state is isolated to key_items in v2 — the other four lists
(successes, red_flags, stalled_tasks, attachments) follow
active → removed → dropped only.

Lifecycle: active/new → removed → archived (1 week later) → archived
(stays for 90 days) → dropped. Resurrection from archived counts as 'new'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: TDD — `carry_forward.transition_attachments` v2 fields

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/test_carry_forward.py`
- Modify: `scheduling/skills/schedule-update/references/carry_forward.py`

- [ ] **Step 1: Add failing tests for v2 attachment row shape**

Append to `tests/test_carry_forward.py`:

```python
class TransitionAttachmentsV2Tests(unittest.TestCase):
    """v2: attachments use 'name'/'procore' field names, optional 'ext'.
    No archived status; lifecycle is active → removed → dropped."""

    def test_active_row_uses_name_and_procore(self):
        last = [
            {'name': 'Report 01.pdf', 'checked': True, 'status': 'active',
             'procore': True},
        ]
        rows = cf.transition_attachments(last, ['Report 01.pdf'],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Report 01.pdf')
        self.assertEqual(rows[0]['procore'], True)
        self.assertNotIn('filename', rows[0])
        self.assertNotIn('share_to_procore', rows[0])
        self.assertNotIn('date_archived', rows[0])

    def test_new_attachment_bootstrap_view_match_defaults_procore_true(self):
        rows = cf.transition_attachments([], ['Owner View Report.pdf'],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'new')
        self.assertEqual(rows[0]['procore'], True)

    def test_new_attachment_bootstrap_unknown_defaults_procore_false(self):
        rows = cf.transition_attachments([], ['Internal Memo.pdf'],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['procore'], False)

    def test_dropped_attachment_goes_to_removed_no_archived(self):
        last = [
            {'name': 'Old Report.pdf', 'checked': True, 'status': 'active',
             'procore': False},
        ]
        rows = cf.transition_attachments(last, [],
                                          today_iso='2026-05-22')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'removed')
        self.assertNotIn('date_archived', rows[0])

    def test_removed_last_week_drops_entirely(self):
        last = [
            {'name': 'Old Report.pdf', 'checked': False, 'status': 'removed',
             'procore': False},
        ]
        rows = cf.transition_attachments(last, [],
                                          today_iso='2026-05-22')
        self.assertEqual(rows, [])

    def test_ext_set_from_filename_extension(self):
        rows = cf.transition_attachments([], ['Update Request.xlsm'],
                                          today_iso='2026-05-22')
        self.assertEqual(rows[0].get('ext'), 'xlsm')
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward.TransitionAttachmentsV2Tests -v
```

Expected: tests FAIL because current `transition_attachments` returns rows with `filename` / `share_to_procore` / `date_archived` (not `name` / `procore` / no-`date_archived`).

- [ ] **Step 3: Rewrite `transition_attachments` for v2 field names**

Open `references/carry_forward.py`. Replace the entire `transition_attachments` function with:

```python
def transition_attachments(last_week_attachments, fresh_filenames=None,
                           today_iso=None):
    """v2 attachment reconciliation.

    Match fresh-globbed filenames against last week's attachments by
    date-stripped fuzzy name. Files that re-appear week-over-week
    (only the date token changed) carry forward as `status='active'`
    with the FRESH filename. Files only in fresh become `status='new'`.

    Unmatched last-week items (Claude/glob dropped them) transition:
        active/new → removed
        removed   → drop entirely (no archived pile for attachments)

    Args:
        last_week_attachments: list of dicts from last week's
            email-draft.json (`last_draft['this_week']['attachments']`).
            Expected v2 fields: name, ext (optional), checked, procore,
            status, prev_idx.
        fresh_filenames: this week's freshly-resolved basename strings.
        today_iso: 'YYYY-MM-DD' for transitions (defaults to today).

    Returns:
        list of {name, ext, checked, procore, status, prev_idx} dicts
        ready for seed.this_week.attachments.
    """
    if today_iso is None:
        today_iso = date.today().isoformat()

    last_items = list(last_week_attachments or [])
    norm_index = {}
    for i, a in enumerate(last_items):
        norm = _normalize_attachment_name(a.get('name', '') or a.get('filename', ''))
        if norm:
            norm_index.setdefault(norm, i)

    used = set()
    result = []

    # --- Match phase: fresh ↔ last-week via normalized names -----------
    for fn in (fresh_filenames or []):
        if not fn:
            continue
        norm = _normalize_attachment_name(fn)
        ext = _ext_of(fn)
        if norm and norm in norm_index and norm_index[norm] not in used:
            i = norm_index[norm]
            used.add(i)
            last_a = last_items[i]
            last_status = last_a.get('status', 'active')

            if last_status in ('active', 'new', 'removed'):
                # Restoration / continuation — call it active.
                row = {
                    'name': fn,
                    'checked': True,
                    'status': 'active',
                    'procore': bool(last_a.get('procore',
                                                last_a.get('share_to_procore', False))),
                    'prev_idx': i,
                }
                if ext:
                    row['ext'] = ext
                result.append(row)
            else:
                # Defensive: unknown status, treat as new.
                row = {
                    'name': fn,
                    'checked': True,
                    'status': 'new',
                    'procore': _bootstrap_share_to_procore(fn),
                    'prev_idx': None,
                }
                if ext:
                    row['ext'] = ext
                result.append(row)
        else:
            row = {
                'name': fn,
                'checked': True,
                'status': 'new',
                'procore': _bootstrap_share_to_procore(fn),
                'prev_idx': None,
            }
            if ext:
                row['ext'] = ext
            result.append(row)

    # --- Drop phase: last-week items not matched this week -------------
    for i, a in enumerate(last_items):
        if i in used:
            continue
        last_status = a.get('status', 'active')
        name = a.get('name', '') or a.get('filename', '')
        if not name:
            continue
        ext = a.get('ext') or _ext_of(name)

        if last_status in ('active', 'new'):
            row = {
                'name': name,
                'checked': False,
                'status': 'removed',
                'procore': bool(a.get('procore',
                                       a.get('share_to_procore', False))),
                'prev_idx': i,
            }
            if ext:
                row['ext'] = ext
            result.append(row)
        # else: drop entirely (no archived pile for attachments in v2).

    return result


def _ext_of(filename):
    """Return lowercase extension without dot, or '' if no extension."""
    if not filename:
        return ''
    base = filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    if '.' not in base:
        return ''
    return base.rsplit('.', 1)[-1].lower()
```

Also remove the now-orphaned `transition_items` function (separate from `reconcile_items`) — search for `def transition_items(` and delete the entire function block.

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward.TransitionAttachmentsV2Tests -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run the full carry_forward test module**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_carry_forward -v
```

Expected: ReconcileItemsV2RowShapeTests pass, ReconcileKeyItemsTests pass, TransitionAttachmentsV2Tests pass. Legacy v1 tests in the same file likely fail — that's fine; we'll prune them in Task 14 when the fixture is regenerated.

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/tests/test_carry_forward.py scheduling/skills/schedule-update/references/carry_forward.py
git commit -m "$(cat <<'EOF'
feat(scheduling): transition_attachments emits v2 row shape

Field renames: filename → name, share_to_procore → procore. Optional
ext added. No date_archived; no archived status. Lifecycle is
active → removed → dropped.

Drops the orphaned transition_items helper (already replaced by
reconcile_items).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: TDD — `email_draft_io.SUPPORTED_VERSIONS = {2}`

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`
- Modify: `scheduling/skills/schedule-update/references/email_draft_io.py:44`

- [ ] **Step 1: Add a failing test that v1 raises DraftError**

Append to `tests/test_email_draft_io.py` (inside the `LoadDraftTests` class, or as a new test method):

```python
    def test_load_draft_raises_on_v1(self):
        """v1 is no longer supported; the Worker rejects v1 seeds too."""
        v1 = json.loads(SAMPLE_DRAFT_PATH.read_text())
        v1['version'] = 1
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(v1, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError) as ctx:
                email_draft_io.load_draft(path)
            self.assertIn('version', str(ctx.exception).lower())
        finally:
            os.unlink(path)

    def test_load_draft_accepts_v2(self):
        """v2 is the only supported version."""
        v2 = json.loads(SAMPLE_DRAFT_PATH.read_text())
        v2['version'] = 2
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(v2, f)
            path = f.name
        try:
            draft = email_draft_io.load_draft(path)
            self.assertEqual(draft['version'], 2)
        finally:
            os.unlink(path)
```

Also update the existing `test_load_draft_returns_parsed_dict` test — change the assertion from `assertEqual(draft['version'], 1)` to `assertEqual(draft['version'], 2)`. (This test will currently fail because the fixture is still v1; that's expected and gets resolved in Task 14.)

- [ ] **Step 2: Run the tests and verify they fail in the right way**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_draft_io.LoadDraftTests -v
```

Expected: `test_load_draft_raises_on_v1` fails because v1 currently loads (SUPPORTED_VERSIONS={1} today). `test_load_draft_accepts_v2` fails because v2 is unsupported today.

- [ ] **Step 3: Update SUPPORTED_VERSIONS in email_draft_io.py**

Change line 44 of `references/email_draft_io.py`:
```python
SUPPORTED_VERSIONS = {1}
```
to:
```python
SUPPORTED_VERSIONS = {2}
```

- [ ] **Step 4: Run the tests**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_draft_io.LoadDraftTests.test_load_draft_raises_on_v1 scheduling.skills.schedule_update.tests.test_email_draft_io.LoadDraftTests.test_load_draft_accepts_v2 -v
```

Expected: both new tests pass. `test_load_draft_returns_parsed_dict` may still fail (the fixture is v1) — that's fine; the fixture gets regenerated in Task 14.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/tests/test_email_draft_io.py scheduling/skills/schedule-update/references/email_draft_io.py
git commit -m "$(cat <<'EOF'
feat(scheduling): email_draft_io accepts only v2

SUPPORTED_VERSIONS = {2}. v1 input raises DraftError, matching the
Worker's policy of rejecting v1 seeds with SEED_VERSION_TOO_OLD (422).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: TDD — `email_draft_io.editorial_to_kwargs` v2 translation

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`
- Modify: `scheduling/skills/schedule-update/references/email_draft_io.py` (replace `editorial_to_kwargs`, add helpers)

- [ ] **Step 1: Add failing tests for v2 translation**

Append a new test class to `tests/test_email_draft_io.py`:

```python
class EditorialToKwargsV2Tests(unittest.TestCase):
    """v2 → builder kwargs flattening."""

    def _v2_this_week(self, **overrides):
        base = {
            'subject': 'Subject Line',
            'to_recipients': [
                {'name': 'Owner', 'email': 'owner@example.com'},
                {'name': 'PM',    'email': 'pm@example.com'},
            ],
            'cc_recipients': [
                {'name': 'Sub',   'email': 'sub@example.com'},
            ],
            'days_metric': {'direction': 'behind', 'value': 14},
            'gain_loss':   {'direction': 'loss', 'value': 3,
                            'narrative': 'Lost 3 days to weather.',
                            'narrative_changed': True},
            'successes': [
                {'text': '<div>Foundation pour done.</div>', 'status': 'active',
                 'checked': True, 'prev_idx': 0},
            ],
            'red_flags':     [],
            'stalled_tasks': [],
            'key_items':     [],
            'key_items_archived': [
                {'text': 'Old archived key item.', 'status': 'archived',
                 'checked': False, 'date_archived': '2026-04-15'},
            ],
            'eot_recovery':        'Drafting EOT 0017.',
            'logic_changes':       'Reordered MEP rough-in.',
            'smartpm_changelog_url': 'https://app.smartpm.com/changelog',
            'closing_paragraphs': [
                {'label': 'Questions', 'checked': True,
                 'text': '<div>Please let me know if you have any questions.</div>'},
                {'label': 'Owner directive', 'checked': True,
                 'text': '<div>Owner directed switch to alternate roofing.</div>'},
                {'label': 'Unchecked', 'checked': False,
                 'text': '<div>Should not render.</div>'},
            ],
            'closing_salutation': 'Thanks,',
            'signer_name': 'Camron Walker', 'signer_title': 'Scheduler',
            'signer_mobile': '555-0100',
            'attachments': [
                {'name': 'Report 01.pdf', 'ext': 'pdf', 'checked': True,
                 'procore': True, 'status': 'active', 'prev_idx': 0},
                {'name': 'Removed.pdf',   'ext': 'pdf', 'checked': False,
                 'procore': False, 'status': 'removed', 'prev_idx': 1},
            ],
            'skip_procore': False,
            'include_changes_report': True,
            'changes_report_filename': 'G2203 Changes Report 2026-05-21.pdf',
            'graph_order': ['01-planned-vs-actual-percent-complete'],
        }
        base.update(overrides)
        return base

    def _v2_project_info(self):
        return {
            'project_name': 'Lubumbashi MTC',
            'job_number': 'G2203',
            'contractual_completion': 'April 30, 2027',
            'projected_completion':   'May 14, 2027',
        }

    def test_recipients_flatten_to_semicolon_string(self):
        tw = self._v2_this_week()
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertEqual(kwargs['to_recipients'],
                          'Owner <owner@example.com>; PM <pm@example.com>')
        self.assertEqual(kwargs['cc_recipients'],
                          'Sub <sub@example.com>')

    def test_days_metric_object_flattens_to_signed_int(self):
        tw = self._v2_this_week(days_metric={'direction': 'behind', 'value': 14})
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertEqual(kwargs['days_behind'], 14)

    def test_days_metric_ahead_flattens_to_negative_int(self):
        tw = self._v2_this_week(days_metric={'direction': 'ahead', 'value': 5})
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertEqual(kwargs['days_behind'], -5)

    def test_gain_loss_object_flattens_to_signed_int(self):
        tw = self._v2_this_week(gain_loss={'direction': 'loss', 'value': 3,
                                            'narrative': 'lost 3',
                                            'narrative_changed': False})
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertEqual(kwargs['gain_loss'], -3)
        self.assertEqual(kwargs['gain_loss_narrative'], 'lost 3')

    def test_gain_loss_gain_flattens_to_positive_int(self):
        tw = self._v2_this_week(gain_loss={'direction': 'gain', 'value': 7,
                                            'narrative': 'gained 7',
                                            'narrative_changed': False})
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertEqual(kwargs['gain_loss'], 7)

    def test_closing_paragraphs_filter_checked_and_concat_html(self):
        tw = self._v2_this_week()
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertIn('Please let me know', kwargs['closing_paragraphs_html'])
        self.assertIn('Owner directed', kwargs['closing_paragraphs_html'])
        self.assertNotIn('Should not render', kwargs['closing_paragraphs_html'])

    def test_closing_salutation_renames_to_salutation_kwarg(self):
        tw = self._v2_this_week(closing_salutation='Best,')
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        self.assertEqual(kwargs['salutation'], 'Best,')

    def test_key_items_archived_not_in_body_kwargs(self):
        tw = self._v2_this_week()
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        # No kwarg named key_items_archived; the archived items must not
        # leak into the email body.
        self.assertNotIn('key_items_archived', kwargs)
        self.assertEqual(kwargs['key_items'], [])

    def test_attachments_filter_removed_and_use_name(self):
        tw = self._v2_this_week()
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info())
        # 'Removed.pdf' is status='removed' → excluded.
        self.assertEqual(kwargs['attachment_paths'], ['Report 01.pdf'])

    def test_last_week_days_metric_flattens_for_prev_kwargs(self):
        tw = self._v2_this_week()
        lw = self._v2_this_week(
            days_metric={'direction': 'behind', 'value': 11},
            gain_loss={'direction': 'gain', 'value': 2,
                       'narrative': 'gained 2', 'narrative_changed': False},
        )
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info(),
                                                     last_week=lw)
        self.assertEqual(kwargs['prev_days_behind'], 11)
        self.assertEqual(kwargs['prev_gain_loss'], 2)

    def test_last_week_none_makes_prev_kwargs_none(self):
        tw = self._v2_this_week()
        kwargs = email_draft_io.editorial_to_kwargs(tw, project_info=self._v2_project_info(),
                                                     last_week=None)
        self.assertIsNone(kwargs['prev_days_behind'])
        self.assertIsNone(kwargs['prev_gain_loss'])
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_draft_io.EditorialToKwargsV2Tests -v
```

Expected: all 11 tests FAIL because current `editorial_to_kwargs` reads v1 fields (`to` / `cc` strings, `days_behind` int, `gain_loss` int).

- [ ] **Step 3: Replace `editorial_to_kwargs` and add helpers**

Open `references/email_draft_io.py`. Find the current `editorial_to_kwargs` function (begins around line 302). Replace it AND its helpers (`_items_for_email_body`, `_custom_paragraphs_for_email_body`, `_attachments_for_email_body`) with the v2 versions below.

Replace lines from `def _items_for_email_body(items):` through the end of `editorial_to_kwargs` with:

```python
def _items_for_email_body(items):
    """Filter an item-list for email rendering.

    Items rendered in the body: checked=True AND status in ('active', 'new').
    Removed and archived items are excluded.
    """
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        if item.get('status') in ('removed', 'archived'):
            continue
        text = (item.get('text') or '').strip()
        if text:
            out.append(text)
    return out


def _attachment_names_for_email(items):
    """Filter v2 attachment rows to a list of names for the email body.

    Items rendered: checked=True AND status != 'removed'.
    Returns basenames (no path). The orchestrator resolves them against
    dated_folder.
    """
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        if item.get('status') == 'removed':
            continue
        name = (item.get('name') or item.get('filename') or '').strip()
        if name:
            out.append(name)
    return out


def _format_recipients(recipients):
    """[{name, email}] → 'Name <email>; Other <email2>' string.

    Empty / None → ''. Each entry: if name is non-empty, formats as
    'Name <email>'; if name is empty, just 'email'.
    """
    if not recipients:
        return ''
    parts = []
    for r in recipients:
        if not isinstance(r, dict):
            continue
        name = (r.get('name') or '').strip()
        email = (r.get('email') or '').strip()
        if not email:
            continue
        if name:
            parts.append(f'{name} <{email}>')
        else:
            parts.append(email)
    return '; '.join(parts)


def _join_closing_paragraphs(paragraphs):
    """closing_paragraphs[checked].text concatenated as HTML.

    Empty / None → ''. Each paragraph's text is HTML from the Trix editor.
    Joined with no separator (paragraphs already wrap themselves).
    """
    if not paragraphs:
        return ''
    parts = []
    for p in paragraphs:
        if not isinstance(p, dict):
            continue
        if not p.get('checked'):
            continue
        text = (p.get('text') or '').strip()
        if text:
            parts.append(text)
    return ''.join(parts)


def _flatten_days_metric(dm):
    """days_metric {direction, value} → signed int.

    'behind' → +value, 'ahead' → -value. Missing/empty → 0.
    """
    if not dm:
        return 0
    direction = (dm.get('direction') or '').lower()
    value = int(dm.get('value') or 0)
    return value if direction == 'behind' else -value


def _flatten_gain_loss(gl):
    """gain_loss {direction, value, ...} → signed int.

    'loss' → -value, 'gain' → +value. Missing/empty → 0.
    """
    if not gl:
        return 0
    direction = (gl.get('direction') or '').lower()
    value = int(gl.get('value') or 0)
    return -value if direction == 'loss' else value


def editorial_to_kwargs(this_week, project_info=None, last_week=None):
    """Translate v2 this_week + project_info (+ optional last_week) -> kwargs
    for generate_update_email_eml / generate_update_email_msg.

    All v2 → builder flattening lives here so the builder signatures stay stable.

    Args:
        this_week:    v2 `this_week` sub-dict from a loaded draft.
        project_info: top-level `project_info` dict.
        last_week:    optional frozen-copy of last week's this_week for
                      prev_days_behind/prev_gain_loss strikethrough badges.

    Returns:
        Dict suitable for `**kwargs` into the .eml or COM builder.
    """
    this_week = this_week or {}
    pi = project_info or {}

    to_str = _format_recipients(this_week.get('to_recipients'))
    cc_str = _format_recipients(this_week.get('cc_recipients'))

    days_behind = _flatten_days_metric(this_week.get('days_metric'))
    gain_loss = _flatten_gain_loss(this_week.get('gain_loss'))
    gl = this_week.get('gain_loss') or {}
    gain_loss_narrative = gl.get('narrative', '') or ''

    closing_html = _join_closing_paragraphs(this_week.get('closing_paragraphs'))

    kwargs = {
        'project_info': dict(pi),
        'subject': this_week.get('subject', '') or '',
        'to_recipients': to_str,
        'cc_recipients': cc_str,
        'days_behind': days_behind,
        'gain_loss': gain_loss,
        'gain_loss_narrative': gain_loss_narrative,
        'successes':     _items_for_email_body(this_week.get('successes')),
        'red_flags':     _items_for_email_body(this_week.get('red_flags')),
        'stalled_tasks': _items_for_email_body(this_week.get('stalled_tasks')),
        'key_items':     _items_for_email_body(this_week.get('key_items')),
        # key_items_archived: deliberately NOT rendered in the body.
        'eot_recovery':        this_week.get('eot_recovery', '') or '',
        'logic_changes':       this_week.get('logic_changes', '') or '',
        'smartpm_changelog_url': this_week.get('smartpm_changelog_url', '') or '',
        'closing_paragraphs_html': closing_html,
        'salutation':            this_week.get('closing_salutation', '') or '',
        'signer_name':  this_week.get('signer_name', '') or '',
        'signer_title': this_week.get('signer_title', '') or '',
        'signer_mobile': this_week.get('signer_mobile', '') or '',
        'attachment_paths': _attachment_names_for_email(this_week.get('attachments')),
        'from_address':    this_week.get('from', '') or '',
    }

    if last_week:
        kwargs['prev_days_behind'] = _flatten_days_metric(last_week.get('days_metric'))
        kwargs['prev_gain_loss']   = _flatten_gain_loss(last_week.get('gain_loss'))
    else:
        kwargs['prev_days_behind'] = None
        kwargs['prev_gain_loss'] = None

    return kwargs
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_draft_io.EditorialToKwargsV2Tests -v
```

Expected: all 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/tests/test_email_draft_io.py scheduling/skills/schedule-update/references/email_draft_io.py
git commit -m "$(cat <<'EOF'
feat(scheduling): editorial_to_kwargs translates v2 → builder kwargs

All v2 flattening happens here so the .eml / COM builders' kwarg
signatures stay stable:

- to_recipients/cc_recipients arrays → 'Name <email>; …' strings
- days_metric / gain_loss objects → signed ints
- closing_paragraphs[checked] → joined HTML
- closing_salutation → salutation kwarg
- attachments name field (not filename), filtered to active/new
- key_items_archived deliberately excluded from body kwargs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Update `generate_email_msg.py` `_build_html_body` signature for closing_paragraphs_html

**Files:**
- Modify: `scheduling/skills/schedule-update/references/generate_email_msg.py`
- Modify: `scheduling/skills/schedule-update/tests/test_email_eml.py`

- [ ] **Step 1: Add a failing test that the new kwarg is consumed**

Append to `tests/test_email_eml.py` (study the existing test class structure first; mirror it):

```python
class BuildHtmlBodyV2Tests(unittest.TestCase):
    """v2 _build_html_body uses closing_paragraphs_html kwarg, no longer
    accepts closing_line / custom_paragraphs."""

    def test_closing_paragraphs_html_renders_verbatim(self):
        from generate_email_msg import _build_html_body
        html = _build_html_body(
            project_info={
                'project_name': 'Test', 'job_number': 'G0000',
                'contractual_completion': 'TBD', 'projected_completion': 'TBD',
            },
            days_behind=0, gain_loss=0,
            successes=[], red_flags=[], stalled_tasks=[], key_items=[],
            gain_loss_narrative='', eot_recovery='', logic_changes='',
            smartpm_changelog_url='',
            closing_paragraphs_html='<div>Please ask questions.</div><div>Owner directive applied.</div>',
            salutation='Thanks,',
            signer_name='Camron', signer_title='Scheduler', signer_mobile='555-0100',
            summary_screenshot_cid='cid:summary',
            smartpm_project_url='', smartpm_trends_url='',
        )
        self.assertIn('Please ask questions.', html)
        self.assertIn('Owner directive applied.', html)

    def test_no_closing_line_kwarg_required(self):
        """The signature must not require closing_line."""
        from generate_email_msg import _build_html_body
        # If closing_line were still required, this raises TypeError.
        html = _build_html_body(
            project_info={
                'project_name': 'Test', 'job_number': 'G0000',
                'contractual_completion': 'TBD', 'projected_completion': 'TBD',
            },
            days_behind=0, gain_loss=0,
            successes=[], red_flags=[], stalled_tasks=[], key_items=[],
            gain_loss_narrative='', eot_recovery='', logic_changes='',
            smartpm_changelog_url='',
            closing_paragraphs_html='',
            salutation='Thanks,',
            signer_name='C', signer_title='S', signer_mobile='',
            summary_screenshot_cid='cid:s',
            smartpm_project_url='', smartpm_trends_url='',
        )
        self.assertIsInstance(html, str)
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_eml.BuildHtmlBodyV2Tests -v
```

Expected: tests fail with `TypeError` (the function doesn't accept `closing_paragraphs_html` today; it expects `closing_line` and `custom_paragraphs`).

- [ ] **Step 3: Update `_build_html_body` signature in generate_email_msg.py**

Find the `_build_html_body` function. Replace its parameter list and the closing-block rendering as follows.

In the parameter list, replace:
```python
closing_line='Please let me know if you have any questions.',
custom_paragraphs=None,
salutation='Thanks,',
```

With:
```python
closing_paragraphs_html='',
salutation='Thanks,',
```

In the body where the closing section renders (search for `closing_line` and the `custom_paragraphs` loop), replace the rendering block with:

```python
# Closing paragraphs: pre-joined HTML from email_draft_io._join_closing_paragraphs
# (or empty). Renders verbatim — the Trix editor emits inline-style HTML that
# Outlook's Word renderer respects.
closing_html_block = closing_paragraphs_html or ''
```

And in the HTML template string, replace the old block that interpolated `closing_line` + iterated `custom_paragraphs` with a single insertion of `{closing_html_block}` where the closing section sits, e.g.:

```html
{closing_html_block}
<p style="...">{salutation}</p>
<p style="..."><strong>{signer_name}</strong><br>{signer_title}<br>{signer_mobile}</p>
```

(Exact surrounding tags depend on the existing template — keep them; only swap the inner content.)

Update the docstring's HTML tag canon block: where it currently lists `<strong>` and `#C94444` / `#FFF59D`, update to:
```
    <b>...</b>                                                       — bold
    <i>...</i>                                                       — italic
    <span style="background-color: #FFF4B8">...</span>               — highlight
    <span style="color: #9B2C2C">...</span>                          — important (Westland red)
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_eml.BuildHtmlBodyV2Tests -v
```

Expected: both new tests pass.

- [ ] **Step 5: Run the full email_eml test module**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_eml -v
```

Expected: any existing tests that passed `closing_line=` or `custom_paragraphs=` as kwargs now FAIL with `TypeError`. Note them and proceed; they get updated in the legacy-test cleanup at Task 23.

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/references/generate_email_msg.py scheduling/skills/schedule-update/tests/test_email_eml.py
git commit -m "$(cat <<'EOF'
feat(scheduling): _build_html_body uses closing_paragraphs_html kwarg

Replaces v1's closing_line + custom_paragraphs with a single
pre-joined HTML string. email_draft_io.editorial_to_kwargs handles
the join.

Docstring HTML tag canon updated to v2:
  <b>, <i>, #FFF4B8 highlight, #9B2C2C important.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Sync generate_email_eml.py with the new closing_paragraphs_html kwarg

**Files:**
- Modify: `scheduling/skills/schedule-update/references/generate_email_eml.py`

- [ ] **Step 1: Inspect how generate_email_eml.py imports from generate_email_msg.py**

Run: `Grep "_build_html_body" scheduling/skills/schedule-update/references/generate_email_eml.py -n`

Expected: `from generate_email_msg import _build_html_body, ...`. The `.eml` builder imports the body builder; with Task 12 done, the kwarg name has already changed at the import target.

- [ ] **Step 2: Find any places `generate_email_eml.py` references the OLD kwargs and update them**

Run: `Grep "closing_line|custom_paragraphs" scheduling/skills/schedule-update/references/generate_email_eml.py -n`

For every match, update the caller to pass `closing_paragraphs_html` instead of `closing_line` / `custom_paragraphs`. Most likely the function `generate_update_email_eml` has a parameter list with these names — replace as in Task 12 (drop both, add `closing_paragraphs_html=''`).

In the function body, where `_build_html_body` is invoked, change the kwargs accordingly.

- [ ] **Step 3: Update the docstring HTML tag canon in generate_email_eml.py too**

If the file's docstring lists `<strong>` / `#C94444` / `#FFF59D`, update to:
```
    <b>...</b>                                                       — bold
    <i>...</i>                                                       — italic
    <span style="background-color: #FFF4B8">...</span>               — highlight
    <span style="color: #9B2C2C">...</span>                          — important (Westland red)
```

- [ ] **Step 4: Run the eml test module to confirm no regressions**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_eml -v
```

Expected: BuildHtmlBodyV2Tests still pass; whatever legacy tests still fail will be cleaned up in Task 23.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/references/generate_email_eml.py
git commit -m "$(cat <<'EOF'
feat(scheduling): generate_update_email_eml uses closing_paragraphs_html

Mirror Task 12's signature change. The .eml builder accepts
closing_paragraphs_html (pre-joined HTML) and passes it through to
_build_html_body. Docstring HTML tag canon updated to v2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Regenerate `tests/fixtures/email-draft-sample.json` as v2

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json` (full rewrite)

- [ ] **Step 1: Replace the fixture content with v2 shape**

Overwrite `tests/fixtures/email-draft-sample.json` entirely with:

```json
{
  "version": 2,
  "report_date": "2026-05-21",
  "project_info": {
    "project_name": "Lubumbashi MTC",
    "job_number": "G2203",
    "contractual_completion": "April 30, 2027",
    "projected_completion": "May 14, 2027"
  },
  "this_week": {
    "subject": "G2203 — Lubumbashi MTC — Weekly Update — 2026-05-21",
    "to_recipients": [
      { "name": "Owner Team", "email": "owner@example.com" },
      { "name": "PM Lead",    "email": "pm@example.com" }
    ],
    "cc_recipients": [
      { "name": "Sub One", "email": "sub1@example.com" },
      { "name": "Sub Two", "email": "sub2@example.com" }
    ],
    "days_metric": { "direction": "behind", "value": 14 },
    "gain_loss":   {
      "direction": "loss",
      "value":     3,
      "narrative": "Lost 3 days this week to weather delays on the south elevation.",
      "narrative_changed": true
    },
    "successes": [
      { "text": "<div>Foundation pour complete on Building A.</div>", "status": "active", "checked": true, "prev_idx": 0 },
      { "text": "<div>Steel delivery confirmed for week of 2026-06-01.</div>", "status": "new", "checked": true, "prev_idx": null }
    ],
    "red_flags": [
      { "text": "<div><span style=\"color: #9B2C2C\">MEP coordination behind two weeks</span> — see RFI 0142.</div>", "status": "active", "checked": true, "edited": true, "prev_idx": 0 }
    ],
    "stalled_tasks": [
      { "text": "<div>Roofing material approval pending owner sign-off.</div>", "status": "active", "checked": true, "prev_idx": 0 }
    ],
    "key_items": [
      { "text": "<div>Owner walkthrough scheduled 2026-05-28.</div>", "status": "active", "checked": true, "prev_idx": 0 }
    ],
    "key_items_archived": [
      { "text": "<div>Old archived key item.</div>", "status": "archived", "checked": false, "date_archived": "2026-04-15", "prev_idx": null }
    ],
    "eot_recovery": "Filing EOT request 0017 for the weather impact; recovery plan attached.",
    "logic_changes": "Reordered MEP rough-in to allow steel erection to continue in parallel.",
    "smartpm_changelog_url": "https://app.smartpm.com/projects/12345/changelog",
    "closing_paragraphs": [
      { "label": "Questions", "checked": true, "text": "<div>Please let me know if you have any questions.</div>" },
      { "label": "Owner directive 2026-05-19", "checked": true, "text": "<div>Owner directed switch to alternate roofing material per email.</div>" }
    ],
    "closing_salutation": "Thanks,",
    "signer_name": "Camron Walker",
    "signer_title": "Scheduler",
    "signer_mobile": "555-0100",
    "attachments": [
      { "name": "G2203 Weekly Report 2026-05-21.pdf", "ext": "pdf", "checked": true, "procore": true,  "status": "active", "prev_idx": 0 },
      { "name": "G2203 EOT Request 0017.pdf",         "ext": "pdf", "checked": true, "procore": false, "status": "new",    "prev_idx": null }
    ],
    "skip_procore": false,
    "include_changes_report": true,
    "changes_report_filename": "G2203 Changes Report 2026-05-21.pdf",
    "graph_order": [
      "01-planned-vs-actual-percent-complete",
      "06-end-date-variance",
      "07-schedule-compression-index-over-time",
      "08-velocity",
      "09-spi-over-time",
      "10-activity-hit-rate",
      "11-window-start-accuracy",
      "12-window-finish-accuracy",
      "smartpm-summary-report"
    ]
  },
  "last_week": {
    "subject": "G2203 — Lubumbashi MTC — Weekly Update — 2026-05-14",
    "to_recipients": [
      { "name": "Owner Team", "email": "owner@example.com" },
      { "name": "PM Lead",    "email": "pm@example.com" }
    ],
    "cc_recipients": [
      { "name": "Sub One", "email": "sub1@example.com" },
      { "name": "Sub Two", "email": "sub2@example.com" }
    ],
    "days_metric": { "direction": "behind", "value": 11 },
    "gain_loss":   {
      "direction": "gain",
      "value":     2,
      "narrative": "Gained 2 days from re-sequencing.",
      "narrative_changed": false
    },
    "successes": [
      { "text": "<div>Foundation pour complete on Building A.</div>", "status": "active", "checked": true },
      { "text": "<div>Trim out kicked off in Building B.</div>",       "status": "active", "checked": true }
    ],
    "red_flags": [
      { "text": "<div><span style=\"color: #9B2C2C\">MEP coordination behind one week.</span></div>", "status": "active", "checked": true }
    ],
    "stalled_tasks": [
      { "text": "<div>Roofing material approval pending owner sign-off.</div>", "status": "active", "checked": true }
    ],
    "key_items": [
      { "text": "<div>Owner walkthrough scheduled 2026-05-28.</div>", "status": "active", "checked": true }
    ],
    "key_items_archived": [],
    "eot_recovery": "Drafting EOT request 0017.",
    "logic_changes": "",
    "smartpm_changelog_url": "https://app.smartpm.com/projects/12345/changelog",
    "closing_paragraphs": [
      { "label": "Questions", "checked": true, "text": "<div>Please let me know if you have any questions.</div>" }
    ],
    "closing_salutation": "Thanks,",
    "signer_name": "Camron Walker",
    "signer_title": "Scheduler",
    "signer_mobile": "555-0100",
    "attachments": [
      { "name": "G2203 Weekly Report 2026-05-14.pdf", "ext": "pdf", "checked": true, "procore": true, "status": "active" }
    ],
    "skip_procore": false,
    "include_changes_report": false,
    "changes_report_filename": "",
    "graph_order": [
      "01-planned-vs-actual-percent-complete",
      "06-end-date-variance",
      "07-schedule-compression-index-over-time",
      "08-velocity",
      "09-spi-over-time",
      "10-activity-hit-rate",
      "11-window-start-accuracy",
      "12-window-finish-accuracy",
      "smartpm-summary-report"
    ]
  },
  "graphs": {
    "01-planned-vs-actual-percent-complete": {
      "html": "<div class=\"chart-card\" data-slug=\"01-planned-vs-actual-percent-complete\"><h3>Planned vs Actual % Complete</h3><svg viewBox=\"0 0 1728 432\"><g class=\"series\"><!-- real svg here --></g></svg></div>",
      "data": { "stub": "real SmartPM response here" }
    },
    "06-end-date-variance": {
      "html": "<div class=\"chart-card\" data-slug=\"06-end-date-variance\"><h3>End Date Variance</h3><svg viewBox=\"0 0 1728 432\"></svg></div>",
      "data": {}
    },
    "smartpm-summary-report": {
      "html": "<div class=\"chart-card\" data-slug=\"smartpm-summary-report\"><h3>Summary Report</h3><div><!-- 3 sections: cards + curve + milestones --></div></div>",
      "data": { "stub": "real summary response here" }
    }
  }
}
```

(Other slugs in `graph_order` are intentionally omitted from `graphs` in this fixture to keep it small. `editorial_to_kwargs` doesn't care; `render_stacked_png` will skip missing slugs.)

- [ ] **Step 2: Run the full email_draft_io test module**

```bash
python -m unittest scheduling.skills.schedule_update.tests.test_email_draft_io -v
```

Expected: `LoadDraftTests` v2-aware tests pass (`test_load_draft_returns_parsed_dict` asserts version==2, `test_load_draft_accepts_v2` passes). All `EditorialToKwargsV2Tests` continue to pass. Any legacy tests that asserted v1 fields will FAIL — note them for Task 23.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json
git commit -m "$(cat <<'EOF'
test(scheduling): regenerate email-draft-sample.json as v2

Full v2 shape: recipients arrays, days_metric / gain_loss objects,
closing_paragraphs + closing_salutation, attachments name/procore/ext,
key_items_archived as a sibling list, include_changes_report +
changes_report_filename, graph_order with the 8 trend slugs + summary.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Update `generate_changes_report_html.py` for v2 kwargs

**Files:**
- Modify: `scheduling/skills/schedule-update/references/generate_changes_report_html.py`

- [ ] **Step 1: Audit current kwargs**

Run: `Grep "def generate_changes_report" scheduling/skills/schedule-update/references/generate_changes_report_html.py -n -A 30`

Identify which kwargs reference v1 fields (`days_behind` int, `gain_loss` int, `custom_paragraphs`, `share_to_procore` on attachments, `previous_text` on items).

- [ ] **Step 2: Translate kwargs to v2 shape**

For each v1 kwarg name, update to the v2 equivalent the calling code (most likely `phases/draft.md` orchestrator) will pass:

- `days_behind` (int) — KEEP as int kwarg name; the orchestrator uses `editorial_to_kwargs` which already flattens `days_metric` → signed int. No code change here.
- `gain_loss` (int) — same: keep as int.
- `custom_paragraphs` (list of `{label, text, checked}`) — replace with `closing_paragraphs_html` (string). Update the rendering: where the function loops over `custom_paragraphs` to render labeled paragraphs, replace with a single insertion of `closing_paragraphs_html` verbatim.
- `closing_line` (string) — DELETE; folded into `closing_paragraphs_html`.
- `attachments` parameter — if rows reference `filename` / `share_to_procore`, update to `name` / `procore`. If the function uses `row.get('filename', row.get('name'))` it already tolerates both — keep the defensive read.
- `key_items_archived` parameter — if accepted today, KEEP accepting it but EXCLUDE from rendering (the PDF treats archived items the same as the email body: hidden everywhere except the editor).

- [ ] **Step 3: Update the docstring**

Update the file-level docstring's diff-rendering rules section to match v2 lifecycle (the four primary lists go active → removed → dropped; `archived` only exists for `key_items_archived` and is excluded from the PDF).

- [ ] **Step 4: Verify the file still imports cleanly**

```bash
python -c "
import sys
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
import generate_changes_report_html
print(generate_changes_report_html.generate_changes_report.__doc__[:200])
"
```

Expected: no import errors; docstring prints.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/references/generate_changes_report_html.py
git commit -m "$(cat <<'EOF'
feat(scheduling): generate_changes_report_html reads v2 fields

- closing_paragraphs_html replaces custom_paragraphs + closing_line
- attachments use name (not filename) and procore (not share_to_procore)
- key_items_archived deliberately excluded from PDF output, matching
  email body — archived items hide everywhere except the editor

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Delete obsolete reference files

**Files:**
- Delete: `scheduling/skills/schedule-update/references/generate_email_docx.py`
- Delete: `scheduling/skills/schedule-update/references/Master Schedule Update Email Example.docx`
- Delete: `scheduling/skills/schedule-update/references/Schedule Update Email Procedure.docx`

- [ ] **Step 1: Confirm no phase or test references these files**

```bash
git grep "generate_email_docx\|Master Schedule Update Email\|Schedule Update Email Procedure" -- scheduling/
```

Expected: zero hits. If any hit appears, stop and reconcile before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm scheduling/skills/schedule-update/references/generate_email_docx.py
git rm "scheduling/skills/schedule-update/references/Master Schedule Update Email Example.docx"
git rm "scheduling/skills/schedule-update/references/Schedule Update Email Procedure.docx"
```

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore(scheduling): delete orphaned .docx generator and legacy reference docs

generate_email_docx.py has no phase referencing it; the pipeline went
.eml / COM-only after the cloud editor migration. The two .docx
reference files (~870 KB total) are superseded by phases/ + the
cloud editor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Update phases/_carry_forward.md for v2

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/_carry_forward.md`

- [ ] **Step 1: Replace the "Function signatures (inline)" block**

Find the `## Function signatures (inline)` section. Replace the existing code block with:

````markdown
```python
# carry_forward.reconcile_items(last_week_items, this_week_texts,
#                               today_iso=None, similarity_threshold=0.6)
#     -> (this_week_rows, last_week_baseline)
#
# v2: rows are {text, status, checked, edited(optional), prev_idx}.
# No date_archived. Status lifecycle: active → removed → dropped (no
# archived pile in these four lists).

# carry_forward.reconcile_key_items(last_week_key_items,
#                                   last_week_key_items_archived,
#                                   this_week_texts, today_iso=None,
#                                   similarity_threshold=0.6,
#                                   max_archived_days=90)
#     -> (this_week_rows, this_week_archived_rows, last_week_baseline)
#
# v2-only: key_items has a sibling key_items_archived list. Lifecycle
# active → removed → archived (1 week later) → archived for 90 days →
# dropped. Resurrection counts as 'new'.

# carry_forward.transition_attachments(last_week_attachments,
#                                      fresh_filenames=None,
#                                      today_iso=None)
#     -> list of {name, ext(optional), checked, procore, status, prev_idx}
#
# v2: name (not filename), procore (not share_to_procore), optional ext.
# No date_archived; no archived state. Lifecycle is
# active → removed → dropped.
```
````

- [ ] **Step 2: Replace the "Pull the carry-forward values from `last`" table**

Replace the existing table with:

```markdown
| Field on `last` (this_week dict) | Pass to seed as | Purpose |
|---|---|---|
| `last['days_metric']`, `last['gain_loss']` | seed.last_week.days_metric / .gain_loss verbatim | week-over-week strikethrough on the metric lines |
| `last['gain_loss']['narrative']`, `last['eot_recovery']`, `last['logic_changes']` | seed.last_week.<field> | inline narrative diff in the editor |
| `last['successes']`, `last['red_flags']`, `last['stalled_tasks']` | through `reconcile_items()` → seed.this_week.<list> + seed.last_week.<list> | per-item state transitions + prev_idx |
| `last['key_items']`, `last['key_items_archived']` | through `reconcile_key_items()` → seed.this_week.key_items + seed.this_week.key_items_archived + seed.last_week.key_items | key_items + archived sibling reconciliation |
| `last['attachments']` | through `transition_attachments()` → seed.this_week.attachments | file carry-forward + procore preservation |
| `last['closing_paragraphs']` | seed.this_week.closing_paragraphs verbatim | closing paragraphs (no diff semantics) |
| `last['include_changes_report']`, `last['changes_report_filename']` | seed.this_week.include_changes_report / .changes_report_filename default | changelog PDF toggle |
| `last['skip_procore']` | seed.this_week.skip_procore default | inherit master Procore-skip toggle |
| `last['closing_salutation']` | seed.this_week.closing_salutation default | preserve colleague's last edit |
```

- [ ] **Step 3: Update the "Reconciliation recipe" code block**

Replace the existing code block with:

````markdown
For list items (red_flags / successes / stalled_tasks):

```python
from carry_forward import reconcile_items

red_flags_this_week, red_flags_last_week = reconcile_items(
    last['red_flags'],
    this_week_red_flag_html_strings,
    today_iso=today_iso,
)
```

For key_items (note the two-input + three-output signature):

```python
from carry_forward import reconcile_key_items

key_items_rows, key_items_archived_rows, key_items_baseline = reconcile_key_items(
    last['key_items'],
    last['key_items_archived'],
    this_week_key_item_html_strings,
    today_iso=today_iso,
)
# Use:
#   key_items_rows           → seed.this_week.key_items
#   key_items_archived_rows  → seed.this_week.key_items_archived
#   key_items_baseline       → seed.last_week.key_items (active only)
```

For attachments:

```python
import glob, os
from carry_forward import transition_attachments

fresh = []
for ext in ('*.pdf', '*.xlsm', '*.xer'):
    fresh.extend(
        os.path.basename(p) for p in glob.glob(os.path.join(dated_folder, ext))
        if not os.path.basename(p).startswith('~$')  # skip Office lock files
    )
attachments_new = transition_attachments(
    last['attachments'], fresh, today_iso=today_iso,
)
```
````

- [ ] **Step 4: Update the "Pass into the cloud-editor seed" subsection**

Replace the example seed_this_week dict with v2 field names. Search for the block starting with `seed_this_week = {` and replace it with:

```python
seed_this_week = {
    **last,
    'subject':       this_week_subject,
    'days_metric':   {'direction': 'behind' if days_behind_int >= 0 else 'ahead',
                      'value': abs(days_behind_int)},
    'gain_loss':     {'direction': 'gain' if gl_int >= 0 else 'loss',
                      'value': abs(gl_int),
                      'narrative': this_week_narratives['gain_loss_narrative'],
                      'narrative_changed': narrative_changed_flag},
    'eot_recovery':        this_week_narratives['eot_recovery'],
    'logic_changes':       this_week_narratives['logic_changes'],
    'successes':           successes_this_week,
    'red_flags':           red_flags_this_week,
    'stalled_tasks':       stalled_this_week,
    'key_items':           key_items_rows,
    'key_items_archived':  key_items_archived_rows,
    'attachments':         attachments_new,
}
```

- [ ] **Step 5: Update the "Changed narrative fields" subsection**

Replace the diff-loop snippet so it knows `gain_loss.narrative` is embedded in the `gain_loss` object now:

```python
changed_narrative_fields = set()
prev_gl_narrative = ((last.get('gain_loss') or {}).get('narrative') or '').strip().lower()
this_gl_narrative = (this_week_narratives['gain_loss_narrative'] or '').strip().lower()
if prev_gl_narrative != this_gl_narrative:
    changed_narrative_fields.add('gain_loss_narrative')
for field in ('eot_recovery', 'logic_changes'):
    if (this_week_narratives[field] or '').strip().lower() != (last.get(field) or '').strip().lower():
        changed_narrative_fields.add(field)
```

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/phases/_carry_forward.md
git commit -m "$(cat <<'EOF'
docs(scheduling): _carry_forward.md updated for v2 field names + reconcile_key_items

Updates the function-signature block, the carry-forward field table,
the reconciliation recipes (now including reconcile_key_items's
two-input + three-output signature), the seed_this_week assembly
example, and the changed-narrative-fields snippet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Update phases/_attachments.md for v2

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/_attachments.md`

- [ ] **Step 1: Replace the per-attachment dict shape block**

Find the block:
```markdown
## Per-attachment dict shape

```python
{
    'filename': str,
    'checked': bool,
    'status': 'active' | 'new' | 'removed' | 'archived',
    'date_archived': str,
    'share_to_procore': bool,
}
```
```

Replace with:
```markdown
## Per-attachment dict shape (v2)

```python
{
    'name':     str,             # basename
    'ext':      str,             # OPTIONAL; lowercase, no dot
    'checked':  bool,            # include in email
    'procore':  bool,            # the P toggle — Procore Documents upload
    'status':   'active' | 'new' | 'removed',
    'prev_idx': int | None,
}
```

No `archived` status, no `date_archived` field. Lifecycle is
active → removed → dropped.
```

- [ ] **Step 2: Update carry-forward bullet points**

Search for `share_to_procore` references and replace with `procore`. Update the bootstrap-rule bullets to read:

```markdown
- **Preserve:** for any file that matches an attachment from last week (date-stripped fuzzy name match), `procore` is propagated verbatim from the prior week's dict. The user's previous decision survives the week boundary.
- **Bootstrap (new attachments only):** for genuinely new files (no last-week match), `procore` defaults per pattern:
  - `True` when the filename matches `View` (case-insensitive) OR matches `Update Request*.xlsm` (case-insensitive).
  - `False` otherwise.
```

- [ ] **Step 3: Update "What to call, from each phase" table**

Replace `share_to_procore` references with `procore`:

```markdown
| Phase | Reads | Writes |
|---|---|---|
| `email.md` (Camron path) | last week's `{prev_date}-email.json` for carry-forward + bootstrap | nothing local — seeds the cloud editor |
| `report.md` | same as email.md | same |
| `draft.md` | this week's `{YYYY-MM-DD}-email.json` for filtered lists in the `.eml` | `.eml` file |
| `procore.md` | this week's `{YYYY-MM-DD}-email.json` for the `procore` filter | nothing (Procore-side via MCP) |
```

- [ ] **Step 4: Commit**

```bash
git add scheduling/skills/schedule-update/phases/_attachments.md
git commit -m "$(cat <<'EOF'
docs(scheduling): _attachments.md updated for v2 field names

share_to_procore → procore; filename → name; optional ext added;
no archived/date_archived. Active → removed → dropped lifecycle.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Update phases/draft.md seed-builder for v2

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/draft.md`

- [ ] **Step 1: Replace the "The seed shape" block**

Find the JSON example under `## The seed shape`. Replace the entire `jsonc` block with:

````markdown
The seed is the v2 top-level email JSON shape minus `graphs` (the Worker renders those). See [scheduling/CLAUDE.md → Email JSON shape](../../../CLAUDE.md) for the full contract. Verbatim shape the MCP tool expects:

```jsonc
{
  "version":     2,
  "report_date": "YYYY-MM-DD",
  "project_info": {
    "project_name": "...", "job_number": "...",
    "contractual_completion": "...", "projected_completion": "..."
  },

  "this_week": {
    "subject": "...",
    "to_recipients": [{"name": "...", "email": "..."}],
    "cc_recipients": [{"name": "...", "email": "..."}],
    "days_metric": {"direction": "behind"|"ahead", "value": int},
    "gain_loss":   {"direction": "loss"|"gain", "value": int,
                    "narrative": "...", "narrative_changed": bool},

    "successes":          [/* {text, status, checked, edited?, prev_idx} */],
    "red_flags":          [/* same */],
    "stalled_tasks":      [/* same */],
    "key_items":          [/* same */],
    "key_items_archived": [/* {text, status='archived', checked, date_archived, prev_idx} */],

    "eot_recovery": "...", "logic_changes": "...",
    "smartpm_changelog_url": "...",
    "closing_paragraphs": [{"label": "...", "checked": true,
                             "text": "<div>...</div>"}],
    "closing_salutation": "Thanks,",
    "signer_name": "...", "signer_title": "...", "signer_mobile": "...",
    "attachments": [/* {name, ext?, checked, procore, status, prev_idx} */],
    "skip_procore": false,
    "include_changes_report": bool,
    "changes_report_filename": "...",
    "graph_order": [
      "01-planned-vs-actual-percent-complete",
      "06-end-date-variance",
      "07-schedule-compression-index-over-time",
      "08-velocity",
      "09-spi-over-time",
      "10-activity-hit-rate",
      "11-window-start-accuracy",
      "12-window-finish-accuracy",
      "smartpm-summary-report"
    ]
  },

  "last_week": { /* identical shape; null if week-1 */ }
}
```

Item rows are `{text, status, checked, edited(optional), prev_idx}` where `text` is HTML and `prev_idx` is an int (index into `last_week.<same-list>`) or `null` for status='new'. Attachment rows: `{name, ext, checked, procore, status, prev_idx}`.
````

- [ ] **Step 2: Update the "Build `this_week` via structured carry-forward" recipe**

Find the code block under `### 2. Build `this_week` via structured carry-forward`. Replace it with:

````markdown
The rule is **carry-forward then revise**: take `prev_draft['this_week']` field-by-field, then apply this week's deltas. Run list items through `carry_forward.reconcile_items` (and key_items through `reconcile_key_items`):

```python
from carry_forward import reconcile_items, reconcile_key_items, transition_attachments

prev_this_week = (prev_draft or {}).get('this_week', {}) or {}

successes_rows, _ = reconcile_items(prev_this_week.get('successes'),
                                     this_week_success_html, today_iso=today)
red_flags_rows, _ = reconcile_items(prev_this_week.get('red_flags'),
                                     this_week_red_flag_html, today_iso=today)
stalled_rows, _   = reconcile_items(prev_this_week.get('stalled_tasks'),
                                     this_week_stalled_html, today_iso=today)

# key_items: two inputs (active + archived), three outputs.
key_items_rows, key_items_archived_rows, _ = reconcile_key_items(
    prev_this_week.get('key_items'),
    prev_this_week.get('key_items_archived'),
    this_week_key_item_html,
    today_iso=today,
)

attachments_rows = transition_attachments(
    prev_this_week.get('attachments'),
    fresh_filenames,
    today_iso=today,
)
```
````

- [ ] **Step 3: Update the "Standard moves" bullets**

Update the "Subject", "Narrative blocks", "Signer block", and metric bullets to reflect v2:

````markdown
- **Subject:** swap last week's date for this week's; keep project name + job number.
- **Narrative blocks (`gain_loss.narrative`, `eot_recovery`, `logic_changes`):** rewrite based on this week's XER deltas + transcript. Leave `smartpm_changelog_url` unchanged unless the URL pattern has shifted.
- **Signer block:** unchanged unless the colleague has rotated.
- **`days_metric` / `gain_loss`:** compute from XER comparison (week-over-week delta on contractual completion + schedule variance). Express as `{direction, value}` objects — `direction` = `'behind'` when slipping vs contract, `'ahead'` when running early; `direction` = `'loss'` when worse than last week, `'gain'` when better. `gain_loss.narrative` is one short paragraph and `narrative_changed` is `True` when it differs from `last['gain_loss']['narrative']`.
- **`graph_order`:** unchanged unless the colleague has reordered. Default is the 8-trend canonical order plus `'smartpm-summary-report'` last.
- **`closing_paragraphs` / `closing_salutation`:** preserve from last week, or default to a single-entry list `[{label: "Questions", checked: true, text: "<div>Please let me know if you have any questions.</div>"}]` and `"Thanks,"`.
````

- [ ] **Step 4: Update the "Assemble the seed" block**

Find the `seed = { ... }` Python block. Replace it with:

```python
seed = {
    'version': 2,
    'report_date': today_iso,
    'project_info': {
        'project_name': ctx['project_name'],
        'job_number':   ctx['job_number'],
        'contractual_completion': ctx['contractual_completion'],
        'projected_completion':   projected_completion_iso,
    },
    'this_week': {
        'subject':       this_week_subject,
        'to_recipients': ctx['to_recipients'],   # [{name, email}, ...] array
        'cc_recipients': ctx['cc_recipients'],   # same
        'days_metric':   this_week_days_metric,  # {direction, value}
        'gain_loss':     this_week_gain_loss,    # {direction, value, narrative, narrative_changed}
        'successes':           successes_rows,
        'red_flags':           red_flags_rows,
        'stalled_tasks':       stalled_rows,
        'key_items':           key_items_rows,
        'key_items_archived':  key_items_archived_rows,
        'eot_recovery':         this_week_eot_recovery,
        'logic_changes':        this_week_logic_changes,
        'smartpm_changelog_url': ctx['smartpm_changelog_url'],
        'closing_paragraphs':   this_week_closing_paragraphs,
        'closing_salutation':   this_week_closing_salutation,
        'signer_name':          ctx['signer_name'],
        'signer_title':         ctx['signer_title'],
        'signer_mobile':        ctx['signer_mobile'],
        'attachments':          attachments_rows,
        'skip_procore':         prev_this_week.get('skip_procore', False),
        'include_changes_report':  bool(prev_this_week.get('include_changes_report', True)),
        'changes_report_filename': changes_report_filename,
        'graph_order':          prev_this_week.get('graph_order') or default_graph_order_with_summary,
    },
    'last_week': prev_this_week if prev_draft else None,
}
with open(os.path.join(dated_folder, f'{today_iso}-email.seed.json'), 'w') as f:
    json.dump(seed, f, indent=2)
```

Note `'smartpm'` top-level key is gone in v2 — the Worker resolves it from `project_info.job_number`.

- [ ] **Step 5: Update the "Build .eml" handoff to load _render_graphs.md**

Find the section that describes the finalize + .eml build (likely near the end). Add a step that explicitly notes the stacked-PNG rasterization happens via `_render_graphs.md`:

```markdown
### 10. Build the .eml

Before building the .eml, **re-read `phases/_render_graphs.md`** — the stacked-PNG rasterization recipe lives there. Then call `email_draft_io.generate_email_from_draft(...)`, which internally:

1. Loads the v2 draft.
2. Stacks `graphs.{slug}.html` chunks in `graph_order` order.
3. Rasterizes to one PNG via `html_to_png.cjs`.
4. Resolves attachment names against `dated_folder`.
5. Calls `editorial_to_kwargs` to flatten v2 → builder kwargs.
6. Calls `generate_update_email_eml` to write the .eml.

If `graphs_ready_count < graphs_total` from the finalize response, warn the colleague before building (some chart cards will be placeholders).
```

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/phases/draft.md
git commit -m "$(cat <<'EOF'
docs(scheduling): draft.md seed-builder updated for v2 shape

- version: 2
- recipients arrays
- days_metric / gain_loss objects
- closing_paragraphs / closing_salutation
- include_changes_report + changes_report_filename
- attachments use name/procore (not filename/share_to_procore)
- key_items_archived added; reconcile_key_items used for key_items
- default graph_order is 8 trend slugs + smartpm-summary-report
- removed top-level 'smartpm' key (Worker resolves it)
- build-.eml step references phases/_render_graphs.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: Update phases/email.md for v2 kwargs

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/email.md`

- [ ] **Step 1: Update the "Read the finalized draft" block**

Find the section starting `### 1. Read the finalized draft`. The `load_draft` call shape itself doesn't change, but the docstring-style hint about the loaded dict's keys should reference v2 fields. Replace:

```markdown
`draft` has the top-level shape canonical to scheduling/CLAUDE.md: `version`, `report_date`, `project_info`, `this_week`, `last_week` (or null), `smartpm`, `graphs`.
```

With:

```markdown
`draft` has the v2 top-level shape (see scheduling/CLAUDE.md "Email JSON shape"): `version: 2`, `report_date`, `project_info`, `this_week` (with v2 field names — recipients arrays, days_metric/gain_loss objects, closing_paragraphs, attachments name/procore), `last_week` (or null), `graphs`.
```

- [ ] **Step 2: Update the kwarg references**

Find any `closing_line`, `salutation`, `custom_paragraphs`, or `share_to_procore` references in the file and remove or rename them per v2:
- `closing_line` → folded into `closing_paragraphs_html`
- `custom_paragraphs` → folded into `closing_paragraphs_html`
- `salutation` → still `salutation` kwarg (post-editorial_to_kwargs flattening); reads from `closing_salutation` in the JSON
- `share_to_procore` → `procore`

The `generate_email_from_draft` call in this file's example doesn't pass these explicitly — they go through `editorial_to_kwargs`. So most likely only the prose / cross-references need updates.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/email.md
git commit -m "$(cat <<'EOF'
docs(scheduling): email.md prose updated for v2 shape

References to closing_line / custom_paragraphs / share_to_procore
replaced with v2 equivalents. The generate_email_from_draft call
itself doesn't change — editorial_to_kwargs handles the flattening
at the seam.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 21: Update phases/report.md step 3b with Glob-resolved schedule-toolbox recipes

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/report.md`

- [ ] **Step 1: Locate step 3b (XER-driven Q&A)**

Run: `Grep "XER-driven Q" scheduling/skills/schedule-update/phases/report.md -n`

Step 3b is the section starting `### 3b. **No transcript** — XER-driven Q&A`.

- [ ] **Step 2: Replace step 3b's content**

Replace step 3b entirely (from `### 3b.` through the end of that subsection but not into step 4) with:

````markdown
### 3b. **No transcript** — XER-driven Q&A

**Don't write ad-hoc XER-parsing Python.** The schedule-toolbox plugin already ships `xer_compare.compare_schedules` and `update_review.expected_updates` — use them.

#### Resolve the script paths (path-portable)

Use the Glob tool with pattern `**/scheduling/skills/schedule-toolbox/references/xer_compare.py` to find the absolute path. Save the result as `xer_compare_path`. Repeat for `update_review.py` → `update_review_path`.

If Glob returns zero results for either, stop and tell the colleague:
> "Schedule-toolbox not found. Install or update the `scheduling` plugin via the marketplace, then re-run."

#### Compare this week's XER to last week's

Find the two most recent XER files: current-week XER in `{dated_folder}/*.xer`, previous-week XER in the most recent prior dated folder.

```bash
python -c "
import sys, json, os
sys.path.insert(0, os.path.dirname(r'<xer_compare_path>'))
from xer_compare import compare_schedules, _parse_xer_file
current  = _parse_xer_file(r'<dated_folder>/<current_xer_filename>')
previous = _parse_xer_file(r'<prev_dated_folder>/<prev_xer_filename>')
result = compare_schedules(current, previous)
print(json.dumps(result, indent=2, default=str))
"
```

Substitute `<xer_compare_path>` with the Glob result and the two XER paths with absolute paths.

Use the JSON output to populate the colleague-facing Q&A:
- `result['sc_date_change']` → "Substantial Completion moved from `{prev}` to `{current}` (`{delta}` days). What's the story?"
- `result['completed_this_week']` → "These finished since the last update: `{list}`. Which should I call out as successes?"
- `result['slipped']` → "These moved later: `{name}` (`{days_slipped}` days). Red flag, slipping task, or expected?"
- `result['unstarted']` → "These were planned to start but haven't: `{list}`. Still blocked, or will they start soon?"
- `result['logic_changes']` → activity adds/deletes/relationship changes (count summary, then "Any scope changes worth mentioning?")
- `result['critical_path_movement']` → "Critical path changed in these areas: `{list}`. Anything to highlight?"

#### Trade-specific upcoming work

If the colleague asks "what does {trade} need to update by next week?", drive `update_review.py` directly:

```bash
python "<update_review_path>" expected_updates "<current_xer_path>" "<future_date_YYYY-MM-DD>" --resource <trade_code>
```

The script returns JSON to stdout — `to_start`, `to_finish`, `in_progress` lists with task names + dates.

#### Open-ended round

After the XER-driven round, ask the open-ended round:
- "Anything else going great that I should add to Successes?"
- "Any red flags coming from the field — material, trade performance, weather, owner decisions?"
- "What are the 2–3 key items the team needs to focus on this coming week?"
- "Is there an EOT/recovery update? What changed with trade performance?"

Keep the conversation tight — ask 2–4 questions per turn. Confirm each answer before moving on.
````

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/report.md
git commit -m "$(cat <<'EOF'
docs(scheduling): report.md step 3b uses Glob-resolved schedule-toolbox recipes

XER-driven Q&A now invokes xer_compare.compare_schedules and
update_review.expected_updates directly. The recipe resolves the
script path with Glob — works for repo dev and plugin-cache layouts
without hardcoded paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 22: Update phases/procore.md for v2 `procore` field

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/procore.md`

- [ ] **Step 1: Replace all `share_to_procore` references with `procore`**

Run: `Grep "share_to_procore" scheduling/skills/schedule-update/phases/procore.md -n`

For each match (likely 3–5 sites in the file), update the field name. Use `Edit` with `replace_all: true` if the exact string appears multiple times consistently:

```
old: share_to_procore
new: procore
```

The semantic meaning of the field is unchanged; only the name changed.

- [ ] **Step 2: Update any prose referring to `attachments[].filename`**

Run: `Grep "filename" scheduling/skills/schedule-update/phases/procore.md -n`

Replace `attachments[].filename` references with `attachments[].name`. Same with `'filename'` field accesses in code blocks — replace with `'name'`.

- [ ] **Step 3: Update phases/status.md detection logic too**

Open `scheduling/skills/schedule-update/phases/status.md`. The detection check `screenshots/ has all required PNGs` needs to change because the screenshots phase is retired. Replace that row of the detection table with:

```
| `{dated_folder}/screenshots/{job_number}-{YYYY-MM-DD}-all-graphs-stacked.png` exists | Stacked PNG built (post-finalize) |
```

And update the no-arg routing block. Replace:
```
- If XER exists but no screenshots → "Run `/schedule-update screenshots`."
- If screenshots exist but no email → "Run `/schedule-update email` or `/schedule-update report`."
```

With:
```
- If XER exists but no `{YYYY-MM-DD}-email.json` → "Run `/schedule-update report`."
```

- [ ] **Step 4: Commit**

```bash
git add scheduling/skills/schedule-update/phases/procore.md scheduling/skills/schedule-update/phases/status.md
git commit -m "$(cat <<'EOF'
docs(scheduling): procore.md + status.md updated for v2 + retired screenshots phase

procore.md: share_to_procore → procore, filename → name throughout.
status.md: drop the screenshots PNG detection; replace with stacked-PNG
detection; update no-arg routing to skip the screenshots step.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 23: Clean up legacy v1 tests and run full test suite

**Files:**
- Modify: `scheduling/skills/schedule-update/tests/test_carry_forward.py` (delete legacy v1 cases)
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py` (delete legacy v1 cases)
- Modify: `scheduling/skills/schedule-update/tests/test_email_eml.py` (delete legacy v1 cases)

- [ ] **Step 1: Run the full test suite and inventory failures**

```bash
python -m unittest discover -s scheduling/skills/schedule-update/tests -v
```

Note each failure. They will fall into two buckets:
- **Legacy v1 assertions to delete** — tests that assert v1 row shape (`date_archived` present), v1 kwargs (`closing_line`, `custom_paragraphs`), v1 field names (`filename`, `share_to_procore`).
- **Tests to update** — tests that exercise behavior we still want, just with v2 inputs.

- [ ] **Step 2: For each legacy failure, decide delete vs update**

For each failing test:
- If the test was asserting a v1-only behavior we've deliberately removed (e.g. "removed items transition to archived", "filename field exists on attachment rows") → **delete the test method**.
- If the test exercises behavior that still exists (e.g. "transition_attachments preserves the procore flag from last week") → **update the test inputs/assertions to v2 shape**.

Use judgment, but err on deletion: the new v2 tests written in Tasks 7, 8, 9, 10, 11, 12 cover the v2 behavior. Legacy v1 coverage is dead weight.

- [ ] **Step 3: Re-run and verify clean**

```bash
python -m unittest discover -s scheduling/skills/schedule-update/tests -v
```

Expected: ALL tests pass. Zero failures, zero errors.

If anything still fails, fix the underlying code or test until it does.

- [ ] **Step 4: Commit**

```bash
git add scheduling/skills/schedule-update/tests/
git commit -m "$(cat <<'EOF'
test(scheduling): prune legacy v1 test cases, verify v2 suite is green

Tests asserting v1 row shape (date_archived present, filename field,
share_to_procore field, closing_line/custom_paragraphs kwargs,
'archived' status in non-key_items lists) are deleted. v2 coverage
written in earlier tasks (test_*_V2* classes) is the canonical surface.

Full test suite is green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 24: Final version bump 6.0.0-dev → 6.0.0 and marketplace.json lockstep

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json:3`
- Modify: `.claude-plugin/marketplace.json` (scheduling entry version)

- [ ] **Step 1: Strip `-dev` from plugin.json**

Edit line 3 of `scheduling/.claude-plugin/plugin.json`:
```json
"version": "6.0.0-dev",
```
to:
```json
"version": "6.0.0",
```

- [ ] **Step 2: Bump marketplace.json scheduling entry**

Open `.claude-plugin/marketplace.json`. Find the entry where `"name": "scheduling"` (around line 14). Update the `version` field on that entry:
```json
"version": "5.6.2"
```
to:
```json
"version": "6.0.0"
```

- [ ] **Step 3: Verify both files are staged together**

```bash
git status
```

Expected: only `scheduling/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` modified. No other files staged. (The hook's "exclude plugin.json from the check" exemption applies because the only scheduling-dir file in the staged set is plugin.json itself.)

- [ ] **Step 4: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "$(cat <<'EOF'
chore(scheduling): release 6.0.0 (v2 Forms MCP)

Strips -dev suffix; bumps marketplace.json scheduling entry to match.

This release includes:
- v2 canonical email JSON shape (recipients arrays, days_metric /
  gain_loss objects, closing_paragraphs / closing_salutation,
  attachment name / procore / optional ext, include_changes_report
  + changes_report_filename, key_items_archived sibling list,
  optional 'edited' flag on item rows).
- SKILL.md re-read-on-phase-transition rule and identical per-phase
  preambles.
- Retirement of phases/screenshots.md (Worker owns SmartPM fetching
  in v2); new phases/_render_graphs.md covers the stacked-PNG
  rasterization step.
- Path-portable schedule-toolbox helper recipes in phases/report.md
  step 3b (Glob-resolved invocation of xer_compare.compare_schedules
  and update_review.expected_updates).
- Deleted: generate_email_docx.py + 2 legacy .docx reference docs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Final sanity check**

```bash
python -m unittest discover -s scheduling/skills/schedule-update/tests -v
git log --oneline main..HEAD
```

Expected: all tests pass. Commit log shows ~24 commits on the branch since `main`, each focused and atomic.

The plan is complete.

---

## Self-review notes

**Spec coverage:**
- v2 canonical shape rewrite — Task 2.
- "if 422 with violations[]" escape hatch — Task 2.
- Cross-skill scripts discipline — Task 3.
- SKILL.md re-read rule + command matrix + pipeline ref — Task 4.
- Per-phase preamble on all phases/*.md — Task 5.
- Retire screenshots.md → _render_graphs.md — Task 6.
- carry_forward.reconcile_items v2 — Task 7.
- carry_forward.reconcile_key_items new function — Task 8.
- carry_forward.transition_attachments v2 — Task 9.
- email_draft_io.SUPPORTED_VERSIONS={2} — Task 10.
- email_draft_io.editorial_to_kwargs v2 — Task 11.
- generate_email_msg._build_html_body closing_paragraphs_html — Task 12.
- generate_email_eml.py closing_paragraphs_html — Task 13.
- email-draft-sample.json regenerate as v2 — Task 14.
- generate_changes_report_html.py v2 kwargs — Task 15.
- Delete generate_email_docx.py + 2 .docx — Task 16.
- phases/_carry_forward.md v2 — Task 17.
- phases/_attachments.md v2 — Task 18.
- phases/draft.md seed-builder v2 — Task 19.
- phases/email.md v2 kwargs — Task 20.
- phases/report.md step 3b Glob recipes — Task 21.
- phases/procore.md v2 + phases/status.md retired screenshots — Task 22.
- Legacy v1 test pruning + full suite green — Task 23.
- Final version bump 6.0.0 + marketplace lockstep — Task 24.

All spec sections covered.

**Placeholder scan:** No "TBD", "TODO", "implement later", or "similar to Task N" placeholders. All test code is concrete; all file edits are concrete.

**Type consistency:** Function signatures match across tasks (reconcile_items, reconcile_key_items, transition_attachments, editorial_to_kwargs, _build_html_body). Field names match between spec and tasks (name not filename, procore not share_to_procore, days_metric, gain_loss, closing_paragraphs, closing_salutation, etc.). No drift detected.
