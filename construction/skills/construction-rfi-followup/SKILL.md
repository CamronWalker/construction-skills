---
name: construction-rfi-followup
description: >
  Drill into a project's open and overdue RFIs, sort by who's holding them and how late, and
  draft chase nudges (or suggest what to draft). Use when someone says "chase overdue RFIs",
  "who owes us RFI responses", "which RFIs are late", "RFI aging", "ball in court on RFIs",
  "follow up on open RFIs", "nudge the architect on RFIs", or wants to push stalled RFI
  responses forward. Read-and-draft only — it never sends without explicit approval. For the
  submittal equivalent use construction-submittal-followup; for a top-level health read use
  construction-project-pulse.
---

# Construction RFI Follow-up

Turn a pile of open RFIs into a prioritized chase list, then draft the nudges. The goal is to move stalled responses — most of that is knowing exactly who is holding what, and for how long.

> Reads through the Procore MCP. See `construction-procore-toolbox` for project resolution, pagination, and the write/draft-safety rules.

## When to use

- "Chase overdue RFIs" / "who owes us responses?" / "RFI aging"
- "Ball in court on RFIs" / "nudge the architect"
- After `construction-project-pulse` flags past-due RFIs.

## Workflow

1. **Resolve the project** — `find_project` → confirm → `projectId`.
2. **Pull open RFIs.** `list_rfis` filtered to open/overdue; **paginate to the end**. Use `get_rfi` for detail on the ones you'll chase, and `list_rfi_ball_in_court_options` to map ball-in-court IDs to people.
3. **Prioritize.** Group by ball-in-court (who's holding it), then sort by days overdue against the due date. Surface the worst offenders first: RFI number, subject, days late, who's holding it, and schedule impact if the RFI carries one.
4. **Present the chase list** as a table the user can act on — most-overdue first.
5. **Draft nudges (only if asked).** For the selected RFIs, draft follow-up messages via the mail MCP — factual, specific, one ask per message ("RFI-042 (curtain-wall head detail) has been with your office 21 days; framing at Grid C starts the 15th — can we get a response by the 10th?"). Group by recipient so one person gets one email covering their open items.
   - **If contacts are unknown**, don't invent addresses — instead *suggest what to draft*: recipient role, subject, the ask, and which RFI numbers to include, so the user can send it.
6. **Drafts only.** Never send. Sending is a separate, explicit action the user takes (external-message rule).

## Quick reference

| Want | Tool |
|------|------|
| Open/overdue RFI list | `list_rfis` (paginate) |
| Detail on one RFI | `get_rfi` |
| Ball-in-court → person | `list_rfi_ball_in_court_options` |
| Draft the nudge | mail MCP (draft, never send) |

## Common mistakes

- **Concluding from page 1.** Page `list_rfis` to the end or the aging is wrong.
- **Sending instead of drafting.** Always stop at a draft; the user sends.
- **Inventing recipient addresses.** If unknown, suggest what to draft rather than guessing an address.
- **One giant email.** Group by recipient so each person gets a focused, short chase.

**Voice:** see `westland-house-style` — factual and specific, state the days-late and the schedule stake plainly, no urgency theatrics.
