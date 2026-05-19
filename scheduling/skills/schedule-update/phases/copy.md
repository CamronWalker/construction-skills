# Phase: `copy` — Pre-Meeting Folder Setup

> Loaded by SKILL.md's router when the user invokes `/schedule-update copy`.

Creates a new dated folder for today's schedule update.

## Prerequisites

- `project-context.html` must exist in the Schedules root (created by `schedule-project-init`).
- Folder resolution rules: see SKILL.md.

## Step 1: Resolve root

Apply folder resolution. Identify the Schedules root.

## Step 2: Find most recent dated folder

List all `YYYY-MM-DD` subdirectories in the Schedules root, sort descending, take the most recent. This is the template folder.

If no dated folders exist, create the folder structure from scratch (ask the user what files/subfolders to include).

## Step 3: Create today's folder

Create `{root}/{YYYY-MM-DD}/` using today's date. Copy the **folder structure** (not file contents) from the most recent dated folder:

- Create matching subdirectories (`screenshots/`, `meeting/`, etc.)
- Do NOT copy schedule files, XER files, or PDFs — those are project deliverables
- Copy any batch scripts (`.bat`, `.ps1`) from the template folder — these are reusable tools

## Step 4: Report

List the created folder and its contents. Tell the user what's next:

> "Folder created at `{path}`. When you're ready to update the schedule, remind the team to send their Excel update file."
