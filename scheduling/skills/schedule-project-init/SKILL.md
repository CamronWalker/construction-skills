---
name: schedule-project-init
description: >
  Initialize a construction project's Schedules folder with a persistent project-context.md file.
  Parses the parent folder name for project name and job number, asks for contractual completion,
  SmartPM workspace URL, recipients, signer info, expected attachments, and graph selection, then
  writes project-context.md to the root Schedules folder. Can be re-run to update any field.
  Use this skill whenever the user says "initialize project", "project setup", "init project",
  "set up project", "create project context", "project init", or when another scheduling skill
  reports that project-context.md is missing.
---

# Project Initialization

Create or update the `project-context.md` file that all scheduling skills depend on. This file lives in the root Schedules folder (not inside dated subfolders) and carries forward across every weekly update.

## Folder Resolution

All scheduling skills share this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** directory (`../`)
2. If CWD basename is `Schedules` → root is CWD
3. If CWD contains a `Schedules/` child directory → root is that child
4. Otherwise → ask the user for the Schedules folder path

**Validate:** The parent of the resolved root should match the pattern `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`). The resolved folder itself should be named `Schedules`.

## Workflow

### Step 1: Resolve Schedules Root

Apply the folder resolution logic above. Then check if `project-context.md` already exists in the resolved root.

- **If it exists:** Read it, display the current values, and ask the user which fields they want to update. Skip to the relevant questions in Step 3.
- **If it does not exist:** Proceed to Step 2 for a fresh setup.

### Step 2: Parse Project Identity

Read the **grandparent** folder name (the parent of `Schedules/`). Parse it using the pattern:

```
W{number} - {Project Name}
```

Regex: `^(W\d+)\s*-\s*(.+)$`

- `job_number` = the `W####` portion (e.g., `W1134`)
- `project_name` = the rest (e.g., `Neiafu Tonga Temple Construction`)

If parsing fails (non-standard folder name), ask the user for both values.

Present the parsed values for confirmation:
> "I read the project as **W1134 — Neiafu Tonga Temple Construction**. Is that correct?"

### Step 3: Collect Project Configuration

Ask each question using AskUserQuestion. Proceed through all fields until everything is filled.

1. **Contractual completion date**
   > "What is the contractual Substantial Completion date for this project?"

2. **SmartPM workspace URL**
   > "Paste the SmartPM workspace URL for this project."

   Validate the URL contains `/workspace` at the end. Derive the other two URLs:
   - `smartpm_trends_url` = replace `/workspace` with `/trends?tab=Graphs`
   - `smartpm_changelog_url` = replace `/workspace` with `/changelog`

   Show all three derived URLs to the user for confirmation.

3. **TO recipients**
   > "Who should receive the weekly update email? (semicolon-separated email addresses, or leave blank for now)"

4. **CC recipients**
   > "Who should be CC'd on the update email? (semicolon-separated, or leave blank for now)"

5. **Signer name**
   > "Whose name goes on the email signature for this project?"

6. **Signer title**
   > "What title for the email signature?"

7. **Signer mobile**
   > "Mobile number for the email signature? (leave blank to omit)"

8. **Procore project ID**
   > "What is the Procore project ID for this project?"

   The Procore company ID is always `11093` (Westland Construction) — do not ask for it.

### Step 4: Build Expected Attachments

Scan the most recent dated folder (sort `YYYY-MM-DD` folders descending, take the first) for files:
- List all `.pdf`, `.xlsm`, `.xlsx`, `.csv` files found
- Build candidate glob patterns by generalizing the filenames (replace dates and project-specific text with `*` wildcards)

Present the candidate list and ask the user to confirm, add, or remove patterns:
> "Based on the files in the most recent update folder, here are the attachment patterns I'd suggest. Edit as needed — these vary per project."

If no dated folders exist yet, present a minimal default set and let the user adjust:
```yaml
expected_attachments:
  - "Report 0.01*Master Schedule*.pdf"
  - "*Schedule Analytics Report*.pdf"
  - "*Progress Update Export*.xlsm"
```

### Step 5: Configure Graph Selection

Present the default graph list for the weekly update email:

```
1. 06-end-date-variance.png
2. 07-schedule-compression-index-over-time.png
3. 08-velocity.png
4. 11-window-start-accuracy.png
5. 12-window-finish-accuracy.png
6. 09-spi-over-time.png
7. 10-activity-hit-rate.png
```

> "These are the default performance graphs included in the update email. Would you like to add, remove, or reorder any?"

The full set of available graphs (from the schedule-screenshots skill):
```
01-planned-vs-actual-percent-complete.png
02-schedule-quality-grade-over-time.png
03-project-health-index-over-time.png
04-schedule-changes-over-time.png
05-schedule-delay-over-time.png
06-end-date-variance.png
07-schedule-compression-index-over-time.png
08-velocity.png
09-spi-over-time.png
10-activity-hit-rate.png
11-window-start-accuracy.png
12-window-finish-accuracy.png
13-missing-logic.png
14-average-total-float.png
15-high-total-float.png
16-critical-path-percentage.png
```

### Step 6: Write project-context.md

Write the file to `{schedules_root}/project-context.md` with YAML frontmatter and a short body:

```markdown
---
project_name: {project_name}
job_number: {job_number}
contractual_completion: {contractual_completion}
smartpm_url: {smartpm_url}
smartpm_trends_url: {smartpm_trends_url}
smartpm_changelog_url: {smartpm_changelog_url}
to_recipients: "{to_recipients}"
cc_recipients: "{cc_recipients}"
signer_name: {signer_name}
signer_title: {signer_title}
signer_mobile: "{signer_mobile}"
procore_company_id: 11093
procore_project_id: {procore_project_id}
expected_attachments:
  - "{pattern_1}"
  - "{pattern_2}"
  - ...
graph_screenshots:
  - "{graph_1}"
  - "{graph_2}"
  - ...
---

# Project Context — {job_number} {project_name}

Project-level configuration that carries forward across updates.
Edit this file to change recipients, signer, attachments, or graph selection.
Weekly email content lives in `YYYY-MM-DD-update-email.md` files.
```

Confirm to the user:
> "Created `project-context.md` in the Schedules root. All scheduling skills will read from this file."

## Re-run Behavior

When `project-context.md` already exists, this skill acts as an editor:

1. Read and display all current values
2. Ask which fields the user wants to change
3. Walk through only those fields
4. Write the updated file back

This is the intended way to update project configuration — for example, when attachment patterns change, recipients change, or a different scheduler takes over the project.

## Folder Structure Reference

After initialization, the project's Schedules folder should look like:

```
Schedules/
├── project-context.md             ← persistent project config (this skill creates it)
├── 2026-04-01/
│   ├── 2026-04-01-update-email.md ← weekly email (schedule-update-email skill)
│   ├── screenshots/               ← SmartPM screenshots (schedule-screenshots skill)
│   └── *.xer, *.pdf, *.xlsm      ← schedule files and reports
├── 2026-04-08/
│   └── ...
```
