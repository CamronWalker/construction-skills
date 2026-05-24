# Westland Scheduler Local MCP — Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Westland Scheduler Local MCP server with the 33 base-catalog (Tier 0) tools, wired into Claude Code via the scheduling plugin's manifest, with a CPM result cache and the source-hiding seam (`references/` → `lib/`, PreToolUse hook). On release, schedulers immediately stop seeing the failure modes diagnosed in the spec (introspection, in-place edits, reimplementation).

**Architecture:** Local Python MCP server bundled with the scheduling plugin. Server registers tools via the official `mcp` Python SDK; each tool is a thin adapter that imports the existing analysis functions from `scheduling/skills/schedule-toolbox/lib/` and returns structured JSON. CPM-current results are cached in-memory keyed by `(xer_path, size, mtime)`. The existing Python scripts stay importable for non-Claude callers (e.g. `iterate.py`).

**Tech Stack:**
- Python 3.10+ (already required by the existing scripts)
- Official `mcp` Python SDK (≥0.9.0)
- Standard library `unittest` for tests
- Existing tab-delimited XER parsing already in `lib/`

**Reference spec:** [2026-05-24-schedule-toolbox-mcp-design.md](../specs/2026-05-24-schedule-toolbox-mcp-design.md)

---

## File Structure

### New files

| Path | Responsibility |
|------|----------------|
| `scheduling/mcp-server/server.py` | MCP server entry point. Boots, attaches cache, imports all tool modules, calls each module's `register(server, cache)`. |
| `scheduling/mcp-server/cache.py` | `CpmCache` class. Keyed by `(xer_path, size, mtime)`. LRU eviction. Stores parsed XER + computed CPM result separately. Includes partial-read guard (read size twice with 100ms gap). |
| `scheduling/mcp-server/errors.py` | Shared error shapes: `XerNotFoundError`, `XerInvalidError`, `MilestoneAmbiguousError` (carries candidate list), `XerLockedError`. Standardized for use across all tools. |
| `scheduling/mcp-server/__init__.py` | Empty (package marker). |
| `scheduling/mcp-server/tools/__init__.py` | Empty (package marker). |
| `scheduling/mcp-server/tools/structure.py` | `get_milestones` tool (1 tool). |
| `scheduling/mcp-server/tools/cpm_path.py` | CPM and path tools (11 tools: `run_cpm`, `get_critical_path`, `get_near_critical_chains`, `get_driving_paths`, `get_parallel_branches`, `get_anchor_conflicts`, `get_anchor_absorption_suggestions`, `get_milestone_path_coverage`, `get_delay_impacts`, `get_gantt_json`, `render_gantt_html`). |
| `scheduling/mcp-server/tools/quality.py` | Quality and scoring tools (10 tools). |
| `scheduling/mcp-server/tools/update_review.py` | Update review tools (4 tools). |
| `scheduling/mcp-server/tools/compare.py` | Compare tools (4 tools). |
| `scheduling/mcp-server/tools/omnibus.py` | Omnibus tools (3 tools: `score_schedule`, `weekly_update_review`, `proposal_schedule_health`). |
| `scheduling/mcp-server/requirements.txt` | `mcp>=0.9.0` and any pinned versions. |
| `scheduling/mcp-server/README.md` | How to install (`pip install -r requirements.txt`), how to register, common troubleshooting pointers. |
| `scheduling/mcp-server/tests/__init__.py` | Empty. |
| `scheduling/mcp-server/tests/test_cache.py` | Cache unit tests. |
| `scheduling/mcp-server/tests/test_structure.py` | `get_milestones` tests. |
| `scheduling/mcp-server/tests/test_cpm_path.py` | CPM/path tool tests. |
| `scheduling/mcp-server/tests/test_quality.py` | Quality tool tests. |
| `scheduling/mcp-server/tests/test_update_review.py` | Update review tests. |
| `scheduling/mcp-server/tests/test_compare.py` | Compare tests. |
| `scheduling/mcp-server/tests/test_omnibus.py` | Omnibus tests. |
| `scheduling/mcp-server/tests/fixtures/` | Small fixture XERs for tests. At minimum: `minimal.xer` (2 milestones), `sample_with_critical_path.xer`, `sample_with_anchors.xer`, `proposal-anchors.json`. |
| `scheduling/skills/westland-scheduler-mcp-troubleshoot/SKILL.md` | Troubleshoot skill (diagnostic-only). |
| `scheduling/skills/westland-scheduler-mcp-troubleshoot/diagnose.py` | The actual diagnostic logic — checks server registration, verifies `mcp` SDK, runs smoke test. |

### Modified files

