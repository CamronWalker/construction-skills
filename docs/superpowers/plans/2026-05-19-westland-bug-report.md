# Westland Bug Report — Implementation Plan

**Spec:** [2026-05-19-westland-bug-report-design.md](../specs/2026-05-19-westland-bug-report-design.md)

**Two repos / two PRs:**
- `C:\Users\camron\code\westland-mcps` — adds `/feedback/mcp` service
- `C:\Users\camron\code\construction-skills\.claude\worktrees\tender-villani-5419d4` — adds `westland-bug-report` skill (worktree of `construction-skills`)

## Execution order

```
[1: DB migration]
        │
        ▼
[2: feedback MCP service] ─► [3: wire into router] ─► [4: set secrets + deploy]
                                                              │
                                                              ▼
                                                      [5: smoke test endpoint]
                                                              │
                                  ┌───────────────────────────┘
                                  ▼
                          [6: westland-bug-report skill]
                                  │
                                  ▼
                    [7: version bumps (plugin + marketplace)]
                                  │
                                  ▼
                 [8: commit + PR — both repos in parallel]
```

## Step 1 — Apply DB migration (Supabase MCP)

**Tool:** `apply_migration`.

**Migration name:** `create_wnd_bug_reports`.

**SQL:** as in spec section A (table + 4 indexes + RLS enable, no policies).

**Verification:**
1. `list_tables` confirms `public.wnd_bug_reports` exists with `rls_enabled: true`.
2. Test insert + delete via `execute_sql` (service role bypasses RLS).

## Step 2 — Build feedback MCP service

In `C:\Users\camron\code\westland-mcps`.

### 2a. `src/services/feedback/ctx.js`
AsyncLocalStorage holding `{ env, email, procoreUserId }`. Same shape as `services/smartpm/ctx.js` minus the company-specific helpers. Export `feedbackCtx`, `getCtx`, `getEnv`, `getEmail`.

### 2b. `src/services/feedback/supabase-client.js`
Two functions, both using stdlib `fetch`:
- `insertBugReport(row)` — POST `${SUPABASE_URL}/rest/v1/wnd_bug_reports` with the row body. Headers: `apikey: <SUPABASE_SERVICE_ROLE_KEY>`, `Authorization: Bearer <same>`, `Content-Type: application/json`, `Prefer: return=representation`. Returns the inserted row.
- `listMyReports({ email, status, limit = 25 })` — GET `${SUPABASE_URL}/rest/v1/wnd_bug_reports?user_email=eq.<email>&order=created_at.desc&limit=<n>` (+ optional `status=eq.<status>`).
- `countRecentReports(email)` — GET with `select=count` and `created_at=gt.<now-1h>` for the rate-limit check.

Validation helpers:
- `requireSecrets(env)` — assert `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` are set.
- `trimField(s, 16384)` — cap to 16 KB, append `…[truncated]` if cut.

### 2c. `src/services/feedback/agent.js`
Mirror `services/smartpm/agent.js`:
- `createFeedbackHandler()` returning `{ fetch }`.
- Per request: build Server (name `westland-feedback`, version `0.1.0`), register `ListTools` + `CallTool` handlers, build transport, `server.connect`, then `feedbackCtx.run({env, email: props.email, procoreUserId: props.procoreUserId}, () => transport.handleRequest(request))`.

### 2d. `src/services/feedback/tools/submit-bug-report.js`
- Input schema as in spec section B.
- Handler:
  1. Pull `email` from ctx.
  2. Check non-empty `title`, `severity`, `what_went_wrong`.
  3. Rate-limit: `await countRecentReports(email)`; if >= 30 throw.
  4. Build row: `{...trimmed args, user_email: email, status: 'new', environment: args.environment || {}}`.
  5. `insertBugReport(row)`.
  6. Return `{ id, created_at, status, title }`.

### 2e. `src/services/feedback/tools/feedback-whoami.js`
- No inputs.
- Returns `{ email, procoreUserId }` from ctx.

### 2f. `src/services/feedback/tools/list-my-reports.js`
- Inputs: `{ status?: enum, limit?: number (default 25, max 100) }`.
- Calls `listMyReports({ email: getEmail(), status, limit })`.

### 2g. `src/services/feedback/tools/index.js`
- Export `tools` array + `toolsByName` map.

