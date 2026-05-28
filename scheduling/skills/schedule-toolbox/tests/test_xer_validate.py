"""Tests for the file-integrity validation engine."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

FIXTURES = (
    Path(__file__).parent.parent.parent.parent / "mcp-server" / "tests" / "fixtures"
)

from xer_validate import ValidationIssue, ValidationReport  # noqa: E402
from xer_io import XerDoc, XerSection  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(sections: dict) -> XerDoc:
    """Build a minimal XerDoc from a dict of {table_name: [row_dict, ...]}."""
    sec_list = []
    for name, rows in sections.items():
        fields = list(rows[0].keys()) if rows else []
        sec_list.append(XerSection(
            name=name,
            field_order=fields,
            rows=[dict(r) for r in rows],
            raw_lines=None,
            e_line=None,
        ))
    return XerDoc(header_line="ERMHDR\t24.12", encoding="cp1252", sections=sec_list)


def _make_task(task_id, task_code="A1000", task_type="TT_Task",
               status_code="TK_NotStart", clndr_id="100",
               wbs_id="1000", target_drtn="8", remain_drtn="8",
               **extra):
    base = dict(
        task_id=task_id,
        proj_id="1",
        wbs_id=wbs_id,
        clndr_id=clndr_id,
        task_code=task_code,
        task_name=f"Task {task_id}",
        task_type=task_type,
        status_code=status_code,
        target_drtn_hr_cnt=target_drtn,
        remain_drtn_hr_cnt=remain_drtn,
        act_start_date="",
        act_end_date="",
        target_start_date="2026-05-25 08:00",
        target_end_date="2026-05-26 17:00",
        early_start_date="",
        early_end_date="",
        late_start_date="",
        late_end_date="",
        restart_date="",
        reend_date="",
        rem_late_start_date="",
        rem_late_end_date="",
        expect_end_date="",
        cstr_date="",
        cstr_date2="",
        suspend_date="",
        resume_date="",
    )
    base.update(extra)
    return base


def _make_pred(task_pred_id, pred_task_id, task_id, pred_type="PR_FS"):
    return dict(
        task_pred_id=task_pred_id,
        task_id=task_id,
        pred_task_id=pred_task_id,
        proj_id="1",
        pred_proj_id="1",
        pred_type=pred_type,
        lag_hr_cnt="0",
    )


def _make_cal(clndr_id="100"):
    return dict(clndr_id=clndr_id, default_flag="Y", clndr_name="Standard",
                proj_id="1")


def _make_wbs(wbs_id, parent_wbs_id="", short="WBS", proj_node="N"):
    return dict(wbs_id=wbs_id, proj_id="1", proj_node_flag=proj_node,
                parent_wbs_id=parent_wbs_id, wbs_short_name=short,
                wbs_name=f"WBS {wbs_id}")


def _make_project(proj_id="1", last_recalc_date="2026-05-25 08:00"):
    return dict(proj_id=proj_id, last_recalc_date=last_recalc_date,
                proj_short_name="TEST")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Duplicate checks (C1)
# ---------------------------------------------------------------------------

class TestDuplicateActivityIds(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.dup = parse_for_writing(str(FIXTURES / "duplicate_ids.xer"))

    def test_detects_duplicate_activity_id(self):
        from xer_validate import validate
        report = validate(self.dup)
        codes = [i.code for i in report.issues]
        self.assertIn("DUPLICATE_ACTIVITY_ID", codes)
        self.assertFalse(report.import_ready)


# ---------------------------------------------------------------------------
# Dangling refs (C1)
# ---------------------------------------------------------------------------

class TestDanglingRefs(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.dangling = parse_for_writing(str(FIXTURES / "dangling_refs.xer"))

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


# ---------------------------------------------------------------------------
# Logic: circular + self-loop (C3 Group 1)
# ---------------------------------------------------------------------------

class TestCircularLogic(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.circ = parse_for_writing(str(FIXTURES / "circular_logic.xer"))

    def test_detects_cycle_in_fixture(self):
        from xer_validate import validate
        report = validate(self.circ)
        codes = [i.code for i in report.issues]
        self.assertIn("CIRCULAR_LOGIC", codes)
        self.assertFalse(report.import_ready)

    def test_cycle_affected_contains_cycle_nodes(self):
        from xer_validate import _check_circular_logic
        issues = _check_circular_logic(self.circ)
        self.assertTrue(len(issues) >= 1)
        affected = issues[0].affected
        self.assertTrue(len(affected) >= 2)

    def test_minimal_has_no_cycle(self):
        from xer_io import parse_for_writing
        from xer_validate import _check_circular_logic
        doc = parse_for_writing(str(FIXTURES / "minimal.xer"))
        issues = _check_circular_logic(doc)
        self.assertEqual(len(issues), 0)

    def test_two_node_cycle(self):
        from xer_validate import _check_circular_logic
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [
                _make_pred("901", "1", "2"),
                _make_pred("902", "2", "1"),  # back edge
            ],
        })
        issues = _check_circular_logic(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "CIRCULAR_LOGIC")


class TestSelfLoops(unittest.TestCase):
    def test_detects_self_loop(self):
        from xer_validate import _check_self_loops
        doc = _make_doc({
            "TASK": [_make_task("1")],
            "TASKPRED": [_make_pred("901", "1", "1")],  # self-loop
        })
        issues = _check_self_loops(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "SELF_LOOP")
        self.assertEqual(issues[0].severity, "error")

    def test_no_self_loop_in_minimal(self):
        from xer_io import parse_for_writing
        from xer_validate import _check_self_loops
        doc = parse_for_writing(str(FIXTURES / "minimal.xer"))
        self.assertEqual(_check_self_loops(doc), [])

    def test_normal_relationship_not_flagged(self):
        from xer_validate import _check_self_loops
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [_make_pred("901", "1", "2")],
        })
        self.assertEqual(_check_self_loops(doc), [])


# ---------------------------------------------------------------------------
# Integration: validate() orchestrator
# ---------------------------------------------------------------------------

class TestValidateOrchestrator(unittest.TestCase):
    def test_minimal_xer_is_import_ready(self):
        from xer_io import parse_for_writing
        from xer_validate import validate
        doc = parse_for_writing(str(FIXTURES / "minimal.xer"))
        report = validate(doc)
        self.assertTrue(report.import_ready,
                        f"minimal.xer expected import_ready but got errors: "
                        f"{[i for i in report.issues if i.severity == 'error']}")

    def test_circular_fixture_not_import_ready(self):
        from xer_io import parse_for_writing
        from xer_validate import validate
        doc = parse_for_writing(str(FIXTURES / "circular_logic.xer"))
        report = validate(doc)
        self.assertFalse(report.import_ready)
        codes = [i.code for i in report.issues]
        self.assertIn("CIRCULAR_LOGIC", codes)

    def test_validate_returns_report_instance(self):
        from xer_io import parse_for_writing
        from xer_validate import validate
        doc = parse_for_writing(str(FIXTURES / "minimal.xer"))
        report = validate(doc)
        self.assertIsInstance(report, ValidationReport)


if __name__ == "__main__":
    unittest.main()
