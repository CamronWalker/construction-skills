# Proposal Schedule Online Review Service (westland-mcps) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `proposal-schedule-review` sub-service to the westland-mcps Cloudflare Worker: a bearer-URL hosted page that renders a proposal schedule from uploaded data and collects attributed, version-scoped task comments, plus three MCP tools to publish versions and pull comments.

**Architecture:** A new `src/services/westland-forms/proposal-schedule-review/` sibling of `weekly-schedule-update-email/`. The review UI is one self-contained `app/index.html` (frappe-gantt + logo inlined) imported as a Text module and served inline via Hono with serve-time placeholder injection. Per-version schedule data (`schedule-activities.json`) is stored in Supabase Storage and validated on upload; comments live in Postgres. Auth is HMAC bearer-URL (generalized from the existing weekly-email signer). Tools are composed into `/westland/mcp`.

**Tech Stack:** Cloudflare Workers (Hono), Node ESM (`node>=22`), `node --test`, Supabase PostgREST + Storage REST (service-role), Web Crypto HMAC-SHA256, frappe-gantt (vendored, browser-side).

## Global Constraints

- Node `>=22`; test runner `node --test` (`node:test` + `node:assert/strict`), colocated `*.test.js`; pure-function unit tests only (no live network — DB/route integration is verified on deploy).
- One `[assets]` binding exists (`WEEKLY_EMAIL_ASSETS`) and MUST NOT be repointed or duplicated. New static bytes ship via `[[rules]] type="Text"` module imports, not a second binding.
- Do NOT modify weekly-email behavior. The HMAC refactor MUST keep `signEditorUrl`/`verifyEditorRequest` behavior identical (their tests/usage unchanged).
- MCP tool export shape: `export default { name, description, annotations, inputSchema, handler }`; `handler` receives the arguments object directly; identity/env come from `getEnv()`/`getEmail()` (ALS). Register new tools in `src/services/westland/agent.js` (the live `/westland/mcp` path) AND mirror in `src/services/westland-forms/agent.js`.
- Supabase: MCP-data project via `SUPABASE_MCPS_URL` + `SUPABASE_MCPS_SERVICE_ROLE_KEY`; service-role bypasses RLS, tenancy enforced in-query. Relate to projects by `job_number` string (no cross-project FK).
- Reuse the existing `EDITOR_HMAC_SECRET` and `PUBLIC_BASE_URL` secrets; `DEFAULT_BASE_URL = "https://westland-mcps.westland.workers.dev"`.
- Deploy = merge to `main` → GitHub Actions `wrangler deploy`. Never `wrangler deploy` locally. Apply the DB migration out-of-band to the MCP-data Supabase project.
- **Worktree:** do all work in an isolated git worktree of westland-mcps (the main checkout is shared by concurrent sessions).

---

## File Structure

```
src/services/westland-forms/
  shared/
    hmac.js                        # MODIFY: add generic signUrl/verifyRequest; keep editor wrappers
    hmac.test.js                   # CREATE: generic + backward-compat tests
  proposal-schedule-review/
    supabase-client.js             # CREATE: reviews/versions/comments CRUD + snapshot blob up/down
    schema.js                      # CREATE: validateActivities() upload validator + version constants
    schema.test.js                 # CREATE
    publish.js                     # CREATE: pure publish-mode decision (create|updated|new_version)
    publish.test.js                # CREATE
    routes.js                      # CREATE: Hono routes (serve app + snapshot + versions + comments + schema)
    app/
      index.html                   # CREATE: self-contained review app (Text-imported)
      vendor/frappe-gantt.umd.js    # CREATE: copied from construction-skills
      vendor/frappe-gantt.css       # CREATE: copied from construction-skills
    tools/
      generate-proposal-review-link.js  # CREATE
      get-proposal-review-comments.js    # CREATE
      get-proposal-review-status.js      # CREATE
      index.js                            # CREATE: { tools, toolsByName }
  routes.js                        # MODIFY: mount /proposal-schedule-review
  agent.js                         # MODIFY: add proposal-review tools to aggregation (mirror)
src/services/westland/agent.js     # MODIFY: add proposal-review tools to allTools (LIVE path)
wrangler.toml                      # MODIFY: add [[rules]] Text for the app html/css/vendor
docs/superpowers/plans/2026-07-23-proposal-review-service.md  # this plan (copied into the worktree)
docs/db/2026-07-23-proposal-review-schema.sql                 # CREATE: migration reference
```

---

### Task 1: DB migration reference SQL

**Files:**
- Create: `docs/db/2026-07-23-proposal-review-schema.sql`

**Interfaces:**
- Produces: tables `wnd_proposal_reviews`, `wnd_proposal_review_versions`, `wnd_proposal_review_comments`; Storage bucket `wnd-proposal-review`. Consumed by Task 3's client.

- [ ] **Step 1: Write the migration reference file**

```sql
-- 2026-07-23 proposal-schedule-review schema (MCP-data Supabase project).
-- Applied out-of-band via Supabase apply_migration / dashboard — NOT run from repo.
-- Storage: create a bucket named 'wnd-proposal-review' (private).

create table if not exists public.wnd_proposal_reviews (
  id                uuid primary key default gen_random_uuid(),
  job_number        text not null unique,
  project_name      text,
  current_version   text not null,
  created_by_email  text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create table if not exists public.wnd_proposal_review_versions (
  id                 uuid primary key default gen_random_uuid(),
  job_number         text not null,
  version_label      text not null,
  snapshot_path      text not null,
  published_at       timestamptz not null default now(),
  published_by_email text,
  unique (job_number, version_label)
);

create table if not exists public.wnd_proposal_review_comments (
  id                      uuid primary key default gen_random_uuid(),
  job_number              text not null,
  version_label           text not null,
  task_code               text not null,
  task_name_snapshot      text,
  orig_duration_snapshot  numeric,
  reviewer_id             text not null,
  reviewer_name           text not null,
  body                    text,
  suggested_duration_days numeric,
  resolved                boolean not null default false,
  resolved_by             text,
  resolved_at             timestamptz,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);
create index if not exists wnd_prc_job_version_idx
  on public.wnd_proposal_review_comments (job_number, version_label, created_at);

alter table public.wnd_proposal_reviews          enable row level security;
alter table public.wnd_proposal_review_versions  enable row level security;
alter table public.wnd_proposal_review_comments  enable row level security;
-- No policies: service-role only (matches wnd_email_drafts / wnd_projects convention).
```

