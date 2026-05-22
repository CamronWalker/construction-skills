# Phase: `screenshots` — Capture SmartPM Graphs

> Loaded by SKILL.md's router when the user invokes `/schedule-update screenshots`.

Captures the SmartPM Summary Report parts and trend graphs listed in `project-context.html`'s `graph_screenshots`. Two paths share the same output filenames so the rest of the pipeline can't tell them apart:

| Invocation | Path | When to use |
|------------|------|-------------|
| `/schedule-update screenshots` (no arg) | **matplotlib (new)** — MCP fetch + Python render | Default. No browser automation; no SmartPM login. |
| `/schedule-update screenshots --legacy` | **Playwright (legacy)** — headless Chromium captures SmartPM | Fallback while matplotlib styling is being dialed in, or when a non-default chart isn't implemented yet. |

Both paths write into `{dated_folder}/screenshots/` with the same PNG filenames.

---

## Default path: matplotlib (no `--legacy` arg)

### Step 0: Pre-flight

Run these checks **before** Step 1 — failing early is cheaper than crashing on render.

1. **Python deps.** Use the Bash tool:
   ```bash
   python -c "import matplotlib, PIL; print('ok')"
   ```
   If it errors with `ModuleNotFoundError`, install:
   ```bash
   pip install -r "{skill_dir}/references/charts/requirements.txt"
   ```

2. **SmartPM MCP tools.** Look at your tool list for any tool whose name matches `mcp__<uuid>__smartpm_*`. The `<uuid>` part is per-installation — don't hardcode it. Throughout this doc, when you see `smartpm_foo`, the real tool name is `mcp__<uuid>__smartpm_foo`. Use the `ToolSearch` tool with `query: "select:smartpm_post_project_summary,smartpm_get_project,smartpm_list_scenarios,smartpm_list_scenario_schedules_v2,smartpm_get_scenario_schedule_compression_trend,smartpm_get_scenario_velocity,smartpm_get_scenario_spi_trend,smartpm_get_scenario_should_start_finish_trend,smartpm_get_scenario_percent_complete_curve_v2,smartpm_list_scenario_change_log_by_type"` to load all the schemas at once.

   If `ToolSearch` reports "no matching deferred tools", the SmartPM connector isn't connected. Tell the colleague:
   > "SmartPM MCP isn't available in this session. Run `/mcp` to reconnect, or use `/schedule-update screenshots --legacy` for the Playwright path."
   …and stop.

### Step 1: Read Project Context

Apply standard folder resolution (see `phases/status.md` for the rule — use today's dated folder under the project's Schedules tree). Read `project-context.html` via `parse_project_context_html` if available, otherwise extract these four fields directly from the HTML:

- `graph_screenshots` — list of slugs to render. If empty or missing, default to:
  `["smartpm-summary-curve", "smartpm-summary-cards", "smartpm-summary-milestones",
    "01-planned-vs-actual-percent-complete",
    "02-schedule-quality-grade-over-time",
    "06-end-date-variance", "07-schedule-compression-index-over-time",
    "08-velocity", "09-spi-over-time", "10-activity-hit-rate",
    "11-window-start-accuracy", "12-window-finish-accuracy"]`
- `smartpm_project_name` — string to match on SmartPM. Falls back to `project_name`.
- `smartpm_url` — used by the email body, not by this phase. Just preserve.
- `contractual_completion` — `YYYY-MM-DD`. Only needed for `06-end-date-variance` (see Step 3). If missing from project-context, Step 3 will fall back to `smartpm_post_project_summary` for it.

If `project-context.html` is missing, stop with:
> "No project-context.html found in {dated_folder}. Run `/schedule-update copy` first, then re-run this command."

### Step 2: Resolve project_id + modelId + scenarioId(s)

This step is precise on purpose — Westland projects have multiple SmartPM scenarios with the same `dataDate`, so picking "the newest" by date is ambiguous and gets you the wrong scenario.

