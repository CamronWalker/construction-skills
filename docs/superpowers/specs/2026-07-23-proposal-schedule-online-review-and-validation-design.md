# Proposal Schedule — Online Review Link + Final XER Validation Gate

- **Date:** 2026-07-23
- **Status:** Design — awaiting user review before writing-plans
- **Repos:** `construction-skills` (skill + tooling) and `westland-mcps` (hosting). One feature, two PRs.
- **Scheduling plugin:** `10.1.2 → 10.2.0` (minor — new capability), marketplace bumped in lockstep.

## Summary

Two additions to the proposal-schedule creator:

1. **A visible final XER-validation gate.** Generation already refuses to write a malformed `.xer` (the 10.1.1/10.1.2 `xer_validate.py` guard runs inline in both `create_xer_from_template` and `apply_xer_changes`). This adds an explicit end-of-flow step that runs the full structural validator on the *finished* file and prints a clear pass/fail + issue list before hand-off — so import-readiness is confirmed and documented at the finish line, not just silently enforced upstream.

2. **An online, commentable review link.** Today the proposal preview is a self-contained local `schedule-review.html` whose feedback is exported via a "Download Feedback" button and emailed back. This turns it into a hosted link (modeled on the existing weekly-schedule-update-email cloud editor) that internal reviewers open, enter their name once (stored in a cookie), and comment on individual tasks — each comment attributed, optionally carrying a suggested duration. Claude later pulls the comments via MCP, reconciles them drift-aware, and iterates. The "Download Feedback" button is removed; comments now flow to the server directly.

## Goals

- A documented, visible import-readiness check on the final proposal `.xer`.
- A distributable link per project that internal reviewers can open with no login and comment on tasks, attributed by name.
- Comments and optional suggested-durations pinned to the schedule **version** they were made against; a **version dropdown** lets reviewers switch between versions.
- A one-way pull of review comments back into Claude's iterate loop, reusing the existing drift-aware reconciliation.

## Non-goals

- **No real-time / live comment sync.** Your own comment appears instantly (optimistic client-side insert on a successful POST); others' comments appear on a normal page refresh. No WebSockets, no Durable Objects, no polling. (A cheap "N new comments — refresh" nudge is a possible later add; explicitly deferred.)
- **No shared destructive editing.** Reviewers comment and *suggest* durations; they never mutate the schedule. The scheduler reconciles suggestions during iterate. (This is the key divergence from the weekly-email editor, which is a live last-write-wins editor.)
- **No authenticated login for reviewers.** Bearer-of-URL + name cookie. Attribution is cooperative ("who do I ask about this note"), not access control. Internal Westland audience only.
- Not touching the weekly-schedule-update-email service's behavior. Shared code (HMAC) is refactored behavior-preserving; its tests must stay green.

## Background — current state (verified)

**construction-skills**
- Skill `scheduling:schedule-create-proposal-schedule` dispatches to `phases/01-draft.md`, `phases/02-iterate.md`, `phases/03-score.md`. Iteration is driven by `scheduling/tools/propsched.py` → `proposal_iterate.py`.
- Local preview: `scheduling/tools/build_gantt_html.py` inlines frappe-gantt (vendored at `scheduling/lib/frappe-gantt/`), the Westland logo, and the activities JSON into `scheduling/templates/gantt-review.html`, writing a fully self-contained `schedule-review.html`. The template already has a per-task note popup, an in-memory `comments`/`edits` map, a **"Copy for Claude"** button, and a **"Download Feedback"** button (`buildReviewerFeedbackPayload`, schema `westland-reviewer-feedback`).
- Reviewer feedback ingest: `scheduling/tools/feedback_ingest.py` (verbs `ingest`/`list`/`show`) parks a downloaded feedback JSON and reports drift vs the current `schedule-activities.json` — it does **not** auto-apply. Core reusable pieces: `_activities_index()` and `_detect_drift()`.
- XER validation: `scheduling/skills/schedule-toolbox/lib/xer_validate.py` — `validate(doc)` → `import_ready` bool + issues; guards for empty NOT-NULL columns (AVAA0-1866-2), bare datetimes, non-numeric IDs, dangling refs, circular logic, etc. Wired into generation so neither entry point can emit a malformed file. Standalone MCP tool: `validate_xer_structure` (`scheduling/mcp-server/tools/xer_validate.py`).

