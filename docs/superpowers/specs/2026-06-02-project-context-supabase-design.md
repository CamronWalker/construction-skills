# Project context → Supabase (`wnd_projects` + `wnd_project_log`)

**Status:** Approved for implementation planning.
**Author:** Camron Walker (via brainstorming session 2026-06-02).
**Plugins:** `scheduling` (skill-side cutover) + Westland MCP connector (`westland-mcps` repo, tool wiring — owned by the in-flight MCP-merge work).

## Goal

Retire `project-context.html` as the per-project source of truth and move project identity/bindings into Supabase, so the data stops going stale and stops depending on a file that has to be hand-saved and copied folder-to-folder. The generic launchers (open a session in the cwd, call weekly update) carry no project identity; the only stable anchor is the `W#### - Name` folder, so the new design keys everything off **`job_number`** parsed from that folder.

Project context becomes a **Supabase row per project** read through the Westland MCP connector. Editing is **conversational + MCP** (no HTML editor). The base64-logo corruption fragility disappears because the editor stops being the store.

## Background

### Why the current approach fails

`project-context.html` does two jobs: it is the *data store* for project identity **and** an *editable HTML UI* wrapped around a ~17 KB embedded base64 logo that corrupts on any direct tool I/O (hence the strict parse/generate-script-only discipline + a test suite, and the W1177 Lubumbashi incident on 2026-05-07). As a per-project file it cannot be a single source of truth across machines / cowork / CLI: colleagues edit it in a browser and must remember to Save back to disk; nothing syncs; if init was never run the file is simply missing and the pipeline halts.

### Why Supabase, not "the JSON it uses"

The `{date}-email.json` is **week-grain and ephemeral** — the wrong home for project-grain data; storing context there re-creates staleness. Meanwhile the backend already points this direction:

- **`spm_projects`** (44 rows, PK `id`, unique `smartpm_id`, has `project_number`, `metadata` jsonb) is the canonical SmartPM project table.
- **`wnd_schedule_updates`** exists, is FK'd to `spm_projects`, and is **empty** — it was designed for weekly schedule email metadata and never wired. Someone already started down this road.
- The email pipeline already keys on `job_number` (`generate_weekly_schedule_update_email_draft(project=job_number…)`), the cloud editor already persists editorial state in Supabase (`wnd_email_drafts`), and the connector is **Procore-OAuth gated** — identity/auth is solved.

So Supabase finishes a path already laid rather than opening a new one.

## Design

### Data model — two tables

Both tables live in the **Power BI Sync** Supabase project (`anwdfilrfczluhudtbzw`), co-located with `spm_projects` and `wnd_bug_reports`, which the connector's internal service already writes to via Procore OAuth. A real FK to `spm_projects` only works same-database, which is the deciding factor.

#### `wnd_projects` — the Westland job-level anchor (1 row per project)

Renamed from the working title `wnd_project_settings`: it is the **expandable per-job record** that links the per-source-system tables (`spm_projects` now; Procore/Buildr later) under one `job_number`. Lean — only stable bindings + identity that are **not** already carried in the email JSON and **not** derivable from Procore.

```sql
create table wnd_projects (
  id                          uuid primary key default gen_random_uuid(),
  job_number                  text not null unique,            -- the key: W####, parsed from "W#### - Name" folder
  spm_project_id              int references spm_projects(id), -- nullable, opportunistically resolved
  project_name                text,
  smartpm_url                 text,                            -- workspace URL
  smartpm_trends_url          text,
  smartpm_changelog_url       text,
  smartpm_project_name        text,                            -- exact SmartPM card title (may differ from folder)
  procore_company_id          text default '11093',
  procore_project_id          text,
  procore_documents_folder_id text,
  source                      text default 'manual',           -- 'init' | 'migrated' | 'manual'
  created_by_email            text,                            -- stamped server-side from OAuth, not client-settable
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);
```

