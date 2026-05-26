"""CPM and path-analysis MCP tools (F1 batch).

Thin adapters around ``schedule-toolbox/lib/cpm_engine.py`` and
``schedule-toolbox/lib/path_analysis.py``. Each tool function pulls already-
parsed (and where helpful, already-CPM'd) data from the ``CpmCache`` and
returns a structured dict that the MCP serialization layer hands back to the
caller as JSON.

The four path-extraction tools (``get_critical_path``,
``get_near_critical_chains``, ``get_driving_paths``, ``get_parallel_branches``)
all read from a single call to :func:`extract_paths` -- they just project
different keys out of the same result. Re-running ``extract_paths`` per call
keeps the cache key flat (no per-milestone variants) and is cheap relative to
the CPM forward/backward passes that are cached.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so we can import the analysis modules without
# packaging them. Mirrors cache.py and structure.py.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cpm_engine import extract_paths  # noqa: E402
from cpm_engine import _path_task_summary  # noqa: E402
from path_analysis import trace_driving_path  # noqa: E402


def _resolve_metadata_for_milestone(
    metadata: dict, milestone_id, tasks: list
) -> dict:
    """Return a metadata dict with ``sc_milestone_*`` fields set to the
    explicit ``milestone_id``. When ``milestone_id`` is None the original
    metadata is returned unchanged (no copy) so the common case is free.

    The CPM math already ran with the cache's default milestone resolution;
    only the post-processing path extraction needs to know which milestone
    counts as "the end" for SC-anchored chains. Updating metadata in place
    would corrupt the cache entry, hence the shallow copy.
    """
    if milestone_id is None:
        return metadata
    new_meta = dict(metadata)
    new_meta["sc_milestone_id"] = milestone_id
    # Best-effort lookup of name + code + date so the metadata dict matches
    # what schedule_forward_backward would have produced if given milestone_id
    # directly. Missing fields default to empty string (extract_paths only
    # uses sc_milestone_id, but other future consumers may read the name).
    for t in tasks:
        if t.get("task_id") == milestone_id:
            new_meta["sc_milestone_name"] = t.get("task_name", "")
            new_meta["sc_milestone_code"] = t.get("task_code", "")
            new_meta["sc_milestone_date"] = t.get("early_end_date", "")
            break
    return new_meta


# Upper bound on tolerance_days for near-critical-chains. ``extract_paths``
# itself uses a hard-coded 40-hour cap (= 5 working days at 8 hrs/day) when
# collecting near-critical tasks; any tolerance request greater than this is
# silently clamped because the underlying chains weren't computed.
_NEAR_CRITICAL_MAX_DAYS = 5


def get_critical_path_impl(
    xer_path: str, milestone_id: Optional[str], cache
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Returns ``{"critical_path": [task_summary, ...]}`` where each
    ``task_summary`` comes straight from ``extract_paths`` -- a dict of
    ``task_id``, ``task_code``, ``task_name``, ``total_float_hr_cnt``,
    ``early_start_date``, ``early_end_date``, etc.
    """
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)
    metadata = _resolve_metadata_for_milestone(
        metadata, milestone_id, parsed.get("TASK", [])
    )
    paths = extract_paths(results, metadata, parsed.get("TASKPRED", []))
    return {"critical_path": paths.get("critical_path", [])}


def get_driving_paths_impl(
    xer_path: str, activity_id: Optional[str], cache
) -> dict:
    """Driving paths through the schedule.

    Without ``activity_id``: returns every driving path that
    :func:`extract_paths` walks back from key end-states (SC milestone,
    project_end, FNLT-constrained tasks). Useful for "what's driving the
    finish?" discovery.

    With ``activity_id``: traces forward from that activity along the least-
    float successor at each step, stopping at the SC milestone or whenever
    there are no successors. Returned in the same single-element list shape
    so callers don't have to special-case the two modes.
    """
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)

    if activity_id is None:
        paths = extract_paths(results, metadata, parsed.get("TASKPRED", []))
        return {"driving_paths": paths.get("driving_paths", [])}

    # Forward trace from a specific activity. trace_driving_path returns a
    # list of task_ids; wrap to match the extract_paths shape so consumers
    # have a single result schema.
    tasks_by_id = {t.get("task_id"): t for t in results}
    if activity_id not in tasks_by_id:
        return {"driving_paths": []}

    # Build a minimal succ_map for trace_driving_path. The function rebuilds
    # its own succ lookup from preds anyway, so an empty defaultdict works;
    # we pass {} and let it own that detail.
    chain_ids = trace_driving_path(
        activity_id,
        tasks_by_id,
        {},
        parsed.get("TASKPRED", []),
        sc_task_id=metadata.get("sc_milestone_id"),
    )
    if not chain_ids:
        return {"driving_paths": []}

    end_id = chain_ids[-1]
    end_task = tasks_by_id.get(end_id, {})
    return {
        "driving_paths": [
            {
                "to": "forward-from-activity",
                "end_task_id": end_id,
                "end_task_code": end_task.get("task_code", "") or end_id,
                "end_task_name": end_task.get("task_name", ""),
                "chain": [
                    _path_task_summary(tasks_by_id[tid], tid)
                    for tid in chain_ids if tid in tasks_by_id
                ],
            }
        ]
    }


