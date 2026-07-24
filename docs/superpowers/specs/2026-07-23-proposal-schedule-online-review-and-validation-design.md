# Proposal Schedule — Online Review Link + Final XER Validation Gate

- **Date:** 2026-07-23
- **Status:** Design — awaiting user review before writing-plans
- **Repos:** `construction-skills` (skill + tooling) and `westland-mcps` (hosting + the review app). One feature, two PRs.
- **Scheduling plugin:** `10.1.2 → 10.2.0` (minor — new capability), marketplace bumped in lockstep.

## Summary

Two additions to the proposal-schedule creator:

1. **A visible final XER-validation gate.** Generation already refuses to write a malformed `.xer` (the 10.1.1/10.1.2 `xer_validate.py` guard runs inline in both `create_xer_from_template` and `apply_xer_changes`). This adds an explicit end-of-flow step that runs the full structural validator on the *finished* file and prints a clear pass/fail + issue list before hand-off — so import-readiness is confirmed and documented at the finish line, not just silently enforced upstream.

2. **An online, commentable review link — replacing the local preview.** Today the proposal preview is a self-contained local `schedule-review.html` whose feedback is exported via a "Download Feedback" button and emailed back. That local surface is **retired**. In its place: a hosted link (modeled on the weekly-schedule-update-email cloud editor) that is **the only review surface** — for solo iteration and distributed review alike. The skill uploads the schedule **data** (`schedule-activities.json`); a single deployed review app on the Worker renders it in the browser and lets internal reviewers enter their name once (cookie), comment on individual tasks (attributed), and optionally attach a suggested duration. Claude later pulls the comments via MCP, reconciles them drift-aware, and iterates.

## Why data-upload + server-rendered (the load-bearing decision)

An earlier draft had the skill render the page HTML locally and upload the bytes for the Worker to serve verbatim. That was rejected: a bad local render would be served wrong with no way for the server to catch or fix it, and a template bug would be baked into every published project. Instead:

- The skill uploads **data** (`schedule-activities.json`), which the Worker **validates on upload**.
- The **review app** (frappe-gantt + P6 grid + comment layer) is a single committed artifact in `westland-mcps`, rendered client-side from the fetched data.
- A render bug is fixed **once, by deploying the Worker** — every project and every past version is corrected immediately; nothing is re-published.
- There is exactly **one** review UI (server-side). The local preview is retired, so there is no second copy to drift (the concern the scheduling `CLAUDE.md` warns about).

## Goals

- A documented, visible import-readiness check on the final proposal `.xer`.
- A single distributable link per project that internal reviewers open with no login and comment on tasks, attributed by name.
- Comments + optional suggested-durations pinned to the schedule **version** they were made against; a **version dropdown** to switch between versions.
- Server-side validation of uploaded schedule data.
- A one-way pull of review comments back into Claude's iterate loop, reusing the existing drift-aware reconciliation.

## Non-goals

- **No real-time / live comment sync.** Your own comment appears instantly (optimistic client-side insert on a successful POST); others' comments appear on a normal page refresh. No WebSockets, no Durable Objects, no polling. (A cheap "N new comments — refresh" nudge is a possible later add; explicitly deferred.)
- **No shared destructive editing.** Reviewers comment and *suggest* durations; they never mutate the schedule. The scheduler reconciles suggestions during iterate.
- **No local preview.** `build_gantt_html.py`, `gantt-review.html`, and both buttons ("Copy for Claude", "Download Feedback") are retired. The online link is the only review surface. (Consequence: a live visual preview requires a publish + browser; there is no offline Gantt view. Accepted.)
- **No authenticated login for reviewers.** Bearer-of-URL + name cookie. Attribution is cooperative ("who do I ask about this note"), not access control. Internal Westland audience only.
- Not changing the weekly-schedule-update-email service's behavior. Shared code (HMAC) is refactored behavior-preserving; its tests must stay green.

## Background — current state (verified)