**westland-mcps** (single Cloudflare Worker; Supabase used as data backend over PostgREST/Storage REST; no edge functions, no in-repo migrations)
- Template to model on: `src/services/westland-forms/weekly-schedule-update-email/`.
  - Hosting: Hono routes serving HTML via `c.html()`; SPA static assets from the one `[assets]` binding (`WEEKLY_EMAIL_ASSETS`) — **only one assets binding is allowed per Worker and it is already taken**.
  - Auth: `src/services/westland-forms/shared/hmac.js` — `signEditorUrl`/`verifyEditorRequest`, HMAC-SHA256 over `` `${project}|${reportDate}|${exp}` `` with `EDITOR_HMAC_SECRET`, default 7-day expiry, bearer-of-URL. URL path is hardcoded to the weekly-email route.
  - Data: `src/services/westland-forms/shared/supabase-client.js` — Postgres `wnd_email_drafts` + Storage bucket `wnd-graph-blobs`, via secrets `SUPABASE_MCPS_URL` / `SUPABASE_MCPS_SERVICE_ROLE_KEY` (MCP-data project `bnvmkkucpuorxafvojod`). Service-role bypasses RLS; tenancy enforced in-query.
  - Schema-is-contract discipline: `/schema` + `/schema.json` endpoints published; callers WebFetch them.
- Tool registration: a tool file exports `{ name, description, annotations, inputSchema, handler }`; add to the service's `tools/index.js`; the westland-forms tools are composed into `/westland/mcp` via `src/services/westland/agent.js`. Handlers read verified identity via `getEmail()` from the Procore-OAuth context.
- Project registry (relate by job number): `wnd_projects` / `wnd_project_log` live in the **other** Supabase project (`anwdfilrfczluhudtbzw`), reached via `get_project`/`upsert_project`/`append_project_log`/`list_project_log`. A cross-project FK is impossible — relate the review to the project by `job_number` string.
- Deploy: merge to `main` → GitHub Actions → `wrangler deploy`. Tests run locally (`node --test`); CI does not run them.

## Feature 1 — Final XER-validation gate (construction-skills only)

A new explicit step at the end of the proposal flow (final approval, before the Plan PDF / hand-off):

