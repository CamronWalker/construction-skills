# Schedule Update — Procore Integration + Skill Restructure

**Date:** 2026-05-18
**Skill:** `scheduling:schedule-update`
**Status:** Design approved — pending implementation plan

## Problem

Three issues with the current `schedule-update` skill:

1. **Inconsistent script use.** When colleagues run the skill, Claude sometimes skips the parse/generate scripts for HTML artifacts and tries to read or edit the HTML directly — corrupting it on UNC shares (W1177, 2026-05-07). Root cause: the skill doesn't enforce "read the whole skill before acting," and the model guesses based on partial context.
2. **Read amplification.** Every run re-reads `parse_email_html.py`, `generate_email_preview_html.py`, the preview HTML itself, and large chunks of `SKILL.md` (~726 lines). Per-run waste is 8–10k tokens for the same workflow. The model is reading scripts to learn their input shapes when it only needs the signatures.
3. **Manual Procore handoff.** Today the human exports the XER, uploads it to SmartPM, and separately uploads PDFs and Excel files to the Procore Documents tool. The Procore MCP can do all of this — XER import to Schedule tool, dated folder creation in Documents, file uploads with verify-and-retry — but the skill doesn't use it.

## Goals

1. Force the model to read the right files before acting, by restructuring `SKILL.md` as a router that names the phase files each command must load.
2. Eliminate redundant reads by inlining script signatures and dict shapes in the phase files. The model never `Read`s a `.py` or HTML artifact to learn its shape.
3. Add a Procore publish step that fires alongside `.eml` creation: XER imports to the Schedule tool, a dated `YYYY-MM-DD` subfolder is created under the project's documents folder, and a user-curated subset of attachments (views + update-request Excels — not the SmartPM summary) uploads with verify-and-retry. The folder is public, so the filter must be opt-in per file.

## Non-Goals

- New Python deps for Procore. The MCP returns curl commands; we execute via Bash.
- Filesystem hooks or watchers. The user still drives the workflow with explicit commands.
- Exponential-backoff retry. One retry per file is enough.
- Automatic creation of the project's top-level documents folder if it doesn't exist. We ask the user once, then store the ID.
- Re-initialization of existing projects. The next schedule-update run catches them up automatically.

## Approach

### A. Skill restructure (router + phase files)

`SKILL.md` becomes a thin router (~150 lines) that contains:

- The two absolute-rule banners (XER immutable; HTML via parse/generate)
- Folder resolution logic
- The `project-context.html` dict shape (so every phase can refer without re-reading)
- A **Command Matrix** that names exactly which phase files each sub-command must read first

Phase files live under `scheduling/skills/schedule-update/phases/`. Each is self-contained — script signatures and dict shapes are quoted inline in fenced blocks. Underscore-prefix files (`_carry_forward.md`, `_attachments.md`) are shared chunks referenced by multiple phases; they are not invoked directly.

The router header says: **"Before running any sub-command, read every file in its 'Phase files to read first' column in full. Do not Read the .py or HTML scripts they reference — each phase file includes the signatures and dict shapes you need."**

```
scheduling/skills/schedule-update/
  SKILL.md                     # router (~150 lines)
  commands/
    write-weekly-schedule-email.md   # cowork drop-in — now a thin shell that
                                     # points back at the same phase files
  phases/
    copy.md
    screenshots.md
    email.md
    report.md
    draft.md
    procore.md                 # NEW
    status.md
    _carry_forward.md          # shared
    _attachments.md            # shared
  references/                  # unchanged scripts + new procore_publish.py
```

#### Command Matrix (lives in SKILL.md)

| Invocation | Phase files to read first | Purpose |
|---|---|---|
| `copy` | `phases/copy.md` | Pre-meeting folder setup |
| `screenshots` | `phases/screenshots.md` | SmartPM capture |
| `email` | `phases/email.md` + `_carry_forward.md` + `_attachments.md` | Camron's path |
| `report` | `phases/report.md` + `_carry_forward.md` + `_attachments.md` + `phases/draft.md` + `phases/procore.md` | Colleague flow steps 6–10 |
| `draft` | `phases/draft.md` + `_attachments.md` + `phases/procore.md` | `.eml` / COM draft + Procore publish |
| `procore` | `phases/procore.md` + `_attachments.md` | Retry / standalone Procore publish |
| `status` | `phases/status.md` | Phase detection |
| no arg | `phases/status.md` | Detect → route |

### B. Inline shape reference

Every script invocation in a phase file is preceded by a fenced block showing the function signature and the dict shapes of its inputs / returns. Example (in `_carry_forward.md`):