**construction-skills**
- Skill `scheduling:schedule-create-proposal-schedule` dispatches to `phases/01-draft.md`, `phases/02-iterate.md`, `phases/03-score.md`. Iteration is driven by `scheduling/tools/propsched.py` → `proposal_iterate.py`.
- Local preview (**to be retired**): `scheduling/tools/build_gantt_html.py` inlines frappe-gantt (`scheduling/lib/frappe-gantt/`), the logo, and the activities JSON into `scheduling/templates/gantt-review.html`, writing a self-contained `schedule-review.html` with a per-task note popup, in-memory `comments`/`edits`, a "Copy for Claude" button, and a "Download Feedback" button.
- Reviewer feedback ingest (**to be reused**): `scheduling/tools/feedback_ingest.py` (`ingest`/`list`/`show`) parks a feedback JSON and reports drift vs the current `schedule-activities.json`; it does not auto-apply. Reusable core: `_activities_index()` + `_detect_drift()`; expected activity shape is `westland-reviewer-feedback` (`task_snapshot.{name,duration_days}`, `duration_change.{from_days,to_days}`, `version_reviewed`).
- XER validation: `scheduling/skills/schedule-toolbox/lib/xer_validate.py` — `validate(doc)` → `import_ready` + issues (empty NOT-NULL columns / AVAA0-1866-2, bare datetimes, non-numeric IDs, dangling refs, circular logic, …). Standalone MCP tool `validate_xer_structure` (`scheduling/mcp-server/tools/xer_validate.py`). XER files are immutable (PreToolUse hook blocks edits).

**westland-mcps** (single Cloudflare Worker; Supabase used as data backend over PostgREST/Storage REST; no edge functions, no in-repo migrations)
- Template to model on: `src/services/westland-forms/weekly-schedule-update-email/` — Hono routes serving HTML via `c.html()`, an SPA that fetches data and renders client-side, autosave, a Refresh button. Data in Postgres (`wnd_email_drafts`) + Storage (`wnd-graph-blobs`), secrets `SUPABASE_MCPS_URL`/`SUPABASE_MCPS_SERVICE_ROLE_KEY` (MCP-data project `bnvmkkucpuorxafvojod`). Service-role bypasses RLS; tenancy enforced in-query. Schema published at `/schema` + `/schema.json` (contract-of-record).
- Auth: `src/services/westland-forms/shared/hmac.js` — `signEditorUrl`/`verifyEditorRequest`, HMAC-SHA256 over `` `${project}|${reportDate}|${exp}` `` with `EDITOR_HMAC_SECRET`, 7-day default, bearer-of-URL.
- Assets constraint: a Worker allows only **one** `[assets]` binding and it's already used by weekly-email. (Resolved below by bundling the review app into the Worker script, not via a second binding.)
- Tool registration: a tool exports `{ name, description, annotations, inputSchema, handler }`; add to the service `tools/index.js`; westland-forms tools compose into `/westland/mcp` via `src/services/westland/agent.js`; handlers read identity via `getEmail()`.
- Project registry: `wnd_projects`/`wnd_project_log` live in the **other** Supabase project (`anwdfilrfczluhudtbzw`), via `get_project`/`upsert_project`/`append_project_log`/`list_project_log`. No cross-project FK — relate by `job_number` string.
- Precedent for authoring render code once and shipping it to the Worker: `@westland/charts` is authored in construction-skills and vendored as a tarball. (Here we go simpler — the review app is committed directly in westland-mcps, since the local preview is retired and there is no second consumer.)
- Deploy: merge to `main` → GitHub Actions → `wrangler deploy`. Tests run locally (`node --test`); CI does not run them.

## Feature 1 — Final XER-validation gate (construction-skills only)

A new explicit step at the end of the proposal flow (final approval, before the Plan PDF / hand-off):

- Runs the existing structural validator on the finished `.xer` — via the `validate_xer_structure` MCP tool (preferred; already deployed).
- Prints a **clear pass/fail banner + itemized issues** (error/warn/info, with `xer_validate` category + row identity) and states import-readiness explicitly.
- **Read-only.** Never modifies the file; on failure it reports and directs back to iterate/regenerate (where the fix happens, since generation guards inline).
- Documented in `phases/03-score.md` (or a short new tail step) and surfaced as a required step in `SKILL.md`. No new wrapper if `validate_xer_structure` suffices; a local pass/fail formatter, if needed, extends existing tooling rather than wrapping it.

Deliberately lightweight — enforcement already exists; this makes it **visible and on the record**.

