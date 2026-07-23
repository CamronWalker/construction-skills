"""File-integrity validation for XER documents.

Distinct from quality_checks (which scores schedule health). This module
answers "will P6/Procore import this file?" Issues are categorized; errors
block import_ready, warnings are advisory.

The same check engine is reused by xer_modify.apply_changes for post-state
validation — that's how a single change_index in the apply output can
carry an issue code from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Severity = Literal["error", "warning", "info"]


# P6-required NOT-NULL scalar columns that must be populated on every TASK /
# PROJWBS row.  Leaving any of these empty crashes Primavera P6 on import
# (Event Code AVAA0-1866-2) when it dereferences the empty bit-flag / enum /
# quantity decimal / OBS pointer.  Verified against a real, P6-importable
# Westland export (BTLP.xer): every one of these is populated on all 43 tasks
# and all 9 WBS nodes.  Deliberately EXCLUDES scheduler-output fields
# (total_float_hr_cnt, dates, driving_path_flag) which are legitimately empty
# on never-scheduled planning files.
REQUIRED_TASK_COLUMNS = (
    "phys_complete_pct",
    "rev_fdbk_flag",
    "est_wt",
    "lock_plan_flag",
    "auto_compute_act_flag",
    "complete_pct_type",
    "task_type",
    "duration_type",
    "status_code",
    "priority_type",
    "act_work_qty",
    "remain_work_qty",
    "target_work_qty",
    "act_equip_qty",
    "remain_equip_qty",
    "target_equip_qty",
    "act_this_per_work_qty",
    "act_this_per_equip_qty",
)

REQUIRED_WBS_COLUMNS = (
    "obs_id",
    "seq_num",
    "est_wt",
    "proj_node_flag",
    "sum_data_flag",
    "status_code",
)
# NOTE: ev_compute_type / ev_etc_compute_type are intentionally NOT required.
# An audit of 204 real, P6-importable Westland exports found 91 of them leave
# these two empty on some WBS nodes while populating others — i.e. P6 tolerates
# an empty EV-compute type, so requiring it would false-flag genuine exports.
# The add_wbs handler still stamps them for internal consistency, but their
# absence is not a crash trigger.


@dataclass(frozen=True)
class ValidationIssue:
    """One row in a ValidationReport.

    Attributes:
        severity: "error" blocks import_ready; "warning" is advisory.
        category: One of "Duplicates", "Dangling refs", "Logic", "Data",
            "Network", "Structure", "Status".
        code: Stable enum-like code (e.g., "DUPLICATE_ACTIVITY_ID").
        message: Human-readable description.
        affected: IDs of the affected entities (activity ids, wbs ids, etc.).
    """

    severity: Severity
    category: str
    code: str
    message: str
    affected: list[str]


@dataclass
class ValidationReport:
    """Output of xer_validate.validate(doc). Aggregates issues + import_ready
    flag + summary counts."""

    issues: list[ValidationIssue]

    @property
    def import_ready(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def summary(self) -> dict[str, int]:
        s = {"errors": 0, "warnings": 0, "info": 0}
        for i in self.issues:
            if i.severity == "error":
                s["errors"] += 1
            elif i.severity == "warning":
                s["warnings"] += 1
            else:
                s["info"] += 1
        return s


def _check_duplicate_activity_ids(doc) -> list[ValidationIssue]:
    task = doc.section("TASK")
    if task is None:
        return []
    issues = []
    seen: dict[str, list[str]] = {}
    for row in task.rows:
        code = row.get("task_code", "")
        seen.setdefault(code, []).append(row.get("task_id", ""))
    for code, ids in seen.items():
        if len(ids) > 1:
            issues.append(ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_ACTIVITY_ID",
                message=f"Activity code {code!r} appears in {len(ids)} rows "
                        f"(task_ids {', '.join(ids)})",
                affected=ids,
            ))
    return issues


def _check_dangling_predecessors(doc) -> list[ValidationIssue]:
    task = doc.section("TASK")
    pred = doc.section("TASKPRED")
    if task is None or pred is None:
        return []
    valid_ids = {r.get("task_id") for r in task.rows}
    issues = []
    for r in pred.rows:
        pid = r.get("pred_task_id")
        sid = r.get("task_id")
        if pid not in valid_ids:
            issues.append(ValidationIssue(
                severity="error",
                category="Dangling refs",
                code="DANGLING_PREDECESSOR",
                message=f"TASKPRED row references non-existent pred_task_id {pid!r}",
                affected=[pid],
            ))
        if sid not in valid_ids:
            issues.append(ValidationIssue(
                severity="error",
                category="Dangling refs",
                code="DANGLING_SUCCESSOR",
                message=f"TASKPRED row references non-existent task_id {sid!r}",
                affected=[sid],
            ))
    return issues


def _check_dangling_calendars(doc) -> list[ValidationIssue]:
    task = doc.section("TASK")
    cal = doc.section("CALENDAR")
    if task is None:
        return []
    valid_ids = {r.get("clndr_id") for r in cal.rows} if cal is not None else set()
    issues = []
    for r in task.rows:
        cid = r.get("clndr_id")
        if cid and cid not in valid_ids:
            issues.append(ValidationIssue(
                severity="error",
                category="Dangling refs",
                code="DANGLING_CALENDAR",
                message=f"Task {r.get('task_id')!r} references non-existent "
                        f"clndr_id {cid!r}",
                affected=[r.get("task_id", "")],
            ))
    return issues


def _check_circular_logic(doc) -> list[ValidationIssue]:
    """DFS cycle detection on the TASKPRED graph.

    Builds a predecessor->successor adjacency map, then runs an iterative
    three-color (white/gray/black) DFS.  Using an explicit call-stack avoids
    Python's recursion limit on large schedules (real projects can have
    predecessor chains longer than 1 000 activities).  Each detected cycle is
    reported once with the cycle path as ``affected``.
    """
    pred_sec = doc.section("TASKPRED")
    task_sec = doc.section("TASK")
    if pred_sec is None or task_sec is None:
        return []

    # Build adjacency: node -> list of successors
    adj: dict[str, list[str]] = {}
    for r in pred_sec.rows:
        p = r.get("pred_task_id", "")
        s = r.get("task_id", "")
        if p and s and p != s:
            adj.setdefault(p, []).append(s)

    all_nodes = {r.get("task_id", "") for r in task_sec.rows}

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in all_nodes}
    issues: list[ValidationIssue] = []
    reported_cycles: set[frozenset] = set()

    # Iterative DFS using an explicit frame stack.
    # Each frame is (node, iterator-over-neighbours, path-snapshot-length).
    # We maintain a path list in parallel to detect back-edges.
    # Sort the start-node order so the reported cycle path is deterministic —
    # downstream diff logic in xer_modify keys on the issue message, and a
    # stable cycle reported from a different start node would otherwise
    # appear as a "new" issue between pre- and post-state.
    for start in sorted(all_nodes):
        if color.get(start, WHITE) != WHITE:
            continue

        path: list[str] = []
        # Stack entries: (node, neighbour_iterator)
        # On first visit push with a fresh iterator; on re-entry continue it.
        call_stack: list[tuple[str, object]] = [(start, iter(adj.get(start, [])))]
        color[start] = GRAY
        path.append(start)

        while call_stack:
            node, nbr_iter = call_stack[-1]
            try:
                nbr = next(nbr_iter)
            except StopIteration:
                # All neighbours visited — node is done.
                color[node] = BLACK
                path.pop()
                call_stack.pop()
                continue

            c = color.get(nbr, WHITE)
            if c == GRAY:
                # Back-edge: nbr is on the current path — cycle found.
                idx = path.index(nbr)
                cycle = path[idx:]
                key = frozenset(cycle)
                if key not in reported_cycles:
                    reported_cycles.add(key)
                    cycle_str = " -> ".join(cycle + [nbr])
                    issues.append(ValidationIssue(
                        severity="error",
                        category="Logic",
                        code="CIRCULAR_LOGIC",
                        message=f"Circular relationship detected: {cycle_str}",
                        affected=list(cycle),
                    ))
            elif c == WHITE:
                color[nbr] = GRAY
                path.append(nbr)
                call_stack.append((nbr, iter(adj.get(nbr, []))))

    return issues


def _check_self_loops(doc) -> list[ValidationIssue]:
    """TASKPRED rows where pred_task_id == task_id."""
    pred_sec = doc.section("TASKPRED")
    if pred_sec is None:
        return []
    issues = []
    for r in pred_sec.rows:
        tid = r.get("task_id", "")
        pid = r.get("pred_task_id", "")
        if tid and tid == pid:
            issues.append(ValidationIssue(
                severity="error",
                category="Logic",
                code="SELF_LOOP",
                message=f"Task {tid!r} has a relationship to itself",
                affected=[tid],
            ))
    return issues


def _check_duplicate_relationships(doc) -> list[ValidationIssue]:
    """TASKPRED rows with identical (pred_task_id, task_id, pred_type) tuples."""
    pred_sec = doc.section("TASKPRED")
    if pred_sec is None:
        return []
    seen: dict[tuple, list[str]] = {}
    for r in pred_sec.rows:
        key = (r.get("pred_task_id", ""), r.get("task_id", ""), r.get("pred_type", ""))
        seen.setdefault(key, []).append(r.get("task_pred_id", ""))
    issues = []
    for (pid, sid, ptype), ids in seen.items():
        if len(ids) > 1:
            issues.append(ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_RELATIONSHIP",
                message=(
                    f"Relationship {pid!r} -> {sid!r} ({ptype}) appears "
                    f"{len(ids)} times (task_pred_ids {', '.join(ids)})"
                ),
                affected=ids,
            ))
    return issues


def _check_duplicate_calendar_ids(doc) -> list[ValidationIssue]:
    """CALENDAR rows with identical clndr_id."""
    cal = doc.section("CALENDAR")
    if cal is None:
        return []
    seen: dict[str, int] = {}
    for r in cal.rows:
        cid = r.get("clndr_id", "")
        seen[cid] = seen.get(cid, 0) + 1
    issues = []
    for cid, count in seen.items():
        if count > 1:
            issues.append(ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_CALENDAR_ID",
                message=f"Calendar id {cid!r} appears {count} times",
                affected=[cid],
            ))
    return issues


def _check_duplicate_wbs_codes(doc) -> list[ValidationIssue]:
    """PROJWBS rows with identical (parent_wbs_id, wbs_short_name) pairs."""
    wbs = doc.section("PROJWBS")
    if wbs is None:
        return []
    seen: dict[tuple, list[str]] = {}
    for r in wbs.rows:
        key = (r.get("parent_wbs_id", ""), r.get("wbs_short_name", ""))
        seen.setdefault(key, []).append(r.get("wbs_id", ""))
    issues = []
    for (parent, short), ids in seen.items():
        if len(ids) > 1:
            issues.append(ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_WBS_CODE",
                message=(
                    f"WBS short name {short!r} under parent {parent!r} "
                    f"appears {len(ids)} times (wbs_ids {', '.join(ids)})"
                ),
                affected=ids,
            ))
    return issues


def _check_negative_durations(doc) -> list[ValidationIssue]:
    """TASK rows where target_drtn_hr_cnt or remain_drtn_hr_cnt < 0."""
    task = doc.section("TASK")
    if task is None:
        return []
    issues = []
    for r in task.rows:
        tid = r.get("task_id", "")
        for field in ("target_drtn_hr_cnt", "remain_drtn_hr_cnt"):
            val = r.get(field, "")
            if not val:
                continue
            try:
                if float(val) < 0:
                    issues.append(ValidationIssue(
                        severity="error",
                        category="Data",
                        code="NEGATIVE_DURATION",
                        message=f"Task {tid!r} has {field}={val!r} (negative)",
                        affected=[tid],
                    ))
            except ValueError:
                pass  # non-numeric caught by invalid-date / data check elsewhere
    return issues


_DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d")

_DATE_FIELDS = (
    "act_start_date", "act_end_date",
    "target_start_date", "target_end_date",
    "early_start_date", "early_end_date",
    "late_start_date", "late_end_date",
    "restart_date", "reend_date",
    "rem_late_start_date", "rem_late_end_date",
    "expect_end_date",
    "cstr_date", "cstr_date2",
    "suspend_date", "resume_date",
    "create_date", "update_date",
)


def _parse_xer_date(value: str):
    """Return a datetime if ``value`` looks like a date, else None.
    Raises ValueError if non-empty but unparseable.
    """
    from datetime import datetime
    v = value.strip()
    if not v:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unrecognised date format: {v!r}")


def _check_invalid_dates(doc) -> list[ValidationIssue]:
    """TASK rows with non-empty date fields that don't match YYYY-MM-DD HH:MM."""
    task = doc.section("TASK")
    if task is None:
        return []
    issues = []
    for r in task.rows:
        tid = r.get("task_id", "")
        for field in _DATE_FIELDS:
            val = r.get(field, "")
            if not val:
                continue
            try:
                _parse_xer_date(val)
            except ValueError:
                issues.append(ValidationIssue(
                    severity="error",
                    category="Data",
                    code="INVALID_DATE",
                    message=f"Task {tid!r} has unparseable {field}={val!r}",
                    affected=[tid],
                ))
    return issues


