# Schedule-update v2 — Forms MCP integration + skill discipline pass

**Status:** Approved, ready for implementation planning.
**Author:** Camron Walker (via brainstorming session 2026-05-24).
**Plugin:** `scheduling` (bumps to **6.0.0**).

## Goal

Bring the `schedule-update` skill in lockstep with the deployed `westland-forms/weekly-schedule-update-email` Worker, which has rejected v1 seeds (`SEED_VERSION_TOO_OLD` 422) since 2026-05-24. While in the same diff:

1. Eliminate dead code from the cloud-editor migration — generation paths the Worker now owns or that the new finalize-only flow has obsoleted.
2. Promote schedule-toolbox helper scripts (`xer_compare.py`, `update_review.py`) into the colleague-facing flow so Claude stops writing ad-hoc XER-walking Python instead of using the canonical implementations.
3. Add a mechanical re-read rule that protects every phase transition from session-stale recall: each phase begins with a TaskCreate task whose sole job is to reload the phase file's text into current context, regardless of how much conversation has already accumulated.

Nothing in this design changes the Worker schema. The Worker is already v2-canonical; this is skill-side catch-up.

## Background

### Why now

The deployed Worker has been v2-only since 2026-05-24. Any project that runs `/schedule-update report` against a fresh `(project, report_date)` today gets a 422 because the local skill is still emitting v1 seeds. No active project is mid-cycle, so there's no migration concern.

### What v2 changes vs v1

The Worker's canonical schema (<https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema>) introduces breaking renames and shape changes from v1:

- Recipients (`to`, `cc`) became arrays of `{name, email}` objects (`to_recipients`, `cc_recipients`).
- Signed-int `days_behind` became `days_metric: {direction, value}`.
- Signed-int `gain_loss` + separate `gain_loss_narrative` string merged into `gain_loss: {direction, value, narrative, narrative_changed}`.
- Attachment fields renamed: `filename` → `name`, `share_to_procore` → `procore`. Optional `ext` added.
- `custom_paragraphs` + `closing_line` merged into single `closing_paragraphs` array; `salutation` renamed `closing_salutation`.
- `changes_report: {include, filename}` object flattened to `include_changes_report` + `changes_report_filename`.
- Item rows: `date_archived` removed from four lists (`successes`, `red_flags`, `stalled_tasks`, `key_items`) — these lifecycle active → removed → dropped only. Archived state isolated to a new sibling list `key_items_archived`. Item rows gain an optional `edited: bool` set when status='active' and text differs from `last_week[prev_idx].text`.
- `graph_order` array introduced (8 trend slugs by default; the skill emits 9 with `smartpm-summary-report` appended for the stacked PNG).

### What changed structurally about the pipeline

The pre-v2 flow had a separate `phases/screenshots.md` that fetched chart data from SmartPM via MCP, wrote payload JSON to `.chart-payload/`, and ran `references/charts/cli.js` to render local PNGs. **The Worker now owns all of that.** The skill POSTs the v2 seed, the Worker enqueues SmartPM ingest server-side, and the `finalize_weekly_schedule_update_email` response carries `graphs.{slug}.html` (server-rendered HTML+SVG) for every entry in `graph_order`. The local job shrinks to: stack the chunks, rasterize to one PNG via `html_to_png.cjs`, embed in the .eml.

The `references/charts/` library survives unchanged — it stays in place for future ad-hoc "render a chart in a Claude window" use, an MCP-fed render-on-demand path, or any other workflow we haven't built yet. The email pipeline just no longer drives it.

## Design

### Scope summary

