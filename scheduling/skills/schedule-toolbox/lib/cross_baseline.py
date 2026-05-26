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


# ---------------------------------------------------------------------------
# Stubs for C3-C5 -- the real implementations land in those tasks.
# ---------------------------------------------------------------------------

def compute_float_consumption(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    raise NotImplementedError("compute_float_consumption ships in Plan 2 Task C3")


def compute_trade_slip_summary(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
    trade_field: Optional[str] = None,
) -> dict:
    raise NotImplementedError("compute_trade_slip_summary ships in Plan 2 Task C4")


def compute_gain_loss_attribution(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    raise NotImplementedError("compute_gain_loss_attribution ships in Plan 2 Task C5")
