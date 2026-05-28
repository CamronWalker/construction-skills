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
