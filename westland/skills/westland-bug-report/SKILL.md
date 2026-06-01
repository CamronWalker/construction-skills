---
name: westland-bug-report
description: >
  Capture a bug, friction point, or feature gap in any Westland skill, MCP tool,
  or workflow — from inside the conversation that hit the problem. Drafts a
  structured report from current-conversation context, shows the user a preview,
  and submits via the Westland MCP connector (Procore-OAuth gated,
  writes to Supabase). Trigger on: "bug report", "report a bug",
  "westland-bug-report", "/westland-bug-report", "this skill is broken",
  "this tool is broken", "log a bug", "submit feedback", "file a complaint",
  "/feedback", "this didn't work", "X is broken".
---

# Westland Bug Report

One-shot bug capture from inside a Claude Code session. The skill drafts a structured report from the conversation that hit the problem, shows the user a preview, then submits via the Westland MCP connector. Westland identity is verified server-side (Procore OAuth), so `user_email` is trustworthy and triage-by-user works.

## When to use

- A Westland skill misbehaved or output something wrong (`scheduling:`, `estimating:`, `project-management:`, `site-operations:`, `safety:`, or `westland:`).
- A Westland MCP tool (Procore, BuildingConnected, SmartPM, Buildr, Westland internal tools) returned an error or unexpected shape.
- A workflow felt confusing, a prompt was missing context, or a step was undocumented.
- A feature gap surfaced ("I wish this skill could …").
- Anything you'd want recorded for the next skill-improvement session.

Not for: general Q&A, code questions, or things unrelated to Westland tooling.

## Prerequisite — install the Westland MCP connector

