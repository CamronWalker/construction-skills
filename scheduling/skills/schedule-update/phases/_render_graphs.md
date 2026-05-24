# _render_graphs — stack and rasterize the Worker's graph chunks

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `_render_graphs` phase; any divergence from it is a bug.
> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `draft.md`, and `report.md` as an internal dependency.

## Why this is internal

In v1 of the schedule-update skill, capturing graphs meant fetching ~17 SmartPM trend payloads via the SmartPM MCP, writing per-slug JSON to `.chart-payload/`, and running `references/charts/cli.js` to render local PNGs — all client-side. That entire pipeline now lives server-side in the `westland-mcps` Worker. The skill POSTs a v2 seed and the Worker enqueues SmartPM ingest async; by the time `finalize_weekly_schedule_update_email` returns, the payload contains `graphs.{slug}.html` (server-rendered HTML+SVG) for every entry in `graph_order`.

The local job shrinks to one step: stack the Worker's HTML chunks in `graph_order` order into one tall HTML page, then rasterize to a single PNG via `html_to_png.cjs`. That's what this phase covers.

## Inputs

- `{dated_folder}/{YYYY-MM-DD}-email.json` — the finalized draft loaded via `email_draft_io.load_draft(path)`. Must contain:
  - `this_week.graph_order` — list of slugs, canonical render order.
  - `graphs` — dict keyed by slug, values `{html, data}` with server-rendered SVG.
- The `references/charts/html_to_png.cjs` rasterizer + `references/package.json`'s Playwright install.

## Outputs

- `{dated_folder}/screenshots/{job_number}-{YYYY-MM-DD}-all-graphs-stacked.png` — one PNG, ~1200×N px (tall), containing all 9 default chart cards stacked vertically. Embedded as a single inline image in the `.eml` body.

## Process

The orchestrator function in `email_draft_io.py` already does all of this. Drive it from `phases/draft.md`'s build step:

```python
import sys, os
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft, render_stacked_png

draft = load_draft(os.path.join(dated_folder, f'{report_date_iso}-email.json'))
stacked_png = render_stacked_png(draft, output_dir=os.path.join(dated_folder, 'screenshots'))
# stacked_png is the absolute path to the PNG; pass it as summary_screenshot_path
# kwarg to the .eml builder.
```

`render_stacked_png` internally:
1. Reads `draft['this_week']['graph_order']` (defaults to insertion order of `graphs` if missing).
2. Calls `build_stacked_chart_page(graphs, order)` to concatenate chunks into one HTML page (1200px viewport, no per-card width transforms — SVG scales crisply).
3. Writes a temp HTML file in the output dir.
4. Runs `node html_to_png.cjs <tmp_html> <png_path> --width=1200 --full-page` via subprocess (120s timeout).
5. Deletes the temp HTML, returns the absolute PNG path.

## What to do if graphs aren't ready

The Worker's `finalize_weekly_schedule_update_email` response includes `graphs_ready_count` and `graphs_total`. If `graphs_ready_count < graphs_total`, some chart cards in `graphs.{slug}.html` will be placeholder SVGs ("Data not yet available" or "Render failed"). Stacking and rasterizing still works — the PNG will contain placeholder cards alongside the ready ones.

Two options when this happens:
- **Wait and re-finalize.** SmartPM usually finishes within ~20 minutes of XER upload. Sleep, then call `finalize_weekly_schedule_update_email` again. Each finalize call returns a fresh snapshot — placeholders update to real cards as the Worker finishes them.
- **Ship with placeholders.** Rare, only if the data is truly unavailable (e.g. SmartPM project deleted). Warn the colleague before proceeding.

`phases/draft.md`'s build step is the right place to gate on this — it has the finalize response in scope.

## What this phase explicitly does NOT do

- Call SmartPM MCP endpoints directly (`smartpm_get_scenario_*`, `smartpm_post_project_summary`, etc.). Those are Worker concerns now.
- Write per-slug `.chart-payload/{slug}.json` files or run `charts/cli.js`. That pipeline is retired for the email use case. The `references/charts/` library survives in the skill for ad-hoc / future use but is not part of the email build.
- Render individual chart PNGs. One stacked PNG holds everything.

## Why one stacked PNG instead of per-slug PNGs

Pre-cloud-editor, the .eml embedded each chart as its own inline image (one `<img cid:slug>` per chart). That's ~10 inline images per email and Outlook's compose-mode loader handled them inconsistently when the recipient list was long. Stacking them into one PNG sidesteps that — one `Content-ID` reference, one image part, identical rendering on classic and new Outlook.

## Cross-references

- `phases/draft.md` — calls `render_stacked_png` after `finalize_weekly_schedule_update_email`.
- `phases/email.md` — the `.eml` build step that consumes `summary_screenshot_path`.
- `references/email_draft_io.py` — implementation of `render_stacked_png`, `build_stacked_chart_page`, `generate_email_from_draft`.
- `references/charts/html_to_png.cjs` — the Node rasterizer (Playwright-backed).
- scheduling/CLAUDE.md "Email JSON shape — single source of truth" — defines `graphs.{slug}.html` shape.
