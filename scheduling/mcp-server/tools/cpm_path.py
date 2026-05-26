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

import json

from cpm_engine import (  # noqa: E402
    build_activities_json,
    check_anchor_dates,
    extract_paths,
    render_schedule_html,
    schedule_forward_backward,
    suggest_anchor_absorption,
)
from cpm_engine import _path_task_summary  # noqa: E402
from path_analysis import (  # noqa: E402
    analyze_sc_path_coverage,
    compute_delay_impacts,
    trace_driving_path,
)

# scheduling/tools/_xer_io.py owns the XER round-tripper that the
# proposal-iterate CLI uses. Reusing it here keeps the write-back logic
# (line endings, encoding, table preservation) in one place. A future
# Plan 2 refactor should move _xer_io into lib/ alongside cpm_engine so
# the MCP doesn't have to reach into tools/.
_TOOLS_DIR = Path(__file__).parent.parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from _xer_io import parse_xer as _xer_io_parse  # noqa: E402
from _xer_io import write_xer_with_updates  # noqa: E402

from tools._common import (  # noqa: E402
    resolve_metadata_for_milestone as _resolve_metadata_for_milestone,
)

# Fields ``schedule_forward_backward`` writes back into each task dict.
# Only these need to be propagated to the output XER; everything else stays
# byte-identical via write_xer_with_updates' pass-through.
_CPM_FIELDS = (
    "early_start_date",
    "early_end_date",
    "late_start_date",
    "late_end_date",
    "total_float_hr_cnt",
    "free_float_hr_cnt",
    "driving_path_flag",
)


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


def get_anchor_conflicts_impl(
    xer_path: str,
    anchors: Optional[list],
    anchors_path: Optional[str],
    tolerance_days: int,
    cache,
) -> dict:
    """Compare CPM-computed dates against bid-given anchors.

    Exactly one of ``anchors`` or ``anchors_path`` must be provided.
    ``anchors_path`` points at a JSON file with the canonical
    ``{"anchors": [...]}`` top-level shape (matches
    ``proposal-anchors.json``).
    """
    if anchors is None and anchors_path is None:
        raise ValueError(
            "get_anchor_conflicts requires either `anchors` (inline list) "
            "or `anchors_path` (JSON file path)."
        )
    if anchors is not None and anchors_path is not None:
        raise ValueError(
            "Pass exactly one of `anchors` or `anchors_path`, not both."
        )

    if anchors_path is not None:
        with open(anchors_path, encoding="utf-8") as f:
            doc = json.load(f)
        anchors = doc.get("anchors", []) if isinstance(doc, dict) else doc

    results, _metadata = cache.get_cpm(xer_path)
    slips = check_anchor_dates(results, anchors or [], tolerance_days=tolerance_days)
    return {"slips": slips}


def run_cpm_impl(
    xer_path: str, output_path: Optional[str], cache
) -> dict:
    """Run CPM forward+backward and emit the result as a new XER file.

    Westland rule: never overwrite the input. ``output_path`` defaults to
    ``<input-stem>-cpm.xer`` next to the source. Refuses to overwrite an
    existing file at the output path (caller must remove or rename first).

    Uses ``_xer_io.parse_xer`` (not the cache) because the round-trip needs
    the original decoded source text to preserve non-TASK tables byte-for-
    byte. Caching wouldn't help here -- this is a one-shot write, not a
    repeated-read workload.

    The ``cache`` parameter is accepted for signature parity with the other
    tools but isn't consulted; it's threaded through to keep the register
    pattern uniform.
    """
    src = Path(xer_path)
    if output_path is None:
        out = src.with_name(f"{src.stem}-cpm{src.suffix}")
        output_path = str(out)
    else:
        out = Path(output_path)

    # Refuse to overwrite the source. Compare resolved paths so a relative
    # vs. absolute input doesn't sneak through.
    if src.resolve() == out.resolve():
        raise ValueError(
            f"output_path is the same as xer_path ({xer_path}); refusing "
            "to overwrite the source XER. Pass a different output_path."
        )
    if out.exists():
        raise FileExistsError(
            f"Output XER already exists at {output_path}; refusing to "
            "overwrite. Remove or rename it first."
        )

    tables, table_fields, original_text = _xer_io_parse(str(src))

    project_rows = tables.get("PROJECT") or [{}]
    data_date = (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
    )
    results, _metadata = schedule_forward_backward(
        tables.get("TASK", []),
        tables.get("TASKPRED", []),
        tables.get("CALENDAR", []),
        data_date,
        schedoptions=tables.get("SCHEDOPTIONS"),
        project=tables.get("PROJECT"),
    )

    # Build TASK row updates keyed by task_id. Only project _CPM_FIELDS so
    # write_xer_with_updates leaves everything else byte-identical.
    task_updates: dict = {}
    for t in results:
        tid = t.get("task_id", "")
        if not tid:
            continue
        task_updates[tid] = {
            f: (t.get(f) if t.get(f) is not None else "")
            for f in _CPM_FIELDS
        }

    write_xer_with_updates(
        original_text,
        table_fields,
        {"TASK": ("task_id", task_updates)},
        str(out),
    )
    return {"output_path": str(out)}