The skill submits via the **Westland MCP** connector (claude.ai-managed). Its tools appear as `mcp__claude_ai_Westland_MCP__*`. If you don't see those tools — or `whoami` errors with "tool not found" / "not connected" / 401 — the connector isn't installed (or you're signed out). Don't fail silently: surface the install steps below and stop until it's added.

**To install:** Settings → Connectors → Add custom connector →
```
https://westland-mcps.westland.workers.dev/westland/mcp
```
Sign in with your `@westlandconstruction.com` Procore account when the browser tab opens. One-time setup; mirrors SmartPM / Buildr. After adding it, the `mcp__claude_ai_Westland_MCP__*` tools become available (you may need to start a new session for them to sync).

## Flow

Follow these steps every time. Do not submit without showing the preview.

### 1. Verify connector

Call `mcp__claude_ai_Westland_MCP__whoami`. Expected response: `{ email: "<user>@westlandconstruction.com", procoreUserId: "...", service: "westland-internal" }`.

If the call errors with "tool not found" or "not connected" / "401" — the connector isn't installed or the user isn't signed in. Show the install instructions above and stop.

### 2. Gather context

Synthesize from the current conversation, not by asking the user every field:

| Field | How to fill |
|---|---|
| `skill_or_tool` | The most recent skill or MCP tool the user was using when the bug surfaced. Look for `/<skill-name>` invocations, recent skill-tool calls, or files touched in a known plugin folder. If genuinely unclear, leave blank and describe in `what_went_wrong`. |
| `what_went_wrong` | The failure in user-facing language. One paragraph. Include the actual error text or unexpected output. |
| `repro_steps` | Concrete steps drawn from the conversation. Number them. |
| `expected_behavior` | What the user (or you) expected. |
| `actual_behavior` | What actually happened. |
| `conversation_summary` | Bounded synthesis of the last ~10 relevant exchanges. ≤2 KB. Trim ruthlessly — only the parts that bear on the bug. |
| `severity` | See rubric below. |
| `suggested_fix` | Your hypothesis for what would fix it. Low-confidence drafts are fine and useful at triage time. |

**Severity rubric:**
- `low` — cosmetic, doesn't block work (wording, formatting, missing label).
- `medium` — annoying but a workaround exists (script needs a flag the docs don't mention, slow but functional).
- `high` — blocks the user's task on this run (skill crashes, MCP tool returns wrong data, can't proceed).
- `critical` — data loss, security exposure, or wrong output that could leave Westland's premises (RFI sent with wrong number, schedule published with bad logic).

### 3. Capture environment

Best-effort. Missing fields are OK.

```python
# Run from a Python or PowerShell cell:
import platform, json
print(json.dumps({"os": platform.platform(), "python": platform.python_version()}))
```

PowerShell alternative for OS:
```powershell
[PSCustomObject]@{ os = "$([System.Environment]::OSVersion.VersionString)"; cwd = (Get-Location).Path } | ConvertTo-Json -Compress
```

Plugin versions — grep each plugin's `plugin.json` (Westland marketplace is at `C:\Users\<user>\code\construction-skills\.claude-plugin\marketplace.json` for local installs; for enterprise zip installs the path differs but the same JSON shape applies):

```bash
# Pick what you can read; skip missing ones quietly.
grep -E '"name"|"version"' .claude-plugin/marketplace.json
```

Assemble into `environment`:
```json
{
  "os": "...",
  "model": "claude-opus-4-7[1m]",          // from your current model context if known
  "claude_code_version": "...",            // CLI build, if known
  "cwd": "...",                            // current working directory
  "plugin_versions": {"westland":"1.4.1","scheduling":"5.3.0", "...":"..."}
}
```

### 4. Draft the suggested_fix

One short paragraph. State your hypothesis even if uncertain. Examples:

- "Likely the parse_email_html.py script doesn't handle UNC paths — add a path-normalization step before opening."
- "The MCP tool's input schema may be missing the `filters[status][]` array form; check the URL-builder in client.js."
- "Probably a missing await on the Procore upload — the test row never reaches the table before the response is sent."

### 5. Show preview

Render the full payload as a markdown report in the terminal. Use this template:

```
**Westland bug report — preview**

**Title:** {title}
**Severity:** {severity}
**Skill / tool:** {skill_or_tool}

**What went wrong**
{what_went_wrong}

**Repro steps**
{repro_steps}

**Expected**
{expected_behavior}

**Actual**
{actual_behavior}

**Conversation summary**
{conversation_summary}

**Suggested fix**
{suggested_fix}

**Environment**
```json
{environment as pretty JSON}
```

---
Submit? Reply `yes` to send, `edit <field>: <new value>` to change a field, or `cancel` to abandon.
```

### 6. Iterate edits

If the user replies `edit <field>: <new value>`, update the payload and re-render the preview. Loop until `yes` or `cancel`.

### 7. Submit

Call `mcp__claude_ai_Westland_MCP__submit_bug_report` with the payload. **Do not include `user_email`** in the arguments — the MCP stamps it server-side from the Procore-verified identity. Anything you pass is overwritten.

### 8. Report receipt

On success the tool returns `{ id, created_at, status, title, user_email }`. Show the row ID to the user:

```
Report submitted.
- ID: {id}
- Submitted at: {created_at}
- As: {user_email}
- Status: new

Track triage in the Supabase dashboard or via `mcp__claude_ai_Westland_MCP__list_my_reports`.
```

### 9. Error handling

If the MCP tool returns `isError: true`, show the message to the user. Common cases:

- "Rate limit: you've submitted N reports in the last hour" — limit is 30/hour per identity. Wait and retry, or trim duplicate noise.
- "SUPABASE_URL is not configured on the Worker" — the Worker is missing secrets. Tell the user to ping Camron; the skill cannot recover.
- Any other Supabase error — show it verbatim and offer retry.

## What NOT to do

- Don't submit without the preview step.
- Don't include passwords, API keys, tokens, or other credentials in any field — strip them from `conversation_summary` before submitting.
- Don't fabricate `skill_or_tool`. If the conversation is ambiguous about which tool broke, leave it blank and describe the context in `what_went_wrong`.
- Don't submit on the user's behalf without an explicit `yes`.
- Don't set `user_email` in the payload — it's ignored, but adding it suggests the wrong mental model. Identity is server-stamped.
- Don't try to bypass the connector by writing a Python script that POSTs to Supabase directly. The MCP IS the supported interface.

## Reference files

| File | Purpose |
|---|---|
| `references/schema.sql` | Reference copy of the `wnd_bug_reports` table CREATE statement (the live schema is in Supabase). |
| `references/mcp-tool-shapes.md` | Input/output schemas for the three tools (`submit_bug_report`, `whoami`, `list_my_reports`). |