_PROJECT_DATE_FIELDS = (
    "plan_start_date", "plan_end_date", "scd_end_date",
    "last_recalc_date", "last_schedule_date", "fcst_start_date",
    "last_tasksum_date", "add_date", "sum_refresh_date",
)


def _check_bare_datetimes(doc) -> list[ValidationIssue]:
    """Flag datetime fields that carry a bare 'YYYY-MM-DD' with no time.

    P6 datetime columns require 'YYYY-MM-DD HH:MM'.  A bare date is an
    unsupported datetime format: Primavera P6 access-violates on import
    (Event Code AVAA0-1866-2) and SmartPM rejects the file outright
    ("Unknown exception parsing file [Unsupported datetime format: ...]").
    Audited against 204 real Westland exports — zero use a bare date — so this
    never false-flags a genuine export.  This is separate from _check_invalid_dates,
    which accepts the bare form; here a bare datetime is explicitly an error.
    """
    import re as _re
    bare = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
    issues: list[ValidationIssue] = []

    proj = doc.section("PROJECT")
    if proj is not None:
        for r in proj.rows:
            for field in _PROJECT_DATE_FIELDS:
                val = (r.get(field, "") or "").strip()
                if val and bare.match(val):
                    issues.append(ValidationIssue(
                        severity="error",
                        category="Data",
                        code="MALFORMED_DATETIME",
                        message=(
                            f"PROJECT.{field}={val!r} is a bare date with no time; "
                            f"P6/SmartPM require 'YYYY-MM-DD HH:MM'"
                        ),
                        affected=[r.get("proj_id", "")],
                    ))

    task = doc.section("TASK")
    if task is not None:
        for r in task.rows:
            tid = r.get("task_id", "")
            for field in _DATE_FIELDS:
                val = (r.get(field, "") or "").strip()
                if val and bare.match(val):
                    issues.append(ValidationIssue(
                        severity="error",
                        category="Data",
                        code="MALFORMED_DATETIME",
                        message=(
                            f"Task {tid!r} {field}={val!r} is a bare date with no time; "
                            f"P6/SmartPM require 'YYYY-MM-DD HH:MM'"
                        ),
                        affected=[tid],
                    ))
    return issues


