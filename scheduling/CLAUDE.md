# Scheduling Plugin — Instructions for Claude

Plugin-level guidance that applies to every skill under `scheduling/skills/`. The repo-root [CLAUDE.md](../CLAUDE.md) covers cross-plugin release conventions; this file is for scheduling-specific contracts.

## Drive the existing scripts — don't wrap them

Every skill under `scheduling/skills/{skill}/references/` ships its own renderers, generators, and parsers — `charts/cli.js`, `generate_email_preview_html.py`, `parse_email_html.py`, `iterate.py` for proposal schedules, and so on. When you need to produce or regenerate an artifact, drive those scripts directly. **Do not write a wrapper file that embeds tool output as literals or defines hardcoded sample kwargs.**

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

The skill emits this shape into its seed; the Worker validates on `generate_weekly_schedule_update_email_draft` and on every `PUT /editorial`. Drift between this doc and the Worker schema is a bug in this doc — the Worker is authoritative.

### The canonical shape

```jsonc
{
  "version":     1,
  "report_date": "YYYY-MM-DD",
  "project_info": {
    "project_name": "...",
    "job_number":   "...",
    "contractual_completion": "...",
    "projected_completion":   "..."
  },

  "this_week": {
    "subject": "...", "to": "...", "cc": "...",
    "days_behind": int, "gain_loss": int,

    "successes":     [/* item rows */],
    "red_flags":     [/* item rows */],
    "stalled_tasks": [/* item rows */],
    "key_items":     [/* item rows */],

    "gain_loss_narrative":   "...",
    "eot_recovery":          "...",
    "logic_changes":         "...",
    "smartpm_changelog_url": "https://...",

    "custom_paragraphs": [{"label": "...", "text": "<div>...</div>", "checked": true}],
    "attachments":       [/* attachment rows — see below */],
    "changes_report":    {"include": bool, "filename": "..."},
    "skip_procore":      bool,

    "closing_line": "Please let me know if you have any questions.",
    "salutation":   "Thanks,",
    "signer_name":  "...", "signer_title": "...", "signer_mobile": "..."
  },

  "last_week": { /* identical shape; frozen copy; null for week-1 of new pipeline */ },

  "smartpm": { "project_name": "...", "scenario_id": null },

  "graphs": {
    "<slug>": { "html": "<svg…>…", "data": { } },
    ...
  }
}
```

### Item row shape — used in `successes` / `red_flags` / `stalled_tasks` / `key_items`

```jsonc
{
  "text":          "<div>Building slab pour complete; field has <strong>moved past</strong> the slab-prep front.</div>",
  "checked":       true,
  "status":        "active",   // 'active' | 'new' | 'removed' | 'archived'
  "date_archived": "",          // 'YYYY-MM-DD' when status='archived', else ''
  "prev_idx":      0             // index into last_week.<same-list>; null when status='new'
}
```

Two breaking changes versus the legacy `-email-preview.html` shape:

1. **`prev_idx` (int|null) replaces `previous_text`.** Diff overlays in the editor and "strikethrough-previous-metric" badges in the `.eml` are computed by walking from `this_week.<list>[i]` → `last_week.<list>[this_week.<list>[i].prev_idx]`. The denormalized `previous_text` field is gone.
2. **`text` is HTML, not markdown.** Drop the `**bold**` / `==priority==` conventions. Use:
   - `<strong>...</strong>` — bold
   - `<span style="color:#C94444;font-weight:bold">...</span>` — priority red (Westland brand red)
   - `<span style="background-color:#FFF59D">...</span>` — highlight (light yellow)

   The Trix editor in the cloud surface emits these inline-style spans verbatim; the `.eml` builder passes them through without conversion.

### Attachment row shape

```jsonc
{
  "filename":         "...",
  "checked":          true,         // include in this email
  "status":           "active",     // 'active' | 'new' | 'removed' | 'archived'
  "date_archived":    "",
  "share_to_procore": false,        // the P toggle — picks Procore upload set
  "prev_idx":         0
}
```

### The Procore fields are load-bearing

`this_week.attachments[].share_to_procore` and `this_week.skip_procore` drive the Procore Documents upload via [`phases/procore.md`](skills/schedule-update/phases/procore.md). They are not cosmetic. Missing them in the JSON snapshot means the colleague's choice ("don't upload the owner summary to a public folder") is lost — that's a privacy bug, not a UX nit.

### `last_week` is frozen

When `phases/draft.md` builds this week's seed, it takes the *prior* week's `{prev_date}-email.json` and copies the entire `this_week` subtree into the new `last_week` slot — unchanged for the lifetime of this week's draft. The SPA renders strikethroughs on changed metrics, diff badges on changed item text, and visual chips on attachments that moved between weeks, all by reading `last_week`. The local `.eml` builder reads `last_week.days_behind` / `last_week.gain_loss` to render strikethrough-previous-metric badges on the colored status lines.

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

### Deprecated — slated for deletion

The pre-cloud-editor `*-email-preview.html` round-trip is being removed:

- ~~`generate_email_preview_html.py`~~ — DEPRECATED. Deleted in fix #6 of this PR.
- ~~`parse_email_html.py`~~ — DEPRECATED. Deleted in fix #6 of this PR.
- ~~`tests/test_email_preview_html.py`~~ — DEPRECATED. Deleted in fix #6 of this PR.

Until the deletion commit lands, do not add new callers of those modules. The seed-emission path in `phases/draft.md` reads `{prev_date}-email.json` only — the legacy HTML parser is not a fallback in the new flow.

## XER files are immutable

Repeated from the skill files for visibility: never `Edit`, never overwrite-`Write`, never `rm` / `Remove-Item` a `.xer` in any project folder. Westland's PreToolUse hook blocks this physically; if you find yourself wanting to, you've misunderstood the workflow — write a new versioned file (`-v2.xer`, `-v3.xer`) alongside instead, or stop and ask.

## HTML CRUD goes through the parse/generate pair

This is the project-context.html lesson from W1177 applied generally: never `Read` → `Edit` → `Write` an embedded-image-bearing HTML directly. Round-tripping ~17KB base64 logos through tool I/O corrupts them. Use the dedicated parse + generate scripts for every artifact that has one (`generate_project_context_html.py` / `parse_project_context_html.py` for the project context). The weekly email no longer round-trips through HTML — it lives in `{YYYY-MM-DD}-email.json` and the cloud editor handles all read/write — but the same rule applies if you ever need to script project-context.html.
