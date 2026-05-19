# Phase: `email` — Generate Update Email Draft (Camron's path)

> Loaded by SKILL.md's router when the user invokes `/schedule-update email`.
> Requires `_carry_forward.md` and `_attachments.md` loaded first.

Generates the Westland schedule update email from XER data, previous email, and meeting transcript.

## Step 0: Read Project Context & Previous Update

Apply folder resolution. Read `project-context.html` for all config.

To find the previous update email: list all `YYYY-MM-DD` sibling folders, sort descending, skip the current folder, check each for `*-update-email.md`. Use the first match.

## Step 1: Check Inputs

Before proceeding, verify which inputs are present:

| Input | Location | Required |
|-------|----------|----------|
| Current XER | `{dated_folder}/*.xer` | REQUIRED -- cannot generate without it |
| Previous email | Previous `YYYY-MM-DD-update-email.md` | Recommended -- carry forward red flags/stalled tasks |
| Meeting transcript | `{dated_folder}/meeting/*.txt` or `.md` or `.docx` | Recommended -- mine for successes/issues |
| Screenshots | `{dated_folder}/screenshots/*.png` | Needed for sections 3 and 12 |

If XER is missing, stop: "No XER file found in `{dated_folder}`. Export the updated schedule and place the XER here before running `email`."

If any recommended input is missing, list what's absent and ask whether to proceed without it or locate it. Do not auto-proceed without telling the user.

## Step 2: Check Screenshots

Check for `screenshots/` folder with at least `smartpm-summary-report.png` and the files listed in `graph_screenshots` from project-context.html.

If screenshots are missing or incomplete, ask: "Screenshots are missing. Run `/schedule-update screenshots` now, or should I proceed without them?" If the user asks to run screenshots first, do so (run the `screenshots` workflow above), then continue.

## Step 3: Parse XER & Extract Metrics

Parse the XER using the `schedule-toolbox` skill. Calculate:

- **Days behind/ahead:** Compare projected Substantial Completion date to contractual completion. Use SC milestone early finish if present; otherwise use project end date from PROJECT table.
- **Gain/loss since last update:** Compare to previous email's days-behind figure.
- **Critical path items:** Activities with total float = 0 or near-zero.
- **Stalled tasks:** `TK_NotStart` status with early start before data date.
- **Slipping tasks:** Started but remaining duration suggests late finish.

## Step 4: Carry Forward from Previous Email

> See `_carry_forward.md` for the parse → transition → generate recipe.
> See `_attachments.md` for the attachment dict shape and the share_to_procore field.

If a previous email exists, extract:
- Red flags list
- Stalled/slipping tasks
- Key items & issues

Ask the user: "These items were on last week's list. Which should carry forward?" Present as a multi-select (keep / remove / update each item).

## Step 5: Mine Meeting Transcript

If a transcript is provided, extract:
- **Successes** (completions, deliveries, milestones hit)
- **Issues/concerns** (delays, material problems, trade performance)
- **Recovery efforts** (acceleration plans, added crews, revised sequences)
- **New red flags or risks**

Present extracted items for confirmation: "I found these items in the meeting transcript. Which should go in the email?" Do not include without user confirmation.

## Step 6: Assemble Draft Email

Build using `{skill_dir}/references/email-template.md` for structure. The 12 sections in order:

1. **Project Info Header** -- project name, job number, contractual completion, projected SC date. Labels teal, values black.
2. **Days Behind/Ahead** -- from XER. Full line red (`#C94444`) if behind, green (`#3A9E6B`) if ahead.
3. **SmartPM Summary Report** -- embed `screenshots/smartpm-summary-report.png`. If missing, invoke `screenshots` workflow.
4. **Successes** -- from transcript extraction + user additions.
5. **Gain/Loss Narrative** -- calculated figure + user narrative. Full line colored.
6. **EOT/Recovery Status** -- from transcript + previous email + user input.
7. **Significant Logic Changes** -- prompt user for summary of changes made during update.
8. **SmartPM Changelog Link** -- from project-context.html `smartpm_changelog_url`.
9. **Red Flags** -- carried forward + new from transcript + user additions. Items in `**bold**` render bold + red.
10. **Stalled/Slipping Tasks** -- from XER analysis + carried forward + user additions. `**bold**` = red.
11. **Key Items & Issues** -- from transcript + previous email + user additions. `**bold**` = red.
12. **Performance Graphs** -- graph screenshots from `screenshots/`, in order from `graph_screenshots` in project-context.html.

