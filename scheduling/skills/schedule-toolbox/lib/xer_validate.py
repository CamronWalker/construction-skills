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
    for start in list(all_nodes):
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
    issues.extend(_check_invalid_relationship_types(doc))
    issues.extend(_check_invalid_status_codes(doc))
    # Network / Structure
    issues.extend(_check_orphan_activities(doc))
    issues.extend(_check_orphaned_wbs_branches(doc))
    issues.extend(_check_missing_or_multiple_project_rows(doc))
    # Status
    issues.extend(_check_status_date_mismatch(doc))
    issues.extend(_check_actual_after_data_date(doc))
    return ValidationReport(issues=issues)
