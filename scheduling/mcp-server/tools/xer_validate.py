"""MCP wrapper for validate_xer_structure.

Thin adapter over xer_validate.validate. Pulls the rich XerDoc from the
cache (via get_for_writing) so we have access to header, field_order,
and raw_lines — not just the lossy dict. Returns the JSON shape from
the spec.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from xer_validate import validate  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402

_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/xer_validate.py"


def validate_xer_structure_impl(xer_path: str, cache) -> dict:
    """Run file-integrity validation against the XER at xer_path.

    Args:
        xer_path: Path to the .xer file.
        cache: CpmCache instance — used to get the parsed XerDoc.

    Returns:
        ``{import_ready: bool, issues: [{severity, category, code, message,
        affected}], summary: {errors, warnings, info}}``
    """
    doc = cache.get_for_writing(xer_path)
    report = validate(doc)
    return {
        "import_ready": report.import_ready,
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "code": i.code,
                "message": i.message,
                "affected": list(i.affected),
            }
            for i in report.issues
        ],
        "summary": report.summary,
    }


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    @wrap_tool_errors(tool_name="validate_xer_structure", lib_script=_LIB_SCRIPT)
    def validate_xer_structure(xer_path: str) -> dict:
        """Comprehensive file-integrity validation.

        Distinct from quality_checks (which scores schedule health). This tool
        answers "will P6/Procore import this file?"

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{import_ready: bool, issues: [{severity, category, code, message,
            affected}], summary: {errors, warnings, info}}``
        """
        return validate_xer_structure_impl(xer_path, cache)
