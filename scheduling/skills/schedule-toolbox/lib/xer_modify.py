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