| Path | Change |
|------|--------|
| `scheduling/skills/schedule-toolbox/references/*.py` | Move to `scheduling/skills/schedule-toolbox/lib/*.py` via `git mv`. |
| `scheduling/skills/schedule-toolbox/lib/score_schedule.py` | Replace `find_sc_milestone(tasks)` with `get_milestones(tasks)` (lists all candidates) + accept explicit `milestone_id` parameter. |
| `scheduling/skills/schedule-toolbox/lib/path_analysis.py` | SC-coverage computation: accept explicit `milestone_id`; raise `MilestoneAmbiguousError` when omitted and multiple candidates exist. |
| `scheduling/skills/schedule-toolbox/SKILL.md` | Replace routing table file-path entries with MCP tool names; remove the Cardinal Rule about not reading source files. |
| `scheduling/skills/schedule-create-proposal-schedule/examples/iterate.py` | Update imports from `references` to `lib`. |
| `scheduling/skills/schedule-update/phases/report.md` | Replace `xer_compare.py` invocation in step 3b with MCP tool calls (`compare_activity_changes` + `compare_milestone_slip` + `compare_date_slips`). |
| `scheduling/skills/schedule-update/phases/draft.md` | Same — replace direct Python calls with MCP tools. |
| `scheduling/.claude-plugin/plugin.json` | Bump version to `7.0.0`, add `mcpServers` field declaring `westland-scheduler-mcp`. |
| `.claude-plugin/marketplace.json` | Bump matching scheduling plugin entry to `7.0.0`. |
| `~/.claude/settings.json` *(or wherever Westland's PreToolUse hooks live — confirm during Task G1)* | Add hook blocking `Read`/`Edit`/`Write`/`Glob`/`Grep` on `scheduling/skills/schedule-toolbox/lib/*.py` when the active skill is not `schedule-toolbox`. |

---

## Phase A: MCP server skeleton (end-to-end thinnest slice)

Goal: a minimal MCP server with one stub tool that Claude Code can discover and invoke. Proves the registration pipeline works before building 32 more tools.

### Task A1: Create the package layout

**Files:**
- Create: `scheduling/mcp-server/__init__.py`
- Create: `scheduling/mcp-server/tools/__init__.py`
- Create: `scheduling/mcp-server/tests/__init__.py`
- Create: `scheduling/mcp-server/tests/fixtures/.gitkeep`
- Create: `scheduling/mcp-server/requirements.txt`

- [ ] **Step 1: Create the empty package files**

```bash
mkdir -p scheduling/mcp-server/tools scheduling/mcp-server/tests/fixtures
```

Write the four `__init__.py` files as empty files. Write `.gitkeep` as empty.

- [ ] **Step 2: Write `requirements.txt`**

```text
mcp>=0.9.0
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/mcp-server/
git commit -m "feat(scheduling): scaffold westland-scheduler-mcp package"
```

### Task A2: Stub `server.py` with a single sentinel tool

**Files:**
- Create: `scheduling/mcp-server/server.py`

- [ ] **Step 1: Write the failing test**

Create `scheduling/mcp-server/tests/test_server.py`:

```python
import unittest
from scheduling.mcp_server import server

class TestServer(unittest.TestCase):
    def test_server_instance_exists(self):
        self.assertIsNotNone(server.mcp)

    def test_ping_tool_registered(self):
        # The smoke-test tool. Should always succeed.
        tool_names = [t.name for t in server.mcp.list_tools()]
        self.assertIn("ping", tool_names)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.mcp_server.tests.test_server -v
```

Expected: ImportError on `server` (module doesn't exist yet).

- [ ] **Step 3: Write minimal `server.py`**

```python
"""Westland Scheduler Local MCP server entry point."""
from mcp.server import FastMCP

mcp = FastMCP("westland-scheduler-mcp")

@mcp.tool()
def ping() -> dict:
    """Health check tool. Always returns {ok: true}."""
    return {"ok": True}

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run test, verify it passes**

```bash
python -m unittest scheduling.mcp_server.tests.test_server -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/server.py scheduling/mcp-server/tests/test_server.py
git commit -m "feat(scheduling): mcp server skeleton with ping tool"
```

### Task A3: Register the MCP server in the plugin manifest

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json`

- [ ] **Step 1: Read the current manifest to capture the existing shape**

```bash
cat scheduling/.claude-plugin/plugin.json
```

Note the current `version`, current top-level fields.

- [ ] **Step 2: Add `mcpServers` field declaring the server**

Edit `scheduling/.claude-plugin/plugin.json` so it includes (alongside existing fields):

```json
{
  "mcpServers": {
    "westland-scheduler-mcp": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "${PLUGIN_DIR}/mcp-server"
    }
  }
}
```

Note: the exact `${PLUGIN_DIR}` substitution syntax — verify against Claude Code's plugin manifest docs at the time of implementation. If unsupported, fall back to a relative path that Claude Code resolves from the plugin install location. The README documents the resolved invocation.

- [ ] **Step 3: Reload Claude Code**

Manual: in Claude Code, run `/plugin reload scheduling` (or restart). Verify the MCP server appears in the tool list with the `ping` tool discoverable via `ToolSearch`.

- [ ] **Step 4: Commit (do NOT bump version yet — that's the release task)**

```bash
git add scheduling/.claude-plugin/plugin.json
git commit -m "feat(scheduling): register westland-scheduler-mcp in plugin manifest"
```

---

## Phase B: CPM result cache

Goal: in-memory cache keyed by `(xer_path, size, mtime)`, with LRU eviction and partial-read guard. All Phase E+ tools depend on this.

### Task B1: Cache key + invalidation tests

**Files:**
- Create: `scheduling/mcp-server/tests/test_cache.py`
- Create: `scheduling/mcp-server/cache.py`

- [ ] **Step 1: Write failing tests for cache key behavior**

Create `scheduling/mcp-server/tests/test_cache.py`:

```python
import os
import tempfile
import time
import unittest
from pathlib import Path

from scheduling.mcp_server.cache import CpmCache, CacheKey

FIXTURE_XER = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestCacheKey(unittest.TestCase):
    def test_key_includes_path_size_mtime(self):
        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            key = CacheKey.for_path(path)
            self.assertEqual(key.path, path)
            self.assertEqual(key.size, 5)
            self.assertGreater(key.mtime, 0)
        finally:
            os.unlink(path)

    def test_key_changes_when_file_size_changes(self):
        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            k1 = CacheKey.for_path(path)
            with open(path, "wb") as f:
                f.write(b"hello world")
            k2 = CacheKey.for_path(path)
            self.assertNotEqual(k1, k2)
        finally:
            os.unlink(path)


class TestCpmCache(unittest.TestCase):
    def test_get_parsed_caches_result(self):
        cache = CpmCache(max_entries=4)
        # Use a tiny fixture XER. Parser is the real one.
        first = cache.get_parsed(str(FIXTURE_XER))
        second = cache.get_parsed(str(FIXTURE_XER))
        # Same object reference proves the cache hit
        self.assertIs(first, second)

    def test_cache_invalidates_on_file_change(self):
        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as f:
            f.write(FIXTURE_XER.read_bytes())
            path = f.name
        try:
            cache = CpmCache(max_entries=4)
            first = cache.get_parsed(path)
            # Modify the file
            time.sleep(0.1)
            with open(path, "ab") as f:
                f.write(b"\n")
            second = cache.get_parsed(path)
            self.assertIsNot(first, second)
        finally:
            os.unlink(path)

    def test_lru_eviction(self):
        cache = CpmCache(max_entries=2)
        # Insert 3 fake parsed entries via internal API
        cache._put("a.xer", CacheKey("a.xer", 1, 1.0), {"parsed": "A"})
        cache._put("b.xer", CacheKey("b.xer", 1, 1.0), {"parsed": "B"})
        cache._put("c.xer", CacheKey("c.xer", 1, 1.0), {"parsed": "C"})
        self.assertNotIn("a.xer", cache._entries)
        self.assertIn("b.xer", cache._entries)
        self.assertIn("c.xer", cache._entries)


if __name__ == "__main__":
    unittest.main()
```

You'll need a minimal fixture XER. For now write `tests/fixtures/minimal.xer` containing the smallest valid XER:

```text
ERMHDR	19.12	2026-05-24	Project	camron	camron	US$	USD	$
%T	PROJECT
%F	proj_id	fy_start_month_num	rsrc_self_add_flag	allow_complete_flag	rsrc_multi_assign_flag	checkout_flag	project_flag	step_complete_flag	cost_qty_recalc_flag	batch_sum_flag	name_sep_char	def_complete_pct_type	proj_short_name	acct_id	orig_proj_id	source_proj_id	base_type_id	clndr_id	sum_base_proj_id	task_code_base	task_code_step	priority_num	wbs_max_sum_level	strgy_priority_num	last_checksum	critical_drtn_hr_cnt	def_cost_per_qty	last_recalc_date	plan_start_date	plan_end_date	scd_end_date	add_date	last_tasksum_date	fcst_start_date	def_duration_type	task_code_prefix	guid	def_qty_type	add_by_name	web_local_root_path	proj_url	def_rate_type	add_act_remain_flag	act_this_per_link_flag	def_task_type	act_pct_link_flag	critical_path_type	task_code_prefix_flag	def_rollup_dates_flag	use_project_baseline_flag	rem_target_link_flag	reset_planned_flag	allow_neg_act_flag	sum_assign_level	last_fin_dates_id	last_baseline_update_date	cr_external_key	apply_actuals_date	location_id	loaded_scope_level	export_flag	new_fin_dates_id	baselines_to_export	baseline_names_to_export	next_data_date	close_period_flag	sum_refresh_date	trsrcsum_loaded
%R	1	1	N	Y	N	N	Y	N	N	N	.	CP_Drtn	WSL	1	1		1	1		A1000	10	500	50	500		8	0		2026-05-24 00:00	2026-05-24 00:00		2026-05-24 00:00		2026-05-24 00:00	DT_FixedDUR2	A	{00000000-0000-0000-0000-000000000000}	QT_Item	camron					Y	N	TT_Task	N	CT_TopFloat	N	Y	N	N	N	N	SL_Whole	0			2026-05-24 00:00		0	Y	0			2026-05-24 00:00	N		N
%T	CALENDAR
%F	clndr_id	default_flag	clndr_name	proj_id	base_clndr_id	last_chng_date	clndr_type	day_hr_cnt	week_hr_cnt	month_hr_cnt	year_hr_cnt	rsrc_private	clndr_data
%R	1	Y	5-Day Standard		0	2026-05-24 00:00	CA_Base	8.0	40.0	172.0	2080.0	N	(0|||CalendarData()(0||CalendarProperties()))
%T	TASK
%F	task_id	proj_id	wbs_id	clndr_id	phys_complete_pct	rev_fdbk_flag	est_wt	lock_plan_flag	auto_compute_act_flag	complete_pct_type	task_type	duration_type	status_code	task_code	task_name	rsrc_id	total_float_hr_cnt	free_float_hr_cnt	remain_drtn_hr_cnt	act_work_qty	remain_work_qty	target_work_qty	target_drtn_hr_cnt	target_equip_qty	act_equip_qty	remain_equip_qty	cstr_date	act_start_date	act_end_date	late_start_date	late_end_date	expect_end_date	early_start_date	early_end_date	restart_date	reend_date	target_start_date	target_end_date	rem_late_start_date	rem_late_end_date	cstr_type	priority_type	suspend_date	resume_date	float_path	float_path_order	guid	tmpl_guid	cstr_date2	cstr_type2	driving_path_flag	act_this_per_work_qty	act_this_per_equip_qty	external_early_start_date	external_late_end_date	create_date	update_date	create_user	update_user	location_id	control_updates_flag	driving_resources
%R	1001	1	1	1	0	N	1.0	N	Y	CP_Drtn	TT_Mile	DT_FixedDUR2	TK_NotStart	NTP	Notice to Proceed		0	0	0	0	0	0	0	0	0	0		2026-05-24 00:00				2026-05-24 00:00	2026-05-24 00:00			2026-05-24 00:00	2026-05-24 00:00			CS_MANDSTART	PT_Normal							{00000000-0000-0000-0000-000000000000}	{00000000-0000-0000-0000-000000000000}			N	0	0	2026-05-24 00:00	2026-05-24 00:00	2026-05-24 00:00	2026-05-24 00:00	camron	camron		N	
%R	1002	1	1	1	0	N	1.0	N	Y	CP_Drtn	TT_FinMile	DT_FixedDUR2	TK_NotStart	SC	Substantial Completion		0	0	0	0	0	0	0	0	0	0		2026-11-24 00:00				2026-11-24 00:00	2026-11-24 00:00			2026-11-24 00:00	2026-11-24 00:00			CS_MANDSTART	PT_Normal							{00000000-0000-0000-0000-000000000000}	{00000000-0000-0000-0000-000000000000}			N	0	0	2026-05-24 00:00	2026-05-24 00:00	2026-05-24 00:00	2026-05-24 00:00	camron	camron		N	
%T	TASKPRED
%F	task_pred_id	task_id	pred_task_id	proj_id	pred_proj_id	pred_type	lag_hr_cnt	float_path	aref	arls
%R	1	1002	1001	1	1	PR_FS	0			
%E
```

Verify it loads by running the existing parser:

```bash
python -c "import sys; sys.path.insert(0, 'scheduling/skills/schedule-toolbox/references'); from quality_checks import parse_xer; r = parse_xer('scheduling/mcp-server/tests/fixtures/minimal.xer'); print('OK:', len(r['tasks']), 'tasks')"
```

Expected: `OK: 2 tasks`. If the parse fails, hand-edit `minimal.xer` until it loads. The fixture is load-bearing — every cache test uses it.

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m unittest scheduling.mcp_server.tests.test_cache -v
```

Expected: ImportError on `cache` module.

- [ ] **Step 3: Implement `cache.py`**

Create `scheduling/mcp-server/cache.py`:

```python
"""CPM result cache for the Westland Scheduler MCP.

Keyed by (xer_path, size, mtime) so any file change invalidates the entry.
LRU eviction at max_entries. Caches parsed XER and computed CPM separately.
"""
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import time
import sys


@dataclass(frozen=True)
class CacheKey:
    path: str
    size: int
    mtime: float

    @classmethod
    def for_path(cls, path: str) -> "CacheKey":
        st = Path(path).stat()
        return cls(path=path, size=st.st_size, mtime=st.st_mtime)


class CpmCache:
    def __init__(self, max_entries: int = 8):
        self._max = max_entries
        self._entries: "OrderedDict[str, tuple[CacheKey, dict]]" = OrderedDict()

    def get_parsed(self, xer_path: str) -> dict:
        """Return parsed XER (cached). Invalidates on file change."""
        key = self._safe_key(xer_path)
        existing = self._entries.get(xer_path)
        if existing and existing[0] == key:
            self._entries.move_to_end(xer_path)
            entry = existing[1]
            if "parsed" in entry:
                return entry["parsed"]
        # Cache miss
        parsed = self._parse(xer_path)
        self._put(xer_path, key, {"parsed": parsed})
        return parsed

    def get_cpm(self, xer_path: str) -> dict:
        """Return CPM result (cached). Computes on first access."""
        key = self._safe_key(xer_path)
        existing = self._entries.get(xer_path)
        if existing and existing[0] == key and "cpm" in existing[1]:
            self._entries.move_to_end(xer_path)
            return existing[1]["cpm"]
        # Need parsed first
        parsed = self.get_parsed(xer_path)
        cpm_result = self._run_cpm(parsed)
        # Stash beside parsed
        existing = self._entries.get(xer_path)
        if existing:
            existing[1]["cpm"] = cpm_result
        else:
            self._put(xer_path, key, {"parsed": parsed, "cpm": cpm_result})
        return cpm_result

    def invalidate(self, xer_path: str) -> bool:
        return self._entries.pop(xer_path, None) is not None

    def _safe_key(self, xer_path: str) -> CacheKey:
        """Partial-read guard: read size twice with 100ms gap.
        If size changes between reads, file is mid-write."""
        s1 = Path(xer_path).stat()
        time.sleep(0.1)
        s2 = Path(xer_path).stat()
        if s1.st_size != s2.st_size:
            raise XerLockedError(f"{xer_path} appears to be mid-write")
        return CacheKey(path=xer_path, size=s2.st_size, mtime=s2.st_mtime)

    def _put(self, path: str, key: CacheKey, entry: dict) -> None:
        self._entries[path] = (key, entry)
        self._entries.move_to_end(path)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def _parse(self, xer_path: str) -> dict:
        # Import from the lib (post-rename) — Task C2 fixes this import path
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "schedule-toolbox" / "lib"))
        from quality_checks import parse_xer  # type: ignore
        return parse_xer(xer_path)

    def _run_cpm(self, parsed: dict) -> dict:
        sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "schedule-toolbox" / "lib"))
        from cpm_engine import run as cpm_run  # type: ignore
        return cpm_run(parsed["tasks"], parsed["preds"])