# Integer key / foreign-key columns per table.  P6 (and SmartPM's Java parser)
# read these as integers; a non-numeric value crashes P6 on import
# (AVAA0-1866-2) and makes SmartPM throw NumberFormatException ("For input
# string: ..."). Audited against 204 real Westland exports: every one of these
# is numeric wherever it is non-empty.  Optional FKs (parent_wbs_id on the root,
# base_clndr_id on a base calendar, proj_id on a global activity-code type) are
# legitimately empty — only NON-EMPTY values are checked.
_INTEGER_ID_COLUMNS = {
    "PROJECT": ("proj_id",),
    "PROJWBS": ("wbs_id", "parent_wbs_id", "obs_id", "proj_id"),
    "TASK": ("task_id", "wbs_id", "clndr_id", "proj_id"),
    "CALENDAR": ("clndr_id", "base_clndr_id", "proj_id"),
    "TASKPRED": ("task_pred_id", "task_id", "pred_task_id", "proj_id", "pred_proj_id"),
    "OBS": ("obs_id",),
    "SCHEDOPTIONS": ("proj_id",),
    "ACTVTYPE": ("actv_code_type_id", "proj_id"),
    "ACTVCODE": ("actv_code_id", "actv_code_type_id"),
    "TASKACTV": ("task_id", "actv_code_type_id", "actv_code_id", "proj_id"),
}