## Feature 2 — Online proposal review link (replaces the local preview)

### Architecture

A new sibling sub-service `src/services/westland-forms/proposal-schedule-review/` on the same Worker, same Supabase MCP-data project.

- **The review app** is committed in `westland-mcps` as a self-contained HTML-in-JS module (e.g. `app.html.js` exporting a template string) that bundles frappe-gantt + CSS + the P6 grid + the comment/version-dropdown layer. The Worker serves it inline via `c.html()`, injecting `{{SIG_QUERY}}`, `{{API_BASE}}`, `{{CURRENT_VERSION}}` at serve time. Bundling into the Worker script sidesteps the single-assets-binding constraint. **Checkpoint (not a blocker):** confirm the added bundle size (frappe-gantt ≈ 100–150 KB) stays within the Worker size limit; if tight, move the static app files into Supabase Storage and have the Worker fetch+cache them.
- **Per-version data** = the `schedule-activities.json` snapshot, stored in Storage and **validated on upload**. The page fetches it (`GET /snapshot`) plus comments (`GET /comments`) and the version list (`GET /versions`) and renders client-side.
- No CORS needed — page and API are same-origin on the Worker.

### Link + evergreen keying

- URL: `https://westland-mcps.westland.workers.dev/westland-forms/proposal-schedule-review/review/{job_number}?sig=…&exp=…`
- **Evergreen:** keyed on `job_number`, stable across versions; opens to the current version by default; `?version=vN` selects a specific version.
- Expiry **30 days** (internal); each publish refreshes `sig`/`exp`; an outstanding valid link keeps working and lands on the newest version.
- **HMAC refactor:** generalize `shared/hmac.js` to a parts-keyed `signUrl(env, { baseUrl, path, parts, expiresInSec })` / `verifyRequest(env, request, { parts })` where the signed payload is `parts.join('|') + '|' + exp`. Reimplement `signEditorUrl`/`verifyEditorRequest` as behavior-preserving wrappers (`parts = [project, reportDate]`) so weekly-email tests stay green. Review service uses `parts = [job_number]`. Default: reuse `EDITOR_HMAC_SECRET` (one secret; separate `REVIEW_HMAC_SECRET` only if independent rotation is wanted).

### Version semantics (publish = create / update-in-place / cut)

- First publish for a job → **v1**.
- Subsequent publishes default to **update-in-place** of the current version's snapshot (comments preserved) — this is the solo-iteration preview path: Claude re-publishes, the reviewer refreshes and sees the new schedule, no version spam.
- A deliberate **new-version cut** (`new_version: true`) freezes the current version (its comments stay pinned to it), creates vN+1 with the new snapshot and a **clean comment slate** — used after a review round, when Claude has addressed feedback.
- The **version dropdown** (from `GET /versions`) lets reviewers switch to any version and see that version's snapshot + comments. Comments are **version-scoped**.
- Note: updating a version in place after comments exist can drift those comments; this is why review rounds cut a new version. In-version drift is still detectable (comments carry name/duration snapshots) and surfaced at pull time.

### Reviewer identity (net-new cookie)

- First load with no cookie → name prompt. On submit set `wl_reviewer_name` + `wl_reviewer_id` (client UUID). No email, no login. Comment writes carry both; the name prefills on reopen.
- A reviewer may **edit/delete their own** comments (matched by `reviewer_id`); others' are read-only. The **resolved** toggle is open to any viewer (cooperative internal trust).
- Spoofable by design; acceptable for the internal, bearer-of-URL model.

### Resolved workflow

- Each comment has a `resolved` boolean, toggleable in the UI in **any** version view (typically the old-version view after Claude addressed it in a new version).
- New versions start clean; reviewers switch back via the dropdown to see/resolve older-version comments.
- `resolved` is a UI `PATCH`; no MCP resolve tool in v1 (Claude reads resolved status via the pull tool).

### The review UI

Adapted from the retired `gantt-review.html` (its design carries over — but as the single server-side app, not a local file):
- P6-style table + Gantt, rendered client-side from the fetched snapshot.
- Per-task note popup **POSTs to the comment API**; optional **suggested-duration** numeric field per task; existing comments shown inline per task with author + version badge + resolved checkbox; version dropdown.
- No "Copy for Claude", no "Download Feedback".
- Westland brand output — load the `westland-house-style` skill when building the app's visible copy/branding.