### 2h. `src/services/feedback/CLAUDE.md`
- Brief service-level docs: purpose, federation pattern, table layout pointer, tool list.

## Step 3 — Wire feedback into router

### `src/oauth/consent.js`
Add to the resource→service mapping:
```js
else if (resource.endsWith("/feedback/mcp")) service = "feedback";
```
Add to the identity-only branch:
```js
const target = (service === "procore" || service === "smartpm" || service === "buildr" || service === "feedback")
  ? buildProcoreAuthorize(env, request, state)
  : buildBcAuthorize(env, request, state);
```

### `src/oauth/upstream/procore.js`
Two changes:
1. The `seedTokens` guard becomes "skip if identity-only service":
   ```js
   if (service === "procore") { await seedTokens(...); }
   ```
   (already correct — extend the comment to include `feedback`).
2. The `props` shape branch — extend the identity-only list:
   ```js
   const props = (service === "smartpm" || service === "buildr" || service === "feedback")
     ? { email, procoreUserId: workerUserId }
     : { workerUserId, email };
   ```

### `src/index.js`
1. `import { createFeedbackHandler } from "./services/feedback/agent.js";`
2. Add `"/feedback/mcp": createFeedbackHandler()` to `apiHandlers`.
3. Add `"feedback"` to the `for (const svc of [...])` protected-resource loop.
4. Update `LANDING_HTML` connectors list: add `<li><strong>Feedback</strong> &mdash; <code>/feedback/mcp</code></li>`.
5. Bump `package.json` version `0.1.0` → `0.2.0`.

## Step 4 — Set secrets + deploy

```powershell
cd C:\Users\camron\code\westland-mcps
npx wrangler secret put SUPABASE_URL
# paste: https://anwdfilrfczluhudtbzw.supabase.co
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
# paste: <service role key from Supabase dashboard>
npx wrangler deploy
```

**Note:** Camron must paste secrets interactively. The skill spec calls out the **value-only paste** gotcha (no `KEY=`).

If Camron isn't available to paste the secrets, the deploy can still go up (the handler will throw `"SUPABASE_URL is not configured"` on first call, which is graceful). The PR description will flag the manual step.

## Step 5 — Smoke test

After deploy:

```powershell
# Connector metadata reachable
curl https://westland-mcps.westland.workers.dev/.well-known/oauth-protected-resource/feedback/mcp

# Endpoint requires auth (401 with WWW-Authenticate)
curl -i https://westland-mcps.westland.workers.dev/feedback/mcp

# Landing page lists the connector
curl https://westland-mcps.westland.workers.dev/ | grep -i feedback
```

Live tool test (post-connector-install):
- Call `feedback_whoami` → expect `{ email: "camron@westlandconstruction.com", procoreUserId: "..." }`.
- Call `submit_bug_report` with a SMOKE TEST payload → expect a row ID.
- `execute_sql` confirms the row, then deletes it.

If Camron hasn't connected the new connector yet, smoke test stops at the curl HTTP checks. The PR description includes the install steps.

## Step 6 — Build skill

In the construction-skills worktree (`tender-villani-5419d4`).

### Files

```
westland/skills/westland-bug-report/
  SKILL.md
  references/
    schema.sql              # reference copy
    mcp-tool-shapes.md      # tool input/output reference
```

### `SKILL.md` outline (~150 lines)

1. **YAML frontmatter:** `name`, `description` with all triggers.
2. **What this skill does** — 2 sentences.
3. **Triggers** — bullet list.
4. **Prerequisite: westland-feedback connector.** Document Settings → Connectors → Add → `https://westland-mcps.westland.workers.dev/feedback/mcp`. Tell the user the skill will prompt them to install if missing.
5. **Flow** — numbered steps 1–10 mirroring spec C.
6. **Field guidance:**
   - Severity rubric (low/medium/high/critical)
   - How to summarize the conversation (≤2 KB, last ~10 exchanges)
   - How to detect `skill_or_tool` (look for `/<skill-name>` invocations, recent skill names in conversation, files touched)
7. **Environment capture** — exact PowerShell + bash command equivalents.
8. **Preview template** — markdown the model produces for the terminal preview.
9. **Submitting** — call `mcp__westland-feedback__submit_bug_report` with the JSON args (NOT a curl).
10. **Error handling** — if `isError: true`, show the message; ask to retry or abandon.
11. **What NOT to do** — listed in spec C.

