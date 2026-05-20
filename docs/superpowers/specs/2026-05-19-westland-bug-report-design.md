# Westland Bug Report — Design

**Date:** 2026-05-19
**Skill:** `westland:westland-bug-report` (new, in `construction-skills`)
**Service:** `/feedback/mcp` (new, in `westland-mcps`)
**Status:** Design — implementation in progress

## Problem

When a Westland skill or tool misbehaves mid-conversation, there's nowhere to report it. The lessons-learned doc convention (per `construction-skills/CLAUDE.md`) captures major divergences after the fact, but daily friction — wrong fields, confusing prompts, scripts that fail on a particular path — falls through the cracks. By the time Camron sits down to a "skill improvement session," the specific reproduction is lost.

A skill that captures the bug *in the moment*, structures it, and persists it to a queryable database would close that loop. The goal is friction-free reporting from inside the conversation that already hit the bug — *with verified Westland identity*, so the report carries a trustworthy `user_email` and can't be flooded by anyone who finds the endpoint.

## Goals

1. **One-shot bug capture from inside any Claude Code session.** User says "westland-bug-report this"; the skill reconstructs the failure from the current conversation, drafts a structured report, shows a preview, submits on confirmation.
2. **Persist to Supabase** (`Power BI Sync Database`, project `anwdfilrfczluhudtbzw`) so future improvement sessions can query the backlog by skill / severity / date.
3. **Westland-only identity** via Procore OAuth (same federation pattern as SmartPM / Buildr — no Procore data scope exercised).
4. **Zero-credential install** for the skill side. The skill calls an authenticated MCP tool; the auth is the user's existing Procore sign-in to the Westland MCPs Worker.
5. **Server-side validation** so junk doesn't pollute the table.
6. **Useful triage fields.** Capture skill/tool, what went wrong, suggested fix — enough that a future "fix this bug" session has reproduction context.

## Non-Goals

- **Anonymous submission.** Camron's first instinct was an open endpoint; on reflection (mid-conversation 2026-05-19) we agreed to gate via Procore identity so `user_email` is trustworthy and rate limiting is per-identity, not per-IP.
- **File attachments / screenshots.** Text-only for v1. Paste error text into the description.
- **Status workflow inside the skill.** Table has a `status` column; v1 only writes `new`. Triage happens in Supabase dashboard or a future skill.
- **Notification on submit.** No Slack/email ping. Camron will query the table when he's ready to triage.
- **Cross-conversation deduplication.** Duplicates are fine; collapse at triage time.
- **Reading old reports from the skill side.** A `feedback_list_my_reports` MCP tool exists for self-service inspection, but the skill itself is submit-only for v1.

## Approach

### A. Storage — `wnd_bug_reports` table (Supabase project `anwdfilrfczluhudtbzw`)

Follows the existing `wnd_` prefix convention (`wnd_schedule_updates`). RLS enabled with **no public policies** — only the Worker (using its service-role key) inserts. Anon clients see zero rows; the `apikey` header alone can't write either.

```sql
create table public.wnd_bug_reports (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  -- Core
  title           text not null,
  severity        text not null check (severity in ('low','medium','high','critical')),
  skill_or_tool   text,                       -- e.g. 'scheduling:schedule-update' or 'propsched iterate'
  what_went_wrong text not null,
  suggested_fix   text,
  -- Repro context
  repro_steps     text,
  expected_behavior text,
  actual_behavior text,
  conversation_summary text,                  -- bounded synthesis of the conversation
  -- Environment
  environment     jsonb,                      -- {os, plugin_versions:{...}, model, claude_code_version, cwd}
  user_email      text not null,              -- ALWAYS stamped server-side from ctx.props.email
  -- Triage
  status          text not null default 'new' check (status in ('new','triaged','in_progress','fixed','wont_fix','duplicate')),
  triage_notes    text,
  triaged_at      timestamptz,
  triaged_by      text
);

create index on public.wnd_bug_reports (created_at desc);
create index on public.wnd_bug_reports (status, created_at desc);
create index on public.wnd_bug_reports (skill_or_tool);
create index on public.wnd_bug_reports (user_email, created_at desc);

alter table public.wnd_bug_reports enable row level security;
-- No policies: service-role bypasses RLS; anon / authenticated roles see / write nothing.
```

