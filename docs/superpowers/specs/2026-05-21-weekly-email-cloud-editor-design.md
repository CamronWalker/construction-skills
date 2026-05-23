# Weekly email — cloud-hosted draft editor

**Date:** 2026-05-21
**Branches:**
- `interesting-noyce-d0f3e2` → `feat/weekly-email-cloud-editor-integration` (construction-skills)
- new worktree to be spun up → `feat/weekly-email-service` (westland-mcps)
**Plugin scope:** `scheduling` (construction-skills side — new MCP tool stubs, new `phases/draft.md`, `.eml` builder modifications)
**Cross-repo scope:** `westland-mcps` — new MCP service exposing 3 weekly-email tools + cloud function HTTP routes + browser editor SPA, all in the existing Cloudflare Worker
**Builds on:** [2026-05-22 HTML+SVG chart migration — JavaScript port](2026-05-22-html-svg-chart-migration-javascript-design.md) (on `claude/blissful-tharp-ad03c2`). That spec ships `@westland/charts` — a JS+JSDoc package of HTML+SVG renderers consumable from both Node and Cloudflare Workers. This spec wraps a draft-editing UX around them.

## Motivation

The weekly-schedule-update skill leans on Claude to orchestrate a lot — and the brittle parts aren't the SmartPM calls (those work reliably via the existing MCP). They're the *editing surface*: the `*-email-preview.html` artifact is managed by parse/generate Python scripts because direct Read/Write on it has corrupted the embedded base64 logo before (W1177, 2026-05-07). An advisory hook steers Claude back, but the underlying problem is using a templated HTML file as a working draft when what we want is a real editor.

This spec replaces that editing surface with a browser-based draft editor backed by a new service in the existing `westland-mcps` Cloudflare Worker:

- The Worker imports the JS chart renderer package (from construction-skills, consumed as an npm dep), fetches SmartPM data via the existing smartpm MCP tools, renders graphs cloud-side, and assembles a working JSON.
- The Worker also serves the editor SPA, accepts autosave POSTs, and returns final state on demand.
- The PM edits the email in a browser (autosave, no Save button, no Download button); graphs render inline with full SmartPM CSS parity; the draft survives across days for the Friday→Monday case; an in-editor `↻ Refresh graphs` button re-pulls SmartPM when an XER finishes processing.
- Claude's job shrinks to: synthesize seed → call one MCP tool → wait → call one MCP tool → run the existing `.eml` builder.

The big wins are (1) deleting the templated-HTML editing flow, (2) giving the PM real autosave + cross-session draft persistence + in-editor graph refresh, and (3) one stacked PNG in the `.eml` instead of N per-chart attachments.

## Goals

