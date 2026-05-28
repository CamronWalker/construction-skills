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
# Duplicate checks C3 Group 2
# ---------------------------------------------------------------------------

class TestDuplicateRelationships(unittest.TestCase):
    def test_detects_duplicate_relationship(self):
        from xer_validate import _check_duplicate_relationships
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [
                _make_pred("9001", "1", "2"),
                _make_pred("9002", "1", "2"),  # same pair + type
            ],
        })
        issues = _check_duplicate_relationships(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "DUPLICATE_RELATIONSHIP")
        self.assertEqual(issues[0].severity, "error")

    def test_different_type_not_duplicate(self):
        from xer_validate import _check_duplicate_relationships
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [
                _make_pred("9001", "1", "2", pred_type="PR_FS"),
                _make_pred("9002", "1", "2", pred_type="PR_SS"),
            ],
        })
        issues = _check_duplicate_relationships(doc)
        self.assertEqual(len(issues), 0)

    def test_no_taskpred_section(self):
        from xer_validate import _check_duplicate_relationships
        doc = _make_doc({"TASK": [_make_task("1")]})
        self.assertEqual(_check_duplicate_relationships(doc), [])


class TestDuplicateCalendarIds(unittest.TestCase):
    def test_detects_duplicate_calendar(self):
        from xer_validate import _check_duplicate_calendar_ids
        doc = _make_doc({
            "CALENDAR": [_make_cal("100"), _make_cal("100")],
        })
        issues = _check_duplicate_calendar_ids(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "DUPLICATE_CALENDAR_ID")

    def test_unique_calendars_ok(self):
        from xer_validate import _check_duplicate_calendar_ids
        doc = _make_doc({"CALENDAR": [_make_cal("100"), _make_cal("200")]})
        self.assertEqual(_check_duplicate_calendar_ids(doc), [])


class TestDuplicateWbsCodes(unittest.TestCase):
    def test_detects_same_short_name_same_parent(self):
        from xer_validate import _check_duplicate_wbs_codes
        doc = _make_doc({
            "PROJWBS": [
                _make_wbs("1000", proj_node="Y"),
                _make_wbs("2001", "1000", "STRUCT"),
                _make_wbs("2002", "1000", "STRUCT"),  # dup
            ],
        })
        issues = _check_duplicate_wbs_codes(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "DUPLICATE_WBS_CODE")

    def test_same_short_name_different_parent_ok(self):
        from xer_validate import _check_duplicate_wbs_codes
        doc = _make_doc({
            "PROJWBS": [
                _make_wbs("1000", proj_node="Y"),
                _make_wbs("2001", "1000", "STRUCT"),
                _make_wbs("2002", "9999", "STRUCT"),  # different parent
            ],
        })
        self.assertEqual(_check_duplicate_wbs_codes(doc), [])


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

    def test_deep_linear_chain_no_recursion_error(self):
        """A chain of 2 000 activities must not raise RecursionError.

        Python's default recursion limit is 1 000 frames; a naive recursive
        DFS would crash on any schedule whose critical path is longer than
        ~900 activities — common on large commercial projects.
        """
        from xer_validate import _check_circular_logic
        n = 2000
        tasks = [_make_task(str(i), task_code=f"A{i:04d}") for i in range(n)]
        preds = [
            _make_pred(str(i), str(i), str(i + 1))
            for i in range(n - 1)
        ]
        doc = _make_doc({"TASK": tasks, "TASKPRED": preds})
        issues = _check_circular_logic(doc)
        self.assertEqual(issues, [], "Linear chain should have no cycles")


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
# Data category (C3 Group 3)
# ---------------------------------------------------------------------------

class TestNegativeDurations(unittest.TestCase):
    def test_detects_negative_target_duration(self):
        from xer_validate import _check_negative_durations
        doc = _make_doc({"TASK": [_make_task("1", target_drtn="-8")]})
        issues = _check_negative_durations(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "NEGATIVE_DURATION")

    def test_detects_negative_remain_duration(self):
        from xer_validate import _check_negative_durations
        doc = _make_doc({"TASK": [_make_task("1", remain_drtn="-1")]})
        issues = _check_negative_durations(doc)
        self.assertEqual(len(issues), 1)

    def test_zero_duration_ok(self):
        from xer_validate import _check_negative_durations
        doc = _make_doc({"TASK": [_make_task("1", target_drtn="0")]})
        self.assertEqual(_check_negative_durations(doc), [])

    def test_empty_duration_skipped(self):
        from xer_validate import _check_negative_durations
        doc = _make_doc({"TASK": [_make_task("1", target_drtn="")]})
        self.assertEqual(_check_negative_durations(doc), [])