```python
# parse_email_html.parse_preview_html(path: str) -> dict
# Returns:
# {
#   'date': 'YYYY-MM-DD',
#   'days_behind': int,
#   'gain_loss': int,
#   'gain_loss_narrative': str,
#   'eot_recovery': str,
#   'logic_changes': str,
#   'successes': list[str],          # filtered: checked, non-archived
#   'red_flags': list[str],
#   'stalled_tasks': list[str],
#   'key_items': list[str],
#   'attachments': list[{           # full dicts with carry-forward fields
#       'name': str,
#       'file_path': str,
#       'status': 'active' | 'new' | 'removed' | 'archived',
#       'date_archived': 'YYYY-MM-DD' | None,
#       'include': bool,            # checked in email
#       'share_to_procore': bool,   # NEW — checked for Procore upload
#   }],
#   'skip_procore': bool,           # NEW — master "skip Procore this week" toggle
#   ...
# }
```

Total addition per phase: ~30 lines. Net effect: 0 `.py` or HTML `Read`s in steady state.

### C. Procore publish phase

`phases/procore.md` orchestrates three operations, in order, when fired:

#### Preflight

```python
# Load project-context.html via parse_project_context_html.
# Resolve Procore IDs if missing.
ctx = load_project_context(schedules_root)

if not ctx['procore_project_id']:
    # find_project MCP tool searches by name and number.
    results = find_project(name=ctx['project_name'], number=ctx['job_number'])

    # Single match where job_number aligns with Procore's project number → silent write-back.
    # Multiple matches OR no exact job-number alignment → AskUserQuestion with
    #   candidates (name, number, ID, address) so user picks the right one.
    # Zero matches → ask user for ID manually.
    ctx['procore_project_id'] = chosen_id
    generate_project_context_html(path, ctx)   # write back

if not ctx['procore_documents_folder_id']:
    # List top-level folders in the project's Documents tool.
    folders = procore_get(
        f"/rest/v1.0/projects/{ctx['procore_project_id']}/folders",
        params={'filters[parent_id]': 'null'},
    )
    # The "Schedules" folder is owned by the v1 Schedule API. Admins see it
    # but cannot edit. It is NOT a valid destination — filter it out.
    candidates = [f for f in folders if f['name'] != 'Schedules']

    # Present candidates + "Create new top-level folder 'Schedule Updates'".
    choice = AskUserQuestion(candidates + [CREATE_NEW_OPTION])
    if choice == CREATE_NEW:
        new_folder = create_document_folder(
            projectId=ctx['procore_project_id'],
            name='Schedule Updates',
            confirm=True,
        )
        ctx['procore_documents_folder_id'] = new_folder['id']
    else:
        ctx['procore_documents_folder_id'] = choice['id']
    generate_project_context_html(path, ctx)   # write back
```

#### Operation 1 — XER → Schedule tool

```python
# Take the latest -vN.xer from the dated folder.
latest_xer = highest_version_suffix(dated_folder, '*.xer')

response = import_xer_schedule(
    projectId=ctx['procore_project_id'],
    filePath=latest_xer,
    confirm=True,
)

if response.get('error') == 'schedule_tool_not_initialized':
    # First-time projects must upload the first XER manually via the web UI.
    # Surface the instruction. Continue to operation 2.
    record_skip('xer', reason='Schedule tool needs first-time manual upload')
else:
    bash(response['curl_command'])
    # Poll until completed | failed | timeout (60s).
    poll(get_schedule_import_status, job_id=response['job_id'])
```

#### Operation 2 — Dated folder create

```python
try:
    dated = create_document_folder(
        projectId=ctx['procore_project_id'],
        name=today_iso,                            # YYYY-MM-DD
        parentId=ctx['procore_documents_folder_id'],
        confirm=True,
    )
    dated_id = dated['id']
except NameExists:
    # Idempotent re-run on the same day. Reuse existing.
    listing = procore_get(f"/rest/v1.0/folders/{ctx['procore_documents_folder_id']}/contents")
    dated_id = next(f['id'] for f in listing['folders'] if f['name'] == today_iso)
```

#### Operation 3 — Attachment uploads (verify-and-retry)