class XerLockedError(Exception):
    """Raised when the partial-read guard detects mid-write."""
```

Note: the `_parse` / `_run_cpm` path-injection is temporary scaffolding for Phase B testing. Task C2 (the `references/` → `lib/` rename) updates the import to a proper package import.

- [ ] **Step 4: Run tests, verify they pass**

```bash
python -m unittest scheduling.mcp_server.tests.test_cache -v
```

Expected: 5 tests pass. If the partial-read guard test is flaky (timing-sensitive), refactor `_safe_key` to accept an injected delay for tests.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/cache.py scheduling/mcp-server/tests/test_cache.py scheduling/mcp-server/tests/fixtures/minimal.xer
git commit -m "feat(scheduling): CPM result cache keyed by (path,size,mtime)"
```

---

## Phase C: Rename `references/` → `lib/`

Goal: source files move to a directory whose name says "implementation, don't read." Imports across the repo get updated.

### Task C1: `git mv` the Python files

**Files:**
- Move all of `scheduling/skills/schedule-toolbox/references/*.py` to `scheduling/skills/schedule-toolbox/lib/*.py`.

- [ ] **Step 1: Inventory the move set**

```bash
ls scheduling/skills/schedule-toolbox/references/*.py
```

Expected: `build_from_raw_template.py`, `calendar_engine.py`, `cpm_engine.py`, `path_analysis.py`, `quality_checks.py`, `score_schedule.py`, `update_review.py`, `xer_compare.py`.