1. **Find the project.** Call `smartpm_list_projects` (no args).

   ```
   target_name = smartpm_project_name  # from Step 1
   ```

   Filter for projects whose `name` equals `target_name` exactly. If zero matches, retry with a case-insensitive, whitespace-trimmed comparison. If still zero, surface the closest 3 matches and ask the colleague:
   > "I couldn't find a SmartPM project named {target_name!r}. Closest matches: 1. … 2. … 3. … Which one (or different)?"

   On match, capture: `project_id = project['id']`.

2. **Get the project record (single source of truth for scenario IDs).** Call `smartpm_get_project(projectId=project_id)`. Response contains:

   ```json
   {
     "id": 147808,
     "name": "Neiafu Tonga Temple",
     "city": "Neiafu", "state": "Vava'u", "zipcode": null,
     "currentModelId": 885,
     "originalScenarioId": 2058,      // ← "Full Schedule" scenario
     "defaultScenarioId": 2062,       // ← milestone scenario (Substantial Completion)
     "dataDate": "2026-04-29T08:00:00"
     // …other fields
   }
   ```

   Capture:
   ```
   model_id              = project['currentModelId']
   default_scenario_id   = project['defaultScenarioId']     # use this for everything
   original_scenario_id  = project['originalScenarioId']    # ONLY for the second row of smartpm-summary-milestones
   project_location      = ", ".join(p for p in (project.get('city'), project.get('state')) if p)
   data_date             = project['dataDate'][:10]
   ```

   The `defaultScenarioId` is the milestone scenario you want for almost every chart. The `originalScenarioId` is the "Full Schedule" sibling — only relevant for the second row of the milestones chart. Do NOT call `smartpm_list_scenarios` to "pick the newest" — they all share `dataDate` and the IDs don't sort meaningfully.

### Step 3: Fetch + write payload JSONs

For each slug in `graph_screenshots`, call the MCP endpoint shown below, transform the response to the canonical payload shape (also shown below), and write it to `{dated_folder}/.chart-payload/{slug}.json`. Create `.chart-payload/` if it doesn't exist.

**`smartpm_post_project_summary` warning:** This endpoint accepts a closed set of columns. ANY unknown column 400s the whole batch with no per-column detail. The valid columns are listed verbatim in the tool description (look for "CANONICAL COLUMNS:"). Don't invent names like `MILESTONES` or `LAST_PERIOD_CHANGES` — they don't exist on this endpoint.

#### Recipe per slug

##### `01-planned-vs-actual-percent-complete`

```
resp = smartpm_get_scenario_percent_complete_curve_v2(
    projectId=project_id, scenarioId=default_scenario_id)
# resp shape: {"percentCompleteTypes": {...},
#              "data": [{"DATE", "LATE_DATE_PLANNED", "BASELINE_PLANNED",
#                        "ACTUAL", "SCHEDULED", "PLANNED"}, ...]}

payload = resp   # pass through as-is
```

Same endpoint as `smartpm-summary-curve`, different consumer: the chart-01
renderer is the HTML+SVG path (clones SmartPM's Highcharts CSS, emits a
sibling `.html` next to the `.png`), while the summary-curve renderer is
the matplotlib path used inside the Summary Report composite.

**Renderer:** chart 01 is rendered by the JavaScript `@westland/charts`
package (`references/charts/01-planned-vs-actual.js`). To render this
slug standalone (e.g. for previewing during development):

```bash
node scheduling/skills/schedule-update/references/charts/cli.js \
     {dated_folder}/.chart-payload \
     {dated_folder}/screenshots
```

The CLI dispatches every payload in `.chart-payload/` through the JS
registry; slugs without a JS renderer are reported in `failed` with
reason `no renderer in registry` (those still go through the Python
`charts.render` step below until they migrate). At this commit, only
chart 01 is on the JS path.

##### `02-schedule-quality-grade-over-time`

```
# No dedicated MCP tool as of 2026-05-21. Use smartpm_get (raw GET):
resp = smartpm_get(
    path=f'/projects/{project_id}/scenarios/{default_scenario_id}/schedule-quality-trend')
# resp is a list of objects, one per historical data date, each shaped:
#   { dataDate, metrics: [...full metrics array...], grade: { mark, indicator, score },
#     qualityProfileId }
# The metrics array is verbose — strip it down to just what the renderer needs:

payload = {
    "trend": [
        {"dataDate": r["dataDate"], "grade": r.get("grade", {})}
        for r in resp
    ]
}
```