def _check_non_numeric_ids(doc) -> list[ValidationIssue]:
    """Flag integer key/FK columns that carry a non-numeric value.

    P6's proj_id / wbs_id / task_id / clndr_id / obs_id are integer primary and
    foreign keys.  A non-numeric value (e.g. proj_id='HHRETAIL') crashes
    Primavera P6 on import (AVAA0-1866-2, a null-deref after the integer key
    fails to bind) and makes SmartPM reject the file with a Java
    NumberFormatException.  Verified against 204 real exports — every value in
    these columns is numeric where present.
    """
    import re as _re
    numeric = _re.compile(r"^-?\d+$")
    issues: list[ValidationIssue] = []
    for sec_name, cols in _INTEGER_ID_COLUMNS.items():
        sec = doc.section(sec_name)
        if sec is None:
            continue
        for r in sec.rows:
            for col in cols:
                val = (r.get(col, "") or "").strip()
                if val and not numeric.match(val):
                    issues.append(ValidationIssue(
                        severity="error",
                        category="Data",
                        code="NON_NUMERIC_ID",
                        message=(
                            f"{sec_name}.{col}={val!r} must be an integer; P6/SmartPM "
                            f"parse this as a numeric key (non-numeric crashes import)"
                        ),
                        affected=[val],
                    ))
    return issues


