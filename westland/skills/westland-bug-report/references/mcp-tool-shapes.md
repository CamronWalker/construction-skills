# Westland MCP — internal bug-report tool shapes

Reference documentation for the three internal bug-report tools served by the Westland MCP connector (`https://westland-mcps.westland.workers.dev/westland/mcp`). Source of truth lives in `westland-mcps/src/services/westland-internal/tools/`.

The underlying service module is named `westland-internal` because it holds tools for internal Westland workflows that aren't tied to a specific upstream vendor — bug reports today, plus future capture flows (feature requests, skill-usage stats, etc.). All three tools in v1 are bug-report-related; they are now served by the unified Westland MCP connector.

## `submit_bug_report`

**Purpose:** Insert a row into `wnd_bug_reports`. `user_email` is stamped server-side — clients cannot forge it.

**Annotations:** `readOnlyHint: false`, `destructiveHint: false`, `openWorldHint: false`.

**Input schema:**

```json
{
  "type": "object",
  "required": ["title", "severity", "what_went_wrong"],
  "additionalProperties": false,
  "properties": {
    "title":                { "type": "string", "maxLength": 200 },
    "severity":             { "type": "string", "enum": ["low","medium","high","critical"] },
    "skill_or_tool":        { "type": "string", "maxLength": 200 },
    "what_went_wrong":      { "type": "string" },
    "suggested_fix":        { "type": "string" },
    "repro_steps":          { "type": "string" },
    "expected_behavior":    { "type": "string" },
    "actual_behavior":      { "type": "string" },
    "conversation_summary": { "type": "string" },
    "environment":          { "type": "object", "additionalProperties": true }
  }
}
```

Text fields >16 KB are trimmed server-side with a `…[truncated]` marker. Validation rejects empty `title` / `what_went_wrong` / `severity`.

**Rate limit:** 30 reports per hour, per identity.

**Success response (text content, JSON-encoded):**

```json
{
  "id":         "<uuid>",
  "created_at": "<ISO-8601>",
  "status":     "new",
  "title":      "<the title that was submitted>",
  "user_email": "<server-stamped from Procore identity>"
}
```

**Error response:** `isError: true`, content text is the message. Common cases:

- `title is required and must be non-empty.`
- `severity is required and must be one of: low, medium, high, critical.`
- `Rate limit: you've submitted 30 reports in the last hour. Slow down — limit is 30/hour per user.`
- `SUPABASE_URL is not configured on the Worker. Run: npx wrangler secret put SUPABASE_URL`
- `Supabase insert failed (<status>): <body>`

## `whoami`

**Purpose:** Returns the authenticated Westland identity. Use as a connectivity check before submitting.

**Annotations:** `readOnlyHint: true`, `openWorldHint: false`.

**Input schema:**

```json
{ "type": "object", "properties": {}, "additionalProperties": false }
```

**Success response:**

```json
{
  "email":         "<westland email>",
  "procoreUserId": "<procore user id>",
  "service":       "westland-internal"
}
```

## `list_my_reports`

**Purpose:** Return the caller's most-recent bug reports. Server-side scoped to `user_email = ctx.email` — you only see your own.

**Annotations:** `readOnlyHint: true`, `openWorldHint: false`.

**Input schema:**

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "status": { "type": "string", "enum": ["new","triaged","in_progress","fixed","wont_fix","duplicate"] },
    "limit":  { "type": "number", "minimum": 1, "maximum": 100, "default": 25 }
  }
}
```

**Success response:**

```json
{
  "count":   25,
  "reports": [
    {
      "id":            "<uuid>",
      "created_at":    "<ISO-8601>",
      "title":         "...",
      "severity":      "high",
      "skill_or_tool": "scheduling:schedule-update",
      "status":        "new"
    }
  ]
}
```