The renderer reads `trend[].grade.score` (0–100 numeric) for the Y-axis and
`trend[].dataDate` (ISO-8601 string) for the X-axis. Background grade bands
(A ≥ 90, B 73–89, C < 73) are hard-coded in the renderer.

Note: `smartpm_get_scenario_schedule_quality` (the dedicated MCP tool) only
returns the latest data date — it does NOT support the `dataDate` query
parameter historically. Use the raw GET path above for the full trend.

##### `03-project-health-index-over-time`

```
resp = smartpm_get_scenario_project_health_trend(
    projectId=project_id, scenarioId=default_scenario_id)
# resp shape: flat list (NOT wrapped in {"trend": [...]}):
#   [{"dataDate": "YYYY-MM-DDTHH:MM:SS",
#     "health": int (0-100),
#     "risk": "GOOD"|"FINE"|"BAD"}, ...]
# Note: the indicator field is named "risk", not "indicator".

payload = resp   # pass through as-is (flat list)
```

Single light-blue line with per-point circle markers color-coded by the
health indicator (GOOD=green / FINE=amber / BAD=red). Y-axis auto-fits to
the visible data range (SmartPM convention). The renderer accepts both the
raw flat-list form and a `{"trend": [...]}` envelope for forward-compatibility.

##### `04-schedule-changes-over-time`

```
resp = smartpm_get_scenario_change_log_summary(
    projectId=project_id, scenarioId=default_scenario_id)
# resp shape: flat list (NOT wrapped in a dict envelope):
#   [{"dataDate": "YYYY-MM-DDTHH:MM:SS",
#     "metrics": {
#         "CriticalChanges":        int,
#         "NearCriticalChanges":    int,
#         "ActivityChanges":        int,
#         "LogicChanges":           int,
#         "CalendarChanges":        int,
#         "DurationChanges":        int,
#         "DelayedActivityChanges": int,
#         "ActivitiesAdded":        int,
#         "ActivitiesDeleted":      int,
#         "AllCalendarChanges":     int,
#         "FlaggedChanges":         int,
#         "WorkingDayChanges":      int
#     }}, ...]
# NOTE: there is no "totalActivities" field in this endpoint — the column
# series visible in the SmartPM UI is not available via MCP.

payload = resp   # pass through as-is (flat list)
```

7 smoothed spline lines, one per change category (Critical / Near-Critical /
Activity / Logic / Calendar / Duration / Delayed Activity). Numeric Y-axis
from 0 to max observed value, rounded up to a sensible tick boundary.
All-zero datasets (early-stage projects) render as an empty-but-valid chart
frame — no crash.

##### `06-end-date-variance`

```
updates_response = smartpm_list_scenario_schedules_v2(
    projectId=project_id, scenarioId=default_scenario_id)
# updates_response is a list of dicts. Each has: dataDate, sourceEndDate, etc.

# Get contractual completion. Prefer project-context if present; else MCP.
if not contractual_completion:
    summary = smartpm_post_project_summary(
        projectId=project_id, modelId=model_id, scenarioId=default_scenario_id,
        columns=["CURRENT_SCENARIO.CONTRACTUAL_END_DATE"])
    contractual_completion = summary["CURRENT_SCENARIO.CONTRACTUAL_END_DATE"][:10]

payload = {
    "updates": updates_response,
    "contractual_completion": contractual_completion,
}
```

##### `07-schedule-compression-index-over-time`

```
resp = smartpm_get_scenario_schedule_compression_trend(
    projectId=project_id, scenarioId=default_scenario_id)
# resp shape: list of {dataDate, scheduleCompression, scheduleCompressionIndex, indicator}

payload = {"trend": resp}
```

##### `08-velocity`

