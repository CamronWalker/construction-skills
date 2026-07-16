---
name: construction-submittal-review
description: >
  Review a submittal against its governing spec section and flag deviations — pull the submittal
  from Procore (or take an uploaded PDF), compare product data to the spec requirements, and
  produce a compliance table plus draft review comments. Use when someone says "review this
  submittal", "check the submittal against the specs", "does this submittal comply", "submittal
  review", "flag deviations in this submittal", "compare submittal to spec section [X]", or hands
  over product data that needs checking against contract requirements. Read-and-draft by default;
  posting review comments to Procore is a confirmed two-stage write.
---

# Construction Submittal Review

Check a submittal against what the spec actually requires, and say plainly where it complies, where it deviates, and where it's missing information. The output is a requirement-by-requirement compliance table and draft review comments the reviewer can adopt.

> Reads through the Procore MCP. See `construction-procore-toolbox` for project resolution, pagination, and (if posting comments) the two-stage write contract.

## When to use

- "Review this submittal against the specs" / "does it comply?"
- "Flag deviations in [submittal]" / "compare to spec section 08 44 13"
- Product data / shop drawings that need checking before approval.

## Inputs — the submittal and the spec

You need both sides. Get them from whichever source is available:

- **Submittal:** `list_submittals` → `get_submittal` for the item and its attachments; or an uploaded submittal PDF (use the pdf skill).
- **Governing spec:** `find_specification` → `get_specification` / `download_specification` for the referenced section; or a local spec PDF. If the spec section is ambiguous, confirm which section governs before reviewing — reviewing against the wrong section is worse than not reviewing.

## Workflow

1. **Resolve the project** — `find_project` → confirm → `projectId` (skip if working purely from uploaded PDFs).
2. **Load both sides** — the submittal's product data and the governing spec section(s).
3. **Extract the spec's requirements** — the discrete, checkable requirements: products/manufacturers, performance criteria, standards (ASTM/ANSI/UL), fire/acoustic ratings, finishes, dimensions, warranty, and submittal-content requirements (what the sub was required to include).
4. **Compare item by item.** For each requirement, find the submitted value and judge: **Comply / Deviate / Insufficient info**. Cite the spec paragraph and the submittal page for each.
5. **Produce the compliance table:**

   | Spec requirement (§ ref) | Required | Submitted (pg) | Verdict |
   |---|---|---|---|
   | … | … | … | Comply / Deviate / Insufficient |

6. **Draft review comments** for the deviations and gaps — specific and actionable ("§2.2.A requires UL-rated assembly; submitted data sheet shows no UL listing — provide UL classification or a compliant alternate"). Recommend a review action (Approved / Approved as Noted / Revise & Resubmit / Rejected) with the reasoning.
7. **Optional: post to Procore.** By default the output is text the reviewer pastes into Procore. If the user wants it posted, do it as a **two-stage write** (`update_submittal` or the raw hatch, `confirm` omitted first → preview → `confirm: true`) — never post review comments without explicit approval.

## Quick reference

| Want | Tool |
|------|------|
| Submittal + attachments | `list_submittals` → `get_submittal` |
| Governing spec | `find_specification` → `get_specification` / `download_specification` |
| Read an uploaded PDF | pdf skill |
| Post comments (optional) | `update_submittal` / raw (dry-run → confirm) |

## Common mistakes

- **Reviewing against the wrong spec section.** Confirm the governing section first.
- **Vague comments.** Cite the spec paragraph and the submittal page; say exactly what's missing or non-compliant.
- **Over-claiming compliance from silence.** If the submittal doesn't show a required property, that's *Insufficient info*, not *Comply*.
- **Posting without approval.** Comments/actions go to Procore only as a confirmed two-stage write.

**Voice:** see `westland-house-style` — factual and specific; a review comment should tell the sub exactly what to fix and against which requirement.
