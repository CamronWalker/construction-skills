# Westland Scheduler Local MCP — Plan 2: Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Tier 1 update-analytics tools (`get_critical_path_changes`, `get_float_consumption`, `get_trade_slip_summary`, `get_gain_loss_attribution`) and the Tier 2 delay-analysis tools (`compute_tia`, `compute_window_analysis`, `compute_change_order_delay`, `get_concurrent_delay_pairs`), wire the two Plan-1-stubbed subkeys of `weekly_update_review` to their real implementations, and clean up the duplicated helpers / hard-coded params / missing test coverage that the Plan-1 review flagged. On release, schedulers get answers to "why did SC change this week — gain or loss, and who drove it" and "what's the TIA for this RFI?" without leaving Claude.

**Architecture:** Two new lib modules (`scheduling/skills/schedule-toolbox/lib/cross_baseline.py` for the cross-XER analytics, `scheduling/skills/schedule-toolbox/lib/delay_analysis.py` for the TIA / window / change-order / concurrent calculations). Each lib function gets its own TDD cycle at the lib level — these are real algorithms, not thin wrappers. The MCP tool adapters in `scheduling/mcp-server/tools/update_analytics.py` and `scheduling/mcp-server/tools/delay_analysis.py` follow the F1–F5 pattern: parse inputs, call the lib via `CpmCache.get_cpm`, marshal into JSON. No new caching layer required — `extract_paths` is an in-memory traversal on already-cached CPM results, so cross-baseline tools call `cache.get_cpm` on each side independently and the cache LRU at 8 entries comfortably covers a weekly-update workflow plus side queries.

**Tech Stack:**
- Python 3.10+ (Plan 1 prereq)
- Official `mcp` Python SDK (Plan 1 prereq)
- Standard library `unittest` for tests
- Existing CPM engine, parser, and `extract_paths` in `schedule-toolbox/lib/`

**Reference spec:** [2026-05-24-schedule-toolbox-mcp-design.md](../specs/2026-05-24-schedule-toolbox-mcp-design.md) — sections "Update analytics tools (new — derived from compare primitives)" and "Delay analysis tools (new — `lib/delay_analysis.py`)".

**Predecessor plan:** [2026-05-24-westland-scheduler-mcp-plan-1-foundation.md](2026-05-24-westland-scheduler-mcp-plan-1-foundation.md) — must be merged and the MCP server registered before Plan 2 execution starts. Plan 2 picks up the F-batch tools as fixed infrastructure.

---

## File Structure

### New files

| Path | Responsibility |
|------|----------------|
| `scheduling/mcp-server/tools/_common.py` | Shared helpers consolidated from `quality.py` + `omnibus.py` + `cpm_path.py`: `data_date_str(parsed)`, `data_date_dt(parsed)`, `FUTURE_DATE_SENTINEL = "2099-12-31"`, `resolve_metadata_for_milestone(metadata, milestone_id, tasks)` (moved from `cpm_path._resolve_metadata_for_milestone`). One canonical location; the F-batch modules import from here. |
| `scheduling/skills/schedule-toolbox/lib/cross_baseline.py` | Cross-XER CPM-aware analytics: `compute_critical_path_changes(...)`, `compute_float_consumption(...)`, `compute_trade_slip_summary(...)`, `compute_gain_loss_attribution(...)`. Operates on `(baseline_parsed, current_parsed, baseline_cpm, current_cpm)` quads passed by the MCP layer. |
| `scheduling/skills/schedule-toolbox/lib/delay_analysis.py` | Forensic delay calculations: `compute_tia(...)`, `compute_window_analysis(...)`, `compute_change_order_delay(...)`, `find_concurrent_delay_pairs(...)`. TIA inserts a fragnet and re-runs CPM in a copy of the parsed tables; the others operate on the cached `(parsed, cpm)` pairs from both sides. |
| `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py` | Lib-level tests for the four `cross_baseline.py` functions. TDD-first: each algorithm has a fixture-driven test that pins behavior before the MCP wrapper is written. |
| `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py` | Lib-level tests for the four `delay_analysis.py` functions. |
| `scheduling/mcp-server/tools/update_analytics.py` | MCP tool adapters for the four Tier 1 tools. Same `_impl(...)` + `register(mcp, cache)` shape as Plan 1's F-batch modules. |
| `scheduling/mcp-server/tools/delay_analysis.py` | MCP tool adapters for the four Tier 2 tools. |
| `scheduling/mcp-server/tests/test_update_analytics.py` | MCP-wrapper tests for the Tier 1 tools (smoke tests that the `_impl` functions invoke the lib correctly and project the right JSON shape). |
| `scheduling/mcp-server/tests/test_delay_analysis.py` | MCP-wrapper tests for the Tier 2 tools. |
| `scheduling/mcp-server/tests/fixtures/cp_baseline.xer` | 6-activity schedule with a single dominant critical path (NTP → A1000 → A1010 → A1020 → SC) plus a parallel non-critical chain. Used by `compute_critical_path_changes` tests. |
| `scheduling/mcp-server/tests/fixtures/cp_shifted.xer` | Same activity set as `cp_baseline.xer`, but the parallel chain's durations grew enough that the critical path now runs through it instead. Tests "critical path shifted from chain A to chain B." |
| `scheduling/mcp-server/tests/fixtures/multi_terminal.xer` | Two unrelated terminal milestones (no successors, both `TT_FinMile`). Exercises `MilestoneAmbiguousError` paths in every milestone-scoped tool — was flagged as a Plan-1 review gap. |
| `scheduling/mcp-server/tests/fixtures/multi_driver_slip_baseline.xer` | 8-activity schedule with NTP → 3 parallel chains → SC, all on the critical path. Used as the baseline for gain/loss attribution and trade-slip tests. |
| `scheduling/mcp-server/tests/fixtures/multi_driver_slip_current.xer` | Same activity set as `multi_driver_slip_baseline.xer`, hand-tuned so the SC slip has three *distinct* drivers: chain A has a duration_change (one task grew 3 days), chain B has a logic_change (a new FS predecessor was added), chain C has an operational_slip (an activity started 5 days late per actual dates). Used to test that `compute_gain_loss_attribution` populates all three category buckets correctly and that residual_days is small. |
| `scheduling/mcp-server/tests/fixtures/tia_baseline.xer` | 4-activity linear schedule (NTP → A1000 → A1010 → SC) suitable for TIA fragnet insertion testing. The fragnet inserts between A1000 and A1010 and pushes SC out. |
| `scheduling/mcp-server/tests/fixtures/concurrent_delay_baseline.xer` + `concurrent_delay_current.xer` | Two activities on independent parallel chains that both slip in the current snapshot. Used to test `find_concurrent_delay_pairs` surfaces both as a concurrent pair. |

### Modified files

| Path | Change |
|------|--------|
| `scheduling/mcp-server/tools/cpm_path.py` | Replace local `_resolve_metadata_for_milestone` with import from `_common`. No behavior change. |
| `scheduling/mcp-server/tools/quality.py` | Replace local `_data_date` with import from `_common.data_date_str`. No behavior change. |
| `scheduling/mcp-server/tools/omnibus.py` | Replace local `_data_date_str` / `_data_date_dt` / `_FUTURE_DATE_SENTINEL` with imports from `_common`. Wire `weekly_update_review_impl` to call into the new `get_critical_path_changes` and `get_gain_loss_attribution` lib functions (Phase H). Expose `match_by` as a tool parameter (default `"task_code"`) per the Plan-1 reviewer note. Remove the `pending_plan_2: True` flag. |
| `scheduling/mcp-server/server.py` | Add `update_analytics.register(mcp, _cache)` and `delay_analysis.register(mcp, _cache)` calls alongside the existing module registrations. |
| `scheduling/mcp-server/tests/test_server.py` | Add an assertion that at least one tool from each registered module appears in the discovered tool list (`get_critical_path_changes` for update_analytics, `compute_tia` for delay_analysis, plus representatives from each Plan-1 batch). Catches `register()` call typos in `server.py` — the gap the Plan-1 reviewer flagged. |
| `scheduling/mcp-server/tests/test_cpm_path.py` | Add a test against `multi_terminal.xer` that confirms `get_milestone_path_coverage` (and one other milestone-scoped tool) raises `MilestoneAmbiguousError` carrying both candidates when `milestone_id` is omitted. |
| `scheduling/.claude-plugin/plugin.json` | Bump `version` to `8.0.0`. |
| `.claude-plugin/marketplace.json` | Bump matching scheduling plugin entry to `8.0.0`. |

### Why a major version bump

Strictly, adding new tools is a minor bump. The omnibus `weekly_update_review` output, however, changes shape: the Plan-1 stubs (`critical_path_changes: null`, `gain_loss_attribution: null`, `pending_plan_2: true`) are filled in and the flag is removed. Any external caller depending on the stub shape breaks. `weekly_update_review` also gains a `match_by` parameter, which is backwards-compatible (default preserved) but worth signalling. Treat as 8.0.0 to make the omnibus shape change visible to anyone pinning a plugin version.

---

## Phase A: Consolidate shared helpers in `tools/_common.py`

Goal: replace the three duplicated copies of `_data_date_*` and the two copies of the future-date sentinel with one canonical module that the F-batch tools import from. Done before Tier 1 so the new tools start out using the consolidated helpers — not perpetuating the duplication.

### Task A1: Create `tools/_common.py` with the four helpers

**Files:**
- Create: `scheduling/mcp-server/tools/_common.py`
- Create: `scheduling/mcp-server/tests/test_common.py`

- [ ] **Step 1: Write failing tests for the shared helpers**

Create `scheduling/mcp-server/tests/test_common.py`:

```python
"""Tests for the shared helper module ``tools/_common.py``.

The helpers were duplicated across ``quality.py``, ``omnibus.py``, and
``cpm_path.py`` in Plan 1; this module consolidates them. Tests pin the
behavior we're preserving so the duplicated-source removals are safe.
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from tools._common import (  # noqa: E402
    FUTURE_DATE_SENTINEL,
    data_date_dt,
    data_date_str,
    resolve_metadata_for_milestone,
)


class TestDataDateStr(unittest.TestCase):
    def test_prefers_last_recalc_date(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25", "data_date": ""}]}
        self.assertEqual(data_date_str(parsed), "2026-05-25")

    def test_falls_back_to_data_date(self):
        parsed = {"PROJECT": [{"last_recalc_date": "", "data_date": "2026-05-20"}]}
        self.assertEqual(data_date_str(parsed), "2026-05-20")

    def test_empty_strings_collapse_to_none(self):
        parsed = {"PROJECT": [{"last_recalc_date": "", "data_date": ""}]}
        self.assertIsNone(data_date_str(parsed))

    def test_missing_project_returns_none(self):
        self.assertIsNone(data_date_str({}))

    def test_empty_project_returns_none(self):
        self.assertIsNone(data_date_str({"PROJECT": []}))


class TestDataDateDt(unittest.TestCase):
    def test_parses_datetime_format(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25 08:00"}]}
        self.assertEqual(data_date_dt(parsed), datetime(2026, 5, 25, 8, 0))

    def test_parses_date_only_format(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25"}]}
        self.assertEqual(data_date_dt(parsed), datetime(2026, 5, 25, 0, 0))

    def test_unparseable_returns_none(self):
        parsed = {"PROJECT": [{"last_recalc_date": "not-a-date"}]}
        self.assertIsNone(data_date_dt(parsed))

    def test_none_data_date_returns_none(self):
        self.assertIsNone(data_date_dt({}))


class TestFutureDateSentinel(unittest.TestCase):
    def test_value_matches_spec(self):
        self.assertEqual(FUTURE_DATE_SENTINEL, "2099-12-31")


class TestResolveMetadataForMilestone(unittest.TestCase):
    def test_none_milestone_returns_metadata_unchanged(self):
        metadata = {"sc_milestone_id": "A1000", "sc_milestone_name": "OldName"}
        result = resolve_metadata_for_milestone(metadata, None, [])
        self.assertIs(result, metadata)  # no copy — same object

    def test_explicit_milestone_sets_id(self):
        metadata = {"sc_milestone_id": "A1000"}
        tasks = [{"task_id": "T999", "task_name": "Custom SC", "task_code": "C9",
                  "early_end_date": "2026-12-31 17:00"}]
        result = resolve_metadata_for_milestone(metadata, "T999", tasks)
        self.assertEqual(result["sc_milestone_id"], "T999")
        self.assertEqual(result["sc_milestone_name"], "Custom SC")
        self.assertEqual(result["sc_milestone_code"], "C9")
        self.assertEqual(result["sc_milestone_date"], "2026-12-31 17:00")
        self.assertIsNot(result, metadata)  # shallow copy — original untouched

    def test_explicit_milestone_not_in_tasks_leaves_name_blank(self):
        metadata = {"sc_milestone_id": "A1000"}
        result = resolve_metadata_for_milestone(metadata, "MISSING", [])
        self.assertEqual(result["sc_milestone_id"], "MISSING")
        self.assertNotIn("sc_milestone_name", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m unittest scheduling.mcp-server.tests.test_common -v
```

Expected: ImportError on `tools._common`.

- [ ] **Step 3: Implement `tools/_common.py`**

Create `scheduling/mcp-server/tools/_common.py`:

```python
"""Shared helpers across the MCP tool modules.

Consolidates the four pieces that were duplicated across ``quality.py``,
``omnibus.py``, and ``cpm_path.py`` in Plan 1:

* :func:`data_date_str` — pull the data_date string out of parsed PROJECT.
* :func:`data_date_dt` — like ``data_date_str`` but parsed to a ``datetime``.
* :const:`FUTURE_DATE_SENTINEL` — far-future date used when a caller doesn't
  pass an explicit window for activities-to-start / activities-to-finish.
* :func:`resolve_metadata_for_milestone` — shallow-copy CPM metadata with
  ``sc_milestone_*`` keys overridden to point at a caller-supplied milestone.

The F-batch modules import from here. New analytics modules in Plan 2 do the
same so a fifth copy doesn't sprout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

# Sentinel future date used internally when ``expected_updates`` (or similar
# date-windowed helpers) need an upper bound but the caller didn't pass one.
# Mirrors the value that lived in ``tools/omnibus.py`` and the same constant
# inlined into ``tools/update_review.py`` -- one canonical home now.
FUTURE_DATE_SENTINEL = "2099-12-31"


def data_date_str(parsed: dict) -> Optional[str]:
    """Pull the data_date string out of the parsed PROJECT table.

    Returns ``None`` in three cases:
      * the PROJECT table is missing from ``parsed``
      * the PROJECT table is present but empty
      * the PROJECT row's ``last_recalc_date`` and ``data_date`` are both
        absent or empty strings

    Downstream library checks branch on ``if data_date is None`` to skip
    date-aware comparisons, so collapsing empty strings to ``None`` is the
    intended behavior -- empty strings would otherwise compare unequal to
    anything and produce spurious "after data date" hits.
    """
    project_rows = parsed.get("PROJECT") or [{}]
    return (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
        or None
    )


def data_date_dt(parsed: dict) -> Optional[datetime]:
    """Like :func:`data_date_str` but returns a parsed ``datetime``.

    Accepts both ``%Y-%m-%d %H:%M`` and ``%Y-%m-%d`` -- the two formats
    seen in real Westland XERs. Returns ``None`` when no format matches
    so the library's no-date branches take over rather than raising.
    """
    s = data_date_str(parsed)
    if s is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def resolve_metadata_for_milestone(
    metadata: dict, milestone_id, tasks: list
) -> dict:
    """Return a metadata dict with ``sc_milestone_*`` fields set to the
    explicit ``milestone_id``.

    When ``milestone_id`` is ``None`` the original metadata is returned
    unchanged (no copy) so the common case is free. When non-None, a
    shallow copy is made and the ``sc_milestone_*`` keys are overridden to
    point at the caller-supplied milestone -- the cached CPM result is
    never mutated.
    """
    if milestone_id is None:
        return metadata
    new_meta = dict(metadata)
    new_meta["sc_milestone_id"] = milestone_id
    for t in tasks:
        if t.get("task_id") == milestone_id:
            new_meta["sc_milestone_name"] = t.get("task_name", "")
            new_meta["sc_milestone_code"] = t.get("task_code", "")
            new_meta["sc_milestone_date"] = t.get("early_end_date", "")
            break
    return new_meta
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
python -m unittest scheduling.mcp-server.tests.test_common -v
```

Expected: 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/tools/_common.py scheduling/mcp-server/tests/test_common.py
git commit -m "feat(scheduling): consolidate F-batch shared helpers in tools/_common.py"
```

### Task A2: Replace duplicated copies in `quality.py`, `omnibus.py`, and `cpm_path.py`

**Files:**
- Modify: `scheduling/mcp-server/tools/quality.py`
- Modify: `scheduling/mcp-server/tools/omnibus.py`
- Modify: `scheduling/mcp-server/tools/cpm_path.py`

- [ ] **Step 1: Update `quality.py` to import from `_common`**

In `scheduling/mcp-server/tools/quality.py`:

Replace the local `_data_date` definition:

```python
def _data_date(parsed: dict) -> Optional[str]:
    """Pull the data_date string out of the parsed PROJECT table.
    # ... docstring ...
    """
    project_rows = parsed.get("PROJECT") or [{}]
    return (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
        or None
    )
