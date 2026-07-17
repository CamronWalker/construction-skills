# Connecting the Microsoft 365 connector

Load this only when the Microsoft 365 tools aren't available — i.e. there is no
`read_resource` / `outlook_calendar_search` tool, or `get_me` errors with
"not connected" / 401. Show the user the steps below, then stop. Connecting is a
one-time, interactive (browser sign-in) action the **user** performs — it can't
be done from inside a headless session, and you must never ask for tokens,
passwords, or callback URLs.

> **Full setup lives in `westland-connectors`.** That skill is the canonical guide for
> installing every Westland plugin and connector (Procore, SmartPM, Buildr,
> BuildingConnected, the Westland MCPs, and Microsoft). This file is the
> transcript-specific supplement: which Microsoft connector this skill needs, and the
> access caveats that decide whether a transcript is reachable at all.

## Which Microsoft connector (there are two)

Westland has **two** Microsoft connectors, and they are not interchangeable:

- **Microsoft 365** — added from the **claude.ai connector directory** (Anthropic-managed,
  same style as SmartPM / Buildr). Once connected it exposes Outlook, Calendar, Teams, and
  SharePoint/OneDrive tools. **This is the connector this skill needs** — the transcript
  chain runs on its `outlook_calendar_search`, `read_resource`, and `get_me` tools.
- **Westland Microsoft MCP** — a *custom* connector at `/microsoft/mcp` (Westland-hosted
  Microsoft Graph). Coming soon; the planned home for MS To Do and image/signature-aware
  email send. It does **not** serve meeting transcripts — adding it won't make this skill
  work.

The two don't conflict, so having both installed is fine. For transcripts, confirm it's the
directory **Microsoft 365** connector that shows **Connected** (see `westland-connectors` for
adding either one).

## Steps for the user

1. Open **claude.ai** (or the Claude Desktop app) → **Settings → Connectors**.
   - In Claude Code specifically, connectors are managed on claude.ai; the
     terminal `/mcp` and `claude mcp` commands manage other MCP servers but the
     browser connector settings are where a claude.ai-managed connector like
     this one is enabled.
2. Find **Microsoft 365** in the connector directory / available connectors and
   click **Connect**.
3. Sign in with your **@westlandconstruction.com** Microsoft work account when
   the browser tab opens, and approve the requested read scopes (calendar, mail,
   files). Approve in Microsoft's own consent screen — Claude never sees your
   password.
4. **Start a new Claude Code session** so the new tools sync in.

## Verify

Once reconnected, `get_me` should return your profile, e.g.:

```json
{ "displayName": "Camron Walker", "mail": "camron@westlandconstruction.com", ... }
```

If `get_me` works, the transcript chain in `SKILL.md` will work (subject to the
organizer / co-organizer / shared **access requirement** — connecting the tool
does not grant access to transcripts of meetings you didn't organize).

## If it still doesn't appear

- Confirm the connector shows **Connected** (not just added) in Settings.
- Confirm you signed in with the Westland Microsoft account, not a personal one.
- Tools sync at session start — a fresh session is usually what's missing.
- For the general "connector added but tools missing" checklist, see
  `westland-connectors` → *Troubleshooting*.
- Persisting past that is an IT/connector issue, not something this skill can
  fix — have the user raise it rather than looping.
