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


@_register_handler("add_activity")
def _handle_add_activity(doc, change: dict, state: ChangeState) -> dict:
    spec = change.get("spec", {})

    # Validation 1: TASK section must exist
    task = doc.section("TASK")
    if task is None:
        raise ValidationFailure(
            "add_activity: TASK section not found in XER document"
        )

    # Validation 2: all required spec fields must be present
    required_fields = ("code", "name", "duration_days", "calendar_id", "wbs_id", "activity_type")
    missing = [f for f in required_fields if f not in spec]
    if missing:
        raise ValidationFailure(
            f"add_activity: missing required spec field(s): {', '.join(missing)}"
        )

    code = spec["code"]
    name = spec["name"]
    duration_days = spec["duration_days"]
    calendar_id = spec["calendar_id"]
    wbs_id = spec["wbs_id"]
    activity_type = spec["activity_type"]

    # Validation 3: task_code must be unique
    existing_codes = {r.get("task_code") for r in task.rows}
    if code in existing_codes or code in state.new_activity_ids:
        raise ValidationFailure(
            f"add_activity: task_code {code!r} already exists — duplicate activity codes are not allowed"
        )

    # Validation 4: wbs_id must exist in doc or state
    projwbs = doc.section("PROJWBS")
    wbs_in_doc = (
        projwbs is not None
        and any(r.get("wbs_id") == wbs_id for r in projwbs.rows)
    )
    if not wbs_in_doc and wbs_id not in state.new_wbs_ids:
        raise ValidationFailure(
            f"add_activity: wbs_id {wbs_id!r} not found in PROJWBS section"
        )

    # Validation 5: calendar_id must exist in doc or state
    calendar_section = doc.section("CALENDAR")
    cal_in_doc = (
        calendar_section is not None
        and any(r.get("clndr_id") == calendar_id for r in calendar_section.rows)
    )
    if not cal_in_doc and calendar_id not in state.new_calendar_ids:
        raise ValidationFailure(
            f"add_activity: calendar_id {calendar_id!r} not found in CALENDAR section"
        )

    # Validation 6: activity_type must be a known P6 enum
    if activity_type not in _ACTIVITY_TYPES:
        raise ValidationFailure(
            f"add_activity: unknown activity_type {activity_type!r} — "
            f"must be one of {sorted(_ACTIVITY_TYPES)}"
        )

    # Validation 7: duration_days must be >= 0
    if duration_days < 0:
        raise ValidationFailure(
            f"add_activity: duration_days must be >= 0, got {duration_days}"
        )

    # Build the new row
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

    # State tracking
    state.new_activity_ids.add(code)
    state.new_activity_id_map[code] = new_task_id

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
