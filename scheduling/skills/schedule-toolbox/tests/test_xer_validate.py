"""Tests for the file-integrity validation engine."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_validate import ValidationIssue, ValidationReport  # noqa: E402


class TestDataModel(unittest.TestCase):
    def test_empty_report_is_import_ready(self):
        r = ValidationReport(issues=[])
        self.assertTrue(r.import_ready)
        self.assertEqual(r.summary, {"errors": 0, "warnings": 0, "info": 0})

    def test_report_with_error_is_not_import_ready(self):
        r = ValidationReport(issues=[
            ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_ACTIVITY_ID",
                message="dup",
                affected=["1", "2"],
            )
        ])
        self.assertFalse(r.import_ready)
        self.assertEqual(r.summary["errors"], 1)

    def test_report_with_only_warnings_is_import_ready(self):
        r = ValidationReport(issues=[
            ValidationIssue(
                severity="warning",
                category="Network",
                code="ORPHAN_ACTIVITY",
                message="orphan",
                affected=["3"],
            )
        ])
        self.assertTrue(r.import_ready)
        self.assertEqual(r.summary["warnings"], 1)


if __name__ == "__main__":
    unittest.main()
