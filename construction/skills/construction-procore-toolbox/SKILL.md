---
name: construction-procore-toolbox
description: >
  The Procore MCP toolkit and dispatcher — how to read from and write to Procore, and which
  specialized skill owns which workflow. Use whenever a task touches Procore data and no more
  specific construction-* skill has already claimed it: "in Procore", "pull from Procore",
  "post to Procore", "look up an RFI / submittal / commitment / observation / drawing / spec /
  budget", "who's on the project", "find the project", "create an RFI / change event / daily log
  / observation in Procore", "what Procore tools do you have", "Procore API", "log this to
  Procore". Also the fallback for any Procore read/write not covered elsewhere, and the reference
  for project resolution, pagination, and the write-safety contract every other construction-*
  skill relies on.
---

# Construction Procore Toolbox

The Procore MCP is the way this plugin reads and writes Procore. This skill is the map: the shared rules, the tool surface by domain, the hands-on recipes for common writes, and a dispatch table to the specialized skills that own the deeper workflows.

**Core principle:** reads are cheap and safe — do them freely. Writes are two-stage and never happen without an explicit human yes.

## Non-negotiable rules (every construction-* skill inherits these)

1. **Resolve the project first.** Call `find_project` with a name/number substring → confirm the match with the user → carry the `projectId`. Zero or multiple matches: show candidates and ask. **Never guess a `projectId`.**
2. **Read before you write.** Look up the current state before changing or adding anything, so you're not creating a duplicate or clobbering a field.
3. **Two-stage writes — the dry-run is the gate.** Every create/update tool takes `confirm`. Call it **without** `confirm` first: the tool returns a dry-run *preview* and writes nothing. Show the preview to the user. Only after an explicit yes, re-call with `confirm: true`. This is both the MCP's own safety gate (plus the `PROCORE_WRITES_DISABLED` kill switch) and the standing rule that posting to an external system needs per-action approval.
4. **Paginate to completion.** List tools return `{ items, pagination }`. Loop on `pagination.has_more` (page + 1) until exhausted before you total, grade, or conclude. Partial reads produce wrong answers.
5. **Sanity-check auth** with `whoami` if a call 401s or the wrong company/user shows up.

### Red flags — STOP

- About to call a `create_*` / `update_*` with `confirm: true` before the user saw a preview → **stop, dry-run first.**
- About to act on a `projectId` you inferred rather than confirmed → **stop, `find_project` and confirm.**
- Totaling or grading off page 1 of a paginated list → **stop, page to the end.**

## Tool surface by domain

Reference the tools by short name (the MCP prefix is `mcp__…__`). This is the high-traffic set, not the whole API — anything missing is reachable via the raw escape hatch below.

| Domain | Read | Write |
|--------|------|-------|
| Project / people | `find_project`, `show_project`, `list_project_users`, `list_project_dates`, `list_locations`, `find_company_vendor`, `whoami` | `update_project`, `set_project_date`, `create_project_worker` |
| Executive digests (inline widgets) | `project_rfi_snapshot`, `project_submittal_snapshot`, `project_response_times`, `project_daily_log_quality` | — |
| RFIs | `list_rfis`, `get_rfi`, `list_rfi_ball_in_court_options` | `create_rfi`, `update_rfi` |
| Submittals | `list_submittals`, `get_submittal` | `create_submittal`, `update_submittal` |
| Daily logs | `list_daily_logs`, `list_manpower_logs`, `list_call_logs`, `list_photos` | `create_manpower_log`, `update_manpower_log`, `create_call_log`, `create_photo` |
| Observations / punch / incidents | `list_observations`, `get_observation`, `list_punch_items`, `list_incidents`, `list_inspections`, `get_inspection` | `create_observation`, `update_observation`, `create_punch_item`, `update_punch_item`, `create_incident`, `update_incident` |
| Change mgmt / financials | `list_change_events`, `get_change_event`, `list_commitments`, `list_commitment_change_orders`, `list_prime_contracts`, `list_prime_change_orders`, `list_budget_views`, `get_budget_view_details`, `list_invoices` | `create_change_event`, `update_change_event` |
| Drawings / specs / docs | `list_drawings`, `list_drawing_revisions`, `get_drawing_revision`, `find_specification`, `get_specification`, `list_specifications`, `list_documents`, `list_folder_contents` | `create_drawing`, `create_document`, `create_document_folder`, `download_*` |
| Schedule | `list_schedules`, `get_schedule`, `list_schedule_activities`, `get_schedule_activity`, `get_schedule_import_status` | `import_xer_schedule` |
| Correspondence | `list_correspondence_types`, `list_correspondence_items`, `get_correspondence_item` | — |
| Tasks / action plans / WBS | `list_tasks`, `get_task`, `list_action_plans`, `list_wbs_codes` | `create_task`, `create_wbs_code` |

