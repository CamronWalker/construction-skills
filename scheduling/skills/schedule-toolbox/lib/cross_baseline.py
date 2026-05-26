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
from milestones import MilestoneNotFoundError, get_milestones
from xer_compare import compare_xer_pair


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
            metadata; raises :class:`MilestoneNotFoundError` if the
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


def _override_sc_milestone(
    metadata: dict, milestone_id: Optional[str], tasks: list
) -> dict:
    """Shallow-copy ``metadata`` with ``sc_milestone_*`` keys overridden
    to point at ``milestone_id``. Helper used by every function in this
    module that accepts an optional ``milestone_id`` parameter.

    Raises :class:`MilestoneNotFoundError` carrying the candidate
    milestone list if ``milestone_id`` doesn't exist in ``tasks`` -- the
    MCP layer can surface the candidates to the caller so they can repair
    the request.
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
        # Surface the not-found case with the candidate list so the
        # caller can repair the request.
        candidates = get_milestones(tasks, include_complete=False)
        raise MilestoneNotFoundError(
            f"milestone_id '{milestone_id}' not found; "
            f"{len(candidates)} candidate(s) available",
            candidates=candidates,
        )
    return new_meta


def _safe_float(value, default: float) -> float:
    """Float-coerce ``value``, returning ``default`` on bad input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def compute_gain_loss_attribution(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    raise NotImplementedError("compute_gain_loss_attribution ships in Plan 2 Task C5")