1. **Three MCP tools** added to westland-mcps as a new service (`/weekly-email/mcp`): `generate_weekly_email_draft`, `get_weekly_email_status`, `finalize_weekly_email`. That's the entire agent surface.
2. **Cloud function HTTP routes** added to the same Cloudflare Worker, namespaced under `/weekly-email/...` — Hono routes (multi-runtime; portable if we ever leave Cloudflare).
3. **Cloud-side rendering** — the Worker imports `@westland/charts` (the JS package shipping from the renderer agent's branch), fetches SmartPM data, calls `RENDERERS[slug](payload)` for each chart, stores the rendered HTML+SVG chunks in Supabase Storage. No local pre-render before the MCP call.
4. **Browser editor** served as static assets by the same Worker. Editorial fields editable (subject, body, recipients, narrative); HTML+SVG chart blocks displayed as static preview. Autosave with localStorage write buffer, 500ms debounce, blue-spinner → green-check → red-X inline indicator per field. No Save button. No Download button. In-editor `↻ Refresh graphs` button calls the Worker to re-pull SmartPM + re-render.
5. **Graceful handling of "SmartPM still processing"** — the cloud function checks `smartpm_get_project_import_status` first; if processing, every chart slot gets a placeholder card via `renderPlaceholder(slug)` from the chart package (same dimensions, "Data not yet available", clock icon). PM can start editing immediately. The editor header shows `Graphs: X/Y ready` next to the Refresh button.
6. **Hybrid auth** — Procore-OAuth identity-federation (existing westland-mcps pattern) for MCP tool calls; HMAC signed URLs for browser routes (signed by the Worker, no OAuth required for the PM to open an editor link).
7. **Local finalize** — `finalize_weekly_email` GETs the merged working JSON from the cloud, writes `{dated_folder}/email-draft.json`. The existing `.eml` builder (modified to consume `email-draft.json`) runs Node `html_to_png.js` on the concatenated chart HTML to produce one stacked PNG, embeds it inline, builds the `.eml`, creates the Outlook draft via existing COM code.
8. **Portability hedge** — all Worker code written in Hono with Web Crypto API + Supabase JS client + no Cloudflare-specific globals (no KV, no Durable Objects, no R2). Static editor SPA served via `serveStatic` middleware. If we ever leave Cloudflare, the cloud function port is ~1-2 days of host config, not a rewrite.

## Non-goals (out of scope this branch)

- Rewriting the carry-forward / "read last week's email" logic. Claude still reads last week's `email-draft.json` + `.eml` locally and synthesizes the seed.
- The chart renderer package itself (that's the renderer agent's spec).
- Replacing `generate_email_eml.py` (`.eml` assembly) or the Outlook COM code, beyond switching the input contract to `email-draft.json` + emitting one stacked PNG.
- Procore upload step — unchanged, runs after `.eml` per existing `phases/procore.md`.
- User accounts, OAuth, RBAC, multi-tenancy on the browser side. HMAC signed URLs cover access; the only "users" are Westland PMs, each gets a URL per project per week.
- Storing PMs' editorial drafts beyond 30 days. Cleanup cron deletes anything older. The dated project folder on the share is the archive.
- Conflict resolution / collaborative editing. One scheduler per project; last write wins on autosave.
- Building anything on Cloudflare KV / D1 / R2. Supabase already hosts `wnd_bug_reports` via the existing `westland-internal` service; this spec uses Supabase for a new `wnd_email_drafts` table + `wnd-graph-blobs` bucket (matching the `wnd_` table-name prefix Westland uses for its internal data). The westland-mcps slice spec ([2026-05-22-weekly-email-service-design.md](https://github.com/CamronWalker/westland-mcps/blob/feat/weekly-email-service/docs/superpowers/specs/2026-05-22-weekly-email-service-design.md)) settles on a **new dedicated Supabase project** for MCP data (suggested name `westland-mcps`) separate from the existing Power BI project `anwdfilrfczluhudtbzw` — gets MCP-write service-role keys out of reach of the BI dataset and decouples free-tier quotas. `wnd_bug_reports` migration to the new project is flagged as future cleanup, out of scope.

## Repo split + agent ownership

Three implementation streams, two repos. Each agent reads this single design doc and writes their own implementation plan for their slice.

| Stream | Repo | Branch / worktree | Agent | Scope |
|---|---|---|---|---|
| Chart renderer migration | construction-skills | `claude/blissful-tharp-ad03c2` | Spec + 12-task plan shipped (2026-05-22); awaiting execution | The `@westland/charts` JS+JSDoc package. Reimplements Python renderers in JS, ships `RENDERERS` registry + `renderPlaceholder` + `CHART_META`. Independent of this spec architecturally. |
| westland-mcps weekly-email service | westland-mcps | New worktree, e.g. `feat/weekly-email-service` | Spun up after this spec is approved | Adds new MCP service (3 tools) + cloud function HTTP routes (Hono) + browser editor SPA + HMAC signing + cron cleanup + Supabase schema in the existing project. Consumes `@westland/charts` as an npm dep. |
| construction-skills integration | construction-skills | This branch — `interesting-noyce-d0f3e2` → `feat/weekly-email-cloud-editor-integration` | This session | Modifies `phases/draft.md` to drive the new flow; modifies `generate_email_eml.py` to consume `email-draft.json` + emit one stacked PNG; updates the html-discipline hook to drop the now-vestigial `*-email-preview.html` matcher; bumps plugin manifest + marketplace entry. Does NOT touch the renderer package or the Worker. |

**Sequencing:**
1. Chart renderer agent ships their commit 1 (package skeleton + types + empty registry + JSDoc shapes). The westland-mcps agent then has a stable API to code against.
2. westland-mcps agent and construction-skills integration agent work in parallel — both consume the design from this spec; their work doesn't depend on each other landing, but both depend on the renderer agent's API surface.
3. End-to-end test happens once all three land. Build + distribute via the construction-skills release convention (build from main working tree, not a worktree).

**Cross-repo coordination points:**
- Chart package consumption mechanism (which the renderer agent's spec calls out as their open question). Recommended: **option B** — publish `@westland/charts` to a private npm registry (GitHub Packages works; free for private under modest usage). One-time setup: `npm publish` step in construction-skills' release flow + `.npmrc` in westland-mcps. Option A (gitpkg shim) is ruled out because construction-skills is a private repo. Option C (git submodule) is an acceptable fallback.
- HMAC secret rotation: stored as a Worker secret in westland-mcps; rotation invalidates all outstanding URLs. Documented in westland-mcps' WAKE-UP.md as part of this work.

## Architecture

```
┌─ Claude (local, construction-skills plugin) ────────────────────┐
│                                                                  │
│  read last-week email-draft.json + .eml                          │
│  read this-week + last-week XER (XER parser, existing)           │
│  read this-week meeting transcript                               │
│  synthesize seed JSON (editorial only — narrative + recipients)  │
│                              │                                   │
│         mcp.generate_weekly_email_draft(project, report_date,    │
│                                          seed_json)              │
│                              ▼                                   │
└──────────────────────────────┼───────────────────────────────────┘
                               │ POST /weekly-email/mcp tool call
                               │ Procore-OAuth bearer (identity-federation)
                               ▼
┌─ Cloudflare Worker (westland-mcps, new /weekly-email service) ──┐
│                                                                  │
│  MCP tool: generate_weekly_email_draft                           │
│    1. write seed to wnd_email_drafts (editorial layer)           │
│    2. check smartpm_get_project_import_status                    │
│    3. if processing → renderPlaceholder(slug) for each slug      │
│       else → fetch SmartPM payload + RENDERERS[slug](payload)    │
│    4. write graph_data + graph_html as JSON blob to              │
│       Supabase Storage (wnd-graph-blobs bucket)                      │
│    5. mint HMAC signed URL with 7-day expiry                     │
│    6. return URL + readiness counts                              │
│                                                                  │
│  HTTP routes (Hono, namespaced /weekly-email/...):               │
│    GET    /editor/{p}/{d}        serve editor SPA shell          │
│    GET    /draft/{p}/{d}/working return merged working JSON      │
│    PUT    /draft/{p}/{d}/editorial autosave editorial layer      │
│    POST   /draft/{p}/{d}/refresh-graphs re-pull SmartPM + render │
│    GET    /draft/{p}/{d}/final   return merged working JSON      │
│    GET    /status/{p}/{d}        status + readiness counts       │
│    POST   /cleanup               internal — cron-triggered       │
│                                                                  │
│  Auth: MCP tool calls verify Procore-OAuth bearer (existing      │
│         westland-mcps gate); HTTP routes verify HMAC signed URL. │
└──────────────────────────────┼──────────────────────────────────┘
                               │ Worker → Supabase (existing pattern
                               │ from westland-internal service)
                               ▼
┌─ Supabase (existing project anwdfilrfczluhudtbzw) ──────────────┐
│  Postgres: wnd_email_drafts (editorial + metadata, ~2-5 KB/row)  │
│  Storage:  wnd-graph-blobs bucket (graph_data + graph_html JSON,     │
│            ~50-200 KB per draft)                                 │
└─────────────────────────────────────────────────────────────────┘

                               │ MCP returns URL to Claude
                               │ Claude tells PM to open it
                               ▼
                       PM clicks URL → browser editor
                              │
                              │ GET /editor + GET /working (signed)
                              │ PUT /editorial (autosave, 500ms debounce, signed)
                              │ POST /refresh-graphs on button click (signed)
                              ▼
                       PM finishes, tells Claude "done"
                              │
                              ▼
┌─ Claude (local) ────────────────────────────────────────────────┐
│  mcp.finalize_weekly_email(project, report_date)                 │
│         │ Worker GETs merged JSON from Supabase                  │
│         │ returns it via MCP tool response                       │
│         │ Claude writes to {dated_folder}/email-draft.json       │
│         ▼                                                        │
│  run existing .eml builder (modified input contract):            │
│    - read email-draft.json                                       │
│    - concat all chart HTML chunks (canonical order)              │
│    - node html_to_png.js → one stacked PNG                       │
│    - assemble .eml: editorial HTML + inline stacked PNG          │
│    - Outlook COM → create Drafts item                            │
└─────────────────────────────────────────────────────────────────┘
```

## Module-by-module

### MCP tools (westland-mcps, new `/weekly-email/mcp` service)

Implemented as a new service alongside `/smartpm/mcp`, `/buildr/mcp`, etc. — same Procore-OAuth identity-federation pattern as `westland-internal`. `ctx.props` delivers `{ email, procoreUserId }`; tools enforce that the PM only operates on their own projects' drafts (server-side check against `editorial.from === ctx.email` or similar, mirroring the bug-reports pattern).

```
generate_weekly_email_draft(project, report_date, seed_json) -> {
  editor_url, expires_at,
  graphs_ready_count, graphs_total,
  smartpm_import_status: 'processing' | 'ready' | 'unknown'
}

  Steps (all server-side in Worker):
    1. Upsert seed_json into wnd_email_drafts (editorial layer + metadata).
       If a draft already exists for (project, report_date), editorial layer
       is preserved — only graphs refresh on re-run.
    2. Resolve scenario_id via smartpm_list_scenarios (cached in
       project-context.html context if Claude provides it; resolved here
       otherwise).
    3. Call smartpm_get_project_import_status.
    4. For each slug in seed.editorial.graph_order:
         if status == 'processing':
             graph_html[slug] = { status: 'processing',
                                   ...renderPlaceholder(slug) }
             graph_data[slug] = null
         else:
             try:
                 payload = call_smartpm_for_slug(slug)
                 { html, svgInner } = RENDERERS[slug](payload)
                 graph_html[slug] = { status: 'ready', html, svgInner }
                 graph_data[slug] = payload
             except RenderError as e:
                 // Per renderer agent's error-handling contract:
                 // programming-bug-class throws → error placeholder.
                 graph_html[slug] = {
                   status: 'error',
                   ...renderPlaceholder(slug, {
                     message: 'Render failed',
                     icon: 'warn'
                   })
                 }
                 graph_data[slug] = null
                 // Log the error server-side for debugging.
    5. Write graph_data + graph_html as JSON blob to wnd-graph-blobs bucket
       at path {project}/{report_date}.json.
    6. Mint HMAC signed URL.
    7. Return URL + counts.

get_weekly_email_status(project, report_date) -> {
  status, last_edited_at, last_refreshed_at,
  graphs_ready_count, graphs_total
}
  - Reads wnd_email_drafts row metadata. Used by Claude before finalize to verify
    the PM is actually done.

finalize_weekly_email(project, report_date) -> {
  working_json, schema_version, graphs_ready_count
}
  - Worker reads editorial from Postgres + graph blob from Storage,
    merges, returns the working JSON.
  - Claude writes it to {dated_folder}/email-draft.json client-side.
  - DOES NOT build the .eml — that's the next phase (phases/email.md).
  - If any graphs are still placeholders, the response includes
    graphs_ready_count < graphs_total so Claude can warn before assembling.
```

URLs computed by the Worker: `https://westland-mcps.westland.workers.dev/weekly-email/editor/{project}/{report_date}?sig=<hmac>&exp=<unix>`. HMAC secret is a Worker secret (`EDITOR_HMAC_SECRET`); never crosses the wire.

### Cloud function HTTP routes (westland-mcps, Hono)

Same Worker, separate route group under `/weekly-email/`. All routes verify HMAC signed URL (`sig` + `exp` query params) except `/cleanup` which is gated by Cloudflare Cron Trigger.

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| `GET` | `/weekly-email/editor/{p}/{d}` | Serve editor SPA shell + JS bundle (Worker static assets). | HMAC |
| `GET` | `/weekly-email/draft/{p}/{d}/working` | Return merged working JSON. Editor calls on load. | HMAC |
| `PUT` | `/weekly-email/draft/{p}/{d}/editorial` | Autosave editorial layer (body: editorial object). | HMAC |
| `POST` | `/weekly-email/draft/{p}/{d}/refresh-graphs` | Re-pull SmartPM + re-render graphs. Editor calls on Refresh button click. Re-checks import status; if still processing, all slugs stay as placeholders. Response body: `{ graph_html: {slug → {status, html, svgInner}}, graphs_ready_count, graphs_total, last_refreshed_at, smartpm_import_status }` — browser uses this to swap chart cards in place without a page reload. | HMAC |
| `GET` | `/weekly-email/draft/{p}/{d}/final` | Return merged working JSON. (Same as `/working` today — separate route reserved for "freeze on finalize" semantics if we add them later.) | HMAC |
| `GET` | `/weekly-email/status/{p}/{d}` | Return status + readiness counts. Polled by `get_weekly_email_status`. | HMAC |
| `POST` | `/weekly-email/cleanup` | Delete drafts older than 30 days + matching graph blobs. | Cron Trigger detection via `request.cf?.cronTrigger` for scheduled; manual invocation requires the `X-Cleanup-Trigger` header carrying a Worker-secret token. Never HMAC-signed (not a PM-facing surface). |

Hono middleware order: route match → HMAC verify → Supabase client → handler. Errors return JSON `{ error, status }`; static assets returned via `serveStatic`.

**SmartPM-call contract.** The Worker only calls SmartPM on two paths: the initial `generate_weekly_email_draft` MCP tool (creating the draft) and `POST /refresh-graphs` (explicit Refresh button click). Every other route — `GET /editor`, `GET /working`, `GET /final`, `GET /status`, `PUT /editorial` — reads from Supabase only. Plain page reloads (tab close + reopen, F5, browser restart, stale cache) never trigger SmartPM. This is a hard invariant: it keeps editing fast, SmartPM rate-limit-safe, and PM's draft state insulated from upstream flapping.

### Supabase resources (new dedicated MCP-data project — see westland-mcps spec)

```sql
create table wnd_email_drafts (
  project text not null,
  report_date date not null,
  editorial jsonb not null,                       -- ~2-5 KB, edited by PM
  graph_blob_path text not null,                  -- path in Storage: {project}/{report_date}.json
  smartpm_import_status text,                     -- 'processing' | 'ready' | 'unknown'
  graphs_ready_count int not null default 0,
  graphs_total int not null default 0,
  status text not null default 'editing',         -- editing | finalized | discarded
  created_by_email text not null,                 -- ctx.email at creation time
  created_at timestamptz not null default now(),
  last_edited_at timestamptz not null default now(),
  last_refreshed_at timestamptz not null default now(),
  primary key (project, report_date)
);
create index wnd_email_drafts_cleanup_idx on wnd_email_drafts(last_edited_at);
```

Storage bucket `wnd-graph-blobs`: object per draft at `{project}/{report_date}.json`, ~50-200 KB. Free tier is 1 GB; weekly cleanup keeps it under 50 MB indefinitely.

Cleanup: Cloudflare Cron Trigger (weekly, Monday 03:00 UTC) dispatches to the Worker's `scheduled` handler, which calls `runWeeklyEmailCleanup` in-process (no HTTP round-trip); the handler issues `delete from wnd_email_drafts where last_edited_at < now() - interval '30 days'` + matching Storage delete. `POST /weekly-email/cleanup` remains as a manual-trigger escape hatch (gated by `request.cf?.cronTrigger` OR an `X-Cleanup-Trigger` header secret). Worker-side cron is consistent with how westland-mcps' control plane works today.

### Browser editor (Worker static assets at `/weekly-email/editor/_assets/`)

Vanilla JavaScript SPA, served as static assets by the Worker. No framework — small.

Layout (vertical, single column, mirroring the email-preview HTML the existing flow uses):

```
┌──────────────────────────────────────────────────┐
│ G2203 — Lubumbashi MTC — Weekly Update           │
│ Report date: 2026-05-21 · Status: editing 🔵     │
│ Graphs: 7/9 ready · Last refreshed: 14:22:08     │
│                              [↻ Refresh graphs]  │
│                                                  │
│ Subject:    [editable input]              ✓      │
│ To:         [editable input — `;`-separated]  ✓  │
│ Cc:         [editable input]              ✓      │
│ Days behind:  [-3]   Gain/loss this week:  [+1]  │
│ ───────────────────────────────────────────────  │
│ Successes (per-item: text + [✓ include] [archive])│
│  • [text input row]                              │
│  • [text input row]   [+ add]                    │
│ Red flags (same shape)                           │
│ Stalled tasks (same shape)                       │
│ Key items (same shape)                           │
│ ───────────────────────────────────────────────  │
│ Gain/loss narrative:    [textarea]               │
│ EOT / recovery:         [textarea]               │
│ Logic changes:          [textarea]               │
│ SmartPM changelog URL:  [input]                  │
│ Custom paragraphs:  [label]/[text]/[✓ include]   │
│ ───────────────────────────────────────────────  │
│ Attachments:                                     │
│  • [filename]  [✓ include]  [P share-to-Procore] │
│    [status: active|new|archived]                 │
│  • ...                                           │
│ Changes report:  [✓ include]  [filename]         │
│ Skip Procore this week:  [☐]                     │
│ ───────────────────────────────────────────────  │
│ Signer:  [name]  [title]  [mobile]               │
│ ───────────────────────────────────────────────  │
│ Graphs preview (display only):                   │
│  [chart 01 HTML+SVG, static, read-only]          │
│  [chart 02 …]                                    │
│  [chart 03 PLACEHOLDER 🕒 Data processing]        │
│  …                                               │
│  [smartpm-summary-report HTML, static]           │
│ ───────────────────────────────────────────────  │
│ Last saved: 14:32:18 · All changes saved ✓       │
└──────────────────────────────────────────────────┘
```

The full field set mirrors what `generate_email_preview_html.py` renders today + what `parse_email_html.py` parses back. Per scheduling/CLAUDE.md, the **render / parse / Copy-for-Claude** trio must agree on the shape; the cloud editor IS the new render+parse, so the rule becomes: any field the existing HTML form has, the SPA has. Procore-related toggles (`skip_procore`, `attachments[].share_to_procore`) get visual emphasis (the `P` chip / master skip switch) because they're load-bearing per the existing CLAUDE.md.

Placeholder cards are emitted by `renderPlaceholder(slug)` from `@westland/charts` so dimensions match real charts by construction (no layout shift on refresh). Card schema:

```html
<div class="chart-card chart-card--placeholder" data-slug="{slug}">
  <header class="chart-card__title">{chart_title}</header>
  <div class="chart-card__body chart-card__body--placeholder">
    <svg viewBox="0 0 {svgWidth} {svgHeight}">
      <!-- subtle clock icon, "Data not yet available" text -->
    </svg>
  </div>
</div>
```

The Refresh button — **in-place swap, no page reload:**

1. User clicks `↻ Refresh graphs`. Button disables; each `.chart-card` gets `.refreshing` class.
2. **CSS overlay** dims each card to 50% opacity and centers a spinner glyph over it. Card dimensions don't change (same SVG viewBox), so layout doesn't shift. Editorial fields (subject, body, recipients) stay editable and focused — they're a separate DOM region.
3. Browser POSTs `/weekly-email/draft/{p}/{d}/refresh-graphs?sig=…`. Worker re-pulls SmartPM + re-renders + updates Supabase blob.
4. Response body returns the updated `graph_html` map + metadata: `{ graph_html: {slug: {status, html, svgInner}}, graphs_ready_count, graphs_total, last_refreshed_at, smartpm_import_status }`.
5. Browser iterates `graph_html`, finds each `.chart-card[data-slug="{slug}"]`, replaces it via `outerHTML = chunk.html`. New card has correct `status` class (ready / processing / error) and updated content.
6. Header `Graphs: X/Y ready` count + `Last refreshed` timestamp update from the response.
7. Button re-enables.

Error handling:
- POST returns 4xx/5xx → toast with the error message, cards lose `.refreshing` class (restored to pre-click state), button re-enables. User retries.
- Network failure → same toast path, browser doesn't blow away in-flight editorial autosaves (they're independent PUT requests, not affected by the refresh POST).

**Why in-place beats full reload:** The PM is mid-edit when they click Refresh. A full reload steals cursor focus, loses scroll position, and flashes a blank state before the editor reinitializes. In-place swap keeps the editor stable — only the chart blocks visibly change, exactly the affordance the button promises.

Autosave race is a non-issue: editorial layer and graph layer live in separate Supabase rows and update via separate Worker routes (`PUT /editorial` vs `POST /refresh-graphs`). The Refresh POST never reads or writes editorial; autosave PUTs never read or write `graph_html`. They can fire simultaneously without conflict.

Autosave pattern:

1. Every editable field input → write current value to `localStorage` under `draft:{project}:{report_date}:{field}` + mark unsaved.
2. Debounced 500ms PUT to `/weekly-email/draft/{p}/{d}/editorial` with the full editorial object.
3. Indicator state machine per field: idle → 🔵 saving → ✓ saved → ❌ save failed (auto-retry every 5s with exponential backoff up to 60s).
4. On editor load, reconcile: server editorial vs. localStorage unsaved entries; if local is newer (timestamp), replay PUT.
5. On `beforeunload`: if unsaved, attempt synchronous fetch (best-effort). localStorage persists either way.
6. On page reload after Refresh: editorial layer is untouched server-side (the MCP tool's upsert preserves it); local edits reconcile as above; graph cards update to reflect new server state.

### Local finalize and `.eml` builder

The existing `generate_email_eml.py` consumes a parsed email-preview HTML today. New input contract: it consumes `email-draft.json` directly.

```python
draft = json.load(open(dated_folder / 'email-draft.json'))
editorial = draft['editorial']
graph_html = draft['graph_html']  # {slug: {status, html, svgInner}}

# Stack all charts (including placeholders, including error cards) into one
# tall HTML page in the canonical order from editorial.graph_order.
# Each entry's `html` field is used (NOT `svgInner` — that's for the browser
# editor's inline-embed case). Composite slugs like smartpm-summary-report
# have svgInner='' anyway; using html uniformly avoids the conditional.
#
# Chart cards are rendered at 1728px native width (SmartPM scale).
# The stacking page sets viewport width to 1200px and uses CSS to scale the
# cards down — SVG scales crisply, no rasterization loss.
stacked_html = build_stacked_chart_page(graph_html, order=editorial['graph_order'])
stacked_html_path = dated_folder / '.tmp-stacked-charts.html'
stacked_html_path.write_text(stacked_html, encoding='utf-8')

# Use the renderer agent's existing rasterizer
subprocess.run(['node', 'html_to_png.js', stacked_html_path,
                dated_folder / 'screenshots' / 'all-graphs-stacked.png',
                '--width=1200', '--full-page'], check=True)

# Build .eml with one inline image instead of N
eml = build_eml(
    subject=editorial['subject'],
    to=editorial['to'], cc=editorial['cc'],
    body_html=editorial['body_html'],
    inline_images={'cid:graphs': dated_folder / 'screenshots' / 'all-graphs-stacked.png'},
)
eml_path.write_bytes(eml.as_bytes())

# Existing Outlook COM code creates the draft from eml_path
create_outlook_draft(eml_path)
```

Per-chart artifacts can still be regenerated standalone via the renderer agent's `@westland/charts` CLI if needed; the email pipeline uses only the stacked PNG.

## Auth: hybrid model

Two distinct caller types, two distinct verifications:

### MCP tool calls (Claude → Worker)

Identical to the existing westland-mcps pattern (smartpm, buildr, westland-internal). Claude's session connects via Procore-OAuth identity-federation; the Worker's `OAuthProvider` middleware validates the bearer token; `ctx.props` delivers `{ email, procoreUserId }` to the tool handler; the `@westlandconstruction.com` email gate (+ allowlist) is enforced at Procore-callback time.

Per-tool authorization: `created_by_email` on the `wnd_email_drafts` row scopes who can read/write each draft. A PM can't view another PM's drafts. (Mirrors the `list_my_reports` pattern in `westland-internal`.)

### Browser route calls (editor → Worker)

Browser has no OAuth context — the PM clicked a URL. Auth is via HMAC signed URLs:

```
sig = base64url(hmacSha256(EDITOR_HMAC_SECRET, `${project}|${report_date}|${exp}`))
url = `${base}/weekly-email/editor/${project}/${report_date}?sig=${sig}&exp=${exp}`
```

Web Crypto API (`crypto.subtle.sign`) — works in Workers, Node 18+, Deno. Constant-time compare via `crypto.subtle.verify`. Every browser-side route extracts `sig` + `exp` from the query string, recomputes HMAC, verifies, checks `exp > now()`. No DB lookup, no session table.

The Worker mints these URLs when the MCP tool returns; the URL is the only credential the PM ever sees. Token is regenerable by re-running `generate_weekly_email_draft` (idempotent — preserves editorial, refreshes graphs, mints new URL).

Secret rotation: change `EDITOR_HMAC_SECRET` Worker secret → all outstanding URLs invalidate immediately. Re-issue via Claude on demand. Document in westland-mcps' `WAKE-UP.md`.

### Why two models

The MCP side needs identity (audit trail, per-PM scoping, allowlist enforcement). The browser side needs zero friction (PM shouldn't OAuth into a separate flow to see their own draft). HMAC over `(project, report_date, exp)` gives presigned-URL semantics: bearer-of-URL == authorized; expiry bounds blast radius if leaked.

**Browser-side ACL clarification:** Row-level `created_by_email === ctx.email` enforcement applies to **MCP-tool callers only**. HMAC-authenticated browser routes do NOT re-check `created_by_email` on each request — the browser has no identity to check against. The chain is: `Procore-OAuth identity at the MCP layer → MCP tool validates created_by_email → MCP mints signed URL → URL bearer has access for `exp` seconds`. This is the standard presigned-URL pattern (same as S3 / Supabase Storage signed URLs). If a PM forwards their URL to someone else inside the expiry window, that someone else can edit the draft; that's a deliberate property of the model, not a gap.

## Data shapes

### Seed JSON (Claude → MCP tool)

**The `editorial` layer mirrors the canonical email-preview shape exactly** — i.e., the dict returned by `scheduling/skills/schedule-update/references/parse_email_html.py::parse_preview_html()`. That shape is documented in `scheduling/CLAUDE.md` ("Email-preview JSON shape — single source of truth") and is the source of truth for both the existing HTML round-trip flow and this new flow. Per the plugin's CLAUDE.md, the Procore-related fields (`skip_procore`, `attachments[].share_to_procore`) are load-bearing, not cosmetic.

```json
{
  "project": "G2203",
  "report_date": "2026-05-21",
  "editorial": {
    "project_info": { "project_name": "Lubumbashi MTC", "...": "..." },
    "subject": "G2203 — Lubumbashi MTC — Weekly Update — 2026-05-21",
    "from": "camron@westlandconstruction.com",
    "to": "owner@example.com; owner2@example.com",
    "cc": "sub1@example.com",
    "days_behind": 14,
    "gain_loss": -3,
    "successes":     [{ "text": "...", "checked": true, "status": "active", "date_archived": "" }, "..."],
    "red_flags":     [{ "text": "...", "checked": true, "status": "active", "date_archived": "" }, "..."],
    "stalled_tasks": [{ "text": "...", "checked": true, "status": "active", "date_archived": "" }, "..."],
    "key_items":     [{ "text": "...", "checked": true, "status": "active", "date_archived": "" }, "..."],
    "gain_loss_narrative": "...",
    "eot_recovery": "...",
    "logic_changes": "...",
    "smartpm_changelog_url": "...",
    "custom_paragraphs": [{ "label": "...", "text": "...", "checked": true }, "..."],
    "attachments": [
      {
        "filename": "...",
        "checked": true,
        "status": "active",
        "date_archived": "",
        "share_to_procore": false
      }
    ],
    "changes_report": { "include": true, "filename": "..." },
    "skip_procore": false,
    "signer_name": "Camron Walker",
    "signer_title": "Scheduler",
    "signer_mobile": "...",
    "graph_order": ["01-...", "02-...", "06-...", "07-...", "smartpm-summary-report"]
  },
  "smartpm": {
    "project_name": "Lubumbashi MTC",
    "scenario_id": null
  }
}
```

Fields that the OLD HTML round-trip computes from the parsed HTML — `summary_screenshot_rel`, `graph_screenshot_rels` — are **dropped from the editorial layer in this flow**. Their replacement is the rendered HTML+SVG chart chunks in `graph_html` plus the single stacked PNG produced at finalize time. Downstream consumers (`generate_email_eml.py`, Procore upload phase) consume the new graph layer + the stacked PNG path instead of per-chart relative paths.

### Working JSON (assembled by Worker, lives on disk after finalize)

```json
{
  "project": "G2203",
  "report_date": "2026-05-21",
  "editorial": { /* full canonical email-preview shape — see seed above + parse_email_html.parse_preview_html() */ },
  "graph_data": {
    "01-planned-vs-actual-percent-complete": { /* SmartPM response */ },
    "smartpm-summary-report": { "cards": {...}, "curve": {...}, "milestones": {...} },
    "03-some-slug": null
  },
  "graph_html": {
    "01-planned-vs-actual-percent-complete": {
      "status": "ready",
      "html": "<div class='chart-card'>...</div>",
      "svgInner": "<g class='series'>...</g>"
    },
    "smartpm-summary-report": {
      "status": "ready",
      "html": "<div class='chart-card'>...</div>",
      "svgInner": ""
    },
    "03-some-slug": {
      "status": "processing",
      "html": "<div class='chart-card chart-card--placeholder'>...</div>",
      "svgInner": ""
    },
    "05-other-slug": {
      "status": "error",
      "html": "<div class='chart-card chart-card--placeholder'>... Render failed ...</div>",
      "svgInner": ""
    }
  },
  "meta": {
    "schema_version": 1,
    "generated_at": "2026-05-21T20:14:33Z",
    "last_refreshed_at": "2026-05-21T20:14:33Z",
    "last_edited_at": "2026-05-21T21:02:11Z",
    "status": "finalized",
    "smartpm_import_status": "ready",
    "graphs_ready_count": 8,
    "graphs_total": 9
  }
}
```

## Migration

Two repos, three streams. Each lands independently per its own release convention.

### westland-mcps (new service)

1. New worktree on westland-mcps; branch `feat/weekly-email-service`.
2. Add `src/services/weekly-email/` mirroring the shape of `src/services/westland-internal/`:
   - `agent.js` — MCP tool registrations (`generate_weekly_email_draft`, `get_weekly_email_status`, `finalize_weekly_email`).
   - `routes.js` — Hono HTTP routes (the editor + draft + refresh + status + cleanup endpoints).
   - `ctx.js` — Worker ctx helpers, mirror existing services. *(No `acl.js` — single equality check `ctx.email === row.created_by_email` is inline in each handler; westland-mcps spec deviates from this file-map on purpose, no admin allowlist needed.)*
   - `supabase-client.js` — adapted from `westland-internal/supabase-client.js`; **points at a new dedicated MCP-data Supabase project, not the existing one**.
   - `hmac.js` — Web Crypto signing/verifying for browser routes.
   - `orchestrator.js` — `generate`/`refresh` flow; the only file that imports `@westland/charts`.
   - `smartpm-bridge.js` — in-process calls to the existing smartpm service (no HTTP round-trip).
   - `editor-html.js`, `editor-js.js`, `editor-css.js` — SPA assets as template-literal-string JS modules (no `[assets]` binding for this small SPA).
   - `cleanup.js` — invoked by the Worker's `scheduled` handler on the Cloudflare Cron Trigger.
   - `CLAUDE.md` — service docs.
3. Wire into `src/index.js` alongside other service handler factories. `scheduled` handler dispatches to `cleanup.runWeeklyEmailCleanup` in-process.
4. Add `@westland/charts` to `package.json` once the renderer agent publishes (GitHub Packages — option B; submodule fallback if the publish flow stalls).
5. Supabase: **create a new dedicated MCP-data project** (suggested name `westland-mcps`, separate from the Power BI project `anwdfilrfczluhudtbzw`). Apply migration creating `wnd_email_drafts` table + `wnd-graph-blobs` bucket. Adds two new Worker secrets: `SUPABASE_MCPS_URL`, `SUPABASE_MCPS_SERVICE_ROLE_KEY` (existing `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` stay pointing at the Power BI project for `westland-internal`).
6. Add Worker secret `EDITOR_HMAC_SECRET` via `npx wrangler secret put` (generate with `node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"`).
7. Add Cloudflare Cron Trigger in `wrangler.toml` (`crons = ["0 3 * * 1"]`) → Worker `scheduled` handler → `cleanup.runWeeklyEmailCleanup`.
8. Update `wrangler.toml` cron config + ensure `default export { fetch, scheduled }` shape coexists with the existing OAuthProvider mount. Resolution risk flagged in westland-mcps spec.
9. Deploy: `npx wrangler deploy`. Verify with `npx wrangler tail`.
10. Update westland-mcps `README.md` + `WAKE-UP.md` with the new connector URL + secret-rotation procedure + GitHub-Packages-PAT provisioning step.

### construction-skills (integration)

1. This branch (`feat/weekly-email-cloud-editor-integration`).
2. Rewrite `scheduling/skills/schedule-update/phases/draft.md` to drive the new flow (replaces the current "edit email-preview.html" body).
3. Update `phases/email.md` to read `email-draft.json` instead of `*-email-preview.html`.
4. Modify `generate_email_eml.py` to consume `email-draft.json` and emit one stacked PNG via `node html_to_png.js`.
5. Update `scheduling/hooks/check_html_discipline.py`: remove the `*-email-preview.html` matcher (vestigial after this lands). Keep the `project-context.html` matcher (still relevant).
6. Bump `scheduling/.claude-plugin/plugin.json` minor version.
7. Bump matching entry in `.claude-plugin/marketplace.json`.
8. `python build.py scheduling` from the main repo working tree (not a worktree).
9. Distribute zip.

### Coordination gates

- westland-mcps service can't deploy meaningfully until renderer agent ships their commit 1 (package skeleton + stable types). The Worker can compile + deploy with stub renderer imports earlier, but end-to-end testing requires the renderer landed.
- **End-to-end smoke test requires the renderer agent's commit 11** (summary report — their last chart before the cleanup commit). Until then, the `smartpm-summary-report` slug doesn't exist; westland-mcps' integration tests should expect it to fall through to `renderPlaceholder('smartpm-summary-report')` with status='error' (slug not in registry). The cloud function can ship before commit 11, but a real weekly email won't render correctly until all 17 slugs (16 trends + summary) are implemented.
- construction-skills integration can ship without the Worker live — `phases/draft.md` documents the new flow but the MCP tools won't exist until the Worker ships. So land the Worker first, then construction-skills.
- End-to-end smoke test: generate a draft for a real recent project (e.g. G2203 most recent week), edit the body in the browser, click Refresh once SmartPM is ready, finalize, verify the `.eml` builds with the stacked PNG inline.

## Risks

- **Renderer agent's API surface drifts mid-implementation.** Mitigation: their spec settles the registry + `renderPlaceholder` + `CHART_META` shapes in commit 1; westland-mcps codes against those as stable. Any later changes require both branches to coordinate. The renderer agent's error-handling contract (throw on programming-bug-class, return empty-state card for empty data arrays) is documented in their spec §"Error handling contract" — westland-mcps' service catches throws at the orchestration layer and substitutes an error placeholder.
- **Cloud function down at finalize.** Mitigation: `finalize_weekly_email` returns a clear error; PM retries Claude in 10 min. Draft state is durable in Supabase. The local seed snapshot (written by Claude before the MCP call returns the URL) is the last-resort recovery.
- **Browser closes before autosave POST lands.** Mitigation: `localStorage` write happens synchronously on every keystroke; reconcile on next load. Worst case = 1 keystroke lost, only if browser closed in the 500ms debounce window.
- **HMAC secret leaks.** Mitigation: rotate Worker secret → all URLs invalidate. Re-issue via Claude (idempotent).
- **30-day retention surprises someone.** Mitigation: documented in `phases/draft.md`. The dated project folder on the share holds `email-draft.json` regardless.
- **PM finalizes with placeholders still showing.** Mitigation: response includes `graphs_ready_count < graphs_total`; Claude warns before assembling. PM can decide to ship with placeholders or wait and re-render.
- **Re-render after PM has edited graph_order.** Mitigation: `graph_order` lives in the editorial layer; re-renders only touch graph_data + graph_html; order preserved.
- **Cloudflare free tier exhaustion (100k req/day).** Realistic projection: ~1,200 req/day at full 40-PM deployment (dominated by autosave PUTs). 80× headroom. If exceeded, upgrade to Workers Paid ($5/mo, 10M req/mo) — zero migration. If we ever needed to leave Cloudflare entirely, the Hono routes port to Node/Deno/Bun ~1-2 days; Supabase stays put.
- **Worker bundle size.** `@westland/charts` (17 renderers + svg-lib reimplemented locally, no d3) should compile to well under the Worker 1 MB compressed limit. Renderer agent's spec asserts ~200 lines for svg-lib + ~25 lines per chart = ~625 lines of pure JS. Verify via wrangler-bundle smoke test in their package.

## Open questions (resolve in implementation plans, not blocking design approval)

- **Editor SPA framework or vanilla?** Default vanilla JS (no framework). If the autosave/refresh UX gets fiddly, escape hatch is htmx or a tiny Lit/Preact island. Settle during the westland-mcps agent's implementation plan.
- **Stacked PNG width.** 1200px (typical email column on desktop Outlook) vs. 800px (denser, narrow viewports). Settle during first end-to-end render.
- **contenteditable vs textarea + markdown for `body_html`.** contenteditable is closer to final rendering; markdown is simpler but adds conversion. Default contenteditable with paste-as-plain-text; revisit if it bites.
- **Placeholder copy.** Exact wording on the placeholder card and the editor-header hint. Settle during first PM walkthrough.
- **Refresh button spinner styling.** CSS-only overlay (`.chart-card.refreshing::after` with a spinner glyph) — no JS animation lib, no need for the chart package to expose a spinner-icon variant of `renderPlaceholder`. Spinner SVG inlined as a data URI in the editor CSS.
- **Per-PM admin view.** Out of scope for v1; PMs only see their own drafts via `created_by_email === ctx.email`. A future admin tool might let Camron see all drafts; out of scope here.