```python
# Source: parsed preview HTML.
candidates = [
    a for a in parsed['attachments']
    if a['share_to_procore'] and a['include'] and a['status'] != 'archived'
]

results = []
for a in candidates:
    # Procore stores files by their original basename. The preview's `name`
    # field is a user-editable label and may diverge from the filename on disk —
    # match Procore listings against basename(file_path), not name.
    upload_filename = os.path.basename(a['file_path'])

    # Pre-upload listing check — idempotent retry.
    listing = procore_get(f"/rest/v1.0/folders/{dated_id}/contents")
    if upload_filename in [f['name'] for f in listing['files']]:
        results.append((upload_filename, 'already_uploaded'))
        continue

    for attempt in (1, 2):
        try:
            response = create_document(
                projectId=ctx['procore_project_id'],
                filePath=a['file_path'],
                folderId=dated_id,
                confirm=True,
            )
            bash(response['curl_command'])     # must exit 0 with 2xx

            # Verify by listing — match Procore's basename, not the preview label.
            listing = procore_get(f"/rest/v1.0/folders/{dated_id}/contents")
            assert upload_filename in [f['name'] for f in listing['files']]
            results.append((upload_filename, 'ok'))
            break
        except Exception as e:
            if attempt == 2:
                results.append((upload_filename, f'failed: {e}'))
            else:
                sleep(5)
```

#### Report

A summary table of (operation, status, detail) is printed. If any operation failed, the message ends with: **"Retry with `/schedule-update procore` once resolved."**

### D. Preview HTML changes

The editable preview gains two new pieces of state, both round-tripped through `parse_email_html` and `generate_email_preview_html`:

- **`skip_procore: bool`** — top-level master toggle ("Skip Procore this week"), rendered near the attachments section. Default `False`. Carried forward verbatim from last week.
- **`share_to_procore: bool`** — per-attachment checkbox in each attachment card, sibling to the existing "Include" checkbox. Defaults:
  - **Smart-on** for filenames matching `*View*` or `*Update Request*.xlsm` (case-insensitive).
  - **Off** for everything else (the folder is public — explicit opt-in for novel files).
  - On carry-forward: preserved verbatim. User-set value always wins over the bootstrap rule.

### E. `project-context.html` changes

Add field **`procore_documents_folder_id: str`** (integer-as-string for HTML uniformity; empty until resolved). Renamed from the earlier `procore_schedule_pdfs_folder_id` proposal — "Schedule PDFs" is one possible name among many.

UI: a read-only row under the existing Procore IDs section, showing the resolved ID. If empty, the row reads "Not set — will resolve on next Procore run."

Both Procore IDs (`procore_project_id`, `procore_documents_folder_id`) are populated by the procore phase on demand — never required by the init skill. The init skill should still prompt for `procore_project_id` if known, as a convenience.

### F. Migration from existing projects

No re-initialization required.

- Parsers tolerate missing fields (return `''` for any field not present in the HTML).
- On the next `schedule-update` run that hits the procore phase, the empty IDs trigger discovery, the values are written back via the generator, and the HTML now has the new rows.
- Steady state from run #2: preflight is two dict reads.

A user who wants to switch to a different Procore folder blanks the ID in the UI; next run re-discovers.

## Data Flow

The `done`-handler in `report.md` / `draft.md` fans out to three outputs that share the parsed-preview dict as their only input:

```
user says "done"
  │
  └─► parse_email_html.parse_preview_html(preview_path)
        │
        ├─► generate_email_eml.generate_update_email_eml(...)   → YYYY-MM-DD-update-email.eml
        │
        ├─► write archive markdown                              → YYYY-MM-DD-update-email.md
        │
        └─► if not skip_procore:
              procore_publish.run(ctx, dated_folder, parsed)    → XER imported + dated folder + uploads
```

The `.eml` write and the Procore publish are independent. One failing does not block the other.

## Failure Paths

| Failure | Email `.eml` | Procore publish | User action |
|---|---|---|---|
| `find_project` returns 0 matches | written | skipped | User provides Procore project ID manually |
| Multiple project matches | written | paused for `AskUserQuestion` | User picks correct project |
| Schedule tool not initialized | written | XER skipped; folder + uploads run | One-time manual XER upload via Procore web UI |
| User cancels folder choice | written | skipped entirely | Re-run `/schedule-update procore` |
| `create_document_folder` reports name exists | written | reuse existing folder; continue | None |
| Single file upload fails twice | written | other uploads continue; failure in summary | Retry `/schedule-update procore` |
| Network down at start | written | step halts after preflight | Retry when connected |
| `skip_procore: true` in preview | written | entire step skipped | None |

## Components Touched