- [ ] **Step 2: Commit**

```bash
git add docs/db/2026-07-23-proposal-review-schema.sql
git commit -m "feat(proposal-review): DB migration reference for review tables + bucket"
```

Rollout note (not a code step): before/with deploy, apply this SQL to the MCP-data project and create the `wnd-proposal-review` bucket.

---

### Task 2: Generalize the HMAC signer (keep editor wrappers)

**Files:**
- Modify: `src/services/westland-forms/shared/hmac.js`
- Test: `src/services/westland-forms/shared/hmac.test.js`

**Interfaces:**
- Produces: `signUrl(env, { baseUrl, path, parts, expiresInSec }) → { url, expiresAt }`; `verifyRequest(env, request, { parts }) → void (throws HttpError)`. `parts` is `string[]`; signed payload is `[...parts, exp].join("|")`.
- Consumes: existing `EDITOR_HMAC_SECRET`, `HttpError`.
- Contract: `signEditorUrl`/`verifyEditorRequest` keep identical output (they become wrappers with `parts=[project, reportDate]`, and the editor path prefix baked into `path`).

- [ ] **Step 1: Write failing tests**

```js
// src/services/westland-forms/shared/hmac.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { signUrl, verifyRequest, signEditorUrl, HttpError } from "./hmac.js";

const ENV = { EDITOR_HMAC_SECRET: "test-secret-please-ignore-000000000000" };

test("signUrl round-trips through verifyRequest", async () => {
  const { url } = await signUrl(ENV, {
    baseUrl: "https://x.example",
    path: "/westland-forms/proposal-schedule-review/review/W1234",
    parts: ["W1234"],
  });
  const req = new Request(url);
  await verifyRequest(ENV, req, { parts: ["W1234"] }); // must not throw
  assert.ok(url.includes("sig=") && url.includes("exp="));
});

test("verifyRequest rejects a tampered part", async () => {
  const { url } = await signUrl(ENV, {
    baseUrl: "https://x.example",
    path: "/p/W1234", parts: ["W1234"],
  });
  const req = new Request(url);
  await assert.rejects(() => verifyRequest(ENV, req, { parts: ["W9999"] }),
    (e) => e instanceof HttpError && e.status === 401);
});

test("verifyRequest rejects an expired url", async () => {
  const { url } = await signUrl(ENV, {
    baseUrl: "https://x.example", path: "/p/W1234", parts: ["W1234"],
    expiresInSec: -10,
  });
  await assert.rejects(() => verifyRequest(ENV, new Request(url), { parts: ["W1234"] }),
    (e) => e instanceof HttpError && e.status === 401);
});

test("signEditorUrl still produces the weekly-email path + verifies", async () => {
  const { url } = await signEditorUrl(ENV, {
    baseUrl: "https://x.example", project: "G2203", reportDate: "2026-06-16",
  });
  assert.ok(url.includes("/westland-forms/weekly-schedule-update-email/editor/G2203/2026-06-16"));
});
```

- [ ] **Step 2: Run — expect FAIL** (`signUrl`/`verifyRequest` not exported)

Run: `node --test src/services/westland-forms/shared/hmac.test.js`
Expected: FAIL (import error / not a function).

- [ ] **Step 3: Implement the generic signer, refactor wrappers**

In `hmac.js`, add a generic payload + `signUrl`/`verifyRequest`, then re-express the editor functions as wrappers. Keep `getKey`, `base64url*`, `HttpError` as-is.

```js
function partsPayload(parts, exp) {
  return [...parts, exp].join("|");
}

/**
 * Generic signed URL. `path` is the full path (no query). `parts` are the
 * path-bound values folded into the signature (order matters).
 */
export async function signUrl(env, { baseUrl, path, parts, expiresInSec = 7 * 24 * 3600 }) {
  if (!env.EDITOR_HMAC_SECRET) throw new Error("EDITOR_HMAC_SECRET is not configured.");
  const exp = Math.floor(Date.now() / 1000) + expiresInSec;
  const key = await getKey(env.EDITOR_HMAC_SECRET);
  const sigBytes = await crypto.subtle.sign("HMAC", key, ENC.encode(partsPayload(parts, exp)));
  const sig = base64urlEncode(sigBytes);
  const url = `${baseUrl}${path}?sig=${sig}&exp=${exp}`;
  return { url, expiresAt: new Date(exp * 1000).toISOString() };
}

export async function verifyRequest(env, request, { parts }) {
  if (!env.EDITOR_HMAC_SECRET) throw new HttpError(500, "EDITOR_HMAC_SECRET is not configured.");
  const url = new URL(request.url);
  const sig = url.searchParams.get("sig");
  const exp = url.searchParams.get("exp");
  if (!sig || !exp) throw new HttpError(401, "missing sig or exp");
  const expNum = Number(exp);
  if (!Number.isFinite(expNum)) throw new HttpError(401, "invalid exp");
  if (expNum < Math.floor(Date.now() / 1000)) throw new HttpError(401, "url expired — re-run the generate tool to get a fresh link");
  const key = await getKey(env.EDITOR_HMAC_SECRET);
  let sigBytes;
  try { sigBytes = base64urlDecode(sig); } catch { throw new HttpError(401, "invalid sig encoding"); }
  const ok = await crypto.subtle.verify("HMAC", key, sigBytes, ENC.encode(partsPayload(parts, expNum)));
  if (!ok) throw new HttpError(401, "invalid sig");
}
```

Refactor the two editor functions to delegate (preserving the exact path + payload — note the editor payload was `project|reportDate|exp`, which equals `partsPayload([project, reportDate], exp)`):

