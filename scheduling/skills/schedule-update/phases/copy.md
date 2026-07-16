# Phase: `copy` — Pre-Meeting Folder Setup

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `copy` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update copy`.

Creates a new dated folder for today's schedule update.

> **This step is optional.** Schedulers usually create the dated folder themselves, and the email flow (`report`) works off the most recent dated folder regardless of who made it. Use `copy` only when you want the folder scaffolded for you.

## Prerequisites

- The project must be initialized in Supabase — `get_project(job_number)` returns a row (created by `schedule-project-init`). Parse `{job_number}` from the `W#### - Name` Schedules-root folder.
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