### B. Endpoint — `/feedback/mcp` (new service in `westland-mcps`)

A new MCP service in the existing Cloudflare Worker monorepo, following the **SmartPM / Buildr identity-federation pattern**:

- Sign-in goes through Procore OAuth (`/oauth/upstream/procore/callback`) with `service = "feedback"`.
- Procore's `/me` provides the email; `requireWestlandEmail()` enforces `@westlandconstruction.com` + allowlist.
- No Procore data scope is exercised — Procore is the identity provider only. `seedTokens()` is skipped.
- `props = { email, procoreUserId }` are delivered to the feedback handler via `ctx.props`.
- Worker holds Supabase credentials as secrets (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) and inserts via the Supabase REST API.

#### Files

```
src/services/feedback/
  agent.js                # createFeedbackHandler() — Server + streamable transport + ctx.run
  ctx.js                  # AsyncLocalStorage: { env, email, procoreUserId }
  supabase-client.js      # insertBugReport, listMyReports — fetch against ${SUPABASE_URL}/rest/v1
  tools/
    submit-bug-report.js
    feedback-whoami.js
    list-my-reports.js
    index.js              # tools + toolsByName
  CLAUDE.md               # service docs
```

#### Wiring

- `src/oauth/consent.js`: route `/feedback/mcp` resource to Procore upstream as identity-only.
- `src/oauth/upstream/procore.js`: extend the identity-only branch to include `service === "feedback"`. Skip `seedTokens()`. Set `props = { email, procoreUserId }`.
- `src/index.js`: import `createFeedbackHandler`, register `"/feedback/mcp"` in `apiHandlers`, add `"feedback"` to the protected-resource metadata loop, add a row to the landing-page connectors list.

#### Tools

**`submit_bug_report`** — primary write tool.

Input schema:
```json
{
  "type": "object",
  "required": ["title", "severity", "what_went_wrong"],
  "additionalProperties": false,
  "properties": {
    "title":             { "type": "string", "maxLength": 200 },
    "severity":          { "type": "string", "enum": ["low","medium","high","critical"] },
    "skill_or_tool":     { "type": "string", "maxLength": 200 },
    "what_went_wrong":   { "type": "string" },
    "suggested_fix":     { "type": "string" },
    "repro_steps":       { "type": "string" },
    "expected_behavior": { "type": "string" },
    "actual_behavior":   { "type": "string" },
    "conversation_summary": { "type": "string" },
    "environment":       { "type": "object" }
  }
}
```

Handler behavior:
1. Validate required fields non-empty (schema enforces presence; check non-empty strings).
2. Trim each text field to 16 KB (append `…[truncated]` marker).
3. Build insert row: client payload + `user_email` from `ctx.props.email` (overwrite if client sent one) + `status='new'`.
4. Insert via `${SUPABASE_URL}/rest/v1/wnd_bug_reports` with `apikey` + `Authorization: Bearer <service_role>` + `Prefer: return=representation`.
5. Return `{ id, created_at, status, title }`.
6. On Supabase error: throw — the MCP layer turns it into an `isError: true` content block.

**Rate limit**: per-identity, 30 inserts/hour. Implemented as a pre-insert `select count(*)` against `wnd_bug_reports where user_email = <ctx.email> and created_at > now() - interval '1 hour'`. >= 30 → throw `"Rate limit: you've submitted 30 reports in the last hour. Slow down."` Permissive on purpose; Westland-only audience.

**`feedback_whoami`** — debugging aid, returns `{ email, procoreUserId }` from the authenticated context. Useful when the skill wants to confirm the connector is wired.

**`list_my_reports`** — read-only, last 25 reports for the caller, ordered by `created_at desc`. Optional `status` filter. Filters server-side by `user_email = ctx.email`.

### C. Skill — `westland/skills/westland-bug-report/`

```
westland/skills/westland-bug-report/
  SKILL.md                              # ~150 lines, router style
  references/
    schema.sql                          # reference copy of the migration
    mcp-tool-shapes.md                  # input/output shapes for the three tools
```

**No `submit.py`.** The skill calls the MCP tool directly via the standard `mcp__<connector>__<tool>` invocation that Claude Code routes to the connected MCP server. The skill source carries no HTTP client and no URL.

**SKILL.md flow** (numbered):

