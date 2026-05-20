# Phase: `screenshots` — Capture SmartPM Graphs

> Loaded by SKILL.md's router when the user invokes `/schedule-update screenshots`.

Captures the SmartPM Summary Report and trend graphs listed in `project-context.html`'s `graph_screenshots`. Two paths share the same output filenames so the rest of the pipeline can't tell them apart:

| Invocation | Path | When to use |
|------------|------|-------------|
| `/schedule-update screenshots` (no arg) | **matplotlib (new)** — MCP fetch + Python render | Default. No browser automation; no SmartPM login. |
| `/schedule-update screenshots --legacy` | **Playwright (legacy)** — headless Chromium captures SmartPM | Fallback while matplotlib styling is being dialed in, or when a non-default chart isn't implemented yet. |

Both paths write into `{dated_folder}/screenshots/` with the same PNG filenames.

---

## Default path: matplotlib (no `--legacy` arg)

### Step 0: Pre-flight

- Python 3.10+
- `matplotlib`, `Pillow` installed: `pip install -r {skill_dir}/references/charts/requirements.txt`
- SmartPM MCP available in the session (the `mcp__...__smartpm_*` tools should be listed)

### Step 1: Read Project Context

Apply folder resolution. Read `project-context.html`. Extract:
- `graph_screenshots` — list of slugs to render
- `smartpm_project_name` — exact name to match on SmartPM
- `smartpm_url`

If `project-context.html` is missing, stop with the standard error.

### Step 2: Resolve project_id + scenario_id

```
project_id  = mcp__...__smartpm_list_projects matching smartpm_project_name
scenario_id = mcp__...__smartpm_list_scenarios(project_id) → newest
```

If no match: surface the names you got and ask the colleague.

### Step 3: Fetch + write payload JSONs

Create `{dated_folder}/.chart-payload/`. For each slug in `graph_screenshots` plus the summary parts, call the right MCP endpoint and write a canonical-shape JSON to `.chart-payload/{slug}.json`. The slug → endpoint mapping:

| Slug | MCP endpoint | Canonical shape |
|------|--------------|-----------------|
| `06-end-date-variance` | `smartpm_list_scenario_schedules_v2(scenario_id)` | `{"updates": [{"dataDate", "sourceEndDate"}, ...], "contractual_completion"}` |
| `07-schedule-compression-index-over-time` | `smartpm_get_scenario_schedule_compression_trend(scenario_id)` | `{"trend": [{"data_date", "value"}, ...]}` |
| `08-velocity` | `smartpm_get_scenario_velocity(scenario_id)` | `{"months": [{"month", "starts", "finishes"}, ...]}` |
| `09-spi-over-time` | `smartpm_get_scenario_spi_trend(scenario_id)` | `{"trend": [{"data_date", "value"}, ...]}` |
| `10-activity-hit-rate` | `smartpm_get_scenario_should_start_finish_trend(scenario_id)` → hit-rate series | `{"trend": [{"data_date", "value"}, ...]}` |
| `11-window-start-accuracy` | same endpoint → start-accuracy series | `{"trend": [{"data_date", "value"}, ...]}` |
| `12-window-finish-accuracy` | same endpoint → finish-accuracy series | `{"trend": [{"data_date", "value"}, ...]}` |
| `smartpm-summary-curve` | `smartpm_get_scenario_percent_complete_curve_v2` | `{"planned": [...], "actual": [...], "data_date"}` — see `charts.py:render_summary_plan_vs_actual` docstring |
| `smartpm-summary-cards` | composite: `smartpm_post_project_summary` (health/SPI/quality/compression/predicted/previous-predicted) | see `charts.py:render_summary_cards` docstring |
| `smartpm-summary-milestones` | composite: `smartpm_post_project_summary` called once per milestone scenario (defaultScenarioId for row 1, originalScenarioId for the Full Schedule row) + `smartpm_get_project` for location + `smartpm_list_scenario_change_log_by_type` for the CPD/recovery bullet items and Last Period Schedule Changes counts | see `charts.py:render_summary_milestones` docstring |

For any slug present in `graph_screenshots` that **isn't** in this table (i.e., one of the 9 non-default charts), the matplotlib path will raise `NotImplementedError`. That's the signal to suggest `--legacy` to the colleague.

### Step 4: Render

```bash
cd {skill_dir}/references
PYTHONPATH=. python -m charts.render {dated_folder}/.chart-payload {dated_folder}/screenshots
```

The script prints a JSON `{rendered: [...], failed: [...]}`. If anything is in `failed`, surface it to the colleague.

### Step 5: Verify

For each PNG named in `graph_screenshots` plus the summary parts: confirm exists in `{dated_folder}/screenshots/` and >0 bytes.

If a slug failed with `NotImplementedError`, tell the colleague:

> "Chart {slug} isn't implemented in the new matplotlib path yet. Run `/schedule-update screenshots --legacy` to capture it via the existing Playwright path."

### Step 6: Clean up

Delete `{dated_folder}/.chart-payload/` so the dated folder stays clean.

---

## Legacy path: `--legacy`

Everything in this section is the **unchanged** Playwright capture. It runs the same `references/smartpm/capture-smartpm.js` script the pipeline has used until now, end-to-end. Use it when a matplotlib chart isn't ready or doesn't look right yet.

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