```

with an import:

```python
from tools._common import data_date_str as _data_date  # noqa: E402
```

Place the import alongside the other top-level imports near the top of the file (after the `sys.path.insert` block, before the `from quality_checks import ...` block).

Leave every internal callsite (`_data_date(parsed)`) unchanged — the alias keeps the local-name shape so existing call sites are byte-identical.

- [ ] **Step 2: Update `omnibus.py` to import from `_common`**

In `scheduling/mcp-server/tools/omnibus.py`:

Delete the local definitions of `_data_date_str`, `_data_date_dt`, and `_FUTURE_DATE_SENTINEL`. Replace with:

```python
from tools._common import (  # noqa: E402
    FUTURE_DATE_SENTINEL as _FUTURE_DATE_SENTINEL,
    data_date_dt as _data_date_dt,
    data_date_str as _data_date_str,
)
```

Leave every internal callsite unchanged — the aliases keep the existing private-name shape.

- [ ] **Step 3: Update `cpm_path.py` to import from `_common`**

In `scheduling/mcp-server/tools/cpm_path.py`:

Delete the local `_resolve_metadata_for_milestone` function. Replace with:

```python
from tools._common import resolve_metadata_for_milestone as _resolve_metadata_for_milestone  # noqa: E402
```

Existing callsites (e.g. `get_critical_path_impl`) keep using the local underscore name via the alias.

- [ ] **Step 4: Run the full test suite to confirm no regression**

```bash
python -m unittest discover -s scheduling/mcp-server/tests -v
```

Expected: every Plan 1 test still passes plus the new `test_common.py`. If any F-batch test fails, that's a sign the alias rename hasn't been applied consistently — fix the callsite and re-run.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/tools/quality.py scheduling/mcp-server/tools/omnibus.py scheduling/mcp-server/tools/cpm_path.py
git commit -m "refactor(scheduling): F-batch tools import shared helpers from tools/_common"
```

---

## Phase B: Cross-baseline test fixtures

Goal: stand up the XER fixtures that Phase C's lib tests and Phase D's MCP tests depend on. Doing the fixtures up front keeps the TDD cycles in C/D focused on algorithm correctness rather than fixture authoring.

All Plan 2 fixtures mirror the Plan 1 `minimal.xer` format: tab-delimited, single PROJECT row, single CALENDAR row (the standard 5-day calendar), single PROJWBS row, then per-fixture TASK + TASKPRED rows. The implementer copies `minimal.xer`'s header tables verbatim and customizes only the TASK / TASKPRED rows.

### Task B1: `multi_terminal.xer` fixture

**Files:**
- Create: `scheduling/mcp-server/tests/fixtures/multi_terminal.xer`

- [ ] **Step 1: Build the fixture**

Take `scheduling/mcp-server/tests/fixtures/minimal.xer` as the template. Keep the ERMHDR, CURRTYPE, PROJECT, CALENDAR, SCHEDOPTIONS, and PROJWBS tables verbatim. Replace the TASK and TASKPRED tables with this content (preserve tab delimiters exactly):

```
%T	TASK
%F	task_id	proj_id	wbs_id	clndr_id	phys_complete_pct	rev_fdbk_flag	est_wt	lock_plan_flag	auto_compute_act_flag	complete_pct_type	task_type	duration_type	status_code	task_code	task_name	rsrc_id	total_float_hr_cnt	free_float_hr_cnt	remain_drtn_hr_cnt	act_work_qty	remain_work_qty	target_work_qty	target_drtn_hr_cnt	target_equip_qty	act_equip_qty	remain_equip_qty	cstr_date	act_start_date	act_end_date	late_start_date	late_end_date	expect_end_date	early_start_date	early_end_date	restart_date	reend_date	target_start_date	target_end_date	rem_late_start_date	rem_late_end_date	cstr_type	priority_type	suspend_date	resume_date	float_path	float_path_order	guid	tmpl_guid	cstr_date2	cstr_type2	driving_path_flag	act_this_per_work_qty	act_this_per_equip_qty	external_early_start_date	external_late_end_date	create_date	update_date	create_user	update_user	location_id	crt_path_num
%R	20001	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Mile	DT_FixedDUR2	TK_NotStart	M0000	NTP				0	0	0	0	0	0	0	0	0	0				2026-05-25 08:00	2026-05-25 08:00		2026-05-25 08:00	2026-05-25 08:00			2026-05-25 08:00	2026-05-25 08:00				PT_Normal					MT-NTP-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	20002	1	1000	100	0	N	1	N	N	CP_Drtn	TT_FinMile	DT_FixedDUR2	TK_NotStart	M9000	Final Acceptance				0	0	0	0	0	0	0	0	0	0				2026-08-15 17:00	2026-08-15 17:00		2026-08-15 17:00	2026-08-15 17:00			2026-08-15 17:00	2026-08-15 17:00				PT_Normal					MT-FA-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	20003	1	1000	100	0	N	1	N	N	CP_Drtn	TT_FinMile	DT_FixedDUR2	TK_NotStart	M9100	TCO			0	0	0	0	0	0	0	0	0	0				2026-08-01 17:00	2026-08-01 17:00		2026-08-01 17:00	2026-08-01 17:00			2026-08-01 17:00	2026-08-01 17:00				PT_Normal					MT-TCO-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%T	TASKPRED
%F	task_pred_id	task_id	pred_task_id	proj_id	pred_proj_id	pred_type	lag_hr_cnt	comments	float_path	aref	arls
%R	7001	20002	20001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	7002	20003	20001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%E
```

The fixture has NTP → Final Acceptance (M9000) and NTP → TCO (M9100). Both are `TT_FinMile` and neither has a successor — two terminal milestones, ambiguous which is "the" SC.

- [ ] **Step 2: Verify the fixture parses cleanly**

```bash
python -c "import sys; sys.path.insert(0, 'scheduling/mcp-server'); from cache import CpmCache; c = CpmCache(); p = c.get_parsed('scheduling/mcp-server/tests/fixtures/multi_terminal.xer'); print('OK tasks=', len(p['TASK']), 'preds=', len(p['TASKPRED']))"
```

Expected: `OK tasks= 3 preds= 2`. If the parser errors, hand-fix the tab-delimited rows until it loads.

- [ ] **Step 3: Commit**

```bash
git add scheduling/mcp-server/tests/fixtures/multi_terminal.xer
git commit -m "test(scheduling): multi_terminal.xer fixture for ambiguity-error coverage"
```

### Task B2: `cp_baseline.xer` + `cp_shifted.xer` fixture pair

**Files:**
- Create: `scheduling/mcp-server/tests/fixtures/cp_baseline.xer`
- Create: `scheduling/mcp-server/tests/fixtures/cp_shifted.xer`

- [ ] **Step 1: Build `cp_baseline.xer`**

Same header tables as `minimal.xer`. TASK + TASKPRED:

```
%T	TASK
%F	task_id	proj_id	wbs_id	clndr_id	phys_complete_pct	rev_fdbk_flag	est_wt	lock_plan_flag	auto_compute_act_flag	complete_pct_type	task_type	duration_type	status_code	task_code	task_name	rsrc_id	total_float_hr_cnt	free_float_hr_cnt	remain_drtn_hr_cnt	act_work_qty	remain_work_qty	target_work_qty	target_drtn_hr_cnt	target_equip_qty	act_equip_qty	remain_equip_qty	cstr_date	act_start_date	act_end_date	late_start_date	late_end_date	expect_end_date	early_start_date	early_end_date	restart_date	reend_date	target_start_date	target_end_date	rem_late_start_date	rem_late_end_date	cstr_type	priority_type	suspend_date	resume_date	float_path	float_path_order	guid	tmpl_guid	cstr_date2	cstr_type2	driving_path_flag	act_this_per_work_qty	act_this_per_equip_qty	external_early_start_date	external_late_end_date	create_date	update_date	create_user	update_user	location_id	crt_path_num
%R	30001	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Mile	DT_FixedDUR2	TK_NotStart	M0000	NTP				0	0	0	0	0	0	0	0	0	0				2026-05-25 08:00	2026-05-25 08:00		2026-05-25 08:00	2026-05-25 08:00			2026-05-25 08:00	2026-05-25 08:00				PT_Normal					CPB-NTP-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	30002	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	A1000	Critical Chain A1			0	0	80	0	80	80	80	0	0	0				2026-05-25 08:00	2026-06-05 17:00		2026-05-25 08:00	2026-06-05 17:00			2026-05-25 08:00	2026-06-05 17:00				PT_Normal					CPB-A1-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	30003	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	A1010	Critical Chain A2			0	0	80	0	80	80	80	0	0	0				2026-06-08 08:00	2026-06-19 17:00		2026-06-08 08:00	2026-06-19 17:00			2026-06-08 08:00	2026-06-19 17:00				PT_Normal					CPB-A2-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	30004	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	B1000	Parallel Chain B1			80	80	40	0	40	40	40	0	0	0				2026-05-25 08:00	2026-05-29 17:00		2026-06-15 08:00	2026-06-19 17:00			2026-05-25 08:00	2026-05-29 17:00				PT_Normal					CPB-B1-GUID				N	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	30005	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	B1010	Parallel Chain B2			80	80	40	0	40	40	40	0	0	0				2026-06-01 08:00	2026-06-05 17:00		2026-06-22 08:00	2026-06-26 17:00			2026-06-01 08:00	2026-06-05 17:00				PT_Normal					CPB-B2-GUID				N	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	30006	1	1000	100	0	N	1	N	N	CP_Drtn	TT_FinMile	DT_FixedDUR2	TK_NotStart	M9000	Substantial Completion			0	0	0	0	0	0	0	0	0	0				2026-06-22 08:00	2026-06-22 08:00		2026-06-22 08:00	2026-06-22 08:00			2026-06-22 08:00	2026-06-22 08:00				PT_Normal					CPB-SC-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%T	TASKPRED
%F	task_pred_id	task_id	pred_task_id	proj_id	pred_proj_id	pred_type	lag_hr_cnt	comments	float_path	aref	arls
%R	8001	30002	30001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	8002	30003	30002	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	8003	30006	30003	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	8004	30004	30001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	8005	30005	30004	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	8006	30006	30005	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%E
```

Baseline critical path: NTP → A1000 (10d) → A1010 (10d) → SC. The B-chain (B1000 5d → B1010 5d) is parallel and has 80hr (= 10 working day) float.

- [ ] **Step 2: Build `cp_shifted.xer`**