```
resp = smartpm_get_scenario_velocity(
    projectId=project_id, scenarioId=default_scenario_id)
# resp: list of {date, baselineStarts, baselineFinishes, currentStarts, currentFinishes}
# Don't try to massage the shape — pass it through as velocityList.

payload = {
    "velocityList": resp,
    "dataDate": data_date,                        # YYYY-MM-DD from Step 2
}
```

##### `09-spi-over-time`

```
resp = smartpm_get_scenario_spi_trend(
    projectId=project_id, scenarioId=default_scenario_id)
# resp: list of {dataDate, spi}

payload = {"trend": resp}
```

##### `10-activity-hit-rate`, `11-window-start-accuracy`, `12-window-finish-accuracy`

These three share a single endpoint — call it once and reuse the response.

```
hit_resp = smartpm_get_scenario_should_start_finish_trend(
    projectId=project_id, scenarioId=default_scenario_id)
# hit_resp: list of {dataDate, totalOnTimeHitRate,
#                    startedOnTime, startedLate, didNotStart,
#                    finishedOnTime, finishedLate, didNotFinish, ...}

# Same payload for all three charts; the chart functions pick the field they want.
payload = {"hitRates": hit_resp}
# Write this same payload to three files:
#   10-activity-hit-rate.json
#   11-window-start-accuracy.json
#   12-window-finish-accuracy.json
```

##### `smartpm-summary-curve`

```
resp = smartpm_get_scenario_percent_complete_curve_v2(
    projectId=project_id, scenarioId=default_scenario_id)
# resp shape: {"percentCompleteTypes": {...},
#              "data": [{"DATE", "LATE_DATE_PLANNED", "ACTUAL",
#                        "SCHEDULED", "PLANNED", "PREDICTIVE"}, ...]}

payload = resp   # pass through as-is
```

##### `smartpm-summary-cards`

One call to `smartpm_post_project_summary`, then map fields into the canonical shape.

```
columns = [
    "CURRENT_SCENARIO.HEALTH",
    "CURRENT_SCENARIO.SCHEDULE_PERFORMANCE_INDEX",
    "CURRENT_SCENARIO.PROGRESS",
    "CURRENT_SCENARIO.DELAY_NET_CRITICAL_PATH_DELAY",
    "CURRENT_SCENARIO.DELAY_PLANNED_RECOVERY",
    "CURRENT_SCENARIO.SCHEDULE_QUALITY",
    "CURRENT_SCENARIO.COMPRESSION_DELTA",
    "CURRENT_SCENARIO.FORECASTED_COMPLETION_DATE",
    "PREVIOUS_SCENARIO.FORECASTED_COMPLETION_DATE",
]
r = smartpm_post_project_summary(
    projectId=project_id, modelId=model_id, scenarioId=default_scenario_id,
    columns=columns)

# COMPRESSION_DELTA.current.index is the integer percentage you want (e.g. 0, 83).
# Don't use .value — that's the raw ratio.
payload = {
    "health":      {"value": r["CURRENT_SCENARIO.HEALTH"]["health"]},
    "spi":         r["CURRENT_SCENARIO.SCHEDULE_PERFORMANCE_INDEX"]["value"],
    "planned_pct": round(r["CURRENT_SCENARIO.PROGRESS"]["currentPlanned"]),
    "actual_pct":  round(r["CURRENT_SCENARIO.PROGRESS"]["currentActual"]),
    "critical_path_delay_days": r["CURRENT_SCENARIO.DELAY_NET_CRITICAL_PATH_DELAY"],
    "planned_impact_days":      r["CURRENT_SCENARIO.DELAY_PLANNED_RECOVERY"],
    "quality_grade":   r["CURRENT_SCENARIO.SCHEDULE_QUALITY"]["mark"],
    "compression_pct": r["CURRENT_SCENARIO.COMPRESSION_DELTA"]["current"]["index"],
    "predicted_completion":      r["CURRENT_SCENARIO.FORECASTED_COMPLETION_DATE"]["forecastedCompletionDate"][:10],
    "last_predicted_completion": r["PREVIOUS_SCENARIO.FORECASTED_COMPLETION_DATE"]["forecastedCompletionDate"][:10],
}
```

