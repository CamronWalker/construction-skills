---
name: construction-submittal-followup
description: >
  Drill into a project's open and pending submittals, sort by who's holding them and how late,
  and draft chase nudges (or suggest what to draft). Use when someone says "chase overdue
  submittals", "who's sitting on submittal approvals", "which submittals are late", "submittal
  aging", "ball in court on submittals", "follow up on submittals", "nudge the reviewer", or
  wants to push stalled submittal reviews forward — especially against required-on-site dates.
  Read-and-draft only — it never sends without explicit approval. For the RFI equivalent use
  construction-rfi-followup; for a top-level health read use construction-project-pulse.
---

# Construction Submittal Follow-up

Turn open submittals into a prioritized chase list, then draft the nudges. Submittals stall in review; the job here is to show exactly who is holding each one, how late it is, and what work it's gating — then push it.

> Reads through the Procore MCP. See `construction-procore-toolbox` for project resolution, pagination, and the write/draft-safety rules.

## When to use

- "Chase overdue submittals" / "who's sitting on approvals?"
- "Submittal aging" / "ball in court on submittals" / "nudge the reviewer"
- After `construction-project-pulse` flags backed-up submittals.

## Workflow

1. **Resolve the project** — `find_project` → confirm → `projectId`.
2. **Pull open submittals.** `list_submittals` for anything not Closed; **paginate to the end**. Use `get_submittal` for detail (current reviewer/ball-in-court, due date, required-on-site date, revision).
3. **Prioritize.** Group by who's holding it (current reviewer / ball-in-court), then sort by days overdue — against the review due date, and against the **required-on-site / need-by** date where present, since a submittal that clears late but after material lead time is the real schedule risk. Flag anything whose remaining review + lead time won't beat its need-by date.
4. **Present the chase list** — most-urgent first: submittal number, title, spec section, who's holding it, days late, and the need-by/lead-time risk.
5. **Draft nudges (only if asked).** Draft follow-ups via the mail MCP — factual, specific, one recipient per message covering their held submittals ("Submittal 08 44 13-001 (curtain wall) has been in review 18 days; with a 6-week fab lead time we need it approved by the 20th to hold the facade start").
   - **If the recipient is ambiguous**, don't guess an address — *suggest what to draft*: recipient, subject, the ask, and which submittal numbers to include.
6. **Drafts only.** Never send; the user sends.

## Quick reference

| Want | Tool |
|------|------|
| Open/pending submittal list | `list_submittals` (paginate) |
| Detail on one submittal | `get_submittal` |
| Draft the nudge | mail MCP (draft, never send) |

## Common mistakes

- **Ignoring lead time.** A submittal cleared "on time" for review can still blow the schedule if fab lead time pushes delivery past need-by. Sort on the need-by risk, not just review days-late.
- **Concluding from page 1.** Paginate `list_submittals` fully.
- **Sending instead of drafting.** Stop at a draft.
- **Guessing recipient addresses.** Suggest what to draft when unknown.

**Voice:** see `westland-house-style` — factual, specific, tie the delay to the schedule stake plainly.