- [ ] **Step 2: Create destination dir and move**

```bash
mkdir -p scheduling/skills/schedule-toolbox/lib
for f in scheduling/skills/schedule-toolbox/references/*.py; do
  git mv "$f" "scheduling/skills/schedule-toolbox/lib/$(basename $f)"
done
```

`references/*.md` stays in place — those are real reference docs.

- [ ] **Step 3: Verify the move**

```bash
ls scheduling/skills/schedule-toolbox/lib/*.py
ls scheduling/skills/schedule-toolbox/references/
```

Expected: 8 `.py` files in `lib/`. References dir contains only `*.md` files.

- [ ] **Step 4: Commit (compile errors expected — fixed in C2)**

```bash
git commit -m "refactor(scheduling): rename schedule-toolbox/references -> lib (py files)"
```

### Task C2: Fix all import paths

**Files:**
- Modify: `scheduling/skills/schedule-create-proposal-schedule/examples/iterate.py`
- Modify: `scheduling/mcp-server/cache.py` (the temporary sys.path injection)
- Modify: `scheduling/skills/schedule-update/phases/report.md` (Glob-resolved path in step 3b)
- Modify: any other consumer found by Grep

- [ ] **Step 1: Find every consumer**

```bash
# Use the Grep tool, not bash grep:
# pattern: "schedule-toolbox/references"
# path: scheduling/ (and any other plugin that might cross-reference)
# Also check scripts/ at repo root.
```

Build a list of files that reference the old path. Expected hits: `iterate.py`, the two `schedule-update/phases/*.md` files, possibly some docs.

- [ ] **Step 2: Update each consumer**

For each file in the list, replace `schedule-toolbox/references` with `schedule-toolbox/lib`. Use Edit tool with full strings to avoid false matches.

For `scheduling/mcp-server/cache.py`, change the import path in `_parse` / `_run_cpm`:

```python
def _parse(self, xer_path: str) -> dict:
    from scheduling.skills.schedule_toolbox.lib.quality_checks import parse_xer  # type: ignore
    return parse_xer(xer_path)
```

Note: `schedule-toolbox` has a hyphen, not underscore, in its path. The import has to use `importlib` or `sys.path` injection because Python's import system doesn't handle hyphenated paths. Keep the `sys.path.insert` approach but point at the new `lib/` directory.

- [ ] **Step 3: Re-run the existing test suites that depend on these scripts**

```bash
# Proposal-schedule iteration tests:
python -m unittest discover -s scheduling/skills/schedule-create-proposal-schedule -p "test_*.py" -v
# Schedule-update tests:
python -m unittest discover -s scheduling/skills/schedule-update/tests -v
# Cache tests:
python -m unittest scheduling.mcp_server.tests.test_cache -v
```

Expected: all pass. If any fail with `ModuleNotFoundError` referencing `references`, that's a missed import — fix and re-run.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor(scheduling): update all imports from references/ to lib/"
```

---

## Phase D: Fix milestone auto-detection

Goal: replace the brittle "find 'Substantial Completion' by name" heuristic with explicit milestone enumeration. Underlying scripts AND the MCP both benefit.

### Task D1: Add `get_milestones()` helper to `lib/`

**Files:**
- Create: `scheduling/skills/schedule-toolbox/lib/milestones.py`
- Create: `scheduling/skills/schedule-toolbox/tests/test_milestones.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from milestones import get_milestones, MilestoneAmbiguousError
from quality_checks import parse_xer

FIXTURE = Path(__file__).parent.parent.parent.parent / "mcp-server" / "tests" / "fixtures" / "minimal.xer"


class TestGetMilestones(unittest.TestCase):
    def test_returns_milestone_tasks(self):
        parsed = parse_xer(str(FIXTURE))
        result = get_milestones(parsed["tasks"])
        self.assertEqual(len(result), 2)  # NTP and SC milestones
        names = {m["task_name"] for m in result}
        self.assertIn("Substantial Completion", names)

    def test_excludes_wbs_and_loe(self):
        # Synthetic task list with a WBS-type and LOE-type entry mixed in
        tasks = [
            {"task_id": 1, "task_name": "NTP", "task_type": "TT_Mile", "status_code": "TK_NotStart"},
            {"task_id": 2, "task_name": "WBS Bar", "task_type": "TT_WBS", "status_code": "TK_NotStart"},
            {"task_id": 3, "task_name": "LOE", "task_type": "TT_LOE", "status_code": "TK_NotStart"},
            {"task_id": 4, "task_name": "SC", "task_type": "TT_FinMile", "status_code": "TK_NotStart"},
        ]
        result = get_milestones(tasks)
        task_ids = {m["task_id"] for m in result}
        self.assertEqual(task_ids, {1, 4})

    def test_excludes_complete_milestones_by_default(self):
        tasks = [
            {"task_id": 1, "task_name": "NTP", "task_type": "TT_Mile", "status_code": "TK_Complete"},
            {"task_id": 2, "task_name": "SC", "task_type": "TT_FinMile", "status_code": "TK_NotStart"},
        ]
        result = get_milestones(tasks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["task_id"], 2)

    def test_include_complete_flag(self):
        tasks = [
            {"task_id": 1, "task_name": "NTP", "task_type": "TT_Mile", "status_code": "TK_Complete"},
            {"task_id": 2, "task_name": "SC", "task_type": "TT_FinMile", "status_code": "TK_NotStart"},
        ]
        result = get_milestones(tasks, include_complete=True)
        self.assertEqual(len(result), 2)


class TestMilestoneAmbiguousError(unittest.TestCase):
    def test_carries_candidate_list(self):
        candidates = [{"task_id": 1, "task_name": "A"}, {"task_id": 2, "task_name": "B"}]
        err = MilestoneAmbiguousError("ambiguous", candidates=candidates)
        self.assertEqual(err.candidates, candidates)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test, verify it fails**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_milestones -v
```

Expected: ImportError on `milestones` module.

- [ ] **Step 3: Implement `milestones.py`**

```python
"""Milestone enumeration — replaces the brittle find_sc_milestone heuristic.

Callers pass `tasks` (the parsed XER task list). This module returns the
candidate milestones; the caller picks which one is meaningful for their
purpose, OR raises MilestoneAmbiguousError carrying the candidate list."""

EXCLUDE_TYPES = {"TT_WBS", "TT_LOE"}
MILESTONE_TYPES = {"TT_Mile", "TT_FinMile"}


class MilestoneAmbiguousError(Exception):
    """Raised when a function expecting one milestone gets multiple candidates.
    The `candidates` attribute carries the structured list for the caller (or MCP)
    to surface."""
    def __init__(self, message: str, candidates: list):
        super().__init__(message)
        self.candidates = candidates


def get_milestones(tasks: list, include_complete: bool = False) -> list:
    """Return all non-WBS, non-LOE milestone tasks.

    Each result entry includes: task_id, task_name, task_type, calendar_id,
    early_finish, late_finish, status_code, predecessor_count, is_terminal.

    Skips TK_Complete by default; pass include_complete=True to include them."""
    result = []
    for t in tasks:
        if t.get("task_type") in EXCLUDE_TYPES:
            continue
        if t.get("task_type") not in MILESTONE_TYPES:
            continue
        if not include_complete and t.get("status_code") == "TK_Complete":
            continue
        result.append({
            "task_id": t.get("task_id"),
            "task_name": t.get("task_name"),
            "task_type": t.get("task_type"),
            "calendar_id": t.get("clndr_id"),
            "early_finish": t.get("early_end_date"),
            "late_finish": t.get("late_end_date"),
            "status_code": t.get("status_code"),
            # predecessor_count and is_terminal are computed by the MCP tool layer
            # (they need the preds list); this helper deliberately keeps the
            # caller-side concern out of the lib.
        })
    return result