##### `smartpm-summary-milestones`

This is the most complex one — 4 MCP calls total. Steps:

1. **Row 1 — Substantial Completion** (the milestone scenario):
   ```
   r1 = smartpm_post_project_summary(
       projectId=project_id, modelId=model_id, scenarioId=default_scenario_id,
       columns=[
           "PROJECT.NAME",
           "SCENARIO.NAME",
           "CURRENT_SCENARIO.DATA_DATE",
           "CURRENT_SCENARIO.END_DATE",
           "CURRENT_SCENARIO.CONTRACTUAL_END_DATE",
           "CURRENT_SCENARIO.CONTRACTUAL_FLOAT",
           "CURRENT_SCENARIO.FORECASTED_COMPLETION_DATE",
           "CURRENT_SCENARIO.COMPRESSION_DELTA",
           "CURRENT_SCENARIO.DELAY_NET_CRITICAL_PATH_DELAY",
           "PREVIOUS_SCENARIO.DELAY_NET_CRITICAL_PATH_DELAY",
       ])
   ```

2. **Row 2 — Full Schedule** (the original/COMPLETE scenario):
   ```
   r2 = smartpm_post_project_summary(
       projectId=project_id, modelId=model_id, scenarioId=original_scenario_id,
       columns=[
           "SCENARIO.NAME",
           "CURRENT_SCENARIO.END_DATE",
           "CURRENT_SCENARIO.CONTRACTUAL_END_DATE",
           "CURRENT_SCENARIO.CONTRACTUAL_FLOAT",
           "CURRENT_SCENARIO.FORECASTED_COMPLETION_DATE",
           "CURRENT_SCENARIO.COMPRESSION_DELTA",
       ])
   ```

3. **Bullet items for Selected Period Critical Path Delays.** Call `smartpm_list_scenario_change_log_by_type` with `type="CriticalChanges"` and `dataDate=data_date` (the latest data date from Step 2):
   ```
   cpd_items = smartpm_list_scenario_change_log_by_type(
       projectId=project_id, scenarioId=default_scenario_id,
       type="CriticalChanges", dataDate=data_date)
   # cpd_items: list of {differences[], friendlyId, ...}.
   # Render each as: f"{friendlyId} (+{N} days)" where N is derived from the
   # remainingDuration or plannedDuration diff in `differences`.
   ```

4. **Last Period Schedule Changes counts.** Same endpoint, different type:
   ```
   activity_items = smartpm_list_scenario_change_log_by_type(
       projectId=project_id, scenarioId=default_scenario_id,
       type="ActivityChanges", dataDate=data_date)
   # last_period_changes.total          = len(activity_items)
   # last_period_changes.critical_path  = len(cpd_items)
   # last_period_changes.acceleration_days = null  (not available from MCP)
   ```