_VALID_REL_TYPES = {"PR_FS", "PR_SS", "PR_FF", "PR_SF"}


def _check_invalid_relationship_types(doc) -> list[ValidationIssue]:
    """TASKPRED rows with pred_type not in the four standard P6 types."""
    pred_sec = doc.section("TASKPRED")
    if pred_sec is None:
        return []
    issues = []
    for r in pred_sec.rows:
        ptype = r.get("pred_type", "")
        if ptype not in _VALID_REL_TYPES:
            rid = r.get("task_pred_id", "")
            issues.append(ValidationIssue(
                severity="error",
                category="Data",
                code="INVALID_RELATIONSHIP_TYPE",
                message=(
                    f"TASKPRED {rid!r} has unrecognised pred_type={ptype!r}"
                ),
                affected=[rid],
            ))
    return issues


_VALID_STATUS_CODES = {"TK_NotStart", "TK_Active", "TK_Complete"}


def _check_invalid_status_codes(doc) -> list[ValidationIssue]:
    """TASK rows with status_code not in the three standard P6 values."""
    task = doc.section("TASK")
    if task is None:
        return []
    issues = []
    for r in task.rows:
        sc = r.get("status_code", "")
        if sc not in _VALID_STATUS_CODES:
            tid = r.get("task_id", "")
            issues.append(ValidationIssue(
                severity="error",
                category="Data",
                code="INVALID_STATUS_CODE",
                message=f"Task {tid!r} has unrecognised status_code={sc!r}",
                affected=[tid],
            ))
    return issues


def _check_orphan_activities(doc) -> list[ValidationIssue]:
    """TASK rows with no predecessor or successor edges.

    Excludes WBS summary tasks (TT_WBS), LOE tasks (TT_LOE), and the
    project-start milestone (TT_Mile with no edges is acceptable as a
    project-open activity).  Everything else with zero edges is flagged
    as a warning — it may still import fine, but it's almost certainly a
    logic gap.
    """
    task = doc.section("TASK")
    pred_sec = doc.section("TASKPRED")
    if task is None:
        return []

    skip_types = {"TT_WBS", "TT_LOE"}
    connected: set[str] = set()
    if pred_sec is not None:
        for r in pred_sec.rows:
            connected.add(r.get("task_id", ""))
            connected.add(r.get("pred_task_id", ""))

    issues = []
    for r in task.rows:
        tid = r.get("task_id", "")
        ttype = r.get("task_type", "")
        if ttype in skip_types:
            continue
        if tid not in connected:
            issues.append(ValidationIssue(
                severity="warning",
                category="Network",
                code="ORPHAN_ACTIVITY",
                message=(
                    f"Task {tid!r} ({r.get('task_code','')}) has no "
                    f"predecessor or successor relationships"
                ),
                affected=[tid],
            ))
    return issues


