# HTML+SVG Chart Migration (JavaScript) — Resume Handoff

> **For the next session picking this up:** read this file first, then the plan + spec it references. This is a bridge document — it captures where the work stands and how to resume without re-reading the whole transcript.

**Branch:** `claude/blissful-tharp-ad03c2`
**Worktree:** `C:\Users\camron\code\construction-skills\.claude\worktrees\blissful-tharp-ad03c2`
**Plan:** [`docs/superpowers/plans/2026-05-22-html-svg-chart-migration-javascript.md`](2026-05-22-html-svg-chart-migration-javascript.md)
**Spec:** [`docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md`](../specs/2026-05-22-html-svg-chart-migration-javascript-design.md)
**Active skill:** `superpowers:subagent-driven-development`

## What's done (5 of 12 tasks)

| # | Commit(s) | Description |
|---|---|---|
| Task 1 | `aeafccc` + `1bef7ee` | Bootstrap chart package — svg-lib, registry/meta/index/cli, workers-import smoke test, html_to_png.js → .cjs rename |
| Task 2 | `a6f109a` + `a107fb5` | Chart 01 (Planned VS Actual % Complete) — 6 series + data-date plotline |
| Task 3 | `6488e2e` | Chart 02 (Schedule Quality Grade™ Over Time) — single #2caffe straight line, categorical Y |
| Task 4 | `eca2c2b` | Chart 03 (Project Health Index™ Over Time) — line + per-point risk-colored markers |
| Task 5 | `d171261` | Chart 04 (Schedule Changes Over Time) — 7 smoothed splines + legend |

Test count: 68 passed / 1 skipped (workers-import skipped — wrangler not installed locally).
Typecheck clean.
Versions: scheduling plugin at `5.4.21` (both `plugin.json` and `marketplace.json`).

## Permanent deltas to plan-as-written (apply to ALL remaining tasks)

These three adjustments were forced by Task 1's code-review fixes. The plan-as-written has stale snippets in every chart-port task; apply these silently in every dispatch:

1. **`meta.js` MUST PRESERVE `renderPlaceholder` + `iconGlyph`** from Task 1's fix commit (`1bef7ee`). When adding a new META entry, only modify the import block and CHART_META object. Do NOT re-introduce `globalThis.__WESTLAND_CHART_META__`. Do NOT delete the `htmlEnvelope`/`escapeHtml` import from `./svg-lib.js`.

2. **`index.js`** re-exports `renderPlaceholder` from `./meta.js`, NOT `./svg-lib.js`. Plan snippets show `from './svg-lib.js'` — that's stale; use `./meta.js`.

3. **Chart files MUST use `parseDate` from `./svg-lib.js`** instead of inlining `new Date(\`${...}T00:00:00Z\`)`. The `parseDate` helper was extracted in Task 2's fix commit (`a107fb5`).

## Code-review pattern (what each task cycle looks like)

Per the subagent-driven-development skill, each task is:
1. Dispatch implementer subagent with full task text + the 3 stale-snippet adjustments above + working directory + version-bump rule
2. Implementer reports DONE
3. Dispatch reviewer (combined spec + code-quality has worked well — see Task 3+ history)
4. If reviewer flags Important issues, send fixes to same implementer; re-review
5. Mark task complete; move to next

Average per-task cost: ~3 subagent dispatches, ~150-200K tokens.

## NEXT UP — Task 6 (charts 05, 13, 14)

These are NEW charts with no Python implementation. They require **parent-agent Chrome MCP DOM inspection** on a data-rich SmartPM project (Wellington NZ Temple `113385` scenario `1644`, or Anchorage Alaska Temple `111751` scenario `1618`). Subagents cannot authenticate to SmartPM — the parent does all DOM inspection.

### Pre-Task-6 checklist