Copy `cp_baseline.xer`. Change B1000's `target_drtn_hr_cnt` / `remain_drtn_hr_cnt` from `40` to `80` (5d → 10d). Change B1010's `target_drtn_hr_cnt` / `remain_drtn_hr_cnt` from `40` to `120` (5d → 15d). Update the early_start / early_end / late_start / late_end dates on B1000, B1010, and SC accordingly so the parsed values are consistent (B-chain is now 25 working days vs A-chain's 20 — B-chain is the new critical path).

Specifically:
- B1000: early_start 2026-05-25 08:00, early_end 2026-06-05 17:00 (10 working days)
- B1010: early_start 2026-06-08 08:00, early_end 2026-06-26 17:00 (15 working days)
- SC: pushed from 2026-06-22 to 2026-06-29 08:00 (B-chain end + 1 working day)
- A-chain dates and durations unchanged

Also flip `driving_path_flag` for the B-chain tasks from `N` to `Y`, and flip A-chain's from `Y` to `N`. This mirrors what P6 would write after a reschedule.

- [ ] **Step 3: Verify both fixtures parse and CPM cleanly**

```bash
python -c "
import sys
sys.path.insert(0, 'scheduling/mcp-server')
from cache import CpmCache
c = CpmCache()
for fname in ('cp_baseline.xer', 'cp_shifted.xer'):
    path = f'scheduling/mcp-server/tests/fixtures/{fname}'
    p = c.get_parsed(path)
    results, meta = c.get_cpm(path)
    print(fname, 'tasks=', len(p['TASK']), 'sc=', meta.get('sc_milestone_id'))
"
```

Expected: both load, each reports 6 tasks. The `sc_milestone_id` may differ (it's whichever terminal milestone the lib auto-picks); for these fixtures there's only one terminal so it's unambiguous.

- [ ] **Step 4: Commit**

```bash
git add scheduling/mcp-server/tests/fixtures/cp_baseline.xer scheduling/mcp-server/tests/fixtures/cp_shifted.xer
git commit -m "test(scheduling): cp_baseline/cp_shifted fixture pair for CP-change tests"
```

### Task B3: `multi_driver_slip_baseline.xer` + `multi_driver_slip_current.xer` fixture pair

**Files:**
- Create: `scheduling/mcp-server/tests/fixtures/multi_driver_slip_baseline.xer`
- Create: `scheduling/mcp-server/tests/fixtures/multi_driver_slip_current.xer`

- [ ] **Step 1: Build `multi_driver_slip_baseline.xer`**

Same header tables as `minimal.xer`. The schedule has NTP + 3 parallel chains (A, B, C) that each merge into SC. Each chain has 2 activities. All 6 activities are on the critical path (no float — engineered for testing).

```
%T	TASK
%F	[same field header as previous fixtures]
%R	40001	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Mile	DT_FixedDUR2	TK_NotStart	M0000	NTP				0	0	0	0	0	0	0	0	0	0				2026-05-25 08:00	2026-05-25 08:00		2026-05-25 08:00	2026-05-25 08:00			2026-05-25 08:00	2026-05-25 08:00				PT_Normal					MDS-NTP-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40002	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	A1000	Trade A Front			0	0	80	0	80	80	80	0	0	0				2026-05-25 08:00	2026-06-05 17:00		2026-05-25 08:00	2026-06-05 17:00			2026-05-25 08:00	2026-06-05 17:00				PT_Normal					MDS-A1-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40003	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	A1010	Trade A Back			0	0	80	0	80	80	80	0	0	0				2026-06-08 08:00	2026-06-19 17:00		2026-06-08 08:00	2026-06-19 17:00			2026-06-08 08:00	2026-06-19 17:00				PT_Normal					MDS-A2-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40004	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	B1000	Trade B Front			0	0	80	0	80	80	80	0	0	0				2026-05-25 08:00	2026-06-05 17:00		2026-05-25 08:00	2026-06-05 17:00			2026-05-25 08:00	2026-06-05 17:00				PT_Normal					MDS-B1-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40005	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	B1010	Trade B Back			0	0	80	0	80	80	80	0	0	0				2026-06-08 08:00	2026-06-19 17:00		2026-06-08 08:00	2026-06-19 17:00			2026-06-08 08:00	2026-06-19 17:00				PT_Normal					MDS-B2-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40006	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	C1000	Trade C Front			0	0	80	0	80	80	80	0	0	0				2026-05-25 08:00	2026-06-05 17:00		2026-05-25 08:00	2026-06-05 17:00			2026-05-25 08:00	2026-06-05 17:00				PT_Normal					MDS-C1-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40007	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	C1010	Trade C Back			0	0	80	0	80	80	80	0	0	0				2026-06-08 08:00	2026-06-19 17:00		2026-06-08 08:00	2026-06-19 17:00			2026-06-08 08:00	2026-06-19 17:00				PT_Normal					MDS-C2-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	40008	1	1000	100	0	N	1	N	N	CP_Drtn	TT_FinMile	DT_FixedDUR2	TK_NotStart	M9000	Substantial Completion			0	0	0	0	0	0	0	0	0	0				2026-06-22 08:00	2026-06-22 08:00		2026-06-22 08:00	2026-06-22 08:00			2026-06-22 08:00	2026-06-22 08:00				PT_Normal					MDS-SC-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%T	TASKPRED
%F	task_pred_id	task_id	pred_task_id	proj_id	pred_proj_id	pred_type	lag_hr_cnt	comments	float_path	aref	arls
%R	9001	40002	40001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9002	40003	40002	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9003	40004	40001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9004	40005	40004	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9005	40006	40001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9006	40007	40006	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9007	40008	40003	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9008	40008	40005	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	9009	40008	40007	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%E
```

- [ ] **Step 2: Build `multi_driver_slip_current.xer`**

Copy `multi_driver_slip_baseline.xer`. Apply three changes — one per chain — engineered so each chain becomes a *distinct* SC driver:

**Chain A — duration_change:** A1000 (`task_id=40002`)
- Change `target_drtn_hr_cnt` and `remain_drtn_hr_cnt` from `80` to `104` (10d → 13d). 
- Update A1000's `early_end_date` from `2026-06-05 17:00` to `2026-06-10 17:00`.
- Update A1010's `early_start_date` to `2026-06-11 08:00` and `early_end_date` to `2026-06-24 17:00`.
- Update SC's predecessor chain dates: SC's earliest predecessor becomes A-chain at `2026-06-24 17:00`.

**Chain B — logic_change:** add a new TASKPRED row inserting a 5-day FS lag on B1000 → B1010.
- Change the existing TASKPRED row for B1010 (`task_pred_id=9004`) to `pred_type=PR_FS` (unchanged) but `lag_hr_cnt=40` (was `0`).
- This pushes B1010's start by 5 working days, B-chain ends at `2026-06-26 17:00`.

**Chain C — operational_slip:** C1000 (`task_id=40006`) — change its `act_start_date` from empty to `2026-06-01 08:00` (5 working days late), update `status_code` from `TK_NotStart` to `TK_Active`, set `phys_complete_pct` to `40`. The activity *actually started* 5 working days late.
- Update C1000's `early_end_date` accordingly (proportional: started 5d late → ends 5d late). New end: `2026-06-12 17:00`.
- Update C1010's `early_start_date` to `2026-06-15 08:00` and `early_end_date` to `2026-06-26 17:00`.
- Update C1000's `act_start_date` and the data_date in PROJECT to reflect a current snapshot post-actual.

**Update PROJECT `last_recalc_date` from `2026-05-25 11:12` to `2026-06-01 11:12`** — the data_date moves forward so the operational_slip on C1000 (started before data_date) is visible.

**Update SC's `early_start_date` / `early_end_date`:** all three chains slip 5 working days. SC moves from `2026-06-22 08:00` to `2026-06-29 08:00` (5 working days = 7 calendar days).

- [ ] **Step 3: Verify both fixtures parse and CPM cleanly**

```bash
python -c "
import sys
sys.path.insert(0, 'scheduling/mcp-server')
from cache import CpmCache
c = CpmCache()
for fname in ('multi_driver_slip_baseline.xer', 'multi_driver_slip_current.xer'):
    path = f'scheduling/mcp-server/tests/fixtures/{fname}'
    p = c.get_parsed(path)
    results, meta = c.get_cpm(path)
    print(fname, 'tasks=', len(p['TASK']), 'sc=', meta.get('sc_milestone_id'))
"
```

Expected: both load with 8 tasks each.

- [ ] **Step 4: Commit**

```bash
git add scheduling/mcp-server/tests/fixtures/multi_driver_slip_baseline.xer scheduling/mcp-server/tests/fixtures/multi_driver_slip_current.xer
git commit -m "test(scheduling): multi_driver_slip fixture pair for gain/loss attribution tests"
```

### Task B4: `tia_baseline.xer` fixture

**Files:**
- Create: `scheduling/mcp-server/tests/fixtures/tia_baseline.xer`

- [ ] **Step 1: Build `tia_baseline.xer`**

Linear schedule: NTP → A1000 (10d) → A1010 (10d) → SC. Same header tables as `minimal.xer`. TASK + TASKPRED:

```
%T	TASK
%F	[same field header]
%R	50001	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Mile	DT_FixedDUR2	TK_NotStart	M0000	NTP				0	0	0	0	0	0	0	0	0	0				2026-05-25 08:00	2026-05-25 08:00		2026-05-25 08:00	2026-05-25 08:00			2026-05-25 08:00	2026-05-25 08:00				PT_Normal					TIA-NTP-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	50002	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	A1000	Pre-Fragnet			0	0	80	0	80	80	80	0	0	0				2026-05-25 08:00	2026-06-05 17:00		2026-05-25 08:00	2026-06-05 17:00			2026-05-25 08:00	2026-06-05 17:00				PT_Normal					TIA-A1-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	50003	1	1000	100	0	N	1	N	N	CP_Drtn	TT_Task	DT_FixedDUR2	TK_NotStart	A1010	Post-Fragnet			0	0	80	0	80	80	80	0	0	0				2026-06-08 08:00	2026-06-19 17:00		2026-06-08 08:00	2026-06-19 17:00			2026-06-08 08:00	2026-06-19 17:00				PT_Normal					TIA-A2-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%R	50004	1	1000	100	0	N	1	N	N	CP_Drtn	TT_FinMile	DT_FixedDUR2	TK_NotStart	M9000	Substantial Completion			0	0	0	0	0	0	0	0	0	0				2026-06-22 08:00	2026-06-22 08:00		2026-06-22 08:00	2026-06-22 08:00			2026-06-22 08:00	2026-06-22 08:00				PT_Normal					TIA-SC-GUID				Y	0	0			2026-05-25 11:12	2026-05-25 11:12	cwalker	cwalker		
%T	TASKPRED
%F	task_pred_id	task_id	pred_task_id	proj_id	pred_proj_id	pred_type	lag_hr_cnt	comments	float_path	aref	arls
%R	11001	50002	50001	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	11002	50003	50002	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%R	11003	50004	50003	1	1	PR_FS	0			2026-05-25 08:00	2026-05-25 08:00
%E
```

A1000 finishes 2026-06-05, A1010 starts 2026-06-08 and finishes 2026-06-19, SC at 2026-06-22.

- [ ] **Step 2: Verify the fixture parses + CPMs cleanly**

```bash
python -c "
import sys
sys.path.insert(0, 'scheduling/mcp-server')
from cache import CpmCache
c = CpmCache()
path = 'scheduling/mcp-server/tests/fixtures/tia_baseline.xer'
p = c.get_parsed(path)
results, meta = c.get_cpm(path)
print('tasks=', len(p['TASK']), 'sc=', meta.get('sc_milestone_id'), 'sc_date=', meta.get('sc_milestone_date'))
"
```

Expected: `tasks= 4 sc= 50004 sc_date= 2026-06-22 08:00`.

- [ ] **Step 3: Commit**

```bash
git add scheduling/mcp-server/tests/fixtures/tia_baseline.xer
git commit -m "test(scheduling): tia_baseline.xer fixture for TIA fragnet tests"
```

### Task B5: `concurrent_delay_baseline.xer` + `concurrent_delay_current.xer` fixture pair

**Files:**
- Create: `scheduling/mcp-server/tests/fixtures/concurrent_delay_baseline.xer`
- Create: `scheduling/mcp-server/tests/fixtures/concurrent_delay_current.xer`

- [ ] **Step 1: Build the pair**

Use `multi_driver_slip_baseline.xer` as the starting point for `concurrent_delay_baseline.xer` (drop chain C — keep just NTP, A-chain, B-chain, SC — 6 activities total). The two chains are parallel, no logic relationship between them.

For `concurrent_delay_current.xer`: make A1000 *and* B1000 both slip by 5 working days via `act_start_date` (both started late, same week). Both chains end 5 working days later; SC slips 5 days. There is no logic relationship between A-chain and B-chain.

This pair tests `find_concurrent_delay_pairs`: it should return one concurrent pair (A1000, B1000) — both slipped in the same window, no logic relationship between them.

- [ ] **Step 2: Verify both fixtures parse + CPM cleanly**

Same verification pattern as Task B3.

- [ ] **Step 3: Commit**

```bash
git add scheduling/mcp-server/tests/fixtures/concurrent_delay_baseline.xer scheduling/mcp-server/tests/fixtures/concurrent_delay_current.xer
git commit -m "test(scheduling): concurrent_delay fixture pair for concurrent-delay-pairs tests"
```

---

## Phase C: `lib/cross_baseline.py` — cross-XER analytics

Goal: four new lib-level functions that operate on `(baseline_parsed, current_parsed, baseline_cpm, current_cpm)` quads. Each gets its own TDD cycle at the lib level (not just the MCP wrapper level) because these are real algorithms, not thin adapters.

### Task C1: Scaffold `lib/cross_baseline.py` and add empty test module

**Files:**
- Create: `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`
- Create: `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py`

- [ ] **Step 1: Write the module skeleton**

Create `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`:

```python
"""Cross-baseline (week-over-week) CPM-aware analytics.

The functions in this module take pre-parsed and pre-CPM'd table dicts for
both a baseline and a current XER and return structured analytics dicts.
They DO NOT parse XERs or run CPM themselves -- callers (the MCP cache, the
schedule-update phase scripts, ad-hoc REPL usage) are responsible for
producing the inputs. That separation keeps the lib functions cheap to
unit-test in isolation: pass two parsed dicts + two CPM result tuples + a
milestone_id and assert the output dict.

The four functions in this module each answer a different update-analytics
question:

* :func:`compute_critical_path_changes` -- which activities moved on/off
  the critical path week over week.
* :func:`compute_float_consumption` -- per-activity float delta.
* :func:`compute_trade_slip_summary` -- group date-slip rows by trade
  (resolved from an activity-code field).
* :func:`compute_gain_loss_attribution` -- categorize SC-milestone slip
  contributors by cause (operational realized delay vs. plan-change delay).
"""
from __future__ import annotations

from typing import Optional

from cpm_engine import extract_paths
from milestones import MilestoneAmbiguousError, get_milestones
from xer_compare import compare_xer_pair
```

Create `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py` with imports + fixture-path constants:

```python
"""Tests for ``lib/cross_baseline.py`` -- the cross-XER CPM-aware analytics.

Each function tests against the Plan 2 fixtures (see
``scheduling/mcp-server/tests/fixtures/``). The tests use the CpmCache to
parse + CPM each fixture so the inputs match what the MCP layer will pass.
"""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

SERVER_DIR = Path(__file__).parent.parent.parent.parent / "mcp-server"
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from cross_baseline import (  # noqa: E402
    compute_critical_path_changes,
    compute_float_consumption,
    compute_gain_loss_attribution,
    compute_trade_slip_summary,
)

FIXTURES = SERVER_DIR / "tests" / "fixtures"
```

- [ ] **Step 2: Commit the scaffolding (tests will fail on import — that's fine, the next tasks add the functions)**

```bash
git add scheduling/skills/schedule-toolbox/lib/cross_baseline.py scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py
git commit -m "feat(scheduling): scaffold lib/cross_baseline.py for Tier 1 analytics"
```

### Task C2: Implement `compute_critical_path_changes`

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py`

- [ ] **Step 1: Write the failing test**

Append to `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py`:

```python
class TestComputeCriticalPathChanges(unittest.TestCase):
    """compute_critical_path_changes diffs the critical_path lists from
    extract_paths() on baseline vs current and returns moved_on / moved_off
    /stable sets. The cp_baseline -> cp_shifted fixture pair was engineered
    so the entire CP shifts from A-chain to B-chain."""

    def setUp(self):
        self.cache = CpmCache()
        self.base_parsed = self.cache.get_parsed(str(FIXTURES / "cp_baseline.xer"))
        self.curr_parsed = self.cache.get_parsed(str(FIXTURES / "cp_shifted.xer"))
        self.base_cpm = self.cache.get_cpm(str(FIXTURES / "cp_baseline.xer"))
        self.curr_cpm = self.cache.get_cpm(str(FIXTURES / "cp_shifted.xer"))

    def test_returns_required_keys(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in (
            "milestone_id", "baseline_cp", "current_cp",
            "moved_on", "moved_off", "stable_count",
        ):
            self.assertIn(key, result)

    def test_baseline_cp_contains_a_chain(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {t["task_code"] for t in result["baseline_cp"]}
        self.assertIn("A1000", codes)
        self.assertIn("A1010", codes)

    def test_current_cp_contains_b_chain(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {t["task_code"] for t in result["current_cp"]}
        self.assertIn("B1000", codes)
        self.assertIn("B1010", codes)

    def test_a_chain_in_moved_off(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        moved_off_codes = {t["task_code"] for t in result["moved_off"]}
        self.assertIn("A1000", moved_off_codes)
        self.assertIn("A1010", moved_off_codes)

    def test_b_chain_in_moved_on(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        moved_on_codes = {t["task_code"] for t in result["moved_on"]}
        self.assertIn("B1000", moved_on_codes)
        self.assertIn("B1010", moved_on_codes)

    def test_no_change_when_inputs_identical(self):
        """When baseline and current are the same XER, moved_on / moved_off
        are empty and stable_count equals len(critical_path)."""
        result = compute_critical_path_changes(
            self.base_parsed, self.base_parsed,
            self.base_cpm, self.base_cpm,
        )
        self.assertEqual(result["moved_on"], [])
        self.assertEqual(result["moved_off"], [])
        self.assertGreater(result["stable_count"], 0)

    def test_milestone_id_passthrough(self):
        """Explicit milestone_id overrides the auto-resolved terminal."""
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            milestone_id="30006",
        )
        self.assertEqual(result["milestone_id"], "30006")
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_cross_baseline.TestComputeCriticalPathChanges -v
```

Expected: ImportError on `compute_critical_path_changes`.

- [ ] **Step 3: Implement `compute_critical_path_changes` in `cross_baseline.py`**

Add to `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`:

```python
def compute_critical_path_changes(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    """Diff the critical path between baseline and current.

    The critical path is what ``extract_paths`` returns under
    ``"critical_path"`` -- the longest contiguous TF<=0 chain ending at the
    terminal milestone. This function calls ``extract_paths`` on each side
    (in-memory traversal of the cached CPM results -- no fresh CPM pass)
    and computes set-difference of the resulting task_code sets.

    Args:
        baseline_parsed: ``parsed`` dict from the cache (baseline XER).
        current_parsed:  ``parsed`` dict from the cache (current XER).
        baseline_cpm:    ``(results, metadata)`` tuple from the cache for
            the baseline XER.
        current_cpm:     ``(results, metadata)`` tuple for the current.
        milestone_id:    Optional terminal milestone task_id. When None,
            ``extract_paths`` uses the metadata's auto-resolved
            ``sc_milestone_id`` on each side independently. When provided,
            both sides resolve to this milestone via a shallow-copied
            metadata; raises :class:`MilestoneAmbiguousError` if the
            milestone is missing from one side.

    Returns:
        ``{milestone_id, baseline_cp, current_cp, moved_on, moved_off,
        stable_count}``. ``baseline_cp`` / ``current_cp`` are the full
        ``extract_paths`` task-summary lists. ``moved_on`` /
        ``moved_off`` carry the rows present on one side but not the
        other (matched by ``task_code``). ``stable_count`` is the size of
        the intersection.
    """
    base_results, base_metadata = baseline_cpm
    curr_results, curr_metadata = current_cpm

    if milestone_id is not None:
        # Shallow-copy each side's metadata so the cache entries aren't
        # mutated. The current-side milestone resolution is canonical;
        # match by task_code to handle task_id renumbering.
        base_metadata = _override_sc_milestone(
            base_metadata, milestone_id, baseline_parsed.get("TASK", []),
        )
        curr_metadata = _override_sc_milestone(
            curr_metadata, milestone_id, current_parsed.get("TASK", []),
        )

    base_paths = extract_paths(
        base_results, base_metadata, baseline_parsed.get("TASKPRED", []),
    )
    curr_paths = extract_paths(
        curr_results, curr_metadata, current_parsed.get("TASKPRED", []),
    )

    base_cp = base_paths.get("critical_path", [])
    curr_cp = curr_paths.get("critical_path", [])

    base_codes = {t.get("task_code") for t in base_cp}
    curr_codes = {t.get("task_code") for t in curr_cp}

    moved_off = [t for t in base_cp if t.get("task_code") not in curr_codes]
    moved_on = [t for t in curr_cp if t.get("task_code") not in base_codes]
    stable_count = len(base_codes & curr_codes)

    return {
        "milestone_id": milestone_id or curr_metadata.get("sc_milestone_id"),
        "baseline_cp": base_cp,
        "current_cp": curr_cp,
        "moved_on": moved_on,
        "moved_off": moved_off,
        "stable_count": stable_count,
    }


def _override_sc_milestone(metadata: dict, milestone_id, tasks: list) -> dict:
    """Shallow-copy ``metadata`` with ``sc_milestone_*`` keys overridden
    to point at ``milestone_id``. Helper used by every function in this
    module that accepts an optional ``milestone_id`` parameter.

    Raises :class:`MilestoneAmbiguousError` carrying the candidate
    milestone list if ``milestone_id`` doesn't exist in ``tasks`` AND the
    schedule has multiple terminal milestones -- a missing-milestone error
    in a multi-terminal schedule is symptomatic of the caller not knowing
    which to pick.
    """
    if milestone_id is None:
        return metadata
    new_meta = dict(metadata)
    new_meta["sc_milestone_id"] = milestone_id
    found = False
    for t in tasks:
        if t.get("task_id") == milestone_id:
            new_meta["sc_milestone_name"] = t.get("task_name", "")
            new_meta["sc_milestone_code"] = t.get("task_code", "")
            new_meta["sc_milestone_date"] = t.get("early_end_date", "")
            found = True
            break
    if not found:
        # Raise ambiguous-error carrying the candidates so the caller can
        # repair the request.
        candidates = get_milestones(tasks, include_complete=False)
        raise MilestoneAmbiguousError(
            f"milestone_id '{milestone_id}' not found; "
            f"{len(candidates)} candidate(s) available",
            candidates=candidates,
        )
    return new_meta
```

- [ ] **Step 4: Run test, verify it passes**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_cross_baseline.TestComputeCriticalPathChanges -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/cross_baseline.py scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py
git commit -m "feat(scheduling): compute_critical_path_changes diffs CP across XER pair"
```

### Task C3: Implement `compute_float_consumption`

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py`

- [ ] **Step 1: Write the failing test**

Append to `test_cross_baseline.py`:

```python
class TestComputeFloatConsumption(unittest.TestCase):
    """compute_float_consumption returns per-activity total_float deltas.
    A negative delta means float was consumed (slip risk increased);
    positive means float was added back (schedule healthier)."""

    def setUp(self):
        self.cache = CpmCache()
        self.base_path = str(FIXTURES / "cp_baseline.xer")
        self.curr_path = str(FIXTURES / "cp_shifted.xer")
        self.base_parsed = self.cache.get_parsed(self.base_path)
        self.curr_parsed = self.cache.get_parsed(self.curr_path)
        self.base_cpm = self.cache.get_cpm(self.base_path)
        self.curr_cpm = self.cache.get_cpm(self.curr_path)

    def test_returns_required_keys(self):
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in (
            "milestone_id", "by_activity", "biggest_losers", "biggest_gainers",
        ):
            self.assertIn(key, result)

    def test_by_activity_is_sorted_by_abs_delta_desc(self):
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        deltas = [abs(row["delta_hours"]) for row in result["by_activity"]]
        self.assertEqual(deltas, sorted(deltas, reverse=True))

    def test_b_chain_lost_float(self):
        """B-chain went from 80hr float to 0hr float in cp_shifted (now CP).
        B1000 and B1010 should show up in biggest_losers with negative
        delta_hours of magnitude ~80."""
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        loser_codes = {row["task_code"] for row in result["biggest_losers"]}
        self.assertIn("B1000", loser_codes)
        self.assertIn("B1010", loser_codes)

    def test_a_chain_gained_float(self):
        """A-chain went from 0hr float to >0hr float (still finishes but
        no longer drives). A1000 and A1010 in biggest_gainers."""
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        gainer_codes = {row["task_code"] for row in result["biggest_gainers"]}
        self.assertIn("A1000", gainer_codes)
        self.assertIn("A1010", gainer_codes)
```

- [ ] **Step 2: Run, verify failure**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_cross_baseline.TestComputeFloatConsumption -v
```

- [ ] **Step 3: Implement `compute_float_consumption`**

Add to `cross_baseline.py`:

```python
def compute_float_consumption(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    """Per-activity total_float delta between baseline and current.

    Matches activities by ``task_code`` (task_id may renumber between
    P6 exports). Returns one row per activity present on BOTH sides
    plus the biggest_losers / biggest_gainers slices for quick triage.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, _metadata)`` tuple; CPM results have
            ``total_float_hr_cnt`` written into each row.
        current_cpm:     same for the current XER.
        milestone_id:    Optional terminal milestone task_id. Forwarded to
            the metadata copy but ``compute_float_consumption`` itself
            doesn't filter by milestone -- the field is in the response
            for cross-tool consistency.

    Returns:
        ``{milestone_id, by_activity: [{task_code, task_name,
        baseline_hours, current_hours, delta_hours}, ...],
        biggest_losers: [...rows with most-negative delta...],
        biggest_gainers: [...rows with most-positive delta...]}``.
        ``by_activity`` is sorted by ``abs(delta_hours)`` descending.
        ``biggest_losers`` and ``biggest_gainers`` are the top-5 of each.
    """
    base_results, base_metadata = baseline_cpm
    curr_results, _ = current_cpm

    def _by_code(rows: list) -> dict:
        return {r.get("task_code"): r for r in rows if r.get("task_code")}

    base_by_code = _by_code(base_results)
    curr_by_code = _by_code(curr_results)

    common = set(base_by_code) & set(curr_by_code)

    by_activity = []
    for code in common:
        b = base_by_code[code]
        c = curr_by_code[code]
        base_hr = _safe_float(b.get("total_float_hr_cnt"), 0.0)
        curr_hr = _safe_float(c.get("total_float_hr_cnt"), 0.0)
        delta = curr_hr - base_hr
        if abs(delta) < 0.01:
            continue
        by_activity.append({
            "task_code": code,
            "task_name": c.get("task_name") or b.get("task_name", ""),
            "baseline_hours": base_hr,
            "current_hours": curr_hr,
            "delta_hours": delta,
        })

    by_activity.sort(key=lambda r: abs(r["delta_hours"]), reverse=True)
    biggest_losers = sorted(
        (r for r in by_activity if r["delta_hours"] < 0),
        key=lambda r: r["delta_hours"],
    )[:5]
    biggest_gainers = sorted(
        (r for r in by_activity if r["delta_hours"] > 0),
        key=lambda r: r["delta_hours"], reverse=True,
    )[:5]

    return {
        "milestone_id": milestone_id or base_metadata.get("sc_milestone_id"),
        "by_activity": by_activity,
        "biggest_losers": biggest_losers,
        "biggest_gainers": biggest_gainers,
    }


def _safe_float(value, default: float) -> float:
    """Float-coerce ``value``, returning ``default`` on bad input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
```

- [ ] **Step 4: Run test, verify it passes**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_cross_baseline.TestComputeFloatConsumption -v
```

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/cross_baseline.py scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py
git commit -m "feat(scheduling): compute_float_consumption per-activity float delta"
```

### Task C4: Implement `compute_trade_slip_summary`

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py`

- [ ] **Step 1: Decide the trade-field resolution strategy**

The spec calls out open question 4: "Trade tagging source. `get_trade_slip_summary` and the trade-filtering in `get_activities_to_start` need a canonical trade field. Westland's existing convention uses the activity-code field — confirm which code maps to 'trade' before locking schemas."

This plan resolves it pragmatically: the function accepts a `trade_field` parameter (default `None`, meaning auto-detect via two strategies in order). When provided, the field is used directly. Otherwise:

1. If `parsed["TASKACTV"]` and `parsed["ACTVTYPE"]` exist, group by the value of `ACTVTYPE` rows whose `actv_short_name` matches one of Westland's known trade codes (`"TRADE"`, `"DIVISION"`, `"DISC"`). If multiple match, prefer in that order.
2. If no activity-code metadata is present, fall back to extracting the trade prefix from `task_code` (e.g. `"D26-1000"` → `"D26"`).

When neither strategy yields a trade, the activity is bucketed under `"UNKNOWN"`.

This is conservative — the tool ships with a usable default for the common case and an explicit knob for unusual projects. A future lessons-learned cycle can lock the canonical Westland field.

- [ ] **Step 2: Write the failing test**

Append to `test_cross_baseline.py`:

```python
class TestComputeTradeSlipSummary(unittest.TestCase):
    """compute_trade_slip_summary groups date_slippage rows by trade and
    returns per-trade totals. The multi_driver_slip fixture pair has three
    chains, each with a different task_code prefix (A, B, C), used as the
    fallback trade key."""

    def setUp(self):
        self.cache = CpmCache()
        self.base_path = str(FIXTURES / "multi_driver_slip_baseline.xer")
        self.curr_path = str(FIXTURES / "multi_driver_slip_current.xer")
        self.base_parsed = self.cache.get_parsed(self.base_path)
        self.curr_parsed = self.cache.get_parsed(self.curr_path)
        self.base_cpm = self.cache.get_cpm(self.base_path)
        self.curr_cpm = self.cache.get_cpm(self.curr_path)

    def test_returns_required_keys(self):
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in ("milestone_id", "by_trade"):
            self.assertIn(key, result)

    def test_by_trade_sorted_by_abs_total_slip(self):
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        slips = [abs(row["total_slip_days"]) for row in result["by_trade"]]
        self.assertEqual(slips, sorted(slips, reverse=True))

    def test_three_trades_surface(self):
        """A, B, C task_code prefixes should each appear as a trade with
        nonzero total_slip_days."""
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        trades = {row["trade"] for row in result["by_trade"]}
        self.assertIn("A", trades)
        self.assertIn("B", trades)
        self.assertIn("C", trades)

    def test_explicit_trade_field_used_when_provided(self):
        """If trade_field is provided and the field doesn't exist on tasks,
        every activity falls into UNKNOWN."""
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            trade_field="nonexistent_field",
        )
        trades = {row["trade"] for row in result["by_trade"]}
        self.assertEqual(trades, {"UNKNOWN"})
```

- [ ] **Step 3: Run, verify failure**

- [ ] **Step 4: Implement `compute_trade_slip_summary`**

Add to `cross_baseline.py`:

```python
def compute_trade_slip_summary(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
    trade_field: Optional[str] = None,
) -> dict:
    """Group per-activity date slip by trade and return per-trade totals.

    Uses ``compare_xer_pair`` to compute date_slippage rows, then maps each
    activity to a trade via:

    1. The named ``trade_field`` on the activity's TASK row (when
       provided). Activities lacking that field fall to ``"UNKNOWN"``.
    2. Otherwise: the first 1-2 alphabetic characters of ``task_code``
       (e.g. ``"D26-1000" -> "D"``, ``"A1000" -> "A"``). Empty task_codes
       fall to ``"UNKNOWN"``.

    Returns one row per distinct trade with the count of affected
    activities, total slip in calendar days (signed -- positive = trades
    slipped later, negative = pulled in), and the activity with the
    largest single-activity slip in that trade.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        milestone_id:    Optional; pass-through for cross-tool consistency.
        trade_field:     Optional TASK field name to use as the trade key.
            When None, falls back to the task_code prefix.

    Returns:
        ``{milestone_id, by_trade: [{trade, activity_count,
        total_slip_days, worst_activity: {task_code, task_name,
        slip_days}}, ...]}``. ``by_trade`` is sorted by
        ``abs(total_slip_days)`` descending.
    """
    # One compare_xer_pair call -- match on task_code to handle renumber.
    compare_result = compare_xer_pair(
        baseline_parsed, current_parsed, match_by="task_code",
    )
    date_slippage = compare_result.get("date_slippage", [])

    # Map task_code -> trade. Use the CURRENT side's TASK rows because
    # that's the canonical "as-of-now" view; if a task only exists on
    # the baseline side (removed), use that side's row.
    task_by_code: dict = {}
    for row in current_parsed.get("TASK", []):
        code = row.get("task_code")
        if code:
            task_by_code[code] = row
    for row in baseline_parsed.get("TASK", []):
        code = row.get("task_code")
        if code and code not in task_by_code:
            task_by_code[code] = row

    def _trade_for(code: str) -> str:
        task = task_by_code.get(code, {})
        if trade_field is not None:
            val = task.get(trade_field)
            return val if val else "UNKNOWN"
        # Fallback: alphabetic prefix of task_code.
        for i, ch in enumerate(code):
            if not ch.isalpha():
                return code[:i] if i > 0 else "UNKNOWN"
        return code or "UNKNOWN"

    # Aggregate slips by trade. Slip days are calendar days; the lib
    # writes ef_slip_days as int (truncated). We sum those.
    by_trade_acc: dict = {}
    for slip_row in date_slippage:
        code = slip_row.get("task_code", "")
        trade = _trade_for(code)
        slip_days = slip_row.get("ef_slip_days", 0)
        bucket = by_trade_acc.setdefault(
            trade,
            {"trade": trade, "activity_count": 0, "total_slip_days": 0,
             "worst_activity": None},
        )
        bucket["activity_count"] += 1
        bucket["total_slip_days"] += slip_days
        worst = bucket["worst_activity"]
        if worst is None or abs(slip_days) > abs(worst["slip_days"]):
            bucket["worst_activity"] = {
                "task_code": code,
                "task_name": slip_row.get("task_name", ""),
                "slip_days": slip_days,
            }

    by_trade = sorted(
        by_trade_acc.values(),
        key=lambda r: abs(r["total_slip_days"]),
        reverse=True,
    )

    _, base_metadata = baseline_cpm
    return {
        "milestone_id": milestone_id or base_metadata.get("sc_milestone_id"),
        "by_trade": by_trade,
    }
```

- [ ] **Step 5: Run test, verify it passes**

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/cross_baseline.py scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py
git commit -m "feat(scheduling): compute_trade_slip_summary per-trade slip aggregation"
```

### Task C5: Implement `compute_gain_loss_attribution`

This is the most novel piece of Plan 2. The algorithm and output shape are spec-defined; the implementation is below.

**Algorithm (locked):**

1. Resolve the terminal milestone on both sides (caller may supply `milestone_id`; otherwise auto-resolve and raise ambiguous-error on multi-terminal).
2. Compute `net_slip_days = current_milestone_early_finish - baseline_milestone_early_finish`. Signed: positive = slipped later, negative = pulled in, zero = no change in milestone date.
3. **Short-circuit:** if `net_slip_days == 0` AND every contributor category would be empty (see step 5), return a `"no_change"` summary with empty buckets.
4. Walk the union of `(baseline_cp ∪ current_cp)` from `extract_paths`. Match by `task_code`. For each activity on either side's CP:
   - Look up baseline row + current row by `task_code`.
   - Compute `contribution_days = current.early_finish - baseline.early_finish` (signed; falls back to 0 if either side missing).
5. Categorize each activity into one or more buckets (an activity can appear in multiple buckets when it has multi-cause changes — list in EACH applicable category with full `contribution_days`). Categories:
   - **`scope_change`** — present on one side only (`type: "added" | "removed"`).
   - **`duration_change`** — `target_drtn_hr_cnt` differs by ≥ 8 hours (= 1 working day) between baseline and current. Subkeys: `baseline_duration_days`, `current_duration_days`, `delta_days`.
   - **`calendar_change`** — `clndr_id` differs. Subkey: `what_changed: "calendar reassigned from {base_id} to {curr_id}"`.
   - **`logic_change`** — predecessors or successors of this activity changed. Compute by diffing TASKPRED rows on both sides where `task_id == activity_id` (predecessors) and `pred_task_id == activity_id` (successors). Subkeys: `predecessor_changes: [{type: "added"|"removed", pred_task_code}, ...]`, `successor_changes: [...]`.
   - **`operational_slip`** — `status_code` advanced (from `TK_NotStart` toward `TK_Active`/`TK_Complete`), AND `act_start_date` / `act_end_date` differ from `target_start_date` / `target_end_date` by ≥ 1 calendar day. Subtypes: `late_start | late_finish | early_start | early_finish | no_start | no_finish`. Subkeys: `planned_date`, `actual_or_current_date`.
6. Compute `residual_days = net_slip_days - sum_of_unique_contribution_days`. Where `sum_of_unique_contribution_days` sums each *task_code*'s contribution_days **once** (regardless of how many categories it appears in), to avoid over-counting multi-cause activities. Document this is a diagnostic of how much net slip is unexplained by the categorized contributors.
7. Build `weekly_email_documentation`:
   - `needs_narrative`: every item from `logic_change | duration_change | calendar_change | scope_change` (the scheduler-initiated subset). Both gains AND losses — a duration shrunk to recover schedule is just as worth narrating as a duration that grew.
   - `summary_paragraph_seed`: generated text combining the top 3 contributors by `abs(contribution_days)`. Format: `"Substantial Completion {moved/held steady} {net_slip} {direction}. The biggest contributors were {a}, {b}, and {c}."`

**Output shape (spec-conformant + the additions above):**

```jsonc
{
  "milestone_id": "...",
  "baseline_completion": "YYYY-MM-DD",
  "current_completion":  "YYYY-MM-DD",
  "net_slip_days":       int,    // signed
  "residual_days":       int,    // signed; net_slip - sum-unique contributions
  "summary":             "no_change" | "changed",

  "contributors_by_category": {
    "operational_slip": [
      { "task_code", "task_name", "contribution_days",
        "type": "late_start" | "late_finish" | "early_start"
              | "early_finish" | "no_start" | "no_finish",
        "planned_date", "actual_or_current_date" }
    ],
    "logic_change":  [
      { "task_code", "task_name", "contribution_days",
        "predecessor_changes": [...], "successor_changes": [...] }
    ],
    "duration_change":  [
      { "task_code", "task_name", "contribution_days",
        "baseline_duration_days", "current_duration_days", "delta_days" }
    ],
    "calendar_change":  [
      { "task_code", "task_name", "contribution_days", "what_changed" }
    ],
    "scope_change":  [
      { "task_code", "task_name", "contribution_days",
        "type": "added" | "removed" }
    ]
  },

  "weekly_email_documentation": {
    "needs_narrative": [ /* concatenation of scheduler-initiated entries */ ],
    "summary_paragraph_seed": "string"
  }
}
```

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/cross_baseline.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_cross_baseline.py`:

```python
class TestComputeGainLossAttribution(unittest.TestCase):
    """compute_gain_loss_attribution categorizes SC slip contributors by
    cause. The multi_driver_slip fixture pair has three distinct causes
    (one duration_change on A1000, one logic_change on B1010, one
    operational_slip on C1000) plus operational propagation downstream."""

    def setUp(self):
        self.cache = CpmCache()
        self.base_path = str(FIXTURES / "multi_driver_slip_baseline.xer")
        self.curr_path = str(FIXTURES / "multi_driver_slip_current.xer")
        self.base_parsed = self.cache.get_parsed(self.base_path)
        self.curr_parsed = self.cache.get_parsed(self.curr_path)
        self.base_cpm = self.cache.get_cpm(self.base_path)
        self.curr_cpm = self.cache.get_cpm(self.curr_path)

    def test_returns_required_top_level_keys(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in (
            "milestone_id", "baseline_completion", "current_completion",
            "net_slip_days", "residual_days", "summary",
            "contributors_by_category", "weekly_email_documentation",
        ):
            self.assertIn(key, result)

    def test_category_buckets_all_present(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        buckets = result["contributors_by_category"]
        for category in (
            "operational_slip", "logic_change", "duration_change",
            "calendar_change", "scope_change",
        ):
            self.assertIn(category, buckets)
            self.assertIsInstance(buckets[category], list)

    def test_net_slip_days_positive(self):
        """multi_driver_slip pair: SC moves from 2026-06-22 to
        2026-06-29 (5 working days = 7 calendar days)."""
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        self.assertGreater(result["net_slip_days"], 0)
        self.assertEqual(result["summary"], "changed")

    def test_duration_change_bucket_has_a1000(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {
            row["task_code"]
            for row in result["contributors_by_category"]["duration_change"]
        }
        self.assertIn("A1000", codes)

    def test_logic_change_bucket_has_b1010(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {
            row["task_code"]
            for row in result["contributors_by_category"]["logic_change"]
        }
        self.assertIn("B1010", codes)

    def test_operational_slip_bucket_has_c1000(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {
            row["task_code"]
            for row in result["contributors_by_category"]["operational_slip"]
        }
        self.assertIn("C1000", codes)

    def test_no_change_short_circuit(self):
        """When baseline and current are the same XER, summary is no_change."""
        result = compute_gain_loss_attribution(
            self.base_parsed, self.base_parsed,
            self.base_cpm, self.base_cpm,
        )
        self.assertEqual(result["summary"], "no_change")
        self.assertEqual(result["net_slip_days"], 0)

    def test_needs_narrative_includes_scheduler_initiated(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        narrative = result["weekly_email_documentation"]["needs_narrative"]
        narrative_codes = {row["task_code"] for row in narrative}
        # All three scheduler-initiated drivers should appear:
        self.assertIn("A1000", narrative_codes)  # duration_change
        self.assertIn("B1010", narrative_codes)  # logic_change
        # C1000 is operational, should NOT be in needs_narrative.
        self.assertNotIn("C1000", narrative_codes)

    def test_summary_paragraph_seed_is_nonempty_string(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        seed = result["weekly_email_documentation"]["summary_paragraph_seed"]
        self.assertIsInstance(seed, str)
        self.assertGreater(len(seed), 0)
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement `compute_gain_loss_attribution`**

Add to `cross_baseline.py`:

```python
def compute_gain_loss_attribution(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    """Categorize SC-milestone slip contributors by cause.

    See the Plan 2 spec for the full output shape. Algorithm summary:

    * Resolve the terminal milestone on both sides.
    * Compute net_slip_days as signed (current_finish - baseline_finish).
    * If net is zero and no contributors exist anywhere, short-circuit
      to ``summary: "no_change"``.
    * For each activity on union(baseline_cp, current_cp), match by
      task_code and categorize the diff:
        - scope_change   -- present on one side only
        - duration_change -- target_drtn_hr_cnt differs >= 8 hr
        - calendar_change -- clndr_id differs
        - logic_change   -- predecessors or successors differ
        - operational_slip -- status_code advanced AND actual dates
                              differ from target dates
    * Multi-cause activities appear in EACH applicable category with
      full contribution_days. summing-across-categories may exceed
      net_slip_days when activities are multi-cause; ``residual_days``
      subtracts a per-task_code-unique sum to surface unexplained slip.
    * weekly_email_documentation.needs_narrative collects every entry
      from the four scheduler-initiated categories (operational_slip
      excluded -- that's realized field reality, not a scheduler decision).
    """
    base_results, base_metadata = baseline_cpm
    curr_results, curr_metadata = current_cpm

    if milestone_id is not None:
        base_metadata = _override_sc_milestone(
            base_metadata, milestone_id, baseline_parsed.get("TASK", []),
        )
        curr_metadata = _override_sc_milestone(
            curr_metadata, milestone_id, current_parsed.get("TASK", []),
        )

    base_paths = extract_paths(
        base_results, base_metadata, baseline_parsed.get("TASKPRED", []),
    )
    curr_paths = extract_paths(
        curr_results, curr_metadata, current_parsed.get("TASKPRED", []),
    )

    base_finish = base_metadata.get("sc_milestone_date", "")
    curr_finish = curr_metadata.get("sc_milestone_date", "")
    net_slip_days = _date_delta_days(base_finish, curr_finish)

    base_tasks_by_code = _by_code(baseline_parsed.get("TASK", []))
    curr_tasks_by_code = _by_code(current_parsed.get("TASK", []))

    union_codes = set()
    for row in base_paths.get("critical_path", []):
        if row.get("task_code"):
            union_codes.add(row["task_code"])
    for row in curr_paths.get("critical_path", []):
        if row.get("task_code"):
            union_codes.add(row["task_code"])

    base_preds_by_id = _preds_grouped_by_task_id(
        baseline_parsed.get("TASKPRED", []),
    )
    curr_preds_by_id = _preds_grouped_by_task_id(
        current_parsed.get("TASKPRED", []),
    )
    base_succs_by_id = _succs_grouped_by_pred_id(
        baseline_parsed.get("TASKPRED", []),
    )
    curr_succs_by_id = _succs_grouped_by_pred_id(
        current_parsed.get("TASKPRED", []),
    )

    buckets: dict = {
        "operational_slip": [],
        "logic_change": [],
        "duration_change": [],
        "calendar_change": [],
        "scope_change": [],
    }
    contribution_by_code: dict = {}

    for code in union_codes:
        base_t = base_tasks_by_code.get(code)
        curr_t = curr_tasks_by_code.get(code)

        # contribution_days: signed early_end_date delta.
        contribution_days = _date_delta_days(
            (base_t or {}).get("early_end_date", ""),
            (curr_t or {}).get("early_end_date", ""),
        )
        contribution_by_code[code] = contribution_days

        # Scope change?
        if base_t is None and curr_t is not None:
            buckets["scope_change"].append({
                "task_code": code,
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "type": "added",
            })
            continue
        if base_t is not None and curr_t is None:
            buckets["scope_change"].append({
                "task_code": code,
                "task_name": base_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "type": "removed",
            })
            continue

        # Both sides present -- check the other dimensions.
        base_dur = _safe_float(base_t.get("target_drtn_hr_cnt"), 0.0)
        curr_dur = _safe_float(curr_t.get("target_drtn_hr_cnt"), 0.0)
        if abs(curr_dur - base_dur) >= 8.0:
            buckets["duration_change"].append({
                "task_code": code,
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "baseline_duration_days": base_dur / 8.0,
                "current_duration_days": curr_dur / 8.0,
                "delta_days": (curr_dur - base_dur) / 8.0,
            })

        if base_t.get("clndr_id") != curr_t.get("clndr_id"):
            buckets["calendar_change"].append({
                "task_code": code,
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "what_changed": (
                    f"calendar reassigned from {base_t.get('clndr_id')} "
                    f"to {curr_t.get('clndr_id')}"
                ),
            })

        # Logic change: diff predecessors and successors by task_code.
        pred_changes = _diff_relationship_sets(
            base_preds_by_id.get(base_t.get("task_id"), []),
            curr_preds_by_id.get(curr_t.get("task_id"), []),
            field="pred_task_id",
            code_lookup=lambda tid: _code_for_id(
                tid, base_tasks_by_code, curr_tasks_by_code,
            ),
        )
        succ_changes = _diff_relationship_sets(
            base_succs_by_id.get(base_t.get("task_id"), []),
            curr_succs_by_id.get(curr_t.get("task_id"), []),
            field="task_id",
            code_lookup=lambda tid: _code_for_id(
                tid, base_tasks_by_code, curr_tasks_by_code,
            ),
        )
        if pred_changes or succ_changes:
            buckets["logic_change"].append({
                "task_code": code,
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "predecessor_changes": pred_changes,
                "successor_changes": succ_changes,
            })

        # Operational slip: status advanced AND actual dates differ.
        op_entry = _operational_slip_entry(base_t, curr_t, contribution_days)
        if op_entry is not None:
            buckets["operational_slip"].append(op_entry)

    # Sum contribution_days per task_code (unique) for residual.
    sum_unique = sum(contribution_by_code.values())
    residual_days = net_slip_days - sum_unique

    # Short-circuit: net_slip_days == 0 AND every bucket empty.
    summary = "no_change" if (
        net_slip_days == 0 and not any(buckets.values())
    ) else "changed"

    # needs_narrative: union of scheduler-initiated categories.
    needs_narrative = (
        list(buckets["logic_change"])
        + list(buckets["duration_change"])
        + list(buckets["calendar_change"])
        + list(buckets["scope_change"])
    )
    summary_paragraph_seed = _seed_paragraph(
        net_slip_days, buckets, base_finish, curr_finish,
    )

    return {
        "milestone_id": milestone_id or curr_metadata.get("sc_milestone_id"),
        "baseline_completion": base_finish,
        "current_completion": curr_finish,
        "net_slip_days": net_slip_days,
        "residual_days": residual_days,
        "summary": summary,
        "contributors_by_category": buckets,
        "weekly_email_documentation": {
            "needs_narrative": needs_narrative,
            "summary_paragraph_seed": summary_paragraph_seed,
        },
    }


def _by_code(rows: list) -> dict:
    """Build a ``{task_code: row}`` lookup, skipping rows with no code."""
    return {r.get("task_code"): r for r in rows if r.get("task_code")}


def _preds_grouped_by_task_id(preds: list) -> dict:
    out: dict = {}
    for r in preds:
        out.setdefault(r.get("task_id"), []).append(r)
    return out


def _succs_grouped_by_pred_id(preds: list) -> dict:
    out: dict = {}
    for r in preds:
        out.setdefault(r.get("pred_task_id"), []).append(r)
    return out


def _diff_relationship_sets(base_rels: list, curr_rels: list,
                            field: str, code_lookup) -> list:
    """Return per-relationship added/removed entries between two TASKPRED
    row lists. ``field`` is the column to extract the *other* end of the
    relationship from (``pred_task_id`` for predecessor diffs,
    ``task_id`` for successor diffs)."""
    base_set = {r.get(field) for r in base_rels}
    curr_set = {r.get(field) for r in curr_rels}
    added = [
        {"type": "added", "pred_task_code": code_lookup(tid)}
        for tid in curr_set - base_set
    ]
    removed = [
        {"type": "removed", "pred_task_code": code_lookup(tid)}
        for tid in base_set - curr_set
    ]
    return added + removed


def _code_for_id(tid, base_by_code: dict, curr_by_code: dict) -> str:
    for d in (curr_by_code, base_by_code):
        for code, row in d.items():
            if row.get("task_id") == tid:
                return code
    return str(tid)


def _operational_slip_entry(base_t: dict, curr_t: dict,
                            contribution_days: int) -> Optional[dict]:
    """Return an operational_slip entry when the activity's status
    advanced AND the actual dates differ from the target dates by >=
    1 calendar day. None otherwise."""
    STATUS_RANK = {
        "TK_NotStart": 0, "TK_Active": 1,
        "TK_Complete": 2,
    }
    base_status = STATUS_RANK.get(base_t.get("status_code"), 0)
    curr_status = STATUS_RANK.get(curr_t.get("status_code"), 0)

    # Only emit when status advanced (work began or completed).
    if curr_status <= base_status:
        return None

    target_start = curr_t.get("target_start_date", "")
    actual_start = curr_t.get("act_start_date", "")
    target_end = curr_t.get("target_end_date", "")
    actual_end = curr_t.get("act_end_date", "")

    # Late start: actual_start > target_start.
    if actual_start and target_start:
        delta = _date_delta_days(target_start, actual_start)
        if delta > 0:
            return {
                "task_code": curr_t.get("task_code", ""),
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "type": "late_start",
                "planned_date": target_start,
                "actual_or_current_date": actual_start,
            }
        if delta < 0:
            return {
                "task_code": curr_t.get("task_code", ""),
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "type": "early_start",
                "planned_date": target_start,
                "actual_or_current_date": actual_start,
            }
    # Late finish: actual_end > target_end.
    if actual_end and target_end:
        delta = _date_delta_days(target_end, actual_end)
        if delta > 0:
            return {
                "task_code": curr_t.get("task_code", ""),
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "type": "late_finish",
                "planned_date": target_end,
                "actual_or_current_date": actual_end,
            }
        if delta < 0:
            return {
                "task_code": curr_t.get("task_code", ""),
                "task_name": curr_t.get("task_name", ""),
                "contribution_days": contribution_days,
                "type": "early_finish",
                "planned_date": target_end,
                "actual_or_current_date": actual_end,
            }
    return None


def _date_delta_days(base_date_str: str, curr_date_str: str) -> int:
    """Return signed calendar-day delta between two date strings.
    Accepts ``%Y-%m-%d %H:%M`` or ``%Y-%m-%d``. Returns 0 when either
    side is empty or unparseable."""
    from datetime import datetime
    def _parse(s: str):
        if not s:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                continue
        return None
    a = _parse(base_date_str)
    b = _parse(curr_date_str)
    if a is None or b is None:
        return 0
    return (b - a).days


def _seed_paragraph(net_slip_days: int, buckets: dict,
                    base_finish: str, curr_finish: str) -> str:
    """Generate a first-draft narrative paragraph the scheduler edits
    into the weekly email."""
    if net_slip_days == 0 and not any(buckets.values()):
        return (
            f"Substantial Completion held steady at {curr_finish}. "
            "No critical-path changes this week."
        )
    direction = "later" if net_slip_days > 0 else "earlier"
    magnitude = abs(net_slip_days)
    all_contributors = []
    for category, rows in buckets.items():
        for row in rows:
            all_contributors.append((row, category))
    all_contributors.sort(
        key=lambda pair: abs(pair[0].get("contribution_days", 0)),
        reverse=True,
    )
    top = all_contributors[:3]
    names = ", ".join(
        f"{row.get('task_code')} ({row.get('task_name', '').strip()})"
        for row, _ in top
    ) if top else "no individual driver"
    return (
        f"Substantial Completion moved {magnitude} calendar day(s) "
        f"{direction} (from {base_finish} to {curr_finish}). "
        f"The biggest contributors were: {names}."
    )
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_cross_baseline.TestComputeGainLossAttribution -v
```

Expected: 9 tests pass. If `test_duration_change_bucket_has_a1000` fails, the fixture's A1000 duration change isn't crossing the 8-hour threshold — verify the fixture content in Task B3.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/cross_baseline.py scheduling/skills/schedule-toolbox/tests/test_cross_baseline.py
git commit -m "feat(scheduling): compute_gain_loss_attribution categorizes SC slip drivers"
```

---

## Phase D: Tier 1 MCP tool adapters (`tools/update_analytics.py`)

Goal: four MCP tool wrappers, one per Phase C lib function. Each is a 10-20 line `_impl(...)` + an `@mcp.tool()` `register(mcp, cache)` block, following the F1-F5 conventions exactly.

### Task D1: Scaffold `tools/update_analytics.py` + register on the server

**Files:**
- Create: `scheduling/mcp-server/tools/update_analytics.py`
- Create: `scheduling/mcp-server/tests/test_update_analytics.py`
- Modify: `scheduling/mcp-server/server.py`

- [ ] **Step 1: Write the module skeleton**

Create `scheduling/mcp-server/tools/update_analytics.py`:

```python
"""Tier 1 update-analytics MCP tools.

Thin adapters around ``schedule-toolbox/lib/cross_baseline.py``. Each tool
fetches parsed tables + CPM results from ``CpmCache`` for both baseline
and current XER paths, hands them to the matching lib function, and
returns the result dict.

Naming convention mirrors the F4 ``compare_*`` tools:

* :func:`get_critical_path_changes` -- diff the critical path week over week.
* :func:`get_float_consumption` -- per-activity total_float delta.
* :func:`get_trade_slip_summary` -- per-trade slip aggregation.
* :func:`get_gain_loss_attribution` -- categorize SC slip drivers by cause.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cross_baseline import (  # noqa: E402
    compute_critical_path_changes,
    compute_float_consumption,
    compute_gain_loss_attribution,
    compute_trade_slip_summary,
)
```

Create `scheduling/mcp-server/tests/test_update_analytics.py` with the imports + fixture paths:

```python
"""Tests for the Tier 1 update-analytics MCP tools.

Smoke-test wrappers -- the algorithmic correctness lives in
``test_cross_baseline.py`` at the lib level. These tests confirm the
wrappers call the lib with the right cached inputs and project the
expected top-level keys.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import update_analytics  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
```

Modify `scheduling/mcp-server/server.py` to register the new module:

```python
from tools import (  # noqa: E402
    compare,
    cpm_path,
    delay_analysis,
    omnibus,
    quality,
    structure,
    update_analytics,
    update_review,
)

# ...

update_analytics.register(mcp, _cache)
delay_analysis.register(mcp, _cache)
```

Note: `delay_analysis` is added in Phase G — leave a placeholder import that will be wired then. To avoid a temporary import error, do NOT add the `delay_analysis` import in this task; add it in Task G1. Add only `update_analytics` in this task.

- [ ] **Step 2: Commit the scaffolding**

```bash
git add scheduling/mcp-server/tools/update_analytics.py scheduling/mcp-server/tests/test_update_analytics.py scheduling/mcp-server/server.py
git commit -m "feat(scheduling): scaffold update_analytics MCP tool module"
```

### Task D2: Implement the four Tier 1 tool wrappers (batched TDD)

Same pattern as Plan 1 Task E1 (fully shown there); the four wrappers are structurally identical to each other. The per-tool variance is below.

**Files:**
- Modify: `scheduling/mcp-server/tools/update_analytics.py`
- Modify: `scheduling/mcp-server/tests/test_update_analytics.py`

| MCP tool | `lib/` function | Wrapper extras |
|----------|-----------------|----------------|
| `get_critical_path_changes` | `compute_critical_path_changes` | Accepts `baseline_xer_path`, `current_xer_path`, `milestone_id?`. |
| `get_float_consumption` | `compute_float_consumption` | Same inputs; no milestone resolution required for the algorithm but the pass-through milestone_id is kept for cross-tool consistency. |
| `get_trade_slip_summary` | `compute_trade_slip_summary` | Adds `trade_field?` parameter (default None → auto-detect). |
| `get_gain_loss_attribution` | `compute_gain_loss_attribution` | Same inputs as critical-path-changes. |

For each tool, follow the F1-pattern from Plan 1 Task E1:

- [ ] **Step 1-N: TDD cycle per tool.** Per Plan 1 convention, batched into one commit per tool. For each:
  1. Write the failing test (`test_<tool>_returns_required_keys`, `test_<tool>_calls_lib_with_cached_inputs`).
  2. Run, verify it fails.
  3. Implement the `_impl` + `@mcp.tool()` registration.
  4. Run, verify it passes.
  5. Commit with message `feat(scheduling): <tool_name> MCP tool wraps <lib_function>`.

**Wrapper template (use this shape for each — the variance is just the lib function name and the docstring):**

```python
def get_critical_path_changes_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Fetches parsed tables + CPM results for both XERs through the cache
    and forwards to :func:`cross_baseline.compute_critical_path_changes`.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_critical_path_changes(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        milestone_id=milestone_id,
    )
```

And in `register(mcp, cache)`:

```python
@mcp.tool()
def get_critical_path_changes(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str] = None,
) -> dict:
    """Diff the critical path between two XER snapshots.

    Returns activities that moved on or off the critical path, plus the
    full baseline and current critical-path lists. Answers
    "which trades just became critical this week?"

    Args:
        baseline_xer_path: Path to the older / baseline .xer file.
        current_xer_path: Path to the newer / current .xer file.
        milestone_id: Optional terminal milestone task_id. Omit on
            single-terminal schedules to auto-resolve; multi-terminal
            schedules raise ``MilestoneAmbiguousError``.

    Returns:
        ``{milestone_id, baseline_cp, current_cp, moved_on, moved_off,
        stable_count}``. ``baseline_cp`` and ``current_cp`` are full
        task-summary lists from ``extract_paths``. ``moved_on`` and
        ``moved_off`` are subsets carrying just the changed entries.
    """
    return get_critical_path_changes_impl(
        baseline_xer_path, current_xer_path, milestone_id, cache,
    )
```

Repeat for each of the four tools. For `get_trade_slip_summary`, the registration signature adds `trade_field: Optional[str] = None`.

- [ ] **Step N+1: After all four tools land, register module on the server.**

In `scheduling/mcp-server/server.py`, after the `cpm_path.register(...)` line:

```python
update_analytics.register(mcp, _cache)
```

- [ ] **Step N+2: Manual smoke test**

In a fresh Claude Code session after reloading the plugin:

```text
ToolSearch select:get_critical_path_changes,get_gain_loss_attribution

get_critical_path_changes(
  baseline_xer_path="<repo>/scheduling/mcp-server/tests/fixtures/cp_baseline.xer",
  current_xer_path="<repo>/scheduling/mcp-server/tests/fixtures/cp_shifted.xer",
)

get_gain_loss_attribution(
  baseline_xer_path="<repo>/scheduling/mcp-server/tests/fixtures/multi_driver_slip_baseline.xer",
  current_xer_path="<repo>/scheduling/mcp-server/tests/fixtures/multi_driver_slip_current.xer",
)
```

Verify the first call returns nonempty `moved_on` / `moved_off` lists and the second returns nonempty `contributors_by_category` buckets.

---

## Phase E: `weekly_update_review` omnibus stub fill-in

Goal: wire `weekly_update_review_impl` in `tools/omnibus.py` to call the new Tier 1 lib functions and remove the Plan-1 stub fields. Also expose the previously hard-coded `match_by` as a tool parameter per the Plan-1 reviewer note.

### Task E1: Wire `critical_path_changes` and `gain_loss_attribution` into the omnibus

**Files:**
- Modify: `scheduling/mcp-server/tools/omnibus.py`
- Modify: `scheduling/mcp-server/tests/test_omnibus.py`

- [ ] **Step 1: Read existing tests to understand the current shape**

```bash
# Use Read tool on scheduling/mcp-server/tests/test_omnibus.py
```

Note the current assertion that `critical_path_changes is None` and `pending_plan_2 is True`.

- [ ] **Step 2: Update existing tests + add new tests**

Modify the existing tests in `test_omnibus.py` to flip the assertions:

```python
def test_critical_path_changes_populated(self):
    """In Plan 2 the omnibus wires the real Tier 1 lib functions.
    Was None in Plan 1 with pending_plan_2 True."""
    result = omnibus.weekly_update_review_impl(
        str(FIXTURE_V1), str(FIXTURE_V2),
        milestone_id=None, future_date=None, match_by="task_code",
        cache=self.cache,
    )
    self.assertIsNotNone(result["critical_path_changes"])
    self.assertIn("baseline_cp", result["critical_path_changes"])

def test_gain_loss_attribution_populated(self):
    result = omnibus.weekly_update_review_impl(
        str(FIXTURE_V1), str(FIXTURE_V2),
        milestone_id=None, future_date=None, match_by="task_code",
        cache=self.cache,
    )
    self.assertIsNotNone(result["gain_loss_attribution"])
    self.assertIn("contributors_by_category", result["gain_loss_attribution"])

def test_pending_plan_2_flag_removed(self):
    result = omnibus.weekly_update_review_impl(
        str(FIXTURE_V1), str(FIXTURE_V2),
        milestone_id=None, future_date=None, match_by="task_code",
        cache=self.cache,
    )
    self.assertNotIn("pending_plan_2", result)

def test_match_by_parameter_plumbs_through(self):
    """match_by was hard-coded to 'task_code' in Plan 1; Plan 2 exposes it."""
    # Use match_by='task_id' -- shouldn't crash, fixtures share task_ids.
    result = omnibus.weekly_update_review_impl(
        str(FIXTURE_V1), str(FIXTURE_V2),
        milestone_id=None, future_date=None, match_by="task_id",
        cache=self.cache,
    )
    # Activity-set lists should be empty (same task_ids), milestone slip
    # should still be detected.
    self.assertEqual(result["activity_changes"]["added_tasks"], [])
    self.assertGreater(abs(result["milestone_slip"]["sc_slip_days"]), 0)
```

- [ ] **Step 3: Run tests, verify they fail**

- [ ] **Step 4: Modify `weekly_update_review_impl` to call the Tier 1 libs and accept `match_by`**

In `scheduling/mcp-server/tools/omnibus.py`:

```python
# Add at the top of the imports section, after the lib injection:
from cross_baseline import (  # noqa: E402
    compute_critical_path_changes,
    compute_gain_loss_attribution,
)
```

Modify the `weekly_update_review_impl` signature and body:

```python
def weekly_update_review_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    future_date: Optional[str],
    match_by: str,                  # NEW -- was hard-coded "task_code"
    cache,
) -> dict:
    """[docstring updated -- see below]"""
    baseline_parsed = cache.get_parsed(baseline_xer_path)
    current_parsed = cache.get_parsed(current_xer_path)
    baseline_cpm = cache.get_cpm(baseline_xer_path)
    current_cpm = cache.get_cpm(current_xer_path)

    compare_result = compare_xer_pair(
        baseline_parsed, current_parsed,
        match_by=match_by, milestone_id=milestone_id,
    )
    activity_changes = {
        "added_tasks": compare_result["added_tasks"],
        "removed_tasks": compare_result["removed_tasks"],
        "changed_durations": compare_result["changed_durations"],
        "status_changes": compare_result["status_changes"],
    }
    milestone_slip = {
        "sc_date_old": compare_result["sc_date_old"],
        "sc_date_new": compare_result["sc_date_new"],
        "sc_slip_days": compare_result["sc_slip_days"],
        "sc_info_old": compare_result["sc_info_old"],
        "sc_info_new": compare_result["sc_info_new"],
    }

    eff_future_date = future_date if future_date is not None else _FUTURE_DATE_SENTINEL
    updates = expected_updates(current_parsed, eff_future_date, resource_filter=None)
    activities_to_start = updates["to_start"]
    activities_to_finish = updates["to_finish"]

    dcma_delta = _compute_dcma_delta(
        baseline_parsed, current_parsed, milestone_id
    )

    # Tier 1 lib calls -- catch MilestoneAmbiguousError so the omnibus
    # degrades gracefully on multi-terminal schedules without an explicit
    # milestone_id (matches the DCMA-delta degrade pattern).
    try:
        critical_path_changes = compute_critical_path_changes(
            baseline_parsed, current_parsed,
            baseline_cpm, current_cpm,
            milestone_id=milestone_id,
        )
    except MilestoneAmbiguousError:
        critical_path_changes = None
    try:
        gain_loss_attribution = compute_gain_loss_attribution(
            baseline_parsed, current_parsed,
            baseline_cpm, current_cpm,
            milestone_id=milestone_id,
        )
    except MilestoneAmbiguousError:
        gain_loss_attribution = None

    return {
        "baseline_xer_path": baseline_xer_path,
        "current_xer_path": current_xer_path,
        "activity_changes": activity_changes,
        "milestone_slip": milestone_slip,
        "activities_to_start": activities_to_start,
        "activities_to_finish": activities_to_finish,
        "dcma_delta": dcma_delta,
        "critical_path_changes": critical_path_changes,
        "gain_loss_attribution": gain_loss_attribution,
        # NO pending_plan_2 key -- removed in Plan 2.
    }
```

Update the `@mcp.tool()` `weekly_update_review` registration to accept `match_by`:

```python
@mcp.tool()
def weekly_update_review(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str] = None,
    future_date: Optional[str] = None,
    match_by: str = "task_code",     # NEW -- default preserved
) -> dict:
    """Bundled 'what changed week over week?' snapshot. [updated docstring]"""
    return weekly_update_review_impl(
        baseline_xer_path, current_xer_path,
        milestone_id, future_date, match_by, cache,
    )
```

Update the module docstring's reconciliation note: replace "Plan-2 tools (...) ship in Plan 2; this output stubs..." with "Plan-2 tools ship as of 8.0.0; this omnibus wires them through." Update the existing class docstring on `weekly_update_review_impl` to reflect the new shape.

- [ ] **Step 5: Run tests, verify they pass**

```bash
python -m unittest scheduling.mcp-server.tests.test_omnibus -v
```

Expected: all existing tests pass with the updated assertions, plus the new tests pass.

- [ ] **Step 6: Commit**

```bash
git add scheduling/mcp-server/tools/omnibus.py scheduling/mcp-server/tests/test_omnibus.py
git commit -m "feat(scheduling): weekly_update_review wires Tier 1 analytics, exposes match_by"
```

---

## Phase F: `lib/delay_analysis.py` — Tier 2 forensic delay calculations

Goal: four new lib-level functions that answer delay-consultant questions. Each gets its own TDD cycle.

### Task F1: Scaffold `lib/delay_analysis.py` + empty test module

**Files:**
- Create: `scheduling/skills/schedule-toolbox/lib/delay_analysis.py`
- Create: `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py`

- [ ] **Step 1: Write the module skeleton**

Create `scheduling/skills/schedule-toolbox/lib/delay_analysis.py`:

```python
"""Forensic delay-analysis calculations.

Genuine new algorithms, not wrappers over existing lib functions. The four
functions in this module answer the questions a delay consultant runs:

* :func:`compute_tia` -- Time Impact Analysis: insert a fragnet activity
  into a copy of the baseline parsed tables, re-run CPM, return the
  projected SC date and net delay days.
* :func:`compute_window_analysis` -- contemporaneous period analysis:
  for each named window between two snapshots, return the activities
  responsible for that window's slip with cause categorization.
* :func:`compute_change_order_delay` -- owner-vs-contractor attribution
  from a change-directive date.
* :func:`find_concurrent_delay_pairs` -- activities that slip
  simultaneously without a logic relationship between them (classic
  concurrent-delay defense candidates).

The functions take pre-parsed and pre-CPM'd table dicts so they're cheap
to unit-test. ``compute_tia`` is the exception -- it must re-run CPM
internally on a mutated copy of the parsed tables to compute the
post-fragnet SC date.
"""
from __future__ import annotations

import copy
from typing import Optional

from cpm_engine import (
    extract_paths,
    schedule_forward_backward,
)
from cross_baseline import (
    _date_delta_days,
    _override_sc_milestone,
)
from milestones import MilestoneAmbiguousError, get_milestones
from xer_compare import compare_xer_pair
```

Create `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py`:

```python
"""Tests for ``lib/delay_analysis.py`` -- Tier 2 forensic calculations."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

SERVER_DIR = Path(__file__).parent.parent.parent.parent / "mcp-server"
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from delay_analysis import (  # noqa: E402
    compute_change_order_delay,
    compute_tia,
    compute_window_analysis,
    find_concurrent_delay_pairs,
)

FIXTURES = SERVER_DIR / "tests" / "fixtures"
```

- [ ] **Step 2: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/delay_analysis.py scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py
git commit -m "feat(scheduling): scaffold lib/delay_analysis.py for Tier 2 calculations"
```

### Task F2: Implement `compute_tia`

The TIA algorithm:

1. Resolve the terminal milestone (or accept explicit `milestone_id`).
2. Capture baseline SC date from `baseline_cpm[1]['sc_milestone_date']`.
3. Deep-copy the baseline parsed tables (so the original cache entry stays clean).
4. Add a new TASK row for the delay-fragment activity (assign a fresh `task_id` that doesn't collide; use the calendar from the predecessor activity if `calendar_id` not provided in the fragment).
5. Add a new TASKPRED row connecting the fragment activity to the predecessor activity per `predecessor_relationship_type` (default `PR_FS`).
6. Run `schedule_forward_backward` on the mutated tables.
7. Read the new SC date from the results; compute `net_delay_days = projected_sc - baseline_sc`.
8. Compute `critical_path_changed` by comparing the old vs new critical_path codes from `extract_paths`.
9. Return the structured result.

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/delay_analysis.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py`

- [ ] **Step 1: Write the failing test**

Append to `test_delay_analysis.py`:

```python
class TestComputeTia(unittest.TestCase):
    """compute_tia inserts a delay fragnet, re-runs CPM, returns projected SC."""

    def setUp(self):
        self.cache = CpmCache()
        self.path = str(FIXTURES / "tia_baseline.xer")
        self.parsed = self.cache.get_parsed(self.path)
        self.cpm = self.cache.get_cpm(self.path)

    def test_returns_required_keys(self):
        result = compute_tia(
            self.parsed, self.cpm,
            delay_fragment={
                "activity_id": "FRAGNET-1",
                "duration_days": 5,
                "description": "RFI-101 delay",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",  # A1000
            },
        )
        for key in (
            "milestone_id", "baseline_completion", "projected_completion",
            "net_delay_days", "critical_path_changed",
            "new_critical_activities", "removed_critical_activities",
            "affected_activities",
        ):
            self.assertIn(key, result)

    def test_5day_fragnet_pushes_sc_by_5_working_days(self):
        """A 5-working-day fragnet on the critical path should push SC by
        5 working days (= 7 calendar days under the standard 5-day cal)."""
        result = compute_tia(
            self.parsed, self.cpm,
            delay_fragment={
                "activity_id": "FRAGNET-1",
                "duration_days": 5,
                "description": "RFI-101 delay",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",
            },
        )
        # 5 working days = 7 calendar days under 5-day calendar.
        self.assertEqual(result["net_delay_days"], 7)

    def test_zero_day_fragnet_no_delay(self):
        result = compute_tia(
            self.parsed, self.cpm,
            delay_fragment={
                "activity_id": "FRAGNET-0",
                "duration_days": 0,
                "description": "no impact",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",
            },
        )
        self.assertEqual(result["net_delay_days"], 0)
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement `compute_tia`**

Add to `delay_analysis.py`:

```python
def compute_tia(
    baseline_parsed: dict,
    baseline_cpm: tuple,
    delay_fragment: dict,
    milestone_id: Optional[str] = None,
) -> dict:
    """Time Impact Analysis: insert a fragnet activity and report the
    projected SC slip.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        baseline_cpm:    ``(results, metadata)`` tuple.
        delay_fragment:  dict with:
            * ``activity_id`` (required) -- string id for the new activity.
              Must not collide with existing task_ids.
            * ``duration_days`` (required) -- working days, will be
              multiplied by 8 to get target_drtn_hr_cnt.
            * ``predecessor_activity_id`` (required) -- task_id of the
              activity the fragnet attaches to.
            * ``predecessor_relationship_type`` (optional, default PR_FS).
            * ``calendar_id`` (optional, defaults to the predecessor's).
            * ``description`` (optional) -- used as task_name.
        milestone_id:    Optional explicit terminal milestone task_id.

    Returns:
        ``{milestone_id, baseline_completion, projected_completion,
        net_delay_days, critical_path_changed, new_critical_activities,
        removed_critical_activities, affected_activities}``.

    Raises:
        ValueError: invalid fragment (missing required fields, colliding
            task_id, unknown predecessor_activity_id).
        MilestoneAmbiguousError: ``milestone_id`` omitted on a multi-
            terminal schedule.
    """
    # Validate fragment.
    for required in ("activity_id", "duration_days", "predecessor_activity_id"):
        if required not in delay_fragment:
            raise ValueError(f"delay_fragment missing required key: {required}")
    new_id = delay_fragment["activity_id"]
    duration_days = float(delay_fragment["duration_days"])
    pred_id = delay_fragment["predecessor_activity_id"]
    relationship = delay_fragment.get("predecessor_relationship_type", "PR_FS")
    description = delay_fragment.get("description", "Delay fragnet")

    base_results, base_metadata = baseline_cpm
    if milestone_id is not None:
        base_metadata = _override_sc_milestone(
            base_metadata, milestone_id, baseline_parsed.get("TASK", []),
        )

    existing_task_ids = {t.get("task_id") for t in baseline_parsed.get("TASK", [])}
    if new_id in existing_task_ids:
        raise ValueError(
            f"delay_fragment activity_id '{new_id}' collides with an existing task"
        )
    pred_task = next(
        (t for t in baseline_parsed.get("TASK", []) if t.get("task_id") == pred_id),
        None,
    )
    if pred_task is None:
        raise ValueError(
            f"predecessor_activity_id '{pred_id}' not found in baseline TASK table"
        )
    calendar_id = delay_fragment.get("calendar_id") or pred_task.get("clndr_id")

    # Deep copy the parsed tables so we don't mutate the cache entry.
    mutated = copy.deepcopy(baseline_parsed)
    new_task = dict(pred_task)
    new_task.update({
        "task_id": new_id,
        "task_code": new_id,
        "task_name": description,
        "task_type": "TT_Task",
        "status_code": "TK_NotStart",
        "clndr_id": calendar_id,
        "target_drtn_hr_cnt": str(duration_days * 8),
        "remain_drtn_hr_cnt": str(duration_days * 8),
        "act_start_date": "",
        "act_end_date": "",
        "phys_complete_pct": "0",
    })
    mutated["TASK"].append(new_task)
    # Find a fresh task_pred_id by scanning existing.
    existing_pred_ids = {
        r.get("task_pred_id") for r in mutated.get("TASKPRED", [])
    }
    new_pred_pred_id = _next_unused_id(existing_pred_ids, prefix="FRAG-PRED-")
    mutated.setdefault("TASKPRED", []).append({
        "task_pred_id": new_pred_pred_id,
        "task_id": new_id,
        "pred_task_id": pred_id,
        "proj_id": pred_task.get("proj_id", "1"),
        "pred_proj_id": pred_task.get("proj_id", "1"),
        "pred_type": relationship,
        "lag_hr_cnt": "0",
    })
    # Re-link any successors that USED to depend on pred_id to depend on
    # new_id instead, so the fragnet sits in-line. Without this, the
    # fragnet would dangle and not push SC.
    for pred_row in mutated["TASKPRED"]:
        if (
            pred_row.get("pred_task_id") == pred_id
            and pred_row.get("task_id") != new_id
        ):
            pred_row["pred_task_id"] = new_id

    # Re-run CPM on the mutated tables.
    project_rows = mutated.get("PROJECT") or [{}]
    data_date = (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
    )
    new_results, new_metadata = schedule_forward_backward(
        mutated.get("TASK", []),
        mutated.get("TASKPRED", []),
        mutated.get("CALENDAR", []),
        data_date,
        schedoptions=mutated.get("SCHEDOPTIONS"),
        project=mutated.get("PROJECT"),
    )

    if milestone_id is not None:
        new_metadata = _override_sc_milestone(
            new_metadata, milestone_id, mutated.get("TASK", []),
        )

    baseline_sc = base_metadata.get("sc_milestone_date", "")
    projected_sc = new_metadata.get("sc_milestone_date", "")
    net_delay_days = _date_delta_days(baseline_sc, projected_sc)

    base_paths = extract_paths(
        base_results, base_metadata, baseline_parsed.get("TASKPRED", []),
    )
    new_paths = extract_paths(
        new_results, new_metadata, mutated.get("TASKPRED", []),
    )
    base_codes = {t.get("task_code") for t in base_paths.get("critical_path", [])}
    new_codes = {t.get("task_code") for t in new_paths.get("critical_path", [])}
    critical_path_changed = base_codes != new_codes
    new_critical = [
        t for t in new_paths.get("critical_path", [])
        if t.get("task_code") not in base_codes
    ]
    removed_critical = [
        t for t in base_paths.get("critical_path", [])
        if t.get("task_code") not in new_codes
    ]

    # Affected activities: any task whose early_end_date changed.
    affected = []
    new_by_id = {r.get("task_id"): r for r in new_results}
    for old_row in base_results:
        tid = old_row.get("task_id")
        new_row = new_by_id.get(tid)
        if new_row is None:
            continue
        delta = _date_delta_days(
            old_row.get("early_end_date", ""),
            new_row.get("early_end_date", ""),
        )
        if delta != 0:
            affected.append({
                "task_id": tid,
                "task_code": old_row.get("task_code", ""),
                "task_name": old_row.get("task_name", ""),
                "baseline_finish": old_row.get("early_end_date", ""),
                "projected_finish": new_row.get("early_end_date", ""),
                "delta_days": delta,
            })

    return {
        "milestone_id": milestone_id or new_metadata.get("sc_milestone_id"),
        "baseline_completion": baseline_sc,
        "projected_completion": projected_sc,
        "net_delay_days": net_delay_days,
        "critical_path_changed": critical_path_changed,
        "new_critical_activities": new_critical,
        "removed_critical_activities": removed_critical,
        "affected_activities": affected,
    }


def _next_unused_id(existing: set, prefix: str) -> str:
    """Generate a string id that doesn't collide with ``existing``."""
    i = 1
    while True:
        candidate = f"{prefix}{i}"
        if candidate not in existing:
            return candidate
        i += 1
```

- [ ] **Step 4: Run tests, verify they pass**

If the 5-day fragnet test fails with `net_delay_days != 7`, investigate the calendar — the fixture's CALENDAR row defines a 5-day working week with 8-hour days; the engine should translate 40 hours of new work into 5 working days = 7 calendar days. Adjust the fixture's calendar definition if it's not standard 5-day.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/delay_analysis.py scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py
git commit -m "feat(scheduling): compute_tia fragnet-insertion delay analysis"
```

### Task F3: Implement `compute_window_analysis`

The algorithm: for each named time window, identify which activities slipped during that window. Slip is measured against the previous snapshot's planned dates; the "window" is the inclusive `[start, end]` date range.

Per spec: `windows: [{ start, end, label }, ...]`. Each window gets:
- `slip_days` — sum of `ef_slip_days` for activities whose `early_finish_baseline` falls inside the window
- `activities_responsible` — per-activity rows with `task_id`, `slip_days`, `cause_category` (one of the categories from `compute_gain_loss_attribution`)

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/delay_analysis.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py`

- [ ] **Step 1: Write failing test**

Append to `test_delay_analysis.py`:

```python
class TestComputeWindowAnalysis(unittest.TestCase):
    """compute_window_analysis groups slip by named time windows."""

    def setUp(self):
        self.cache = CpmCache()
        self.base_path = str(FIXTURES / "multi_driver_slip_baseline.xer")
        self.curr_path = str(FIXTURES / "multi_driver_slip_current.xer")
        self.base_parsed = self.cache.get_parsed(self.base_path)
        self.curr_parsed = self.cache.get_parsed(self.curr_path)
        self.base_cpm = self.cache.get_cpm(self.base_path)
        self.curr_cpm = self.cache.get_cpm(self.curr_path)

    def test_single_window_returns_one_entry(self):
        windows = [{"start": "2026-05-25", "end": "2026-07-01",
                    "label": "May 25 – Jul 1"}]
        result = compute_window_analysis(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            windows=windows,
        )
        self.assertIn("windows", result)
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["label"], "May 25 – Jul 1")

    def test_window_activities_responsible_has_cause_category(self):
        windows = [{"start": "2026-05-25", "end": "2026-07-01",
                    "label": "test"}]
        result = compute_window_analysis(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            windows=windows,
        )
        for activity in result["windows"][0]["activities_responsible"]:
            self.assertIn("cause_category", activity)
            self.assertIn(activity["cause_category"], (
                "operational_slip", "logic_change", "duration_change",
                "calendar_change", "scope_change", "unknown",
            ))
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement `compute_window_analysis`**

Add to `delay_analysis.py`:

```python
def compute_window_analysis(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    windows: list,
    milestone_id: Optional[str] = None,
) -> dict:
    """Contemporaneous period analysis: per-window slip attribution.

    For each named time window, identify activities whose baseline
    early_finish fell inside the window AND that slipped between
    baseline and current. Categorize each activity's cause via the
    same algorithm as :func:`cross_baseline.compute_gain_loss_attribution`.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        windows:         list of ``{start, end, label}`` dicts. Dates are
            ``YYYY-MM-DD`` strings.
        milestone_id:    Optional terminal milestone task_id.

    Returns:
        ``{milestone_id, windows: [{label, start, end, slip_days,
        activities_responsible: [{task_id, task_code, task_name,
        slip_days, cause_category}, ...]}, ...]}``.
    """
    from cross_baseline import compute_gain_loss_attribution

    attribution = compute_gain_loss_attribution(
        baseline_parsed, current_parsed,
        baseline_cpm, current_cpm,
        milestone_id=milestone_id,
    )

    # Flatten the categorized contributors into a single lookup keyed by
    # task_code -> cause_category. For multi-cause activities, pick the
    # first category found in the priority order (a deliberate choice for
    # window-analysis output; the per-category view lives in
    # compute_gain_loss_attribution).
    priority = (
        "scope_change", "calendar_change", "duration_change",
        "logic_change", "operational_slip",
    )
    cause_by_code: dict = {}
    contribution_by_code: dict = {}
    for category in priority:
        for row in attribution["contributors_by_category"].get(category, []):
            code = row.get("task_code")
            if code and code not in cause_by_code:
                cause_by_code[code] = category
                contribution_by_code[code] = row.get("contribution_days", 0)

    # Baseline-finish lookup for window membership.
    base_by_code = {
        r.get("task_code"): r
        for r in baseline_parsed.get("TASK", []) if r.get("task_code")
    }

    out_windows = []
    for w in windows:
        start = w.get("start", "")
        end = w.get("end", "")
        activities = []
        total_slip = 0
        for code, cause in cause_by_code.items():
            base_row = base_by_code.get(code, {})
            baseline_finish = (base_row.get("early_end_date") or "")[:10]
            if not baseline_finish:
                continue
            if start <= baseline_finish <= end:
                slip = contribution_by_code.get(code, 0)
                activities.append({
                    "task_id": base_row.get("task_id", ""),
                    "task_code": code,
                    "task_name": base_row.get("task_name", ""),
                    "slip_days": slip,
                    "cause_category": cause,
                })
                total_slip += slip
        activities.sort(key=lambda r: abs(r["slip_days"]), reverse=True)
        out_windows.append({
            "label": w.get("label", ""),
            "start": start,
            "end": end,
            "slip_days": total_slip,
            "activities_responsible": activities,
        })

    return {
        "milestone_id": attribution["milestone_id"],
        "windows": out_windows,
    }
```

- [ ] **Step 4: Run tests, verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/delay_analysis.py scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py
git commit -m "feat(scheduling): compute_window_analysis time-window slip attribution"
```

### Task F4: Implement `compute_change_order_delay`

Algorithm: split the net SC slip into "attributable to the change event" vs "attributable to other causes." The change-event date partitions baseline-finish into pre-event and post-event activities. Owner activities (the input list) and activities slipped *after* `change_event_date` are bucketed as owner-attributable; others as contractor or other.

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/delay_analysis.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py`

- [ ] **Step 1: Write failing test, then implement, then commit** — same TDD pattern as Task F2 / F3. Below is the wrapper signature; the algorithm fills in the standard `compute_gain_loss_attribution` cause categorization plus the owner-attribution partition.

```python
def compute_change_order_delay(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    change_event_date: str,
    owner_activities: Optional[list] = None,
    milestone_id: Optional[str] = None,
) -> dict:
    """Owner-vs-contractor attribution from a change-directive date.

    The change_event_date partitions the schedule: activities whose
    baseline_finish was on or after the change_event_date AND that
    appear in owner_activities (or that have a scope_change /
    duration_change / logic_change reason post-event) are bucketed as
    attributable to the change event. Everything else is bucketed as
    other causes (or contractor-attributable).

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        change_event_date: ISO ``YYYY-MM-DD`` partition date.
        owner_activities: Optional explicit list of task_ids the owner is
            responsible for. When provided, these are treated as
            change-event-attributable regardless of cause category.
        milestone_id:    Optional terminal milestone task_id.

    Returns:
        ``{milestone_id, change_event_date, total_slip_days,
        attributable_to_change_event, attributable_to_other_causes,
        breakdown: [{task_code, attribution, days, cause_category}, ...]}``.
    """
    from cross_baseline import compute_gain_loss_attribution

    owner_set = set(owner_activities or [])
    attribution = compute_gain_loss_attribution(
        baseline_parsed, current_parsed,
        baseline_cpm, current_cpm,
        milestone_id=milestone_id,
    )

    base_by_id = {
        r.get("task_id"): r for r in baseline_parsed.get("TASK", [])
    }
    base_by_code = {
        r.get("task_code"): r
        for r in baseline_parsed.get("TASK", []) if r.get("task_code")
    }

    breakdown = []
    sum_change = 0
    sum_other = 0
    for category, rows in attribution["contributors_by_category"].items():
        for row in rows:
            code = row.get("task_code")
            base_row = base_by_code.get(code, {})
            baseline_finish = (base_row.get("early_end_date") or "")[:10]
            task_id = base_row.get("task_id")
            days = row.get("contribution_days", 0)

            # Attribution rules:
            #  1. If task_id is in owner_activities -> change_event.
            #  2. Else if scope_change AND baseline_finish >= event_date -> change_event.
            #  3. Else -> other.
            if task_id in owner_set:
                attribution_kind = "change_event"
            elif category == "scope_change" and baseline_finish >= change_event_date:
                attribution_kind = "change_event"
            else:
                attribution_kind = "other"
            breakdown.append({
                "task_code": code,
                "attribution": attribution_kind,
                "days": days,
                "cause_category": category,
            })
            if attribution_kind == "change_event":
                sum_change += days
            else:
                sum_other += days

    return {
        "milestone_id": attribution["milestone_id"],
        "change_event_date": change_event_date,
        "total_slip_days": attribution["net_slip_days"],
        "attributable_to_change_event": sum_change,
        "attributable_to_other_causes": sum_other,
        "breakdown": breakdown,
    }
```

Tests should assert: (1) required keys present, (2) when `owner_activities=[40006]` (C1000 in multi_driver_slip_current), C1000 is bucketed as change_event in `breakdown`, (3) `attributable_to_change_event + attributable_to_other_causes` is close to (may not equal due to multi-cause) `total_slip_days`.

- [ ] **Step N: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/delay_analysis.py scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py
git commit -m "feat(scheduling): compute_change_order_delay owner-attribution"
```

### Task F5: Implement `find_concurrent_delay_pairs`

Algorithm: find pairs of activities (a, b) where:
- Both slipped (contribution_days != 0 in the current schedule vs baseline).
- Neither is a transitive predecessor of the other (no logic relationship between them).
- Their slipping windows overlap — both activities' baseline-finish dates fall within a single shared window (the spec says "shared_window").

The shared_window is the intersection of each activity's `[baseline_start, baseline_finish]` ranges. If they don't overlap, they're not concurrent.

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/delay_analysis.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py`

- [ ] **Step 1-5: TDD cycle** — same pattern as Task F4.

```python
def find_concurrent_delay_pairs(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    """Find pairs of slipping activities with no logic relationship.

    A "concurrent pair" is two activities (a, b) where:
    * Both slipped between baseline and current.
    * Neither is in the other's transitive-predecessor closure.
    * Their baseline (planned) ``[early_start, early_finish]`` ranges
      overlap -- the slips happened simultaneously.

    Concurrent delays are a classic contractor defense in delay claims
    -- if owner-attributable delay X happened simultaneously with
    contractor-attributable delay Y, the contractor argues X doesn't
    extend the project beyond what Y was already doing.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        milestone_id:    Optional terminal milestone task_id.

    Returns:
        ``{milestone_id, concurrent_pairs: [{activity_a, activity_b,
        shared_window: {start, end}, owner_a, owner_b}, ...]}``.
        ``owner_a`` / ``owner_b`` default to ``"unknown"`` -- the caller
        is responsible for layering owner attribution from
        :func:`compute_change_order_delay` if needed.
    """
    # Build the slip set (task_codes with nonzero ef_slip_days).
    cmp_result = compare_xer_pair(
        baseline_parsed, current_parsed, match_by="task_code",
    )
    slipping = [
        row for row in cmp_result.get("date_slippage", [])
        if row.get("ef_slip_days", 0) != 0
    ]
    if len(slipping) < 2:
        return {
            "milestone_id": milestone_id or baseline_cpm[1].get("sc_milestone_id"),
            "concurrent_pairs": [],
        }

    # Build the transitive-predecessor closure on the BASELINE side.
    closure = _transitive_pred_closure(baseline_parsed.get("TASKPRED", []))

    base_by_code = {
        r.get("task_code"): r
        for r in baseline_parsed.get("TASK", []) if r.get("task_code")
    }
    pairs = []
    n = len(slipping)
    for i in range(n):
        for j in range(i + 1, n):
            a_row = slipping[i]
            b_row = slipping[j]
            a_code = a_row.get("task_code")
            b_code = b_row.get("task_code")
            a_id = base_by_code.get(a_code, {}).get("task_id")
            b_id = base_by_code.get(b_code, {}).get("task_id")
            if a_id in closure.get(b_id, set()) or b_id in closure.get(a_id, set()):
                continue  # one is a (transitive) pred of the other
            a_start = (base_by_code[a_code].get("early_start_date") or "")[:10]
            a_end = (base_by_code[a_code].get("early_end_date") or "")[:10]
            b_start = (base_by_code[b_code].get("early_start_date") or "")[:10]
            b_end = (base_by_code[b_code].get("early_end_date") or "")[:10]
            if not all((a_start, a_end, b_start, b_end)):
                continue
            shared_start = max(a_start, b_start)
            shared_end = min(a_end, b_end)
            if shared_start > shared_end:
                continue  # windows don't overlap
            pairs.append({
                "activity_a": {
                    "task_code": a_code,
                    "task_name": a_row.get("task_name", ""),
                    "slip_days": a_row.get("ef_slip_days", 0),
                },
                "activity_b": {
                    "task_code": b_code,
                    "task_name": b_row.get("task_name", ""),
                    "slip_days": b_row.get("ef_slip_days", 0),
                },
                "shared_window": {"start": shared_start, "end": shared_end},
                "owner_a": "unknown",
                "owner_b": "unknown",
            })

    return {
        "milestone_id": milestone_id or baseline_cpm[1].get("sc_milestone_id"),
        "concurrent_pairs": pairs,
    }


def _transitive_pred_closure(preds: list) -> dict:
    """Build ``{task_id: set(transitive_predecessor_task_ids)}``."""
    direct: dict = {}
    for r in preds:
        direct.setdefault(r.get("task_id"), set()).add(r.get("pred_task_id"))
    closure: dict = {}
    for tid in direct:
        stack = list(direct[tid])
        seen = set()
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            stack.extend(direct.get(p, set()))
        closure[tid] = seen
    return closure
```

Tests should assert: against the `concurrent_delay_baseline.xer` / `concurrent_delay_current.xer` pair, the result contains exactly one concurrent pair with A1000 and B1000 in `activity_a` / `activity_b` (order may swap — assert as a set).

- [ ] **Step N: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/delay_analysis.py scheduling/skills/schedule-toolbox/tests/test_delay_analysis.py
git commit -m "feat(scheduling): find_concurrent_delay_pairs simultaneous-slip detection"
```

---

## Phase G: Tier 2 MCP tool adapters (`tools/delay_analysis.py`)

Goal: four MCP tool wrappers, one per Phase F lib function. Same `_impl(...)` + `register(mcp, cache)` pattern as the F-batch and Phase D.

### Task G1: Scaffold `tools/delay_analysis.py` + register on the server

**Files:**
- Create: `scheduling/mcp-server/tools/delay_analysis.py`
- Create: `scheduling/mcp-server/tests/test_delay_analysis.py`
- Modify: `scheduling/mcp-server/server.py`

- [ ] **Step 1: Write the module skeleton**

Create `scheduling/mcp-server/tools/delay_analysis.py`:

```python
"""Tier 2 forensic-delay-analysis MCP tools.

Thin adapters around ``schedule-toolbox/lib/delay_analysis.py``. Each tool
fetches cached parsed + CPM inputs and forwards to the matching lib
function:

* :func:`compute_tia` -- Time Impact Analysis (single XER + fragnet).
* :func:`compute_window_analysis` -- contemporaneous period analysis.
* :func:`compute_change_order_delay` -- owner-attribution.
* :func:`get_concurrent_delay_pairs` -- concurrent-slip pairs.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from delay_analysis import (  # noqa: E402
    compute_change_order_delay,
    compute_tia,
    compute_window_analysis,
    find_concurrent_delay_pairs,
)
```

Modify `scheduling/mcp-server/server.py` to register the new module:

```python
from tools import (
    compare,
    cpm_path,
    delay_analysis,        # NEW
    omnibus,
    quality,
    structure,
    update_analytics,
    update_review,
)

# ... after update_analytics.register(...):
delay_analysis.register(mcp, _cache)
```

- [ ] **Step 2: Commit**

```bash
git add scheduling/mcp-server/tools/delay_analysis.py scheduling/mcp-server/tests/test_delay_analysis.py scheduling/mcp-server/server.py
git commit -m "feat(scheduling): scaffold delay_analysis MCP tool module"
```

### Task G2: Implement the four Tier 2 tool wrappers (batched TDD)

Same shape as Phase D Task D2. Four tools, one commit each.

| MCP tool | `lib/` function | Wrapper extras |
|----------|-----------------|----------------|
| `compute_tia` | `compute_tia` | Accepts `baseline_xer_path`, `delay_fragment`, `milestone_id?`. Single XER input (not a pair). |
| `compute_window_analysis` | `compute_window_analysis` | Accepts both paths + `windows: list`, `milestone_id?`. |
| `compute_change_order_delay` | `compute_change_order_delay` | Accepts both paths + `change_event_date`, `owner_activities?`, `milestone_id?`. |
| `get_concurrent_delay_pairs` | `find_concurrent_delay_pairs` | Accepts both paths + `milestone_id?`. Note the MCP tool name is `get_concurrent_delay_pairs` (per spec) but the lib function is `find_concurrent_delay_pairs` (verb consistency with other lib code). |

**Wrapper template (`compute_tia` shown — others follow the same shape):**

```python
def compute_tia_impl(
    baseline_xer_path: str,
    delay_fragment: dict,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests."""
    parsed = cache.get_parsed(baseline_xer_path)
    cpm = cache.get_cpm(baseline_xer_path)
    return compute_tia(parsed, cpm, delay_fragment, milestone_id=milestone_id)
```

And in `register(mcp, cache)`:

```python
@mcp.tool()
def compute_tia(
    baseline_xer_path: str,
    delay_fragment: dict,
    milestone_id: Optional[str] = None,
) -> dict:
    """Time Impact Analysis: insert a delay fragnet, re-run CPM, report
    projected SC slip.

    Args:
        baseline_xer_path: Path to the baseline .xer file.
        delay_fragment: dict with required keys ``activity_id``,
            ``duration_days``, ``predecessor_activity_id``; optional
            ``predecessor_relationship_type`` (default ``"PR_FS"``),
            ``calendar_id`` (defaults to the predecessor's), and
            ``description``.
        milestone_id: Optional terminal milestone task_id. Omit on
            single-terminal schedules to auto-resolve.

    Returns:
        ``{milestone_id, baseline_completion, projected_completion,
        net_delay_days, critical_path_changed, new_critical_activities,
        removed_critical_activities, affected_activities}``.
    """
    return compute_tia_impl(
        baseline_xer_path, delay_fragment, milestone_id, cache,
    )
```

- [ ] **Step 1-N: TDD cycle per tool — 4 commits.** Each test asserts the wrapper returns the expected top-level keys and one shape-specific value (e.g. for `compute_tia`, `net_delay_days == 7` against `tia_baseline.xer` with the 5-day fragment from Task F2's test).

- [ ] **Step N+1: Manual smoke test**

In Claude Code after plugin reload:

```text
ToolSearch select:compute_tia,get_concurrent_delay_pairs

compute_tia(
  baseline_xer_path="<repo>/scheduling/mcp-server/tests/fixtures/tia_baseline.xer",
  delay_fragment={
    "activity_id": "RFI-101",
    "duration_days": 10,
    "description": "Foundation rebar substitution",
    "predecessor_activity_id": "50002"
  }
)
```

Verify the result shows a 14-day SC slip (10 working days × 7/5 = 14 calendar days).

---

## Phase H: Cleanup batch

Three small tasks the Plan-1 reviewer flagged. They share Plan 2's release so the cleanup ships with the analytics work.

### Task H1: Add `multi_terminal.xer` test coverage for ambiguity errors

**Files:**
- Modify: `scheduling/mcp-server/tests/test_cpm_path.py`

- [ ] **Step 1: Add tests asserting MilestoneAmbiguousError**

Add a new test class:

```python
class TestMilestoneAmbiguous(unittest.TestCase):
    """multi_terminal.xer has two TT_FinMile activities with no
    successors. Tools that auto-resolve the terminal milestone should
    raise MilestoneAmbiguousError carrying both candidates when
    milestone_id is omitted."""

    def setUp(self):
        self.cache = CpmCache()
        self.fixture = str(FIXTURES_DIR / "multi_terminal.xer")

    def test_get_milestone_path_coverage_raises_with_candidates(self):
        from milestones import MilestoneAmbiguousError
        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            cpm_path.get_milestone_path_coverage_impl(
                self.fixture, milestone_id=None, cache=self.cache,
            )
        self.assertGreaterEqual(len(ctx.exception.candidates), 2)

    def test_get_delay_impacts_raises_with_candidates(self):
        from milestones import MilestoneAmbiguousError
        with self.assertRaises(MilestoneAmbiguousError):
            cpm_path.get_delay_impacts_impl(
                self.fixture, impact_activities=None, milestone_id=None,
                cache=self.cache,
            )

    def test_explicit_milestone_id_succeeds(self):
        # Pass an explicit terminal milestone -- no error.
        result = cpm_path.get_milestone_path_coverage_impl(
            self.fixture, milestone_id="20002", cache=self.cache,
        )
        self.assertIn("sc_task_id", result)
```

Add the import: `from milestones import MilestoneAmbiguousError` at the top of `test_cpm_path.py` if not already present.

- [ ] **Step 2: Run tests**

```bash
python -m unittest scheduling.mcp-server.tests.test_cpm_path.TestMilestoneAmbiguous -v
```

Expected: 3 tests pass. If one fails because the underlying lib function doesn't raise `MilestoneAmbiguousError` against a multi-terminal schedule, that's a real bug — escalate to the user as a Plan-1 hangover rather than fixing it here.

- [ ] **Step 3: Commit**

```bash
git add scheduling/mcp-server/tests/test_cpm_path.py
git commit -m "test(scheduling): multi_terminal.xer ambiguity-error coverage"
```

### Task H2: Add registration assertions in `test_server.py`

**Files:**
- Modify: `scheduling/mcp-server/tests/test_server.py`

- [ ] **Step 1: Add assertion that one tool from each registered module is discoverable**

Append to the existing `TestServer` class:

```python
def test_one_tool_from_each_module_is_registered(self):
    """Catches typos in server.py's register() calls. If a module's
    register(mcp, cache) gets dropped, this fails immediately rather
    than waiting for an end-to-end smoke test."""
    tool_names = self._list_tool_names(server.mcp)
    expected_representatives = {
        "structure": "get_milestones",
        "cpm_path": "get_critical_path",
        "quality": "get_quality_check",
        "update_review": "get_activities_to_start",
        "compare": "compare_activity_changes",
        "omnibus": "weekly_update_review",
        "update_analytics": "get_critical_path_changes",   # Plan 2
        "delay_analysis": "compute_tia",                   # Plan 2
    }
    missing = [
        name for name in expected_representatives.values()
        if name not in tool_names
    ]
    self.assertEqual(
        missing, [],
        f"Tools missing from server registration: {missing}. "
        f"Check server.py imports + register() calls.",
    )
```

- [ ] **Step 2: Run, verify passes**

- [ ] **Step 3: Commit**

```bash
git add scheduling/mcp-server/tests/test_server.py
git commit -m "test(scheduling): assert one tool from each registered module is discoverable"
```

---

## Phase I: Release

### Task I1: Bump plugin version + marketplace version

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json` (version field)
- Modify: `.claude-plugin/marketplace.json` (matching scheduling entry)

- [ ] **Step 1: Set both versions to `8.0.0`**

This is a major bump because:
- The omnibus `weekly_update_review` output shape changed: `pending_plan_2: true` removed; `critical_path_changes` and `gain_loss_attribution` populated rather than null.
- The omnibus `weekly_update_review` gained a `match_by` parameter (backwards-compatible default, but worth signalling).
- Eight new MCP tools were added.

- [ ] **Step 2: Verify the lockstep pre-commit hook would pass**

```bash
bash .githooks/test_pre_commit.sh
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore(scheduling): release 8.0.0 (Tier 1 + Tier 2 analytics)"
```

### Task I2: Open PR + merge

- [ ] **Step 1: Push the branch**

```bash
git push -u origin claude/reverent-wilbur-343c19
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "scheduling 8.0.0: Tier 1 + Tier 2 MCP analytics (Plan 2)" --body "$(cat <<'EOF'
## Summary

- Tier 1 update-analytics: `get_critical_path_changes`, `get_float_consumption`, `get_trade_slip_summary`, `get_gain_loss_attribution`
- Tier 2 delay-analysis: `compute_tia`, `compute_window_analysis`, `compute_change_order_delay`, `get_concurrent_delay_pairs`
- `weekly_update_review` omnibus: Plan-1 stubs filled in, `match_by` parameter exposed
- Cleanup: shared helpers consolidated into `tools/_common.py`, multi-terminal ambiguity coverage, server-registration test

## Test plan

- [ ] Lib-level tests pass: `python -m unittest discover -s scheduling/skills/schedule-toolbox/tests -v`
- [ ] MCP-wrapper tests pass: `python -m unittest discover -s scheduling/mcp-server/tests -v`
- [ ] Plugin manifest version + marketplace version both at `8.0.0`
- [ ] Smoke test against a real project XER (W1177 or Wellington Temple): call `get_gain_loss_attribution` against a baseline/current pair and verify the summary paragraph reads correctly

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Merge after review**

Squash or merge per repo convention.

### Task I3: Build + distribute

- [ ] **Step 1: Switch to the main checkout (NOT the worktree), pull**

```bash
# From C:\Users\camron\code\construction-skills (the main repo, NOT under .claude/worktrees/):
git switch main
git pull --ff-only
```

- [ ] **Step 2: Build**

```bash
python build.py scheduling
```

- [ ] **Step 3: Verify zip artifact contains the new modules**

```bash
unzip -l src/scheduling.zip | grep -E "(cross_baseline|delay_analysis|update_analytics|_common)\.py"
```

Expected: `cross_baseline.py`, `delay_analysis.py`, `tools/update_analytics.py`, `tools/delay_analysis.py`, `tools/_common.py` all present.

- [ ] **Step 4: Distribute**

Upload `src/scheduling.zip` to enterprise plugin distribution. Notify the 4 schedulers — `pip install mcp` already done from Plan 1; just `/plugin update scheduling` picks up 8.0.0.

### Task I4: Smoke test on a real project

- [ ] **Step 1: Pick a project with both baseline and current XER**

W1177 (recent weekly update) or Wellington Temple have a couple of week-over-week XER pairs in their Schedules folders.

- [ ] **Step 2: Exercise the new tools**

In Claude Code:

```text
ToolSearch select:get_critical_path_changes,get_gain_loss_attribution,compute_tia,get_concurrent_delay_pairs

get_milestones(xer_path="<current.xer>")
# Pick the SC milestone task_id from the result

get_critical_path_changes(
  baseline_xer_path="<baseline.xer>",
  current_xer_path="<current.xer>",
  milestone_id="<chosen>",
)

get_gain_loss_attribution(
  baseline_xer_path="<baseline.xer>",
  current_xer_path="<current.xer>",
  milestone_id="<chosen>",
)
```

- [ ] **Step 3: Verify behavior**

- `get_critical_path_changes` returns the actual CP shift narrative.
- `get_gain_loss_attribution.weekly_email_documentation.summary_paragraph_seed` reads like a credible first draft of the email's gain/loss narrative.
- `compute_tia` against the current XER with a synthetic fragnet returns a sensible projected SC.
- The PreToolUse hook still blocks `Read` against `scheduling/skills/schedule-toolbox/lib/*.py` files (Plan 1 reinforcement still works).

- [ ] **Step 4: Document any surprises in `MEMORY.md`**

Lessons-learned cycle — capture anything the smoke test surfaces for Plan 3 to fold in.

---

## Self-review

Checking the plan against the spec and Plan 1's deferral list:

**1. Spec coverage:**

| Spec requirement | Where addressed |
|------------------|-----------------|
| § Update analytics tools (Tier 1) — 4 tools | Phase C (lib) + Phase D (MCP wrappers) ✓ |
| § Delay analysis tools (Tier 2) — 4 tools | Phase F (lib) + Phase G (MCP wrappers) ✓ |
| § Gain/loss output shape (signed contribution, multi-cause, needs_narrative) | Phase C Task C5 algorithm spec ✓ |
| § `weekly_update_review` Plan-2 fill-in | Phase E ✓ |
| § F2-F5 reviewer flag — `tools/_common.py` consolidation | Phase A ✓ |
| § F2-F5 reviewer flag — `match_by` parameter on `weekly_update_review` | Phase E (added to the omnibus signature) ✓ |
| § F2-F5 reviewer flag — `multi_terminal.xer` ambiguity coverage | Phase B Task B1 (fixture) + Phase H Task H1 (test) ✓ |
| § F2-F5 reviewer flag — `test_server.py` registration assertions | Phase H Task H2 ✓ |
| § Cross-baseline cache strategy (open question from prompt) | Resolved in Architecture preamble: `extract_paths` is in-memory; no new cache slot needed. 8-entry LRU comfortably covers a weekly-update workflow. |
| § Test fixtures | Phase B covers `multi_terminal`, `cp_baseline`/`cp_shifted`, `multi_driver_slip_baseline`/`_current`, `tia_baseline`, `concurrent_delay_baseline`/`_current` ✓ |
| § Plan-2 version bump (8.0.0) | Phase I Task I1 ✓ |

**Deferred to Plan 3:** Tier 3 modification tools (`apply_xer_changes`, `fix_duplicate_activity_ids`, `validate_xer_structure`, `create_xer_from_template`, `invalidate_cache_for`), the Westland skeleton extraction + curation, and any compositional generation work. Plan 2 is strictly read/analyze; no XER writing beyond the existing Plan 1 `run_cpm` write-through pattern.

**Other spec items NOT in scope for Plan 2 (deliberately):**
- `xer_parse` raw-table tool (spec open question 2: recommend not adding initially)
- Per-tool input validation standardization (spec open question 3: lands with Tier 3's `validate_xer_structure`)
- Owner-attribution sidecar shape for `compute_change_order_delay` (spec open question 5: the tool accepts an explicit `owner_activities` list; sidecar-file ingestion can land in Plan 3 if needed)
- Trade-tagging canonical field (spec open question 4: `compute_trade_slip_summary` accepts `trade_field` parameter with a sensible default; locking the canonical field is a lessons-learned-cycle outcome, not a Plan 2 blocker)

**2. Placeholder scan:**

Phase D Task D2 and Phase G Task G2 batch the four-tool TDD cycles into "Step 1-N per tool" with full templates shown. This matches Plan 1's convention (Phase F batched the F1-F5 cycles the same way). The wrapper template, the registration template, and the test template are all fully shown — no `// TODO`, no "implement later." Per-tool variance is in the task tables.

Phase F Task F4 and F5 abbreviate the TDD cycle steps ("Step 1-5: TDD cycle — same pattern as Task F2") rather than spelling each step out, but the lib function bodies are fully spec'd and the test assertions are spec'd in the task body. The pattern is the same as Plan 1 Phase F (the 10-tool F1 batch abbreviated the same way after E1 set the template).

No "TBD" / "fill in later" / "add appropriate error handling" anywhere.

**3. Type consistency:**

- `_override_sc_milestone(metadata, milestone_id, tasks)` defined in Phase C Task C2's `cross_baseline.py`; referenced in Phase F Task F2's `delay_analysis.py` via cross-module import. Signature stable across both modules.
- `_date_delta_days(base_str, curr_str)` defined in Phase C Task C5; referenced in Phase F Task F2. Same signature.
- `CpmCache.get_parsed(xer_path)` and `CpmCache.get_cpm(xer_path)` — used identically in Phase D, Phase E, and Phase G. The `get_cpm` return is unpacked as `(results, metadata)` consistently throughout.
- `compute_gain_loss_attribution` output shape: the `contributors_by_category` dict's category keys (`operational_slip`, `logic_change`, `duration_change`, `calendar_change`, `scope_change`) match the spec's shape and the Phase F Task F3 `compute_window_analysis` consumer's expected priority order.
- The `MilestoneAmbiguousError.candidates` attribute (Plan 1 D1) is read in Phase H Task H1's test (`ctx.exception.candidates`). Same attribute name throughout.

**4. Ambiguity flags:**

- Phase C Task C4 (`compute_trade_slip_summary`): the `trade_field` auto-detect strategy is a best-guess. Plan 1's lessons-learned cycle is the right venue to lock the canonical Westland trade-field after the first real project uses this tool.
- Phase F Task F2 (`compute_tia`): the calendar inheritance ("use predecessor's calendar if `calendar_id` not provided") is pragmatic. If a fragnet legitimately needs a different calendar (e.g. weather-impacted activity), the caller passes `calendar_id` explicitly. Otherwise this default holds.
- Phase F Task F4 (`compute_change_order_delay`): the attribution rules (owner_activities override > scope_change post-event > else other) are a simple model. Real delay claims often involve "but-for" causation that requires layering. This tool is a first cut; Plan 3 may add a "rule_overrides" parameter for project-specific attribution logic.
- Phase F Task F5 (`find_concurrent_delay_pairs`): "neither is a transitive predecessor of the other" uses baseline-side topology. If logic relationships were added in the current snapshot that create a path between two previously-independent activities, they'd no longer be "concurrent" by this definition under the current side — but the function checks baseline. This is intentional (concurrent delay analysis looks at the as-planned topology, not the as-built) but worth flagging.

---

**Plan complete and saved to** [`docs/superpowers/plans/2026-05-26-westland-scheduler-mcp-plan-2-analytics.md`](2026-05-26-westland-scheduler-mcp-plan-2-analytics.md)**. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks. Works well for Plan 2 because most lib-level TDD cycles in Phase C and Phase F are independent (one algorithm at a time) and the MCP wrappers in Phase D / Phase G are structurally identical.

**2. Inline Execution** — Execute tasks in this session via executing-plans with batch checkpoints.

**Which approach?**

