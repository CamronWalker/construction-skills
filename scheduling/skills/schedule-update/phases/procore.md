# Phase: `procore` — Publish XER + Attachments to Procore

> Loaded by SKILL.md's router when the user invokes `/schedule-update procore`, and bundled into `report.md` and `draft.md` as the final step of the weekly "done" handler.
> Also requires `_attachments.md`.

Publishes three artifacts to Procore in one step:

1. **XER → Schedule tool** (parsed into the live schedule).
2. **Dated `YYYY-MM-DD` folder → Documents tool** (created under the project's configured documents folder).
3. **Selected attachments → dated folder** (the `share_to_procore`-tagged subset, verified by listing, with one retry on failure).

All Procore work uses MCP tools called directly by Claude. There is no Python orchestrator. The bootstrap rule for `share_to_procore` defaults lives in `carry_forward.transition_attachments` — see `_attachments.md`.

## Skip conditions

- If `parsed['skip_procore'] == True`, **do not run this phase**. Print "Procore: skipped this week (per master toggle)." and return.
- If the user explicitly aborts during folder discovery, print "Procore: aborted by user." and return.

## Preflight 1 — Resolve `procore_project_id`

Load `project-context.html` via `parse_project_context_html.load_project_context(schedules_root)`. If `ctx['procore_project_id']` is non-empty, **skip to Preflight 2**.

Otherwise, call the MCP tool to look up the project by name + number:

```
mcp__a695fe63-..-bbf8965a4c43__find_project(
    name=ctx['project_name'],
    number=ctx['job_number'],
)
```

(Replace `..` with the full server prefix at runtime.)

Decision logic:

- **Single result whose `project_number` exactly matches `ctx['job_number']`** → silent write-back. Set `ctx['procore_project_id'] = result['id']` and immediately persist via:
  ```python
  import generate_project_context_html
  generate_project_context_html.generate_project_context_html(html_path, ctx)
  ```
- **Multiple results OR no exact job-number match** → call `AskUserQuestion`:
  - Question: "Multiple Procore projects matched. Which is the right one?"
  - Header: "Procore project"
  - Options: one per candidate, label `"{name} (#{number})"`, description `"ID {id} — {address or 'address unknown'}"`
  - After user selection, set `ctx['procore_project_id']`, write back.
- **Zero results** → call `AskUserQuestion`:
  - Question: "I couldn't find the Procore project for this job. Please enter the Procore project ID manually (find it in the URL when you open the project in Procore)."
  - Header: "Procore ID"
  - Options: "Provide ID manually" and "Cancel Procore publish"
  - On manual, follow up with a free-text prompt (`AskUserQuestion` "Other" path or a follow-up question).

## Preflight 2 — Resolve `procore_documents_folder_id`

If `ctx['procore_documents_folder_id']` is non-empty, **skip to Operation 1**.

Otherwise, list the project's top-level Documents folders:

```
mcp__a695fe63-..__procore_get(
    path=f"/rest/v1.0/projects/{ctx['procore_project_id']}/folders",
    params={'filters[parent_id]': 'null'},
)
```

**Filter out the `Schedules` folder.** This is owned by the Procore v1 Schedule API. Admins can see it but cannot edit it; uploads into it will fail or be hidden. It is NEVER a valid choice.

```python
candidates = [f for f in folders if f.get('name') != 'Schedules']
```

If `candidates` is non-empty: call `AskUserQuestion`:
- Question: "Which top-level Procore Documents folder should the weekly schedule updates go into? (The dated YYYY-MM-DD subfolder will be created inside.)"
- Header: "Procore folder"
- Options: one per candidate folder (label = folder name, description = `"ID {id}"`), PLUS a final option labeled "Create new folder 'Schedule Updates'" with description "I'll create a fresh top-level folder called Schedule Updates."

If `candidates` is empty: skip the question and offer only the "Create new" path.

On user selection:
- **Existing folder picked** → set `ctx['procore_documents_folder_id'] = chosen_folder['id']`.
- **Create new** → call:
  ```
  mcp__a695fe63-..__create_document_folder(
      projectId=ctx['procore_project_id'],
      name='Schedule Updates',
      confirm=True,
  )
  ```
  Set `ctx['procore_documents_folder_id'] = response['id']`.
- **User cancels** → print "Procore: aborted by user." and return.

Persist via `generate_project_context_html` immediately so the next run skips this step.

## Operation 1 — XER import to Schedule tool

Find the latest `.xer` in the dated folder (highest `-vN` suffix; if none, the unversioned file):

```python
import glob, os, re
xer_files = glob.glob(os.path.join(dated_folder, '*.xer'))
xer_files = [x for x in xer_files if not os.path.basename(x).startswith('~$')]
def _version(path):
    m = re.search(r'-v(\d+)\.xer$', path, re.IGNORECASE)
    return int(m.group(1)) if m else 0
latest_xer = max(xer_files, key=_version) if xer_files else None
```

If no XER, log "XER: no .xer in dated folder, skipping." and continue to Operation 2.

Otherwise call:

```
mcp__a695fe63-..__import_xer_schedule(
    projectId=ctx['procore_project_id'],
    filePath=latest_xer,
    confirm=True,
)
```

Response handling:

- **`schedule_tool_not_initialized`** → log "XER: Schedule tool needs first-time upload via Procore web UI. Skipping XER for this run." Continue to Operation 2.
- **Successful response** → response contains a `curl_command` and a `jobId`. Run the curl via Bash:
  ```bash
  bash -c "{curl_command}"
  ```
  Then poll status every 5 seconds, up to 60 seconds total:
  ```
  mcp__a695fe63-..__get_schedule_import_status(
      projectId=ctx['procore_project_id'],
      jobId=response['jobId'],
  )
  ```
  Until `status == 'completed'` (success), `status == 'failed'` (error), or 60s elapsed (timeout). Record the outcome.

## Operation 2 — Create dated folder

```
today_iso = '2026-05-18'  # or whatever today is
mcp__a695fe63-..__create_document_folder(
    projectId=ctx['procore_project_id'],
    name=today_iso,
    parentId=int(ctx['procore_documents_folder_id']),
    confirm=True,
)
```

- **Success** → capture `dated_folder_id = response['id']`.
- **`name_exists` / 422** (idempotent re-run on the same day) → list parent contents and find the folder with today's name:
  ```
  listing = mcp__a695fe63-..__procore_get(
      path=f"/rest/v1.0/folders/{ctx['procore_documents_folder_id']}/contents"
  )
  dated_folder_id = next(
      f['id'] for f in listing.get('folders', []) if f.get('name') == today_iso
  )
  ```

## Operation 3 — Upload selected attachments

Filter the parsed attachments:

```python
candidates = [
    a for a in parsed['attachments']
    if a.get('share_to_procore') and a.get('checked')
       and a.get('status') != 'archived'
]
```

Resolve each filename to an absolute path the same way the parser does — relative paths join against the dated folder:

```python
import os
def resolve(filename, dated_folder):
    return filename if os.path.isabs(filename) else os.path.normpath(
        os.path.join(dated_folder, filename)
    )
```

For each candidate, run the verify-and-retry loop:

```
for a in candidates:
    upload_path = resolve(a['filename'], dated_folder)
    upload_basename = os.path.basename(upload_path)

    # Pre-check: already uploaded? (idempotent retry on same day)
    listing = procore_get(f"/rest/v1.0/folders/{dated_folder_id}/contents")
    if upload_basename in [f['name'] for f in listing.get('files', [])]:
        results.append((upload_basename, 'already_uploaded'))
        continue

    for attempt in (1, 2):
        try:
            response = create_document(
                projectId=ctx['procore_project_id'],
                filePath=upload_path,
                folderId=dated_folder_id,
                confirm=True,
            )
            # Execute the returned curl via Bash. Capture stdout/stderr.
            bash(response['curl_command'])

            # Verify by listing.
            listing = procore_get(
                f"/rest/v1.0/folders/{dated_folder_id}/contents"
            )
            if upload_basename in [f['name'] for f in listing.get('files', [])]:
                results.append((upload_basename, 'ok'))
                break
            raise RuntimeError("upload did not appear in folder listing")
        except Exception as e:
            if attempt == 2:
                results.append((upload_basename, f'failed: {e}'))
            else:
                time.sleep(5)
```

(Pseudocode — when actually running, Claude calls each MCP tool, executes the curl via the Bash tool, and uses TaskCreate / printed text to track per-file outcomes.)

## Step Final — Summary

Print a table:

```
Operation        Status   Detail
---------------  -------  -----------------------------------------
Project ID       ok       resolved from find_project (id 2646569)
Documents folder ok       reused existing 'Schedule Updates' (id 4592384)
XER import       ok       Schedule tool import completed in 38s
Dated folder     ok       created '2026-05-18' (id 9182374)
Upload: View 01.pdf       ok
Upload: Update Request.xlsm  ok
Upload: 3-Week Look-Ahead.pdf  failed: curl exit 28 (timeout)
```

If any line is `failed:` or `skipped:`, end with:

> "Retry with `/schedule-update procore` once resolved."

## What this phase MUST NOT do

- Read `email_draft_io.py`, `parse_project_context_html.py`, `generate_*.py`, or the project-context HTML directly. Use the documented function signatures only.
- Re-prompt for IDs already in `project-context.html`. The whole point of the write-back is that subsequent runs are silent.
- Upload `share_to_procore: false` attachments. The folder is public; explicit opt-in is the safety net.
- Upload the SmartPM Summary screenshot or any other file outside the user's curated `share_to_procore` set.
