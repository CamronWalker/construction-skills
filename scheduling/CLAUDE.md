# Scheduling Plugin — Instructions for Claude

Plugin-level guidance that applies to every skill under `scheduling/skills/`. The repo-root [CLAUDE.md](../CLAUDE.md) covers cross-plugin release conventions; this file is for scheduling-specific contracts.

## Iterating on chart HTML — use the live preview loop

When the user wants to change how a chart in `scheduling/skills/schedule-update/references/charts/` looks (the SmartPM summary report, plan-vs-actual, schedule changes, etc.), **do not edit the renderer file blind**. The renderers emit a wall of CSS + SVG + table markup, and the only way to know whether a tweak landed right is to see it. The workflow that has worked in practice:

### 1. Spin up Claude Desktop's Preview as the iteration surface

Write `.claude/launch.json` (this file is gitignored — fine to leave checked-in or to drop after the session):

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "summary-report",
      "runtimeExecutable": "python",
      "runtimeArgs": ["-m", "http.server", "5173", "--bind", "127.0.0.1", "--directory", ".preview/<slug>"],
      "port": 5173
    }
  ]
}
```

Then call `mcp__Claude_Preview__preview_start` with `name: "summary-report"`. The Preview pane on the right of Claude Desktop now serves `.preview/<slug>/index.html` and refreshes on demand. The user can click any element in the preview and ship it back to you as a `<launch-selected-element>` payload — far higher signal than a screenshot annotation.

### 2. Render the chart with the real renderer

```text
Bash, one-liner:
  node -e "
    import('./scheduling/skills/schedule-update/references/charts/<slug>.js').then(m => {
      const fs = require('fs');
      const payload = JSON.parse(fs.readFileSync('scheduling/skills/schedule-update/references/charts/tests/fixtures/<slug>.json','utf8'));
      const { html } = m.render<Whatever>(payload);
      fs.writeFileSync('.preview/<slug>/index.html', html);
    });
  "
```

The fixtures under `tests/fixtures/` are sized for real projects (Wellington Temple, etc.), so what you see in the preview matches what a real schedule update would produce.

### 3. Patch the rendered HTML to mock the design change — do NOT edit the renderer yet

For each iteration, take the renderer's output and apply a small string-replace patch to demo the change. This is fast, low-risk, and reversible: the user is reviewing pixels, not committing to source. Keep the patch script at `.preview/render-<slug>.mjs`; it imports the renderer, mutates the returned HTML (drop a section, swap CSS rules, restructure a block), and writes to `.preview/<slug>/index.html`. The user refreshes the Preview pane after each push.

Patching is preferred over editing the source during iteration because:

- A typical session pushes 6–12 visual revisions. Editing the renderer for each one means committing half-thought-through state into version control.
- Many tweaks are pure CSS or trivial markup substitutions that translate cleanly from a string-replace into a source edit at the end.
- If the user changes their mind (they often do), reverting a `.preview/render-<slug>.mjs` line is one Edit. Reverting the renderer is a full diff.

### 4. Port the approved design into the real source

Once the user says "this looks good, move on", do exactly two things:

1. Apply the patched-in changes to the renderer file (`<slug>.js`) as a clean source edit.
2. Re-render straight from the updated source into `.preview/<slug>/index.html` and ask the user to refresh once. This is the regression check — if the source-rendered output diverges from the patched preview the user just approved, you have a bug in the port.

Then update the renderer's test file, bump versions per [the release convention](../CLAUDE.md), and clean up the preview server (`preview_stop` with the `serverId` from `preview_start`).

### What to skip

- Don't render via the full `cli.js` batch pipeline during iteration — it produces PNGs through headless Chromium, which adds 5–10 s per cycle for no benefit. The Preview pane renders HTML directly.
- Don't introduce a wrapper script in `references/charts/` for the preview workflow — the patch script lives in `.preview/` and dies with the session.
- Don't commit `.preview/`. It's gitignored. The renderer source and the test file are the durable artifacts.

## Drive the existing scripts — don't wrap them

Every skill under `scheduling/skills/{skill}/references/` ships its own renderers, generators, and parsers — `charts/cli.js`, `email_draft_io.py`, `generate_email_eml.py`, `iterate.py` for proposal schedules, and so on. When you need to produce or regenerate an artifact, drive those scripts directly. **Do not write a wrapper file that embeds tool output as literals or defines hardcoded sample kwargs.**

### Canonical pattern for MCP → chart rendering

```text
1. For each slug in graph_screenshots (from project-context.html):
     Call the documented MCP endpoint (see phases/screenshots.md per-slug recipes).
     Take the response as-is.
     Write tool → {dated_folder}/.chart-payload/{slug}.json
   (One Write call per slug. No transformation, no Python literal-pasting,
   no "let me assemble it in a script first". The renderer already
   knows the shape.)