def _check_orphaned_wbs_branches(doc) -> list[ValidationIssue]:
    """PROJWBS nodes that have no child WBS rows and no tasks assigned.

    The project root (proj_node_flag == 'Y') is excluded — a root with no
    children is valid for a trivial project.
    """
    wbs = doc.section("PROJWBS")
    task = doc.section("TASK")
    if wbs is None:
        return []

    # Collect WBS ids that are parents of other WBS rows
    has_children: set[str] = set()
    for r in wbs.rows:
        parent = r.get("parent_wbs_id", "")
        if parent:
            has_children.add(parent)

    # Collect WBS ids that have tasks
    has_tasks: set[str] = set()
    if task is not None:
        for r in task.rows:
            wid = r.get("wbs_id", "")
            if wid:
                has_tasks.add(wid)

    issues = []
    for r in wbs.rows:
        wid = r.get("wbs_id", "")
        # Skip the project root node
        if r.get("proj_node_flag", "N") == "Y":
            continue
        if wid not in has_children and wid not in has_tasks:
            issues.append(ValidationIssue(
                severity="warning",
                category="Structure",
                code="ORPHANED_WBS_BRANCH",
                message=(
                    f"WBS node {wid!r} ({r.get('wbs_short_name','')}) "
                    f"has no child WBS rows and no tasks"
                ),
                affected=[wid],
            ))
    return issues


def _check_missing_or_multiple_project_rows(doc) -> list[ValidationIssue]:
    """Zero PROJECT rows -> error; more than one -> warning."""
    proj = doc.section("PROJECT")
    issues = []
    if proj is None or len(proj.rows) == 0:
        issues.append(ValidationIssue(
            severity="error",
            category="Structure",
            code="MISSING_PROJECT_ROW",
            message="No PROJECT row found in the XER — file cannot be imported",
            affected=[],
        ))
    elif len(proj.rows) > 1:
        ids = [r.get("proj_id", "") for r in proj.rows]
        issues.append(ValidationIssue(
            severity="warning",
            category="Structure",
            code="MULTIPLE_PROJECT_ROWS",
            message=(
                f"XER contains {len(proj.rows)} PROJECT rows "
                f"(proj_ids {', '.join(ids)}); only one is expected"
            ),
            affected=ids,
        ))
    return issues


def _check_status_date_mismatch(doc) -> list[ValidationIssue]:
    """TK_Complete tasks with no act_end_date."""
    task = doc.section("TASK")
    if task is None:
        return []
    issues = []
    for r in task.rows:
        if r.get("status_code", "") == "TK_Complete" and not r.get("act_end_date", "").strip():
            tid = r.get("task_id", "")
            issues.append(ValidationIssue(
                severity="warning",
                category="Status",
                code="STATUS_DATE_MISMATCH",
                message=(
                    f"Task {tid!r} has status_code='TK_Complete' but no act_end_date"
                ),
                affected=[tid],
            ))
    return issues


def _check_actual_after_data_date(doc) -> list[ValidationIssue]:
    """Actual dates (act_start_date, act_end_date) after the PROJECT data date."""
    proj = doc.section("PROJECT")
    task = doc.section("TASK")
    if proj is None or task is None or not proj.rows:
        return []

    dd_raw = proj.rows[0].get("last_recalc_date", "").strip()
    if not dd_raw:
        return []
    try:
        data_date = _parse_xer_date(dd_raw)
    except ValueError:
        return []

    issues = []
    for r in task.rows:
        tid = r.get("task_id", "")
        for field in ("act_start_date", "act_end_date"):
            val = r.get(field, "").strip()
            if not val:
                continue
            try:
                dt = _parse_xer_date(val)
            except ValueError:
                continue  # will be caught by _check_invalid_dates
            if dt and data_date and dt > data_date:
                issues.append(ValidationIssue(
                    severity="warning",
                    category="Status",
                    code="ACTUAL_AFTER_DATA_DATE",
                    message=(
                        f"Task {tid!r} has {field}={val!r} which is after "
                        f"the data date {dd_raw!r}"
                    ),
                    affected=[tid],
                ))
    return issues