```js
export async function signEditorUrl(env, { baseUrl, project, reportDate, expiresInSec = 7 * 24 * 3600 }) {
  return signUrl(env, {
    baseUrl,
    path: `/westland-forms/weekly-schedule-update-email/editor/${encodeURIComponent(project)}/${encodeURIComponent(reportDate)}`,
    parts: [project, reportDate],
    expiresInSec,
  });
}

export async function verifyEditorRequest(env, request, { project, reportDate }) {
  return verifyRequest(env, request, { parts: [project, reportDate] });
}
```

- [ ] **Step 4: Run — expect PASS**

Run: `node --test src/services/westland-forms/shared/hmac.test.js`
Expected: PASS (all 4).

- [ ] **Step 5: Commit**

```bash
git add src/services/westland-forms/shared/hmac.js src/services/westland-forms/shared/hmac.test.js
git commit -m "feat(proposal-review): generalize HMAC signer; editor URLs become wrappers"
```

---

### Task 3: Review Supabase client (DB + Storage helpers)

**Files:**
- Create: `src/services/westland-forms/proposal-schedule-review/supabase-client.js`

**Interfaces:**
- Consumes: `getEnv()` from `../shared/ctx.js`; secrets `SUPABASE_MCPS_URL`/`SUPABASE_MCPS_SERVICE_ROLE_KEY`.
- Produces:
  - `readReview(jobNumber) → row|null`
  - `upsertReview({ job_number, project_name, current_version, created_by_email }) → row`
  - `listVersions(jobNumber) → [{version_label, snapshot_path, published_at}]` (asc)
  - `insertVersion({ job_number, version_label, snapshot_path, published_by_email }) → row`
  - `getVersion(jobNumber, versionLabel) → row|null`
  - `listComments(jobNumber, versionLabel?) → rows`
  - `insertComment(fields) → row`
  - `updateComment(id, patch) → row`  (used for edit body / toggle resolved)
  - `deleteComment(id) → void`
  - `uploadSnapshot(jobNumber, versionLabel, obj) → path`  (Storage; `x-upsert:true`)
  - `readSnapshot(path) → obj|null`

- [ ] **Step 1: Implement the client (mirror the weekly-email `shared/supabase-client.js` REST style verbatim: `requireSecrets`, `jsonHeaders`, PostgREST verbs, Storage REST).**

Key rules to copy exactly: `requireSecrets(env)` reads `SUPABASE_MCPS_URL`/`SUPABASE_MCPS_SERVICE_ROLE_KEY`, strips trailing slash; `jsonHeaders(key)` = `{ apikey, Authorization: Bearer, Content-Type, Accept }`; POST/PATCH use `Prefer: return=representation`; Storage uses bucket `wnd-proposal-review`, path `${job}/${version}.json`, POST with `x-upsert:true`. `updated_at` is set in code (`new Date().toISOString()`), not by a trigger. `upsertReview` is read-then-PATCH-or-POST keyed on `job_number` (mirror `upsertProject`/`upsertDraftAtomic`).

```js
// src/services/westland-forms/proposal-schedule-review/supabase-client.js
import { getEnv } from "../shared/ctx.js";

const BUCKET = "wnd-proposal-review";

function requireSecrets(env) {
  if (!env.SUPABASE_MCPS_URL) throw new Error("SUPABASE_MCPS_URL is not configured.");
  if (!env.SUPABASE_MCPS_SERVICE_ROLE_KEY) throw new Error("SUPABASE_MCPS_SERVICE_ROLE_KEY is not configured.");
  return { url: env.SUPABASE_MCPS_URL.replace(/\/$/, ""), key: env.SUPABASE_MCPS_SERVICE_ROLE_KEY };
}
function jsonHeaders(key) {
  return { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", Accept: "application/json" };
}
async function pg(env, method, pathAndQs, body, extraHeaders = {}) {
  const { url, key } = requireSecrets(env);
  const res = await fetch(`${url}/rest/v1/${pathAndQs}`, {
    method, headers: { ...jsonHeaders(key), ...extraHeaders },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Supabase ${method} ${pathAndQs} failed (${res.status}): ${(await res.text()).slice(0, 500)}`);
  const txt = await res.text();
  return txt ? JSON.parse(txt) : null;
}