| File | Change |
|---|---|
| `scheduling/skills/schedule-update/SKILL.md` | Rewrite as router; remove per-phase content; add command matrix |
| `scheduling/skills/schedule-update/commands/write-weekly-schedule-email.md` | Reduce to thin shell pointing at `phases/report.md` |
| `scheduling/skills/schedule-update/phases/copy.md` | NEW — lifted from current SKILL.md |
| `scheduling/skills/schedule-update/phases/screenshots.md` | NEW — lifted from current SKILL.md |
| `scheduling/skills/schedule-update/phases/email.md` | NEW — lifted; references shared chunks |
| `scheduling/skills/schedule-update/phases/report.md` | NEW — lifted; `done`-handler fans out to draft + procore |
| `scheduling/skills/schedule-update/phases/draft.md` | NEW — lifted; references `_attachments.md` |
| `scheduling/skills/schedule-update/phases/procore.md` | NEW — full Procore publish phase |
| `scheduling/skills/schedule-update/phases/status.md` | NEW — lifted; phase detection extended to include Procore publish state |
| `scheduling/skills/schedule-update/phases/_carry_forward.md` | NEW — shared "carry forward from last week" chunk with inline shapes |
| `scheduling/skills/schedule-update/phases/_attachments.md` | NEW — shared attachment data model including `share_to_procore` |
| `scheduling/skills/schedule-update/references/procore_publish.py` | NEW — orchestrator |
| `scheduling/skills/schedule-update/references/generate_email_preview_html.py` | Add `share_to_procore` checkbox to attachment cards; add `skip_procore` master toggle |
| `scheduling/skills/schedule-update/references/parse_email_html.py` | Return `share_to_procore` per attachment; return top-level `skip_procore` |
| `scheduling/skills/schedule-update/references/carry_forward.py` | `transition_attachments` carries `share_to_procore` verbatim; bootstrap rule for new attachments |
| `scheduling/skills/schedule-project-init/references/parse_project_context_html.py` | Add `procore_documents_folder_id` to returned dict |
| `scheduling/skills/schedule-project-init/references/generate_project_context_html.py` | Render row for `procore_documents_folder_id` |
| `scheduling/.claude-plugin/plugin.json` | Bump version (minor) |
| `.claude-plugin/marketplace.json` | Bump scheduling plugin version to match |

## Testing

### Unit tests (mocked Procore MCP)

| Surface | Test |
|---|---|
| `parse_email_html.parse_preview_html` | Round-trip preview with mixed `share_to_procore` values + `skip_procore: true` → flags survive |
| `carry_forward.transition_attachments` | Last week `share_to_procore: true` preserved; new `*View*.pdf` defaults true; new generic file defaults false; user-override beats bootstrap |
| `parse_project_context_html` / `generate_project_context_html` | Round-trip `procore_documents_folder_id` + `procore_project_id`; existing fields unaffected; missing field tolerated on read |
| `generate_email_preview_html` | Cards render second checkbox; master toggle present; bootstrap matches expected files |
| `procore_publish.run` preflight | Empty project_id + single match → silent write-back; multiple matches → `AskUserQuestion` invoked; folder discovery filters out `Schedules` |
| `procore_publish.run` ops | Dated folder already exists → reused; file in listing → `already_uploaded`; simulated curl failure → one retry |

Runner: existing pytest setup. Procore MCP calls mocked at module boundary — no live Procore in unit tests.

### Manual smoke tests (Westland sandbox project)

1. **Happy path on fresh project.** Empty Procore fields in `project-context.html`. Run `/schedule-update procore` standalone. Verify project ID auto-resolution, folder discovery (with `Schedules` excluded), XER imports to Schedule tool, dated folder created, only `share_to_procore`-tagged attachments upload, SmartPM summary NOT uploaded, project-context.html has both IDs populated.
2. **Retry path.** Kill network mid-upload. Re-run. Verify IDs reused without re-prompting, already-uploaded files skip, failed file retries and lands, XER re-import is idempotent.

### Continuous improvement

First production run saves `Lessons Learned - <Project> - Procore Integration.md` next to the run output per the CLAUDE.md improvement loop.

## Open Decisions Resolved

| Question | Decision |
|---|---|
| XER destination in Procore | Schedule tool (parse), not Documents |
| Procore-eligibility filter | Per-attachment toggle in preview; defaults off; smart-on for `*View*` / `*Update Request*.xlsm` |
| Folder ID storage | `procore_documents_folder_id` in `project-context.html` |
| Failure semantics | Verify-and-retry per file; `.eml` and Procore independent |
| Procore step timing | Bundled into `done`-handler alongside `.eml` write |
| Skill read enforcement | Router + per-phase files, command matrix names required reads |
| Shape reference | Inline in each phase file |
| Project ID resolution | `find_project`; single match silent; ambiguity → `AskUserQuestion` |
| Folder discovery | MCP listing; `Schedules` (v1-owned) hard-excluded; "Create new 'Schedule Updates'" option |
| Existing project migration | No re-init; first procore run resolves and writes back |