_INCOMPLETE_ROW_SPECS = (
    ("TASK", REQUIRED_TASK_COLUMNS, "task_id", "task_code", "INCOMPLETE_TASK_ROW"),
    ("PROJWBS", REQUIRED_WBS_COLUMNS, "wbs_id", "wbs_short_name", "INCOMPLETE_WBS_ROW"),
)


def _check_incomplete_required_columns(doc) -> list[ValidationIssue]:
    """Flag TASK / PROJWBS rows that leave P6-required NOT-NULL columns empty.

    Root cause of the AVAA0-1866-2 import crash: the proposal-schedule
    add-handlers emitted rows with only a subset of columns populated, leaving
    bit-flags / enums / quantity decimals / the OBS pointer / EV settings blank.
    P6 access-violates on import when it dereferences these.  A genuine P6
    export populates them on every row.

    To avoid false positives on legitimately sparse exports, a column is treated
    as required only when at least one row in the same section DOES populate it —
    i.e. the file is internally inconsistent ("half-built"), which is the
    signature of the generator bug and does not occur in a real P6 export.
    """
    issues: list[ValidationIssue] = []
    for sec_name, req_cols, id_field, label_field, code in _INCOMPLETE_ROW_SPECS:
        sec = doc.section(sec_name)
        if sec is None or not sec.rows:
            continue
        present = set(sec.field_order)
        # Only require a column that exists AND that some row actually fills.
        expected = [
            c for c in req_cols
            if c in present and any(str(r.get(c, "")).strip() for r in sec.rows)
        ]
        if not expected:
            continue
        for r in sec.rows:
            empties = [c for c in expected if not str(r.get(c, "")).strip()]
            if empties:
                rid = r.get(id_field, "")
                issues.append(ValidationIssue(
                    severity="error",
                    category="Data",
                    code=code,
                    message=(
                        f"{sec_name} row {rid!r} ({r.get(label_field, '')}) is missing "
                        f"P6-required column(s) that sibling rows populate: "
                        f"{', '.join(empties)}"
                    ),
                    affected=[rid],
                ))
    return issues


def validate(doc) -> ValidationReport:
    """Run all file-integrity checks. Returns a ValidationReport with
    all detected issues. import_ready = no error-severity issues.
    """
    issues: list[ValidationIssue] = []
    # Dangling refs
    issues.extend(_check_dangling_predecessors(doc))
    issues.extend(_check_dangling_calendars(doc))
    # Duplicates
    issues.extend(_check_duplicate_activity_ids(doc))
    issues.extend(_check_duplicate_relationships(doc))
    issues.extend(_check_duplicate_calendar_ids(doc))
    issues.extend(_check_duplicate_wbs_codes(doc))
    # Logic
    issues.extend(_check_circular_logic(doc))
    issues.extend(_check_self_loops(doc))
    # Data
    issues.extend(_check_negative_durations(doc))
    issues.extend(_check_invalid_dates(doc))
    issues.extend(_check_bare_datetimes(doc))
    issues.extend(_check_non_numeric_ids(doc))
    issues.extend(_check_invalid_relationship_types(doc))
    issues.extend(_check_invalid_status_codes(doc))
    # Network / Structure
    issues.extend(_check_orphan_activities(doc))
    issues.extend(_check_orphaned_wbs_branches(doc))
    issues.extend(_check_missing_or_multiple_project_rows(doc))
    # Status
    issues.extend(_check_status_date_mismatch(doc))
    issues.extend(_check_actual_after_data_date(doc))
    # Completeness — empty P6-required columns crash P6 on import (AVAA0-1866-2)
    issues.extend(_check_incomplete_required_columns(doc))
    return ValidationReport(issues=issues)