```

- [ ] **Step 4: Run test, verify it passes**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_milestones -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/milestones.py scheduling/skills/schedule-toolbox/tests/
git commit -m "feat(scheduling): get_milestones() helper replaces find_sc_milestone"
```

### Task D2: Remove `find_sc_milestone` from `score_schedule.py`

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/score_schedule.py`

- [ ] **Step 1: Find every call site for `find_sc_milestone`**

```bash
# Use Grep tool:
# pattern: "find_sc_milestone"
# path: scheduling/
```

Build a list. Expected at least: `score_schedule.py` (where it's defined), possibly `path_analysis.py`, possibly `update_review.py`.

- [ ] **Step 2: Update `score_schedule.py` to accept explicit `milestone_id`**

The current `compute_quality_score(tasks, preds, data_date)` signature needs an optional `milestone_id` parameter:

```python
def compute_quality_score(tasks, preds, data_date, milestone_id=None):
    """Score the schedule. If milestone_id is omitted, uses the unique
    non-WBS, non-LOE terminal milestone; raises MilestoneAmbiguousError
    if multiple candidates exist."""
    from .milestones import get_milestones, MilestoneAmbiguousError
    
    if milestone_id is None:
        candidates = get_milestones(tasks, include_complete=False)
        # Terminal = no non-WBS/LOE successors
        # ... (implementation detail; the helper returns metadata that
        # makes this filter easy, computed alongside predecessor_count)
        terminal = [m for m in candidates if is_terminal_milestone(m, preds, tasks)]
        if len(terminal) != 1:
            raise MilestoneAmbiguousError(
                f"{len(terminal)} terminal milestones — pass milestone_id explicitly",
                candidates=candidates,
            )
        milestone_id = terminal[0]["task_id"]
    # ... rest of scoring logic unchanged, except wherever find_sc_milestone
    # was called, substitute the explicit milestone_id.
```

Replace every internal call to `find_sc_milestone(tasks)` with the explicit `milestone_id`. Delete the `find_sc_milestone` function definition.

- [ ] **Step 3: Add tests for the new milestone_id parameter**

In `scheduling/skills/schedule-toolbox/tests/test_score_schedule.py` (create if it doesn't exist), add a test that calls `compute_quality_score(tasks, preds, data_date, milestone_id=1002)` against the fixture XER and asserts the result is computed against the SC milestone explicitly.

Add a second test that calls without `milestone_id` against an XER with multiple terminal milestones and asserts `MilestoneAmbiguousError` is raised with both candidates.

- [ ] **Step 4: Run tests**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_score_schedule -v
```

Expected: pass. Also re-run the full proposal-schedule and schedule-update test suites to confirm no regressions where they called `compute_quality_score` without `milestone_id` and relied on the old name-based detection.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "fix(scheduling): score_schedule accepts explicit milestone_id, removes find_sc_milestone heuristic"
```

### Task D3: Same surgery for `path_analysis.py`'s SC-coverage

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/path_analysis.py`

- [ ] **Step 1: Locate the SC-coverage computation**

Read `path_analysis.py` and identify the function(s) that detect the SC milestone for coverage analysis. Likely a `compute_sc_coverage` or similar.

- [ ] **Step 2: Update signature to accept `milestone_id`**

Add `milestone_id` parameter. When omitted, use the same enumerate-or-raise pattern as score_schedule.

- [ ] **Step 3: Update tests, run, verify**