5. **Assemble:**
   ```
   def days_late(r):
       cf = r.get("CURRENT_SCENARIO.CONTRACTUAL_FLOAT")
       return abs(cf) if cf is not None and cf < 0 else 0

   payload = {
       "project_name":     r1["PROJECT.NAME"],
       "milestone_name":   r1["SCENARIO.NAME"],
       "project_location": project_location,        # from Step 2
       "data_date":        data_date,
       "milestones": [
           {
               "order": 1,
               "name": r1["SCENARIO.NAME"],
               "contractual": r1["CURRENT_SCENARIO.CONTRACTUAL_END_DATE"][:10] if r1.get("CURRENT_SCENARIO.CONTRACTUAL_END_DATE") else None,
               "current":     r1["CURRENT_SCENARIO.END_DATE"][:10],
               "days_late":   days_late(r1),
               "predicted":   r1["CURRENT_SCENARIO.FORECASTED_COMPLETION_DATE"]["forecastedCompletionDate"][:10],
               "compression_pct": r1["CURRENT_SCENARIO.COMPRESSION_DELTA"]["current"]["index"],
           },
           {
               "order": 2,
               "name": r2["SCENARIO.NAME"],
               "contractual": r2["CURRENT_SCENARIO.CONTRACTUAL_END_DATE"][:10] if r2.get("CURRENT_SCENARIO.CONTRACTUAL_END_DATE") else None,
               "current":     r2["CURRENT_SCENARIO.END_DATE"][:10],
               "days_late":   days_late(r2),
               "predicted":   r2["CURRENT_SCENARIO.FORECASTED_COMPLETION_DATE"]["forecastedCompletionDate"][:10],
               "compression_pct": r2["CURRENT_SCENARIO.COMPRESSION_DELTA"]["current"]["index"],
           },
       ],
       "critical_path_delays": {
           "count": (r1["CURRENT_SCENARIO.DELAY_NET_CRITICAL_PATH_DELAY"]
                     - r1["PREVIOUS_SCENARIO.DELAY_NET_CRITICAL_PATH_DELAY"]),
           "items": [render_cpd_bullet(it) for it in cpd_items],
       },
       "critical_path_recoveries": {"count": 0, "items": []},
       "last_period_changes": {
           "total":         len(activity_items),
           "critical_path": len(cpd_items),
           "acceleration_days": None,
       },
   }
   ```

#### Non-default slugs

For any slug in `graph_screenshots` that **isn't** in the recipes above (i.e., one of the 6 remaining non-default trends — `04`, `05`, `13`, `14`, `15`, `16`), the registry has a stub that raises `NotImplementedError` mentioning `--legacy`. Skip the fetch — write a minimal `{}` payload so the orchestrator can dispatch and report the stub's `NotImplementedError`. The colleague-facing message in Step 5 handles the rest.

### Step 4: Render

```bash
cd "{skill_dir}/references"
python -m charts.render "{dated_folder}/.chart-payload" "{dated_folder}/screenshots"
```

`charts/` is a regular Python package — no `PYTHONPATH` gymnastics needed when run as a module from the `references/` directory. Works identically on Windows PowerShell and bash.

The script prints a JSON `{rendered: [...], failed: [...]}` to stdout.

**Summary-report composite.** After the main loop, if all three summary parts (`smartpm-summary-cards`, `smartpm-summary-curve`, `smartpm-summary-milestones`) rendered successfully, the orchestrator stacks them vertically into a single `smartpm-summary-report.png` in the output dir (cards on top, curve in the middle, milestones table at the bottom). This matches the legacy Playwright filename and is what the email body / preview / changes-report embed as the single `summary_screenshot_path`. Nothing extra to do — the composite appears as another entry in the `rendered` list.

### Step 5: Verify

For every slug in `graph_screenshots`: confirm `{dated_folder}/screenshots/{slug}.png` exists with size > 0 bytes. Use the Bash tool:

```bash
ls -la "{dated_folder}/screenshots/"
```

For any slug in the orchestrator's `failed` list whose `reason` contains `NotImplementedError`, tell the colleague:

> "Chart {slug} isn't implemented in the new matplotlib path yet. Run `/schedule-update screenshots --legacy` to capture it via the existing Playwright path."

For any other failure (e.g. MCP error, JSON write error), surface the exact `reason` so the colleague can decide.

### Step 6: Clean up

Remove the working payload directory:

```bash
rm -rf "{dated_folder}/.chart-payload"
```

(On Windows PowerShell: `Remove-Item -Recurse -Force "{dated_folder}\.chart-payload"`.)

---

## Failures & recovery

| Failure mode | Where it surfaces | Action |
|---|---|---|
| `ToolSearch` returns no matches for `smartpm_*` tools | Step 0 | Tell the colleague to `/mcp` reconnect or use `--legacy`. |
| `ModuleNotFoundError: matplotlib` | Step 0 | `pip install -r {skill_dir}/references/charts/requirements.txt` |
| `smartpm_list_projects` returns no match for `smartpm_project_name` | Step 2.1 | Try case-insensitive match; if still no match, show the closest 3 names and ask. |
| `smartpm_post_project_summary` 400 BAD_REQUEST | Step 3 | A column in the batch isn't in the canonical set. Re-check the tool description's "CANONICAL COLUMNS" list — don't invent column names. |
| Renderer `failed` entry mentions `NotImplementedError` | Step 5 | Non-default slug. Quote the `--legacy` message above. |
| Renderer `failed` entry mentions `KeyError` / `TypeError` | Step 5 | Payload shape doesn't match what the chart expects. Re-check the recipe in Step 3 for that slug — every chart's expected shape is inlined there. Don't `Read` the chart `.py` file. |
| Renderer creates a PNG of size 0 | Step 5 | Likely an empty trend response (project too new). Show the colleague and offer to skip that slug. |