| File | Change |
|---|---|
| `scheduling/CLAUDE.md` | Rewrite "Email JSON shape" section to v2 verbatim (see [v2 canonical shape](#v2-canonical-shape) below). Add "if 422 with violations[], refetch live schema from URL" escape hatch. Add cross-skill-scripts discipline subsection. |
| `scheduling/skills/schedule-update/SKILL.md` | Add re-read-on-phase-transition rule, drop `screenshots` from command matrix + pipeline table, renumber pipeline rows. |
| `phases/copy.md`, `phases/email.md`, `phases/draft.md`, `phases/report.md`, `phases/procore.md`, `phases/status.md`, `phases/_carry_forward.md`, `phases/_attachments.md` | Each gains identical top-of-file preamble. Internal content updates per v2 field names. |
| `phases/screenshots.md` | Renamed to `phases/_render_graphs.md`. Stripped to: load `graphs.{slug}.html` from finalize payload, stack per `graph_order`, rasterize via `html_to_png.cjs`. No more SmartPM MCP recipes. No public `/schedule-update screenshots` command. |
| `phases/report.md` step 3b | Path-portable copy-paste recipes for `xer_compare.compare_schedules` and `update_review.expected_updates` via Glob path resolution. Replaces ad-hoc XER-walking prose. |
| `phases/draft.md` | Seed-builder rewritten for v2 shape. Folds in stacked-PNG rasterization via `_render_graphs.md`. |
| `references/carry_forward.py` | `reconcile_items` returns rows with `prev_idx` + optional `edited`, drops `date_archived` on four lists. New `reconcile_key_items` splits `key_items` + `key_items_archived`. `transition_attachments` returns `name`/`procore`/optional `ext`. |
| `references/email_draft_io.py` | `SUPPORTED_VERSIONS = {2}`. `editorial_to_kwargs` translates v2 → builder kwargs (recipients flatten, days_metric/gain_loss object → signed int, closing_paragraphs join → HTML, key_items_archived ignored for body). |
| `references/generate_email_eml.py`, `generate_email_msg.py` | `_build_html_body` gains `closing_paragraphs_html` kwarg, drops `closing_line` + `custom_paragraphs`. Docstring HTML-tag canon updated to `<b>` / `<i>` / `#FFF4B8` / `#9B2C2C`. |
| `references/generate_changes_report_html.py` | Read v2 fields. `key_items_archived` excluded (matches email body — archived items are hidden everywhere except the editor). |
| `references/generate_email_docx.py` | **Delete** — orphaned. |
| `references/Master Schedule Update Email Example.docx`, `Schedule Update Email Procedure.docx` | **Delete** — legacy reference docs. |
| `tests/test_carry_forward.py`, `tests/test_email_draft_io.py`, `tests/test_email_eml.py`, `tests/fixtures/email-draft-sample.json` | Update for v2 shapes. |
| `scheduling/.claude-plugin/plugin.json` | Bump to **6.0.0**. |
| `.claude-plugin/marketplace.json` (scheduling entry) | Bump to **6.0.0** (lockstep per pre-commit hook). |

Files **not** touched (intentional): `commands/write-weekly-schedule-email.md`, `take-screenshots.bat`, `evals/evals.json`, `references/charts/*` (library survives for future use), `references/html-to-pdf.js`, `references/package.json`, `references/westland-logo.png`, `references/email-template.md`, `references/checklist-template.md`, the proposal-schedule skill, schedule-toolbox itself.

### v2 canonical shape

The full Markdown block that replaces `scheduling/CLAUDE.md`'s "Email JSON shape — single source of truth" section.

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
        "ext":      "pdf",          // optional
        "checked":  true,
        "procore":  false,
        "status":   "active",       // 'active' | 'new' | 'removed'
        "prev_idx": 0               // null when status='new'
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
    "06-end-date-variance":                   { "html": "<svg…>…", "data": { } },
    /* …seven more, one per `graph_order` entry… */
  }
}
```

### Item row shape — used in `successes` / `red_flags` / `stalled_tasks` / `key_items` / `key_items_archived`

```jsonc
{
  "text":     "<div>Building slab pour complete; field has <b>moved past</b> the slab-prep front.</div>",
  "status":   "active",   // 'active' | 'new' | 'removed' | 'archived'
  "checked":  true,
  "edited":   false,       // OPTIONAL; only set when status='active' AND text differs from last week
  "prev_idx": 0             // index into last_week.<same-list>; null when status='new'
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
  "name":     "Report 01 - Foo.pdf",   // basename, no path
  "ext":      "pdf",                    // OPTIONAL; lowercase, no dot
  "checked":  true,                     // include in this email
  "procore":  false,                    // the P toggle — upload to Procore Documents
  "status":   "active",                 // 'active' | 'new' | 'removed'
  "prev_idx": 0                          // null when status='new'
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

### SKILL.md changes

Three additions:

#### Re-read rule (added near top of SKILL.md, after the existing "Before invoking any sub-command — read the right phase files" callout)

````markdown
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
…etc.
```

Why this works: each re-read task forces the phase file's exact field names, function signatures, and ordering back into context just before the work that depends on them. After 100k+ of context the phase files' lemmas haven't drifted — just your recall of them.

Phase files all open with an identical preamble (next section) so when you hit one of these tasks you know exactly what to load.
````

#### Per-phase preamble (added as first lines of every `phases/*.md` file)

````markdown
> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `<phase-name>` phase; any divergence from it is a bug.

> Loaded by SKILL.md's router when the user invokes `/schedule-update <phase-name>` (or when called as an internal dependency from another phase).
````

Two lines, no blank-line separator, phase-name placeholder filled per file. Internal "_"-prefixed files (`_carry_forward.md`, `_attachments.md`, `_render_graphs.md`) substitute "called as an internal dependency from another phase" for the user-invocation line.

#### Command Matrix and Pipeline Reference (replace lines 25–38 and the Pipeline Reference table)

````markdown
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
````

### `references/` Python diffs

#### `carry_forward.py`

**`reconcile_items(last_week_items, this_week_texts, today_iso=None, similarity_threshold=0.6) -> (this_week_rows, last_week_baseline)`**

Row shape changes. Returned `this_week_rows[i]`:

```python
{
  'text':     str,        # HTML passthrough
  'status':   str,        # 'active' | 'new' | 'removed'   (NO 'archived' for these four lists)
  'checked':  bool,
  'edited':   bool,       # ONLY present when status='active' AND text differs from last_week[prev_idx].text
  'prev_idx': int | None, # None when status='new'
}
```

`last_week_baseline[i]` is the same shape minus `prev_idx` and `edited` — pure pass-through of last week's normalized state.

Lifecycle change: items that fall out this week go to `status='removed'`. They do not transition to `status='archived'` next week — they simply drop. `MAX_ARCHIVED_DAYS` no longer applies to these lists.

**`reconcile_key_items(last_week_key_items, last_week_key_items_archived, this_week_texts, today_iso=None) -> (this_week_rows, this_week_archived_rows, last_week_baseline)`**

New function. Same fuzzy-matching logic as `reconcile_items`, but splits output:
- `this_week_rows` → `seed.this_week.key_items` (status: `active`/`new`/`removed`)
- `this_week_archived_rows` → `seed.this_week.key_items_archived` (status: `archived`, `date_archived` set)
- `last_week_baseline` → `seed.last_week.key_items` (active key_items only)

90-day prune applies: archived rows older than `MAX_ARCHIVED_DAYS` drop from result entirely.

**`transition_attachments(last_week_attachments, fresh_filenames=None, today_iso=None) -> list`**

Field renames. Returned rows:

```python
{
  'name':     str,         # basename (was 'filename')
  'ext':      str,         # OPTIONAL; lowercase, no dot
  'checked':  bool,
  'procore':  bool,        # was 'share_to_procore'
  'status':   str,         # 'active' | 'new' | 'removed' (NO 'archived', NO date_archived)
  'prev_idx': int | None,
}
```

Lifecycle: active → removed → dropped (no archived pile). `_PROCORE_BOOTSTRAP_PATTERNS` and `_normalize_attachment_name` survive unchanged.

**Removed:** `transition_items()` (legacy non-reconciling helper, already unused). `MAX_ARCHIVED_DAYS` becomes module-private to `reconcile_key_items` only.

#### `email_draft_io.py`

**`SUPPORTED_VERSIONS = {2}`** — v1 raises `DraftError`. No backward compatibility.

**`REQUIRED_TOP_LEVEL_KEYS`** — unchanged: `{'version', 'report_date', 'project_info', 'this_week'}`. `last_week` and `graphs` optional at top level.

**`editorial_to_kwargs(this_week, project_info=None, last_week=None)`** — all v2→builder flattening lives here:

```python
def editorial_to_kwargs(this_week, project_info=None, last_week=None):
    this_week = this_week or {}
    pi = project_info or {}

    to_str = _format_recipients(this_week.get('to_recipients'))
    cc_str = _format_recipients(this_week.get('cc_recipients'))

    dm = this_week.get('days_metric') or {}
    days_behind = (+1 if dm.get('direction') == 'behind' else -1) * int(dm.get('value') or 0)

    gl = this_week.get('gain_loss') or {}
    gain_loss = (-1 if gl.get('direction') == 'loss' else +1) * int(gl.get('value') or 0)
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
        # key_items_archived: NOT rendered in the .eml body. UI-only.
        'eot_recovery':        this_week.get('eot_recovery', '') or '',
        'logic_changes':       this_week.get('logic_changes', '') or '',
        'smartpm_changelog_url': this_week.get('smartpm_changelog_url', '') or '',
        'closing_paragraphs_html': closing_html,
        'salutation':              this_week.get('closing_salutation', '') or '',
        'signer_name':  this_week.get('signer_name', '') or '',
        'signer_title': this_week.get('signer_title', '') or '',
        'signer_mobile': this_week.get('signer_mobile', '') or '',
        'attachment_paths': _attachment_names_for_email(this_week.get('attachments')),
    }

    if last_week:
        prev_dm = last_week.get('days_metric') or {}
        prev_gl = last_week.get('gain_loss') or {}
        kwargs['prev_days_behind'] = (+1 if prev_dm.get('direction') == 'behind' else -1) * int(prev_dm.get('value') or 0)
        kwargs['prev_gain_loss']   = (-1 if prev_gl.get('direction') == 'loss'   else +1) * int(prev_gl.get('value') or 0)
    else:
        kwargs['prev_days_behind'] = None
        kwargs['prev_gain_loss']   = None

    return kwargs
```

Helpers (module-private):
- `_format_recipients(arr)` — `[{name, email}]` → `"Name <email>; Other <email2>"`. Empty/None → `''`.
- `_join_closing_paragraphs(arr)` — filter `checked=True`, concatenate `text` fields. Empty/None → `''`.
- `_items_for_email_body(arr)` — filter `checked=True && status != 'removed'`. Returns list of HTML strings.
- `_attachment_names_for_email(arr)` — filter `checked=True && status != 'removed'`. Returns list of basenames.

**`build_stacked_chart_page`, `render_stacked_png`, `generate_email_from_draft`** — signatures unchanged. Internals already operate on `graph_order` + `graphs.{slug}.html`, which match v2.

#### `generate_email_eml.py` and `generate_email_msg.py`

**`_build_html_body(...)`** — signature gains `closing_paragraphs_html: str` kwarg, drops `closing_line: str` and `custom_paragraphs: list`. The closing block renders as:

```html
{closing_paragraphs_html}
<p>{salutation}</p>
<p>{signer_name}<br>{signer_title}<br>{signer_mobile}</p>
```

Where `closing_paragraphs_html` is pre-joined HTML from `_join_closing_paragraphs`.

Docstring HTML-tag canon updated from `<strong>`/`#C94444`/`#FFF59D` to `<b>`/`<i>`/`#FFF4B8`/`#9B2C2C`. Runtime is pure HTML passthrough — no parsing — so this is doc-only.

Recipients consumed as semicolon strings (already flattened by `editorial_to_kwargs`). `_normalize_recipients` (semicolon→comma for RFC 5322) and Outlook COM `mail.To = ...` paths unchanged.

`_ensure_subject_has_date` unchanged.

#### `generate_changes_report_html.py`

`generate_changes_report_attachment(output_path, **kwargs)` gains v2-aware kwargs:
- `days_metric` / `gain_loss` objects → signed-int + direction word for header strikethrough.
- `closing_paragraphs[checked]` → "Closing" section (replaces old `custom_paragraphs` + `closing_line`).
- Attachments display `name` (not `filename`); `procore` column joins the diff table.
- `key_items_archived`: **excluded** from the PDF. Matches the email body — archived items are hidden everywhere except the editor.

The orchestrator path (`generate_changes_report_attachment` → `generate_changes_report` → `html-to-pdf.js`) is unchanged.

#### Deletions

- `references/generate_email_docx.py` — orphaned; no phase references it.
- `references/Master Schedule Update Email Example.docx` — legacy reference doc.
- `references/Schedule Update Email Procedure.docx` — legacy reference doc.

#### Test updates

- `tests/test_carry_forward.py` — rewrite for `reconcile_items` v2 rows (no `date_archived`, optional `edited`); add coverage for `reconcile_key_items`; update `transition_attachments` cases for `name`/`procore`/no archived.
- `tests/test_email_draft_io.py` — load v2 fixture; assert `editorial_to_kwargs` produces correct signed-int / string / HTML kwargs; assert v1 input raises `DraftError`.
- `tests/test_email_eml.py` — assert `_build_html_body` consumes `closing_paragraphs_html` and emits expected HTML; remove `closing_line` / `custom_paragraphs` cases.
- `tests/fixtures/email-draft-sample.json` — regenerate as v2 (recipients arrays, `days_metric` object, `key_items_archived` list, attachments with `name`/`procore`, `closing_paragraphs`).

### Schedule-toolbox helper integration

Goal: make `xer_compare.compare_schedules` and `update_review.expected_updates` discoverable from inside `phases/report.md` so Claude actually invokes them instead of writing ad-hoc Python.

#### Path-portable recipe in `phases/report.md` step 3b

```markdown
### Week-over-week XER comparison

**Don't write ad-hoc XER-parsing Python.** The schedule-toolbox plugin already ships `xer_compare.compare_schedules` — use it.

#### Resolve the script path (path-portable)

Use the Glob tool with pattern: `**/scheduling/skills/schedule-toolbox/references/xer_compare.py`

Save the result as `xer_compare_path`. If Glob returns zero results, the scheduling plugin isn't installed — stop and tell the colleague:
> "Schedule-toolbox not found. Install or update the `scheduling` plugin via the marketplace, then re-run."

#### Compare this week's XER to last week's

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

Substitute `<xer_compare_path>` with the Glob result, and the two XER paths with the absolute paths to this week's and last week's `.xer` files. The script returns JSON to stdout — Claude reads it via Bash tool result.

Use the JSON to populate the colleague-facing Q&A per `phases/report.md` step 3b prose.

### Trade-specific upcoming work

```bash
python <update_review_path> expected_updates <current_xer_path> <future_date> --resource <trade_code>
```

Where `<update_review_path>` comes from `Glob: **/scheduling/skills/schedule-toolbox/references/update_review.py`. Output is JSON to stdout — `to_start`, `to_finish`, `in_progress` lists with task names + dates.

**Do not** write a custom Python script to walk the XER. The CLI exists; use it.
```

#### Cross-skill discipline addendum to `scheduling/CLAUDE.md`

Appended to the existing "Drive the existing scripts — don't wrap them" section:

```markdown
### Cross-skill scripts: same rule, with Glob for path resolution

The "drive existing scripts, don't wrap them" rule extends to scripts in **sibling skills** of the scheduling plugin. The week-over-week XER comparison helpers in `schedule-toolbox/references/` (`xer_compare.py`, `update_review.py`) are used by `schedule-update`'s `phases/report.md` and `phases/draft.md`.

**Resolve the path with Glob, then drive the script as-is.** Never:
- Hardcode `~/.claude/plugins/cache/...` (the version segment changes).
- Hardcode the repo path `C:\Users\camron\code\construction-skills\...` (only works on one machine).
- Copy the script into `schedule-update/references/` to avoid the cross-skill path (two copies drift).
- Write a one-off Python re-implementation of `compare_schedules` "because it's easier" (it isn't, and it diverges silently from the canonical implementation).

The recipe pattern in `phases/report.md` step 3b is the template. Apply it to any future cross-skill helper need.
```

## Out of scope

- Worker-side schema changes (none needed; the Worker is already v2-canonical).
- Proposal-schedule skill (independent of v2).
- Schedule-toolbox itself (used as-is; only the calling pattern from schedule-update changes).
- `references/charts/` library (kept in place for future use; no longer driven by the email pipeline).
- XER immutability hook in the westland plugin (already enforces correctly).
- Project-context HTML parse/generate scripts (no shape changes).
- `commands/write-weekly-schedule-email.md`, `take-screenshots.bat`, `evals/evals.json`.

## Risks

- **Path-portability fragility** — Glob-based path resolution depends on Claude Code Glob behavior; if Glob ever excludes plugin caches by default, recipes break. Mitigation: the recipe's "if Glob returns zero" branch tells the colleague to reinstall, which is a clear failure mode.
- **Re-read fatigue** — adding ~5 extra TaskCreate "[re-read]" tasks per run inflates the task list. Mitigation: the `[re-read]` prefix makes them visually distinct in the task UI; they don't clutter the substantive work.
- **`generate_changes_report_html.py` v2 update lag** — this file is large (~33 KB) and used at every weekly update where `include_changes_report=True`. A v1→v2 bug here corrupts the changelog PDF silently. Mitigation: the test suite gains a v2 fixture case for the changes-report renderer; CI fails fast on shape drift.

## Verification

After implementation lands:

1. **Local tests pass:**
   ```bash
   python -m unittest discover -s scheduling/skills/schedule-update/tests
   ```
2. **Worker round-trip on a fresh project:**
   - Pick a project with no `{prev_date}-email.json` on disk (week-1 of v2).
   - Run `/schedule-update report`.
   - Inspect the POST payload: `version: 2`, recipients arrays, `days_metric` object, `closing_paragraphs`, attachments with `name`/`procore`.
   - Verify Worker returns 200 with `editor_url` (not 422 with `violations[]`).
   - Open the editor; confirm all fields render and edits autosave.
   - Say "done" in chat; finalize completes and writes `{YYYY-MM-DD}-email.json` v2-shaped.
   - Verify the `.eml` opens in Outlook with the stacked PNG, attachments, recipients, signer block all correct.
3. **Worker round-trip on an existing project (week-N of v2):**
   - Pick a project that's run `/schedule-update report` at least once under v2.
   - Verify `last_week` is the prior week's `this_week` verbatim.
   - Verify `prev_idx` walks correctly for at least one strikethrough-rendered item.
4. **Helper-script invocation discipline:**
   - Run the `report` flow on a project without a meeting transcript (forces XER-driven Q&A).
   - Verify Claude invokes `xer_compare.compare_schedules` via the Glob-resolved path, not via an ad-hoc walker. Visible in the Bash tool call.

If any step fails: the Worker's 422 `violations[]` array names the exact JSON path that drifted. Fix the seed-builder in `phases/draft.md` or the kwarg-translation in `email_draft_io.editorial_to_kwargs`, re-run, repeat until clean.