### `references/schema.sql`
Copy of the CREATE TABLE statement, for humans reading the skill source later.

### `references/mcp-tool-shapes.md`
Tool input/output schemas as documentation. The skill SKILL.md doesn't re-quote them — readers can refer here.

## Step 7 — Version bumps

### Plugin (construction-skills)
- `westland/.claude-plugin/plugin.json`: `1.3.1` → `1.4.0`. Also update `description` to mention the bug-report skill briefly.
- `.claude-plugin/marketplace.json`: matching westland entry to `1.4.0` with matching description.

### Worker (westland-mcps)
- `package.json`: `0.1.0` → `0.2.0`.

## Step 8 — Commit + open PRs

### PR 1 — westland-mcps

Branch: `feat/feedback-mcp-service`

Files:
- `src/services/feedback/` (all)
- `src/oauth/consent.js` (modified)
- `src/oauth/upstream/procore.js` (modified)
- `src/index.js` (modified — landing page, apiHandlers, protected-resource loop)
- `package.json` (modified — version)
- `docs/superpowers/specs/2026-05-19-feedback-mcp-design.md` (new — short spec specific to the MCP)

Commit message:
```
feat(feedback): add /feedback/mcp service for bug reports — v0.2.0

New MCP service that accepts bug reports from Westland users and writes
them to wnd_bug_reports in the Power BI Sync Supabase project. Uses the
existing Procore-OAuth identity-federation pattern (no data scope).
Service-role Supabase key stays on the Worker; user_email is stamped
server-side from the verified OAuth identity.

Tools: submit_bug_report, feedback_whoami, list_my_reports.

Requires new secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
```

PR title: `feat(feedback): /feedback/mcp service for bug reports`

PR body: design summary, secrets-required note, connector-install instructions, link to construction-skills companion PR.

### PR 2 — construction-skills

Branch: already `claude/tender-villani-5419d4`.

Files:
- `westland/skills/westland-bug-report/` (all)
- `westland/.claude-plugin/plugin.json` (version + description)
- `.claude-plugin/marketplace.json` (version + description)
- `docs/superpowers/specs/2026-05-19-westland-bug-report-design.md`
- `docs/superpowers/plans/2026-05-19-westland-bug-report.md`

Commit message:
```
feat(westland): add westland-bug-report skill — v1.4.0

Captures bugs from inside any Claude Code session, drafts a structured
report from conversation context, and submits via the new
westland-feedback MCP connector (gated by Procore OAuth, writes to
wnd_bug_reports in Supabase).

Companion PR: westland-mcps#<TBD>
```

PR title: `feat(westland): westland-bug-report skill — Procore-gated Supabase bug capture`

PR body: design summary, connector-install instructions, link to westland-mcps companion PR.

## Risk register

| Risk | Mitigation |
|------|-----------|
| OAuth flow breaks because identity-federation branches missed `feedback` | Plan step 3 explicitly extends consent.js and procore.js; smoke test step 5 verifies 401 on the endpoint. |
| Supabase secrets not pasted on first deploy | Handler throws a graceful `"SUPABASE_URL is not configured"`; PR description flags the manual step. |
| Pre-commit hook trips (plugin + marketplace version mismatch) | Plan step 7 bumps both in one commit. |
| Service role key leaks into a log | All Supabase fetches happen inside the Worker; no client receives the key. Worker logs would only show the URL hostname. |
| Rate-limit query is slow at scale | New `(user_email, created_at desc)` index covers the lookup. v1 traffic is low. |
| Connector install friction blocks adoption | The skill prompts with exact install steps when whoami fails. One-time setup; mirrors SmartPM/Buildr. |

## Subagent dispatch

I considered splitting into two parallel agents (one for westland-mcps, one for construction-skills). Decided against it:
- Both depend on the table existing and the MCP tool shape being settled.
- One author maintains schema coherence (skill ↔ MCP tool input shape ↔ table columns).
- Cost of context-switching between two repos in one session is low.

If timing becomes an issue, the construction-skills skill is the cleanly-delegatable piece — its only external dependency is the deployed MCP, which it documents.