### Data model (MCP-data Supabase project `bnvmkkucpuorxafvojod`)

Storage bucket `wnd-proposal-review` — per-version schedule snapshot at `{job_number}/{version_label}.json`.

Postgres (RLS on, no public policy — service-role only; `wnd_` prefix; uuid PKs; `created_at` default now(); `updated_at` set in code):

```sql
create table public.wnd_proposal_reviews (
  id                uuid primary key default gen_random_uuid(),
  job_number        text not null unique,          -- relate to wnd_projects by string (cross-project)
  project_name      text,
  current_version   text not null,                 -- e.g. "v3"
  created_by_email  text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create table public.wnd_proposal_review_versions (
  id                 uuid primary key default gen_random_uuid(),
  job_number         text not null,
  version_label      text not null,                -- "v1","v2",...
  snapshot_path      text not null,                -- storage path of the activities JSON
  published_at       timestamptz not null default now(),
  published_by_email text,
  unique (job_number, version_label)
);

create table public.wnd_proposal_review_comments (
  id                      uuid primary key default gen_random_uuid(),
  job_number              text not null,
  version_label           text not null,           -- version the comment was made against
  task_code               text not null,           -- activity code
  task_name_snapshot      text,                     -- for drift detection at pull time
  orig_duration_snapshot  numeric,                  -- days, for drift detection
  reviewer_id             text not null,            -- cookie UUID
  reviewer_name           text not null,
  body                    text,
  suggested_duration_days numeric,                  -- nullable
  resolved                boolean not null default false,
  resolved_by             text,
  resolved_at             timestamptz,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);
create index wnd_prc_job_version_idx on public.wnd_proposal_review_comments (job_number, version_label, created_at);
```

Migration applied out-of-band to `bnvmkkucpuorxafvojod`, with a reference copy checked into the repo alongside the existing schema references.

### Routes (Hono, mounted under `/westland-forms/proposal-schedule-review`), all HMAC-gated (parts `[job_number]`)

- `GET /review/:job_number` — serve the committed app inline, placeholders injected; `?version=vN` sets the initial version.
- `GET /snapshot/:job_number/:version_label` — the activities JSON for a version.
- `GET /versions/:job_number` — `[{version_label, published_at, is_current}]`.
- `GET /comments/:job_number?version=vN` — comments for a version (default current).
- `POST /comments/:job_number` — create a comment.
- `PATCH /comments/:job_number/:id` — edit own comment (reviewer_id match) or toggle `resolved` (open).
- `DELETE /comments/:job_number/:id` — delete own comment (reviewer_id match).
- `GET /schema` + `GET /schema.json` — published contract (mirrors the weekly-email discipline; includes the accepted `schedule-activities.json` upload shape).

### MCP tools (composed into `/westland/mcp`)

- `generate_proposal_review_link` — input `{ job_number, project_name, activities_json, new_version?: bool, version_label? }`. **Validates `activities_json` shape** (reject on failure). If no review exists → create v1. If `new_version` → cut a new version (freeze current, clean slate). Else → update the current version's snapshot in place (comments preserved). Uploads the JSON to Storage, upserts `wnd_proposal_reviews`, inserts/updates `wnd_proposal_review_versions`, mints the signed evergreen URL. Returns `{ review_url, expires_at, version_label, mode: "created"|"updated"|"new_version" }`.
- `get_proposal_review_comments` — input `{ job_number, version_label? }`. Returns attributed comments (all versions by default) with resolved status. Drift vs the current local schedule is computed locally by the skill.
- `get_proposal_review_status` — input `{ job_number }`. Returns versions list, per-version comment counts, unresolved count, distinct reviewers.

Handlers stamp `created_by_email`/`published_by_email` from `getEmail()`.

## Skill + tooling changes (construction-skills)