Include closing paragraphs about Schedule Compliance Report and procurement spreadsheets as applicable.

## Step 7: Generate Editable HTML Preview

Instead of presenting the draft inline for section-by-section edits in chat, generate an editable HTML preview file. This is the canonical review artifact for both `email` and `report` — it's easier to edit than markdown and it renders exactly like the final email.

> See `_carry_forward.md` for the full last-week → this-week generation recipe
> including the new `skip_procore` carry-forward.

#### Changed narrative fields

Narrative blocks (`gain_loss_narrative`, `eot_recovery`, `logic_changes`) often get rewritten each week. Diff each one against last week's value from the parser — if the text changed (trim + case-insensitive compare), add the field name to a set and pass it to the generator as `changed_narrative_fields`. Those fields render with a **green dashed outline + light green background** so the reviewer sees at a glance what Claude touched. Any live in-browser edit also flips the field to green via a JS input listener, so the "touched this week" state stays visible as the colleague iterates.

#### State transitions (git-diff semantics)

Each list item and attachment tracks `status ∈ {active, new, removed, archived}` plus `date_archived`. The visual in the preview matches:

| Status   | Dashed outline | Background   | Meaning |
|----------|----------------|--------------|---------|
| active   | gray           | off-white    | Normal — in this email |
| active + `previous_text` | **amber** | light amber | **Edited** — text was tweaked this update; renders inline diff (`<ins>` green-underline, `<del>` red-strikethrough) |
| new      | green          | light green  | Added this update |
| removed  | red            | light red    | Unchecked this update; was included previously |
| archived | gray           | (collapsed sub-list) | Still removed after another update — hidden under a caret |

`transition_items()` applies these rules week-over-week:

- `new`      + checked      → `active`   (settles after one update)
- `new`      + unchecked    → `removed`  (added then cancelled)
- `active`   + unchecked    → `removed`
- `removed`  + still unchecked → `archived` (set `date_archived` = today)
- `removed`  + re-checked   → `active`   (user put it back — treated as a revert, no green badge)
- `archived` + re-checked   → `active`   (un-archived — also a revert, no green badge)
- `archived` + still unchecked → `archived` (date_archived preserved)

**90-day archive prune:** archived items with `date_archived` older than 90 days are dropped entirely on transition. Applies to list items (`red_flags`, `successes`, `stalled_tasks`, `key_items`) and attachments. `custom_paragraphs` are NOT age-pruned — they're a curated list. Override via the `max_archived_days` kwarg on `transition_items()` / `transition_attachments()` if needed.

Same rules apply to attachments. The archived date is shown inside the item's card when the user expands it. Archived items render in a **separate sub-list** below the main list (own numbering) so they don't merge back into the main numbering when the caret is opened.

#### Output file

Run `references/generate_email_preview_html.py` with the assembled data. Output: `{dated_folder}/{YYYY-MM-DD}-email-preview.html`.

The preview is a self-contained HTML file with:

- **Production styling** for every email section (Days Behind label teal, value colored red/green).
- **Per-item cards:** click into any list item (red flag, success, etc.) and a card expands below with Include checkbox, Bold/Italic/Priority buttons, ↑/↓ reorder, × Remove. Unchecked items stay in the list (carry to next week) but are excluded from this email.
- **Git-diff colors** on the dashed edit outline: green for new, red for removed, gray for archived (see table above).
- **Archived caret:** items unchecked for more than one update collapse under a "▶ N archived" caret at the bottom of each list.
- **Sticky WYSIWYG toolbar** for narrative blocks (Bold / Italic / Priority); keyboard shortcuts Ctrl+B, Ctrl+I, Ctrl+Shift+P. Markdown shortcuts `**bold**` and `==priority==` still work.
- **Custom closing paragraphs:** editable list with add / remove / reorder, each with its own include checkbox and editable label + body.
- **Attachments section** below the email body: each attachment has TWO checkboxes — the left checkbox is "Include in email" (existing behavior) and the **P** badge checkbox is "Share to Procore" (new). See `_attachments.md`. "+ Browse files" opens a file picker (defaults to the folder the HTML lives in, so browsers open in the dated folder). "+ Add by name" for typing a filename.
- **Save Edits** button downloads the edited HTML — the user saves it back over the same file.
- **Copy for Claude** button copies a JSON snapshot to the clipboard as a fallback.
- Embeds screenshots as **relative file paths** so the browser and the parser both resolve to `{dated_folder}/screenshots/`.