1. **Triggers:** "bug report", "report a bug", "westland-bug-report", "this skill is broken", "log a bug", "submit feedback", "/westland-bug-report".
2. **Verify connector.** Try `mcp__westland-feedback__feedback_whoami`. If it errors (not connected / not signed in), show the install instructions (Settings → Connectors → Add custom connector → `https://westland-mcps.westland.workers.dev/feedback/mcp`) and stop.
3. **Gather context.** Synthesize from the current conversation:
   - `skill_or_tool` — most recent skill or tool the user was using
   - `what_went_wrong` — the failure mode in user-facing language
   - `repro_steps` — concrete steps from the conversation
   - `expected_behavior` / `actual_behavior`
   - `conversation_summary` — ≤2 KB, last ~10 relevant exchanges
4. **Draft a `suggested_fix`** — one-paragraph hypothesis. Even low-confidence drafts are useful at triage time.
5. **Capture environment** — `{ os, plugin_versions, model, claude_code_version, cwd }`. Best-effort; missing fields are OK.
6. **Show preview** — render the payload as a markdown report. Prompt: `Submit? yes / edit <field>: <value> / cancel`.
7. **Iterate edits** as user provides them. Re-render after each.
8. **Submit** — call `mcp__westland-feedback__submit_bug_report` with the payload (no `user_email` — server stamps it).
9. **Report receipt** — show the row ID and `created_at`. Done.
10. **Error handling** — if the MCP returns `isError`, show the message and offer retry.

**What NOT to do** (explicit in SKILL.md):
- Don't submit without preview.
- Don't include secrets / credentials in any field.
- Don't fabricate `skill_or_tool` if the conversation is ambiguous — leave it blank or describe in `what_went_wrong`.
- Don't submit on the user's behalf without explicit "yes."

### D. Security model

- **Westland-only writes.** Procore OAuth + email allowlist gate the entire `/feedback/mcp` endpoint. Anyone outside `@westlandconstruction.com` (or the explicit allowlist) gets bounced at upstream callback time.
- **User identity is trustworthy.** `user_email` is set server-side from `ctx.props.email` (Procore-verified). The client cannot forge it.
- **Service role key never leaves the Worker.** It lives in `wrangler secret`; the MCP tool's handler reads it from `env`.
- **RLS denies anon access.** Even the URL of the table is irrelevant — without service-role, no rows visible.
- **Rate limit by identity** (not IP) — 30/hour. Generous; abuse is low-risk since the audience is bounded.
- **No raw SQL exposed.** The MCP tool accepts a fixed JSON schema; arbitrary inserts/queries aren't possible.

### E. Why MCP and not a vanilla edge function

This was a mid-conversation pivot. The first draft used an unauthenticated Supabase edge function with the URL baked into the plugin. Camron raised the concern that "westland user validation" mattered, and asked about MCP-based gating. The MCP route is strictly better:

- **Auth piggybacks** on the already-deployed Procore OAuth → Worker flow. Zero new identity surface.
- **No baked-in URL secret.** Plugin source carries no credentials.
- **Server-stamped user_email.** Triage by user is reliable.
- **Per-identity rate limits** are meaningful, unlike per-IP for a small fleet.
- **Consistent with the rest of the platform.** SmartPM and Buildr are already federated this way; feedback fits the same mold.

The cost is one extra step for the user — install the `westland-feedback` connector once. That's a one-time browser tab, then forgotten.

### F. Versioning

- **westland-mcps:** package version bumps to `0.2.0` (minor — new service). Internal versioning; no marketplace.
- **westland plugin** (`construction-skills`): `1.3.1` → `1.4.0` (minor — new skill). Both `westland/.claude-plugin/plugin.json` and the matching `.claude-plugin/marketplace.json` entry bump in the same commit (pre-commit hook enforces).

## Open questions / future work

- **`feedback_update_status`** — let triagers set `status='fixed'` etc. from inside Claude. Out of scope for v1; do it via Supabase dashboard.
- **Auto-link to commits.** Future: PR descriptions that mention a row ID auto-mark `status='fixed'` via a CI hook. Out of scope.
- **`feedback_search`** — keyword search across past reports. Out of scope; SQL works for v1.
- **Per-severity routing.** `critical` could ping Camron via Telegram. Skipped because Camron is the only triager and would self-spam.
