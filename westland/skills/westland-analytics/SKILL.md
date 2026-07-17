---
name: westland-analytics
description: >
  Catalog of the pre-built analytics reports across the Westland MCP ecosystem —
  the one-call, opinionated reports (executive digests, win/loss, schedule health)
  that render a widget plus a narrative, grouped by MCP, each with the skill that
  owns its deeper workflow. Use when someone asks "what reports can I run", "what
  analytics do we have", "list the pre-built / canned reports", "is there a report
  for X", "report catalog", or wants to know what ready-made analytics exist before
  building something custom. Also covers how to request a new report — file a
  westland-bug-report or email Camron.
---

# Westland Analytics — Report Catalog

The Westland MCPs ship a small set of **pre-built reports**: single-call, opinionated
tools that pull the data, render an inline widget, and hand back a short narrative.
They are not raw API pulls — someone already decided what matters and how to frame it.
This skill is the index of what exists today, so you reach for a ready-made report
before building one from scratch.

> Each report lives in a domain plugin's MCP. This catalog is central; the deeper
> workflow (project resolution, follow-up actions) lives in the owning skill named in
> the last column. To install the MCPs these run on, see `westland-connectors`.

## The catalog

### Procore — project digests (`construction` plugin)

Read-only executive widgets. Resolve the project first (`find_project` → confirm `projectId`).

| Report tool | Answers | Owning skill |
|---|---|---|
| `project_rfi_snapshot` | Open/overdue RFIs, aging breakdown, ball-in-court | `construction-project-pulse` |
| `project_submittal_snapshot` | Open/overdue submittals, aging | `construction-project-pulse` |
| `project_response_times` | RFI/submittal turnaround vs. target (last 90 days) | `construction-project-pulse` |
| `project_daily_log_quality` | Field-documentation health — daily-log completeness | `construction-daily-log-review` |

### Buildr — CRM & workforce insights (`preconstruction` plugin)

Aggregate + inline widget. Pull broad, reuse the result — the connector is rate-limited.

| Report tool | Answers | Owning skill |
|---|---|---|
| `get_win_loss_report` | Win rate + won/lost/no-decision rollups by division, market sector, loss reason | `buildr-toolbox` |
| `get_workforce_availability` | Per-employee deployed / bench / freeing-up over a horizon | `buildr-toolbox` |

### Scheduler — schedule health (`scheduling` plugin, local MCP)

One-shot composed reports over a `.xer`. This MCP is bundled with the scheduling plugin
— no connector to install.

| Report tool | Answers | Owning skill |
|---|---|---|
| `proposal_schedule_health` | One-shot proposal fitness — score + missing logic + high float + anchor conflicts | `schedule-toolbox` |
| `weekly_update_review` | "What changed week over week" — activity changes, milestone slip, activities to start/finish, DCMA delta, critical-path changes, gain/loss attribution | `schedule-update`, `schedule-toolbox` |
| `score_schedule` | DCMA/quality score + letter grade + per-metric deductions | `schedule-toolbox` |

## Running a report

1. **Confirm the connector/MCP is live.** If the report tool isn't in your tool list,
   its connector or plugin isn't installed — see `westland-connectors`.
2. **Resolve the subject.** Procore/Buildr reports need a confirmed `projectId` / division;
   scheduler reports need an `.xer` path. Never guess the project.
3. **Call the report** — one call returns the widget and a summary.
4. **Synthesize a short read.** Lead with the headline, state the two or three numbers that
   matter, name the single biggest lever. Don't dump the widget with no narrative.
5. **Hand off to act.** For follow-up (chasing overdue items, drafting nudges, fixing schedule
   logic), invoke the owning skill rather than acting here.

## Don't see the report you need?

Two ways to request one, in order of preference:

1. **File a `westland-bug-report`** (feature-gap). It captures the request in a structured,
   triaged form and writes to Supabase — the fastest path to getting a report built. Say
   what question the report should answer, which MCP it belongs to, and who'd use it.
2. **Email Camron** — camron@westlandconstruction.com — to scope a new report or talk through
   whether one already covers it.

**Voice** for anything user-facing: see `westland-house-style` — lead with the headline, state
numbers plainly, no hedging.