Add a test that explicitly passes `milestone_id` and confirms the coverage % matches the expected value for the fixture.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "fix(scheduling): path_analysis accepts explicit milestone_id"
```

### Task D4: Audit for stragglers

- [ ] **Step 1: Grep for any remaining heuristic**

```bash
# Grep tool:
# pattern: "Substantial Completion|find_sc_milestone|find_sc"
# path: scheduling/
```

- [ ] **Step 2: Triage each hit**

For each hit, decide: legitimate string (e.g. a column header in an output report) or a fallback heuristic to remove. Remove fallbacks; leave legitimate references alone but note them in the commit message.

- [ ] **Step 3: Commit any cleanups**

```bash
git add -u
git commit -m "chore(scheduling): audit + cleanup remaining SC-name heuristics"
```

---

## Phase E: First real tool — `get_milestones`

Goal: prove the wrapping pattern end-to-end with the simplest tool. Sets the template that the other 32 tools follow.

### Task E1: Implement `get_milestones` MCP tool

**Files:**
- Create: `scheduling/mcp-server/tools/structure.py`
- Modify: `scheduling/mcp-server/server.py`
- Create: `scheduling/mcp-server/tests/test_structure.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from pathlib import Path
from scheduling.mcp_server.cache import CpmCache
from scheduling.mcp_server.tools import structure

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestGetMilestonesTool(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_milestone_list(self):
        result = structure.get_milestones_impl(str(FIXTURE), include_complete=False, cache=self.cache)
        self.assertIn("milestones", result)
        self.assertEqual(len(result["milestones"]), 2)

    def test_each_milestone_has_required_fields(self):
        result = structure.get_milestones_impl(str(FIXTURE), include_complete=False, cache=self.cache)
        for m in result["milestones"]:
            self.assertIn("task_id", m)
            self.assertIn("task_name", m)
            self.assertIn("task_type", m)
            self.assertIn("predecessor_count", m)
            self.assertIn("is_terminal", m)

    def test_sc_milestone_is_terminal(self):
        result = structure.get_milestones_impl(str(FIXTURE), include_complete=False, cache=self.cache)
        sc = next(m for m in result["milestones"] if m["task_name"] == "Substantial Completion")
        self.assertTrue(sc["is_terminal"])

    def test_xer_not_found_returns_error(self):
        with self.assertRaises(FileNotFoundError):
            structure.get_milestones_impl("/nonexistent.xer", include_complete=False, cache=self.cache)
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python -m unittest scheduling.mcp_server.tests.test_structure -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `structure.py`**

```python
"""Schedule structure tools: get_milestones."""
from typing import Optional
import sys
from pathlib import Path

LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
sys.path.insert(0, str(LIB))

from milestones import get_milestones as _get_milestones_helper  # type: ignore


def get_milestones_impl(xer_path: str, include_complete: bool, cache) -> dict:
    """Implementation — called by both the test and the MCP tool wrapper."""
    parsed = cache.get_parsed(xer_path)
    milestones = _get_milestones_helper(parsed["tasks"], include_complete=include_complete)
    # Compute predecessor_count and is_terminal (the MCP-layer enrichments)
    pred_by_succ: dict = {}
    succ_by_pred: dict = {}
    for p in parsed["preds"]:
        pred_by_succ.setdefault(p["task_id"], []).append(p["pred_task_id"])
        succ_by_pred.setdefault(p["pred_task_id"], []).append(p["task_id"])
    for m in milestones:
        m["predecessor_count"] = len(pred_by_succ.get(m["task_id"], []))
        # Terminal: no non-WBS/LOE successor
        successors = succ_by_pred.get(m["task_id"], [])
        task_by_id = {t["task_id"]: t for t in parsed["tasks"]}
        m["is_terminal"] = all(
            task_by_id.get(s, {}).get("task_type") in {"TT_WBS", "TT_LOE"}
            for s in successors
        )
    return {"milestones": milestones}


def register(mcp, cache):
    """Register this module's tools on the MCP server."""

    @mcp.tool()
    def get_milestones(xer_path: str, include_complete: bool = False) -> dict:
        """List all non-WBS, non-LOE milestones in the XER.
        
        Args:
            xer_path: Path to the .xer file.
            include_complete: If True, include milestones already marked complete.
        
        Returns:
            { milestones: [{ task_id, task_name, task_type, calendar_id,
                             early_finish, late_finish, status_code,
                             predecessor_count, is_terminal }, ...] }
        """
        return get_milestones_impl(xer_path, include_complete, cache)
```

- [ ] **Step 4: Update `server.py` to call `structure.register(...)`**

```python
"""Westland Scheduler Local MCP server entry point."""
from mcp.server import FastMCP
from .cache import CpmCache
from .tools import structure

mcp = FastMCP("westland-scheduler-mcp")
_cache = CpmCache()

# Health-check tool
@mcp.tool()
def ping() -> dict:
    return {"ok": True}

# Register all tool modules
structure.register(mcp, _cache)

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 5: Run tests, verify they pass**

```bash
python -m unittest scheduling.mcp_server.tests.test_structure -v
python -m unittest scheduling.mcp_server.tests.test_server -v
```

Expected: all pass.

- [ ] **Step 6: Manual smoke test in Claude Code**

Reload the plugin. In a fresh Claude Code session, run `ToolSearch select:get_milestones`. The tool schema should load. Then call:

```text
get_milestones(xer_path="C:/Users/camron/code/construction-skills/.claude/worktrees/reverent-wilbur-343c19/scheduling/mcp-server/tests/fixtures/minimal.xer")
```

Expected: returns 2 milestones (NTP + SC).

- [ ] **Step 7: Commit**

```bash
git add -u
git commit -m "feat(scheduling): get_milestones MCP tool"
```

---

## Phase F: Implement the remaining 32 Tier 0 tools

Goal: each tool is a 5-20 line adapter that imports an existing function from `lib/`, calls it via the cache, marshals the result. Same TDD pattern as Task E1.

**Pattern for every tool in Phase F:**

1. Write failing test in the appropriate `tests/test_<category>.py`.
2. Run, verify ImportError or AssertionError.
3. Implement the tool in the appropriate `tools/<category>.py`.
4. Update the category's `register()` function in `tools/<category>.py`.
5. Update `server.py` to call the new category's `register()` (one-time per category).
6. Run tests, verify pass.
7. Commit.

The task list below names each tool and the underlying function it wraps. The engineer references the spec at `docs/superpowers/specs/2026-05-24-schedule-toolbox-mcp-design.md` for exact input/output shapes.

### Task F1: CPM and path tools (10 tools, batched)

**Files:**
- Create: `scheduling/mcp-server/tools/cpm_path.py`
- Modify: `scheduling/mcp-server/server.py` (one new `register` call)
- Create: `scheduling/mcp-server/tests/test_cpm_path.py`

For each of the 10 tools, follow the F-pattern. Tools and their `lib/` function maps:

| MCP tool | `lib/` function | Notes |
|----------|-----------------|-------|
| `run_cpm` | `cpm_engine.run` + write XER | Writes new XER to `<input>-cpm.xer`. Atomic. Never overwrite. |
| `get_critical_path` | `cpm_engine.critical_path` | Accepts `milestone_id?`. |
| `get_near_critical_chains` | `cpm_engine.near_critical_chains` | `tolerance_days?` default 5. |
| `get_driving_paths` | `cpm_engine.driving_paths_for` | Takes `activity_id`. |
| `get_parallel_branches` | `cpm_engine.parallel_branches_in_window` | Takes `start_date`, `end_date`. |
| `get_anchor_conflicts` | `cpm_engine.check_anchor_dates` | Accepts `anchors` inline OR `anchors_path`. `tolerance_days?` default 0. |
| `get_anchor_absorption_suggestions` | `cpm_engine.suggest_anchor_absorption` | Takes `slip` + `max_suggestions?` default 8. |
| `get_milestone_path_coverage` | `path_analysis.compute_milestone_coverage` | Accepts `milestone_id?`; ambiguity error if omitted and multiple terminal. |
| `get_delay_impacts` | `path_analysis.compute_delay_impacts` | Accepts `milestone_id?`. |
| `get_gantt_json` | `cpm_engine.gantt_json` | Returns structured chart data. |
| `render_gantt_html` | `cpm_engine.render_gantt_html` | Writes HTML to a file; returns path. |

Each tool's task is 6 steps (test, run-fail, implement, register, run-pass, commit). The engineer writes 10 small tasks here; each is structurally identical to Task E1.

- [ ] **Step 1-66: One TDD cycle per tool.** Test against the fixture XER. Implement against the spec's documented input/output shapes. Commit per tool — 10 commits.

**Commit message template:**

```
feat(scheduling): <tool_name> MCP tool wraps <underlying function>
```

After all 10 are done, run the full `test_cpm_path.py` and the `ToolSearch select:<tool_name>` smoke test for at least 3 of them (`get_critical_path`, `get_anchor_conflicts`, `run_cpm`).

### Task F2: Quality and scoring tools (10 tools)

**Files:**
- Create: `scheduling/mcp-server/tools/quality.py`
- Modify: `scheduling/mcp-server/server.py`
- Create: `scheduling/mcp-server/tests/test_quality.py`

Tool map:

| MCP tool | `lib/` function |
|----------|-----------------|
| `get_quality_check` | `quality_checks.run_check(check_name, tasks, preds)` — accepts enum of 28 check names |
| `get_relationship_type_breakdown` | `quality_checks.relationship_type_breakdown` |
| `get_missing_logic` | `quality_checks.missing_logic_check` |
| `get_high_float_activities` | `quality_checks.high_float_check` — `threshold_days?` default 44 |
| `get_negative_float_activities` | `quality_checks.negative_float_check` |
| `get_constraint_violations` | `quality_checks.constraint_check` |
| `get_high_duration_activities` | `quality_checks.high_duration_check` — `threshold_days?` default 44 |
| `get_duplicate_relationships` | `quality_checks.duplicate_relationships_check` |
| `get_circular_relationships` | `quality_checks.circular_logic_check` |
| `get_invalid_dates` | `quality_checks.invalid_dates_check` |

- [ ] **Step 1-66: TDD cycle per tool — 10 commits.**

### Task F3: Update review tools (4 tools)

**Files:**
- Create: `scheduling/mcp-server/tools/update_review.py`
- Modify: `scheduling/mcp-server/server.py`
- Create: `scheduling/mcp-server/tests/test_update_review.py`

| MCP tool | `lib/` function |
|----------|-----------------|
| `get_activities_to_start` | `update_review.activities_to_start(parsed, by_date, resource_filter?, trade_filter?)` |
| `get_activities_to_finish` | `update_review.activities_to_finish(parsed, by_date)` |
| `get_in_progress_activities` | `update_review.in_progress_activities(parsed)` |
| `get_ride_data_date_violations` | `update_review.ride_data_date_check(parsed, data_date?)` |

- [ ] **Step 1-24: TDD cycle per tool — 4 commits.**

### Task F4: Compare tools (4 tools)

**Files:**
- Create: `scheduling/mcp-server/tools/compare.py`
- Modify: `scheduling/mcp-server/server.py`
- Create: `scheduling/mcp-server/tests/test_compare.py`

| MCP tool | `lib/` function |
|----------|-----------------|
| `compare_activity_changes` | `xer_compare.activity_changes(baseline, current)` |
| `compare_date_slips` | `xer_compare.date_slips(baseline, current)` |
| `compare_milestone_slip` | `xer_compare.milestone_slip(baseline, current, milestone_id?)` |
| `compare_missed_dates` | `xer_compare.missed_dates(baseline, current)` |

- [ ] **Step 1-24: TDD cycle per tool — 4 commits.**

For `compare_milestone_slip` tests, build a second fixture XER (`tests/fixtures/minimal_v2.xer`) by copying `minimal.xer` and pushing the SC milestone date forward by 14 days. Compare returns `{ days_change: 14 }`.

### Task F5: Omnibus tools (3 tools)

**Files:**
- Create: `scheduling/mcp-server/tools/omnibus.py`
- Modify: `scheduling/mcp-server/server.py`
- Create: `scheduling/mcp-server/tests/test_omnibus.py`

| MCP tool | Composition |
|----------|-------------|
| `score_schedule` | `score_schedule.compute_quality_score` + `score_schedule.generate_quality_report` → return full {score, grade, scored, info, deductions, scope, details}. Accepts `milestone_id?`. |
| `weekly_update_review` | Composition of: `compare_activity_changes` + `compare_milestone_slip` + `get_activities_to_start` + `get_activities_to_finish` + DCMA-delta (computed inline). Used by `schedule-update` report phase. NOTE: Tier 1 tools (`get_critical_path_changes`, `get_gain_loss_attribution`) ship in Plan 2; this omnibus tool's output gets extended at that point. For Plan 1, stub those subkeys with `null` and a `pending_plan_2: true` flag. |
| `proposal_schedule_health` | Composition: `score_schedule` + `get_missing_logic` + `get_high_float_activities` + `get_anchor_conflicts`. |

- [ ] **Step 1-18: TDD cycle per tool — 3 commits.**

---

## Phase G: PreToolUse hook for `lib/*.py`

Goal: block `Read`/`Edit`/`Write`/`Glob`/`Grep` against `lib/*.py` files when the active skill isn't `schedule-toolbox` itself.

### Task G1: Locate the existing Westland PreToolUse hooks

**Files:**
- *(investigate first, then modify)*

- [ ] **Step 1: Find the existing hook config**

```bash
# Grep tool:
# pattern: "PreToolUse"
# path: ~/.claude/ AND scheduling/ AND .claude/
# (Westland's existing hook blocks .xer overwrites per scheduling/CLAUDE.md)
```

Identify which file holds the hook config. Typical locations:
- `~/.claude/settings.json`
- `.claude/settings.json` at repo root
- `.claude/settings.local.json`

Read the existing config to understand the hook shape.

- [ ] **Step 2: Add a new hook rule**

Extend the PreToolUse hook config with a rule that:
- Matches tools: `Read`, `Edit`, `Write`, `Glob`, `Grep`, `MultiEdit`
- Matches paths: `**/schedule-toolbox/lib/**/*.py`
- Exits with code 2 (block) unless the active skill is `schedule-toolbox` (intentional improvement work) — detect via context

If the hook system doesn't natively support skill-based gating, the safer minimal rule is "block unconditionally; the curator does improvement work in a temporary worktree with the hook disabled." Document this fallback in the troubleshoot skill.

- [ ] **Step 3: Test the hook manually**

In a fresh Claude Code session (not the `schedule-toolbox` skill):

```text
# This should be blocked:
Read scheduling/skills/schedule-toolbox/lib/score_schedule.py
```

Expected: tool blocked with a clear message.

In a session where `schedule-toolbox` is the active skill, the same read should succeed.

- [ ] **Step 4: Commit the settings change**

If the hook is in repo (`.claude/settings.json`), commit it:

```bash
git add .claude/settings.json
git commit -m "feat(scheduling): PreToolUse hook blocks Read/Edit on schedule-toolbox/lib/*.py"
```

If it's in user-level `~/.claude/settings.json`, document the required entry in the troubleshoot skill instead.

---

## Phase H: SKILL.md and integration updates

### Task H1: Update `schedule-toolbox` SKILL.md

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/SKILL.md`

- [ ] **Step 1: Replace the routing table**

Read the current SKILL.md routing table. Replace each "where to look" row (referring to `references/*.md` files) with a "which tool to call" row referring to MCP tool names.

Example transformation:

Before:
```
| Score schedule / check quality | `references/quality-checks.md` |
```

After:
```
| Score schedule / check quality | Call `score_schedule` (omnibus) or `get_quality_check` for one specific check |
```

Reference docs (`*.md` files) stay in `references/` and are still useful for XER format / concept lookup — keep those routing entries but reframe them as "concept reference, not code to call."

- [ ] **Step 2: Remove the Cardinal Rule**

Delete the block:

```
## Cardinal Rule
Do not read Python source files for routine operations. Call the CLI → get JSON → use it. Fall back to source only if the result seems wrong.
```

The MCP seam makes this rule moot — the source isn't reachable.

- [ ] **Step 3: Add a header line documenting the seam**

Above the routing table, add:

```
> This skill's analysis logic is exposed via the Westland Scheduler Local MCP — call tools by name (e.g. `score_schedule`, `get_critical_path`). The Python source lives in `lib/` and is intentionally fenced off; do not read it.
```

- [ ] **Step 4: Commit**

```bash
git add scheduling/skills/schedule-toolbox/SKILL.md
git commit -m "docs(scheduling): SKILL.md routing table -> MCP tool names"
```

### Task H2: Update `schedule-update/phases/report.md`

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/report.md`

- [ ] **Step 1: Find the step 3b xer_compare invocation**

```bash
# Grep tool:
# pattern: "xer_compare"
# path: scheduling/skills/schedule-update/phases/report.md
```

- [ ] **Step 2: Replace with MCP tool calls**

The current step 3b uses Glob to resolve the `xer_compare.py` path, then runs `python xer_compare.py baseline current`. Replace with the MCP equivalent — typically a sequence of three calls:

```text
1. ToolSearch select:compare_activity_changes,compare_milestone_slip,compare_date_slips
2. compare_activity_changes(baseline_path="...", current_path="...")
3. compare_milestone_slip(baseline_path="...", current_path="...", milestone_id="<resolved>")
4. compare_date_slips(baseline_path="...", current_path="...")
```

Document in the phase file that `milestone_id` must be resolved up front via `get_milestones` if there's ambiguity.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/report.md
git commit -m "docs(scheduling): schedule-update report phase uses MCP tools"
```

### Task H3: Update `schedule-update/phases/draft.md`

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/draft.md`

- [ ] **Step 1: Find and replace direct Python invocations**

Same pattern as H2. Search for `xer_compare`, `score_schedule`, any other direct Python calls. Replace with MCP tool calls.

- [ ] **Step 2: Commit**

```bash
git add scheduling/skills/schedule-update/phases/draft.md
git commit -m "docs(scheduling): schedule-update draft phase uses MCP tools"
```

---

## Phase I: `westland-scheduler-mcp-troubleshoot` skill

Goal: a skill that diagnoses MCP registration / setup problems. Diagnostic-only, not a setup walkthrough.

### Task I1: Skeleton skill structure

**Files:**
- Create: `scheduling/skills/westland-scheduler-mcp-troubleshoot/SKILL.md`
- Create: `scheduling/skills/westland-scheduler-mcp-troubleshoot/diagnose.py`

- [ ] **Step 1: Write SKILL.md frontmatter and overview**

```markdown
---
name: westland-scheduler-mcp-troubleshoot
description: >
  Diagnose Westland Scheduler Local MCP registration or setup issues. Use when the MCP tools (get_critical_path, score_schedule, etc.) aren't appearing in Claude Code's tool list, when an MCP tool call fails with a registration or import error, or when the user reports that the schedule toolbox "isn't working." Diagnostic-only — does not perform setup unless explicitly asked.
---

# Westland Scheduler MCP — Troubleshoot

If the Westland Scheduler Local MCP is registered and working, no one runs this skill. It exists for when something is wrong.

## What it checks

1. Is the `mcp` Python SDK installed?
2. Is the scheduling plugin's manifest declaring the server correctly?
3. Can Claude Code discover the server's tools (smoke test via `ToolSearch select:ping`)?
4. Can the server actually parse a known-good XER (smoke test via `ping` then `get_milestones` against the fixture)?

## What it does

Runs `diagnose.py` and reports findings. Each failed check has a copy-pasteable fix command.

## Manual registration fallback

If the plugin manifest's `mcpServers` declaration isn't being honored (Claude Code version skew, manifest parse error), the skill walks the user through writing the registration to `~/.claude/settings.json` manually.
```

- [ ] **Step 2: Write `diagnose.py`**

Implement the checks listed above. Each check returns `{ name, status: "pass"|"fail", message, fix_command? }`. Print as a table.

- [ ] **Step 3: Register the skill in the scheduling plugin manifest**

Edit `scheduling/.claude-plugin/plugin.json` to add `westland-scheduler-mcp-troubleshoot` to the skills list.

- [ ] **Step 4: Commit**

```bash
git add scheduling/skills/westland-scheduler-mcp-troubleshoot/ scheduling/.claude-plugin/plugin.json
git commit -m "feat(scheduling): westland-scheduler-mcp-troubleshoot skill"
```

---

## Phase J: Release

### Task J1: Bump plugin version

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json` (version field)
- Modify: `.claude-plugin/marketplace.json` (matching scheduling entry)

- [ ] **Step 1: Set both versions to `7.0.0`**

This is a major bump because the SKILL.md routing table changes and the `references/` → `lib/` rename are breaking for any external caller that imports `references.*` directly. Internal callers were already updated in Task C2.

- [ ] **Step 2: Verify the lockstep check passes**

Run the pre-commit hook against a staging commit to confirm both files agree:

```bash
bash .githooks/test_pre_commit.sh
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore(scheduling): release 7.0.0 (Westland Scheduler Local MCP foundation)"
```

### Task J2: Merge to main

- [ ] **Step 1: Push the branch**

```bash
git push -u origin claude/reverent-wilbur-343c19
```

- [ ] **Step 2: Open the PR**

Use `gh pr create` with a title under 70 chars and a summary that links the spec and notes the 3-plan sequence (foundation, analytics, modification). Mark this as Plan 1.

- [ ] **Step 3: Merge after review**

Squash or merge per repo convention. Do not push directly to main.

### Task J3: Build and distribute

- [ ] **Step 1: Switch to main checkout, pull**

```bash
# From C:\Users\camron\code\construction-skills (the main repo, NOT a worktree):
git switch main
git pull --ff-only
```

- [ ] **Step 2: Build**

```bash
python build.py scheduling
```

- [ ] **Step 3: Verify zip artifact**

```bash
ls -la src/scheduling.zip
```

Confirm the zip contains `mcp-server/`, the new `lib/` directory, the troubleshoot skill.

- [ ] **Step 4: Distribute**

Upload `src/scheduling.zip` to the enterprise plugin distribution per the repo's existing process. Notify the 4 schedulers on the team: each runs `pip install mcp` once, then `/plugin update scheduling`.

### Task J4: Smoke test on a real project

- [ ] **Step 1: Pick a project**

Wellington Temple or W1177 — both have recent XERs and known-good state.

- [ ] **Step 2: Run a few MCP tools against a real XER**

In Claude Code, in a fresh session:

```text
ToolSearch select:get_milestones,get_critical_path,score_schedule

get_milestones(xer_path="<path to real project XER>")
# Pick the meaningful milestone from the returned list

get_critical_path(xer_path="<path>", milestone_id="<chosen>")
score_schedule(xer_path="<path>", milestone_id="<chosen>")
```

- [ ] **Step 3: Verify behavior**

- The MCP tools should return results that match what the underlying Python scripts produced previously (within the cleanup of the milestone auto-detect bug, which may produce *different* — and correct — scores for projects where the heuristic was picking the wrong milestone).
- A `Read` against `scheduling/skills/schedule-toolbox/lib/score_schedule.py` should be blocked by the PreToolUse hook (if not in the `schedule-toolbox` skill context).
- The `weekly_update_review` omnibus tool should return a structured result with the Plan-2 fields stubbed as `null` and `pending_plan_2: true` flagged.

- [ ] **Step 4: Document any surprises in `MEMORY.md`**

If the smoke test surfaces a behavior gap, add a feedback or project memory entry per the auto-memory rules. Do not silently fix — let the lessons-learned cycle pick it up for Plan 2 or a follow-up.

---

## Self-review

Checking the plan against the spec:

**1. Spec coverage:**
- § Problem, Goal, Non-goals — addressed by Plan 1's scope statement ✓
- § Architecture (local MCP, scripts importable, lessons-learned preserved) — Phase A + Phase C ✓
- § Tool catalog (33 base-catalog tools) — Phase E + Phase F ✓
- § Milestone scoping — Phase D ✓
- § CPM result caching — Phase B ✓
- § XER input/output handling — applied in every tool task; the `run_cpm` write-to-sibling-path pattern is documented in F1
- § Source hiding (rename, hook) — Phases C + G ✓
- § Distribution — Phase A3 (manifest registration) + Phase I (troubleshoot skill) ✓
- § Integration with existing skills — Phase H ✓
- § Risks and mitigations — addressed via test fixtures and the smoke-test in J4
- § Implementation order — followed (lib rename before tools to keep import path stable)
- **Deferred to Plan 2:** Tier 1 update analytics tools, Tier 2 delay-analysis tools. `weekly_update_review` omnibus output stubs Plan-2 fields.
- **Deferred to Plan 3:** Tier 3 modification tools, skeleton extraction, compositional generation.

**2. Placeholder scan:**
- Phase F tasks summarize the TDD cycle as "Step 1-N: TDD cycle per tool" with a tool/function map table. This is intentional batching — each individual tool's TDD cycle is structurally identical to Task E1, fully shown. The engineer references E1 for the pattern and the spec for input/output shapes. Not a placeholder violation per the skill's "Similar to Task N" rule — the *pattern* is fully shown in E1, and the per-tool variance is captured in the function map. If executed via subagent-driven-development, each tool can be its own subagent dispatch.

**3. Type consistency:**
- `CpmCache` used in E1 matches B1 ✓
- `MilestoneAmbiguousError` from D1 surfaces in the MCP error standardization (open question 3 in the spec; this plan doesn't lock the wire format — that's a Plan 2 follow-up)
- `get_milestones` helper signature in D1 matches E1's usage ✓
- The `lib/` import path used in E1 (`scheduling/skills/schedule-toolbox/lib/`) matches C1's rename target ✓

**4. Ambiguity flag:**
- Task A3's `${PLUGIN_DIR}` substitution syntax is verified-against-docs-at-implementation-time. If unsupported, fall back is documented.
- Task G1's PreToolUse hook may or may not support skill-based gating depending on the Claude Code version. Fallback is "block unconditionally; improvement work happens in a temporary worktree with hook disabled."
- The `mcp` Python SDK API (`FastMCP` vs alternatives) — A2 assumes `FastMCP` from `mcp.server`. Verify at implementation time; if API differs, A2's `server.py` template adjusts but the structure (one decorator per tool, registered via module `register(mcp, cache)` functions) is stable.

---

**Plan complete and saved to** [`docs/superpowers/plans/2026-05-24-westland-scheduler-mcp-plan-1-foundation.md`](2026-05-24-westland-scheduler-mcp-plan-1-foundation.md)**. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Works well for this plan because most tasks are independent (per-tool TDD cycles in Phase F especially).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
