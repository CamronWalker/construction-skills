"""Mutation engine for XerDoc.

One handler function per change type plus an orchestrator that runs the
4-pass validation (syntactic, handler-dispatch-on-deep-copy, xer_validate
post-state, post-CPM feedback diff) and atomic write.

Public API:
    apply_changes(doc, changes, *, strict, dry_run) -> ApplyResult
    fix_duplicate_ids(doc, strategy) -> tuple[XerDoc, dict]
    create_from_template(template_path, metadata) -> XerDoc

Each change-type handler has the signature:
    handler(doc: XerDoc, change: dict, state: ChangeState) -> dict
where state carries cross-change accumulators (newly-added IDs, etc.) and
the return value populates per_change_feedback.
"""
from __future__ import annotations

import copy
import importlib.util
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Load cpm_engine from the same lib directory at import time so the handler
# can call schedule_forward_backward and suggest_anchor_absorption without
# adding lib to sys.path (xer_modify may be imported from outside contexts
# where sys.path does not include the lib directory).
_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_cpm_spec = importlib.util.spec_from_file_location(
    "cpm_engine", os.path.join(_LIB_DIR, "cpm_engine.py")
)
_cpm = importlib.util.module_from_spec(_cpm_spec)
_cpm_spec.loader.exec_module(_cpm)

# ---- public types -----------------------------------------------------------


ChangeRecord = dict  # tagged-union shape; validated per type


@dataclass
class ValidationIssueLite:
    """Lite version of the issue shape — keyed to a change_index so the MCP
    can map errors back to specific records."""

    change_index: int | None
    code: str
    message: str


@dataclass
class PerChangeFeedback:
    change_index: int
    type: str
    feedback: dict


@dataclass
class ApplyResult:
    """Output of apply_changes."""

    doc: object | None        # mutated XerDoc; None on validation failure
    changes_applied: int
    validation_errors: list[ValidationIssueLite] = field(default_factory=list)
    validation_warnings: list[ValidationIssueLite] = field(default_factory=list)
    per_change_feedback: list[PerChangeFeedback] = field(default_factory=list)
    post_cpm_summary: Optional[dict] = None


class ValidationFailure(Exception):
    """Raised by apply_changes when a change record is structurally malformed
    (unknown type, missing required field). Distinguishes 'caller bug' from
    'business rule violation' (which is reported via validation_errors)."""


# ---- handler registry -------------------------------------------------------

_HANDLERS: dict[str, Any] = {}


def _register_handler(change_type: str):
    def decorator(fn):
        _HANDLERS[change_type] = fn
        return fn
    return decorator


# ---- orchestrator -----------------------------------------------------------


@dataclass
class ChangeState:
    """Cross-change accumulator passed to each handler. Tracks new IDs so a
    later add_logic can reference an activity added earlier in the call."""

    new_activity_ids: set[str] = field(default_factory=set)
    new_activity_id_map: dict[str, str] = field(default_factory=dict)
    new_calendar_ids: set[str] = field(default_factory=set)
    new_wbs_ids: set[str] = field(default_factory=set)
    removed_activity_ids: set[str] = field(default_factory=set)
    removed_wbs_ids: set[str] = field(default_factory=set)


def apply_changes(
    doc,
    changes: list[ChangeRecord],
    *,
    strict: bool,
    dry_run: bool,
    pre_state_cpm: Optional[list[dict]] = None,
    target_milestone_id: Optional[str] = None,
) -> ApplyResult:
    """4-pass atomic application of changes to doc.

    Pass 1: syntactic check (per-record required fields, enum validity).
    Pass 2: order-aware reference resolution (apply changes against an
            in-memory copy; track new IDs).
    Pass 3: post-state graph check via xer_validate — any NEW error-severity
            issue (not present before the mutations) blocks the apply.
    Pass 4: post-state CPM + diff (only when Pass 3 succeeds and
            pre_state_cpm is provided).

    Atomicity: Pass 2 works on a deep copy of doc.  The original doc is never
    mutated.  On success, result.doc is the mutated copy.  On any error,
    result.doc is None.

    strict=True treats post-state warnings as errors (Pass 3).
    dry_run=True still runs all four passes and populates CPM feedback, but
    the caller is expected to skip persisting the result; errors still set
    result.doc=None.

    pre_state_cpm: the result list from cpm_engine.schedule_forward_backward
        on the pre-mutation doc (same shape as returned by that function).
        If None, per-change CPM feedback fields stay None (no diff possible)
        and result.post_cpm_summary stays None.
    target_milestone_id: P6 task_id (numeric string) of the milestone to use
        for milestone_impact_days.  If None, the latest TT_FinMile by
        early_finish in the pre-state CPM is selected automatically.
    """
    # Late import avoids an import-time circular dependency.
    from xer_validate import validate as _xer_validate  # noqa: PLC0415

    result = ApplyResult(doc=None, changes_applied=0)

    # Pass 1: syntactic — raise immediately on unknown type (caller bug).
    for i, change in enumerate(changes):
        ct = change.get("type")
        if ct not in _HANDLERS:
            raise ValidationFailure(f"Unknown change type at index {i}: {ct!r}")

    if not changes:
        result.doc = doc
        return result

    # Work on a deep copy so the original doc is never partially mutated.
    working_doc = copy.deepcopy(doc)

    # Pass 3 baseline: capture error-severity issue codes BEFORE mutations so
    # we can identify which errors (if any) are newly introduced.
    pre_report = _xer_validate(working_doc)
    pre_error_keys = frozenset(
        (i.code, i.message) for i in pre_report.issues if i.severity == "error"
    )

    # Pass 2: handler loop — break on first ValidationFailure (partial mutation
    # cannot be safely continued on the same working_doc).
    state = ChangeState()
    for i, change in enumerate(changes):
        handler = _HANDLERS[change["type"]]
        try:
            feedback = handler(working_doc, change, state)
        except ValidationFailure as exc:
            result.validation_errors.append(ValidationIssueLite(
                change_index=i,
                code="HANDLER_ERROR",
                message=str(exc),
            ))
            result.doc = None
            return result
        result.per_change_feedback.append(PerChangeFeedback(
            change_index=i, type=change["type"], feedback=feedback,
        ))
        result.changes_applied += 1

    # Pass 3: validate the post-mutation state; only flag NEW issues.
    # Policy note: orphan-rule issues (ORPHAN_ACTIVITY, ORPHANED_WBS_BRANCH)
    # are emitted by xer_validate at warning severity — they describe logic
    # gaps that still produce P6-importable files. The design spec's table
    # lists the orphan rule as "error" in the apply_xer_changes context;
    # we honor that by treating warnings as blocking only when strict=True.
    # A caller who wants the strict-spec semantics must opt in.
    post_report = _xer_validate(working_doc)
    for issue in post_report.issues:
        key = (issue.code, issue.message)
        if issue.severity == "error" and key not in pre_error_keys:
            result.validation_errors.append(ValidationIssueLite(
                change_index=None,
                code=issue.code,
                message=issue.message,
            ))
        elif issue.severity == "warning":
            result.validation_warnings.append(ValidationIssueLite(
                change_index=None,
                code=issue.code,
                message=issue.message,
            ))
            if strict:
                result.validation_errors.append(ValidationIssueLite(
                    change_index=None,
                    code=issue.code,
                    message=issue.message,
                ))

    if result.validation_errors:
        result.doc = None
        return result

    # Pass 4: post-state CPM + diff (runs even on dry_run; skip only when
    # pre_state_cpm is None — no diff possible without a baseline).
    if pre_state_cpm is not None:
        _run_post_cpm_diff(
            working_doc,
            result,
            changes,
            pre_state_cpm,
            target_milestone_id,
        )

    # All passes clean — return the mutated copy.
    result.doc = working_doc
    return result


# ---- Pass 4: post-CPM diff --------------------------------------------------

# Critical-path threshold: total float <= 8 working hours (1 day) = critical.
_CP_THRESHOLD_HOURS = 8.0


def _is_critical(task_result: dict) -> bool:
    """Return True if a CPM result dict represents a critical activity.

    Uses total_float_hr_cnt (string) written by cpm_engine.  Absent or
    non-numeric values are treated as non-critical.
    """
    try:
        return float(task_result.get("total_float_hr_cnt") or "999") <= _CP_THRESHOLD_HOURS
    except (ValueError, TypeError):
        return False


def _fmt_date(date_str: str | None) -> str | None:
    """Trim a CPM date string to YYYY-MM-DD; return None for empty/None."""
    if not date_str:
        return None
    return date_str[:10]


def _find_target_milestone(
    pre_state_cpm: list[dict],
    target_milestone_id: Optional[str],
) -> Optional[dict]:
    """Return the CPM result dict for the target milestone.

    If target_milestone_id is provided, look it up by task_id.
    Otherwise, find the latest TT_FinMile by early_finish in pre_state_cpm.
    Returns None if no suitable milestone is found.
    """
    if target_milestone_id is not None:
        for task in pre_state_cpm:
            if task.get("task_id") == target_milestone_id:
                return task
        return None

    # Auto-detect: latest TT_FinMile by early_finish
    best = None
    best_ef = None
    for task in pre_state_cpm:
        if task.get("task_type") != "TT_FinMile":
            continue
        ef_str = task.get("early_end_date") or ""
        if not ef_str:
            continue
        ef = ef_str[:10]
        if best_ef is None or ef > best_ef:
            best_ef = ef
            best = task
    return best


def _days_between_date_strings(before: str | None, after: str | None) -> Optional[int]:
    """Return integer day difference (after - before); positive = later.

    Parses only the date portion (YYYY-MM-DD).  Returns None if either
    string is absent or un-parseable.
    """
    if not before or not after:
        return None
    try:
        from datetime import date as _date
        b = _date.fromisoformat(before[:10])
        a = _date.fromisoformat(after[:10])
        return (a - b).days
    except (ValueError, AttributeError):
        return None


def _activity_id_for_change(change: dict) -> Optional[str]:
    """Return the task_code that a change record primarily affects.

    Returns the task_code (i.e. the P6 task_code field, which is what
    callers call 'activity_id') for the affected activity, or None for
    change types where there is no single affected activity (e.g. WBS ops).

    For logic changes (add/remove/modify_logic), the successor is the
    activity whose dates shift.
    """
    ct = change.get("type")
    if ct in ("set_duration", "set_calendar", "remove_activity",
              "dissolve_activity", "set_responsibility"):
        return change.get("activity_id")
    if ct in ("add_logic", "remove_logic", "modify_logic"):
        return change.get("successor_id")
    if ct == "add_activity":
        return change.get("spec", {}).get("code")
    if ct == "pop_activity":
        # The new X activity is the one whose dates are fresh
        return change.get("spec", {}).get("code")
    if ct == "apply_anchor_absorption":
        # Delegates to set_duration — the lowered task_code is in the feedback
        # not in the change record.  Return None; outer loop will leave as None.
        return None
    # WBS handlers: add_wbs, remove_wbs, modify_wbs, move_activities_to_wbs
    return None