export async function readReview(jobNumber) {
  const rows = await pg(getEnv(), "GET", `wnd_proposal_reviews?job_number=eq.${encodeURIComponent(jobNumber)}&limit=1&select=*`);
  return (rows && rows[0]) || null;
}
export async function upsertReview(fields) {
  const env = getEnv();
  const now = new Date().toISOString();
  const existing = await readReview(fields.job_number);
  if (existing) {
    const rows = await pg(env, "PATCH", `wnd_proposal_reviews?job_number=eq.${encodeURIComponent(fields.job_number)}`,
      { project_name: fields.project_name ?? existing.project_name, current_version: fields.current_version, updated_at: now },
      { Prefer: "return=representation" });
    return rows[0];
  }
  const rows = await pg(env, "POST", "wnd_proposal_reviews",
    { job_number: fields.job_number, project_name: fields.project_name, current_version: fields.current_version,
      created_by_email: fields.created_by_email, created_at: now, updated_at: now },
    { Prefer: "return=representation" });
  return Array.isArray(rows) ? rows[0] : rows;
}
export async function listVersions(jobNumber) {
  return pg(getEnv(), "GET", `wnd_proposal_review_versions?job_number=eq.${encodeURIComponent(jobNumber)}&order=published_at.asc&select=version_label,snapshot_path,published_at`);
}
export async function getVersion(jobNumber, versionLabel) {
  const rows = await pg(getEnv(), "GET", `wnd_proposal_review_versions?job_number=eq.${encodeURIComponent(jobNumber)}&version_label=eq.${encodeURIComponent(versionLabel)}&limit=1&select=*`);
  return (rows && rows[0]) || null;
}
export async function insertVersion(fields) {
  const rows = await pg(getEnv(), "POST", "wnd_proposal_review_versions",
    { job_number: fields.job_number, version_label: fields.version_label, snapshot_path: fields.snapshot_path,
      published_by_email: fields.published_by_email, published_at: new Date().toISOString() },
    { Prefer: "return=representation" });
  return Array.isArray(rows) ? rows[0] : rows;
}
export async function listComments(jobNumber, versionLabel) {
  let qs = `wnd_proposal_review_comments?job_number=eq.${encodeURIComponent(jobNumber)}`;
  if (versionLabel) qs += `&version_label=eq.${encodeURIComponent(versionLabel)}`;
  qs += "&order=created_at.asc&select=*";
  return pg(getEnv(), "GET", qs);
}
export async function insertComment(f) {
  const now = new Date().toISOString();
  const rows = await pg(getEnv(), "POST", "wnd_proposal_review_comments",
    { ...f, created_at: now, updated_at: now }, { Prefer: "return=representation" });
  return Array.isArray(rows) ? rows[0] : rows;
}
export async function updateComment(id, patch) {
  const rows = await pg(getEnv(), "PATCH", `wnd_proposal_review_comments?id=eq.${encodeURIComponent(id)}`,
    { ...patch, updated_at: new Date().toISOString() }, { Prefer: "return=representation" });
  return rows[0];
}
export async function deleteComment(id) {
  await pg(getEnv(), "DELETE", `wnd_proposal_review_comments?id=eq.${encodeURIComponent(id)}`);
}
export async function uploadSnapshot(jobNumber, versionLabel, obj) {
  const { url, key } = requireSecrets(getEnv());
  const path = `${jobNumber}/${versionLabel}.json`;
  const res = await fetch(`${url}/storage/v1/object/${BUCKET}/${path}`, {
    method: "POST",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", "x-upsert": "true" },
    body: JSON.stringify(obj),
  });
  if (!res.ok) throw new Error(`Storage upload failed (${res.status}): ${(await res.text()).slice(0, 500)}`);
  return path;
}
export async function readSnapshot(path) {
  const { url, key } = requireSecrets(getEnv());
  const res = await fetch(`${url}/storage/v1/object/${BUCKET}/${path}`, { headers: { apikey: key, Authorization: `Bearer ${key}` } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Storage read failed (${res.status}): ${(await res.text()).slice(0, 500)}`);
  return res.json();
}
```

- [ ] **Step 2: Commit** (no unit test — DB is deploy-verified per the repo's test-on-deploy model)

```bash
git add src/services/westland-forms/proposal-schedule-review/supabase-client.js
git commit -m "feat(proposal-review): supabase client (reviews/versions/comments + snapshot blobs)"
```

---

### Task 4: Upload-shape validator + version constants

**Files:**
- Create: `src/services/westland-forms/proposal-schedule-review/schema.js`
- Test: `src/services/westland-forms/proposal-schedule-review/schema.test.js`

**Interfaces:**
- Produces: `SCHEMA_VERSION`, `SCHEMA_DOC_URL`, `validateActivities(obj) → { ok:true, value } | { ok:false, status:400, response }`. Validates the uploaded `schedule-activities.json`: top-level `project` object (with `name`, optional `version`) and a non-empty `activities` array whose items have `task_code` (string) and a numeric duration field. Mirrors the weekly-email `validateSeed` discriminated-result contract.

- [ ] **Step 1: Write failing tests**

```js
// src/services/westland-forms/proposal-schedule-review/schema.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { validateActivities } from "./schema.js";

const good = { project: { name: "Apex", version: 3 },
  activities: [{ id: "1", task_code: "A0010", name: "Mobilize", duration_days: 5 }] };

test("accepts a well-formed activities doc", () => {
  const r = validateActivities(good);
  assert.equal(r.ok, true);
});
test("rejects a non-object", () => {
  assert.equal(validateActivities(null).ok, false);
  assert.equal(validateActivities([]).ok, false);
});
test("rejects missing project.name", () => {
  const r = validateActivities({ project: {}, activities: good.activities });
  assert.equal(r.ok, false);
  assert.equal(r.status, 400);
});
test("rejects empty activities", () => {
  assert.equal(validateActivities({ project: { name: "X" }, activities: [] }).ok, false);
});
test("rejects an activity missing task_code", () => {
  const r = validateActivities({ project: { name: "X" }, activities: [{ id: "1", duration_days: 5 }] });
  assert.equal(r.ok, false);
});
```

- [ ] **Step 2: Run — expect FAIL.** `node --test src/services/westland-forms/proposal-schedule-review/schema.test.js`

- [ ] **Step 3: Implement**

```js
// src/services/westland-forms/proposal-schedule-review/schema.js
export const SCHEMA_VERSION = 1;
export const SCHEMA_DOC_URL = "https://westland-mcps.westland.workers.dev/westland-forms/proposal-schedule-review/schema";

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

export function validateActivities(obj) {
  const violations = [];
  if (!isObj(obj)) return fail([{ path: "", reason: "not_an_object" }]);
  if (!isObj(obj.project)) violations.push({ path: "project", reason: "missing_required" });
  else if (typeof obj.project.name !== "string" || !obj.project.name.trim())
    violations.push({ path: "project.name", reason: "missing_required" });
  if (!Array.isArray(obj.activities) || obj.activities.length === 0)
    violations.push({ path: "activities", reason: "empty_or_missing" });
  else {
    obj.activities.forEach((a, i) => {
      if (!isObj(a)) { violations.push({ path: `activities[${i}]`, reason: "not_an_object" }); return; }
      if (typeof a.task_code !== "string" || !a.task_code.trim())
        violations.push({ path: `activities[${i}].task_code`, reason: "missing_required" });
    });
  }
  if (violations.length) return fail(violations);
  return { ok: true, value: obj };
}
function fail(violations) {
  return { ok: false, status: 400,
    response: { error: "INVALID_ACTIVITIES_SHAPE", version_required: SCHEMA_VERSION, violations, schema_url: SCHEMA_DOC_URL } };
}
```

- [ ] **Step 4: Run — expect PASS.** Same command.

- [ ] **Step 5: Commit**

```bash
git add src/services/westland-forms/proposal-schedule-review/schema.js src/services/westland-forms/proposal-schedule-review/schema.test.js
git commit -m "feat(proposal-review): activities upload validator"
```

---

### Task 5: Publish-mode decision (pure) + version labelling

**Files:**
- Create: `src/services/westland-forms/proposal-schedule-review/publish.js`
- Test: `src/services/westland-forms/proposal-schedule-review/publish.test.js`

**Interfaces:**
- Produces: `decidePublish({ existingReview, requestedVersion, newVersion }) → { versionLabel, mode }` where `mode ∈ {"created","updated","new_version"}`. Rules: no existing review → `{ versionLabel: requestedVersion || "v1", mode: "created" }`. Existing + `newVersion` → `{ versionLabel: requestedVersion || nextV(existing.current_version), mode: "new_version" }`. Existing + not newVersion → `{ versionLabel: requestedVersion || existing.current_version, mode: "updated" }`. `nextV("v3") → "v4"`; `nextV(non-vN) → "v2"`.

- [ ] **Step 1: Write failing tests**

```js
// src/services/westland-forms/proposal-schedule-review/publish.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { decidePublish, nextV } from "./publish.js";

test("nextV increments vN, defaults to v2", () => {
  assert.equal(nextV("v3"), "v4");
  assert.equal(nextV("v1"), "v2");
  assert.equal(nextV("weird"), "v2");
});
test("no review => created v1", () => {
  assert.deepEqual(decidePublish({ existingReview: null }), { versionLabel: "v1", mode: "created" });
});
test("existing + update-in-place keeps current", () => {
  assert.deepEqual(decidePublish({ existingReview: { current_version: "v2" } }),
    { versionLabel: "v2", mode: "updated" });
});
test("existing + new_version bumps", () => {
  assert.deepEqual(decidePublish({ existingReview: { current_version: "v2" }, newVersion: true }),
    { versionLabel: "v3", mode: "new_version" });
});
test("explicit requestedVersion wins", () => {
  assert.deepEqual(decidePublish({ existingReview: { current_version: "v2" }, requestedVersion: "v5", newVersion: true }),
    { versionLabel: "v5", mode: "new_version" });
});
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Implement**

```js
// src/services/westland-forms/proposal-schedule-review/publish.js
export function nextV(label) {
  const m = /^v(\d+)$/.exec(String(label || ""));
  return m ? `v${Number(m[1]) + 1}` : "v2";
}
export function decidePublish({ existingReview, requestedVersion, newVersion }) {
  if (!existingReview) return { versionLabel: requestedVersion || "v1", mode: "created" };
  if (newVersion) return { versionLabel: requestedVersion || nextV(existingReview.current_version), mode: "new_version" };
  return { versionLabel: requestedVersion || existingReview.current_version, mode: "updated" };
}
```

- [ ] **Step 4: Run — expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add src/services/westland-forms/proposal-schedule-review/publish.js src/services/westland-forms/proposal-schedule-review/publish.test.js
git commit -m "feat(proposal-review): pure publish-mode decision"
```

---

### Task 6: The review app (`app/index.html`) + vendored assets + Text rule

**Files:**
- Create: `src/services/westland-forms/proposal-schedule-review/app/index.html`
- Create: `src/services/westland-forms/proposal-schedule-review/app/vendor/frappe-gantt.umd.js` (copy from construction-skills `scheduling/lib/frappe-gantt/frappe-gantt.umd.js`)
- Create: `src/services/westland-forms/proposal-schedule-review/app/vendor/frappe-gantt.css` (copy)
- Modify: `wrangler.toml`

**Interfaces:**
- Produces: a self-contained HTML app served with `{{SIG_QUERY}}`, `{{API_BASE}}`, `{{CURRENT_VERSION}}` placeholders. At runtime it: reads the reviewer-name cookie (prompts if absent, sets `wl_reviewer_name` + `wl_reviewer_id`); fetches `GET {{API_BASE}}/versions/{job}{{SIG_QUERY}}`, `GET .../snapshot/{job}/{version}{{SIG_QUERY}}`, `GET .../comments/{job}?version={version}&...`; renders the P6 grid + Gantt (frappe-gantt) from the snapshot; renders per-task comment chips with author + resolved checkbox; posts new comments (`POST .../comments/{job}`), edits/deletes own, toggles resolved (`PATCH`). Version dropdown navigates `?version=vN`.
- Consumes: the routes from Task 7.

- [ ] **Step 1: Copy the frappe-gantt vendor files from construction-skills into `app/vendor/`.**

```bash
mkdir -p src/services/westland-forms/proposal-schedule-review/app/vendor
cp "/c/Users/camron/code/construction-skills/scheduling/lib/frappe-gantt/frappe-gantt.umd.js" src/services/westland-forms/proposal-schedule-review/app/vendor/
cp "/c/Users/camron/code/construction-skills/scheduling/lib/frappe-gantt/frappe-gantt.css" src/services/westland-forms/proposal-schedule-review/app/vendor/
```

- [ ] **Step 2: Author `app/index.html`.**

Adapt the retired `gantt-review.html` (see the construction-skills plan for the exact regions). Keep: the P6 grid + Gantt render, float coloring, the note popup UI. Replace the feedback machinery: instead of in-memory `comments`/`edits` + Copy-for-Claude/Download-Feedback, the note popup POSTs to the comment API and includes a `suggested_duration_days` numeric input; comments render inline per task (author + version badge + resolved checkbox). Add a version `<select>` populated from `/versions`. Inline frappe-gantt JS + CSS from `vendor/` and the Westland logo (base64). Load the `westland-house-style` skill before finalizing visible copy/branding.

Reviewer identity JS (the net-new cookie logic — include verbatim):

```html
<script>
  const API_BASE = "{{API_BASE}}";
  const SIG = "{{SIG_QUERY}}"; // "?sig=...&exp=..." — append with & for extra params
  const JOB = document.currentScript.dataset ? null : null; // JOB injected below
</script>
```

```js
// reviewer identity (cookie)
function getCookie(name) {
  return document.cookie.split("; ").find((r) => r.startsWith(name + "="))?.split("=")[1];
}
function setCookie(name, val) {
  document.cookie = `${name}=${encodeURIComponent(val)}; path=/; max-age=${60*60*24*365}; SameSite=Lax`;
}
function uuid() {
  return (crypto.randomUUID && crypto.randomUUID()) ||
    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0; return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
}
function ensureReviewer() {
  let name = getCookie("wl_reviewer_name");
  let id = getCookie("wl_reviewer_id");
  if (name) name = decodeURIComponent(name);
  if (!id) { id = uuid(); setCookie("wl_reviewer_id", id); }
  if (!name) {
    name = (window.prompt("Enter your name to review (saved on this device):") || "").trim();
    if (name) setCookie("wl_reviewer_name", name);
  }
  return { name, id };
}
function withSig(path, extra) {
  // SIG is "?sig=...&exp=..."; add extra params with &
  return API_BASE + path + SIG + (extra ? "&" + extra : "");
}
```

Comment fetch/post helpers (verbatim shape the routes expect):

```js
async function loadComments(job, version) {
  const res = await fetch(withSig(`/comments/${encodeURIComponent(job)}`, `version=${encodeURIComponent(version)}`));
  return res.ok ? res.json() : [];
}
async function postComment(job, payload) {
  const res = await fetch(withSig(`/comments/${encodeURIComponent(job)}`), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
// payload = { version_label, task_code, task_name_snapshot, orig_duration_snapshot,
//             reviewer_id, reviewer_name, body, suggested_duration_days }
```

- [ ] **Step 3: Add the Text module rule to `wrangler.toml`** (so the Worker can `import` the html/vendor as strings). Append:

```toml
[[rules]]
type = "Text"
globs = [
  "src/services/westland-forms/proposal-schedule-review/app/index.html",
  "src/services/westland-forms/proposal-schedule-review/app/vendor/frappe-gantt.umd.js",
  "src/services/westland-forms/proposal-schedule-review/app/vendor/frappe-gantt.css",
]
fallthrough = true
```

(If you inline the vendor files directly into `index.html` instead, only the `index.html` glob is needed.)

- [ ] **Step 4: Commit**

```bash
git add src/services/westland-forms/proposal-schedule-review/app wrangler.toml
git commit -m "feat(proposal-review): self-contained review app + Text module rule"
```

---

### Task 7: Routes + mount

**Files:**
- Create: `src/services/westland-forms/proposal-schedule-review/routes.js`
- Modify: `src/services/westland-forms/routes.js`

**Interfaces:**
- Consumes: `verifyRequest` (Task 2), the client (Task 3), `SCHEMA_VERSION`/`SCHEMA_DOC_URL` (Task 4), the Text-imported app (Task 6).
- Produces: `buildProposalScheduleReviewRoutes()` returning a Hono app with the routes listed in the spec. Mounted at `/proposal-schedule-review`.

- [ ] **Step 1: Implement `routes.js`** (mirror the weekly-email `routes.js` `withCtx`/`asHttpError`/HMAC-verify pattern). Import the app as Text:

```js
// src/services/westland-forms/proposal-schedule-review/routes.js
import { Hono } from "hono";
import { verifyRequest, HttpError } from "../shared/hmac.js";
import { westlandFormsCtx } from "../shared/ctx.js";
import { SCHEMA_VERSION, SCHEMA_DOC_URL } from "./schema.js";
import {
  readReview, listVersions, getVersion, readSnapshot,
  listComments, insertComment, updateComment, deleteComment,
} from "./supabase-client.js";
import APP_HTML from "./app/index.html";

function withCtx(h) { return (c) => westlandFormsCtx.run({ env: c.env, email: null, procoreUserId: null }, () => h(c)); }
function asHttpError(c, err) { return err instanceof HttpError ? c.text(err.message, err.status) : c.text(err.message || "internal error", 500); }
function sigQuery(c) {
  const u = new URL(c.req.url);
  const sig = u.searchParams.get("sig"), exp = u.searchParams.get("exp");
  return (sig && exp) ? `?sig=${encodeURIComponent(sig)}&exp=${encodeURIComponent(exp)}` : "";
}
const API_BASE = "/westland-forms/proposal-schedule-review";

export function buildProposalScheduleReviewRoutes() {
  const app = new Hono();

  app.get("/schema.json", (c) => c.json({ schema_version: SCHEMA_VERSION, schema_doc_url: SCHEMA_DOC_URL }));

  app.get("/review/:job", withCtx(async (c) => {
    const job = c.req.param("job");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const review = await readReview(job);
    if (!review) return c.text("review not found", 404);
    const requested = new URL(c.req.url).searchParams.get("version");
    const current = requested || review.current_version;
    const html = APP_HTML
      .replaceAll("{{API_BASE}}", API_BASE)
      .replaceAll("{{SIG_QUERY}}", sigQuery(c))
      .replaceAll("{{CURRENT_VERSION}}", current)
      .replaceAll("{{JOB_NUMBER}}", job)
      .replaceAll("{{PROJECT_NAME}}", (review.project_name || job));
    return c.html(html);
  }));

  app.get("/versions/:job", withCtx(async (c) => {
    const job = c.req.param("job");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const review = await readReview(job);
    const versions = await listVersions(job);
    return c.json(versions.map((v) => ({ ...v, is_current: review && v.version_label === review.current_version })));
  }));

  app.get("/snapshot/:job/:version", withCtx(async (c) => {
    const job = c.req.param("job"), version = c.req.param("version");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const ver = await getVersion(job, version);
    if (!ver) return c.text("version not found", 404);
    const snap = await readSnapshot(ver.snapshot_path);
    if (!snap) return c.text("snapshot missing", 404);
    return c.json(snap);
  }));

  app.get("/comments/:job", withCtx(async (c) => {
    const job = c.req.param("job");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const version = new URL(c.req.url).searchParams.get("version") || undefined;
    return c.json(await listComments(job, version));
  }));

  app.post("/comments/:job", withCtx(async (c) => {
    const job = c.req.param("job");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const b = await c.req.json();
    if (!b || !b.version_label || !b.task_code || !b.reviewer_id || !b.reviewer_name)
      return c.text("missing required comment fields", 400);
    const row = await insertComment({
      job_number: job, version_label: b.version_label, task_code: b.task_code,
      task_name_snapshot: b.task_name_snapshot ?? null,
      orig_duration_snapshot: b.orig_duration_snapshot ?? null,
      reviewer_id: b.reviewer_id, reviewer_name: b.reviewer_name,
      body: b.body ?? null, suggested_duration_days: b.suggested_duration_days ?? null,
      resolved: false,
    });
    return c.json(row);
  }));

  app.patch("/comments/:job/:id", withCtx(async (c) => {
    const job = c.req.param("job"), id = c.req.param("id");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const b = await c.req.json();
    const patch = {};
    if (typeof b.resolved === "boolean") { patch.resolved = b.resolved; patch.resolved_by = b.reviewer_name || null; patch.resolved_at = b.resolved ? new Date().toISOString() : null; }
    if (typeof b.body === "string" || b.suggested_duration_days !== undefined) {
      // edit own comment only
      const existing = (await listComments(job)).find((r) => r.id === id);
      if (!existing) return c.text("comment not found", 404);
      if (existing.reviewer_id !== b.reviewer_id) return c.text("cannot edit another reviewer's comment", 403);
      if (typeof b.body === "string") patch.body = b.body;
      if (b.suggested_duration_days !== undefined) patch.suggested_duration_days = b.suggested_duration_days;
    }
    if (!Object.keys(patch).length) return c.text("nothing to update", 400);
    return c.json(await updateComment(id, patch));
  }));

  app.delete("/comments/:job/:id", withCtx(async (c) => {
    const job = c.req.param("job"), id = c.req.param("id");
    try { await verifyRequest(c.env, c.req.raw, { parts: [job] }); } catch (e) { return asHttpError(c, e); }
    const b = await c.req.json().catch(() => ({}));
    const existing = (await listComments(job)).find((r) => r.id === id);
    if (!existing) return c.text("comment not found", 404);
    if (existing.reviewer_id !== b.reviewer_id) return c.text("cannot delete another reviewer's comment", 403);
    await deleteComment(id);
    return c.json({ ok: true });
  }));

  return app;
}
```

- [ ] **Step 2: Mount in `src/services/westland-forms/routes.js`** — add the import + one `app.route` line beside the existing weekly-email mount (line ~34):

```js
import { buildProposalScheduleReviewRoutes } from "./proposal-schedule-review/routes.js";
// ...inside buildWestlandFormsRoutes(), after the weekly-email mount:
app.route("/proposal-schedule-review", buildProposalScheduleReviewRoutes());
```

- [ ] **Step 3: Commit**

```bash
git add src/services/westland-forms/proposal-schedule-review/routes.js src/services/westland-forms/routes.js
git commit -m "feat(proposal-review): Hono routes (serve app + snapshot + versions + comments) + mount"
```

---

### Task 8: MCP tools + registration

**Files:**
- Create: `src/services/westland-forms/proposal-schedule-review/tools/generate-proposal-review-link.js`
- Create: `.../tools/get-proposal-review-comments.js`
- Create: `.../tools/get-proposal-review-status.js`
- Create: `.../tools/index.js`
- Modify: `src/services/westland/agent.js` (LIVE path), `src/services/westland-forms/agent.js` (mirror)

**Interfaces:**
- Consumes: `getEnv`/`getEmail` (ctx), `signUrl` (Task 2), the client (Task 3), `validateActivities` (Task 4), `decidePublish` (Task 5).
- Produces three default-export tool objects + `{ tools, toolsByName }`.

- [ ] **Step 1: `generate-proposal-review-link.js`**

```js
import { getEnv, getEmail } from "../../shared/ctx.js";
import { signUrl } from "../../shared/hmac.js";
import { validateActivities } from "../schema.js";
import { decidePublish } from "../publish.js";
import { readReview, upsertReview, insertVersion, getVersion, uploadSnapshot } from "../supabase-client.js";

const DEFAULT_BASE_URL = "https://westland-mcps.westland.workers.dev";

export default {
  name: "generate_proposal_review_link",
  description: "Publish (or update) a proposal schedule to the online review page and return a shareable link. Pass the project's schedule-activities.json as activities_json. Omit new_version to update the current version in place (comments preserved); pass new_version:true to cut a new version with a clean comment slate.",
  annotations: { title: "proposal review: publish + link", readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  inputSchema: {
    type: "object",
    required: ["job_number", "activities_json"],
    additionalProperties: false,
    properties: {
      job_number: { type: "string", description: "Westland job number, e.g. W1234." },
      project_name: { type: "string" },
      activities_json: { type: "object", description: "The schedule-activities.json contents.", additionalProperties: true },
      new_version: { type: "boolean", description: "Cut a new version (freeze current, clean slate)." },
      version_label: { type: "string", description: "Explicit version label; defaults to auto." },
    },
  },
  handler: async ({ job_number, project_name, activities_json, new_version, version_label }) => {
    const env = getEnv();
    const email = getEmail();
    const validation = validateActivities(activities_json);
    if (!validation.ok) { const e = new Error(JSON.stringify(validation.response, null, 2)); e.code = validation.response.error; throw e; }
    const existingReview = await readReview(job_number);
    const { versionLabel, mode } = decidePublish({ existingReview, requestedVersion: version_label, newVersion: new_version });
    const path = await uploadSnapshot(job_number, versionLabel, activities_json);
    if (mode !== "updated" || !(await getVersion(job_number, versionLabel))) {
      await insertVersion({ job_number, version_label: versionLabel, snapshot_path: path, published_by_email: email });
    }
    const name = project_name || existingReview?.project_name || (activities_json.project && activities_json.project.name) || job_number;
    await upsertReview({ job_number, project_name: name, current_version: versionLabel, created_by_email: email });
    const baseUrl = env.PUBLIC_BASE_URL || DEFAULT_BASE_URL;
    const { url, expiresAt } = await signUrl(env, {
      baseUrl,
      path: `/westland-forms/proposal-schedule-review/review/${encodeURIComponent(job_number)}`,
      parts: [job_number],
      expiresInSec: 30 * 24 * 3600,
    });
    return { review_url: url, expires_at: expiresAt, version_label: versionLabel, mode };
  },
};
```

- [ ] **Step 2: `get-proposal-review-comments.js`**

```js
import { getEmail } from "../../shared/ctx.js";
import { readReview, listComments, listVersions } from "../supabase-client.js";
export default {
  name: "get_proposal_review_comments",
  description: "Fetch attributed review comments for a proposal schedule. Returns comments (optionally filtered to one version) with reviewer name, version, suggested duration, and resolved status.",
  annotations: { title: "proposal review: get comments", readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  inputSchema: { type: "object", required: ["job_number"], additionalProperties: false,
    properties: { job_number: { type: "string" }, version_label: { type: "string" } } },
  handler: async ({ job_number, version_label }) => {
    getEmail(); // identity presence check
    const review = await readReview(job_number);
    if (!review) return { job_number, current_version: null, versions: [], comments: [] };
    const versions = await listVersions(job_number);
    const comments = await listComments(job_number, version_label);
    return { job_number, current_version: review.current_version,
      versions: versions.map((v) => v.version_label), comments };
  },
};
```

- [ ] **Step 3: `get-proposal-review-status.js`**

```js
import { getEmail } from "../../shared/ctx.js";
import { readReview, listVersions, listComments } from "../supabase-client.js";
export default {
  name: "get_proposal_review_status",
  description: "Summarize a proposal schedule review: versions, per-version comment counts, unresolved count, and distinct reviewers.",
  annotations: { title: "proposal review: status", readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  inputSchema: { type: "object", required: ["job_number"], additionalProperties: false, properties: { job_number: { type: "string" } } },
  handler: async ({ job_number }) => {
    getEmail();
    const review = await readReview(job_number);
    if (!review) return { job_number, exists: false };
    const versions = await listVersions(job_number);
    const all = await listComments(job_number);
    const byVersion = {};
    for (const v of versions) byVersion[v.version_label] = 0;
    let unresolved = 0; const reviewers = new Set();
    for (const cmt of all) { byVersion[cmt.version_label] = (byVersion[cmt.version_label] || 0) + 1; if (!cmt.resolved) unresolved++; reviewers.add(cmt.reviewer_name); }
    return { job_number, exists: true, current_version: review.current_version,
      versions: versions.map((v) => v.version_label), comment_counts: byVersion, unresolved, reviewers: [...reviewers] };
  },
};
```

- [ ] **Step 4: `tools/index.js`**

```js
import generate from "./generate-proposal-review-link.js";
import getComments from "./get-proposal-review-comments.js";
import getStatus from "./get-proposal-review-status.js";
export const tools = [generate, getComments, getStatus];
export const toolsByName = Object.fromEntries(tools.map((t) => [t.name, t]));
```

- [ ] **Step 5: Register in `src/services/westland/agent.js`** — add the import beside the forms-tools import (~L28-31) and extend the spreads (L41-42):

```js
import { tools as reviewTools, toolsByName as reviewToolsByName }
  from "../westland-forms/proposal-schedule-review/tools/index.js";
// ...
const allTools = [...formsTools, ...reviewTools, ...internalTools];
const allToolsByName = { ...formsToolsByName, ...reviewToolsByName, ...internalToolsByName };
```

- [ ] **Step 6: Mirror in `src/services/westland-forms/agent.js`** (L15-16):

```js
import { tools as reviewTools, toolsByName as reviewToolsByName } from "./proposal-schedule-review/tools/index.js";
const allTools = [...weeklyScheduleUpdateEmailTools, ...reviewTools];
const allToolsByName = { ...toolsByName, ...reviewToolsByName };
```

- [ ] **Step 7: Run the full test suite — expect PASS** (unit tests + module-load duplicate-name guard in agent.js).

Run: `node --test`
Expected: all pass; no "duplicate tool name" throw at import.

- [ ] **Step 8: Commit**

```bash
git add src/services/westland-forms/proposal-schedule-review/tools src/services/westland/agent.js src/services/westland-forms/agent.js
git commit -m "feat(proposal-review): MCP tools (generate link, get comments, status) + registration"
```

---

### Task 9: Schema doc endpoint text + README pointer

**Files:**
- Modify: `src/services/westland-forms/proposal-schedule-review/routes.js` (add `GET /schema` returning a short markdown contract)
- Modify: `README.md` (add the new sub-service + tables to the westland-forms section)

- [ ] **Step 1: Add `GET /schema`** returning `text/markdown` describing the accepted `activities_json` shape (project.name/version + activities[].task_code/duration_days), the routes, and the comment model. Mirror the weekly-email `/schema` pattern (public, no auth needed for the doc).

- [ ] **Step 2: Update `README.md`** westland-forms/Supabase tables list to include `wnd_proposal_reviews`, `wnd_proposal_review_versions`, `wnd_proposal_review_comments` + the `wnd-proposal-review` bucket.

- [ ] **Step 3: Commit**

```bash
git add src/services/westland-forms/proposal-schedule-review/routes.js README.md
git commit -m "docs(proposal-review): schema endpoint + README tables"
```

---

## Self-Review (run after all tasks)

- Every route HMAC-verifies with `parts:[job]`; the app never calls `getEmail()` (routes pass `email:null`).
- Tool names disjoint from existing (`generate_proposal_review_link`/`get_proposal_review_comments`/`get_proposal_review_status` — no collision with forms/internal).
- `signUrl`/`verifyRequest` payload equals the old editor payload for `parts=[project,reportDate]` (backward compat).
- Bundle size after adding frappe-gantt as Text: check `wrangler deploy --dry-run --outdir /tmp/wm-build` output stays within limits (checkpoint; if tight, fall back to Storage-hosted app files).
- Migration applied + bucket created before first real publish.