def get_gantt_json_impl(
    xer_path: str, project_name: Optional[str], cache
) -> dict:
    """Return the structured chart payload that ``build_gantt_html`` consumes:
    project metadata + WBS+activity rows + the ``paths`` analytics block."""
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)
    project_rows = parsed.get("PROJECT") or [{}]
    data_date = (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
    )
    return build_activities_json(
        results,
        metadata,
        parsed.get("TASKPRED", []),
        project_name=project_name,
        data_date=data_date,
        wbs_rows=parsed.get("PROJWBS", []),
    )


def render_gantt_html_impl(
    xer_path: str, project_name: Optional[str], output_path: str, cache
) -> dict:
    """Write a standalone HTML Gantt report to ``output_path`` and return the
    resolved path. Caller is responsible for choosing a writable location;
    the tool doesn't overwrite-protect (rendering a chart isn't destructive
    of XER source, which is what the file-immutability rule covers)."""
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)
    project_rows = parsed.get("PROJECT") or [{}]
    data_date = (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
    )
    render_schedule_html(
        results,
        project_name or "",
        data_date,
        metadata,
        output_path,
    )
    return {"output_path": output_path}


def get_delay_impacts_impl(
    xer_path: str,
    impact_activities: Optional[list],
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Float Path Delay Analysis: how delayed activities push the terminal
    milestone. The underlying function runs its own CPM internally (it needs
    the late-date fields to compute float-based variance) so the cache's CPM
    result isn't reused here.
    """
    parsed = cache.get_parsed(xer_path)
    # Match the data_date selection logic the cache uses for consistency.
    project_rows = parsed.get("PROJECT") or [{}]
    data_date = (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
    )
    return compute_delay_impacts(
        parsed.get("TASK", []),
        parsed.get("TASKPRED", []),
        parsed.get("CALENDAR", []),
        data_date,
        impact_activities=impact_activities,
        milestone_id=milestone_id,
    )


def get_milestone_path_coverage_impl(
    xer_path: str, milestone_id: Optional[str], cache
) -> dict:
    """Connect/disconnect analysis against the terminal milestone.

    Raises :class:`milestones.MilestoneAmbiguousError` (via the underlying
    function) when ``milestone_id`` is omitted and the schedule has more
    than one terminal milestone.
    """
    parsed = cache.get_parsed(xer_path)
    coverage = analyze_sc_path_coverage(
        parsed.get("TASK", []),
        parsed.get("TASKPRED", []),
        wbs_rows=parsed.get("PROJWBS", []),
        milestone_id=milestone_id,
    )
    # The underlying function returns ``connected_ids`` as a Python set;
    # convert to a sorted list so the JSON serializer is happy and callers
    # get a stable order.
    if isinstance(coverage.get("connected_ids"), set):
        coverage["connected_ids"] = sorted(coverage["connected_ids"])
    return coverage


def get_anchor_absorption_suggestions_impl(
    xer_path: str, slip: dict, max_suggestions: int, cache
) -> dict:
    """Return ranked duration-cut suggestions that would pull a slipped
    anchor task back to its target date. Thin pass-through to
    :func:`suggest_anchor_absorption`."""
    parsed = cache.get_parsed(xer_path)
    results, _metadata = cache.get_cpm(xer_path)
    suggestions = suggest_anchor_absorption(
        results,
        parsed.get("TASKPRED", []),
        slip,
        max_suggestions=max_suggestions,
    )
    return {"suggestions": suggestions}


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
    def get_anchor_conflicts(
        xer_path: str,
        anchors: Optional[list] = None,
        anchors_path: Optional[str] = None,
        tolerance_days: int = 0,
    ) -> dict:
        """Report any CPM-computed dates that drift past the project's
        bid-given anchor dates beyond ``tolerance_days``.

        Args:
            xer_path: Path to the .xer file.
            anchors: Optional inline list of anchor dicts (``task_code``,
                ``anchor_date``, ``anchor_kind``, ``kind_label``).
            anchors_path: Optional path to a JSON file with
                ``{"anchors": [...]}`` top-level.
            tolerance_days: Allowed absolute slip in calendar days without
                being reported. Defaults to 0 (strict).

        Returns:
            ``{ slips: [{task_id, task_code, task_name, kind_label,
            anchor_date, computed_date, anchor_kind, slip_days}, ...] }``.
            Empty list means every anchor holds.
        """
        return get_anchor_conflicts_impl(
            xer_path, anchors, anchors_path, tolerance_days, cache
        )

    @mcp.tool()
    def run_cpm(xer_path: str, output_path: Optional[str] = None) -> dict:
        """Run a fresh CPM forward+backward pass on the XER and write the
        result to a new file. The source XER is never overwritten.

        Args:
            xer_path: Path to the .xer file.
            output_path: Optional output path. Defaults to
                ``<input-stem>-cpm.xer`` next to the source. Refuses to
                overwrite an existing file -- remove or rename the
                existing target first.

        Returns:
            ``{ output_path: "<resolved path>" }``.
        """
        return run_cpm_impl(xer_path, output_path, cache)

    @mcp.tool()
    def get_gantt_json(
        xer_path: str, project_name: Optional[str] = None
    ) -> dict:
        """Return the structured chart payload (project metadata, WBS +
        activity rows, paths analytics) that the standalone Gantt HTML
        renderer consumes.

        Args:
            xer_path: Path to the .xer file.
            project_name: Optional display name surfaced in the ``project``
                block.

        Returns:
            ``{ project: {...}, activities: [...], paths: [...],
            circular_dependencies: [...] }``.
        """
        return get_gantt_json_impl(xer_path, project_name, cache)

    @mcp.tool()
    def render_gantt_html(
        xer_path: str, output_path: str, project_name: Optional[str] = None
    ) -> dict:
        """Render a standalone HTML schedule report and write it to
        ``output_path``.

        Args:
            xer_path: Path to the .xer file.
            output_path: Filesystem path where the HTML will be written.
            project_name: Optional display name in the report header.

        Returns:
            ``{ output_path: "<resolved path>" }``.
        """
        return render_gantt_html_impl(
            xer_path, project_name, output_path, cache
        )

    @mcp.tool()
    def get_delay_impacts(
        xer_path: str,
        impact_activities: Optional[list] = None,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Float Path Delay Analysis: how delayed (or specified impact)
        activities push the terminal milestone.

        Args:
            xer_path: Path to the .xer file.
            impact_activities: Optional list of task_ids to analyze. When
                omitted, the underlying function auto-detects IMPACT/delay
                activities by name.
            milestone_id: Optional terminal milestone task_id. Raises
                ``MilestoneAmbiguousError`` when omitted on multi-terminal
                schedules.

        Returns:
            ``{ sc_task_id, sc_task_name, sc_task_code, baseline_sc_date,
            data_date, impacts: [{task_id, task_code, task_name, data_date,
            previous_sc_date, revised_sc_date, variance_cal_days,
            driving_path, driving_path_names, is_critical,
            total_float_days}, ...] }``.
        """
        return get_delay_impacts_impl(
            xer_path, impact_activities, milestone_id, cache
        )

    @mcp.tool()
    def get_milestone_path_coverage(
        xer_path: str, milestone_id: Optional[str] = None
    ) -> dict:
        """Identify which incomplete activities trace to the terminal
        milestone and which don't (= dangling work that needs a successor
        added).

        Args:
            xer_path: Path to the .xer file.
            milestone_id: Optional task_id of the terminal milestone. Omit
                on single-terminal schedules to auto-resolve; raises
                ``MilestoneAmbiguousError`` when omitted and multiple
                terminal milestones exist.

        Returns:
            ``{ sc_task_id, sc_task_name, sc_task_code, connected_count,
            connected_ids: [...], disconnected_count, disconnected_tasks,
            disconnected_by_wbs, coverage_pct, total_incomplete,
            recommendations }``.
        """
        return get_milestone_path_coverage_impl(xer_path, milestone_id, cache)

    @mcp.tool()
    def get_anchor_absorption_suggestions(
        xer_path: str, slip: dict, max_suggestions: int = 8
    ) -> dict:
        """Given a single anchor slip (typically one entry from
        ``get_anchor_conflicts`` output), return ranked duration-cut
        candidates on the driving path that could absorb the slip.

        Args:
            xer_path: Path to the .xer file.
            slip: Slip dict with ``task_id`` and ``slip_days``. The other
                fields from ``get_anchor_conflicts`` output are ignored.
            max_suggestions: Cap on the number of candidates returned.
                Defaults to 8.

        Returns:
            ``{ suggestions: [{task_id, task_code, task_name,
            current_duration_days, suggested_max_cut_days,
            total_float_days, kind, rationale}, ...] }`` ranked by leverage
            (largest current_duration_days first).
        """
        return get_anchor_absorption_suggestions_impl(
            xer_path, slip, max_suggestions, cache
        )

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