**Deliberately NOT stored here** (per design decisions):
- `contractual_completion` → pulled from **Procore** at email-build time (see open item on field mapping).
- `to_recipients` / `cc_recipients` and signer name/title/mobile (email signature) → live in the **email JSON**, seeded conversationally on the first email and carried forward week-over-week by the existing reconcile logic.
- `graph_order` → email JSON; defaults to the canonical 8-slug order when absent.

#### `wnd_project_log` — append-only log (1 row per entry)

Split out from `wnd_projects` so the row doesn't bloat and drag every settings read by end-of-project.

```sql
create table wnd_project_log (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references wnd_projects(id) on delete cascade,
  body             text not null,
  category         text not null default 'note',  -- 'note' | 'eot' | 'scope_change' | 'schedule_published' | ...
  created_at       timestamptz not null default now(),  -- the date-time link
  created_by_email text                                  -- stamped server-side from OAuth
);
create index wnd_project_log_project_created_idx on wnd_project_log (project_id, created_at);
```

The HTML's client-side date-locking of past log entries is **dropped** — it was a rendering concern; with conversational editing past entries simply aren't touched, and the append tool stamps the server's time.

RLS is enabled on both tables with no public policies (matches `wnd_bug_reports`); all writes go through the connector's service role.

### MCP tool contracts (Westland connector, internal-service side)

Wired into the unified `/westland/mcp` handler **with / after the MCP merge** (Phase 1, owned by the merge work). The spec defines the contract so the tools drop in cleanly:

| tool | input | behavior / output |
|---|---|---|
| `get_project` | `job_number` | returns the `wnd_projects` row as JSON, or `null` if absent |
| `upsert_project` | `job_number`, bindings… | create or update; stamps `created_by_email` on create, `updated_at` always; returns the row |
| `append_project_log` | `job_number`, `body`, `category?` | **first-class, directly-callable write** — resolves `project_id` from `job_number`, inserts a `wnd_project_log` row stamping `created_at` + `created_by_email`; returns the new entry. Designed so any skill / automation / cron can drop a log entry without read-modify-writing the project row. |
| `list_project_log` | `job_number`, `limit?` | returns recent entries (desc by `created_at`) |
| `list_projects` *(optional)* | — | minimal fields for central visibility / debugging |

`created_by_email` is OAuth-stamped on every write and is not client-settable.

### Skill-side seam (`scheduling` plugin)

A shared helper **`load_project(job_number)`** replaces `parse_project_context_html.load_project_context(schedules_root)`. It returns the binding fields under the **established `parse_project_context_html` key names** (`project_name`, `smartpm_url`, `smartpm_trends_url`, `smartpm_changelog_url`, `smartpm_project_name`, `procore_*`) so callers that read those keys are unchanged. It does **not** carry the fields that left the store — recipients/signer/graph_order now come from the prior email JSON or the report Q&A (see below), and `contractual_completion` from Procore — so the report/draft phases that used to read those from `ctx` are rewired accordingly. The helper:

1. calls `get_project(job_number)`;
2. on a hit → returns the bindings dict and writes a local read-only `project-settings.json` snapshot (for transparency/debugging — never the source);
3. on a miss → runs lazy migration (below).

`job_number` comes from the existing folder-resolution logic (it already validates the `W#### - …` parent).

**Callers updated:** `schedule-update` (report/draft phases), `write-weekly-schedule-email`, and the project-log append path.

**Behavior changes that follow from the cuts:**
- **Recipients / signer / graph_order sourcing moves.** Today week-1 seeds these from `project-context.html`. New behavior: source from the previous email JSON (carry-forward) when present, else gather conversationally during the report Q&A on the first email (`graph_order` → canonical default). The report/draft phases stop reading these from `ctx`.
- **`contractual_completion` from Procore.** The build step pulls it via a Procore MCP call (`list_project_dates` / `show_project`) instead of from the store. *(Open item: confirm which Procore date field maps to "contractual completion.")*
- **Project-log appends become MCP calls.** Where `schedule-update` previously parsed the HTML, appended a `{date, body}`, and re-generated, it now calls `append_project_log(job_number, body, category)`. Integration points to wire: EOT filed (`category='eot'`), scope change (`'scope_change'`), schedule published to Procore (`'schedule_published'`), plus free-form notes (`'note'`).