- Runs the existing structural validator on the finished `.xer` — via the `validate_xer_structure` MCP tool (preferred; already deployed) or `xer_validate.validate()` locally.
- Prints a **clear pass/fail banner + itemized issues** (error/warn/info, with the `xer_validate` category + row identity), and states import-readiness explicitly.
- **Read-only.** XER files are immutable (PreToolUse hook blocks edits). The gate never modifies the file; on failure it reports and stops, directing back to iterate/regenerate (which is where the actual fix happens, since generation guards inline).
- Documented in the phase files (`phases/03-score.md` or a short new tail step) and surfaced as a required step in `SKILL.md`. No new wrapper script if `validate_xer_structure` suffices; if a local formatter is needed, it extends existing tooling (drive/extend, don't wrap).

This is deliberately lightweight — the enforcement already exists; this makes it **visible and on-the-record** at the finish line.

## Feature 2 — Online proposal review link

### Architecture overview

A new sibling sub-service `src/services/westland-forms/proposal-schedule-review/` on the same Worker, same Supabase MCP-data project. The page is the *rendered* proposal review HTML (built by the skill, reusing the vendored frappe-gantt assets that live in construction-skills) **stored per version in Supabase Storage** and served inline by the Worker. This sidesteps the single-assets-binding constraint and keeps frappe-gantt from being duplicated into westland-mcps — the Worker is a dumb store/serve for the schedule view, plus a small comment API. A thin dynamic comment layer (JS baked into the template) fetches comments + the version list from same-origin API routes; no CORS needed.

Separation of concerns:
- **Static per version:** the schedule table + Gantt (rendered HTML, stored in Storage at `{job_number}/{version_label}.html`).
- **Dynamic:** comments + version list (fetched client-side from the comment API, rendered as per-task chips/badges).
- **Injected at serve time by the Worker:** `{{SIG_QUERY}}`, `{{API_BASE}}`, `{{CURRENT_VERSION}}` — so the evergreen link's refreshed signature is always current and never baked stale into stored bytes.

### Link + evergreen keying

- URL: `https://westland-mcps.westland.workers.dev/westland-forms/proposal-schedule-review/review/{job_number}?sig=…&exp=…`
- **Evergreen:** the path is keyed on `job_number` and is stable across versions. Opening it shows the **current (latest)** version by default. `?version=vN` serves a specific version.
- Expiry **30 days** (internal, longer-lived than the email's 7). Each publish refreshes `sig`/`exp`; an outstanding still-valid link keeps working and lands on the newest version.
- **HMAC refactor:** generalize `shared/hmac.js` to a parts-keyed `signUrl(env, { baseUrl, path, parts, expiresInSec })` / `verifyRequest(env, request, { parts })` where the signed payload is `parts.join('|') + '|' + exp`. Reimplement `signEditorUrl`/`verifyEditorRequest` as behavior-preserving wrappers (`parts = [project, reportDate]`) so weekly-email tests stay green. Review service uses `parts = [job_number]`.

### Versioning + dropdown semantics

- Every publish creates a **retained** version (`v1`, `v2`, …). All versions' rendered HTML persist in Storage.
- A **version dropdown** on the page (populated from `GET /versions`) lets reviewers switch to any version; switching navigates to `?version=vN`, serving that version's stored HTML, and the comment layer loads that version's comments.
- Comments are **version-scoped** — pinned to the version they were written against. A newly published version starts with a **clean** comment slate. Reviewers refresh the same link to land on the newest version; their earlier comments remain visible under the old version in the dropdown.

### Reviewer identity (net-new cookie)

- First load with no cookie → a name prompt ("Enter your name to review"). On submit, set cookies `wl_reviewer_name` and `wl_reviewer_id` (a client-generated UUID). No email, no login.
- Comment writes carry `reviewer_id` + `reviewer_name`. On reopen the name prefills.
- A reviewer may **edit/delete their own** comments (matched by `reviewer_id`); others' comments are read-only. The **resolved** toggle is open to any viewer (cooperative internal trust) — see below.
- This is spoofable by design and acceptable for the internal, bearer-of-URL trust model.

### Resolved workflow

- Each comment has a `resolved` boolean, toggleable in the UI in **any** version view (typically the old-version view after Claude has addressed it in a new version).
- Publishing a new version does not carry comments forward — the new version is clean — but reviewers can switch back via the dropdown to see/resolve older-version comments.
- `resolved` is primarily a UI action (a `PATCH` on the comment). No MCP resolve tool in v1 (Claude reads resolved status via the pull tool; can be added later if wanted).

### The page (adapted from `gantt-review.html`)

One template, mode-switched at render, to avoid divergence (per the scheduling `CLAUDE.md` "don't let two copies drift" rule):
- `window.WL_REVIEW_MODE = 'local' | 'online'`.
- **local** (unchanged solo loop): keeps **"Copy for Claude"**; **"Download Feedback" is removed** in both modes.
- **online:** per-task note popup **POSTs to the comment API** (not the in-memory map); adds an optional **suggested-duration** numeric field per task; renders existing comments inline per task with author + version badge + resolved checkbox; shows the version dropdown. Reads `{{API_BASE}}` + `{{SIG_QUERY}}` + `{{CURRENT_VERSION}}` injected by the Worker.
- `build_gantt_html.py` gains an `--online` flag: emits the template in online mode with `{{…}}` placeholders left intact and the selected version's activities JSON inlined. Local default behavior is unchanged.
- Westland brand output — load the `westland-house-style` skill when building the page's visible copy/branding.

### Data model (MCP-data Supabase project `bnvmkkucpuorxafvojod`)

Storage bucket `wnd-proposal-review` — per-version rendered page HTML at `{job_number}/{version_label}.html`.

Postgres (RLS enabled, no public policy — service-role only; `wnd_` prefix; uuid PKs; `created_at timestamptz default now()`; `updated_at` set in code):

```sql
create table public.wnd_proposal_reviews (
  id                uuid primary key default gen_random_uuid(),
  job_number        text not null unique,          -- relate to wnd_projects by string (cross-project)
  project_name      text,
  current_version   text not null,                 -- e.g. "v3"
  created_by_email  text,                          -- Procore identity of the publisher
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create table public.wnd_proposal_review_versions (
  id                uuid primary key default gen_random_uuid(),
  job_number        text not null,
  version_label     text not null,                 -- "v1","v2",...
  html_path         text not null,                 -- storage path of the rendered page
  published_at      timestamptz not null default now(),
  published_by_email text,
  unique (job_number, version_label)
);

create table public.wnd_proposal_review_comments (
  id                     uuid primary key default gen_random_uuid(),
  job_number             text not null,
  version_label          text not null,            -- version the comment was made against
  task_code              text not null,            -- activity code (stable-ish key)
  task_name_snapshot     text,                      -- for drift detection at pull time
  orig_duration_snapshot numeric,                   -- days, for drift detection
  reviewer_id            text not null,             -- cookie UUID
  reviewer_name          text not null,
  body                   text,
  suggested_duration_days numeric,                  -- nullable
  resolved               boolean not null default false,
  resolved_by            text,
  resolved_at            timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index wnd_prc_job_version_idx on public.wnd_proposal_review_comments (job_number, version_label, created_at);
```

Migration applied out-of-band to `bnvmkkucpuorxafvojod` (Supabase `apply_migration`/dashboard), with a reference copy checked into the repo alongside the existing schema references. New secret if needed: reuse `EDITOR_HMAC_SECRET` (single secret for both signed-URL surfaces) unless a separate `REVIEW_HMAC_SECRET` is preferred for independent rotation — default: reuse.

### Routes (Hono, mounted under `/westland-forms/proposal-schedule-review`)

All HMAC-gated (parts `[job_number]`) except none-public here (no separate SPA-asset routes — page is stored HTML):
- `GET /review/:job_number` — serve current version's stored HTML with placeholders injected. `?version=vN` → that version.
- `GET /versions/:job_number` — `[{version_label, published_at, is_current}]` for the dropdown.
- `GET /comments/:job_number?version=vN` — comments for a version (default current).
- `POST /comments/:job_number` — create a comment (`{version_label, task_code, task_name_snapshot, orig_duration_snapshot, reviewer_id, reviewer_name, body, suggested_duration_days}`).
- `PATCH /comments/:job_number/:id` — edit own comment (reviewer_id must match) or toggle `resolved` (open).
- `DELETE /comments/:job_number/:id` — delete own comment (reviewer_id must match).
- `GET /schema` + `GET /schema.json` — published contract (mirror the weekly-email discipline).

### MCP tools (composed into `/westland/mcp` via westland-forms tools index)

- `generate_proposal_review_link` — input `{ job_number, project_name, version_label, page_html }` (the skill uploads the rendered online-mode HTML). Uploads to Storage `{job_number}/{version_label}.html`, upserts `wnd_proposal_reviews` (sets `current_version`), inserts `wnd_proposal_review_versions`, mints the signed evergreen URL. Returns `{ review_url, expires_at, version_label }`. Idempotent per `(job_number, version_label)`.
- `get_proposal_review_comments` — input `{ job_number, version_label? }`. Returns attributed comments (all versions by default) with resolved status. Drift vs the current local schedule is computed **locally** by the skill (see below), not here.
- `get_proposal_review_status` — input `{ job_number }`. Returns versions list, per-version comment counts, unresolved count, distinct reviewers.

Handlers stamp `created_by_email`/`published_by_email` from `getEmail()`.

## Skill + tooling changes (construction-skills)

- **Publish step** (`phases/01-draft.md` / `phases/02-iterate.md`): after a version is built, Claude renders the online page (`build_gantt_html.py --online`), calls `generate_proposal_review_link` with that HTML + `version_label`, and hands the reviewer the returned link. Optionally append a `wnd_project_log` entry (category `schedule_published`) via `append_project_log`.
- **Pull + iterate step** (`phases/02-iterate.md`, replacing the download-JSON path): Claude calls `get_proposal_review_comments`, writes the result to disk (per CLAUDE.md — dump tool output, don't embed as literals), then runs a new `feedback_ingest.py` verb (e.g. `pull --file online-comments.json`) that maps the online-comment rows onto the existing `westland-reviewer-feedback` activity shape (`task_snapshot.{name,duration_days}`, `duration_change.{from_days,to_days}` from `suggested_duration_days`, `version_reviewed` from `version_label`) so it can **reuse `_activities_index()` + `_detect_drift()` unchanged** to reconcile against the current `schedule-activities.json` and produce the same parked-file + drift report, grouped by reviewer/version. Claude then applies non-drifted suggestions/comments in the normal iterate loop and publishes the next version.
- **Remove "Download Feedback"** from `gantt-review.html` (both modes). Keep "Copy for Claude" (local offline fallback) unless the user later says otherwise.
- **Version label source:** tie `version_label` to the proposal iteration version already tracked in `schedule-activities.json` (`project.version`) so comment version-stamps line up with drift detection.

## Two-PR split, release, deploy

- **PR A — `westland-mcps`:** new `proposal-schedule-review/` service (routes, template-serving, DB helpers, three tools, `/schema`), the HMAC generalization refactor, tool-index registration, `node --test` unit tests, migration reference file. Merge to `main` → Actions deploys. Apply the Supabase migration to `bnvmkkucpuorxafvojod` (out-of-band) as part of rollout.
- **PR B — `construction-skills`:** `build_gantt_html.py --online`, template mode-switch + button removal, `feedback_ingest.py pull` verb, publish/pull phase edits, final XER-validation gate step, `SKILL.md` updates, scheduling `10.1.2 → 10.2.0` + marketplace lockstep, `pytest` coverage. Follow the repo release convention (branch → bump both version fields → PR → merge → build from main checkout → distribute zip).
- **Ordering:** deploy PR A first (the tools + hosting must exist before the skill calls them), then PR B. Mirrors the prior connector-before-skills ordering.

## Testing

- **westland-mcps (`node --test`):** HMAC generic sign/verify round-trip + backward-compat for the weekly-email wrappers; comment insert/list/patch/delete with reviewer_id ownership enforcement; version upsert + current-version bump; tool handlers (happy path + missing-secret + not-found). No live-network tests (test-on-deploy model).
- **construction-skills (`pytest`):** `feedback_ingest.py pull` reconciliation reusing `_detect_drift` (current version, N-behind, renamed/re-durationed/dropped, multi-reviewer grouping); `build_gantt_html.py --online` emits placeholders + online-mode flag and leaves local mode unchanged; final-gate reporter formats pass/fail from a `validate()` result. Existing `xer_validate` + `build_gantt_html` tests stay green.

## Security / privacy

- Bearer-of-URL: anyone with the (30-day, signed) link can read the schedule and comment. Internal audience only. Rotating `EDITOR_HMAC_SECRET` invalidates all outstanding links.
- Reviewer identity is cooperative (name cookie), not authenticated; comments are attributable but spoofable — acceptable for internal review.
- Proposal/bid schedule data is exposed on the page; keep the audience internal (the chosen constraint). No secrets, no PII beyond reviewer names.
- Comment writes are gated by the signed URL; ownership (edit/delete) enforced by `reviewer_id` match server-side.

## Open questions (minor — defaults chosen, flag to change)

1. Keep "Copy for Claude" in the online page, or make the link the sole path? **Default: keep it.**
2. Reuse `EDITOR_HMAC_SECRET` for the review link, or a separate `REVIEW_HMAC_SECRET`? **Default: reuse** (one secret; simpler). Separate only if independent rotation is wanted.
3. Store rendered HTML per version (chosen — avoids frappe-gantt duplication) vs. store activities JSON per version + a shell renderer in westland-mcps. **Default: rendered HTML per version.**