def _run_post_cpm_diff(
    working_doc,
    result: "ApplyResult",
    changes: list[dict],
    pre_state_cpm: list[dict],
    target_milestone_id: Optional[str],
) -> None:
    """Run CPM on working_doc and diff against pre_state_cpm.

    Populates result.post_cpm_summary and patches CPM fields on each
    per_change_feedback entry in-place.  All errors are swallowed — if CPM
    fails, the feedback fields simply remain None.
    """
    # Resolve required sections from working_doc
    task_section = working_doc.section("TASK")
    pred_section = working_doc.section("TASKPRED")
    cal_section = working_doc.section("CALENDAR")
    project_section = working_doc.section("PROJECT")

    if task_section is None or pred_section is None or cal_section is None:
        return  # Cannot run CPM without these sections

    # Resolve data_date from PROJECT
    data_date = ""
    if project_section is not None and project_section.rows:
        proj_row = project_section.rows[0]
        data_date = (
            proj_row.get("last_recalc_date")
            or proj_row.get("plan_start_date")
            or ""
        )

    try:
        # Run post-state CPM.  schedule_forward_backward mutates the task dicts
        # in working_doc — that is expected (the mutation note in MEMORY.md
        # refers to passing the SAME dicts to a second CPM call; here we are
        # calling CPM once on the working copy).
        post_cpm_results, _meta = _cpm.schedule_forward_backward(
            task_section.rows,
            pred_section.rows,
            cal_section.rows,
            data_date,
        )
    except Exception:
        # CPM failure — skip diff silently
        return

    # Build lookup maps: task_code -> result dict
    pre_map: dict[str, dict] = {
        t.get("task_code", ""): t for t in pre_state_cpm if t.get("task_code")
    }
    post_map: dict[str, dict] = {
        t.get("task_code", ""): t for t in post_cpm_results if t.get("task_code")
    }

    # Resolve target milestone
    target_pre = _find_target_milestone(pre_state_cpm, target_milestone_id)

    # Find the target milestone in post_map by task_code
    target_post: Optional[dict] = None
    if target_pre is not None:
        target_code = target_pre.get("task_code", "")
        target_post = post_map.get(target_code)

    # Compute milestone completion change
    milestone_before = _fmt_date(
        target_pre.get("early_end_date") if target_pre else None
    )
    milestone_after = _fmt_date(
        target_post.get("early_end_date") if target_post else None
    )
    milestone_net_days = _days_between_date_strings(milestone_before, milestone_after)

    # Compute critical-path membership for each task in pre vs post state
    pre_critical: dict[str, bool] = {
        t.get("task_code", ""): _is_critical(t)
        for t in pre_state_cpm if t.get("task_code")
    }
    post_critical: dict[str, bool] = {
        t.get("task_code", ""): _is_critical(t)
        for t in post_cpm_results if t.get("task_code")
    }

    # CP-changed flag: any task whose is_critical status changed
    all_codes = set(pre_critical.keys()) | set(post_critical.keys())
    cp_diff_count = sum(
        1 for code in all_codes
        if pre_critical.get(code, False) != post_critical.get(code, False)
    )
    critical_path_changed = cp_diff_count > 0
    substantial_cp_change = cp_diff_count > 5

    # Populate post_cpm_summary
    result.post_cpm_summary = {
        "target_milestone_id": target_pre.get("task_id") if target_pre else None,
        "completion_before": milestone_before,
        "completion_after": milestone_after,
        "net_days_change": milestone_net_days,
        "critical_path_changed": critical_path_changed,
        "substantial_cp_change": substantial_cp_change,
    }

    # Patch per-change feedback with CPM-derived fields.
    # Each PerChangeFeedback has a change_index that indexes into the original
    # changes list, letting us recover the change record and hence the
    # affected activity's task_code.
    for pcf in result.per_change_feedback:
        change_record = changes[pcf.change_index] if pcf.change_index < len(changes) else {}
        activity_code = _activity_code_for_pcf(pcf, change_record)
        if activity_code is None:
            continue

        fb = pcf.feedback
        # Only patch feedback dicts that carry the four CPM keys (i.e. handlers
        # that left them as None stubs).  WBS handlers don't have these keys.
        if "activity_end_before" not in fb:
            continue

        pre_task = pre_map.get(activity_code)
        post_task = post_map.get(activity_code)

        # activity_end_before: pre-state EF (None for add_activity — didn't exist)
        ef_before: Optional[str] = None
        if pre_task is not None and pcf.type not in ("add_activity", "pop_activity"):
            ef_before = _fmt_date(pre_task.get("early_end_date"))

        # activity_end_after: post-state EF (None for remove_activity / dissolve_activity)
        ef_after: Optional[str] = None
        if post_task is not None and pcf.type not in ("remove_activity", "dissolve_activity"):
            ef_after = _fmt_date(post_task.get("early_end_date"))

        # now_on_critical_path: from post-state (None if post task not found)
        now_critical: Optional[bool] = None
        if post_task is not None and pcf.type not in ("remove_activity", "dissolve_activity"):
            now_critical = _is_critical(post_task)

        fb["activity_end_before"] = ef_before
        fb["activity_end_after"] = ef_after
        fb["milestone_impact_days"] = milestone_net_days
        fb["now_on_critical_path"] = now_critical


def _activity_code_for_pcf(
    pcf: "PerChangeFeedback",
    change: dict,
) -> Optional[str]:
    """Return the task_code affected by a change, given the original change record.

    WBS handlers and apply_anchor_absorption return None (no single
    activity code to diff).
    """
    ct = pcf.type

    # WBS handlers — no schedule logic impact; skip
    if ct in ("add_wbs", "remove_wbs", "modify_wbs", "move_activities_to_wbs"):
        return None

    # apply_anchor_absorption — delegates to set_duration; the suggestion's
    # task_code is in set_duration_feedback inside the feedback dict.
    if ct == "apply_anchor_absorption":
        inner = pcf.feedback.get("set_duration_feedback") or {}
        # set_duration_feedback is the dict returned by _handle_set_duration,
        # which does not embed the activity_id.  We cannot recover it from
        # feedback alone.  The suggestion_chosen dict has 'task_code'.
        suggestion = pcf.feedback.get("suggestion_chosen") or {}
        return suggestion.get("task_code") or None

    return _activity_id_for_change(change)


# ---- handlers ---------------------------------------------------------------