**`schedule-project-init` rewritten:** gathers fields conversationally → `upsert_project(source='init')`. It **stops generating `project-context.html`** but still drops the generic launchers into the Schedules root (they're unchanged and still needed). Triggers/description updated.

**Script fate:** `parse_project_context_html.py` is **kept** (lazy migration needs it). `generate_project_context_html.py` is **retired**, along with its generate-path tests; new tests cover `load_project`, the import→row mapping, and the lazy-migrate + retire behavior.

### Lazy migration + HTML retirement

On a DB miss, `load_project` looks for `project-context.html` in the Schedules root. If present:

1. parse it with the existing safe parser;
2. map bindings → `upsert_project(source='migrated')`;
3. each existing log entry → `append_project_log` (body + `created_at` from the entry's date where possible, `category='note'`);
4. **rename the file to `project-context-migrated.html`** so nothing reads — or accidentally edits — a dead artifact;
5. return the bindings dict.

Recipients / signer / graph_order in the old HTML are **discarded** — every mid-stream project already carries them in its latest email JSON. If no HTML is found, instruct the user to run `schedule-project-init`. No bulk sweep; the same import function is reusable later if one is ever wanted.

### Build sequencing — merge-first, Workflow-driven

Implementation runs as a **Workflow** (per request). Phasing:

- **Phase 0 — executable now (this repo + Supabase), independent of the merge.** Create both tables + RLS via Supabase `apply_migration`; build and unit-test the import/parse→row mapping and the `load_project` dict-shape adapter against a stub MCP. Land on `feat/project-context-supabase`. Nothing user-facing flips yet.
- **Phase 1 — gated on the MCP merge landing (`westland-mcps`, owned by the merge work).** Add `get_project` / `upsert_project` / `append_project_log` / `list_project_log` to the unified `/westland/mcp` internal handler; bump Worker version.
- **Phase 2 — skill cutover (this repo, after Phase 1).** Swap callers to `load_project`, rewrite `schedule-project-init`, wire lazy-migrate + HTML-retire, move the log-append path to the MCP tool, source `contractual_completion` from Procore, retire `generate_project_context_html.py` + tests, add new tests. Bump `scheduling` plugin + `marketplace.json` in lockstep; branch → PR → merge → `python build.py scheduling` → distribute.
- **Phase 3 — cleanup.** Remove dead code after a couple of real weekly updates run clean.

## Risks / open items

- **Hard connector/network dependency** for project reads — acceptable; the weekly update already hard-depends on the connector (cloud editor) + network (SmartPM/Procore). The lazy-parse + local `project-settings.json` snapshot cushion the edges.
- **`contractual_completion` Procore field mapping is unresolved** — must be nailed in the implementation plan before Phase 2.
- **Week-1 sourcing path** (recipients/signer/graph_order with no prior email JSON) must be exercised in tests.
- **`job_number ↔ spm_projects` is soft** — `spm_project_id` stays null when `project_number` isn't populated; `job_number` is the real key regardless.
- **Expansion is via real columns** — add typed columns when a field is actually needed; no jsonb catch-all unless the column count ever becomes genuinely unwieldy.
- **Naming** — `wnd_projects` chosen as the job-level anchor; revert to `wnd_project_settings` if a narrower scope is preferred.

## Out of scope

- Rich HTML / cloud-editor settings UI (explicitly conversational + MCP).
- Bulk migration sweep (lazy only).
- Repurposing the empty `wnd_schedule_updates` table (separate per-update grain; left as-is).
- The MCP merge itself (prerequisite, tracked separately in `wf-westland-mcp-merge.js`).