- [ ] Camron's Chrome is open
- [ ] SmartPM (https://app.smartpmtech.com) is signed in
- [ ] Wellington (113385) or Anchorage (111751) project is loaded, Trends tab visible
- [ ] Chrome MCP tools are available in the new session (deferred — load via ToolSearch as needed)

### Task 6 workflow (parent agent steps)

1. **Navigate** to `https://app.smartpmtech.com/projects/113385/scenarios/1644/trends` (or equivalent).
2. **For each chart 05, 13, 14**, scroll to that chart on the page and use Chrome MCP to:
   - Read the chart's `<svg>` element and capture every `stroke="..."` and `stroke-dasharray="..."` value (the palette).
   - Capture the legend labels (string values from `<text>` nodes or HTML).
   - Note the series count and the marker shape per series (if any).
   - Note Y-axis units / scale type (numeric? categorical?).
3. **Save the captured JSON** as `chart-{05,13,14}-inspection.json` in a notes folder (or just write it into the dispatch prompt for the subagent).
4. **Fetch the MCP payload** for each chart via the SmartPM MCP tool (`smartpm_get_scenario_delay` for 05; endpoints for 13 and 14 need confirmation via the DOM network tab or SmartPM MCP docs).
5. **Save the fixture** to `scheduling/skills/schedule-update/references/charts/tests/fixtures/{slug}.json`.
6. **Dispatch the implementer subagent** with the captured palette JSON + the fixture path + the standard chart-port instructions (apply the three stale-snippet adjustments).
7. **Review** the resulting commit (combined spec + quality, like Tasks 3-5).

Repeat for charts 13 (Missing Logic) and 14 (Average Total Float). Single commit for all three charts (commit 6 of the 12-commit plan).

## Tasks 7-12 (after Task 6)

- **Task 7:** Charts 15 (High Total Float), 16 (Critical Path Percentage) — same Chrome MCP workflow.
- **Task 8:** Charts 06 (End Date Variance), 07 (Schedule Compression Index) — REPLACE matplotlib approximations. Re-inspect DOM since matplotlib drift is expected.
- **Task 9:** Charts 08 (Velocity — 6 grouped bar series + average line + data-date marker, the heaviest), 09 (SPI — simple line).
- **Task 10:** Hit-rate trio (10/11/12). Shared `_hit-rate.js` helper, three thin entry wrappers.
- **Task 11:** Summary report composite (3 sections in 1 HTML). The hardest commit. See plan Task 11.
- **Task 12:** Cleanup — delete Python rendering + legacy Playwright capture. See plan Task 12.

## How to resume in a fresh session

Paste the prompt at the bottom of this file into a new Claude Code session opened at the worktree:

```
C:\Users\camron\code\construction-skills\.claude\worktrees\blissful-tharp-ad03c2
```

The resume prompt is self-contained — it tells the new agent to read this handoff + the plan + the spec, then continue from Task 6.

## Resume prompt (paste in a fresh session)

```
We're resuming the HTML+SVG chart migration on branch claude/blissful-tharp-ad03c2.
Read docs/superpowers/plans/2026-05-22-html-svg-chart-migration-javascript-RESUME.md
first — that handoff doc captures what's done (5 of 12 tasks) and how to resume.
Then read the plan + spec it references.

Use superpowers:subagent-driven-development to continue from Task 6. Apply the
three stale-snippet adjustments documented in the resume doc to every remaining
chart-port task. Chrome MCP DOM inspection (Tasks 6-10) is parent-agent-only —
subagents can't auth to SmartPM.

Continue executing until BLOCKED, all tasks done, or I tell you to stop.
```

## Useful commands for the resuming session

```bash
# Verify branch state
cd C:\Users\camron\code\construction-skills\.claude\worktrees\blissful-tharp-ad03c2
git log --oneline -10
git status

# Confirm tests still pass
cd scheduling/skills/schedule-update/references/charts
npm test
npm run typecheck

# Render all current charts to chart-previews/ (eyeball check)
cd C:\Users\camron\code\construction-skills\.claude\worktrees\blissful-tharp-ad03c2
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

## Open issues / known gaps (carry into Task 12 cleanup)

- **Chart 02 test coverage gaps** flagged in code review of Task 3: all-same-grade padding path, explicit flat-list test (currently only envelope form exercised), unrecognised-grade-skip behavior. Reviewer judged non-blocking.
- **Chart 03/04 marker/spline coverage**: no test asserts that paths actually use `C` (cubic Bezier) commands or per-series path count. Smoke render confirms it; regression to straight segments would slip past the committed tests.

Either backfill in Task 12 cleanup, or in a small follow-up commit between Tasks 5 and 6.
