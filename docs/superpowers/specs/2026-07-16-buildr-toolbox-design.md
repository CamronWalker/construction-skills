# Buildr Toolbox skill + `estimating` → `preconstruction` rename — design

**Date:** 2026-07-16
**Branch:** `claude/buildr-toolbox-skill-4ddb3c`
**Status:** approved (brainstorm), ready to implement

## Summary

Add a `buildr-toolbox` skill — a companion/usage skill for the remote **Buildr MCP**
connector (`/buildr/mcp`, lives in the `westland-mcps` repo). Buildr is a cross-role tool used
by Westland's business-development, estimating, and proposals teams; the skill teaches Claude
how to route the connector's 92 tools and ships four demo report/workflow recipes.

To house it, rename the stub `estimating` plugin to **`preconstruction`** — a superset that
still covers the planned estimating skills (bid review, scope-gap, leveling) while giving BD and
proposals a natural home.

## Why this skill looks different from `schedule-toolbox`

`schedule-toolbox` is the repo's model "toolbox" skill, but it **ships its own Python `lib/` and
a local MCP**. `buildr-toolbox` does not ship code. It is a *usage skill for a remote MCP that
already exists* — pure routing tables, workflow recipes, and reference docs. It documents tools;
it never implements them. No `lib/`, no tests, no build step for the skill itself.

## The Buildr MCP surface (what the skill documents)

Ground truth from `westland-mcps/src/services/buildr/CLAUDE.md`:

- **92 tools**: 72 read + 20 write, plus a generic `buildr_get` passthrough over all ~89 read
  endpoints (`buildr_get`, `buildr_describe_endpoint`, `buildr_list_endpoints`, `buildr_whoami`).
- **Two insight tools with inline widgets**: `get_win_loss_report`, `get_workforce_availability`.
- **Domains**: projects & divisions; CRM/pipeline (companies, contacts, leads, bidding packages,
  calls, emails, comments, meetings); project sub-resources (documents, folders, photos, events,
  memberships, changesets, custom fields); financials (prime contracts, change orders,
  billing/closed/forecast periods); tasks & task lists; workforce (employees, assignments,
  time-off, roles, certifications, experiences); users.

### Load-bearing gotchas the skill must surface

1. **Shared client-credentials token.** Rate limits are **per-account, shared across all Westland
   users** (burst 20/10s, 2,000/hr, 48,000/day). Concurrent operators hit the limit fast.
2. **Write attribution.** `created_by` is always the app creator (Camron Walker, 110547), *not*
   the signed-in user. Free-text writes auto-append a "logged via Claude by \<user\>" line
   (`attribution.js`, default-on). Per-user tokens (`add_buildr_token`) are a planned fix, not yet
   built.
3. **Buildr silently ignores unsupported `filters`.** Aggregate tools pull full sets via
   `buildrGetAll` and filter in JS. Never trust a server-side filter without verifying it.
4. **Writes are confirm-gated.** Every write tool needs `confirm: true`; omit → dry-run preview.
   `BUILDR_WRITES_DISABLED=true` is a global kill switch.
5. **Win/loss classification.** won = complete/active or stage `won`; **lost = `closed_lost`
   ONLY** (a competitive loss); `closed_cancelled` + `closed_did_not_pursue` are a separate
   **no_decision** bucket EXCLUDED from the win rate. True rate ≈ 74%; folding no_decision into
   losses understates it to ~52%.

## Deliverable 1 — plugin rename (`estimating` → `preconstruction`)

`estimating` is a pure stub (only a `plugin.json`, zero skills), so the rename is mechanical and
low-risk. Still six plugins after — count unchanged.