### Raw escape hatch

For anything without a typed helper: `procore_describe_endpoint(method, path)` to read the OAS spec (templated path, keep the `{param}` placeholders), then `procore_get` / `procore_post` / `procore_patch` to execute. `describe` returns `{found:false, hint}` when a path isn't in the pre-built index — that means "not indexed," not necessarily "not on the API"; a raw call may still work.

## Dispatch — hand off to the skill that owns the workflow

| The user wants to… | Use |
|--------------------|-----|
| Review / grade a project's daily logs, month-in-review | `construction-daily-log-review` |
| A quick project-health snapshot (RFIs/submittals/turnaround) | `construction-project-pulse` |
| Chase overdue **RFIs** / draft nudges | `construction-rfi-followup` |
| Chase overdue **submittals** / draft nudges | `construction-submittal-followup` |
| Post manpower / call / photo daily-log entries | `construction-daily-log-entry` |
| Turn recent emails into Procore call-log entries | `construction-email-to-log` |
| Batch-import observations from a field/observation report | `construction-observations-import` |
| Review submittals against the specs | `construction-submittal-review` |
| Write a well-formed RFI (with document search first) | `construction-rfi-writing` |
| Break down / distribute a change event to subs | `construction-change-event` |
| Build a closeout status dashboard | `construction-closeout-status-dashboard` |

If a specialized skill fits, invoke it rather than reimplementing here. Use the recipes below only for one-off writes that don't warrant a full skill.

## Hands-on recipes (one-off writes)

Each follows the two-stage write rule: dry-run → preview → `confirm: true`.

**Create an RFI**
1. `find_project` → confirm `projectId`.
2. `list_project_users` if you need an `assigneeId` / `ballInCourtId`.
3. `create_rfi(projectId, subject, question, …)` with no `confirm` → show preview → re-call with `confirm: true`. (For the full drafting workflow — searching docs first — use `construction-rfi-writing`.)

**Log manpower or a call**
1. `find_project` → confirm `projectId`.
2. `find_company_vendor` to resolve the sub → `vendorId`.
3. `create_manpower_log(projectId, date, vendorId, numWorkers, hours, comments)` — or `create_call_log(projectId, date, subjectTo, description, …)` — dry-run → preview → `confirm: true`.

**Find a vendor / sub on the project**
`find_company_vendor(searchText)` → use the returned `vendorId` in manpower/call/observation writes.

**Look up a spec or drawing**
`find_specification(projectId, …)` → `get_specification` / `download_specification`; `list_drawings` → `get_drawing_revision` / `download_drawing`.

## Common mistakes

- **Skipping the dry-run** because "it's obviously right." The preview costs one call and is the user's approval point — never skip it.
- **Guessing the `projectId`** from a name instead of `find_project`-and-confirm.
- **Concluding from page 1** of a paginated list.
- **Reinventing a workflow** the dispatch table already routes to a dedicated skill.
- **Setting a field to blank** on an `update_*` — send only the fields you mean to change.

**Voice** for anything user-facing: see `westland-house-style` — direct, concrete, active, numbers stated plainly.