---

## Legacy path: `--legacy`

Everything in this section is the **unchanged** Playwright capture. It runs `references/smartpm/capture-smartpm.js` end-to-end. Use when a matplotlib chart isn't ready or doesn't look right yet.

### Step 0: Pre-Flight — credentials + Node setup

The script reads SmartPM credentials from `~/.claude/.env`:

| Key | Required | Purpose |
|-----|----------|---------|
| `SMARTPM_EMAIL` | yes | Auto-login email |
| `SMARTPM_PASSWORD` | yes | Auto-login password |
| `SMARTPM_PROJECTS_URL` | no | v2 projects/cards URL (defaults to Westland's org URL) |
| `SMARTPM_BASE_URL` | no | Defaults to `https://live.smartpmtech.com` |

If credentials are missing, the script throws `ENV_MISSING`. To set them up:

```bash
node "{skill_dir}/references/smartpm/env-loader.js" setup
```

Or ask the colleague for them via `AskUserQuestion` (header: "SmartPM creds") and write them yourself by calling `upsertEnvFile({SMARTPM_EMAIL, SMARTPM_PASSWORD})` from `references/smartpm/env-loader.js`. Never log the password back to the user.

Node + Playwright pre-flight:
1. `node --version` (any 18+).
2. Check `node_modules/` exists in `{skill_dir}/references/`. If missing, run `npm install` in that folder.
3. Chromium is installed via `npx playwright install chromium` (the script handles this).

### Step 1: Read Project Context

Apply folder resolution. Read `project-context.html`. Extract `smartpm_project_name` (falls back to `project_name`).

Output dir: `{dated_folder}/screenshots/`.

### Step 2: Write Checklist

Create `{dated_folder}/screenshots/` if it doesn't exist. Write `screenshots/checklist.md` from `{skill_dir}/references/checklist-template.md`.

Print the checklist.

### Step 3: Capture via Node script

```bash
node "{skill_dir}/references/smartpm/capture-smartpm.js" \
  "{smartpm_project_name or project_name}" "{dated_folder}/screenshots"
```

stdout: JSON `{ status, total, screenshots: [{name, file, path, size}, ...], urls }`.

Errors:
- `ENV_MISSING` → run the setup command (Step 0) or ask the user for credentials.
- Login redirect timeout → bad creds, MFA challenge, or captcha. Surface and ask the user to log in manually once via the headed debug helper.
- "No chart cards found" → trends page didn't render. Likely upload-still-processing or stale cache; retry after 30 seconds.
- Sign-in button stuck disabled → Angular form validation rejected the email. Confirm `SMARTPM_EMAIL`.

### Step 4: Verify

Read the captured PNGs visually. Confirm `smartpm-summary-report.png` shows the Summary Report modal, and each graph file shows the correct chart with data.

**SmartPM processing warning:** If called within 30 minutes of XER upload, SmartPM may still be processing. Check the Workspace page status; offer to wait.

### Step 5: Report

Mark checklist complete. Report total screenshots captured, file paths and sizes, SmartPM URLs used.

---

## Iteration note

The matplotlib path is brand new. Expect back-and-forth on styling — fonts, gridlines, axis labels, colors, table cell formatting — against live data. Tweak the relevant function in `references/charts/charts.py`; everything else (registry, orchestrator, tests) stays still. When a chart looks right, that's it — no formal sign-off step, just keep using it. Until each default chart is dialed in, `--legacy` is the safety net.
