---
name: schedule-toolbox
description: >
  P6 XER schedule analysis, quality scoring, update review, path analysis, comparison, and
  generation. Trigger on: XER file, schedule quality, DCMA, SmartPM, float, critical path,
  resource loading, schedule update, trade activities, SC coverage, generate XER, build schedule.
---

# Schedule Toolbox

==============================================================================
!!!!!!!!!!!!!!!!!!  CRITICAL RULE -- NEVER WRITE XER FILES  !!!!!!!!!!!!!!!!!!
ALL ANALYSIS RUNS IN MEMORY ONLY. NEVER OVERWRITE ANY XER FILE.
HISTORICAL RECORDS MUST NEVER BE ALTERED BY ANALYSIS TOOLS.
EXCEPTION: Explicit user instruction to generate or modify a specific file.
==============================================================================

## Quick Routing

| Task | Where to look |
|------|--------------|
| Score schedule / check quality | `references/quality-checks.md` |
| What needs field updates by date X | `references/update-review.md` |
| What is trade X doing this month | `references/update-review.md` |
| Riding the data date | `references/update-review.md` |
| Parse / read XER | `references/xer-format.md` |
| Modify / write back XER | `references/xer-modify.md` |
| Run CPM, float, critical path | `references/cpm-usage.md` |
| Render the Gantt review HTML for proposal iteration | `references/cpm-usage.md` (§ Gantt Review HTML) |
| SC path coverage, delay impact | `references/analysis-tools.md` |
| Generate a new XER from scratch | `references/xer-generation.md` |
| XER table / field definitions | `references/xer-tables.md` (grep by table name) |

## Cardinal Rule

Do not read Python source files for routine operations. Call the CLI → get JSON → use it. Fall back to source only if the result seems wrong.