Tell the user:
> "Preview at `{path}`. Click into any list item to see its card (Include / B / I / ! / ↑ / ↓ / × Remove). Items turn **green** when newly added, **red** when unchecked (they carry to next week), and collapse under a caret after another update. Each attachment now has TWO checkboxes — the ☐ on the left is 'Include in email' (existing), the **P** badge on the right is 'Share to Procore' (new, off by default for safety since the folder is public). Use the **⏭ Skip Procore this week** toggle above the attachments list to suppress the Procore upload entirely. When you're done: click **Save Edits**, save the download over this file, then tell me `done`."

When the user says `done`, read the (now-edited) HTML via `references/parse_email_html.py` and continue to Step 8. The parser returns both:
- Filtered lists (strings of checked, non-archived items) and `attachment_paths` — ready for `generate_email_msg.py`.
- Full dicts (`red_flags_full`, `attachments`, etc.) — persisted into next week's preview via `carry_forward`.

## Step 8: Save Archive Markdown

Save `{dated_folder}/YYYY-MM-DD-update-email.md` from the parsed HTML values:

```yaml
---
date: YYYY-MM-DD
days_behind: {number}
gain_loss: {+/- days}
projected_completion: {date}
screenshots_captured: true/false
---
```

Followed by:
- **## Update Email** -- the full 12-section email content
- **## Project Log** -- cumulative notes on delays, late starts, impacts, decisions. Each week adds a dated entry. Do not overwrite previous entries.

The markdown is the archive/audit record and powers next week's carry-forward logic. The HTML preview is the review artifact. Keep them in sync.

Update `project-context.html` if any config changed (recipients, attachments, graphs).

Then offer to run the `draft` workflow to push the approved content to Outlook.

### Email changelog PDF attachment

If the parsed preview has `changes_report.include=True`, the `draft` workflow (and the `report` command) must also:

1. Call `references/generate_changes_report_html.generate_changes_report_attachment(...)` with:
   - `output_path` = `{dated_folder}/{changes_report.filename}` — default filename is `"{YYYY-MM-DD} Schedule Update Email (Change Report).pdf"`. The ".pdf" extension triggers HTML generation followed by headless-Chromium PDF conversion (via `references/html-to-pdf.js`); the intermediate HTML is deleted on success so only the PDF remains in the dated folder (`keep_html=True` overrides for debugging, and HTML is always preserved if PDF conversion fails). A ".html" filename skips the PDF step. The "Email (Change Report)" wording is deliberate — distinct from the SmartPM **schedule** changelog, this tracks what changed in the email's content (new items, edited items, removed items).
   - The same lists (with `previous_text` carried via the parser), narratives, and attachments passed to the preview.
   - `previous_narratives` = dict of last week's narrative values (so the report renders narrative-level diffs).
   - `changed_narrative_fields` = same set passed to the generator.
2. Append the resulting PDF's absolute path to `attachment_paths` before calling either `generate_email_eml.generate_update_email_eml(...)` (default `.eml` path) or `generate_email_msg.generate_update_email_msg(...)` (COM Outlook alternative). Both functions accept the same `attachment_paths` kwarg.
3. Pre-flight: if `references/node_modules/playwright` is missing, run `npm install` in `references/` first (same pre-flight as `screenshots`). On PDF-conversion failure (missing Node, no Chromium, timeout), fall back to attaching the `.html` alongside — the HTML is still saved, and a warning is surfaced to the user.

The PDF uses the same visual vocabulary as the preview — green for new, red strikethrough for removed, amber dashed outline on edited items with inline word-level diff that preserves bold/italic/priority formatting. It's read-only, paginated Letter-size, and safe to forward.