def get_parallel_branches_impl(
    xer_path: str,
    start_date: Optional[str],
    end_date: Optional[str],
    cache,
) -> dict:
    """Diverge-then-converge subgraphs ranked by criticality.

    Optional date window filters branches whose ``diverge_at`` task starts
    within ``[start_date, end_date]`` (inclusive, ISO ``YYYY-MM-DD``). When
    either bound is None it's treated as unbounded on that side.
    """
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)
    paths = extract_paths(results, metadata, parsed.get("TASKPRED", []))
    branches = paths.get("parallel_branches", [])

    if start_date is None and end_date is None:
        return {"parallel_branches": branches}

    def _in_window(branch: dict) -> bool:
        es = (branch.get("diverge_at") or {}).get("early_start", "")
        if not es:
            return False
        # early_start is YYYY-MM-DD (string compare works).
        if start_date and es < start_date:
            return False
        if end_date and es > end_date:
            return False
        return True

    return {"parallel_branches": [b for b in branches if _in_window(b)]}


def get_near_critical_chains_impl(
    xer_path: str, tolerance_days: float, cache
) -> dict:
    """Return chains of tasks with 0 < TF <= ``tolerance_days``.

    The underlying :func:`extract_paths` produces chains capped at 5 working
    days of float; values greater than 5 are silently clamped. Values <= 5
    filter the returned chains down to those whose minimum-float member is
    within the requested tolerance.
    """
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)
    paths = extract_paths(results, metadata, parsed.get("TASKPRED", []))
    chains = paths.get("near_critical", [])
    effective_tol = min(tolerance_days, _NEAR_CRITICAL_MAX_DAYS)
    chains = [c for c in chains if c.get("float_days", 999) <= effective_tol]
    return {"near_critical": chains}


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def get_critical_path(
        xer_path: str, milestone_id: Optional[str] = None
    ) -> dict:
        """Return the longest contiguous TF<=0 chain ending at the project's
        terminal milestone (or at ``milestone_id`` if provided).

        Args:
            xer_path: Path to the .xer file.
            milestone_id: Optional task_id of the terminal milestone to walk
                back from. Omit on single-terminal schedules to auto-resolve.

        Returns:
            ``{ critical_path: [{task_id, task_code, task_name,
            total_float_hr_cnt, early_start_date, early_end_date, ...}, ...] }``.
            Empty list if no TF<=0 chain exists.
        """
        return get_critical_path_impl(xer_path, milestone_id, cache)

    @mcp.tool()
    def get_driving_paths(
        xer_path: str, activity_id: Optional[str] = None
    ) -> dict:
        """Driving paths through the schedule.

        Args:
            xer_path: Path to the .xer file.
            activity_id: Optional task_id. When omitted, returns every
                driving path walked backward from key end-states (SC,
                project_end, FNLT). When provided, returns a single chain
                walked forward from that activity along the least-float
                successor at each step.

        Returns:
            ``{ driving_paths: [{to, end_task_id, end_task_code,
            end_task_name, chain: [task_summary, ...]}, ...] }``.
        """
        return get_driving_paths_impl(xer_path, activity_id, cache)

    @mcp.tool()
    def get_parallel_branches(
        xer_path: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Diverge-then-converge subgraphs through the schedule, ranked by
        the minimum total float across both branches.

        Args:
            xer_path: Path to the .xer file.
            start_date: Optional ISO ``YYYY-MM-DD`` lower bound on
                ``diverge_at.early_start``.
            end_date: Optional ISO ``YYYY-MM-DD`` upper bound.

        Returns:
            ``{ parallel_branches: [{diverge_at, converge_at, min_float_days,
            branches: [[summary, ...], [summary, ...]]}, ...] }`` sorted by
            ``min_float_days`` ascending.
        """
        return get_parallel_branches_impl(
            xer_path, start_date, end_date, cache
        )

    @mcp.tool()
    def get_near_critical_chains(
        xer_path: str, tolerance_days: float = 5
    ) -> dict:
        """Return chains of activities whose total float is positive but
        within ``tolerance_days`` of zero.

        Args:
            xer_path: Path to the .xer file.
            tolerance_days: Max chain float in working days. Defaults to 5;
                values greater than 5 are silently clamped to 5 because the
                underlying engine doesn't collect tasks with TF >= 5 days as
                near-critical.

        Returns:
            ``{ near_critical: [{float_days, length, chain: [task_summary,
            ...]}, ...] }``. Chains sorted ascending by float_days.
        """
        return get_near_critical_chains_impl(xer_path, tolerance_days, cache)
