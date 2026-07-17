---
name: westland-house-style
description: >
  Westland Construction's house style guide — formatting, naming, voice, and
  document conventions for internal and external-facing work. Use this skill
  whenever producing or reviewing company-branded output: emails to owners and
  subcontractors, project reports, RFIs, submittals, schedule updates, proposal
  documents, meeting minutes, daily logs, and anything else that represents
  Westland externally. Also applies to internal artifact naming (project folders,
  file suffixes, version markers) and to document structure (headers, tables,
  signature blocks). Trigger on: "Westland style", "company format", "how should
  I format this", "is this how we write it", "draft an email/report/letter",
  "name this file", or any formatting/naming question on company work.
---

# Westland Construction House Style

Progressive-disclosure skill that holds Westland's formatting, naming, and voice conventions. The SKILL.md carries the triggers and a quick-reference summary; topic-specific details live in `references/` and are loaded only when needed.

## When to use

Any output that represents Westland externally or gets filed as company work product:

- Emails (owner, subcontractor, architect, consultant)
- Weekly schedule update reports and stakeholder emails
- RFIs, submittals, change orders, meeting minutes
- Proposal documents, schedule narratives, scope letters
- File and folder naming conventions (including `.xer` version suffixes)
- Signature blocks, header/footer styling, logo placement
- Tone-of-voice questions on company communication

## Quick reference

These are the high-frequency rules — if your task matches one of these, apply directly. For edge cases or anything not covered here, read the relevant file under `references/`.

**File and folder naming:**

- Project folders: `W{job_number} - {Project Name}` (e.g. `W1134 - Neiafu Tonga Temple Construction`).
- Dated work folders: `YYYY-MM-DD/` (ISO 8601, underscore-free).
- Versioned files: `{base}-v{N}.{ext}` — increment by one each revision. `.xer` files **must** follow this (see XER rule below).
- No spaces in version suffixes (`-v2`, not `- v 2`).

**XER immutability (enforced by this plugin's PreToolUse hook):**

Every `.xer` in a Westland project folder is an immutable record. No in-place edits, no overwrites, no deletes. Every revision is a new versioned file (`-v2.xer`, `-v3.xer`, etc.). See `references/xer-files.md` for the full policy and rationale.

**Office record protection:**

Existing Excel / Word / PowerPoint files on the Westland share that are *settled records* — a submitted report, a signed workbook, an issued deck, anything final — are not overwritten in place. Write a new versioned copy (`{base}-v2.xlsx`, `-v3`, …) or ask the colleague first. Files you're actively iterating this week are working docs and fine to edit. The PreToolUse hook enforces this for direct edits it can see (it locks Office files untouched for more than 7 days). Office files written by scripts (openpyxl / python-docx) carry their path inside the script and are out of the hook's reach — so for those, this convention *(version over overwrite)* is the protection. When in doubt, version; don't overwrite.

**Voice and tone (external):**

- Professional but not stiff. Westland is competent and direct, not corporate-speak.
- Active voice. Concrete nouns. Short paragraphs.
- Lead with what matters to the reader (the owner's schedule impact, the sub's action item) — not with internal process.
- Never hedge on hard facts. Dates, durations, dollar figures, and float values are stated plainly.

## Reference files

Load these on demand when the task goes deeper than the quick reference above. Keep the top-level SKILL.md terse; push content into these files so the progressive-disclosure budget stays small.

| File | Purpose |
|------|---------|
| `references/xer-files.md` | Full `.xer` policy, rationale, how the PreToolUse hook enforces it. |
| `references/emails.md` | *(placeholder)* — tone, salutations, closing, signature block rules per recipient type. |
| `references/reports.md` | *(placeholder)* — schedule updates, RFI/submittal formatting, table styles, header structure. |
| `references/naming.md` | *(placeholder)* — full file/folder naming conventions across all project artifacts. |
| `references/voice.md` | *(placeholder)* — voice-and-tone worked examples (good vs bad), company vocabulary, terms-to-avoid. |

Placeholder files exist so future expansions drop into the right slot; Camron to fill in over time.