2. Bash tool, one invocation for the whole batch:
     node scheduling/skills/schedule-update/references/charts/cli.js \
          "{dated_folder}/.chart-payload" "{dated_folder}/screenshots"
```

### Canonical pattern for email draft I/O

```text
Bash tool, python -c one-liner:
  python -c "
  import sys; sys.path.insert(0, 'scheduling/skills/schedule-update/references')
  from email_draft_io import load_draft
  draft = load_draft('<dated_folder>/<YYYY-MM-DD>-email.json')
  # inspect draft['this_week'], draft['last_week'], draft['graphs'], etc.
  "
```

The cloud editor at `westland-mcps` writes the JSON file; the local skill reads it via `email_draft_io.load_draft` and builds the `.eml`. Do not check in a `test_*.py` next to the shipping scripts — colleagues mistake them for product code, and they rot the instant the underlying script's shape changes.

### Why this matters

| Anti-pattern | What it costs |
|--------------|---------------|
| Embedding ~200 lines of MCP response JSON as Python literals | Pure token waste — the JSON was already in the tool result. Dump it to disk with `Write` instead. |
| Wrapper script that re-declares the canonical input shape | Drifts silently when the renderer adds or renames a field. The wrapper "works" until someone notices the chart looks wrong. |
| `test_xyz.py` checked in beside shipping scripts | Future colleagues can't tell product code from harness. The `scripts/` folder at repo root is for repo-wide tools (e.g. `build.py`), not per-skill ad-hoc helpers. |

If you genuinely need an orchestration file (e.g. a new shipping CLI that some future skill will call), put it under the skill's `references/` directory, give it a clear non-test name, and update the skill's `SKILL.md` / phase files to document it. Otherwise: `Write` + `Bash`, no `.py` files.

### Where the per-slug recipes live

`phases/screenshots.md` has the exact MCP tool, parameters, response shape, and payload assembly for every chart slug. Read it before fetching anything; do not improvise endpoint choices.

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

## XER files are immutable

Repeated from the skill files for visibility: never `Edit`, never overwrite-`Write`, never `rm` / `Remove-Item` a `.xer` in any project folder. Westland's PreToolUse hook blocks this physically; if you find yourself wanting to, you've misunderstood the workflow — write a new versioned file (`-v2.xer`, `-v3.xer`) alongside instead, or stop and ask.

## HTML CRUD goes through the parse/generate pair

This is the project-context.html lesson from W1177 applied generally: never `Read` → `Edit` → `Write` an embedded-image-bearing HTML directly. Round-tripping ~17KB base64 logos through tool I/O corrupts them. Use the dedicated parse + generate scripts for every artifact that has one (`generate_project_context_html.py` / `parse_project_context_html.py` for the project context). The weekly email no longer round-trips through HTML — it lives in `{YYYY-MM-DD}-email.json` and the cloud editor handles all read/write — but the same rule applies if you ever need to script project-context.html.