@_register_handler("set_duration")
def _handle_set_duration(doc, change: dict, state: ChangeState) -> dict:
    activity_id = change["activity_id"]
    new_duration_days = change["new_duration_days"]

    task_section = doc.section("TASK")
    row_index = None
    if task_section is not None:
        for i, row in enumerate(task_section.rows):
            if row.get("task_code") == activity_id:
                row_index = i
                break

    if row_index is None:
        raise ValidationFailure(
            f"set_duration: activity_id {activity_id!r} not found in TASK section"
        )

    # P6 stores duration as whole-hour integer strings (e.g. "80", not "80.0")
    hours_str = str(int(new_duration_days * 8))
    task_section.rows[row_index]["target_drtn_hr_cnt"] = hours_str
    task_section.rows[row_index]["remain_drtn_hr_cnt"] = hours_str
    task_section.mark_dirty(row_index)

    return {
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


_ACTIVITY_TYPES = {"TT_Task", "TT_Mile", "TT_FinMile", "TT_LOE", "TT_WBSSummary"}

_PRED_TYPE_MAP = {
    "FS": "PR_FS",
    "SS": "PR_SS",
    "FF": "PR_FF",
    "SF": "PR_SF",
}

# Reverse map used by dissolve_activity to convert the XER pred_type token back
# to the two-character short form before composition.
_INVERSE_PRED_TYPE_MAP = {v: k for k, v in _PRED_TYPE_MAP.items()}


def _compose_dissolve(pred_rel: str, succ_rel: str) -> str:
    """Return the composed relationship type when an activity is dissolved.

    P6 dissolve composition rule: take the predecessor-endpoint (first character
    of pred_rel) and the successor-endpoint (second character of succ_rel).

        new_rel = pred_rel[0] + succ_rel[1]

    The dissolved activity's interior endpoints (pred_rel[1] and succ_rel[0])
    are absorbed into the lag formula (pred_lag + dissolved_duration + succ_lag).

    Full 16-combination table:
        FS×FS→FS  FS×SS→FS  FS×FF→FF  FS×SF→FF
        SS×FS→SS  SS×SS→SS  SS×FF→SF  SS×SF→SF
        FF×FS→FS  FF×SS→FS  FF×FF→FF  FF×SF→FF
        SF×FS→SS  SF×SS→SS  SF×FF→SF  SF×SF→SF

    Note: the plan's illustrative "FS×SS→SS" example was almost certainly a typo;
    FS×SS → "F"+"S" = FS under this rule, which is information-preserving and
    consistent with the lag formula.  The rule above is used throughout.
    """
    return pred_rel[0] + succ_rel[1]


@_register_handler("add_logic")
def _handle_add_logic(doc, change: dict, state: ChangeState) -> dict:
    predecessor_id = change["predecessor_id"]
    successor_id = change["successor_id"]
    relationship = change["relationship"]
    lag_days = change["lag_days"]

    # Validate the TASKPRED section exists
    taskpred = doc.section("TASKPRED")
    if taskpred is None:
        raise ValidationFailure(
            "add_logic: TASKPRED section not found in XER document"
        )

    # Resolve predecessor and successor task_codes to numeric task_ids.
    # Order-aware: check the TASK section first, then fall back to
    # state.new_activity_id_map so a later add_logic can reference an activity
    # added by an earlier add_activity in the same apply_changes call.
    task_section = doc.section("TASK")

    pred_task_id = None
    succ_task_id = None
    pred_proj_id = ""
    succ_proj_id = ""

    if task_section is not None:
        for row in task_section.rows:
            if row.get("task_code") == predecessor_id:
                pred_task_id = row["task_id"]
                pred_proj_id = row.get("proj_id", "")
            if row.get("task_code") == successor_id:
                succ_task_id = row["task_id"]
                succ_proj_id = row.get("proj_id", "")

    # Fall back to state for activities added earlier in the same call.
    if pred_task_id is None and predecessor_id in state.new_activity_id_map:
        pred_task_id = state.new_activity_id_map[predecessor_id]
        # proj_id is not tracked in state; default to proj_id of first TASK row.
        if task_section is not None and task_section.rows:
            pred_proj_id = task_section.rows[0].get("proj_id", "")

    if succ_task_id is None and successor_id in state.new_activity_id_map:
        succ_task_id = state.new_activity_id_map[successor_id]
        if task_section is not None and task_section.rows:
            succ_proj_id = task_section.rows[0].get("proj_id", "")

    if pred_task_id is None:
        raise ValidationFailure(
            f"add_logic: predecessor_id {predecessor_id!r} not found in TASK section"
        )
    if succ_task_id is None:
        raise ValidationFailure(
            f"add_logic: successor_id {successor_id!r} not found in TASK section"
        )

    # Map the relationship string to P6 pred_type
    p6_pred_type = _PRED_TYPE_MAP[relationship]

    # Duplicate edge check: (pred_task_id, task_id, pred_type) triple must be unique
    for row in taskpred.rows:
        if (
            row.get("pred_task_id") == pred_task_id
            and row.get("task_id") == succ_task_id
            and row.get("pred_type") == p6_pred_type
        ):
            raise ValidationFailure(
                f"add_logic: relationship ({predecessor_id!r} → {successor_id!r}, "
                f"{relationship!r}) already exists in TASKPRED"
            )

    # Generate the next task_pred_id
    if taskpred.rows:
        next_id = str(max(int(row["task_pred_id"]) for row in taskpred.rows) + 1)
    else:
        next_id = "1"

    # P6 stores lag as whole-hour integer strings
    lag_hr_cnt = str(int(lag_days * 8))

    # Build the new row, filling all fields in the section's field_order.
    # Fields not provided by this handler default to "".
    new_row = {f: "" for f in taskpred.field_order}
    new_row["task_pred_id"] = next_id
    new_row["task_id"] = succ_task_id
    new_row["pred_task_id"] = pred_task_id
    new_row["proj_id"] = succ_proj_id
    new_row["pred_proj_id"] = pred_proj_id
    new_row["pred_type"] = p6_pred_type
    new_row["lag_hr_cnt"] = lag_hr_cnt

    taskpred.append_row(new_row)

    return {
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


@_register_handler("remove_logic")
def _handle_remove_logic(doc, change: dict, state: ChangeState) -> dict:
    predecessor_id = change["predecessor_id"]
    successor_id = change["successor_id"]
    relationship = change["relationship"]

    # Validate the TASKPRED section exists
    taskpred = doc.section("TASKPRED")
    if taskpred is None:
        raise ValidationFailure(
            "remove_logic: TASKPRED section not found in XER document"
        )

    # Resolve predecessor and successor task_codes to numeric task_ids
    task_section = doc.section("TASK")

    pred_task_id = None
    succ_task_id = None

    if task_section is not None:
        for row in task_section.rows:
            if row.get("task_code") == predecessor_id:
                pred_task_id = row["task_id"]
            if row.get("task_code") == successor_id:
                succ_task_id = row["task_id"]

    if pred_task_id is None:
        raise ValidationFailure(
            f"remove_logic: predecessor_id {predecessor_id!r} not found in TASK section"
        )
    if succ_task_id is None:
        raise ValidationFailure(
            f"remove_logic: successor_id {successor_id!r} not found in TASK section"
        )

    # Map the relationship string to P6 pred_type
    p6_pred_type = _PRED_TYPE_MAP[relationship]

    # Find all matching rows
    matching_indices = [
        i for i, row in enumerate(taskpred.rows)
        if (
            row.get("pred_task_id") == pred_task_id
            and row.get("task_id") == succ_task_id
            and row.get("pred_type") == p6_pred_type
        )
    ]

    if len(matching_indices) == 0:
        raise ValidationFailure(
            f"remove_logic: relationship ({predecessor_id!r} → {successor_id!r}, "
            f"{relationship!r}) not found in TASKPRED"
        )
    if len(matching_indices) > 1:
        raise ValidationFailure(
            f"remove_logic: multiple rows match ({predecessor_id!r} → {successor_id!r}, "
            f"{relationship!r}) in TASKPRED — document is structurally malformed"
        )

    i = matching_indices[0]

    # Remove the row from rows (and raw_lines if present), then re-index _dirty.
    # raw_lines is a prefix of rows: rows appended in this same edit session
    # (e.g. via add_logic) have no raw_lines entry, so a popped index can sit
    # beyond len(raw_lines). Guard the raw_lines.pop on bounds, not just None,
    # or removing a freshly-added edge raises IndexError.
    taskpred.rows.pop(i)
    if taskpred.raw_lines is not None and i < len(taskpred.raw_lines):
        taskpred.raw_lines.pop(i)

    # Re-index _dirty: entries at index > i shift down by 1; entry i itself is gone
    taskpred._dirty = {d - 1 if d > i else d for d in taskpred._dirty if d != i}

    return {
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


@_register_handler("modify_logic")
def _handle_modify_logic(doc, change: dict, state: ChangeState) -> dict:
    predecessor_id = change["predecessor_id"]
    successor_id = change["successor_id"]
    relationship = change["relationship"]
    new_relationship = change.get("new_relationship")
    new_lag_days = change.get("new_lag_days")

    # At least one mutation field must be provided
    if new_relationship is None and new_lag_days is None:
        raise ValidationFailure(
            "modify_logic: at least one of 'new_relationship' or 'new_lag_days' must be provided"
        )

    # Validate the TASKPRED section exists
    taskpred = doc.section("TASKPRED")
    if taskpred is None:
        raise ValidationFailure(
            "modify_logic: TASKPRED section not found in XER document"
        )

    # Resolve predecessor and successor task_codes to numeric task_ids
    task_section = doc.section("TASK")

    pred_task_id = None
    succ_task_id = None

    if task_section is not None:
        for row in task_section.rows:
            if row.get("task_code") == predecessor_id:
                pred_task_id = row["task_id"]
            if row.get("task_code") == successor_id:
                succ_task_id = row["task_id"]

    if pred_task_id is None:
        raise ValidationFailure(
            f"modify_logic: predecessor_id {predecessor_id!r} not found in TASK section"
        )
    if succ_task_id is None:
        raise ValidationFailure(
            f"modify_logic: successor_id {successor_id!r} not found in TASK section"
        )

    # Map the selector relationship to P6 pred_type
    p6_pred_type = _PRED_TYPE_MAP[relationship]

    # Find all rows matching the selector triple (pred_task_id, task_id, pred_type)
    matching_indices = [
        i for i, row in enumerate(taskpred.rows)
        if (
            row.get("pred_task_id") == pred_task_id
            and row.get("task_id") == succ_task_id
            and row.get("pred_type") == p6_pred_type
        )
    ]

    if len(matching_indices) == 0:
        raise ValidationFailure(
            f"modify_logic: relationship ({predecessor_id!r} → {successor_id!r}, "
            f"{relationship!r}) not found in TASKPRED"
        )
    if len(matching_indices) > 1:
        raise ValidationFailure(
            f"modify_logic: multiple rows match ({predecessor_id!r} → {successor_id!r}, "
            f"{relationship!r}) in TASKPRED — document is structurally malformed"
        )

    i = matching_indices[0]

    # If new_relationship changes the type, verify the new triple won't create a duplicate.
    # Only check when new_relationship is provided AND differs from the current selector.
    if new_relationship is not None:
        new_p6_pred_type = _PRED_TYPE_MAP[new_relationship]
        if new_p6_pred_type != p6_pred_type:
            for j, row in enumerate(taskpred.rows):
                if j == i:
                    continue
                if (
                    row.get("pred_task_id") == pred_task_id
                    and row.get("task_id") == succ_task_id
                    and row.get("pred_type") == new_p6_pred_type
                ):
                    raise ValidationFailure(
                        f"modify_logic: changing ({predecessor_id!r} → {successor_id!r}) "
                        f"from {relationship!r} to {new_relationship!r} would create a "
                        f"duplicate relationship in TASKPRED"
                    )

    # Apply mutations
    if new_relationship is not None:
        taskpred.rows[i]["pred_type"] = _PRED_TYPE_MAP[new_relationship]
    if new_lag_days is not None:
        taskpred.rows[i]["lag_hr_cnt"] = str(int(new_lag_days * 8))

    taskpred.mark_dirty(i)

    return {
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


def _validate_activity_spec(
    spec: dict,
    task,
    doc,
    state: ChangeState,
    handler_name: str,
) -> None:
    """Validate a new-activity spec dict; raise ValidationFailure on any violation.

    Checks performed (same rules as add_activity D7):
      1. All 6 required fields present.
      2. task_code not already in TASK section or state.new_activity_ids.
      3. wbs_id in PROJWBS or state.new_wbs_ids.
      4. calendar_id in CALENDAR or state.new_calendar_ids.
      5. activity_type in _ACTIVITY_TYPES.
      6. duration_days >= 0.

    handler_name is used as a prefix in error messages so callers get context
    (e.g. "pop_activity: ..." rather than the generic form).
    """
    required_fields = ("code", "name", "duration_days", "calendar_id", "wbs_id", "activity_type")
    missing = [f for f in required_fields if f not in spec]
    if missing:
        raise ValidationFailure(
            f"{handler_name}: missing required spec field(s): {', '.join(missing)}"
        )

    code = spec["code"]
    duration_days = spec["duration_days"]
    calendar_id = spec["calendar_id"]
    wbs_id = spec["wbs_id"]
    activity_type = spec["activity_type"]

    existing_codes = {r.get("task_code") for r in task.rows}
    if code in existing_codes or code in state.new_activity_ids:
        raise ValidationFailure(
            f"{handler_name}: task_code {code!r} already exists — duplicate activity codes are not allowed"
        )

    projwbs = doc.section("PROJWBS")
    wbs_in_doc = (
        projwbs is not None
        and any(r.get("wbs_id") == wbs_id for r in projwbs.rows)
    )
    if not wbs_in_doc and wbs_id not in state.new_wbs_ids:
        raise ValidationFailure(
            f"{handler_name}: wbs_id {wbs_id!r} not found in PROJWBS section"
        )

    calendar_section = doc.section("CALENDAR")
    cal_in_doc = (
        calendar_section is not None
        and any(r.get("clndr_id") == calendar_id for r in calendar_section.rows)
    )
    if not cal_in_doc and calendar_id not in state.new_calendar_ids:
        raise ValidationFailure(
            f"{handler_name}: calendar_id {calendar_id!r} not found in CALENDAR section"
        )

    if activity_type not in _ACTIVITY_TYPES:
        raise ValidationFailure(
            f"{handler_name}: unknown activity_type {activity_type!r} — "
            f"must be one of {sorted(_ACTIVITY_TYPES)}"
        )

    if duration_days < 0:
        raise ValidationFailure(
            f"{handler_name}: duration_days must be >= 0, got {duration_days}"
        )


# P6-required NOT-NULL scalar columns for a new, not-started activity.  These
# must never be empty or P6 access-violates on import (AVAA0-1866-2).  Values
# match real Westland exports and the skeleton's milestone rows.  Per-activity
# fields (task_id/code/name/type, durations, clndr_id, wbs_id, proj_id) are
# overridden by the caller after this map is applied.
_NEW_TASK_REQUIRED_DEFAULTS = {
    "phys_complete_pct": "0",
    "rev_fdbk_flag": "N",
    "est_wt": "1",
    "lock_plan_flag": "N",
    "auto_compute_act_flag": "N",
    "complete_pct_type": "CP_Drtn",
    "duration_type": "DT_FixedDUR2",
    "status_code": "TK_NotStart",
    "total_float_hr_cnt": "0",
    "free_float_hr_cnt": "0",
    "act_work_qty": "0",
    "remain_work_qty": "0",
    "target_work_qty": "0",
    "target_equip_qty": "0",
    "act_equip_qty": "0",
    "remain_equip_qty": "0",
    "priority_type": "PT_Normal",
    "driving_path_flag": "N",
    "act_this_per_work_qty": "0",
    "act_this_per_equip_qty": "0",
}


def _append_new_task(task, spec: dict, state: ChangeState) -> str:
    """Append a new TASK row from a validated spec dict; update state; return new task_id.

    Assumes spec has already been validated by _validate_activity_spec.
    Returns the new numeric task_id string.
    """
    code = spec["code"]
    name = spec["name"]
    duration_days = spec["duration_days"]
    calendar_id = spec["calendar_id"]
    wbs_id = spec["wbs_id"]
    activity_type = spec["activity_type"]

    new_task_id = str(max((int(r["task_id"]) for r in task.rows), default=0) + 1)
    hours_str = str(int(duration_days * 8))

    # Start from a blank field map, then stamp the FULL set of P6-required
    # NOT-NULL scalar columns before the per-activity overrides.  Emitting a
    # partial row (as the original code did) left bit-flags, the priority enum
    # and the work/equip quantity decimals empty on every generated activity,
    # which crashes Primavera P6 on import (Event Code AVAA0-1866-2).  Defaults
    # mirror a real Westland export (BTLP.xer) and the skeleton's milestone rows.
    new_row = {f: "" for f in task.field_order}
    new_row.update(_NEW_TASK_REQUIRED_DEFAULTS)
    new_row["task_id"] = new_task_id
    new_row["task_code"] = code
    new_row["task_name"] = name
    new_row["task_type"] = activity_type
    new_row["target_drtn_hr_cnt"] = hours_str
    new_row["remain_drtn_hr_cnt"] = hours_str
    new_row["clndr_id"] = calendar_id
    new_row["wbs_id"] = wbs_id
    new_row["proj_id"] = task.rows[0]["proj_id"] if task.rows else ""

    task.append_row(new_row)

    state.new_activity_ids.add(code)
    state.new_activity_id_map[code] = new_task_id

    return new_task_id


@_register_handler("add_activity")
def _handle_add_activity(doc, change: dict, state: ChangeState) -> dict:
    spec = change.get("spec", {})

    # Validation 1: TASK section must exist
    task = doc.section("TASK")
    if task is None:
        raise ValidationFailure(
            "add_activity: TASK section not found in XER document"
        )

    # Validations 2-7: delegate to shared helper
    _validate_activity_spec(spec, task, doc, state, "add_activity")

    # Build and append the new row; update state
    new_task_id = _append_new_task(task, spec, state)

    return {
        "new_task_id": new_task_id,
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


@_register_handler("remove_activity")
def _handle_remove_activity(doc, change: dict, state: ChangeState) -> dict:
    activity_id = change["activity_id"]

    # Validation 1: TASK section must exist
    task = doc.section("TASK")
    if task is None:
        raise ValidationFailure(
            "remove_activity: TASK section not found in XER document"
        )

    # Validation 2: the activity must exist in the TASK section
    task_row_index = None
    removed_task_id = None
    for i, row in enumerate(task.rows):
        if row.get("task_code") == activity_id:
            task_row_index = i
            removed_task_id = row["task_id"]
            break

    if task_row_index is None:
        raise ValidationFailure(
            f"remove_activity: activity_id {activity_id!r} not found in TASK section"
        )

    # Step 1: remove the TASK row
    task.rows.pop(task_row_index)
    if task.raw_lines is not None and task_row_index < len(task.raw_lines):
        task.raw_lines.pop(task_row_index)
    # Re-index _dirty for TASK: entries at index > task_row_index shift down by 1;
    # entry task_row_index itself is gone
    task._dirty = {
        d - 1 if d > task_row_index else d
        for d in task._dirty
        if d != task_row_index
    }

    # Step 2: remove all TASKPRED rows referencing the removed activity
    taskpred = doc.section("TASKPRED")
    removed_edges_count = 0

    if taskpred is not None:
        # Collect indices of all rows where pred_task_id or task_id == removed_task_id
        taskpred_indices_to_remove = [
            i for i, row in enumerate(taskpred.rows)
            if row.get("pred_task_id") == removed_task_id
            or row.get("task_id") == removed_task_id
        ]
        removed_edges_count = len(taskpred_indices_to_remove)

        # Remove in reverse order so earlier pops don't shift later indices
        for i in sorted(taskpred_indices_to_remove, reverse=True):
            taskpred.rows.pop(i)
            if taskpred.raw_lines is not None and i < len(taskpred.raw_lines):
                taskpred.raw_lines.pop(i)

        # Re-index _dirty for TASKPRED: subtract the count of removed indices
        # that were less than each dirty index; drop dirty indices that were removed
        removed_set = set(taskpred_indices_to_remove)
        new_dirty: set[int] = set()
        for d in taskpred._dirty:
            if d in removed_set:
                continue  # row is gone
            shift = sum(1 for r in removed_set if r < d)
            new_dirty.add(d - shift)
        taskpred._dirty = new_dirty

    # Step 3: record in state
    state.removed_activity_ids.add(activity_id)

    return {
        "removed_task_id": removed_task_id,
        "removed_edges_count": removed_edges_count,
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


@_register_handler("dissolve_activity")
def _handle_dissolve_activity(doc, change: dict, state: ChangeState) -> dict:
    """Remove an activity and re-wire its predecessors directly to its successors.

    For each (pred, succ) pair in the cartesian product of the dissolved
    activity's predecessors × successors, inserts a new direct edge:

        pred -<composed_rel>+<combined_lag>-> succ

    Composition rule (XZ endpoint composition):
        new_rel = pred_to_D_rel[0] + D_to_succ_rel[1]

    Lag formula:
        new_lag_hr = pred_to_D_lag_hr + dissolved_target_drtn_hr + D_to_succ_lag_hr

    Edge cases:
    - 0 preds OR 0 succs: remove the activity and its edges; no new edges created.
    - Self-loop guard: if pred task_id == succ task_id, skip that cartesian pair.
    - Duplicate guard: if the composed new edge would duplicate an existing
      (pred, succ, rel) triple in TASKPRED, raise ValidationFailure (strict, mirrors
      add_logic behaviour — caller should use remove_logic + add_logic if different
      behaviour is needed).
    - Fanout warning: if more than 20 new edges land (after self-loop pruning),
      feedback['fanout_warning'] = True; no error raised.

    Returns a feedback dict with keys:
        removed_task_id, removed_edges_count, new_edges_count,
        fanout_warning, activity_end_before, activity_end_after,
        milestone_impact_days, now_on_critical_path.
    """
    activity_id = change["activity_id"]

    # --- Locate the TASK row for the dissolved activity -----------------------
    task = doc.section("TASK")
    if task is None:
        raise ValidationFailure(
            "dissolve_activity: TASK section not found in XER document"
        )

    task_row_index = None
    dissolved_task_id = None
    dissolved_drtn_hr = 0

    for i, row in enumerate(task.rows):
        if row.get("task_code") == activity_id:
            task_row_index = i
            dissolved_task_id = row["task_id"]
            try:
                dissolved_drtn_hr = int(row.get("target_drtn_hr_cnt") or "0")
            except ValueError:
                dissolved_drtn_hr = 0
            break

    if task_row_index is None:
        raise ValidationFailure(
            f"dissolve_activity: activity_id {activity_id!r} not found in TASK section"
        )

    # --- Collect predecessor and successor edges from TASKPRED ----------------
    taskpred = doc.section("TASKPRED")
    pred_edges: list[dict] = []  # edges where D is the successor (task_id == D)
    succ_edges: list[dict] = []  # edges where D is the predecessor (pred_task_id == D)

    if taskpred is not None:
        for row in taskpred.rows:
            if row.get("task_id") == dissolved_task_id:
                pred_edges.append(row)
            elif row.get("pred_task_id") == dissolved_task_id:
                succ_edges.append(row)

    # --- Read max task_pred_id BEFORE any removal ----------------------------
    # Step 1 of the task_pred_id sequencing contract: snapshot max now so that
    # the IDs we generate don't collide with the rows we are about to remove.
    if taskpred is not None and taskpred.rows:
        max_task_pred_id = max(int(r["task_pred_id"]) for r in taskpred.rows)
    else:
        max_task_pred_id = 0

    # --- Compute new edges (cartesian product) --------------------------------
    new_edge_specs: list[tuple[str, str, str, str]] = []
    # Each entry: (pred_task_id, succ_task_id, p6_pred_type, lag_hr_str)

    if pred_edges and succ_edges:
        # Build a snapshot of existing (pred, succ, type) triples for dup check.
        # We include all current TASKPRED rows; after removal the D-edges will be
        # gone, but the remaining edges are what we must avoid duplicating against.
        # Exclude D's own edges from the dup-check set since they will be removed.
        # pred_edges/succ_edges are populated only inside the `taskpred is not None`
        # block above, so reaching here guarantees taskpred exists.
        d_edge_ids = {r["task_pred_id"] for r in pred_edges + succ_edges}
        existing_triples: set[tuple[str, str, str]] = set()
        for row in taskpred.rows:
            if row["task_pred_id"] not in d_edge_ids:
                existing_triples.add((
                    row["pred_task_id"],
                    row["task_id"],
                    row["pred_type"],
                ))

        for pred_edge in pred_edges:
            for succ_edge in succ_edges:
                p_task_id = pred_edge["pred_task_id"]
                s_task_id = succ_edge["task_id"]

                # Self-loop guard
                if p_task_id == s_task_id:
                    continue

                # Compose relationship type
                pred_short = _INVERSE_PRED_TYPE_MAP.get(pred_edge["pred_type"], "FS")
                succ_short = _INVERSE_PRED_TYPE_MAP.get(succ_edge["pred_type"], "FS")
                composed_short = _compose_dissolve(pred_short, succ_short)
                p6_composed = _PRED_TYPE_MAP[composed_short]

                # Compute combined lag
                try:
                    pred_lag = int(pred_edge.get("lag_hr_cnt") or "0")
                except ValueError:
                    pred_lag = 0
                try:
                    succ_lag = int(succ_edge.get("lag_hr_cnt") or "0")
                except ValueError:
                    succ_lag = 0
                new_lag_hr = pred_lag + dissolved_drtn_hr + succ_lag

                # Duplicate edge check (strict — raise, do not skip)
                triple = (p_task_id, s_task_id, p6_composed)
                if triple in existing_triples:
                    # Identify human-readable codes for the error message
                    pred_code = next(
                        (r["task_code"] for r in task.rows if r["task_id"] == p_task_id),
                        p_task_id,
                    )
                    succ_code = next(
                        (r["task_code"] for r in task.rows if r["task_id"] == s_task_id),
                        s_task_id,
                    )
                    raise ValidationFailure(
                        f"dissolve_activity: dissolving {activity_id!r} would create a "
                        f"duplicate relationship ({pred_code!r} → {succ_code!r}, "
                        f"{composed_short!r}) — already exists in TASKPRED"
                    )

                new_edge_specs.append((p_task_id, s_task_id, p6_composed, str(new_lag_hr)))
                # Register in the dup-check set so later cartesian pairs also see it
                existing_triples.add(triple)

    # --- Remove the dissolved activity's TASK row and all its edges -----------
    # (mirrors _handle_remove_activity logic exactly)

    # Remove TASK row
    task.rows.pop(task_row_index)
    if task.raw_lines is not None and task_row_index < len(task.raw_lines):
        task.raw_lines.pop(task_row_index)
    task._dirty = {
        d - 1 if d > task_row_index else d
        for d in task._dirty
        if d != task_row_index
    }

    removed_edges_count = 0
    if taskpred is not None:
        taskpred_indices_to_remove = [
            i for i, row in enumerate(taskpred.rows)
            if row.get("pred_task_id") == dissolved_task_id
            or row.get("task_id") == dissolved_task_id
        ]
        removed_edges_count = len(taskpred_indices_to_remove)

        for i in sorted(taskpred_indices_to_remove, reverse=True):
            taskpred.rows.pop(i)
            if taskpred.raw_lines is not None and i < len(taskpred.raw_lines):
                taskpred.raw_lines.pop(i)

        removed_set = set(taskpred_indices_to_remove)
        new_dirty: set[int] = set()
        for d in taskpred._dirty:
            if d in removed_set:
                continue
            shift = sum(1 for r in removed_set if r < d)
            new_dirty.add(d - shift)
        taskpred._dirty = new_dirty

    # --- Append new edges to TASKPRED -----------------------------------------
    if new_edge_specs and taskpred is not None:
        # Determine proj_ids from the TASK rows (best-effort; fall back to "")
        task_proj_map: dict[str, str] = {
            row["task_id"]: row.get("proj_id", "")
            for row in task.rows
        }

        next_id = max_task_pred_id
        for (p_task_id, s_task_id, p6_type, lag_hr_str) in new_edge_specs:
            next_id += 1
            new_row = {f: "" for f in taskpred.field_order}
            new_row["task_pred_id"] = str(next_id)
            new_row["task_id"] = s_task_id
            new_row["pred_task_id"] = p_task_id
            new_row["proj_id"] = task_proj_map.get(s_task_id, "")
            new_row["pred_proj_id"] = task_proj_map.get(p_task_id, "")
            new_row["pred_type"] = p6_type
            new_row["lag_hr_cnt"] = lag_hr_str
            taskpred.append_row(new_row)

    # --- State and feedback ---------------------------------------------------
    state.removed_activity_ids.add(activity_id)

    new_edges_count = len(new_edge_specs)
    fanout_warning = new_edges_count > 20

    return {
        "removed_task_id": dissolved_task_id,
        "removed_edges_count": removed_edges_count,
        "new_edges_count": new_edges_count,
        "fanout_warning": fanout_warning,
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


@_register_handler("pop_activity")
def _handle_pop_activity(doc, change: dict, state: ChangeState) -> dict:
    """Insert a new activity X between an existing (predecessor_id, successor_id) edge.

    Mutation sequence:
      1. Remove the original A→B TASKPRED row.
      2. Add new activity X to TASK.
      3. Append two new TASKPRED rows:
           A→X  (pred_type=original, lag_hr_cnt="0")
           X→B  (pred_type=original, lag_hr_cnt=original if preserve_total else "0")

    Spec ambiguity resolutions:
      #1  Both new edges inherit the original A→B pred_type (not "FS" as the spec
          comment suggests).  Rationale: information-preserving — an SS chain
          A SS→X SS→B maintains A_start → X_start → B_start semantics, whereas
          forcing FS would destroy them.
      #2  A→X lag is always 0 regardless of split_lag policy.
      #3  X→B lag = original A→B lag if split_lag=="preserve_total", else 0.
    """
    predecessor_id = change["predecessor_id"]
    successor_id = change["successor_id"]
    spec = change.get("spec", {})
    split_lag = change.get("split_lag")

    # --- Validate split_lag enum -----------------------------------------------
    if split_lag not in ("preserve_total", "drop"):
        raise ValidationFailure(
            f"pop_activity: split_lag must be 'preserve_total' or 'drop', got {split_lag!r}"
        )

    # --- TASK section must exist -----------------------------------------------
    task = doc.section("TASK")
    if task is None:
        raise ValidationFailure(
            "pop_activity: TASK section not found in XER document"
        )

    # --- TASKPRED section must exist -------------------------------------------
    taskpred = doc.section("TASKPRED")
    if taskpred is None:
        raise ValidationFailure(
            "pop_activity: TASKPRED section not found in XER document"
        )

    # --- Resolve predecessor and successor task_codes to numeric task_ids ------
    pred_task_id = None
    succ_task_id = None
    pred_proj_id = ""
    succ_proj_id = ""

    for row in task.rows:
        if row.get("task_code") == predecessor_id:
            pred_task_id = row["task_id"]
            pred_proj_id = row.get("proj_id", "")
        if row.get("task_code") == successor_id:
            succ_task_id = row["task_id"]
            succ_proj_id = row.get("proj_id", "")

    if pred_task_id is None:
        raise ValidationFailure(
            f"pop_activity: predecessor_id {predecessor_id!r} not found in TASK section"
        )
    if succ_task_id is None:
        raise ValidationFailure(
            f"pop_activity: successor_id {successor_id!r} not found in TASK section"
        )

    # --- Find exactly one matching TASKPRED row --------------------------------
    matching_indices = [
        i for i, row in enumerate(taskpred.rows)
        if row.get("pred_task_id") == pred_task_id
        and row.get("task_id") == succ_task_id
    ]

    if len(matching_indices) == 0:
        raise ValidationFailure(
            f"pop_activity: no edge found between {predecessor_id!r} and {successor_id!r} "
            f"in TASKPRED"
        )
    if len(matching_indices) > 1:
        candidates = [
            f"task_pred_id={taskpred.rows[i]['task_pred_id']} "
            f"pred_type={taskpred.rows[i]['pred_type']}"
            for i in matching_indices
        ]
        raise ValidationFailure(
            f"pop_activity: multiple edges exist between {predecessor_id!r} and "
            f"{successor_id!r} — cannot determine which to split without an explicit "
            f"relationship selector. Candidates: {candidates}"
        )

    target_idx = matching_indices[0]
    original_row = taskpred.rows[target_idx]
    original_pred_type = original_row["pred_type"]
    original_lag_hr_cnt = original_row.get("lag_hr_cnt", "0") or "0"

    # --- Validate the new-activity spec ----------------------------------------
    _validate_activity_spec(spec, task, doc, state, "pop_activity")

    # --- Snapshot max task_pred_id BEFORE removal (per sequencing contract) ----
    max_task_pred_id = max(int(r["task_pred_id"]) for r in taskpred.rows)

    # --- Remove the original A→B edge -----------------------------------------
    taskpred.rows.pop(target_idx)
    if taskpred.raw_lines is not None and target_idx < len(taskpred.raw_lines):
        taskpred.raw_lines.pop(target_idx)
    # Re-index _dirty
    taskpred._dirty = {
        d - 1 if d > target_idx else d
        for d in taskpred._dirty
        if d != target_idx
    }

    # --- Add new activity X to TASK; update state ------------------------------
    new_x_task_id = _append_new_task(task, spec, state)
    x_code = spec["code"]

    # --- Append A→X and X→B edges ---------------------------------------------
    # Determine proj_id for X (inherit from the TASK row we just appended)
    x_proj_id = task.rows[-1].get("proj_id", "")

    x_lag_hr_cnt = original_lag_hr_cnt if split_lag == "preserve_total" else "0"

    for edge_pred_task_id, edge_task_id, edge_pred_proj, edge_proj, edge_lag in (
        (pred_task_id,    new_x_task_id, pred_proj_id, x_proj_id,    "0"),
        (new_x_task_id,  succ_task_id,  x_proj_id,    succ_proj_id, x_lag_hr_cnt),
    ):
        max_task_pred_id += 1
        new_edge = {f: "" for f in taskpred.field_order}
        new_edge["task_pred_id"] = str(max_task_pred_id)
        new_edge["task_id"] = edge_task_id
        new_edge["pred_task_id"] = edge_pred_task_id
        new_edge["proj_id"] = edge_proj
        new_edge["pred_proj_id"] = edge_pred_proj
        new_edge["pred_type"] = original_pred_type
        new_edge["lag_hr_cnt"] = edge_lag
        taskpred.append_row(new_edge)

    # --- Feedback --------------------------------------------------------------
    original_lag_days = int(original_lag_hr_cnt) // 8
    removed_edge_short = _INVERSE_PRED_TYPE_MAP.get(original_pred_type, original_pred_type)

    return {
        "new_x_task_id": new_x_task_id,
        "new_x_task_code": x_code,
        "removed_edge_relationship": removed_edge_short,
        "removed_edge_lag_days": original_lag_days,
        "split_policy_applied": split_lag,
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


_WBS_STOP_WORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "at",
})


def _derive_wbs_short_name(wbs_name: str) -> str:
    """Derive a WBS short name from the full WBS name.

    Split on whitespace and hyphens; filter empty tokens and stop-words
    (case-insensitive); take the first letter (uppercased) of each
    remaining word; concatenate.

    Raises ValidationFailure if the result is fewer than 2 characters.
    """
    tokens = re.split(r"[\s\-]+", wbs_name)
    initials = [
        t[0].upper()
        for t in tokens
        if t and t.lower() not in _WBS_STOP_WORDS
    ]
    result = "".join(initials)
    if len(result) < 2:
        raise ValidationFailure(
            f"add_wbs: cannot derive wbs_short_name from {wbs_name!r} — "
            f"only {len(result)} significant initial(s) found (minimum 2 required). "
            f"Provide wbs_short_name explicitly."
        )
    return result


@_register_handler("add_wbs")
def _handle_add_wbs(doc, change: dict, state: ChangeState) -> dict:
    """Append a new PROJWBS row.

    Spec keys:
        wbs_code (required)
        wbs_name (required)
        parent_wbs_id (required)
        wbs_short_name (optional — derived from wbs_name if omitted)

    Validations:
      1. PROJWBS section must exist.
      2. Required spec fields must all be present.
      3. wbs_code must not already exist in PROJWBS.
      4. parent_wbs_id must exist in PROJWBS or state.new_wbs_ids.
      5. wbs_short_name must be >= 2 chars (derived or provided).
    """
    spec = change.get("spec", {})

    # Validation 1: PROJWBS section must exist
    projwbs = doc.section("PROJWBS")
    if projwbs is None:
        raise ValidationFailure(
            "add_wbs: PROJWBS section not found in XER document"
        )

    # Validation 2: required fields
    required_fields = ("wbs_code", "wbs_name", "parent_wbs_id")
    missing = [f for f in required_fields if f not in spec]
    if missing:
        raise ValidationFailure(
            f"add_wbs: missing required spec field(s): {', '.join(missing)}"
        )

    wbs_code = spec["wbs_code"]
    wbs_name = spec["wbs_name"]
    parent_wbs_id = spec["parent_wbs_id"]
    provided_short_name = spec.get("wbs_short_name")

    # Validation 3: wbs_code uniqueness against existing PROJWBS rows
    existing_codes = {r.get("wbs_code") for r in projwbs.rows}
    if wbs_code in existing_codes:
        raise ValidationFailure(
            f"add_wbs: wbs_code {wbs_code!r} already exists in PROJWBS"
        )

    # Validation 4: parent_wbs_id must exist in PROJWBS or state
    parent_in_doc = any(r.get("wbs_id") == parent_wbs_id for r in projwbs.rows)
    if not parent_in_doc and parent_wbs_id not in state.new_wbs_ids:
        raise ValidationFailure(
            f"add_wbs: parent_wbs_id {parent_wbs_id!r} not found in PROJWBS section"
        )

    # Validation 5: resolve wbs_short_name
    if provided_short_name is not None:
        if len(provided_short_name) < 2:
            raise ValidationFailure(
                f"add_wbs: wbs_short_name {provided_short_name!r} is too short "
                f"(minimum 2 characters required)"
            )
        short_name = provided_short_name
        derived = False
    else:
        short_name = _derive_wbs_short_name(wbs_name)
        derived = True

    # Generate the new wbs_id: max(existing) + 1
    new_wbs_id = str(
        max((int(r["wbs_id"]) for r in projwbs.rows), default=0) + 1
    )

    # Build the new row.  Blank the field map, then stamp the P6-required
    # NOT-NULL columns (OBS pointer, node-type flags, EV settings, weight,
    # sequence) BEFORE the per-node overrides.  Leaving these empty crashes P6
    # on import (AVAA0-1866-2).  OBS/EV/weight are inherited from an existing
    # node so the OBS pointer references a row present in THIS file; the
    # node-type flags are forced (a newly-added node is never the project root).
    def _first_nonempty(field, fallback):
        for r in projwbs.rows:
            v = str(r.get(field, "")).strip()
            if v:
                return v
        return fallback

    seqs = [
        int(r["seq_num"]) for r in projwbs.rows
        if str(r.get("seq_num", "")).strip().lstrip("-").isdigit()
    ]

    new_row = {f: "" for f in projwbs.field_order}
    new_row["obs_id"] = _first_nonempty("obs_id", "")
    new_row["seq_num"] = str((max(seqs) if seqs else 0) + 100)
    new_row["est_wt"] = _first_nonempty("est_wt", "1")
    new_row["proj_node_flag"] = "N"
    new_row["sum_data_flag"] = "N"
    new_row["ev_compute_type"] = _first_nonempty("ev_compute_type", "EC_Cmp_pct")
    new_row["ev_etc_compute_type"] = _first_nonempty("ev_etc_compute_type", "EE_PF_cpi")
    new_row["status_code"] = "WS_Open"
    new_row["wbs_id"] = new_wbs_id
    new_row["wbs_code"] = wbs_code
    new_row["wbs_name"] = wbs_name
    new_row["wbs_short_name"] = short_name
    new_row["parent_wbs_id"] = parent_wbs_id
    new_row["proj_id"] = projwbs.rows[0]["proj_id"] if projwbs.rows else ""

    projwbs.append_row(new_row)

    # Update state
    state.new_wbs_ids.add(new_wbs_id)

    return {
        "new_wbs_id": new_wbs_id,
        "derived_short_name": derived,
        "wbs_short_name": short_name,
    }


_REMOVE_WBS_CASCADE_VALUES = frozenset({"fail_if_used", "move_to_parent"})


@_register_handler("remove_wbs")
def _handle_remove_wbs(doc, change: dict, state: ChangeState) -> dict:
    """Remove a PROJWBS row, with optional reparenting of dependents.

    cascade='fail_if_used'  — ValidationFailure if any TASK or child PROJWBS
                              references the removed wbs_id.
    cascade='move_to_parent' — reparent all referencing TASK rows and child
                               PROJWBS rows to the removed WBS's own parent,
                               then remove the row.

    Always disallows removing the project root (parent_wbs_id empty/missing).
    """
    removed_wbs_id = change.get("wbs_id", "")
    cascade = change.get("cascade")

    # Validation 1: cascade enum
    if cascade not in _REMOVE_WBS_CASCADE_VALUES:
        raise ValidationFailure(
            f"remove_wbs: cascade must be one of "
            f"{sorted(_REMOVE_WBS_CASCADE_VALUES)}, got {cascade!r}"
        )

    # Validation 2: PROJWBS section must exist
    projwbs = doc.section("PROJWBS")
    if projwbs is None:
        raise ValidationFailure(
            "remove_wbs: PROJWBS section not found in XER document"
        )

    # Find the WBS row to remove
    wbs_row_index = None
    wbs_row = None
    for i, row in enumerate(projwbs.rows):
        if row.get("wbs_id") == removed_wbs_id:
            wbs_row_index = i
            wbs_row = row
            break

    if wbs_row_index is None:
        raise ValidationFailure(
            f"remove_wbs: wbs_id {removed_wbs_id!r} not found in PROJWBS section"
        )

    # Validation 3: disallow root removal (parent_wbs_id empty or missing)
    parent_wbs_id = wbs_row.get("parent_wbs_id", "")
    if not parent_wbs_id:
        raise ValidationFailure(
            f"remove_wbs: wbs_id {removed_wbs_id!r} is the project root "
            f"(no parent_wbs_id) — root WBS cannot be removed"
        )

    # Collect referencing TASK rows and child PROJWBS rows
    task_section = doc.section("TASK")
    referencing_task_indices: list[int] = []
    if task_section is not None:
        for i, row in enumerate(task_section.rows):
            if row.get("wbs_id") == removed_wbs_id:
                referencing_task_indices.append(i)

    child_wbs_indices: list[int] = []
    for i, row in enumerate(projwbs.rows):
        if row.get("parent_wbs_id") == removed_wbs_id:
            child_wbs_indices.append(i)

    if cascade == "fail_if_used":
        # Validation: fail if any references exist
        blocking_task_codes = []
        if task_section is not None:
            blocking_task_codes = [
                task_section.rows[i].get("task_code", f"task_index={i}")
                for i in referencing_task_indices
            ]
        blocking_child_wbs_ids = [
            projwbs.rows[i].get("wbs_id", f"wbs_index={i}")
            for i in child_wbs_indices
        ]

        if blocking_task_codes or blocking_child_wbs_ids:
            parts = []
            if blocking_task_codes:
                parts.append(f"activities: {blocking_task_codes}")
            if blocking_child_wbs_ids:
                parts.append(f"child WBS: {blocking_child_wbs_ids}")
            raise ValidationFailure(
                f"remove_wbs: wbs_id {removed_wbs_id!r} is still referenced by "
                + "; ".join(parts)
            )

    # cascade == "move_to_parent": reparent before removing
    reparented_task_count = 0
    reparented_wbs_count = 0

    if cascade == "move_to_parent":
        # Reparent TASK rows
        for i in referencing_task_indices:
            task_section.rows[i]["wbs_id"] = parent_wbs_id
            task_section.mark_dirty(i)
            reparented_task_count += 1

        # Reparent child PROJWBS rows
        # Note: these indices are relative to current projwbs.rows; we have not
        # yet removed wbs_row_index, so indices are stable during this loop.
        for i in child_wbs_indices:
            projwbs.rows[i]["parent_wbs_id"] = parent_wbs_id
            projwbs.mark_dirty(i)
            reparented_wbs_count += 1

    # Remove the PROJWBS row (single-row removal pattern from D5)
    projwbs.rows.pop(wbs_row_index)
    if projwbs.raw_lines is not None and wbs_row_index < len(projwbs.raw_lines):
        projwbs.raw_lines.pop(wbs_row_index)
    # Re-index _dirty: entries at index > wbs_row_index shift down by 1;
    # entry wbs_row_index itself is gone.
    projwbs._dirty = {
        d - 1 if d > wbs_row_index else d
        for d in projwbs._dirty
        if d != wbs_row_index
    }

    # Update state
    state.removed_wbs_ids.add(removed_wbs_id)

    return {
        "removed_wbs_id": removed_wbs_id,
        "cascade": cascade,
        "reparented_task_count": reparented_task_count,
        "reparented_wbs_count": reparented_wbs_count,
    }


def _would_create_wbs_cycle(
    projwbs,
    candidate_parent_id: str,
    target_wbs_id: str,
) -> bool:
    """Return True if making candidate_parent_id the parent of target_wbs_id creates a cycle.

    Walks up candidate_parent's ancestor chain; if we encounter target_wbs_id, it's
    a cycle (target is an ancestor of candidate_parent, so candidate_parent is a
    descendant of target — making target a child of its own descendant closes the loop).

    Also returns True on self-loop (candidate_parent_id == target_wbs_id).
    """
    current = candidate_parent_id
    visited: set[str] = set()
    while current:
        if current == target_wbs_id:
            return True
        if current in visited:
            # Existing cycle in the tree — defensive guard
            return True
        visited.add(current)
        # Find the row with wbs_id == current to get its parent
        parent = None
        for r in projwbs.rows:
            if r.get("wbs_id") == current:
                parent = r.get("parent_wbs_id", "")
                break
        if parent is None:
            # current not in PROJWBS rows — it may be a newly added WBS whose row
            # was appended by a preceding add_wbs in the same call.  The spec says
            # state.new_wbs_ids only tracks IDs, not parent links.  Since we cannot
            # walk further, break conservatively (no cycle detected so far).
            break
        current = parent
    return False


@_register_handler("modify_wbs")
def _handle_modify_wbs(doc, change: dict, state: ChangeState) -> dict:
    """Update fields on an existing PROJWBS row.

    Supported fields (all optional, but at least one required):
        new_wbs_code         — must not collide with any OTHER row's wbs_code
        new_wbs_name         — free text
        new_parent_wbs_id    — must exist in PROJWBS or state.new_wbs_ids; must
                               not create a WBS cycle
        new_wbs_short_name   — must be >= 2 characters

    Returns:
        {"wbs_id": <str>, "fields_changed": [<field_name>, ...]}
    """
    wbs_id = change.get("wbs_id", "")
    new_wbs_code = change.get("new_wbs_code")
    new_wbs_name = change.get("new_wbs_name")
    new_parent_wbs_id = change.get("new_parent_wbs_id")
    new_wbs_short_name = change.get("new_wbs_short_name")

    # Validation 1: at least one new_* field
    if (new_wbs_code is None
            and new_wbs_name is None
            and new_parent_wbs_id is None
            and new_wbs_short_name is None):
        raise ValidationFailure(
            "modify_wbs: at least one of new_wbs_code, new_wbs_name, "
            "new_parent_wbs_id, or new_wbs_short_name must be provided"
        )

    # Validation 2: PROJWBS section must exist
    projwbs = doc.section("PROJWBS")
    if projwbs is None:
        raise ValidationFailure(
            "modify_wbs: PROJWBS section not found in XER document"
        )

    # Validation 3: wbs_id must exist in PROJWBS
    row_index = None
    for i, row in enumerate(projwbs.rows):
        if row.get("wbs_id") == wbs_id:
            row_index = i
            break

    if row_index is None:
        raise ValidationFailure(
            f"modify_wbs: wbs_id {wbs_id!r} not found in PROJWBS section"
        )

    target_row = projwbs.rows[row_index]

    # Validation 4: new_wbs_code uniqueness (exempt own row from the check)
    if new_wbs_code is not None:
        current_code = target_row.get("wbs_code", "")
        if new_wbs_code != current_code:
            for i, row in enumerate(projwbs.rows):
                if i == row_index:
                    continue
                if row.get("wbs_code") == new_wbs_code:
                    raise ValidationFailure(
                        f"modify_wbs: new_wbs_code {new_wbs_code!r} already exists "
                        f"in PROJWBS (wbs_id={row.get('wbs_id')!r})"
                    )

    # Validation 5: new_parent_wbs_id checks
    if new_parent_wbs_id is not None:
        # 5a: self-loop
        if new_parent_wbs_id == wbs_id:
            raise ValidationFailure(
                f"modify_wbs: new_parent_wbs_id {new_parent_wbs_id!r} equals the "
                f"target wbs_id — a WBS node cannot be its own parent (cycle)"
            )

        # 5b: parent must exist
        parent_in_doc = any(
            r.get("wbs_id") == new_parent_wbs_id for r in projwbs.rows
        )
        if not parent_in_doc and new_parent_wbs_id not in state.new_wbs_ids:
            raise ValidationFailure(
                f"modify_wbs: new_parent_wbs_id {new_parent_wbs_id!r} not found "
                f"in PROJWBS section"
            )

        # 5c: cycle check — candidate_parent must not be a descendant of target
        if _would_create_wbs_cycle(projwbs, new_parent_wbs_id, wbs_id):
            raise ValidationFailure(
                f"modify_wbs: setting parent of {wbs_id!r} to "
                f"{new_parent_wbs_id!r} would create a WBS cycle"
            )

    # Validation 6: new_wbs_short_name length
    if new_wbs_short_name is not None:
        if len(new_wbs_short_name) < 2:
            raise ValidationFailure(
                f"modify_wbs: new_wbs_short_name {new_wbs_short_name!r} is too short "
                f"(minimum 2 characters required)"
            )

    # Mutation: apply all requested changes and track what changed
    fields_changed: list[str] = []

    if new_wbs_code is not None:
        target_row["wbs_code"] = new_wbs_code
        fields_changed.append("wbs_code")

    if new_wbs_name is not None:
        target_row["wbs_name"] = new_wbs_name
        fields_changed.append("wbs_name")

    if new_parent_wbs_id is not None:
        target_row["parent_wbs_id"] = new_parent_wbs_id
        fields_changed.append("parent_wbs_id")

    if new_wbs_short_name is not None:
        target_row["wbs_short_name"] = new_wbs_short_name
        fields_changed.append("wbs_short_name")

    projwbs.mark_dirty(row_index)

    return {
        "wbs_id": wbs_id,
        "fields_changed": fields_changed,
    }


@_register_handler("move_activities_to_wbs")
def _handle_move_activities_to_wbs(doc, change: dict, state: ChangeState) -> dict:
    """Bulk set TASK.wbs_id for a list of activities.

    Validations (all raise ValidationFailure):
      1. TASK section must exist.
      2. PROJWBS section must exist.
      3. activity_ids must not be empty.
      4. new_wbs_id must exist in PROJWBS or state.new_wbs_ids.
      5. All activity_ids must resolve to TASK rows by task_code (all missing
         ids collected and reported together).

    Duplicate activity_ids are silently deduplicated.

    Returns:
      {"moved_count": int, "new_wbs_id": str, "activity_ids": [sorted deduped list]}
    """
    activity_ids = change["activity_ids"]
    new_wbs_id = change["new_wbs_id"]

    # Validation 1: TASK section must exist
    task_section = doc.section("TASK")
    if task_section is None:
        raise ValidationFailure(
            "move_activities_to_wbs: TASK section not found in XER document"
        )

    # Validation 2: PROJWBS section must exist
    projwbs = doc.section("PROJWBS")
    if projwbs is None:
        raise ValidationFailure(
            "move_activities_to_wbs: PROJWBS section not found in XER document"
        )

    # Validation 3: activity_ids must not be empty
    if not activity_ids:
        raise ValidationFailure(
            "move_activities_to_wbs: activity_ids must not be empty"
        )

    # Validation 4: new_wbs_id must exist in PROJWBS or state.new_wbs_ids
    wbs_in_doc = any(r.get("wbs_id") == new_wbs_id for r in projwbs.rows)
    if not wbs_in_doc and new_wbs_id not in state.new_wbs_ids:
        raise ValidationFailure(
            f"move_activities_to_wbs: new_wbs_id {new_wbs_id!r} not found in PROJWBS section"
        )

    # Dedup activity_ids (order-insensitive; duplicates are a no-op)
    deduped_ids = list(dict.fromkeys(activity_ids))  # preserves first-seen order for dedup

    # Validation 5: all activity_ids must resolve to TASK rows
    existing_codes = {r.get("task_code") for r in task_section.rows}
    missing = [aid for aid in deduped_ids if aid not in existing_codes]
    if missing:
        raise ValidationFailure(
            f"move_activities_to_wbs: activity_id(s) not found in TASK section: "
            f"{missing}"
        )

    # Mutation: set wbs_id on all matching TASK rows
    moved_count = 0
    for i, row in enumerate(task_section.rows):
        if row.get("task_code") in deduped_ids:
            row["wbs_id"] = new_wbs_id
            task_section.mark_dirty(i)
            moved_count += 1

    return {
        "moved_count": moved_count,
        "new_wbs_id": new_wbs_id,
        "activity_ids": sorted(deduped_ids),
    }


@_register_handler("set_calendar")
def _handle_set_calendar(doc, change: dict, state: ChangeState) -> dict:
    activity_id = change["activity_id"]
    new_calendar_id = change["new_calendar_id"]

    # Locate the TASK row
    task_section = doc.section("TASK")
    row_index = None
    if task_section is not None:
        for i, row in enumerate(task_section.rows):
            if row.get("task_code") == activity_id:
                row_index = i
                break

    if row_index is None:
        raise ValidationFailure(
            f"set_calendar: activity_id {activity_id!r} not found in TASK section"
        )

    # Validate the calendar exists in the doc or in state (order-aware pass)
    calendar_section = doc.section("CALENDAR")
    calendar_exists = new_calendar_id in state.new_calendar_ids or (
        calendar_section is not None
        and any(
            row.get("clndr_id") == new_calendar_id
            for row in calendar_section.rows
        )
    )

    if not calendar_exists:
        raise ValidationFailure(
            f"set_calendar: calendar_id {new_calendar_id!r} not found in CALENDAR section"
        )

    task_section.rows[row_index]["clndr_id"] = new_calendar_id
    task_section.mark_dirty(row_index)

    return {
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


@_register_handler("set_responsibility")
def _handle_set_responsibility(doc, change: dict, state: ChangeState) -> dict:
    """Assign a Responsibility (trade) activity code to an activity.

    Writes the activity-code chain: ACTVTYPE (the "Responsibility - Global"
    type) -> ACTVCODE (the trade value) -> TASKACTV (the per-activity
    assignment). Prefers the GLOBAL type and creates the code value there when
    missing, so we never create a project-scoped duplicate of a global code.
    Replaces any existing Responsibility assignment on the activity (one trade
    per activity).

    Required change keys:
        activity_id — task_code of the activity to code.
        code        — Responsibility short code (e.g. "ELEC").
    Optional:
        name        — code description (used only when creating a new code
                      value); defaults to the short code.
        code_type   — activity-code type name; defaults to
                      "Responsibility - Global".

    Requires the ACTVTYPE / ACTVCODE / TASKACTV sections to exist (they do in
    every schedule that uses activity codes). Raises if the schedule has no
    activity-code framework yet — add the code in P6 once, then this can drive
    the bulk assignment.
    """
    activity_id = change["activity_id"]
    code = change["code"]
    name = change.get("name") or code
    type_name = change.get("code_type") or "Responsibility - Global"

    task_section = doc.section("TASK")
    task_row = None
    if task_section is not None:
        for row in task_section.rows:
            if row.get("task_code") == activity_id:
                task_row = row
                break
        if task_row is None and activity_id in state.new_activity_id_map:
            tid = state.new_activity_id_map[activity_id]
            for row in task_section.rows:
                if row.get("task_id") == tid:
                    task_row = row
                    break
    if task_row is None:
        raise ValidationFailure(
            f"set_responsibility: activity_id {activity_id!r} not found in TASK section"
        )
    task_id = task_row["task_id"]
    proj_id = task_row.get("proj_id", "")

    actvtype = doc.section("ACTVTYPE")
    actvcode = doc.section("ACTVCODE")
    taskactv = doc.section("TASKACTV")
    for sec, nm in ((actvtype, "ACTVTYPE"), (actvcode, "ACTVCODE"), (taskactv, "TASKACTV")):
        if sec is None:
            raise ValidationFailure(
                f"set_responsibility: {nm} section not found — this schedule has no "
                "activity-code framework yet. Add the Responsibility - Global code "
                "in P6 once (and assign one activity), then re-run."
            )

    # 1) Resolve (or append) the Responsibility type row, preferring global scope.
    resp_types = [
        r for r in actvtype.rows
        if (r.get("actv_code_type", "") or "").strip().lower().startswith("responsib")
    ]
    resp_types.sort(key=lambda r: 0 if r.get("actv_code_type_scope") == "AS_Global" else 1)
    if resp_types:
        type_id = resp_types[0]["actv_code_type_id"]
    else:
        type_id = str(max((int(r["actv_code_type_id"]) for r in actvtype.rows), default=0) + 1)
        new_t = {f: "" for f in actvtype.field_order}
        new_t["actv_code_type_id"] = type_id
        new_t["actv_code_type"] = type_name
        new_t["actv_code_type_scope"] = "AS_Global"
        if "actv_short_len" in new_t:
            new_t["actv_short_len"] = "20"
        if "seq_num" in new_t:
            new_t["seq_num"] = str(len(actvtype.rows) + 1)
        actvtype.append_row(new_t)

    # 2) Resolve (or append) the trade code value under that type.
    code_u = code.strip().upper()
    code_id = None
    for r in actvcode.rows:
        if (r.get("actv_code_type_id") == type_id
                and (r.get("short_name", "") or "").strip().upper() == code_u):
            code_id = r["actv_code_id"]
            break
    created_code = False
    if code_id is None:
        code_id = str(max((int(r["actv_code_id"]) for r in actvcode.rows), default=0) + 1)
        new_c = {f: "" for f in actvcode.field_order}
        new_c["actv_code_id"] = code_id
        new_c["actv_code_type_id"] = type_id
        new_c["short_name"] = code
        new_c["actv_code_name"] = name
        if "seq_num" in new_c:
            same = sum(1 for r in actvcode.rows if r.get("actv_code_type_id") == type_id)
            new_c["seq_num"] = str(same + 1)
        actvcode.append_row(new_c)
        created_code = True

    # 3) Replace any existing Responsibility assignment on this activity, then add.
    replaced = False
    dup_idxs = [
        i for i, r in enumerate(taskactv.rows)
        if r.get("task_id") == task_id and r.get("actv_code_type_id") == type_id
    ]
    for i in reversed(dup_idxs):
        taskactv.rows.pop(i)
        if taskactv.raw_lines is not None and i < len(taskactv.raw_lines):
            taskactv.raw_lines.pop(i)
        taskactv._dirty = {d - 1 if d > i else d for d in taskactv._dirty if d != i}
        replaced = True
    new_a = {f: "" for f in taskactv.field_order}
    new_a["task_id"] = task_id
    new_a["actv_code_type_id"] = type_id
    new_a["actv_code_id"] = code_id
    if "proj_id" in new_a:
        new_a["proj_id"] = proj_id
    taskactv.append_row(new_a)

    return {
        "activity_id": activity_id,
        "code": code,
        "code_name": name,
        "actv_code_type_id": type_id,
        "actv_code_id": code_id,
        "created_code_value": created_code,
        "replaced_existing": replaced,
    }


@_register_handler("apply_anchor_absorption")
def _handle_apply_anchor_absorption(doc, change: dict, state: ChangeState) -> dict:
    """Re-invoke the anchor-absorption-suggestion logic and lower the chosen
    suggestion to a set_duration change.

    Required change keys:
        anchor_slip      — one entry from get_anchor_conflicts; must contain
                           'task_id' and 'slip_days'.
        suggestion_index — non-negative int index into the regenerated
                           suggestion list.

    Lowering: picks suggestions[suggestion_index], computes
        new_duration = current_duration_days - suggested_max_cut_days
    and delegates to _handle_set_duration with a synthetic change record.

    Validations (all raise ValidationFailure):
      1. Required sections TASK, TASKPRED, CALENDAR, PROJECT must all exist.
      2. anchor_slip must contain 'task_id'.
      3. anchor_slip must contain 'slip_days'.
      4. suggestion_index must be a non-negative int.
      5. suggest_anchor_absorption must return a non-empty list.
      6. suggestion_index must be in range of the suggestion list.
      7. suggestion kind must be 'duration_cut' (future-proofing: explicit
         rejection of unknown kinds so v2 kinds don't silently do the wrong
         thing here).
      8. new_duration_days (current - cut) must be >= 1 (a 0-day work task
         is nonsensical; set_duration allows 0 but we gate it here).
    """
    anchor_slip = change.get("anchor_slip", {})
    suggestion_index = change.get("suggestion_index")

    # Validation 1: required sections
    for section_name in ("TASK", "TASKPRED", "CALENDAR", "PROJECT"):
        if doc.section(section_name) is None:
            raise ValidationFailure(
                f"apply_anchor_absorption: {section_name} section not found in XER document"
            )

    # Validation 2-3: anchor_slip shape
    if "task_id" not in anchor_slip:
        raise ValidationFailure(
            "apply_anchor_absorption: anchor_slip must contain 'task_id'"
        )
    if "slip_days" not in anchor_slip:
        raise ValidationFailure(
            "apply_anchor_absorption: anchor_slip must contain 'slip_days'"
        )

    # Validation 4: suggestion_index must be a non-negative int
    if not isinstance(suggestion_index, int) or suggestion_index < 0:
        raise ValidationFailure(
            f"apply_anchor_absorption: suggestion_index must be a non-negative int, "
            f"got {suggestion_index!r}"
        )

    # Run CPM to get results needed by suggest_anchor_absorption.
    # The memory note says schedule_forward_backward mutates TASK dicts; we
    # read only the suggestion metadata (task_code, durations) so mutation is
    # acceptable here — the dict values are string fields CPM only writes
    # float/datetime computed fields back onto, not the duration fields we need.
    task_rows = doc.section("TASK").rows
    pred_rows = doc.section("TASKPRED").rows
    cal_rows = doc.section("CALENDAR").rows
    project_row = doc.section("PROJECT").rows[0]
    data_date = (
        project_row.get("last_recalc_date")
        or project_row.get("plan_start_date")
    )

    results, _meta = _cpm.schedule_forward_backward(
        task_rows, pred_rows, cal_rows, data_date
    )

    suggestions = _cpm.suggest_anchor_absorption(results, pred_rows, anchor_slip)

    # Validation 5: non-empty suggestion list
    if not suggestions:
        raise ValidationFailure(
            "apply_anchor_absorption: no absorption suggestions available for the "
            "given anchor_slip (anchor task may have no driving critical predecessors "
            "with reducible durations)"
        )

    # Validation 6: suggestion_index in range
    if suggestion_index >= len(suggestions):
        raise ValidationFailure(
            f"apply_anchor_absorption: suggestion_index {suggestion_index} is out of "
            f"range — {len(suggestions)} suggestion(s) available "
            f"(valid indices: 0–{len(suggestions) - 1})"
        )

    suggestion = suggestions[suggestion_index]

    # Validation 7: kind must be 'duration_cut'
    kind = suggestion.get("kind")
    if kind != "duration_cut":
        raise ValidationFailure(
            f"apply_anchor_absorption: suggestion kind {kind!r} is not supported — "
            f"only 'duration_cut' is handled in this version"
        )

    # Compute the lowered duration
    new_duration_days = (
        suggestion["current_duration_days"] - suggestion["suggested_max_cut_days"]
    )

    # Validation 8: new_duration must be >= 1 (guard against over-aggressive cuts)
    if new_duration_days < 1:
        raise ValidationFailure(
            f"apply_anchor_absorption: lowered duration would be {new_duration_days} days "
            f"(current={suggestion['current_duration_days']}d, "
            f"cut={suggestion['suggested_max_cut_days']}d) — minimum is 1 day"
        )

    # Lower to a set_duration change and delegate to the existing handler
    lowered_change = {
        "type": "set_duration",
        "activity_id": suggestion["task_code"],
        "new_duration_days": new_duration_days,
    }
    set_duration_feedback = _handle_set_duration(doc, lowered_change, state)

    return {
        "suggestion_chosen": suggestion,
        "total_suggestions": len(suggestions),
        "lowered_changes_count": 1,
        "set_duration_feedback": set_duration_feedback,
        "activity_end_before": None,
        "activity_end_after": None,
        "milestone_impact_days": None,
        "now_on_critical_path": None,
    }


# ---- public API: create_from_template ---------------------------------------


def create_from_template(template_path: str, metadata: dict):
    """Load the skeleton XER and stamp it with project metadata.

    metadata keys (all optional except project_name + project_id):
        project_name        -> PROJECT.proj_short_name
        project_id          -> PROJECT.proj_id AND every proj_id field across
                               all sections (referential consistency)
        planned_start       -> PROJECT.plan_start_date (date string "YYYY-MM-DD"
                               or "YYYY-MM-DD HH:MM"; normalize to "... 08:00"
                               if no time component)
        planned_data_date   -> PROJECT.last_recalc_date
        task_code_prefix    -> PROJECT.task_code_prefix (optional)

    Returns the mutated XerDoc. Caller (MCP wrapper) writes it via xer_io.write
    and extracts NTP/SC milestone task_ids by task_code lookup.

    Raises:
        ValidationFailure: if project_name or project_id is missing from metadata.
        FileNotFoundError / ValueError: propagated from parse_for_writing if the
            template path is invalid or the file is malformed.
    """
    from xer_io import parse_for_writing  # noqa: PLC0415

    # Validate required metadata fields before touching the file.
    project_name = metadata.get("project_name")
    project_id = metadata.get("project_id")

    if not project_name:
        raise ValidationFailure(
            "create_from_template: metadata must include 'project_name'"
        )
    if not project_id:
        raise ValidationFailure(
            "create_from_template: metadata must include 'project_id'"
        )

    # Parse the template — propagate file/format errors to the caller.
    doc = parse_for_writing(template_path)

    # P6 datetime fields require "YYYY-MM-DD HH:MM".  A bare "YYYY-MM-DD" is an
    # unsupported datetime format that crashes Primavera P6 on import (Event
    # Code AVAA0-1866-2) and is rejected by SmartPM ("Unsupported datetime
    # format").  Normalize every date the template stamps — historically only
    # planned_start was normalized, so planned_data_date shipped bare into
    # PROJECT.last_recalc_date and broke both importers.
    def _normalize_xer_datetime(value):
        if value is not None and len(value.strip()) == 10:
            return value.strip() + " 08:00"
        return value

    planned_start = _normalize_xer_datetime(metadata.get("planned_start"))
    planned_data_date = _normalize_xer_datetime(metadata.get("planned_data_date"))
    task_code_prefix = metadata.get("task_code_prefix")

    # P6's proj_id is the INTEGER primary key of the PROJECT table (P6 reassigns
    # it on import).  The human-readable project code (e.g. "HHRETAIL") is P6's
    # "Project ID" and belongs in proj_short_name; the long project name belongs
    # on the root WBS node's wbs_name.  Putting a non-numeric code into proj_id
    # crashes Primavera P6 on import (AVAA0-1866-2) and is rejected by SmartPM
    # ("For input string: ..." -> Java parseLong failure), because both parse
    # proj_id as an integer.  Confirmed against 204 real Westland exports: every
    # proj_id is numeric; proj_short_name carries the code; root wbs_name the
    # long name.  Mirror that mapping here.
    code = str(project_id).strip()
    if code.lstrip("-").isdigit():
        numeric_proj_id = code
    else:
        import hashlib  # noqa: PLC0415
        # Deterministic 6-digit surrogate key so regenerating the same project
        # yields a stable proj_id (P6 reassigns it on import regardless).
        digest = hashlib.md5(code.encode("utf-8")).hexdigest()
        numeric_proj_id = str(int(digest[:6], 16) % 900000 + 100000)

    # Stamp the PROJECT row.
    project_section = doc.section("PROJECT")
    if project_section is not None and project_section.rows:
        proj_row = project_section.rows[0]
        proj_row["proj_id"] = numeric_proj_id
        proj_row["proj_short_name"] = code
        if planned_start is not None:
            proj_row["plan_start_date"] = planned_start
        if planned_data_date is not None:
            proj_row["last_recalc_date"] = planned_data_date
        if task_code_prefix is not None:
            proj_row["task_code_prefix"] = task_code_prefix
        project_section.mark_dirty(0)

    # Put the long project name on the root WBS node (P6 shows it as the project
    # name); the short code on its wbs_short_name, mirroring real exports.
    projwbs_section = doc.section("PROJWBS")
    if projwbs_section is not None:
        for i, row in enumerate(projwbs_section.rows):
            if row.get("proj_node_flag") == "Y":
                row["wbs_name"] = project_name
                row["wbs_short_name"] = code
                projwbs_section.mark_dirty(i)
                break

    # Propagate the NUMERIC proj_id to every row in every section that carries
    # the field (referential consistency).  Also propagate pred_proj_id.
    for section in doc.sections:
        for i, row in enumerate(section.rows):
            mutated = False
            if "proj_id" in row:
                row["proj_id"] = numeric_proj_id
                mutated = True
            if "pred_proj_id" in row:
                row["pred_proj_id"] = numeric_proj_id
                mutated = True
            if mutated:
                section.mark_dirty(i)

    return doc


# ---- public API: fix_duplicate_ids ------------------------------------------


def _split_numeric_suffix(code: str) -> tuple[str, int | None]:
    """Split 'A1010' -> ('A', 1010); 'DEMO' -> ('DEMO', None).

    The trailing numeric part is a maximal run of decimal digits at the end of
    the string.  If there are no trailing digits the suffix is None and the
    prefix is the whole string.
    """
    m = re.search(r"^(.*?)(\d+)$", code)
    if m:
        return m.group(1), int(m.group(2))
    return code, None


def _next_unused_numeric_code(prefix: str, used_codes: set[str]) -> str:
    """Return the lowest unused code with the given prefix and a numeric suffix.

    Policy (P6 task_code_step = 10):
        1. Collect all existing numeric suffixes for this prefix in used_codes.
        2. Start at max(existing_suffixes) + 10 (or 10 if none).
        3. Increment by 10 until we find a code not in used_codes.

    This mirrors P6's own auto-numbering convention.
    """
    existing_suffixes = []
    for code in used_codes:
        p, n = _split_numeric_suffix(code)
        if p == prefix and n is not None:
            existing_suffixes.append(n)

    candidate_suffix = (max(existing_suffixes) + 10) if existing_suffixes else 10
    while True:
        candidate = f"{prefix}{candidate_suffix}"
        if candidate not in used_codes:
            return candidate
        candidate_suffix += 10


def _next_unused_non_numeric_code(base: str, used_codes: set[str]) -> str:
    """Return 'base-DUP1', 'base-DUP2', ... until an unused code is found."""
    n = 1
    while True:
        candidate = f"{base}-DUP{n}"
        if candidate not in used_codes:
            return candidate
        n += 1


def _compute_rename(original_code: str, used_codes: set[str]) -> str:
    """Compute the new code for a duplicate, following the renumber policy.

    - Numeric-suffix codes: _next_unused_numeric_code
    - Non-numeric codes: _next_unused_non_numeric_code
    """
    prefix, suffix = _split_numeric_suffix(original_code)
    if suffix is not None:
        return _next_unused_numeric_code(prefix, used_codes)
    return _next_unused_non_numeric_code(original_code, used_codes)


def _detect_duplicate_groups(task_rows: list[dict]) -> dict[str, list[int]]:
    """Return a mapping code -> [row_indices] for groups with > 1 row.

    Row indices are in original list order (stable).
    """
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(task_rows):
        code = row.get("task_code", "")
        groups.setdefault(code, []).append(i)
    return {code: indices for code, indices in groups.items() if len(indices) > 1}


def fix_duplicate_ids(doc, strategy: str = "renumber") -> tuple[object, dict]:
    """Detect and resolve duplicate task_code values in the TASK table.

    Strategies
    ----------
    renumber (default)
        For each duplicate group (same task_code), keep the FIRST occurrence
        and rename the rest to an unused task_code.  The task_id is unchanged
        (logic edges reference task_id, so they are unaffected by a code rename).
        Renaming policy:
          - Numeric-suffix codes (e.g., "A1010"): find the next unused code
            at prefix + (max_existing_suffix + 10), incrementing by 10 until
            an unused slot is found.
          - Non-numeric codes (e.g., "DEMO"): append "-DUP1", "-DUP2", ...
        A live "used codes" set prevents the generated code from colliding with
        any other existing code or with codes assigned earlier in this same run.

    report_only
        Run duplicate detection and compute proposed new codes using the same
        renumber policy.  DO NOT mutate any rows.  Return the mapping of what
        WOULD change (each entry's new_id is the proposed code).

    merge_consolidate
        For TRUE duplicates (same task_code AND same target_drtn_hr_cnt AND same
        wbs_id — likely an XER-export bug that double-emitted a row), keep the
        FIRST row, DELETE the rest, and reroute every TASKPRED edge that
        referenced a deleted row's task_id to the kept row's task_id.
        Self-loops and duplicate edges created by rerouting are dropped.
        Groups where rows differ on duration or WBS are placed in 'unresolved'
        with an explanatory reason and left untouched.

    Parameters
    ----------
    doc : XerDoc
        Parsed XER document (from xer_io.parse_for_writing).
    strategy : str
        One of "renumber", "report_only", "merge_consolidate".

    Returns
    -------
    (XerDoc, dict)
        The (possibly mutated) doc and a result dict:
        {
            "duplicates_found": int,
            "mapping":    [{"original_id", "new_id", "task_name", "reason"}, ...],
            "unresolved": [{"original_id", "reason"}, ...]
        }

    Raises
    ------
    ValidationFailure
        If strategy is unknown, or if no TASK section exists in the document.
    """
    _valid_strategies = {"renumber", "report_only", "merge_consolidate"}
    if strategy not in _valid_strategies:
        raise ValidationFailure(
            f"fix_duplicate_ids: unknown strategy {strategy!r} — "
            f"must be one of {sorted(_valid_strategies)}"
        )

    task_section = doc.section("TASK")
    if task_section is None:
        raise ValidationFailure(
            "fix_duplicate_ids: no TASK section found in the XER document"
        )

    dup_groups = _detect_duplicate_groups(task_section.rows)

    empty_result: dict = {"duplicates_found": 0, "mapping": [], "unresolved": []}
    if not dup_groups:
        return doc, empty_result

    if strategy == "report_only":
        return _fix_report_only(doc, task_section, dup_groups)

    if strategy == "renumber":
        return _fix_renumber(doc, task_section, dup_groups)

    # strategy == "merge_consolidate"
    return _fix_merge_consolidate(doc, task_section, dup_groups)


def _fix_report_only(
    doc,
    task_section,
    dup_groups: dict[str, list[int]],
) -> tuple[object, dict]:
    """report_only: compute proposed renames without mutating the doc."""
    # Build the live used-codes set from the full TASK table (read-only snapshot).
    used_codes: set[str] = {r.get("task_code", "") for r in task_section.rows}

    mapping = []
    duplicates_found = 0

    for code, indices in dup_groups.items():
        # Keep indices[0]; propose renames for indices[1:]
        for idx in indices[1:]:
            row = task_section.rows[idx]
            proposed_new = _compute_rename(code, used_codes)
            # Reserve the proposed code so later iterations don't collide with it
            used_codes.add(proposed_new)
            mapping.append({
                "original_id": code,
                "new_id": proposed_new,
                "task_name": row.get("task_name", ""),
                "reason": f"renumbered duplicate of task_code {code!r}",
            })
            duplicates_found += 1

    return doc, {
        "duplicates_found": duplicates_found,
        "mapping": mapping,
        "unresolved": [],
    }


def _fix_renumber(
    doc,
    task_section,
    dup_groups: dict[str, list[int]],
) -> tuple[object, dict]:
    """renumber: rename all duplicate occurrences (2nd, 3rd, …) in-place."""
    # Live used-codes set includes ALL codes currently in the TASK table.
    # This prevents a renamed code from colliding with any existing code,
    # including codes generated by earlier iterations of this loop.
    used_codes: set[str] = {r.get("task_code", "") for r in task_section.rows}

    mapping = []
    duplicates_found = 0

    for code, indices in dup_groups.items():
        # Keep indices[0] unchanged; rename indices[1:]
        for idx in indices[1:]:
            row = task_section.rows[idx]
            new_code = _compute_rename(code, used_codes)
            used_codes.add(new_code)  # reserve immediately

            # Mutate the row in-place
            row["task_code"] = new_code
            task_section.mark_dirty(idx)

            mapping.append({
                "original_id": code,
                "new_id": new_code,
                "task_name": row.get("task_name", ""),
                "reason": f"renumbered duplicate of task_code {code!r}",
            })
            duplicates_found += 1

    return doc, {
        "duplicates_found": duplicates_found,
        "mapping": mapping,
        "unresolved": [],
    }


def _fix_merge_consolidate(
    doc,
    task_section,
    dup_groups: dict[str, list[int]],
) -> tuple[object, dict]:
    """merge_consolidate: delete true-duplicate rows and reroute TASKPRED edges.

    True duplicate: same task_code AND same target_drtn_hr_cnt AND same wbs_id.
    Groups that split on those fields go to unresolved (untouched).
    """
    taskpred = doc.section("TASKPRED")

    mapping = []
    unresolved = []
    duplicates_found = 0

    # Collect indices to delete across all groups (for reverse-sorted batch removal)
    task_indices_to_delete: list[int] = []
    # Map deleted task_id -> kept task_id (for TASKPRED rerouting)
    reroute_map: dict[str, str] = {}

    for code, indices in dup_groups.items():
        rows_in_group = [task_section.rows[i] for i in indices]

        # Sub-group by (target_drtn_hr_cnt, wbs_id)
        def _sub_key(r):
            return (r.get("target_drtn_hr_cnt", ""), r.get("wbs_id", ""))
        first_key = _sub_key(rows_in_group[0])
        all_same = all(_sub_key(r) == first_key for r in rows_in_group)

        if not all_same:
            unresolved.append({
                "original_id": code,
                "reason": (
                    f"code {code!r} has rows with differing duration/WBS; "
                    "manual review needed"
                ),
            })
            continue

        # True duplicates — keep indices[0], delete indices[1:]
        kept_row = task_section.rows[indices[0]]
        kept_task_id = kept_row.get("task_id", "")

        for idx in indices[1:]:
            deleted_row = task_section.rows[idx]
            deleted_task_id = deleted_row.get("task_id", "")
            task_indices_to_delete.append(idx)
            reroute_map[deleted_task_id] = kept_task_id
            mapping.append({
                "original_id": code,
                "new_id": code,  # code does not change; the row is removed
                "task_name": deleted_row.get("task_name", ""),
                "reason": (
                    f"merged into task_id {kept_task_id} "
                    f"(identical duration+WBS)"
                ),
            })
            duplicates_found += 1

    # --- Reroute TASKPRED edges before removing rows (indices are still valid) -
    if taskpred is not None and reroute_map:
        edges_to_drop: list[int] = []  # self-loops or exact duplicates after reroute

        # Build a set of (pred_task_id, task_id) pairs for post-reroute dup check
        # We start with the existing non-rerouted edges.
        existing_pairs: set[tuple[str, str, str]] = set()

        # First pass: apply the reroute mapping speculatively to every edge,
        # flagging self-loops (drop) and post-reroute duplicates (drop).
        for i, row in enumerate(taskpred.rows):
            p = row.get("pred_task_id", "")
            s = row.get("task_id", "")
            t = row.get("pred_type", "")
            # Apply reroute to see what these will become
            final_p = reroute_map.get(p, p)
            final_s = reroute_map.get(s, s)
            # Self-loop after reroute?
            if final_p == final_s:
                edges_to_drop.append(i)
                continue
            triple = (final_p, final_s, t)
            if triple in existing_pairs:
                edges_to_drop.append(i)
            else:
                existing_pairs.add(triple)

        # Second pass: apply rerouting mutations (only on rows not being dropped)
        drop_set = set(edges_to_drop)
        for i, row in enumerate(taskpred.rows):
            if i in drop_set:
                continue
            p = row.get("pred_task_id", "")
            s = row.get("task_id", "")
            new_p = reroute_map.get(p, p)
            new_s = reroute_map.get(s, s)
            if new_p != p or new_s != s:
                row["pred_task_id"] = new_p
                row["task_id"] = new_s
                taskpred.mark_dirty(i)

        # Remove dropped edges in reverse order
        for i in sorted(drop_set, reverse=True):
            taskpred.rows.pop(i)
            if taskpred.raw_lines is not None and i < len(taskpred.raw_lines):
                taskpred.raw_lines.pop(i)

        # Re-index _dirty for TASKPRED
        removed_set = drop_set
        new_dirty: set[int] = set()
        for d in taskpred._dirty:
            if d in removed_set:
                continue
            shift = sum(1 for r in removed_set if r < d)
            new_dirty.add(d - shift)
        taskpred._dirty = new_dirty

    # --- Remove deleted TASK rows in reverse order ----------------------------
    for idx in sorted(task_indices_to_delete, reverse=True):
        task_section.rows.pop(idx)
        if task_section.raw_lines is not None and idx < len(task_section.raw_lines):
            task_section.raw_lines.pop(idx)

    # Re-index _dirty for TASK
    removed_task_set = set(task_indices_to_delete)
    new_task_dirty: set[int] = set()
    for d in task_section._dirty:
        if d in removed_task_set:
            continue
        shift = sum(1 for r in removed_task_set if r < d)
        new_task_dirty.add(d - shift)
    task_section._dirty = new_task_dirty

    return doc, {
        "duplicates_found": duplicates_found,
        "mapping": mapping,
        "unresolved": unresolved,
    }