class TestInvalidDates(unittest.TestCase):
    def test_detects_bad_date_format(self):
        from xer_validate import _check_invalid_dates
        t = _make_task("1")
        t["act_start_date"] = "25/05/2026"  # wrong format
        doc = _make_doc({"TASK": [t]})
        issues = _check_invalid_dates(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "INVALID_DATE")

    def test_valid_datetime_ok(self):
        from xer_validate import _check_invalid_dates
        t = _make_task("1")
        t["act_start_date"] = "2026-05-25 08:00"
        doc = _make_doc({"TASK": [t]})
        self.assertEqual(_check_invalid_dates(doc), [])

    def test_valid_date_only_ok(self):
        from xer_validate import _check_invalid_dates
        t = _make_task("1")
        t["act_start_date"] = "2026-05-25"
        doc = _make_doc({"TASK": [t]})
        self.assertEqual(_check_invalid_dates(doc), [])

    def test_empty_date_skipped(self):
        from xer_validate import _check_invalid_dates
        doc = _make_doc({"TASK": [_make_task("1")]})
        self.assertEqual(_check_invalid_dates(doc), [])


class TestInvalidRelationshipTypes(unittest.TestCase):
    def test_detects_invalid_type(self):
        from xer_validate import _check_invalid_relationship_types
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [_make_pred("901", "1", "2", pred_type="PR_XY")],
        })
        issues = _check_invalid_relationship_types(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "INVALID_RELATIONSHIP_TYPE")

    def test_all_valid_types(self):
        from xer_validate import _check_invalid_relationship_types
        rows = []
        for i, ptype in enumerate(["PR_FS", "PR_SS", "PR_FF", "PR_SF"]):
            rows.append(_make_pred(str(900 + i), str(i), str(i + 10), pred_type=ptype))
        tasks = [_make_task(str(j), task_code=f"A{j}") for j in list(range(4)) + list(range(10, 14))]
        doc = _make_doc({"TASK": tasks, "TASKPRED": rows})
        self.assertEqual(_check_invalid_relationship_types(doc), [])


class TestInvalidStatusCodes(unittest.TestCase):
    def test_detects_invalid_status(self):
        from xer_validate import _check_invalid_status_codes
        doc = _make_doc({"TASK": [_make_task("1", status_code="TK_Unknown")]})
        issues = _check_invalid_status_codes(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "INVALID_STATUS_CODE")

    def test_valid_status_codes(self):
        from xer_validate import _check_invalid_status_codes
        tasks = [
            _make_task("1", status_code="TK_NotStart"),
            _make_task("2", task_code="A2000", status_code="TK_Active"),
            _make_task("3", task_code="A3000", status_code="TK_Complete"),
        ]
        doc = _make_doc({"TASK": tasks})
        self.assertEqual(_check_invalid_status_codes(doc), [])


# ---------------------------------------------------------------------------
# Network + Structure (C3 Group 4)
# ---------------------------------------------------------------------------

class TestOrphanActivities(unittest.TestCase):
    def test_detects_activity_with_no_edges(self):
        from xer_validate import _check_orphan_activities
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [],  # no relationships at all
        })
        issues = _check_orphan_activities(doc)
        codes = [i.code for i in issues]
        self.assertTrue(all(c == "ORPHAN_ACTIVITY" for c in codes))
        self.assertTrue(len(issues) >= 1)

    def test_wbs_summary_excluded(self):
        from xer_validate import _check_orphan_activities
        doc = _make_doc({
            "TASK": [_make_task("1", task_type="TT_WBS")],
            "TASKPRED": [],
        })
        self.assertEqual(_check_orphan_activities(doc), [])

    def test_loe_excluded(self):
        from xer_validate import _check_orphan_activities
        doc = _make_doc({
            "TASK": [_make_task("1", task_type="TT_LOE")],
            "TASKPRED": [],
        })
        self.assertEqual(_check_orphan_activities(doc), [])

    def test_connected_activity_not_flagged(self):
        from xer_validate import _check_orphan_activities
        doc = _make_doc({
            "TASK": [_make_task("1"), _make_task("2", task_code="A2000")],
            "TASKPRED": [_make_pred("901", "1", "2")],
        })
        issues = _check_orphan_activities(doc)
        self.assertEqual(len(issues), 0)

    def test_orphan_activity_is_warning(self):
        from xer_validate import _check_orphan_activities
        doc = _make_doc({
            "TASK": [_make_task("1")],
            "TASKPRED": [],
        })
        issues = _check_orphan_activities(doc)
        if issues:
            self.assertEqual(issues[0].severity, "warning")


