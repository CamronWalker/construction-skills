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

    Builds a predecessor->successor adjacency map, then runs a three-color
    (white/gray/black) DFS.  Each detected cycle is reported once with the
    cycle path as ``affected``.
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
    stack_path: list[str] = []
    issues: list[ValidationIssue] = []
    reported_cycles: set[frozenset] = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        stack_path.append(node)
        for nbr in adj.get(node, []):
            if color.get(nbr, WHITE) == GRAY:
                # Found a back-edge: extract cycle from stack
                idx = stack_path.index(nbr)
                cycle = stack_path[idx:]
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
            elif color.get(nbr, WHITE) == WHITE:
                dfs(nbr)
        stack_path.pop()
        color[node] = BLACK

    for node in list(all_nodes):
        if color.get(node, WHITE) == WHITE:
            dfs(node)

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
    # Logic
    issues.extend(_check_circular_logic(doc))
    issues.extend(_check_self_loops(doc))
    return ValidationReport(issues=issues)
