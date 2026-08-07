---
name: westland-connectors
description: >
  Setup and install guide for Westland's Claude tooling — how to install the
  construction-skills plugins (including the bundled scheduler MCP), open the
  connector manager, add each Westland MCP connector by URL, and sign in with your
  Westland identity. Use when someone asks "how do I install / set up the connectors",
  "add the Procore / SmartPM / Buildr / BuildingConnected / Microsoft connector",
  "connect the Westland MCP", "how do I install the plugins", "what connectors do we
  have", "set up my MCPs", "the tools aren't showing up", or is onboarding to Westland's
  Claude tooling.
---

# Westland Connectors & Plugins — Setup

Westland's Claude tooling comes in two layers. You need both.

1. **Plugins** — the `construction-skills` marketplace ships the skills *and* the bundled
   **scheduler MCP**. Installed with `/plugin`.
2. **Connectors** — the remote Westland MCPs (Procore, SmartPM, Buildr, BuildingConnected,
   Westland MCP, Microsoft) are claude.ai-managed connectors you add once in **Connectors**.

Skills tell Claude *how* to do the work; connectors give it the *data and actions*. A skill
whose connector isn't installed will name the missing tools and point back here.

## Access requirement

Every Westland connector signs in through your Westland identity and only admits a
Westland-affiliated email — `@westlandconstruction.com` or `@gowestland.com`. For
joint-venture or partner access, contact Camron Walker (camron@westlandconstruction.com).

## Step 1 — Install the plugins

From Claude Code, add the marketplace once, then install the plugins. **Install `westland`
first** — it's the required base every domain plugin depends on.

```
/plugin marketplace add westland-construction/construction-skills
/plugin install westland@construction-skills
/plugin install scheduling@construction-skills
/plugin install preconstruction@construction-skills
/plugin install construction@construction-skills
/plugin install safety@construction-skills
```

Install only the domain plugins you need — but always `westland`. Enterprise-managed setups
install the same plugins from distributed zips instead of the marketplace; if that's your
environment, IT hands you the zips and the rest of this guide is unchanged.

The **scheduler MCP** rides inside the `scheduling` plugin and registers itself on install
— there's no connector to add for it. If its tools (`score_schedule`, `get_critical_path`,
`weekly_update_review`, …) don't appear after install, run `westland-scheduler-mcp-troubleshoot`.

## Step 2 — Open the connector manager

Connectors are managed on claude.ai (in Claude Code, the terminal `/mcp` and `claude mcp`
commands manage *other* MCP servers — the browser connector settings are where a claude.ai
connector is enabled).

In the Claude app, open the **+** menu in the composer → **Connectors** → **Manage connectors**
(or **Add connector**). See `references/open-connectors.svg`.

You can also reach it from **Settings → Connectors**.

## Step 3 — Add a connector

1. In the connector manager, choose **Add custom connector** (or **Add connector →**).
2. Paste the connector's URL (below).
3. When the browser tab opens, **sign in with your Westland account** — Procore identity for
   the Westland-hosted connectors, your Microsoft work account for Microsoft 365. Approve on
   the provider's own screen; Claude never sees your password.
4. **Start a new Claude Code session** so the new tools sync in.

Verify with the connector's `whoami` (e.g. the Westland MCP returns your email + Procore user
id). If a tool 401s or shows the wrong company, re-check the sign-in.

## The connectors

Base URL for the Westland-hosted connectors: `https://westland-mcps.westland.workers.dev`.
Append the path shown and add it as a **custom connector**.

| Connector | Add via | What it does | Companion skill |
|---|---|---|---|
| **Procore** | custom · `/procore/mcp` | Procore read/write — RFIs, submittals, daily logs, drawings, specs, budgets, schedule import, executive digests | `construction-procore-toolbox` |
| **BuildingConnected** | custom · `/buildingconnected/mcp` | Bidding — bid packages, bids, invites, bidder contacts | `preconstruction` skills |
| **SmartPM** | custom · `/smartpm/mcp` | Schedule analytics — project health, SPI, compression, quality | `scheduling` skills |
| **Buildr** | custom · `/buildr/mcp` | CRM / precon — win-loss, workforce, pipeline. **Invite-only** (operator allowlist) — ask Camron to be added | `buildr-toolbox` |
| **Westland MCP** | custom · `/westland/mcp` | Bug-report capture, project bindings + log, weekly-email cloud editor | `westland-bug-report`, `scheduling` |
| **Microsoft 365** | claude.ai connector directory | Email, calendar, files, and Teams meeting transcripts (Outlook + SharePoint). Sign in with your Microsoft work account | `read-meeting-transcript` |
| **Westland Microsoft MCP** | custom · `/microsoft/mcp` | Westland-hosted Microsoft Graph. **Coming soon** — planned home for MS To Do and a rich email-send that carries images and email signatures. Add it now to be ready; the To Do / rich-send tools land later | — |

**Two Microsoft connectors, on purpose.** **Microsoft 365** (from the connector directory) is
the one you use today for email, calendar, and meeting transcripts — install it if you touch
those. **Westland Microsoft MCP** (`/microsoft/mcp`) is Westland's own Graph connector; it's
where MS To Do and image/signature-aware email sending are headed. They don't conflict — add
whichever you need.

For deeper Microsoft 365 setup and the transcript-access caveats, see
`read-meeting-transcript`'s `references/connect-m365.md`.

## Troubleshooting — tools aren't showing up

- **Connector shows "added" but tools are missing** → it may not be **Connected** (not just
  added), or you're signed out. Re-open the connector manager and confirm the status.
- **Just added it** → start a **fresh session**; tools sync at session start.
- **Signed in with the wrong account** → Westland connectors reject non-Westland emails; sign
  out and back in with your `@westlandconstruction.com` / `@gowestland.com` account.
- **Scheduler tools missing** → that's the bundled plugin MCP, not a connector — run
  `westland-scheduler-mcp-troubleshoot`, then `/plugin reload scheduling` and a fresh session.
- **Persists past that** → connector/IT issue, not something a skill can fix. Raise it rather
  than looping.

## Related

- `westland-analytics` — the pre-built reports these connectors power.
- `westland-bug-report` — file a bug or request against any connector or skill.
- `read-meeting-transcript` — Microsoft 365 transcript reading, with the access caveats.