class TestOrphanedWbsBranches(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.orphan_doc = parse_for_writing(str(FIXTURES / "orphan_branch.xer"))

    def test_detects_orphaned_wbs_in_fixture(self):
        from xer_validate import validate
        report = validate(self.orphan_doc)
        codes = [i.code for i in report.issues]
        self.assertIn("ORPHANED_WBS_BRANCH", codes)

    def test_orphaned_wbs_is_warning(self):
        from xer_validate import _check_orphaned_wbs_branches
        doc = _make_doc({
            "PROJWBS": [
                _make_wbs("1000", proj_node="Y"),
                _make_wbs("9001", "1000", "ORPHAN"),
            ],
            "TASK": [],
        })
        issues = _check_orphaned_wbs_branches(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "ORPHANED_WBS_BRANCH")
        self.assertEqual(issues[0].severity, "warning")

    def test_root_not_flagged(self):
        from xer_validate import _check_orphaned_wbs_branches
        doc = _make_doc({
            "PROJWBS": [_make_wbs("1000", proj_node="Y")],
            "TASK": [],
        })
        self.assertEqual(_check_orphaned_wbs_branches(doc), [])

    def test_wbs_with_task_not_flagged(self):
        from xer_validate import _check_orphaned_wbs_branches
        doc = _make_doc({
            "PROJWBS": [
                _make_wbs("1000", proj_node="Y"),
                _make_wbs("2001", "1000", "STRUCT"),
            ],
            "TASK": [_make_task("1", wbs_id="2001")],
        })
        self.assertEqual(_check_orphaned_wbs_branches(doc), [])

    def test_wbs_with_children_not_flagged(self):
        from xer_validate import _check_orphaned_wbs_branches
        doc = _make_doc({
            "PROJWBS": [
                _make_wbs("1000", proj_node="Y"),
                _make_wbs("2001", "1000", "PARENT"),
                _make_wbs("3001", "2001", "CHILD"),
            ],
            "TASK": [],
        })
        issues = _check_orphaned_wbs_branches(doc)
        affected = [i.affected[0] for i in issues]
        self.assertIn("3001", affected)
        self.assertNotIn("2001", affected)


class TestMissingMultipleProjectRows(unittest.TestCase):
    def test_missing_project_section_errors(self):
        from xer_validate import _check_missing_or_multiple_project_rows
        doc = _make_doc({"TASK": [_make_task("1")]})
        issues = _check_missing_or_multiple_project_rows(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "MISSING_PROJECT_ROW")
        self.assertEqual(issues[0].severity, "error")

    def test_empty_project_section_errors(self):
        from xer_validate import _check_missing_or_multiple_project_rows
        doc = _make_doc({"PROJECT": []})
        issues = _check_missing_or_multiple_project_rows(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "MISSING_PROJECT_ROW")

    def test_multiple_project_rows_warns(self):
        from xer_validate import _check_missing_or_multiple_project_rows
        doc = _make_doc({
            "PROJECT": [_make_project("1"), _make_project("2")],
        })
        issues = _check_missing_or_multiple_project_rows(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "MULTIPLE_PROJECT_ROWS")
        self.assertEqual(issues[0].severity, "warning")

    def test_single_project_ok(self):
        from xer_validate import _check_missing_or_multiple_project_rows
        doc = _make_doc({"PROJECT": [_make_project()]})
        self.assertEqual(_check_missing_or_multiple_project_rows(doc), [])


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

    def test_orphan_branch_fixture_import_ready_with_warning(self):
        from xer_io import parse_for_writing
        from xer_validate import validate
        doc = parse_for_writing(str(FIXTURES / "orphan_branch.xer"))
        report = validate(doc)
        # Orphan WBS is a warning, not an error
        self.assertTrue(report.import_ready,
                        f"orphan_branch.xer should be import_ready but errors: "
                        f"{[i for i in report.issues if i.severity == 'error']}")
        codes = [i.code for i in report.issues]
        self.assertIn("ORPHANED_WBS_BRANCH", codes)

    def test_validate_returns_report_instance(self):
        from xer_io import parse_for_writing
        from xer_validate import validate
        doc = parse_for_writing(str(FIXTURES / "minimal.xer"))
        report = validate(doc)
        self.assertIsInstance(report, ValidationReport)


# ---------------------------------------------------------------------------
# Status (C3 Group 5)
# ---------------------------------------------------------------------------

class TestStatusDateMismatch(unittest.TestCase):
    def test_complete_without_act_end_date(self):
        from xer_validate import _check_status_date_mismatch
        t = _make_task("1", status_code="TK_Complete")
        t["act_end_date"] = ""
        doc = _make_doc({"TASK": [t]})
        issues = _check_status_date_mismatch(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "STATUS_DATE_MISMATCH")
        self.assertEqual(issues[0].severity, "warning")

    def test_complete_with_act_end_date_ok(self):
        from xer_validate import _check_status_date_mismatch
        t = _make_task("1", status_code="TK_Complete")
        t["act_end_date"] = "2026-05-20 17:00"
        doc = _make_doc({"TASK": [t]})
        self.assertEqual(_check_status_date_mismatch(doc), [])

    def test_not_started_empty_end_ok(self):
        from xer_validate import _check_status_date_mismatch
        doc = _make_doc({"TASK": [_make_task("1", status_code="TK_NotStart")]})
        self.assertEqual(_check_status_date_mismatch(doc), [])


class TestActualAfterDataDate(unittest.TestCase):
    def test_act_start_after_data_date(self):
        from xer_validate import _check_actual_after_data_date
        t = _make_task("1", status_code="TK_Active")
        t["act_start_date"] = "2026-05-30 08:00"  # after data date 2026-05-25
        doc = _make_doc({
            "PROJECT": [_make_project(last_recalc_date="2026-05-25 08:00")],
            "TASK": [t],
        })
        issues = _check_actual_after_data_date(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "ACTUAL_AFTER_DATA_DATE")
        self.assertEqual(issues[0].severity, "warning")

    def test_act_end_after_data_date(self):
        from xer_validate import _check_actual_after_data_date
        t = _make_task("1", status_code="TK_Complete")
        t["act_start_date"] = "2026-05-20 08:00"
        t["act_end_date"] = "2026-05-28 17:00"  # after data date
        doc = _make_doc({
            "PROJECT": [_make_project(last_recalc_date="2026-05-25 08:00")],
            "TASK": [t],
        })
        issues = _check_actual_after_data_date(doc)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "ACTUAL_AFTER_DATA_DATE")

    def test_act_on_data_date_ok(self):
        from xer_validate import _check_actual_after_data_date
        t = _make_task("1", status_code="TK_Active")
        t["act_start_date"] = "2026-05-25 08:00"  # equal to data date
        doc = _make_doc({
            "PROJECT": [_make_project(last_recalc_date="2026-05-25 08:00")],
            "TASK": [t],
        })
        self.assertEqual(_check_actual_after_data_date(doc), [])

    def test_no_data_date_skips(self):
        from xer_validate import _check_actual_after_data_date
        t = _make_task("1")
        t["act_start_date"] = "2026-05-30 08:00"
        doc = _make_doc({
            "PROJECT": [_make_project(last_recalc_date="")],
            "TASK": [t],
        })
        self.assertEqual(_check_actual_after_data_date(doc), [])

    def test_no_project_section_skips(self):
        from xer_validate import _check_actual_after_data_date
        doc = _make_doc({"TASK": [_make_task("1")]})
        self.assertEqual(_check_actual_after_data_date(doc), [])


if __name__ == "__main__":
    unittest.main()