- **Publish step** (`phases/01-draft.md` / `phases/02-iterate.md`): Claude calls `generate_proposal_review_link` with the current `schedule-activities.json` (no local render). Solo iteration re-publishes (update-in-place); after a review round Claude publishes with `new_version: true`. Hand the reviewer the returned link. Optionally `append_project_log` (category `schedule_published`).
- **Pull + iterate step** (`phases/02-iterate.md`): Claude calls `get_proposal_review_comments`, writes the result to disk (don't embed tool output as literals), then runs a new `feedback_ingest.py` verb (e.g. `pull --file online-comments.json`) that maps the online-comment rows onto the existing `westland-reviewer-feedback` activity shape (`task_snapshot.{name,duration_days}`, `duration_change.{from_days,to_days}` from `suggested_duration_days`, `version_reviewed` from `version_label`) so it can **reuse `_activities_index()` + `_detect_drift()` unchanged** to reconcile against the current `schedule-activities.json` and produce the same parked-file + drift report, grouped by reviewer/version. Claude applies non-drifted feedback in the iterate loop, then publishes the next version.
- **Retire the local preview:** remove `scheduling/tools/build_gantt_html.py`, `scheduling/templates/gantt-review.html`, and (after confirming no other consumer) `scheduling/lib/frappe-gantt/`; excise the "Copy for Claude" / "Download Feedback" machinery. Update `phases/01-draft.md`, `phases/02-iterate.md`, and `SKILL.md` to reference the online link instead of the local HTML. Retire or repurpose any `build_gantt_html`-specific tests.
- **Version label source:** tie `version_label` to `schedule-activities.json`'s `project.version` so comment version-stamps line up with drift detection.

## Two-PR split, release, deploy

- **PR A — `westland-mcps`:** new `proposal-schedule-review/` service (the committed review app, routes, DB helpers, snapshot validation, three tools, `/schema`), the HMAC generalization refactor, tool-index registration, `node --test` unit tests, migration reference file. Merge to `main` → Actions deploys. Apply the Supabase migration to `bnvmkkucpuorxafvojod` out-of-band as part of rollout.
- **PR B — `construction-skills`:** publish/pull phase edits, `feedback_ingest.py pull` verb, retirement of the local-preview files, final XER-validation gate step, `SKILL.md` updates, scheduling `10.1.2 → 10.2.0` + marketplace lockstep, `pytest` coverage. Follow the repo release convention (branch → bump both version fields → PR → merge → build from the main checkout → distribute zip).
- **Ordering:** deploy PR A first (tools + hosting must exist before the skill calls them), then PR B.

## Testing

- **westland-mcps (`node --test`):** generic HMAC sign/verify round-trip + backward-compat for the weekly-email wrappers; `activities_json` upload validation (accept good, reject malformed); publish mode logic (create v1 / update-in-place preserves comments / new_version freezes + clean slate); comment insert/list/patch/delete with reviewer_id ownership; version list + current-version bump; serve-app placeholder injection; tool handlers (happy path + missing-secret + not-found). No live-network tests.
- **construction-skills (`pytest`):** `feedback_ingest.py pull` mapping + reconciliation reusing `_detect_drift` (current version, N-behind, renamed/re-durationed/dropped, multi-reviewer grouping); confirm removing `build_gantt_html.py` breaks no other flow; final-gate reporter formats pass/fail from a `validate()` result. Existing `xer_validate` tests stay green.

## Security / privacy

- Bearer-of-URL: anyone with the (30-day, signed) link can read the schedule and comment. Internal audience only. Rotating the HMAC secret invalidates outstanding links.
- Reviewer identity is cooperative (name cookie), attributable but spoofable — acceptable for internal review.
- Proposal/bid schedule data is exposed on the page; audience kept internal. No secrets, no PII beyond reviewer names.
- Comment writes gated by the signed URL; ownership (edit/delete) enforced by `reviewer_id` server-side. Uploaded data is shape-validated before it is stored/served.

## Open questions (minor — defaults chosen, flag to change)

1. Keep the offline solo view? **Resolved: no — local preview retired, online link is the only surface.**
2. Reuse `EDITOR_HMAC_SECRET` for the review link, or a separate `REVIEW_HMAC_SECRET`? **Default: reuse.**
3. Render model? **Resolved: upload data, server-served committed app (validated on upload).**
4. Review app bundled into the Worker script vs. stored in Supabase Storage? **Default: bundled**, with a size checkpoint; fall back to Storage if the bundle limit is tight.