| File | Change |
|---|---|
| `estimating/` dir | `git mv` → `preconstruction/` |
| `preconstruction/.claude-plugin/plugin.json` | `name`, `description` (mention buildr-toolbox), `keywords`, `version` → **0.2.0** |
| `.claude-plugin/marketplace.json` | entry `name`/`source`/`description` + `version` → **0.2.0** (lockstep with plugin.json) |
| `build.py` | `PLUGINS` list: `estimating` → `preconstruction` |
| `.github/workflows/lint.yml` | version-bump loop list (line ~132): `estimating` → `preconstruction` |
| `CLAUDE.md` | subdirectory list + the "six plugins" enumeration |
| `README.md` | install command, section header (Estimating → Preconstruction), add buildr-toolbox entry, keep the 4 estimating TODOs |
| `westland/skills/westland-bug-report/SKILL.md` | prefix list: `estimating:` → `preconstruction:` |

Scheduling-skill prose that says "estimating / preconstruction" refers to the *department*, not
the plugin — left untouched.

### CI safety (verified against `lint.yml`)

The version-bump job (a) loops a hardcoded plugin list and (b) excludes `plugin.json` itself when
deciding whether a plugin "changed." Result, either way GitHub resolves the workflow file:

- **`preconstruction`** (new): SKILL/reference files count as changed; plugin.json shows
  `+"version": "0.2.0"` as an added file; base version empty → monotonicity check skipped;
  lockstep holds → **[ok]**.
- **`estimating`** (deleted): its only file is `plugin.json`, which the check excludes → "no files
  changed" → **skipped**, no failure.

`forbid-personal-paths` only scans non-`.md` added lines; the non-md edits (plugin.json,
marketplace.json, build.py) carry no user paths.

## Deliverable 2 — the `buildr-toolbox` skill

Location: `preconstruction/skills/buildr-toolbox/`. Skills auto-discover from `skills/`; no
explicit registration beyond the plugin `description`.

### `SKILL.md` structure (routing-hub pattern, mirrors schedule-toolbox)

- **Frontmatter** — `name: buildr-toolbox`; description packed with triggers: *Buildr, win/loss,
  win rate, pipeline, pursuit, workforce availability, bench, bidding package, lead, CRM, prime
  contract, change order, account history, precon reporting, BD*.
- **Header note** — companion to the Buildr connector; call tools by name. If the tools are
  absent → connect the Buildr connector (Procore-federated sign-in; must be a current Buildr
  user).
- **Access & gotchas box** (top banner, like schedule-toolbox's critical-rule box) — shared
  token / per-account rate limits, write attribution reality, filters-in-JS, confirm gate.
- **Quick Routing table** — task → tool, domain-grouped.
- **Role lenses** — three short blurbs (BD, Estimating, Proposals) mapping each team to its
  tools/workflows.
- **The 4 workflow recipes** — 3–4 line summaries each, pointing to `references/workflows.md`.
- **Writes (fenced section)** — attribution reality + confirm-gate + kill switch + the 20 write
  tools by group + the `add_buildr_token` forward note.
- **House style** — reports load `westland-house-style` for output formatting.

### `references/` (three lean files)

- `tool-catalog.md` — the 72 reads + 20 writes grouped by domain + the passthrough trio, so Claude
  routes without round-tripping `buildr_list_endpoints`.
- `gotchas.md` — access/identity model, per-account rate limits, attribution, filters-in-JS,
  confirm gate — distilled from the MCP's own CLAUDE.md.
- `workflows.md` — the four recipes in full (*when to use → exact tools+params → house-style output
  shape*): **Win/Loss report**, **Workforce availability**, **Pipeline / pursuit snapshot**,
  **Account 360**. Carries the win/loss classification method so the numbers read correctly.

## Non-goals (YAGNI)

- No new MCP tools (that's `westland-mcps` work).
- No `add_buildr_token` setup skill yet (its tool + webpage don't exist).
- No write-heavy automation.
- No code shipped in the skill.

## Release

Per the repo convention: work on `claude/buildr-toolbox-skill-4ddb3c`; plugin.json +
marketplace.json bumped to **0.2.0** in lockstep; one commit; PR to `main`. The build/distribute
step happens after merge, from the main checkout (never from a worktree).
