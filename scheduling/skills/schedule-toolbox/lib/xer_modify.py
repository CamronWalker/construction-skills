"""Mutation engine for XerDoc.

One handler function per change type plus an orchestrator that runs the
3-pass validation and atomic write.

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

import re
from dataclasses import dataclass, field
from typing import Any

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
) -> ApplyResult:
    """3-pass atomic application of changes to doc.

    Pass 1: syntactic check (per-record required fields, enum validity).
    Pass 2: order-aware reference resolution (apply changes against an
            in-memory copy; track new IDs).
    Pass 3: post-state graph check (orphan rule, cycle check, dup-edge).

    On error: no mutation persisted, errors returned.
    On success (or dry_run): mutations applied to doc; ApplyResult populated.
    """
    result = ApplyResult(doc=None, changes_applied=0)

    # Pass 1: syntactic
    for i, change in enumerate(changes):
        ct = change.get("type")
        if ct not in _HANDLERS:
            raise ValidationFailure(f"Unknown change type at index {i}: {ct!r}")

    if not changes:
        result.doc = doc
        return result

    # Pass 2+3: deferred to D-N tasks
    state = ChangeState()
    for i, change in enumerate(changes):
        handler = _HANDLERS[change["type"]]
        feedback = handler(doc, change, state)
        result.per_change_feedback.append(PerChangeFeedback(
            change_index=i, type=change["type"], feedback=feedback,
        ))
        result.changes_applied += 1

    result.doc = doc
    return result


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
    # Forward-reference resolution (state.new_activity_ids) is D16's job.
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

    # Remove the row from rows (and raw_lines if present), then re-index _dirty
    taskpred.rows.pop(i)
    if taskpred.raw_lines is not None:
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

    new_row = {f: "" for f in task.field_order}
    new_row["task_id"] = new_task_id
    new_row["task_code"] = code
    new_row["task_name"] = name
    new_row["task_type"] = activity_type
    new_row["target_drtn_hr_cnt"] = hours_str
    new_row["remain_drtn_hr_cnt"] = hours_str
    new_row["clndr_id"] = calendar_id
    new_row["wbs_id"] = wbs_id
    new_row["proj_id"] = task.rows[0]["proj_id"] if task.rows else ""
    new_row["status_code"] = "TK_NotStart"
    new_row["duration_type"] = "DT_FixedDUR2"
    new_row["complete_pct_type"] = "CP_Drtn"
    new_row["phys_complete_pct"] = "0"

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
    if task.raw_lines is not None:
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
            if taskpred.raw_lines is not None:
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
    if task.raw_lines is not None:
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
            if taskpred.raw_lines is not None:
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
    if taskpred.raw_lines is not None:
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

    # Build the new row — blank all fields from field_order, then populate
    new_row = {f: "" for f in projwbs.field_order}
    new_row["wbs_id"] = new_wbs_id
    new_row["wbs_code"] = wbs_code
    new_row["wbs_name"] = wbs_name
    new_row["wbs_short_name"] = short_name
    new_row["parent_wbs_id"] = parent_wbs_id
    new_row["proj_id"] = projwbs.rows[0]["proj_id"] if projwbs.rows else ""
    new_row["status_code"] = "WS_Open"

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
    if projwbs.raw_lines is not None:
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
