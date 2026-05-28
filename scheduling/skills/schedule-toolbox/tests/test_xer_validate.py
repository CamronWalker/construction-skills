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


class TestDuplicateChecks(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.dup = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "duplicate_ids.xer"
        ))

    def test_detects_duplicate_activity_id(self):
        from xer_validate import validate
        report = validate(self.dup)
        codes = [i.code for i in report.issues]
        self.assertIn("DUPLICATE_ACTIVITY_ID", codes)
        self.assertFalse(report.import_ready)


class TestDanglingRefs(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.dangling = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "dangling_refs.xer"
        ))

    def test_detects_dangling_predecessor(self):
        from xer_validate import validate
        report = validate(self.dangling)
        codes = [i.code for i in report.issues]
        self.assertIn("DANGLING_PREDECESSOR", codes)

    def test_detects_dangling_calendar(self):
        from xer_validate import validate
        report = validate(self.dangling)
        codes = [i.code for i in report.issues]
        self.assertIn("DANGLING_CALENDAR", codes)


if __name__ == "__main__":
    unittest.main()
