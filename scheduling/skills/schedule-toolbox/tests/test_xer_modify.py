"""Tests for the mutation engine."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_modify import (  # noqa: E402
    apply_changes, ApplyResult, ChangeRecord, ValidationFailure,
    create_from_template, fix_duplicate_ids,
)


def _make_doc_with_task(task_code: str, target_drtn: str, remain_drtn: str):
    """Build a minimal in-memory XerDoc containing one TASK row."""
    from xer_io import XerDoc, XerSection
    task_section = XerSection(
        name="TASK",
        field_order=["task_id", "task_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
        rows=[{
            "task_id": "1",
            "task_code": task_code,
            "target_drtn_hr_cnt": target_drtn,
            "remain_drtn_hr_cnt": remain_drtn,
        }],
        raw_lines=[f"%R\t1\t{task_code}\t{target_drtn}\t{remain_drtn}"],
        e_line=None,
    )
    return XerDoc(header_line="ERMHDR\t...", encoding="cp1252", sections=[task_section])


def _make_doc_with_task_and_calendar(
    task_code: str,
    target_drtn: str,
    remain_drtn: str,
    calendar_id: str,
    task_calendar_id: str = "100",
):
    """Build a minimal in-memory XerDoc with one TASK row and one CALENDAR row.

    task_calendar_id is the calendar currently assigned to the task (clndr_id on
    the TASK row).  calendar_id is the calendar that exists in the CALENDAR section.
    """
    from xer_io import XerDoc, XerSection
    task_section = XerSection(
        name="TASK",
        field_order=["task_id", "task_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt", "clndr_id"],
        rows=[{
            "task_id": "1",
            "task_code": task_code,
            "target_drtn_hr_cnt": target_drtn,
            "remain_drtn_hr_cnt": remain_drtn,
            "clndr_id": task_calendar_id,
        }],
        raw_lines=[f"%R\t1\t{task_code}\t{target_drtn}\t{remain_drtn}\t{task_calendar_id}"],
        e_line=None,
    )
    calendar_section = XerSection(
        name="CALENDAR",
        field_order=["clndr_id", "clndr_name"],
        rows=[{
            "clndr_id": calendar_id,
            "clndr_name": "Standard",
        }],
        raw_lines=[f"%R\t{calendar_id}\tStandard"],
        e_line=None,
    )
    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[task_section, calendar_section],
    )


class TestOrchestratorShell(unittest.TestCase):
    def test_empty_changes_returns_no_op(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        ))
        result = apply_changes(doc, [], strict=False, dry_run=False)
        self.assertIsInstance(result, ApplyResult)
        self.assertEqual(result.changes_applied, 0)
        self.assertEqual(result.validation_errors, [])

    def test_unknown_change_type_raises(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        ))
        with self.assertRaises(ValidationFailure):
            result = apply_changes(doc, [{"type": "wat"}], strict=False, dry_run=False)


class TestSetDuration(unittest.TestCase):
    def test_happy_path_sets_duration(self):
        """set_duration updates target and remain duration fields to days*8 hours."""
        doc = _make_doc_with_task("A1010", target_drtn="40", remain_drtn="40")
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1010", "new_duration_days": 2}],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task_section = result.doc.section("TASK")
        row = task_section.rows[0]
        self.assertEqual(row["target_drtn_hr_cnt"], "16")
        self.assertEqual(row["remain_drtn_hr_cnt"], "16")

    def test_happy_path_row_marked_dirty(self):
        """The mutated row index is marked dirty after set_duration."""
        doc = _make_doc_with_task("A1010", target_drtn="40", remain_drtn="40")
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1010", "new_duration_days": 2}],
            strict=False,
            dry_run=False,
        )
        task_section = result.doc.section("TASK")
        self.assertTrue(task_section.is_dirty(0))

    def test_activity_not_found_raises(self):
        """set_duration raises ValidationFailure when activity_id not in TASK rows."""
        doc = _make_doc_with_task("A1010", target_drtn="40", remain_drtn="40")
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "ZZZZ", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZZ", result.validation_errors[0].message)

    def test_feedback_shape_all_none(self):
        """Feedback keys are present and all stubbed to None pending D17 CPM pass."""
        doc = _make_doc_with_task("A1010", target_drtn="40", remain_drtn="40")
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1010", "new_duration_days": 3}],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(len(result.per_change_feedback), 1)
        fb = result.per_change_feedback[0].feedback
        self.assertIn("activity_end_before", fb)
        self.assertIn("activity_end_after", fb)
        self.assertIn("milestone_impact_days", fb)
        self.assertIn("now_on_critical_path", fb)
        self.assertIsNone(fb["activity_end_before"])
        self.assertIsNone(fb["activity_end_after"])
        self.assertIsNone(fb["milestone_impact_days"])
        self.assertIsNone(fb["now_on_critical_path"])


def _make_doc_with_task_and_taskpred(
    task_rows: list[dict],
    taskpred_rows: list[dict],
):
    """Build an in-memory XerDoc with TASK and TASKPRED sections.

    task_rows: list of dicts with at least {"task_id", "task_code", "proj_id"}.
    taskpred_rows: list of dicts conforming to the TASKPRED field_order; pass
        [] for an empty TASKPRED section.
    """
    from xer_io import XerDoc, XerSection

    task_field_order = ["task_id", "proj_id", "task_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt"]
    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=task_rows,
        raw_lines=[
            "%R\t{task_id}\t{proj_id}\t{task_code}\t{target_drtn_hr_cnt}\t{remain_drtn_hr_cnt}".format(**r)
            for r in task_rows
        ],
        e_line=None,
    )

    taskpred_field_order = [
        "task_pred_id", "task_id", "pred_task_id",
        "proj_id", "pred_proj_id",
        "pred_type", "lag_hr_cnt",
        "comments", "float_path", "aref", "arls",
    ]
    taskpred_section = XerSection(
        name="TASKPRED",
        field_order=taskpred_field_order,
        rows=taskpred_rows,
        raw_lines=[
            "%R\t{task_pred_id}\t{task_id}\t{pred_task_id}\t{proj_id}\t{pred_proj_id}\t{pred_type}\t{lag_hr_cnt}\t\t\t\t".format(**r)
            for r in taskpred_rows
        ],
        e_line=None,
    )

    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[task_section, taskpred_section],
    )


class TestAddLogic(unittest.TestCase):
    """Tests for the add_logic change handler (D4)."""

    def _two_activity_doc(self, taskpred_rows=None):
        """Two activities (A1010, A1020) with an empty or supplied TASKPRED."""
        if taskpred_rows is None:
            taskpred_rows = []
        return _make_doc_with_task_and_taskpred(
            task_rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            taskpred_rows=taskpred_rows,
        )

    def test_happy_path_appends_row(self):
        """Both activities exist; new edge appended with correct fields."""
        doc = self._two_activity_doc()
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "lag_days": 2,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 1)
        row = tp.rows[0]
        self.assertEqual(row["pred_task_id"], "101")   # numeric task_id of A1010
        self.assertEqual(row["task_id"], "102")         # numeric task_id of A1020
        self.assertEqual(row["pred_type"], "PR_FS")
        self.assertEqual(row["lag_hr_cnt"], "16")       # 2 days * 8
        self.assertEqual(row["task_pred_id"], "1")      # max(empty)+1 → 1

    def test_predecessor_not_found_raises(self):
        """ValidationFailure naming the missing predecessor activity_id."""
        doc = self._two_activity_doc()
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "ZZZPRED",
                "successor_id": "A1020",
                "relationship": "FS",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZPRED", result.validation_errors[0].message)

    def test_successor_not_found_raises(self):
        """ValidationFailure naming the missing successor activity_id."""
        doc = self._two_activity_doc()
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "ZZZSUCC",
                "relationship": "FS",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZSUCC", result.validation_errors[0].message)

    def test_duplicate_edge_raises(self):
        """TASKPRED already has (A1010→A1020, PR_FS); adding same triple raises."""
        existing_row = {
            "task_pred_id": "5001",
            "task_id": "102",        # A1020
            "pred_task_id": "101",   # A1010
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_FS",
            "lag_hr_cnt": "0",
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }
        doc = self._two_activity_doc(taskpred_rows=[existing_row])
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)

    def test_same_pair_different_type_succeeds(self):
        """(A1010→A1020, PR_FS) exists; adding (A1010→A1020, SS) succeeds."""
        existing_row = {
            "task_pred_id": "5001",
            "task_id": "102",
            "pred_task_id": "101",
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_FS",
            "lag_hr_cnt": "0",
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }
        doc = self._two_activity_doc(taskpred_rows=[existing_row])
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "SS",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 2)
        new_row = tp.rows[1]
        self.assertEqual(new_row["pred_type"], "PR_SS")

    def test_task_pred_id_is_max_plus_one(self):
        """New task_pred_id = max of existing IDs + 1 (gaps allowed)."""
        rows = [
            {
                "task_pred_id": str(tid),
                "task_id": "102", "pred_task_id": "101",
                "proj_id": "1", "pred_proj_id": "1",
                "pred_type": "PR_SS",
                "lag_hr_cnt": "0", "comments": "",
                "float_path": "", "aref": "", "arls": "",
            }
            for tid in [1, 5, 3]
        ]
        doc = self._two_activity_doc(taskpred_rows=rows)
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FF",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        new_id = tp.rows[-1]["task_pred_id"]
        self.assertEqual(new_id, "6")   # max(1,5,3)+1

    def test_lag_days_zero(self):
        """lag_days=0 yields lag_hr_cnt='0', not an error."""
        doc = self._two_activity_doc()
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(tp.rows[0]["lag_hr_cnt"], "0")

    def test_empty_taskpred_task_pred_id_is_one(self):
        """When TASKPRED has zero rows, the first new row gets task_pred_id='1'."""
        doc = self._two_activity_doc(taskpred_rows=[])
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "SF",
                "lag_days": 1,
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(tp.rows[0]["task_pred_id"], "1")
        self.assertEqual(tp.rows[0]["pred_type"], "PR_SF")

    def test_new_row_is_dirty(self):
        """Appended row is always dirty (no raw_lines entry behind it)."""
        doc = self._two_activity_doc()
        result = apply_changes(
            doc,
            [{
                "type": "add_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "lag_days": 0,
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertTrue(tp.is_dirty(0))


class TestRemoveLogic(unittest.TestCase):
    """Tests for the remove_logic change handler (D5)."""

    def _two_activity_doc(self, taskpred_rows=None):
        """Two activities (A1010, A1020) with an empty or supplied TASKPRED."""
        if taskpred_rows is None:
            taskpred_rows = []
        return _make_doc_with_task_and_taskpred(
            task_rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            taskpred_rows=taskpred_rows,
        )

    def _fs_row(self, pred_id="101", succ_id="102", tpid="5001"):
        return {
            "task_pred_id": tpid,
            "task_id": succ_id,
            "pred_task_id": pred_id,
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_FS",
            "lag_hr_cnt": "0",
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }

    def _ss_row(self, pred_id="101", succ_id="102", tpid="5002"):
        return {
            "task_pred_id": tpid,
            "task_id": succ_id,
            "pred_task_id": pred_id,
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_SS",
            "lag_hr_cnt": "0",
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }

    # ---- Test 1: happy path --------------------------------------------------

    def test_happy_path_removes_matching_row(self):
        """TASKPRED has the matching edge; row is gone after remove_logic."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 0)

    # ---- Test 2: predecessor not found --------------------------------------

    def test_predecessor_not_found_raises(self):
        """ValidationFailure naming the missing predecessor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "ZZZPRED",
                "successor_id": "A1020",
                "relationship": "FS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZPRED", result.validation_errors[0].message)

    # ---- Test 3: successor not found ----------------------------------------

    def test_successor_not_found_raises(self):
        """ValidationFailure naming the missing successor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "ZZZSUCC",
                "relationship": "FS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZSUCC", result.validation_errors[0].message)

    # ---- Test 4: edge not found (wrong type) ---------------------------------

    def test_edge_not_found_wrong_type_raises(self):
        """TASKPRED has (A1010→A1020, FS); removing SS raises with triple in message."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "SS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)
        self.assertIn("SS", err)

    # ---- Test 5: same pair multiple types — removes only the right one ------

    def test_same_pair_multiple_types_removes_only_target(self):
        """TASKPRED has (A1010→A1020, FS) and (A1010→A1020, SS); remove FS leaves SS."""
        doc = self._two_activity_doc(
            taskpred_rows=[self._fs_row(), self._ss_row()]
        )
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 1)
        self.assertEqual(tp.rows[0]["pred_type"], "PR_SS")

    # ---- Test 6: raw_lines positional alignment preserved -------------------

    def test_removal_preserves_raw_lines_alignment(self):
        """After removal: len(rows) == len(raw_lines) == original - 1."""
        from xer_io import XerDoc, XerSection

        taskpred_field_order = [
            "task_pred_id", "task_id", "pred_task_id",
            "proj_id", "pred_proj_id",
            "pred_type", "lag_hr_cnt",
            "comments", "float_path", "aref", "arls",
        ]
        rows = [
            {"task_pred_id": "1", "task_id": "102", "pred_task_id": "101",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS",
             "lag_hr_cnt": "0", "comments": "", "float_path": "", "aref": "", "arls": ""},
            {"task_pred_id": "2", "task_id": "102", "pred_task_id": "101",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_SS",
             "lag_hr_cnt": "0", "comments": "", "float_path": "", "aref": "", "arls": ""},
            {"task_pred_id": "3", "task_id": "102", "pred_task_id": "101",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FF",
             "lag_hr_cnt": "0", "comments": "", "float_path": "", "aref": "", "arls": ""},
        ]
        raw = ["%R\t1\t102\t101\t1\t1\tPR_FS\t0\t\t\t\t",
               "%R\t2\t102\t101\t1\t1\tPR_SS\t0\t\t\t\t",
               "%R\t3\t102\t101\t1\t1\tPR_FF\t0\t\t\t\t"]

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "proj_id", "task_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
            rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            raw_lines=[
                "%R\t101\t1\tA1010\t40\t40",
                "%R\t102\t1\tA1020\t40\t40",
            ],
            e_line=None,
        )
        taskpred_section = XerSection(
            name="TASKPRED",
            field_order=taskpred_field_order,
            rows=rows,
            raw_lines=raw,
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section, taskpred_section],
        )

        # Pre-condition: 3 rows, 3 raw_lines
        tp_before = doc.section("TASKPRED")
        self.assertEqual(len(tp_before.rows), 3)
        self.assertEqual(len(tp_before.raw_lines), 3)

        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "SS",   # remove middle row (index 1)
            }],
            strict=False,
            dry_run=False,
        )

        # Post-condition: 2 rows, 2 raw_lines
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 2)
        self.assertEqual(len(tp.raw_lines), 2)
        # FS and FF remain; SS is gone
        types_left = [r["pred_type"] for r in tp.rows]
        self.assertIn("PR_FS", types_left)
        self.assertIn("PR_FF", types_left)
        self.assertNotIn("PR_SS", types_left)

    # ---- Test 7: _dirty re-indexing -----------------------------------------

    def test_dirty_reindex_after_removal(self):
        """Remove rows[1]; _dirty={0,2} → {0,1} (index-2 follows its row down)."""
        from xer_io import XerDoc, XerSection

        taskpred_field_order = [
            "task_pred_id", "task_id", "pred_task_id",
            "proj_id", "pred_proj_id",
            "pred_type", "lag_hr_cnt",
            "comments", "float_path", "aref", "arls",
        ]
        rows = [
            {"task_pred_id": "1", "task_id": "102", "pred_task_id": "101",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS",
             "lag_hr_cnt": "0", "comments": "", "float_path": "", "aref": "", "arls": ""},
            {"task_pred_id": "2", "task_id": "102", "pred_task_id": "101",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_SS",
             "lag_hr_cnt": "0", "comments": "", "float_path": "", "aref": "", "arls": ""},
            {"task_pred_id": "3", "task_id": "102", "pred_task_id": "101",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FF",
             "lag_hr_cnt": "0", "comments": "", "float_path": "", "aref": "", "arls": ""},
        ]
        raw = ["%R\t1\t102\t101\t1\t1\tPR_FS\t0\t\t\t\t",
               "%R\t2\t102\t101\t1\t1\tPR_SS\t0\t\t\t\t",
               "%R\t3\t102\t101\t1\t1\tPR_FF\t0\t\t\t\t"]

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "proj_id", "task_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
            rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            raw_lines=[
                "%R\t101\t1\tA1010\t40\t40",
                "%R\t102\t1\tA1020\t40\t40",
            ],
            e_line=None,
        )
        taskpred_section = XerSection(
            name="TASKPRED",
            field_order=taskpred_field_order,
            rows=rows,
            raw_lines=raw,
            e_line=None,
        )
        # Manually pre-seed _dirty with {0, 2} (rows 0 and 2 were already mutated)
        taskpred_section._dirty = {0, 2}

        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section, taskpred_section],
        )

        # Remove middle row (index 1 = PR_SS)
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "SS",
            }],
            strict=False,
            dry_run=False,
        )

        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 2)
        # Original index-0 (PR_FS) stays at 0; original index-2 (PR_FF) moves to 1.
        # _dirty should be {0, 1}: index-0 unchanged, index-2→1 decremented.
        self.assertEqual(tp._dirty, {0, 1})

    # ---- Test 8: duplicate rows in TASKPRED is a structural error -----------

    def test_multiple_matching_rows_raises(self):
        """If TASKPRED has two identical (pred, succ, type) rows, raise ValidationFailure."""
        dup_row_a = {
            "task_pred_id": "5001",
            "task_id": "102",
            "pred_task_id": "101",
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_FS",
            "lag_hr_cnt": "0",
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }
        dup_row_b = {
            "task_pred_id": "5002",
            "task_id": "102",
            "pred_task_id": "101",
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_FS",
            "lag_hr_cnt": "8",   # different lag, same triple
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }
        doc = self._two_activity_doc(taskpred_rows=[dup_row_a, dup_row_b])
        result = apply_changes(
            doc,
            [{
                "type": "remove_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)


class TestSetCalendar(unittest.TestCase):
    def test_happy_path_updates_clndr_id_and_marks_dirty(self):
        """set_calendar writes new calendar ID to TASK row and marks it dirty."""
        doc = _make_doc_with_task_and_calendar(
            task_code="A1010",
            target_drtn="40",
            remain_drtn="40",
            calendar_id="200",
            task_calendar_id="100",
        )
        result = apply_changes(
            doc,
            [{"type": "set_calendar", "activity_id": "A1010", "new_calendar_id": "200"}],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task_section = result.doc.section("TASK")
        row = task_section.rows[0]
        self.assertEqual(row["clndr_id"], "200")
        self.assertTrue(task_section.is_dirty(0))

    def test_activity_not_found_raises(self):
        """set_calendar raises ValidationFailure when activity_id not in TASK rows."""
        doc = _make_doc_with_task_and_calendar(
            task_code="A1010",
            target_drtn="40",
            remain_drtn="40",
            calendar_id="200",
        )
        result = apply_changes(
            doc,
            [{"type": "set_calendar", "activity_id": "ZZZZ", "new_calendar_id": "200"}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZZ", result.validation_errors[0].message)

    def test_calendar_not_found_raises(self):
        """set_calendar raises ValidationFailure when calendar not in doc and not in state."""
        doc = _make_doc_with_task_and_calendar(
            task_code="A1010",
            target_drtn="40",
            remain_drtn="40",
            calendar_id="200",
        )
        result = apply_changes(
            doc,
            [{"type": "set_calendar", "activity_id": "A1010", "new_calendar_id": "999"}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("999", result.validation_errors[0].message)

    def test_calendar_in_state_succeeds(self):
        """set_calendar succeeds when calendar is in state.new_calendar_ids even if absent from doc."""
        from xer_modify import ChangeState
        from xer_io import XerDoc, XerSection

        # Build a doc with a TASK but a CALENDAR section that does NOT contain "300"
        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code", "target_drtn_hr_cnt", "remain_drtn_hr_cnt", "clndr_id"],
            rows=[{
                "task_id": "1",
                "task_code": "A1010",
                "target_drtn_hr_cnt": "40",
                "remain_drtn_hr_cnt": "40",
                "clndr_id": "100",
            }],
            raw_lines=["%R\t1\tA1010\t40\t40\t100"],
            e_line=None,
        )
        calendar_section = XerSection(
            name="CALENDAR",
            field_order=["clndr_id", "clndr_name"],
            rows=[{"clndr_id": "100", "clndr_name": "Standard"}],
            raw_lines=["%R\t100\tStandard"],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section, calendar_section],
        )

        # Directly invoke apply_changes — "300" is not in the CALENDAR section,
        # but a preceding change (simulated here by pre-populating state) would
        # have added it.  We test the state hook by pre-seeding state indirectly
        # through a two-change list where the first change is set_calendar with
        # a known calendar (100) and the second targets "300" — but that won't
        # put "300" in state either.  Instead we confirm the lookup logic by
        # verifying that without "300" in state the call raises, and separately
        # that when the orchestrator would have it in state it passes.
        #
        # Since we cannot inject state directly through apply_changes, we call
        # the handler directly to verify the state-path branch.
        from xer_modify import _HANDLERS, ChangeState
        handler = _HANDLERS["set_calendar"]
        state = ChangeState(new_calendar_ids={"300"})
        feedback = handler(doc, {"type": "set_calendar", "activity_id": "A1010", "new_calendar_id": "300"}, state)
        self.assertEqual(doc.section("TASK").rows[0]["clndr_id"], "300")
        self.assertIn("activity_end_before", feedback)


def _make_doc_with_task_wbs_calendar(
    task_rows: list[dict] | None = None,
    wbs_rows: list[dict] | None = None,
    calendar_rows: list[dict] | None = None,
):
    """Build an in-memory XerDoc with TASK, PROJWBS, and CALENDAR sections.

    Defaults build a single-row fixture matching minimal.xer's structure:
      - TASK: one row (task_id=10001, task_code=A1010, TT_Task, 40h)
      - PROJWBS: one row (wbs_id=1000, proj_id=1)
      - CALENDAR: one row (clndr_id=100)

    Callers may supply their own rows lists to override any section.
    """
    from xer_io import XerDoc, XerSection

    if task_rows is None:
        task_rows = [
            {
                "task_id": "10001",
                "proj_id": "1",
                "wbs_id": "1000",
                "clndr_id": "100",
                "task_code": "A1010",
                "task_name": "Existing Task",
                "task_type": "TT_Task",
                "duration_type": "DT_FixedDUR2",
                "status_code": "TK_NotStart",
                "complete_pct_type": "CP_Drtn",
                "phys_complete_pct": "0",
                "target_drtn_hr_cnt": "40",
                "remain_drtn_hr_cnt": "40",
            }
        ]
    if wbs_rows is None:
        wbs_rows = [{"wbs_id": "1000", "proj_id": "1", "wbs_name": "Root"}]
    if calendar_rows is None:
        calendar_rows = [{"clndr_id": "100", "clndr_name": "Standard"}]

    task_field_order = [
        "task_id", "proj_id", "wbs_id", "clndr_id",
        "task_code", "task_name", "task_type", "duration_type",
        "status_code", "complete_pct_type", "phys_complete_pct",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    ]
    wbs_field_order = ["wbs_id", "proj_id", "wbs_name"]
    cal_field_order = ["clndr_id", "clndr_name"]

    def _raw_task(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in task_field_order)

    def _raw_wbs(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in wbs_field_order)

    def _raw_cal(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in cal_field_order)

    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=task_rows,
        raw_lines=[_raw_task(r) for r in task_rows],
        e_line=None,
    )
    wbs_section = XerSection(
        name="PROJWBS",
        field_order=wbs_field_order,
        rows=wbs_rows,
        raw_lines=[_raw_wbs(r) for r in wbs_rows],
        e_line=None,
    )
    cal_section = XerSection(
        name="CALENDAR",
        field_order=cal_field_order,
        rows=calendar_rows,
        raw_lines=[_raw_cal(r) for r in calendar_rows],
        e_line=None,
    )
    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[task_section, wbs_section, cal_section],
    )


def _add_activity_change(**spec_kwargs):
    """Return a minimal add_activity change record. All spec fields required."""
    spec = {
        "code": "A2010",
        "name": "New Task",
        "duration_days": 5,
        "calendar_id": "100",
        "wbs_id": "1000",
        "activity_type": "TT_Task",
    }
    spec.update(spec_kwargs)
    return {"type": "add_activity", "spec": spec}


class TestAddActivity(unittest.TestCase):
    """Tests for the add_activity change handler (D7)."""

    # ---- Test 1: happy path --------------------------------------------------

    def test_happy_path_appends_row_and_populates_state(self):
        """All fields valid; new TASK row appended with correct values; state updated."""
        doc = _make_doc_with_task_wbs_calendar()
        result = apply_changes(
            doc,
            [_add_activity_change()],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task_section = result.doc.section("TASK")
        self.assertEqual(len(task_section.rows), 2)

        new_row = task_section.rows[1]
        self.assertEqual(new_row["task_id"], "10002")       # max(10001)+1
        self.assertEqual(new_row["task_code"], "A2010")
        self.assertEqual(new_row["task_name"], "New Task")
        self.assertEqual(new_row["task_type"], "TT_Task")
        self.assertEqual(new_row["target_drtn_hr_cnt"], "40")   # 5 days * 8
        self.assertEqual(new_row["remain_drtn_hr_cnt"], "40")
        self.assertEqual(new_row["clndr_id"], "100")
        self.assertEqual(new_row["wbs_id"], "1000")
        self.assertEqual(new_row["status_code"], "TK_NotStart")
        self.assertEqual(new_row["duration_type"], "DT_FixedDUR2")
        self.assertEqual(new_row["complete_pct_type"], "CP_Drtn")
        self.assertEqual(new_row["phys_complete_pct"], "0")

        # State tracking
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_task_id"], "10002")

        # Verify state via direct handler call to inspect ChangeState
        from xer_modify import _HANDLERS, ChangeState
        doc2 = _make_doc_with_task_wbs_calendar()
        state = ChangeState()
        _HANDLERS["add_activity"](doc2, _add_activity_change(), state)
        self.assertIn("A2010", state.new_activity_ids)
        self.assertEqual(state.new_activity_id_map["A2010"], "10002")

    # ---- Test 2: missing required field -------------------------------------

    def test_missing_spec_field_raises(self):
        """Omitting 'name' from spec raises ValidationFailure naming the field."""
        doc = _make_doc_with_task_wbs_calendar()
        change = {"type": "add_activity", "spec": {
            "code": "A2010",
            # name intentionally omitted
            "duration_days": 5,
            "calendar_id": "100",
            "wbs_id": "1000",
            "activity_type": "TT_Task",
        }}
        result = apply_changes(doc, [change], strict=False, dry_run=False)
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("name", result.validation_errors[0].message)

    # ---- Test 3: duplicate task_code ----------------------------------------

    def test_duplicate_task_code_raises(self):
        """task_code already exists in TASK section; ValidationFailure names the code."""
        doc = _make_doc_with_task_wbs_calendar()
        # A1010 is the existing row's task_code
        result = apply_changes(
            doc,
            [_add_activity_change(code="A1010")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("A1010", result.validation_errors[0].message)

    # ---- Test 4: unknown wbs_id ---------------------------------------------

    def test_unknown_wbs_id_raises(self):
        """wbs_id not in PROJWBS and not in state → ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        result = apply_changes(
            doc,
            [_add_activity_change(wbs_id="9999")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("9999", result.validation_errors[0].message)

    # ---- Test 5: unknown calendar_id ----------------------------------------

    def test_unknown_calendar_id_raises(self):
        """calendar_id not in CALENDAR and not in state → ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        result = apply_changes(
            doc,
            [_add_activity_change(calendar_id="999")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("999", result.validation_errors[0].message)

    # ---- Test 6: unknown activity_type --------------------------------------

    def test_unknown_activity_type_raises(self):
        """activity_type='TT_Bogus' raises ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        result = apply_changes(
            doc,
            [_add_activity_change(activity_type="TT_Bogus")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("TT_Bogus", result.validation_errors[0].message)

    # ---- Test 7: negative duration ------------------------------------------

    def test_negative_duration_raises(self):
        """duration_days=-1 raises ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        result = apply_changes(
            doc,
            [_add_activity_change(duration_days=-1)],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("-1", result.validation_errors[0].message)

    # ---- Test 8: zero-duration milestone ------------------------------------

    def test_zero_duration_milestone_succeeds(self):
        """TT_Mile with duration_days=0 succeeds; durations stored as '0'."""
        doc = _make_doc_with_task_wbs_calendar()
        result = apply_changes(
            doc,
            [_add_activity_change(activity_type="TT_Mile", duration_days=0)],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        new_row = result.doc.section("TASK").rows[1]
        self.assertEqual(new_row["target_drtn_hr_cnt"], "0")
        self.assertEqual(new_row["remain_drtn_hr_cnt"], "0")
        self.assertEqual(new_row["task_type"], "TT_Mile")

    # ---- Test 9: task_id generation from non-contiguous existing ids --------

    def test_task_id_is_max_plus_one(self):
        """TASK has task_ids '1', '5', '3'; new id should be '6'."""
        task_rows = [
            {
                "task_id": tid, "proj_id": "1", "wbs_id": "1000", "clndr_id": "100",
                "task_code": f"A{tid}", "task_name": "X",
                "task_type": "TT_Task", "duration_type": "DT_FixedDUR2",
                "status_code": "TK_NotStart", "complete_pct_type": "CP_Drtn",
                "phys_complete_pct": "0",
                "target_drtn_hr_cnt": "8", "remain_drtn_hr_cnt": "8",
            }
            for tid in ["1", "5", "3"]
        ]
        doc = _make_doc_with_task_wbs_calendar(task_rows=task_rows)
        result = apply_changes(
            doc,
            [_add_activity_change(code="A9999")],
            strict=False,
            dry_run=False,
        )
        new_row = result.doc.section("TASK").rows[-1]
        self.assertEqual(new_row["task_id"], "6")   # max(1,5,3)+1

    # ---- Test 10: empty TASK section → task_id starts at 1 -----------------

    def test_empty_task_section_task_id_starts_at_one(self):
        """When TASK has no rows, the first new row gets task_id='1'."""
        doc = _make_doc_with_task_wbs_calendar(task_rows=[])
        result = apply_changes(
            doc,
            [_add_activity_change()],
            strict=False,
            dry_run=False,
        )
        new_row = result.doc.section("TASK").rows[0]
        self.assertEqual(new_row["task_id"], "1")

    # ---- Test 11: wbs_id satisfied by state.new_wbs_ids ---------------------

    def test_wbs_id_satisfied_by_state(self):
        """wbs_id not in PROJWBS but present in state.new_wbs_ids → succeeds."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_task_wbs_calendar()
        state = ChangeState(new_wbs_ids={"8888"})
        feedback = _HANDLERS["add_activity"](
            doc,
            _add_activity_change(wbs_id="8888"),
            state,
        )
        new_row = doc.section("TASK").rows[-1]
        self.assertEqual(new_row["wbs_id"], "8888")
        self.assertIn("new_task_id", feedback)

    # ---- Test 12: calendar_id satisfied by state.new_calendar_ids -----------

    def test_calendar_id_satisfied_by_state(self):
        """calendar_id not in CALENDAR but present in state.new_calendar_ids → succeeds."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_task_wbs_calendar()
        state = ChangeState(new_calendar_ids={"777"})
        feedback = _HANDLERS["add_activity"](
            doc,
            _add_activity_change(calendar_id="777"),
            state,
        )
        new_row = doc.section("TASK").rows[-1]
        self.assertEqual(new_row["clndr_id"], "777")
        self.assertIn("new_task_id", feedback)


class TestModifyLogic(unittest.TestCase):
    """Tests for the modify_logic change handler (D6)."""

    def _two_activity_doc(self, taskpred_rows=None):
        """Two activities (A1010, A1020) with an empty or supplied TASKPRED."""
        if taskpred_rows is None:
            taskpred_rows = []
        return _make_doc_with_task_and_taskpred(
            task_rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            taskpred_rows=taskpred_rows,
        )

    def _fs_row(self, pred_id="101", succ_id="102", tpid="5001", lag="8"):
        return {
            "task_pred_id": tpid,
            "task_id": succ_id,
            "pred_task_id": pred_id,
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_FS",
            "lag_hr_cnt": lag,
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }

    def _ss_row(self, pred_id="101", succ_id="102", tpid="5002", lag="0"):
        return {
            "task_pred_id": tpid,
            "task_id": succ_id,
            "pred_task_id": pred_id,
            "proj_id": "1",
            "pred_proj_id": "1",
            "pred_type": "PR_SS",
            "lag_hr_cnt": lag,
            "comments": "",
            "float_path": "",
            "aref": "",
            "arls": "",
        }

    # ---- Test 1: modify lag only ---------------------------------------------

    def test_modify_lag_only(self):
        """new_lag_days=3 only: lag_hr_cnt becomes '24', pred_type unchanged, row dirty."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row(lag="8")])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_lag_days": 3,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        tp = result.doc.section("TASKPRED")
        row = tp.rows[0]
        self.assertEqual(row["lag_hr_cnt"], "24")       # 3 days * 8
        self.assertEqual(row["pred_type"], "PR_FS")     # unchanged
        self.assertTrue(tp.is_dirty(0))

    # ---- Test 2: modify relationship only ------------------------------------

    def test_modify_relationship_only(self):
        """new_relationship='SS' only: pred_type becomes 'PR_SS', lag unchanged, dirty."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row(lag="8")])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_relationship": "SS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        tp = result.doc.section("TASKPRED")
        row = tp.rows[0]
        self.assertEqual(row["pred_type"], "PR_SS")
        self.assertEqual(row["lag_hr_cnt"], "8")        # unchanged
        self.assertTrue(tp.is_dirty(0))

    # ---- Test 3: modify both -------------------------------------------------

    def test_modify_both_fields(self):
        """Both new_relationship and new_lag_days provided: both updated."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row(lag="8")])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_relationship": "FF",
                "new_lag_days": 2,
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        row = tp.rows[0]
        self.assertEqual(row["pred_type"], "PR_FF")
        self.assertEqual(row["lag_hr_cnt"], "16")       # 2 days * 8
        self.assertTrue(tp.is_dirty(0))

    # ---- Test 4: neither field provided → ValidationFailure ------------------

    def test_neither_field_provided_raises(self):
        """No new_relationship and no new_lag_days → ValidationFailure (caller bug)."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("modify_logic", result.validation_errors[0].message)

    # ---- Test 5: predecessor not found ---------------------------------------

    def test_predecessor_not_found_raises(self):
        """ValidationFailure naming the missing predecessor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "ZZZPRED",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_lag_days": 1,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZPRED", result.validation_errors[0].message)

    # ---- Test 6: successor not found -----------------------------------------

    def test_successor_not_found_raises(self):
        """ValidationFailure naming the missing successor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "ZZZSUCC",
                "relationship": "FS",
                "new_lag_days": 1,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZSUCC", result.validation_errors[0].message)

    # ---- Test 7: edge not found (wrong selector type) ------------------------

    def test_edge_not_found_raises(self):
        """TASKPRED has (A1010→A1020, FS); selecting SS raises ValidationFailure."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "SS",       # selector, not the existing edge
                "new_lag_days": 1,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)

    # ---- Test 8: multiple matching rows → ValidationFailure ------------------

    def test_multiple_matching_rows_raises(self):
        """Two identical (pred, succ, type) rows in TASKPRED → ValidationFailure."""
        dup_a = self._fs_row(tpid="5001", lag="8")
        dup_b = self._fs_row(tpid="5002", lag="16")   # same triple, different lag
        doc = self._two_activity_doc(taskpred_rows=[dup_a, dup_b])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_lag_days": 2,
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)

    # ---- Test 9: duplicate new edge → ValidationFailure ---------------------

    def test_duplicate_new_edge_raises(self):
        """TASKPRED has (A,B,FS) and (A,B,SS); modify (A,B,FS) → SS would create duplicate."""
        doc = self._two_activity_doc(
            taskpred_rows=[self._fs_row(tpid="5001"), self._ss_row(tpid="5002")]
        )
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_relationship": "SS",   # would collide with existing SS row
            }],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)

    # ---- Test 10: no-op relationship change does not trip duplicate check ----

    def test_noop_relationship_with_lag_change_succeeds(self):
        """modify (A,B,FS) with new_relationship='FS' (same) + new_lag_days=10; no duplicate error."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row(lag="8")])
        result = apply_changes(
            doc,
            [{
                "type": "modify_logic",
                "predecessor_id": "A1010",
                "successor_id": "A1020",
                "relationship": "FS",
                "new_relationship": "FS",   # same type — no-op on relationship
                "new_lag_days": 10,
            }],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        row = tp.rows[0]
        self.assertEqual(row["lag_hr_cnt"], "80")   # 10 days * 8
        self.assertEqual(row["pred_type"], "PR_FS")
        self.assertEqual(result.changes_applied, 1)


# ---------------------------------------------------------------------------
# Helpers for TestRemoveActivity
# ---------------------------------------------------------------------------

def _make_doc_with_two_tasks_and_edge():
    """Three-activity doc (A1010, A1020, A1030) with one TASKPRED edge:
    A1010 → A1020 (FS).  A1030 has no edges.
    """
    return _make_doc_with_task_and_taskpred(
        task_rows=[
            {"task_id": "101", "proj_id": "1", "task_code": "A1010",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "102", "proj_id": "1", "task_code": "A1020",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "103", "proj_id": "1", "task_code": "A1030",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
        ],
        taskpred_rows=[
            {
                "task_pred_id": "5001",
                "task_id": "102",       # A1020 (successor)
                "pred_task_id": "101",  # A1010 (predecessor)
                "proj_id": "1",
                "pred_proj_id": "1",
                "pred_type": "PR_FS",
                "lag_hr_cnt": "0",
                "comments": "",
                "float_path": "",
                "aref": "",
                "arls": "",
            },
        ],
    )


def _remove_activity_change(activity_id: str):
    return {"type": "remove_activity", "activity_id": activity_id}


class TestRemoveActivity(unittest.TestCase):
    """Tests for the remove_activity change handler (D8)."""

    # ---- Test 1: happy path --------------------------------------------------

    def test_happy_path_removes_task_and_edges(self):
        """Remove A1010: TASK row count drops by 1, TASKPRED row drops by 1,
        state.removed_activity_ids contains A1010."""
        doc = _make_doc_with_two_tasks_and_edge()
        result = apply_changes(
            doc,
            [_remove_activity_change("A1010")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")
        # Three tasks → two remaining (A1020, A1030)
        self.assertEqual(len(task.rows), 2)
        remaining_codes = {r["task_code"] for r in task.rows}
        self.assertNotIn("A1010", remaining_codes)
        # One edge referencing A1010 removed
        self.assertEqual(len(tp.rows), 0)

        # Confirm state via direct handler call
        from xer_modify import _HANDLERS, ChangeState
        doc2 = _make_doc_with_two_tasks_and_edge()
        state = ChangeState()
        _HANDLERS["remove_activity"](doc2, _remove_activity_change("A1010"), state)
        self.assertIn("A1010", state.removed_activity_ids)

    # ---- Test 2: activity not found → ValidationFailure ----------------------

    def test_activity_not_found_raises(self):
        """remove_activity raises ValidationFailure naming the missing id."""
        doc = _make_doc_with_two_tasks_and_edge()
        result = apply_changes(
            doc,
            [_remove_activity_change("ZZZZ")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZZ", result.validation_errors[0].message)

    # ---- Test 3: no TASKPRED section → succeeds ------------------------------

    def test_no_taskpred_section_succeeds(self):
        """remove_activity succeeds when no TASKPRED section exists."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "proj_id", "task_code",
                         "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
            rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            raw_lines=[
                "%R\t101\t1\tA1010\t40\t40",
                "%R\t102\t1\tA1020\t40\t40",
            ],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section],
        )

        result = apply_changes(
            doc,
            [_remove_activity_change("A1010")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task = result.doc.section("TASK")
        self.assertEqual(len(task.rows), 1)
        self.assertEqual(task.rows[0]["task_code"], "A1020")
        self.assertIsNone(result.doc.section("TASKPRED"))

    # ---- Test 4: no edges referencing the activity → TASKPRED untouched ------

    def test_no_edges_referencing_activity_untouched(self):
        """Remove A1030 (no edges); TASKPRED rows for other activities unchanged."""
        doc = _make_doc_with_two_tasks_and_edge()
        result = apply_changes(
            doc,
            [_remove_activity_change("A1030")],
            strict=False,
            dry_run=False,
        )
        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")
        # A1030 removed; A1010 and A1020 remain
        self.assertEqual(len(task.rows), 2)
        # The A1010→A1020 edge is untouched
        self.assertEqual(len(tp.rows), 1)
        self.assertEqual(tp.rows[0]["pred_task_id"], "101")

    # ---- Test 5: multiple referencing edges all removed ----------------------

    def test_multiple_referencing_edges_all_removed(self):
        """A1010 is predecessor in 2 edges and successor in 1; all 3 removed."""
        task_rows = [
            {"task_id": "101", "proj_id": "1", "task_code": "A1010",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "102", "proj_id": "1", "task_code": "A1020",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "103", "proj_id": "1", "task_code": "A1030",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "104", "proj_id": "1", "task_code": "A1040",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
        ]

        def _tp_row(tpid, succ, pred, pred_type="PR_FS"):
            return {
                "task_pred_id": tpid,
                "task_id": succ,
                "pred_task_id": pred,
                "proj_id": "1",
                "pred_proj_id": "1",
                "pred_type": pred_type,
                "lag_hr_cnt": "0",
                "comments": "",
                "float_path": "",
                "aref": "",
                "arls": "",
            }

        taskpred_rows = [
            _tp_row("1", "102", "101"),   # A1010 → A1020 FS
            _tp_row("2", "103", "101"),   # A1010 → A1030 FS
            _tp_row("3", "101", "104"),   # A1040 → A1010 FS  (A1010 as successor)
            _tp_row("4", "103", "102"),   # A1020 → A1030 FS  (unrelated)
        ]
        doc = _make_doc_with_task_and_taskpred(
            task_rows=task_rows,
            taskpred_rows=taskpred_rows,
        )

        result = apply_changes(
            doc,
            [_remove_activity_change("A1010")],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        # 3 edges referencing A1010 removed; 1 unrelated edge remains
        self.assertEqual(len(tp.rows), 1)
        self.assertEqual(tp.rows[0]["task_pred_id"], "4")

        # Feedback should report removed_edges_count == 3
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["removed_edges_count"], 3)

    # ---- Test 6: dirty re-indexing on TASK -----------------------------------

    def test_dirty_reindex_on_task(self):
        """TASK has 3 rows with rows[0] and rows[2] dirty; remove rows[1]; _dirty=={0, 1}."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "proj_id", "task_code",
                         "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
            rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "A1010",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "A1020",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "103", "proj_id": "1", "task_code": "A1030",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            raw_lines=[
                "%R\t101\t1\tA1010\t40\t40",
                "%R\t102\t1\tA1020\t40\t40",
                "%R\t103\t1\tA1030\t40\t40",
            ],
            e_line=None,
        )
        # Pre-seed dirty: rows[0] and rows[2] are dirty
        task_section._dirty = {0, 2}

        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section],
        )

        # Remove rows[1] (A1020)
        result = apply_changes(
            doc,
            [_remove_activity_change("A1020")],
            strict=False,
            dry_run=False,
        )

        task = result.doc.section("TASK")
        self.assertEqual(len(task.rows), 2)
        # Original index-0 stays at 0; original index-2 moves to 1.
        # _dirty should be {0, 1}
        self.assertEqual(task._dirty, {0, 1})

    # ---- Test 7: dirty re-indexing on TASKPRED with multiple removals --------

    def test_dirty_reindex_on_taskpred_multi_removal(self):
        """5 TASKPRED rows; rows[1] and rows[3] reference the target; rows[0] and rows[4]
        are dirty.  After removal of indices {1,3}, remaining rows are originals
        [0,2,4] at new indices [0,1,2]; original dirty {0,4} → new dirty {0,2}."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "proj_id", "task_code",
                         "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
            rows=[
                {"task_id": "101", "proj_id": "1", "task_code": "TARGET",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "102", "proj_id": "1", "task_code": "OTHER1",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
                {"task_id": "103", "proj_id": "1", "task_code": "OTHER2",
                 "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            ],
            raw_lines=[
                "%R\t101\t1\tTARGET\t40\t40",
                "%R\t102\t1\tOTHER1\t40\t40",
                "%R\t103\t1\tOTHER2\t40\t40",
            ],
            e_line=None,
        )

        def _tp(tpid, succ, pred):
            return {
                "task_pred_id": tpid,
                "task_id": succ,
                "pred_task_id": pred,
                "proj_id": "1",
                "pred_proj_id": "1",
                "pred_type": "PR_FS",
                "lag_hr_cnt": "0",
                "comments": "",
                "float_path": "",
                "aref": "",
                "arls": "",
            }

        # Build TASKPRED: indices 1 and 3 reference TARGET (task_id=101)
        tp_rows = [
            _tp("1", "102", "103"),   # index 0: OTHER2 → OTHER1 (unrelated)
            _tp("2", "102", "101"),   # index 1: TARGET → OTHER1
            _tp("3", "103", "102"),   # index 2: OTHER1 → OTHER2 (unrelated)
            _tp("4", "103", "101"),   # index 3: TARGET → OTHER2
            _tp("5", "102", "103"),   # index 4: OTHER2 → OTHER1 (unrelated)
        ]
        tp_raw = [
            "%R\t1\t102\t103\t1\t1\tPR_FS\t0\t\t\t\t",
            "%R\t2\t102\t101\t1\t1\tPR_FS\t0\t\t\t\t",
            "%R\t3\t103\t102\t1\t1\tPR_FS\t0\t\t\t\t",
            "%R\t4\t103\t101\t1\t1\tPR_FS\t0\t\t\t\t",
            "%R\t5\t102\t103\t1\t1\tPR_FS\t0\t\t\t\t",
        ]
        taskpred_section = XerSection(
            name="TASKPRED",
            field_order=[
                "task_pred_id", "task_id", "pred_task_id",
                "proj_id", "pred_proj_id",
                "pred_type", "lag_hr_cnt",
                "comments", "float_path", "aref", "arls",
            ],
            rows=tp_rows,
            raw_lines=tp_raw,
            e_line=None,
        )
        # Pre-seed dirty: rows[0] and rows[4]
        taskpred_section._dirty = {0, 4}

        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section, taskpred_section],
        )

        result = apply_changes(
            doc,
            [_remove_activity_change("TARGET")],
            strict=False,
            dry_run=False,
        )

        tp = result.doc.section("TASKPRED")
        # Rows at original indices 1 and 3 removed; 3 remain
        self.assertEqual(len(tp.rows), 3)
        # Remaining task_pred_ids: "1", "3", "5" (originals at 0, 2, 4)
        remaining_ids = [r["task_pred_id"] for r in tp.rows]
        self.assertEqual(remaining_ids, ["1", "3", "5"])
        # Dirty re-indexing: original 0→0, original 4→2
        self.assertEqual(tp._dirty, {0, 2})

    # ---- Test 8: raw_lines stay aligned after removal ------------------------

    def test_raw_lines_aligned_after_removal(self):
        """len(taskpred.raw_lines) == len(taskpred.rows) after removal."""
        doc = _make_doc_with_two_tasks_and_edge()
        tp_before = doc.section("TASKPRED")
        rows_before = len(tp_before.rows)
        raw_before = len(tp_before.raw_lines)
        self.assertEqual(rows_before, raw_before)

        result = apply_changes(
            doc,
            [_remove_activity_change("A1010")],
            strict=False,
            dry_run=False,
        )

        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), len(tp.raw_lines))

    # ---- Test 9: feedback shape ----------------------------------------------

    def test_feedback_shape(self):
        """Happy path returns dict with all 6 keys; CPM stubs are None."""
        doc = _make_doc_with_two_tasks_and_edge()
        result = apply_changes(
            doc,
            [_remove_activity_change("A1010")],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        self.assertIn("removed_task_id", fb)
        self.assertIn("removed_edges_count", fb)
        self.assertIn("activity_end_before", fb)
        self.assertIn("activity_end_after", fb)
        self.assertIn("milestone_impact_days", fb)
        self.assertIn("now_on_critical_path", fb)

        self.assertEqual(fb["removed_task_id"], "101")  # numeric id of A1010
        self.assertEqual(fb["removed_edges_count"], 1)
        self.assertIsNone(fb["activity_end_before"])
        self.assertIsNone(fb["activity_end_after"])
        self.assertIsNone(fb["milestone_impact_days"])
        self.assertIsNone(fb["now_on_critical_path"])

    # ---- Test 10: state.removed_activity_ids accumulates ---------------------

    def test_state_accumulates_across_multiple_removals(self):
        """Two remove_activity changes in one call; state.removed_activity_ids contains both."""
        task_rows = [
            {"task_id": "101", "proj_id": "1", "task_code": "A1010",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "102", "proj_id": "1", "task_code": "A1020",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
            {"task_id": "103", "proj_id": "1", "task_code": "A1030",
             "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40"},
        ]
        doc = _make_doc_with_task_and_taskpred(
            task_rows=task_rows,
            taskpred_rows=[],
        )

        from xer_modify import _HANDLERS, ChangeState
        state = ChangeState()
        _HANDLERS["remove_activity"](
            doc,
            _remove_activity_change("A1010"),
            state,
        )
        _HANDLERS["remove_activity"](
            doc,
            _remove_activity_change("A1020"),
            state,
        )

        self.assertIn("A1010", state.removed_activity_ids)
        self.assertIn("A1020", state.removed_activity_ids)
        # A1030 is untouched
        self.assertNotIn("A1030", state.removed_activity_ids)


# ---------------------------------------------------------------------------
# Helpers for TestDissolveActivity
# ---------------------------------------------------------------------------

def _make_dissolve_doc(
    task_rows: list[dict],
    taskpred_rows: list[dict],
):
    """Build an in-memory XerDoc with TASK and TASKPRED sections for dissolve tests.

    task_rows must include at least: task_id, proj_id, task_code,
    target_drtn_hr_cnt, remain_drtn_hr_cnt.
    """
    from xer_io import XerDoc, XerSection

    task_field_order = [
        "task_id", "proj_id", "task_code",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    ]
    taskpred_field_order = [
        "task_pred_id", "task_id", "pred_task_id",
        "proj_id", "pred_proj_id",
        "pred_type", "lag_hr_cnt",
        "comments", "float_path", "aref", "arls",
    ]

    def _raw_task(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in task_field_order)

    def _raw_tp(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in taskpred_field_order)

    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=task_rows,
        raw_lines=[_raw_task(r) for r in task_rows],
        e_line=None,
    )
    taskpred_section = XerSection(
        name="TASKPRED",
        field_order=taskpred_field_order,
        rows=taskpred_rows,
        raw_lines=[_raw_tp(r) for r in taskpred_rows],
        e_line=None,
    )
    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[task_section, taskpred_section],
    )


def _tp_row(tpid, succ_task_id, pred_task_id, pred_type="PR_FS", lag="0"):
    """Convenience: build a TASKPRED row dict."""
    return {
        "task_pred_id": tpid,
        "task_id": succ_task_id,
        "pred_task_id": pred_task_id,
        "proj_id": "1",
        "pred_proj_id": "1",
        "pred_type": pred_type,
        "lag_hr_cnt": lag,
        "comments": "",
        "float_path": "",
        "aref": "",
        "arls": "",
    }


def _task_row(task_id, task_code, drtn="16"):
    return {
        "task_id": task_id,
        "proj_id": "1",
        "task_code": task_code,
        "target_drtn_hr_cnt": drtn,
        "remain_drtn_hr_cnt": drtn,
    }


class TestDissolveActivity(unittest.TestCase):
    """Tests for the dissolve_activity change handler (D9).

    Composition rule: new_rel = pred_rel[0] + succ_rel[1]  (XZ endpoint composition).
    Lag formula: new_lag_hr = pred_lag_hr + dissolved_drtn_hr + succ_lag_hr.
    """

    # ---- Test 1: single pred, single succ ------------------------------------

    def test_single_pred_single_succ_happy_path(self):
        """A FS→D FS→B, D duration=16h.  Dissolve D:
        - New edge A FS→B with lag=16h created.
        - Original A→D and D→B edges removed.
        - D removed from TASK.
        """
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("101", "A"),
                _task_row("200", "D", drtn="16"),
                _task_row("103", "B"),
            ],
            taskpred_rows=[
                _tp_row("1", "200", "101", "PR_FS", "0"),  # A FS→D lag=0
                _tp_row("2", "103", "200", "PR_FS", "0"),  # D FS→B lag=0
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)

        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")

        # D is gone from TASK
        task_codes = {r["task_code"] for r in task.rows}
        self.assertNotIn("D", task_codes)
        self.assertIn("A", task_codes)
        self.assertIn("B", task_codes)

        # Exactly one edge remains: A→B
        self.assertEqual(len(tp.rows), 1)
        new_edge = tp.rows[0]
        self.assertEqual(new_edge["pred_task_id"], "101")   # A
        self.assertEqual(new_edge["task_id"], "103")         # B
        self.assertEqual(new_edge["pred_type"], "PR_FS")     # FS×FS → FS
        self.assertEqual(new_edge["lag_hr_cnt"], "16")       # 0 + 16 + 0

        # Feedback
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["removed_edges_count"], 2)
        self.assertEqual(fb["new_edges_count"], 1)
        self.assertFalse(fb["fanout_warning"])

    # ---- Test 2: cartesian fanout (2 preds × 2 succs) -------------------------

    def test_cartesian_fanout_two_by_two(self):
        """A1,A2 FS→D FS→B1,B2; D duration=8h; dissolve D → 4 new edges."""
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("10", "A1"),
                _task_row("20", "A2"),
                _task_row("50", "D", drtn="8"),
                _task_row("60", "B1"),
                _task_row("70", "B2"),
            ],
            taskpred_rows=[
                _tp_row("1", "50", "10", "PR_FS", "0"),   # A1 FS→D
                _tp_row("2", "50", "20", "PR_FS", "0"),   # A2 FS→D
                _tp_row("3", "60", "50", "PR_FS", "0"),   # D FS→B1
                _tp_row("4", "70", "50", "PR_FS", "0"),   # D FS→B2
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 4)

        # All D-related edges gone; 4 new edges A1→B1, A1→B2, A2→B1, A2→B2
        new_pairs = {(r["pred_task_id"], r["task_id"]) for r in tp.rows}
        self.assertIn(("10", "60"), new_pairs)
        self.assertIn(("10", "70"), new_pairs)
        self.assertIn(("20", "60"), new_pairs)
        self.assertIn(("20", "70"), new_pairs)

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_edges_count"], 4)
        self.assertFalse(fb["fanout_warning"])

    # ---- Test 3: composition table SS×FS → SS ---------------------------------

    def test_composition_ss_fs_yields_ss(self):
        """A SS→D FS→B, D duration=16h: new edge A SS→B, lag=0+16+0=16h."""
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("101", "A"),
                _task_row("200", "D", drtn="16"),
                _task_row("103", "B"),
            ],
            taskpred_rows=[
                _tp_row("1", "200", "101", "PR_SS", "0"),  # A SS→D
                _tp_row("2", "103", "200", "PR_FS", "0"),  # D FS→B
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 1)
        new_edge = tp.rows[0]
        self.assertEqual(new_edge["pred_type"], "PR_SS")   # SS×FS → SS (S+S)
        self.assertEqual(new_edge["lag_hr_cnt"], "16")

    # ---- Test 4: all 16 composition combinations (parametrized via subTest) ---

    def test_all_16_composition_combinations(self):
        """_compose_dissolve(pred_rel, succ_rel) == pred_rel[0] + succ_rel[1] for all 16."""
        from xer_modify import _compose_dissolve

        rel_types = ["FS", "SS", "FF", "SF"]
        expected = {
            ("FS", "FS"): "FS",
            ("FS", "SS"): "FS",
            ("FS", "FF"): "FF",
            ("FS", "SF"): "FF",
            ("SS", "FS"): "SS",
            ("SS", "SS"): "SS",
            ("SS", "FF"): "SF",
            ("SS", "SF"): "SF",
            ("FF", "FS"): "FS",
            ("FF", "SS"): "FS",
            ("FF", "FF"): "FF",
            ("FF", "SF"): "FF",
            ("SF", "FS"): "SS",
            ("SF", "SS"): "SS",
            ("SF", "FF"): "SF",
            ("SF", "SF"): "SF",
        }
        for pred_rel in rel_types:
            for succ_rel in rel_types:
                with self.subTest(pred_rel=pred_rel, succ_rel=succ_rel):
                    result = _compose_dissolve(pred_rel, succ_rel)
                    self.assertEqual(result, expected[(pred_rel, succ_rel)])

    # ---- Test 5: 0 predecessors, N successors → no new edges -----------------

    def test_zero_preds_n_succs_removes_only(self):
        """D has 0 preds, 2 succs: dissolve removes D and its 2 succ-edges; no new edges."""
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("50", "D", drtn="8"),
                _task_row("60", "B1"),
                _task_row("70", "B2"),
            ],
            taskpred_rows=[
                _tp_row("1", "60", "50", "PR_FS", "0"),   # D FS→B1
                _tp_row("2", "70", "50", "PR_FS", "0"),   # D FS→B2
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 0)

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_edges_count"], 0)
        self.assertEqual(fb["removed_edges_count"], 2)
        self.assertFalse(fb["fanout_warning"])

    # ---- Test 6: N predecessors, 0 successors → no new edges -----------------

    def test_n_preds_zero_succs_removes_only(self):
        """D has 2 preds, 0 succs: dissolve removes D and its 2 pred-edges; no new edges."""
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("10", "A1"),
                _task_row("20", "A2"),
                _task_row("50", "D", drtn="8"),
            ],
            taskpred_rows=[
                _tp_row("1", "50", "10", "PR_FS", "0"),   # A1 FS→D
                _tp_row("2", "50", "20", "PR_FS", "0"),   # A2 FS→D
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 0)

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_edges_count"], 0)
        self.assertEqual(fb["removed_edges_count"], 2)

    # ---- Test 7: 0 preds, 0 succs → just remove D ----------------------------

    def test_zero_preds_zero_succs_removes_task_only(self):
        """Isolated D: no edges, no new edges; just D removed from TASK."""
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("50", "D", drtn="8"),
                _task_row("60", "B"),
            ],
            taskpred_rows=[],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        task = result.doc.section("TASK")
        self.assertEqual(len(task.rows), 1)
        self.assertEqual(task.rows[0]["task_code"], "B")

        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 0)

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_edges_count"], 0)
        self.assertEqual(fb["removed_edges_count"], 0)

    # ---- Test 8: activity not found → ValidationFailure ----------------------

    def test_activity_not_found_raises(self):
        """dissolve_activity raises ValidationFailure for unknown activity_id."""
        doc = _make_dissolve_doc(
            task_rows=[_task_row("101", "A")],
            taskpred_rows=[],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "ZZZZ"}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZZ", result.validation_errors[0].message)

    # ---- Test 9: duplicate edge → ValidationFailure --------------------------

    def test_duplicate_edge_raises(self):
        """A already has FS→B in TASKPRED; dissolve D (A→D→B) would create A FS→B duplicate."""
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("101", "A"),
                _task_row("200", "D", drtn="8"),
                _task_row("103", "B"),
            ],
            taskpred_rows=[
                _tp_row("1", "200", "101", "PR_FS", "0"),  # A FS→D
                _tp_row("2", "103", "200", "PR_FS", "0"),  # D FS→B
                # Pre-existing A→B edge — would be duplicated by dissolve
                _tp_row("3", "103", "101", "PR_FS", "0"),  # A FS→B
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A", err)
        self.assertIn("B", err)

    # ---- Test 10: fanout warning (5×5 = 25 new edges) -------------------------

    def test_fanout_warning_twenty_five_edges(self):
        """5 preds × 5 succs = 25 new edges; fanout_warning=True."""
        task_rows = [_task_row(str(i), f"P{i}") for i in range(1, 6)]
        task_rows += [_task_row("50", "D", drtn="8")]
        task_rows += [_task_row(str(i + 60), f"S{i}") for i in range(1, 6)]

        # D's preds: P1-P5 → D
        pred_rows = [_tp_row(str(i), "50", str(i), "PR_FS", "0") for i in range(1, 6)]
        # D's succs: D → S1-S5
        succ_rows = [_tp_row(str(i + 10), str(i + 60), "50", "PR_FS", "0") for i in range(1, 6)]

        doc = _make_dissolve_doc(
            task_rows=task_rows,
            taskpred_rows=pred_rows + succ_rows,
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_edges_count"], 25)
        self.assertTrue(fb["fanout_warning"])

    # ---- Test 11: lag math with non-zero lags on both sides -------------------

    def test_lag_math_with_lags(self):
        """A FS+8→D (lag=8h); D duration=24h; D FS+16→B (lag=16h).
        New lag = 8 + 24 + 16 = 48h.
        """
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("101", "A"),
                _task_row("200", "D", drtn="24"),
                _task_row("103", "B"),
            ],
            taskpred_rows=[
                _tp_row("1", "200", "101", "PR_FS", "8"),   # A FS+8→D
                _tp_row("2", "103", "200", "PR_FS", "16"),  # D FS+16→B
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 1)
        self.assertEqual(tp.rows[0]["lag_hr_cnt"], "48")   # 8 + 24 + 16

    # ---- Test 12: task_pred_id generation respects pre-removal max ------------

    def test_task_pred_id_generation_respects_pre_removal_max(self):
        """TASKPRED has IDs {1,2,3,4} where 2 and 3 reference D.
        After dissolve with 1 new edge, new edge gets task_pred_id='5' (not 3 or 4).
        """
        doc = _make_dissolve_doc(
            task_rows=[
                _task_row("101", "A"),
                _task_row("200", "D", drtn="8"),
                _task_row("103", "B"),
                _task_row("104", "C"),  # unrelated task
            ],
            taskpred_rows=[
                # ID=1: unrelated edge (A→C)
                _tp_row("1", "104", "101", "PR_FS", "0"),
                # ID=2: A FS→D  (D as successor)
                _tp_row("2", "200", "101", "PR_FS", "0"),
                # ID=3: D FS→B  (D as predecessor)
                _tp_row("3", "103", "200", "PR_FS", "0"),
                # ID=4: unrelated edge (A→C, different type)
                _tp_row("4", "104", "101", "PR_SS", "0"),
            ],
        )
        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        # Original: 4 rows; 2 removed (IDs 2,3); 1 new added.
        # Remaining rows: ID=1 (A→C FS), ID=4 (A→C SS), new edge (A→B FS).
        self.assertEqual(len(tp.rows), 3)

        # New edge should have task_pred_id = "5" (max of original {1,2,3,4} + 1)
        new_edge = next(
            r for r in tp.rows
            if r["pred_task_id"] == "101" and r["task_id"] == "103"
        )
        self.assertEqual(new_edge["task_pred_id"], "5")

    # ---- Test 13: state.removed_activity_ids populated -----------------------

    def test_state_removed_activity_ids_populated(self):
        """dissolve_activity adds the dissolved activity_id to state.removed_activity_ids."""
        from xer_modify import _HANDLERS, ChangeState

        doc = _make_dissolve_doc(
            task_rows=[_task_row("200", "D", drtn="8")],
            taskpred_rows=[],
        )
        state = ChangeState()
        _HANDLERS["dissolve_activity"](
            doc,
            {"type": "dissolve_activity", "activity_id": "D"},
            state,
        )
        self.assertIn("D", state.removed_activity_ids)

    # ---- Test 14: TASKPRED _dirty re-indexed correctly -----------------------

    def test_dirty_reindex_after_dissolve(self):
        """5 TASKPRED rows; rows 1 and 2 reference D; rows 0 and 4 are dirty.
        After dissolve: rows 1 and 2 removed, 1 new row appended.
        Surviving rows are originals [0,3,4] at new indices [0,1,2].
        Original dirty {0,4} → new dirty {0,2}; appended new row is also dirty.
        """
        from xer_io import XerDoc, XerSection

        task_field_order = [
            "task_id", "proj_id", "task_code",
            "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
        ]
        taskpred_field_order = [
            "task_pred_id", "task_id", "pred_task_id",
            "proj_id", "pred_proj_id",
            "pred_type", "lag_hr_cnt",
            "comments", "float_path", "aref", "arls",
        ]

        def _raw_task(r):
            return "%R\t" + "\t".join(r.get(f, "") for f in task_field_order)

        def _raw_tp(r):
            return "%R\t" + "\t".join(r.get(f, "") for f in taskpred_field_order)

        task_rows = [
            _task_row("101", "A"),
            _task_row("200", "D", drtn="8"),
            _task_row("103", "B"),
            _task_row("104", "C"),
        ]
        tp_rows = [
            _tp_row("1", "104", "101", "PR_FS", "0"),  # idx 0: A→C (unrelated)
            _tp_row("2", "200", "101", "PR_FS", "0"),  # idx 1: A→D  (D as succ)
            _tp_row("3", "103", "200", "PR_FS", "0"),  # idx 2: D→B  (D as pred)
            _tp_row("4", "103", "101", "PR_SS", "0"),  # idx 3: A→B SS (unrelated)
            _tp_row("5", "104", "103", "PR_FS", "0"),  # idx 4: B→C (unrelated)
        ]

        task_section = XerSection(
            name="TASK",
            field_order=task_field_order,
            rows=task_rows,
            raw_lines=[_raw_task(r) for r in task_rows],
            e_line=None,
        )
        taskpred_section = XerSection(
            name="TASKPRED",
            field_order=taskpred_field_order,
            rows=tp_rows,
            raw_lines=[_raw_tp(r) for r in tp_rows],
            e_line=None,
        )
        # Pre-seed dirty: original rows 0 and 4
        taskpred_section._dirty = {0, 4}

        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section, taskpred_section],
        )

        result = apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )

        tp = result.doc.section("TASKPRED")
        # Rows removed: idx 1 (A→D) and idx 2 (D→B); 1 new row appended (A→B FS).
        # Final rows: A→C(FS), A→B(SS), B→C, A→B(FS) — 4 rows total
        self.assertEqual(len(tp.rows), 4)

        # Original idx 0 (A→C FS) → new idx 0; dirty stays at 0
        # Original idx 3 (A→B SS) → new idx 1; was not dirty
        # Original idx 4 (B→C) → new idx 2; dirty was 4 → now 2
        # Appended row → new idx 3; always dirty
        self.assertIn(0, tp._dirty)       # original row 0
        self.assertIn(2, tp._dirty)       # original row 4 → shifted to 2
        self.assertTrue(tp.is_dirty(3))   # newly appended row (no raw_lines entry)


# ---------------------------------------------------------------------------
# Helpers for TestPopActivity
# ---------------------------------------------------------------------------

def _make_pop_doc(
    task_rows: list[dict],
    taskpred_rows: list[dict],
    extra_sections: list | None = None,
):
    """Build an in-memory XerDoc with TASK, TASKPRED, PROJWBS, and CALENDAR sections.

    PROJWBS has one row (wbs_id="1000").
    CALENDAR has one row (clndr_id="100").
    task_rows: dicts with at least task_id, proj_id, task_code,
               target_drtn_hr_cnt, remain_drtn_hr_cnt.
    taskpred_rows: dicts conforming to _tp_row() shape.
    """
    from xer_io import XerDoc, XerSection

    task_field_order = [
        "task_id", "proj_id", "wbs_id", "clndr_id",
        "task_code", "task_name", "task_type", "duration_type",
        "status_code", "complete_pct_type", "phys_complete_pct",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    ]
    taskpred_field_order = [
        "task_pred_id", "task_id", "pred_task_id",
        "proj_id", "pred_proj_id",
        "pred_type", "lag_hr_cnt",
        "comments", "float_path", "aref", "arls",
    ]
    wbs_field_order = ["wbs_id", "proj_id", "wbs_name"]
    cal_field_order = ["clndr_id", "clndr_name"]

    def _raw_task(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in task_field_order)

    def _raw_tp(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in taskpred_field_order)

    # Ensure all task rows have the full field_order set (fill defaults)
    full_task_rows = []
    for r in task_rows:
        row = {f: "" for f in task_field_order}
        row.update(r)
        if not row.get("wbs_id"):
            row["wbs_id"] = "1000"
        if not row.get("clndr_id"):
            row["clndr_id"] = "100"
        if not row.get("task_type"):
            row["task_type"] = "TT_Task"
        if not row.get("status_code"):
            row["status_code"] = "TK_NotStart"
        if not row.get("duration_type"):
            row["duration_type"] = "DT_FixedDUR2"
        if not row.get("complete_pct_type"):
            row["complete_pct_type"] = "CP_Drtn"
        if not row.get("phys_complete_pct"):
            row["phys_complete_pct"] = "0"
        full_task_rows.append(row)

    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=full_task_rows,
        raw_lines=[_raw_task(r) for r in full_task_rows],
        e_line=None,
    )
    taskpred_section = XerSection(
        name="TASKPRED",
        field_order=taskpred_field_order,
        rows=taskpred_rows,
        raw_lines=[_raw_tp(r) for r in taskpred_rows],
        e_line=None,
    )
    wbs_section = XerSection(
        name="PROJWBS",
        field_order=wbs_field_order,
        rows=[{"wbs_id": "1000", "proj_id": "1", "wbs_name": "Root"}],
        raw_lines=["%R\t1000\t1\tRoot"],
        e_line=None,
    )
    cal_section = XerSection(
        name="CALENDAR",
        field_order=cal_field_order,
        rows=[{"clndr_id": "100", "clndr_name": "Standard"}],
        raw_lines=["%R\t100\tStandard"],
        e_line=None,
    )
    sections = [task_section, taskpred_section, wbs_section, cal_section]
    if extra_sections:
        sections.extend(extra_sections)
    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=sections,
    )


def _pop_task_row(task_id, task_code, drtn="16"):
    """Minimal TASK row dict for pop_activity tests."""
    return {
        "task_id": task_id,
        "proj_id": "1",
        "task_code": task_code,
        "target_drtn_hr_cnt": drtn,
        "remain_drtn_hr_cnt": drtn,
    }


def _pop_change(
    pred_id="A",
    succ_id="B",
    split_lag="preserve_total",
    **spec_overrides,
):
    """Build a minimal pop_activity change record."""
    spec = {
        "code": "X",
        "name": "Inserted Task",
        "duration_days": 1,
        "calendar_id": "100",
        "wbs_id": "1000",
        "activity_type": "TT_Task",
    }
    spec.update(spec_overrides)
    return {
        "type": "pop_activity",
        "predecessor_id": pred_id,
        "successor_id": succ_id,
        "spec": spec,
        "split_lag": split_lag,
    }


class TestPopActivity(unittest.TestCase):
    """Tests for the pop_activity change handler (D10).

    pop_activity inserts a new activity X between an existing (pred, succ) edge:
      - removes the original A→B edge
      - adds A→X (pred_type=original, lag=0)
      - adds X→B (pred_type=original, lag=original if preserve_total else 0)
    """

    # ---- Shared helpers -------------------------------------------------------

    def _two_task_doc_with_edge(self, pred_type="PR_FS", lag="16", tpid="3"):
        """A (task_id=101) and B (task_id=102) with one TASKPRED edge."""
        return _make_pop_doc(
            task_rows=[
                _pop_task_row("101", "A"),
                _pop_task_row("102", "B"),
            ],
            taskpred_rows=[
                _tp_row(tpid, "102", "101", pred_type, lag),
            ],
        )

    # ---- Test 1: happy path preserve_total -------------------------------------

    def test_happy_path_preserve_total(self):
        """A FS→B lag=16h; pop X with preserve_total:
        - A→X: FS lag=0
        - X→B: FS lag=16h
        - TASK: 3 rows (A, B, X)
        - TASKPRED: 2 rows (was 1)
        """
        doc = self._two_task_doc_with_edge(pred_type="PR_FS", lag="16", tpid="3")
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", split_lag="preserve_total",
                         code="X", duration_days=1)],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)

        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")

        # TASK: A, B, X
        self.assertEqual(len(task.rows), 3)
        codes = {r["task_code"] for r in task.rows}
        self.assertIn("X", codes)

        # TASKPRED: exactly 2 rows
        self.assertEqual(len(tp.rows), 2)

        # Locate A→X and X→B rows
        x_task_id = next(r["task_id"] for r in task.rows if r["task_code"] == "X")
        ax_row = next(
            (r for r in tp.rows if r["pred_task_id"] == "101" and r["task_id"] == x_task_id),
            None,
        )
        xb_row = next(
            (r for r in tp.rows if r["pred_task_id"] == x_task_id and r["task_id"] == "102"),
            None,
        )
        self.assertIsNotNone(ax_row, "A→X edge not found")
        self.assertIsNotNone(xb_row, "X→B edge not found")

        # A→X: FS, lag=0
        self.assertEqual(ax_row["pred_type"], "PR_FS")
        self.assertEqual(ax_row["lag_hr_cnt"], "0")

        # X→B: FS, lag=original (16)
        self.assertEqual(xb_row["pred_type"], "PR_FS")
        self.assertEqual(xb_row["lag_hr_cnt"], "16")

        # Feedback shape: 5 business values + 4 CPM stubs
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_x_task_id"], x_task_id)
        self.assertEqual(fb["new_x_task_code"], "X")
        self.assertEqual(fb["removed_edge_relationship"], "FS")
        self.assertEqual(fb["removed_edge_lag_days"], 2)
        self.assertEqual(fb["split_policy_applied"], "preserve_total")
        self.assertIsNone(fb["activity_end_before"])
        self.assertIsNone(fb["activity_end_after"])
        self.assertIsNone(fb["milestone_impact_days"])
        self.assertIsNone(fb["now_on_critical_path"])

    # ---- Test 2: happy path drop -----------------------------------------------

    def test_happy_path_drop(self):
        """A FS→B lag=16h; pop X with split_lag='drop': X→B lag=0."""
        doc = self._two_task_doc_with_edge(pred_type="PR_FS", lag="16", tpid="3")
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", split_lag="drop",
                         code="X", duration_days=1)],
            strict=False,
            dry_run=False,
        )
        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")

        x_task_id = next(r["task_id"] for r in task.rows if r["task_code"] == "X")
        xb_row = next(
            (r for r in tp.rows if r["pred_task_id"] == x_task_id and r["task_id"] == "102"),
            None,
        )
        self.assertIsNotNone(xb_row)
        self.assertEqual(xb_row["lag_hr_cnt"], "0")

    # ---- Test 3: SS inheritance ------------------------------------------------

    def test_ss_relationship_inherited(self):
        """A SS→B lag=8h; pop X: both A→X and X→B are SS (not FS)."""
        doc = self._two_task_doc_with_edge(pred_type="PR_SS", lag="8", tpid="3")
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", split_lag="preserve_total",
                         code="X")],
            strict=False,
            dry_run=False,
        )
        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")
        x_task_id = next(r["task_id"] for r in task.rows if r["task_code"] == "X")

        ax_row = next(r for r in tp.rows if r["pred_task_id"] == "101" and r["task_id"] == x_task_id)
        xb_row = next(r for r in tp.rows if r["pred_task_id"] == x_task_id and r["task_id"] == "102")

        self.assertEqual(ax_row["pred_type"], "PR_SS")
        self.assertEqual(xb_row["pred_type"], "PR_SS")
        self.assertEqual(xb_row["lag_hr_cnt"], "8")   # preserve_total

    # ---- Test 4: FF inheritance ------------------------------------------------

    def test_ff_relationship_inherited(self):
        """A FF→B lag=8h; pop X: both A→X and X→B are FF."""
        doc = self._two_task_doc_with_edge(pred_type="PR_FF", lag="8", tpid="3")
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", split_lag="preserve_total",
                         code="X")],
            strict=False,
            dry_run=False,
        )
        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")
        x_task_id = next(r["task_id"] for r in task.rows if r["task_code"] == "X")

        ax_row = next(r for r in tp.rows if r["pred_task_id"] == "101" and r["task_id"] == x_task_id)
        xb_row = next(r for r in tp.rows if r["pred_task_id"] == x_task_id and r["task_id"] == "102")

        self.assertEqual(ax_row["pred_type"], "PR_FF")
        self.assertEqual(xb_row["pred_type"], "PR_FF")
        self.assertEqual(xb_row["lag_hr_cnt"], "8")

    # ---- Test 5: predecessor not found → ValidationFailure --------------------

    def test_predecessor_not_found_raises(self):
        """predecessor_id not in TASK → ValidationFailure naming the missing id."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="ZZZPRED", succ_id="B")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZPRED", result.validation_errors[0].message)

    # ---- Test 6: successor not found → ValidationFailure ----------------------

    def test_successor_not_found_raises(self):
        """successor_id not in TASK → ValidationFailure naming the missing id."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="ZZZSUCC")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("ZZZSUCC", result.validation_errors[0].message)

    # ---- Test 7: edge not found → ValidationFailure ---------------------------

    def test_edge_not_found_raises(self):
        """A and B exist in TASK but no TASKPRED row between them → ValidationFailure."""
        doc = _make_pop_doc(
            task_rows=[
                _pop_task_row("101", "A"),
                _pop_task_row("102", "B"),
                _pop_task_row("103", "C"),
            ],
            taskpred_rows=[
                # edge between C and B, not A and B
                _tp_row("1", "102", "103", "PR_FS", "0"),
            ],
        )
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A", err)
        self.assertIn("B", err)

    # ---- Test 8: multiple edges (ambiguous) → ValidationFailure ---------------

    def test_multiple_edges_between_pred_succ_raises(self):
        """Both FS and SS exist between A and B → ValidationFailure (ambiguous)."""
        doc = _make_pop_doc(
            task_rows=[
                _pop_task_row("101", "A"),
                _pop_task_row("102", "B"),
            ],
            taskpred_rows=[
                _tp_row("1", "102", "101", "PR_FS", "0"),
                _tp_row("2", "102", "101", "PR_SS", "8"),
            ],
        )
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("A", err)
        self.assertIn("B", err)

    # ---- Test 9: missing spec field → ValidationFailure -----------------------

    def test_missing_spec_field_raises(self):
        """Omit 'code' from spec → ValidationFailure naming the missing field."""
        doc = self._two_task_doc_with_edge()
        change = {
            "type": "pop_activity",
            "predecessor_id": "A",
            "successor_id": "B",
            "spec": {
                # code intentionally omitted
                "name": "New",
                "duration_days": 1,
                "calendar_id": "100",
                "wbs_id": "1000",
                "activity_type": "TT_Task",
            },
            "split_lag": "preserve_total",
        }
        result = apply_changes(doc, [change], strict=False, dry_run=False)
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("code", result.validation_errors[0].message)

    # ---- Test 10: duplicate X code → ValidationFailure -------------------------

    def test_duplicate_x_code_raises(self):
        """X's code already exists in TASK → ValidationFailure."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            # "A" already exists in TASK
            [_pop_change(pred_id="A", succ_id="B", code="A")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("A", result.validation_errors[0].message)

    # ---- Test 11: unknown wbs_id / calendar_id / activity_type ----------------

    def test_unknown_wbs_id_raises(self):
        """wbs_id not in PROJWBS → ValidationFailure."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", wbs_id="9999")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("9999", result.validation_errors[0].message)

    def test_unknown_calendar_id_raises(self):
        """calendar_id not in CALENDAR → ValidationFailure."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", calendar_id="999")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("999", result.validation_errors[0].message)

    def test_unknown_activity_type_raises(self):
        """activity_type not in _ACTIVITY_TYPES → ValidationFailure."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", activity_type="TT_Bogus")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("TT_Bogus", result.validation_errors[0].message)

    # ---- Test 12: negative duration → ValidationFailure -----------------------

    def test_negative_duration_raises(self):
        """duration_days=-1 → ValidationFailure."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", duration_days=-1)],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("-1", result.validation_errors[0].message)

    # ---- Test 13: bad split_lag value → ValidationFailure ---------------------

    def test_bad_split_lag_raises(self):
        """split_lag='partial' (not a valid enum) → ValidationFailure."""
        doc = self._two_task_doc_with_edge()
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", split_lag="partial")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("partial", result.validation_errors[0].message)

    # ---- Test 14: state propagation -------------------------------------------

    def test_state_propagation(self):
        """After pop_activity: state.new_activity_ids contains X's code,
        state.new_activity_id_map[X.code] == X's numeric task_id."""
        from xer_modify import _HANDLERS, ChangeState

        doc = self._two_task_doc_with_edge()
        state = ChangeState()
        _HANDLERS["pop_activity"](
            doc,
            _pop_change(pred_id="A", succ_id="B", code="X"),
            state,
        )
        self.assertIn("X", state.new_activity_ids)
        x_task_id = state.new_activity_id_map["X"]
        # Verify the task_id maps to the actual row in TASK
        task = doc.section("TASK")
        x_row = next((r for r in task.rows if r["task_code"] == "X"), None)
        self.assertIsNotNone(x_row)
        self.assertEqual(x_row["task_id"], x_task_id)

    # ---- Test 15: task_pred_id generation -------------------------------------

    def test_task_pred_id_generation(self):
        """Original edge has task_pred_id='3'; max existing is '5'.
        After pop_activity, the two new edges get IDs '6' and '7'."""
        doc = _make_pop_doc(
            task_rows=[
                _pop_task_row("101", "A"),
                _pop_task_row("102", "B"),
            ],
            taskpred_rows=[
                # Unrelated edges with higher IDs to set max=5
                _tp_row("3", "102", "101", "PR_FS", "0"),   # A→B, the target edge
                _tp_row("4", "101", "101", "PR_SS", "0"),   # self-ref filler (not realistic but valid for ID sequencing)
                _tp_row("5", "102", "102", "PR_FF", "0"),   # filler
            ],
        )
        # Remove the self-ref filler rows; use a simpler approach:
        # Build doc with IDs 3,4,5 present; target edge is 3 (A→B)
        # After pop: max pre-removal=5; new edges get 6 and 7.
        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", code="X")],
            strict=False,
            dry_run=False,
        )
        tp = result.doc.section("TASKPRED")
        # Only the two new edges and the surviving fillers remain
        task = result.doc.section("TASK")
        x_task_id = next(r["task_id"] for r in task.rows if r["task_code"] == "X")

        ax_row = next(r for r in tp.rows if r["pred_task_id"] == "101" and r["task_id"] == x_task_id)
        xb_row = next(r for r in tp.rows if r["pred_task_id"] == x_task_id and r["task_id"] == "102")

        new_ids = {ax_row["task_pred_id"], xb_row["task_pred_id"]}
        self.assertIn("6", new_ids)
        self.assertIn("7", new_ids)

    # ---- Test 16: TASK and TASKPRED row counts --------------------------------

    def test_task_and_taskpred_row_counts(self):
        """Pre: TASK=2 (A, B), TASKPRED=1 (A→B).
        Post: TASK=3 (A, X, B), TASKPRED=2 (A→X, X→B)."""
        doc = self._two_task_doc_with_edge()
        pre_task_count = len(doc.section("TASK").rows)
        pre_tp_count = len(doc.section("TASKPRED").rows)
        self.assertEqual(pre_task_count, 2)
        self.assertEqual(pre_tp_count, 1)

        result = apply_changes(
            doc,
            [_pop_change(pred_id="A", succ_id="B", code="X")],
            strict=False,
            dry_run=False,
        )
        task = result.doc.section("TASK")
        tp = result.doc.section("TASKPRED")

        self.assertEqual(len(task.rows), 3)
        self.assertEqual(len(tp.rows), 2)


# ---------------------------------------------------------------------------
# Helpers for TestAddWbs
# ---------------------------------------------------------------------------

def _make_doc_with_projwbs(wbs_rows=None):
    """Build a minimal in-memory XerDoc containing a PROJWBS section.

    Uses the real field_order observed from minimal.xer.  Defaults to a
    single root WBS row (wbs_id='1000', proj_id='1').
    """
    from xer_io import XerDoc, XerSection

    wbs_field_order = [
        "wbs_id", "proj_id", "obs_id", "seq_num", "est_wt",
        "proj_node_flag", "sum_data_flag", "status_code",
        "wbs_short_name", "wbs_name", "phase_id", "parent_wbs_id",
        "ev_user_pct", "ev_etc_user_value", "orig_cost",
        "indep_remain_total_cost", "ann_dscnt_rate_pct",
        "dscnt_period_type", "indep_remain_work_qty",
        "anticip_start_date", "anticip_end_date",
        "ev_compute_type", "ev_etc_compute_type",
        "guid", "tmpl_guid", "plan_open_state",
    ]

    if wbs_rows is None:
        wbs_rows = [
            {
                "wbs_id": "1000",
                "proj_id": "1",
                "obs_id": "",
                "seq_num": "1",
                "est_wt": "1",
                "proj_node_flag": "Y",
                "sum_data_flag": "N",
                "status_code": "WS_Open",
                "wbs_short_name": "ROOT",
                "wbs_name": "Root WBS Node",
                "phase_id": "",
                "parent_wbs_id": "",
                "ev_user_pct": "",
                "ev_etc_user_value": "0.0000",
                "orig_cost": "0.0000",
                "indep_remain_total_cost": "",
                "ann_dscnt_rate_pct": "",
                "dscnt_period_type": "",
                "indep_remain_work_qty": "",
                "anticip_start_date": "",
                "anticip_end_date": "",
                "ev_compute_type": "EC_Cmp_pct",
                "ev_etc_compute_type": "EE_PF_cpi",
                "guid": "TEST-WBS-GUID-001",
                "tmpl_guid": "",
                "plan_open_state": "",
            }
        ]

    def _raw(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in wbs_field_order)

    wbs_section = XerSection(
        name="PROJWBS",
        field_order=wbs_field_order,
        rows=wbs_rows,
        raw_lines=[_raw(r) for r in wbs_rows],
        e_line=None,
    )
    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[wbs_section],
    )


def _add_wbs_change(**spec_kwargs):
    """Return a minimal add_wbs change record.

    Defaults: wbs_code='WBS-CHILD', wbs_name='Building Enclosure',
    parent_wbs_id='1000'.  No wbs_short_name (derived by handler).
    """
    spec = {
        "wbs_code": "WBS-CHILD",
        "wbs_name": "Building Enclosure",
        "parent_wbs_id": "1000",
    }
    spec.update(spec_kwargs)
    return {"type": "add_wbs", "spec": spec}


class TestAddWbs(unittest.TestCase):
    """Tests for the add_wbs change handler (D11)."""

    # ---- Test 1: happy path with explicit wbs_short_name ---------------------

    def test_happy_path_explicit_short_name(self):
        """All fields provided including wbs_short_name; row appended correctly."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_short_name="BE")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        projwbs = result.doc.section("PROJWBS")
        self.assertEqual(len(projwbs.rows), 2)

        new_row = projwbs.rows[1]
        self.assertEqual(new_row["wbs_id"], "1001")          # max(1000)+1
        self.assertEqual(new_row["wbs_code"], "WBS-CHILD")
        self.assertEqual(new_row["wbs_name"], "Building Enclosure")
        self.assertEqual(new_row["wbs_short_name"], "BE")
        self.assertEqual(new_row["parent_wbs_id"], "1000")
        self.assertEqual(new_row["proj_id"], "1")            # copied from existing row

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["new_wbs_id"], "1001")
        self.assertFalse(fb["derived_short_name"])
        self.assertEqual(fb["wbs_short_name"], "BE")

    # ---- Test 2: derived wbs_short_name — two-word name ----------------------

    def test_derived_short_name_two_words(self):
        """wbs_name='Building Enclosure' without short_name → 'BE'; derived_short_name=True."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change()],   # default name is 'Building Enclosure'
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["wbs_short_name"], "BE")
        self.assertTrue(fb["derived_short_name"])
        projwbs = result.doc.section("PROJWBS")
        self.assertEqual(projwbs.rows[1]["wbs_short_name"], "BE")

    # ---- Test 3: derived — stop-words filtered --------------------------------

    def test_derived_short_name_stop_words_filtered(self):
        """'Permitting and Approvals' → 'PA' (skips 'and')."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_name="Permitting and Approvals")],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["wbs_short_name"], "PA")
        self.assertTrue(fb["derived_short_name"])

    # ---- Test 4: derived — hyphens treated as word separators ----------------

    def test_derived_short_name_hyphens_as_separators(self):
        """'MEP Rough-In' splits to ['MEP','Rough','In']; 'In' is stop-word → 'MR'."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_name="MEP Rough-In")],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        # 'In' is a stop-word → filtered out → "MEP" → 'M', "Rough" → 'R' → "MR"
        self.assertEqual(fb["wbs_short_name"], "MR")
        self.assertTrue(fb["derived_short_name"])

    # ---- Test 5: derived fails — single significant word → 1 char -----------

    def test_derived_short_name_single_word_raises(self):
        """'Closeout' → initials='C' → 1 char → ValidationFailure."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_name="Closeout")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("wbs_short_name", err)

    # ---- Test 6: derived fails — all stop-words → 0 chars -------------------

    def test_derived_short_name_all_stop_words_raises(self):
        """'the and of' → 0 initials → ValidationFailure."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_name="the and of")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("wbs_short_name", err)

    # ---- Test 7: caller-provided short_name too short → ValidationFailure ----

    def test_explicit_short_name_too_short_raises(self):
        """Caller provides wbs_short_name='X' (1 char) → ValidationFailure."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_short_name="X")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("wbs_short_name", err)

    # ---- Test 8: missing wbs_code → ValidationFailure ------------------------

    def test_missing_wbs_code_raises(self):
        """Spec without 'wbs_code' raises ValidationFailure naming the missing field."""
        doc = _make_doc_with_projwbs()
        change = {"type": "add_wbs", "spec": {
            "wbs_name": "Site Work",
            "parent_wbs_id": "1000",
        }}
        result = apply_changes(doc, [change], strict=False, dry_run=False)
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("wbs_code", result.validation_errors[0].message)

    # ---- Test 9: missing wbs_name → ValidationFailure ------------------------

    def test_missing_wbs_name_raises(self):
        """Spec without 'wbs_name' raises ValidationFailure naming the missing field."""
        doc = _make_doc_with_projwbs()
        change = {"type": "add_wbs", "spec": {
            "wbs_code": "WBS-SW",
            "parent_wbs_id": "1000",
        }}
        result = apply_changes(doc, [change], strict=False, dry_run=False)
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("wbs_name", result.validation_errors[0].message)

    # ---- Test 10: missing parent_wbs_id → ValidationFailure -----------------

    def test_missing_parent_wbs_id_raises(self):
        """Spec without 'parent_wbs_id' raises ValidationFailure naming the missing field."""
        doc = _make_doc_with_projwbs()
        change = {"type": "add_wbs", "spec": {
            "wbs_code": "WBS-SW",
            "wbs_name": "Site Work",
        }}
        result = apply_changes(doc, [change], strict=False, dry_run=False)
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("parent_wbs_id", result.validation_errors[0].message)

    # ---- Test 11: duplicate wbs_code → ValidationFailure --------------------

    def test_duplicate_wbs_code_raises(self):
        """wbs_code already exists in PROJWBS → ValidationFailure naming the code."""
        wbs_rows = [
            {
                "wbs_id": "1000", "proj_id": "1", "obs_id": "", "seq_num": "1",
                "est_wt": "1", "proj_node_flag": "Y", "sum_data_flag": "N",
                "status_code": "WS_Open", "wbs_short_name": "ROOT",
                "wbs_name": "Root", "phase_id": "", "parent_wbs_id": "",
                "ev_user_pct": "", "ev_etc_user_value": "0.0000",
                "orig_cost": "0.0000", "indep_remain_total_cost": "",
                "ann_dscnt_rate_pct": "", "dscnt_period_type": "",
                "indep_remain_work_qty": "", "anticip_start_date": "",
                "anticip_end_date": "", "ev_compute_type": "EC_Cmp_pct",
                "ev_etc_compute_type": "EE_PF_cpi", "guid": "G1",
                "tmpl_guid": "", "plan_open_state": "",
            },
            {
                "wbs_id": "1001", "proj_id": "1", "obs_id": "", "seq_num": "2",
                "est_wt": "1", "proj_node_flag": "N", "sum_data_flag": "N",
                "status_code": "WS_Open", "wbs_short_name": "EX",
                "wbs_name": "Existing Child", "phase_id": "", "parent_wbs_id": "1000",
                "ev_user_pct": "", "ev_etc_user_value": "0.0000",
                "orig_cost": "0.0000", "indep_remain_total_cost": "",
                "ann_dscnt_rate_pct": "", "dscnt_period_type": "",
                "indep_remain_work_qty": "", "anticip_start_date": "",
                "anticip_end_date": "", "ev_compute_type": "EC_Cmp_pct",
                "ev_etc_compute_type": "EE_PF_cpi", "guid": "G2",
                "tmpl_guid": "", "plan_open_state": "",
                "wbs_code": "WBS-DUP",
            },
        ]
        # Patch wbs_code into row[0] too so the field is available
        wbs_rows[0]["wbs_code"] = "WBS-ROOT"
        doc = _make_doc_with_projwbs(wbs_rows=wbs_rows)
        # Add wbs_code to the section's field_order for this test
        doc.section("PROJWBS").field_order.append("wbs_code")
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_code="WBS-DUP", wbs_short_name="WD")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("WBS-DUP", err)

    # ---- Test 12: parent wbs_id not found → ValidationFailure ---------------

    def test_parent_wbs_id_not_found_raises(self):
        """parent_wbs_id='9999' not in PROJWBS and not in state → ValidationFailure."""
        doc = _make_doc_with_projwbs()
        result = apply_changes(
            doc,
            [_add_wbs_change(parent_wbs_id="9999", wbs_short_name="SW")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("9999", err)

    # ---- Test 13: parent satisfied by state.new_wbs_ids ---------------------

    def test_parent_satisfied_by_state_new_wbs_ids(self):
        """parent_wbs_id='999' pre-seeded in state.new_wbs_ids → handler succeeds."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_projwbs()
        state = ChangeState(new_wbs_ids={"999"})
        feedback = _HANDLERS["add_wbs"](
            doc,
            _add_wbs_change(parent_wbs_id="999", wbs_short_name="SW"),
            state,
        )
        projwbs = doc.section("PROJWBS")
        self.assertEqual(len(projwbs.rows), 2)
        self.assertEqual(projwbs.rows[1]["parent_wbs_id"], "999")
        self.assertIn("new_wbs_id", feedback)

    # ---- Test 14: no PROJWBS section → ValidationFailure --------------------

    def test_no_projwbs_section_raises(self):
        """Doc with no PROJWBS section raises ValidationFailure."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code"],
            rows=[{"task_id": "1", "task_code": "A1010"}],
            raw_lines=["%R\t1\tA1010"],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section],
        )
        result = apply_changes(
            doc,
            [_add_wbs_change(wbs_short_name="SW")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("PROJWBS", err)

    # ---- Test 15: wbs_id generation from non-contiguous ids -----------------

    def test_wbs_id_generation_non_contiguous(self):
        """PROJWBS has wbs_ids {1, 5, 3}; new wbs_id = '6'."""
        wbs_field_order = [
            "wbs_id", "proj_id", "obs_id", "seq_num", "est_wt",
            "proj_node_flag", "sum_data_flag", "status_code",
            "wbs_short_name", "wbs_name", "phase_id", "parent_wbs_id",
            "ev_user_pct", "ev_etc_user_value", "orig_cost",
            "indep_remain_total_cost", "ann_dscnt_rate_pct",
            "dscnt_period_type", "indep_remain_work_qty",
            "anticip_start_date", "anticip_end_date",
            "ev_compute_type", "ev_etc_compute_type",
            "guid", "tmpl_guid", "plan_open_state",
        ]

        def _row(wid, parent=""):
            return {f: "" for f in wbs_field_order} | {
                "wbs_id": str(wid), "proj_id": "1", "wbs_short_name": "XX",
                "wbs_name": "X", "parent_wbs_id": parent,
                "status_code": "WS_Open",
            }

        from xer_io import XerDoc, XerSection
        wbs_section = XerSection(
            name="PROJWBS",
            field_order=wbs_field_order,
            rows=[_row(1), _row(5, "1"), _row(3, "1")],
            raw_lines=["%R\t" + "\t".join(_row(wid).get(f, "") for f in wbs_field_order)
                       for wid in [1, 5, 3]],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[wbs_section],
        )
        result = apply_changes(
            doc,
            [_add_wbs_change(parent_wbs_id="1", wbs_short_name="SW")],
            strict=False,
            dry_run=False,
        )
        projwbs = result.doc.section("PROJWBS")
        new_row = projwbs.rows[-1]
        self.assertEqual(new_row["wbs_id"], "6")   # max(1,5,3)+1

    # ---- Test 16: state.new_wbs_ids populated after handler ------------------

    def test_state_new_wbs_ids_populated(self):
        """After add_wbs, state.new_wbs_ids contains the new wbs_id string."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_projwbs()
        state = ChangeState()
        feedback = _HANDLERS["add_wbs"](
            doc,
            _add_wbs_change(wbs_short_name="BE"),
            state,
        )
        new_id = feedback["new_wbs_id"]
        self.assertIn(new_id, state.new_wbs_ids)


# ---------------------------------------------------------------------------
# Helpers for TestRemoveWbs
# ---------------------------------------------------------------------------

def _make_doc_with_wbs_tree(extra_task_rows=None):
    """Build a doc with PROJWBS (root + 2 children + 1 grandchild) and TASK rows.

    WBS layout:
        wbs_id="10"  parent=""    → project root (no parent)
        wbs_id="20"  parent="10"  → child-A
        wbs_id="30"  parent="10"  → child-B
        wbs_id="40"  parent="20"  → grandchild-of-child-A

    TASK rows (all assigned to child-B unless extra_task_rows overrides):
        task_id="101" wbs_id="30"  task_code="T101"
        task_id="102" wbs_id="30"  task_code="T102"

    Callers may supply extra_task_rows to override or extend the task list.
    """
    from xer_io import XerDoc, XerSection

    wbs_field_order = [
        "wbs_id", "proj_id", "wbs_short_name", "wbs_name",
        "parent_wbs_id", "status_code",
    ]
    wbs_rows = [
        {"wbs_id": "10", "proj_id": "1", "wbs_short_name": "ROOT",
         "wbs_name": "Root", "parent_wbs_id": "", "status_code": "WS_Open"},
        {"wbs_id": "20", "proj_id": "1", "wbs_short_name": "CA",
         "wbs_name": "Child A", "parent_wbs_id": "10", "status_code": "WS_Open"},
        {"wbs_id": "30", "proj_id": "1", "wbs_short_name": "CB",
         "wbs_name": "Child B", "parent_wbs_id": "10", "status_code": "WS_Open"},
        {"wbs_id": "40", "proj_id": "1", "wbs_short_name": "GC",
         "wbs_name": "Grandchild", "parent_wbs_id": "20", "status_code": "WS_Open"},
    ]

    def _raw_wbs(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in wbs_field_order)

    wbs_section = XerSection(
        name="PROJWBS",
        field_order=wbs_field_order,
        rows=wbs_rows,
        raw_lines=[_raw_wbs(r) for r in wbs_rows],
        e_line=None,
    )

    task_field_order = [
        "task_id", "proj_id", "wbs_id", "task_code",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    ]
    if extra_task_rows is None:
        task_rows = [
            {"task_id": "101", "proj_id": "1", "wbs_id": "30",
             "task_code": "T101",
             "target_drtn_hr_cnt": "8", "remain_drtn_hr_cnt": "8"},
            {"task_id": "102", "proj_id": "1", "wbs_id": "30",
             "task_code": "T102",
             "target_drtn_hr_cnt": "8", "remain_drtn_hr_cnt": "8"},
        ]
    else:
        task_rows = extra_task_rows

    def _raw_task(r):
        return "%R\t" + "\t".join(r.get(f, "") for f in task_field_order)

    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=task_rows,
        raw_lines=[_raw_task(r) for r in task_rows],
        e_line=None,
    )

    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[wbs_section, task_section],
    )


def _remove_wbs_change(wbs_id: str, cascade: str):
    return {"type": "remove_wbs", "wbs_id": wbs_id, "cascade": cascade}


class TestRemoveWbs(unittest.TestCase):
    """Tests for the remove_wbs change handler (D12)."""

    # ---- Test 1: fail_if_used, no references — succeeds ----------------------

    def test_fail_if_used_no_references_succeeds(self):
        """WBS has no activities and no children; removed; state.removed_wbs_ids populated."""
        # child-A (wbs_id="20") has one child (wbs_id="40") but no tasks directly
        # We target grandchild "40" — it has no children and no tasks.
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("40", "fail_if_used")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        projwbs = result.doc.section("PROJWBS")
        wbs_ids = {r["wbs_id"] for r in projwbs.rows}
        self.assertNotIn("40", wbs_ids)
        self.assertEqual(len(projwbs.rows), 3)

        # Confirm state via direct handler call
        from xer_modify import _HANDLERS, ChangeState
        doc2 = _make_doc_with_wbs_tree()
        state = ChangeState()
        _HANDLERS["remove_wbs"](doc2, _remove_wbs_change("40", "fail_if_used"), state)
        self.assertIn("40", state.removed_wbs_ids)

    # ---- Test 2: fail_if_used, has activity reference → ValidationFailure ----

    def test_fail_if_used_has_activity_reference_raises(self):
        """WBS has TASK rows assigned → ValidationFailure naming the activity id(s)."""
        # child-B (wbs_id="30") has tasks T101 and T102
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("30", "fail_if_used")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        # Should mention at least one of the blocking task codes or the wbs_id
        self.assertTrue("T101" in err or "T102" in err or "30" in err)

    # ---- Test 3: fail_if_used, has child WBS → ValidationFailure -------------

    def test_fail_if_used_has_child_wbs_raises(self):
        """WBS has child PROJWBS rows → ValidationFailure naming the child wbs_id(s)."""
        # child-A (wbs_id="20") has grandchild wbs_id="40" as child, no tasks directly
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("20", "fail_if_used")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("40", err)

    # ---- Test 4: move_to_parent, no references — succeeds --------------------

    def test_move_to_parent_no_references_succeeds(self):
        """WBS has no activities and no children; removed cleanly."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("40", "move_to_parent")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        projwbs = result.doc.section("PROJWBS")
        wbs_ids = {r["wbs_id"] for r in projwbs.rows}
        self.assertNotIn("40", wbs_ids)
        self.assertEqual(len(projwbs.rows), 3)
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["reparented_task_count"], 0)
        self.assertEqual(fb["reparented_wbs_count"], 0)

    # ---- Test 5: move_to_parent, with activity references --------------------

    def test_move_to_parent_with_activity_references(self):
        """Tasks assigned to removed WBS are reparented to its parent."""
        # child-B (wbs_id="30") parent is root (wbs_id="10"); tasks T101 and T102
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("30", "move_to_parent")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task_section = result.doc.section("TASK")
        for row in task_section.rows:
            self.assertEqual(row["wbs_id"], "10",
                             f"task {row['task_code']} should be reparented to '10'")

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["reparented_task_count"], 2)
        self.assertEqual(fb["reparented_wbs_count"], 0)

        # Verify TASK rows are marked dirty
        for i in range(len(task_section.rows)):
            self.assertTrue(task_section.is_dirty(i),
                            f"task row {i} should be dirty after reparenting")

    # ---- Test 6: move_to_parent, with child WBS ------------------------------

    def test_move_to_parent_with_child_wbs(self):
        """Child WBS of removed WBS is reparented to removed WBS's parent."""
        # child-A (wbs_id="20") parent is root (wbs_id="10"); grandchild (wbs_id="40") points to "20"
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("20", "move_to_parent")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        projwbs = result.doc.section("PROJWBS")
        wbs_ids = {r["wbs_id"] for r in projwbs.rows}
        self.assertNotIn("20", wbs_ids)

        # grandchild "40" should now point to root "10"
        gc_row = next(r for r in projwbs.rows if r["wbs_id"] == "40")
        self.assertEqual(gc_row["parent_wbs_id"], "10")

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["reparented_wbs_count"], 1)
        self.assertEqual(fb["reparented_task_count"], 0)

    # ---- Test 7: move_to_parent, both activities and child WBS ---------------

    def test_move_to_parent_with_both_activities_and_child_wbs(self):
        """WBS has both task references and child WBS; both reparented."""
        # Build a doc where wbs_id="20" has one task AND one child WBS
        task_rows = [
            {"task_id": "101", "proj_id": "1", "wbs_id": "20",
             "task_code": "T101",
             "target_drtn_hr_cnt": "8", "remain_drtn_hr_cnt": "8"},
        ]
        doc = _make_doc_with_wbs_tree(extra_task_rows=task_rows)
        result = apply_changes(
            doc,
            [_remove_wbs_change("20", "move_to_parent")],
            strict=False,
            dry_run=False,
        )
        projwbs = result.doc.section("PROJWBS")
        task_section = result.doc.section("TASK")

        # "20" removed
        self.assertNotIn("20", {r["wbs_id"] for r in projwbs.rows})

        # grandchild "40" reparented to root "10"
        gc_row = next(r for r in projwbs.rows if r["wbs_id"] == "40")
        self.assertEqual(gc_row["parent_wbs_id"], "10")

        # task T101 reparented to root "10"
        self.assertEqual(task_section.rows[0]["wbs_id"], "10")

        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["reparented_task_count"], 1)
        self.assertEqual(fb["reparented_wbs_count"], 1)

    # ---- Test 8: remove root WBS → ValidationFailure (any cascade) -----------

    def test_remove_root_wbs_raises_regardless_of_cascade(self):
        """Root WBS (parent_wbs_id empty) removal always fails."""
        for cascade in ("fail_if_used", "move_to_parent"):
            with self.subTest(cascade=cascade):
                doc = _make_doc_with_wbs_tree()
                result = apply_changes(
                    doc,
                    [_remove_wbs_change("10", cascade)],
                    strict=False,
                    dry_run=False,
                )
                self.assertIsNone(result.doc)
                self.assertTrue(result.validation_errors)
                err = result.validation_errors[0].message
                self.assertIn("root", err.lower())

    # ---- Test 9: WBS not found → ValidationFailure ---------------------------

    def test_wbs_not_found_raises(self):
        """Removing a wbs_id that does not exist raises ValidationFailure naming the id."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("9999", "fail_if_used")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("9999", result.validation_errors[0].message)

    # ---- Test 10: bad cascade enum → ValidationFailure ----------------------

    def test_bad_cascade_enum_raises(self):
        """cascade='delete_all' is not a valid value → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_remove_wbs_change("40", "delete_all")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("delete_all", err)

    # ---- Test 11: state.removed_wbs_ids populated ----------------------------

    def test_state_removed_wbs_ids_populated(self):
        """After removal, state.removed_wbs_ids contains the removed wbs_id."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_wbs_tree()
        state = ChangeState()
        _HANDLERS["remove_wbs"](doc, _remove_wbs_change("40", "fail_if_used"), state)
        self.assertIn("40", state.removed_wbs_ids)

    # ---- Test 12: PROJWBS _dirty re-indexed correctly after row removal ------

    def test_projwbs_dirty_reindex_after_removal(self):
        """Pre: rows[0] and rows[2] dirty; remove rows[1]; _dirty == {0, 1}."""
        from xer_io import XerDoc, XerSection

        wbs_field_order = [
            "wbs_id", "proj_id", "wbs_short_name", "wbs_name",
            "parent_wbs_id", "status_code",
        ]
        wbs_rows = [
            {"wbs_id": "10", "proj_id": "1", "wbs_short_name": "R",
             "wbs_name": "Root", "parent_wbs_id": "", "status_code": "WS_Open"},
            {"wbs_id": "20", "proj_id": "1", "wbs_short_name": "A",
             "wbs_name": "ChildA", "parent_wbs_id": "10", "status_code": "WS_Open"},
            {"wbs_id": "30", "proj_id": "1", "wbs_short_name": "B",
             "wbs_name": "ChildB", "parent_wbs_id": "10", "status_code": "WS_Open"},
        ]

        def _raw(r):
            return "%R\t" + "\t".join(r.get(f, "") for f in wbs_field_order)

        wbs_section = XerSection(
            name="PROJWBS",
            field_order=wbs_field_order,
            rows=wbs_rows,
            raw_lines=[_raw(r) for r in wbs_rows],
            e_line=None,
        )
        # Pre-seed dirty: rows[0] and rows[2]
        wbs_section._dirty = {0, 2}

        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[wbs_section],
        )

        # Remove rows[1] = wbs_id="20" (no tasks, no children)
        result = apply_changes(
            doc,
            [_remove_wbs_change("20", "fail_if_used")],
            strict=False,
            dry_run=False,
        )

        projwbs = result.doc.section("PROJWBS")
        self.assertEqual(len(projwbs.rows), 2)
        # Original index-0 stays at 0; original index-2 moves to 1.
        self.assertEqual(projwbs._dirty, {0, 1})

    # ---- Test 13: no PROJWBS section → ValidationFailure --------------------

    def test_no_projwbs_section_raises(self):
        """Doc with no PROJWBS section raises ValidationFailure."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code"],
            rows=[{"task_id": "1", "task_code": "A1010"}],
            raw_lines=["%R\t1\tA1010"],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section],
        )
        result = apply_changes(
            doc,
            [_remove_wbs_change("10", "fail_if_used")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("PROJWBS", result.validation_errors[0].message)

    # ---- Test 14: no TASK section is fine — WBS removal proceeds -------------

    def test_no_task_section_is_fine(self):
        """Doc with no TASK section; WBS removal proceeds without error."""
        from xer_io import XerDoc, XerSection

        wbs_field_order = [
            "wbs_id", "proj_id", "wbs_short_name", "wbs_name",
            "parent_wbs_id", "status_code",
        ]
        wbs_rows = [
            {"wbs_id": "10", "proj_id": "1", "wbs_short_name": "R",
             "wbs_name": "Root", "parent_wbs_id": "", "status_code": "WS_Open"},
            {"wbs_id": "20", "proj_id": "1", "wbs_short_name": "A",
             "wbs_name": "Child", "parent_wbs_id": "10", "status_code": "WS_Open"},
        ]

        def _raw(r):
            return "%R\t" + "\t".join(r.get(f, "") for f in wbs_field_order)

        wbs_section = XerSection(
            name="PROJWBS",
            field_order=wbs_field_order,
            rows=wbs_rows,
            raw_lines=[_raw(r) for r in wbs_rows],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[wbs_section],
        )
        result = apply_changes(
            doc,
            [_remove_wbs_change("20", "fail_if_used")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        projwbs = result.doc.section("PROJWBS")
        self.assertEqual(len(projwbs.rows), 1)
        self.assertEqual(projwbs.rows[0]["wbs_id"], "10")


# ---------------------------------------------------------------------------
# Helpers for TestModifyWbs
# ---------------------------------------------------------------------------


def _modify_wbs_change(wbs_id: str, **kwargs):
    """Return a modify_wbs change record.

    wbs_id is required.  Any of new_wbs_code, new_wbs_name,
    new_parent_wbs_id, new_wbs_short_name may be supplied via kwargs.
    """
    return {"type": "modify_wbs", "wbs_id": wbs_id, **kwargs}


class TestModifyWbs(unittest.TestCase):
    """Tests for the modify_wbs change handler (D13)."""

    # _make_doc_with_wbs_tree builds:
    #   wbs_id="10"  parent=""    root
    #   wbs_id="20"  parent="10"  child-A  (wbs_code absent unless added)
    #   wbs_id="30"  parent="10"  child-B
    #   wbs_id="40"  parent="20"  grandchild

    # ---- Test 1: modify name only --------------------------------------------

    def test_modify_name_only(self):
        """new_wbs_name updates wbs_name; other fields untouched; row is dirty."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_wbs_name="Renamed Child A")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        projwbs = result.doc.section("PROJWBS")
        row = next(r for r in projwbs.rows if r["wbs_id"] == "20")
        self.assertEqual(row["wbs_name"], "Renamed Child A")
        # parent untouched
        self.assertEqual(row["parent_wbs_id"], "10")
        # dirty
        idx = projwbs.rows.index(row)
        self.assertTrue(projwbs.is_dirty(idx))
        # feedback
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["wbs_id"], "20")
        self.assertIn("wbs_name", fb["fields_changed"])
        self.assertNotIn("wbs_code", fb["fields_changed"])

    # ---- Test 2: modify code only -------------------------------------------

    def test_modify_code_only(self):
        """new_wbs_code updates wbs_code and row is dirty."""
        # Add wbs_code field to the existing tree fixture
        doc = _make_doc_with_wbs_tree()
        projwbs = doc.section("PROJWBS")
        projwbs.field_order.append("wbs_code")
        for row in projwbs.rows:
            row.setdefault("wbs_code", "")
        projwbs.rows[1]["wbs_code"] = "OLD-CODE"   # wbs_id="20"

        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_wbs_code="NEW-CODE")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        row = next(r for r in result.doc.section("PROJWBS").rows if r["wbs_id"] == "20")
        self.assertEqual(row["wbs_code"], "NEW-CODE")
        idx = result.doc.section("PROJWBS").rows.index(row)
        self.assertTrue(result.doc.section("PROJWBS").is_dirty(idx))
        fb = result.per_change_feedback[0].feedback
        self.assertIn("wbs_code", fb["fields_changed"])

    # ---- Test 3: modify parent only -----------------------------------------

    def test_modify_parent_only(self):
        """new_parent_wbs_id reparents the WBS node."""
        doc = _make_doc_with_wbs_tree()
        # Move grandchild ("40", parent="20") to child-B ("30")
        result = apply_changes(
            doc,
            [_modify_wbs_change("40", new_parent_wbs_id="30")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        row = next(r for r in result.doc.section("PROJWBS").rows if r["wbs_id"] == "40")
        self.assertEqual(row["parent_wbs_id"], "30")
        fb = result.per_change_feedback[0].feedback
        self.assertIn("parent_wbs_id", fb["fields_changed"])

    # ---- Test 4: modify short_name only -------------------------------------

    def test_modify_short_name_only(self):
        """new_wbs_short_name updates wbs_short_name field."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_wbs_short_name="XY")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        row = next(r for r in result.doc.section("PROJWBS").rows if r["wbs_id"] == "20")
        self.assertEqual(row["wbs_short_name"], "XY")
        fb = result.per_change_feedback[0].feedback
        self.assertIn("wbs_short_name", fb["fields_changed"])

    # ---- Test 5: modify multiple fields at once -----------------------------

    def test_modify_multiple_fields(self):
        """All four new_* fields provided; all updated; fields_changed lists all four."""
        doc = _make_doc_with_wbs_tree()
        projwbs = doc.section("PROJWBS")
        projwbs.field_order.append("wbs_code")
        for row in projwbs.rows:
            row.setdefault("wbs_code", "")

        result = apply_changes(
            doc,
            [_modify_wbs_change(
                "40",
                new_wbs_code="GC-NEW",
                new_wbs_name="Grandchild Renamed",
                new_parent_wbs_id="30",
                new_wbs_short_name="GR",
            )],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        row = next(r for r in result.doc.section("PROJWBS").rows if r["wbs_id"] == "40")
        self.assertEqual(row["wbs_code"], "GC-NEW")
        self.assertEqual(row["wbs_name"], "Grandchild Renamed")
        self.assertEqual(row["parent_wbs_id"], "30")
        self.assertEqual(row["wbs_short_name"], "GR")
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(set(fb["fields_changed"]),
                         {"wbs_code", "wbs_name", "parent_wbs_id", "wbs_short_name"})

    # ---- Test 6: no new_* fields → ValidationFailure -------------------------

    def test_no_fields_raises(self):
        """modify_wbs with no new_* fields is a caller bug → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("modify_wbs", err)

    # ---- Test 7: wbs_id not found → ValidationFailure -----------------------

    def test_wbs_id_not_found_raises(self):
        """wbs_id that does not exist in PROJWBS → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("9999", new_wbs_name="X")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("9999", err)

    # ---- Test 8: new_wbs_code collides with another row → ValidationFailure --

    def test_new_wbs_code_collision_raises(self):
        """new_wbs_code already in use by a different row → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        projwbs = doc.section("PROJWBS")
        projwbs.field_order.append("wbs_code")
        for row in projwbs.rows:
            row.setdefault("wbs_code", "")
        # wbs_id="20" has code "CODE-A"; wbs_id="30" has code "CODE-B"
        projwbs.rows[1]["wbs_code"] = "CODE-A"   # wbs_id="20"
        projwbs.rows[2]["wbs_code"] = "CODE-B"   # wbs_id="30"

        result = apply_changes(
            doc,
            # Try to rename "20" to use the code already belonging to "30"
            [_modify_wbs_change("20", new_wbs_code="CODE-B")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("CODE-B", err)

    # ---- Test 9: new_wbs_code same as existing — not a collision -------------

    def test_new_wbs_code_same_as_existing_succeeds(self):
        """Setting new_wbs_code to the row's current value is a no-op; not a collision."""
        doc = _make_doc_with_wbs_tree()
        projwbs = doc.section("PROJWBS")
        projwbs.field_order.append("wbs_code")
        for row in projwbs.rows:
            row.setdefault("wbs_code", "")
        projwbs.rows[1]["wbs_code"] = "SAME-CODE"   # wbs_id="20"

        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_wbs_code="SAME-CODE")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        row = next(r for r in result.doc.section("PROJWBS").rows if r["wbs_id"] == "20")
        self.assertEqual(row["wbs_code"], "SAME-CODE")

    # ---- Test 10: new_parent_wbs_id not found → ValidationFailure -----------

    def test_new_parent_wbs_id_not_found_raises(self):
        """new_parent_wbs_id not in PROJWBS and not in state.new_wbs_ids → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("40", new_parent_wbs_id="8888")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("8888", err)

    # ---- Test 11: new_parent_wbs_id satisfied by state.new_wbs_ids ----------

    def test_new_parent_satisfied_by_state(self):
        """new_parent_wbs_id in state.new_wbs_ids (added by preceding add_wbs) succeeds."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_wbs_tree()
        state = ChangeState(new_wbs_ids={"999"})
        feedback = _HANDLERS["modify_wbs"](
            doc,
            _modify_wbs_change("40", new_parent_wbs_id="999"),
            state,
        )
        row = next(r for r in doc.section("PROJWBS").rows if r["wbs_id"] == "40")
        self.assertEqual(row["parent_wbs_id"], "999")
        self.assertIn("parent_wbs_id", feedback["fields_changed"])

    # ---- Test 12: cycle — self-loop (new_parent == target) → ValidationFailure

    def test_cycle_self_loop_raises(self):
        """Setting new_parent_wbs_id to the node's own wbs_id → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_parent_wbs_id="20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("cycle", err.lower())

    # ---- Test 13: cycle — direct child as new parent → ValidationFailure ----

    def test_cycle_direct_child_raises(self):
        """Reparenting root ("10") under its direct child ("20") → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            # "10" is parent of "20"; making "20" the parent of "10" = cycle
            [_modify_wbs_change("10", new_parent_wbs_id="20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("cycle", err.lower())

    # ---- Test 14: cycle — grandchild as new parent → ValidationFailure ------

    def test_cycle_grandchild_raises(self):
        """Reparenting root ("10") under its grandchild ("40") → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        # Tree: 10→20→40; trying to make 40 the parent of 10 creates a cycle
        result = apply_changes(
            doc,
            [_modify_wbs_change("10", new_parent_wbs_id="40")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("cycle", err.lower())

    # ---- Test 15: no cycle when new parent is sibling → succeeds -------------

    def test_no_cycle_sibling_reparent_succeeds(self):
        """Reparenting grandchild ("40") under sibling child-B ("30") — no cycle."""
        doc = _make_doc_with_wbs_tree()
        # "40" is under "20"; "30" is a sibling of "20" (both under "10")
        result = apply_changes(
            doc,
            [_modify_wbs_change("40", new_parent_wbs_id="30")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        row = next(r for r in result.doc.section("PROJWBS").rows if r["wbs_id"] == "40")
        self.assertEqual(row["parent_wbs_id"], "30")

    # ---- Test 16: new_wbs_short_name too short → ValidationFailure ----------

    def test_short_name_too_short_raises(self):
        """new_wbs_short_name='X' (1 char) → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_wbs_short_name="X")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("wbs_short_name", err)

    # ---- Test 17: missing PROJWBS section → ValidationFailure ---------------

    def test_no_projwbs_section_raises(self):
        """Doc with no PROJWBS section raises ValidationFailure."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code"],
            rows=[{"task_id": "1", "task_code": "A1010"}],
            raw_lines=["%R\t1\tA1010"],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section],
        )
        result = apply_changes(
            doc,
            [_modify_wbs_change("10", new_wbs_name="X")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("PROJWBS", result.validation_errors[0].message)

    # ---- Test 18: feedback shape — fields_changed exact match ---------------

    def test_feedback_fields_changed_exact(self):
        """fields_changed reflects exactly the new_* fields that were provided."""
        doc = _make_doc_with_wbs_tree()
        # Provide only new_wbs_name and new_wbs_short_name
        result = apply_changes(
            doc,
            [_modify_wbs_change("20", new_wbs_name="X Y", new_wbs_short_name="XY")],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["wbs_id"], "20")
        self.assertEqual(set(fb["fields_changed"]), {"wbs_name", "wbs_short_name"})
        self.assertNotIn("wbs_code", fb["fields_changed"])
        self.assertNotIn("parent_wbs_id", fb["fields_changed"])


# ---------------------------------------------------------------------------
# Helpers for TestMoveActivitiesToWbs
# ---------------------------------------------------------------------------

def _move_activities_change(activity_ids: list, new_wbs_id: str):
    """Return a move_activities_to_wbs change record."""
    return {
        "type": "move_activities_to_wbs",
        "activity_ids": activity_ids,
        "new_wbs_id": new_wbs_id,
    }


class TestMoveActivitiesToWbs(unittest.TestCase):
    """Tests for the move_activities_to_wbs change handler (D14).

    Uses _make_doc_with_wbs_tree which builds:
        wbs_id="10"  parent=""    root
        wbs_id="20"  parent="10"  child-A
        wbs_id="30"  parent="10"  child-B  ← default location of T101 and T102
        wbs_id="40"  parent="20"  grandchild

    TASK rows (default): T101 and T102 assigned to wbs_id="30".
    """

    # ---- Test 1: happy path single activity ----------------------------------

    def test_happy_path_single_activity(self):
        """One activity moved: TASK row updated to new_wbs_id; row is dirty."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change(["T101"], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task = result.doc.section("TASK")
        t101_row = next(r for r in task.rows if r["task_code"] == "T101")
        t102_row = next(r for r in task.rows if r["task_code"] == "T102")
        # T101 moved; T102 untouched
        self.assertEqual(t101_row["wbs_id"], "20")
        self.assertEqual(t102_row["wbs_id"], "30")
        # Verify dirty: row index 0 is T101
        t101_idx = task.rows.index(t101_row)
        self.assertTrue(task.is_dirty(t101_idx))

    # ---- Test 2: happy path multiple activities ------------------------------

    def test_happy_path_multiple_activities(self):
        """All listed activities updated to new_wbs_id."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change(["T101", "T102"], "40")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task = result.doc.section("TASK")
        for row in task.rows:
            self.assertEqual(row["wbs_id"], "40",
                             f"{row['task_code']} should have wbs_id='40'")
        # Both rows dirty
        for i in range(len(task.rows)):
            self.assertTrue(task.is_dirty(i))

    # ---- Test 3: duplicate activity_ids silently deduplicated ----------------

    def test_duplicate_activity_ids_deduplicated(self):
        """Duplicate ids in the list are silently deduplicated; moved_count=1."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change(["T101", "T101"], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        fb = result.per_change_feedback[0].feedback
        self.assertEqual(fb["moved_count"], 1)
        # T101 still moved
        task = result.doc.section("TASK")
        t101 = next(r for r in task.rows if r["task_code"] == "T101")
        self.assertEqual(t101["wbs_id"], "20")

    # ---- Test 4: empty activity_ids list → ValidationFailure -----------------

    def test_empty_activity_ids_raises(self):
        """Empty activity_ids list is a caller bug → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change([], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("move_activities_to_wbs", err)

    # ---- Test 5: one activity missing → ValidationFailure --------------------

    def test_one_activity_missing_raises(self):
        """One activity_id not found in TASK → ValidationFailure naming it."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change(["T101", "ZZZZ"], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("ZZZZ", err)

    # ---- Test 6: multiple activities missing → ValidationFailure listing all -

    def test_multiple_activities_missing_raises(self):
        """Multiple missing activity_ids all listed in ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change(["AAAA", "BBBB"], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("AAAA", err)
        self.assertIn("BBBB", err)

    # ---- Test 7: new_wbs_id missing → ValidationFailure ---------------------

    def test_new_wbs_id_missing_raises(self):
        """new_wbs_id not in PROJWBS and not in state.new_wbs_ids → ValidationFailure."""
        doc = _make_doc_with_wbs_tree()
        result = apply_changes(
            doc,
            [_move_activities_change(["T101"], "9999")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message
        self.assertIn("9999", err)

    # ---- Test 8: new_wbs_id from state.new_wbs_ids → succeeds ---------------

    def test_new_wbs_id_from_state_succeeds(self):
        """new_wbs_id in state.new_wbs_ids (preceding add_wbs) → handler succeeds."""
        from xer_modify import _HANDLERS, ChangeState
        doc = _make_doc_with_wbs_tree()
        state = ChangeState(new_wbs_ids={"999"})
        feedback = _HANDLERS["move_activities_to_wbs"](
            doc,
            _move_activities_change(["T101"], "999"),
            state,
        )
        t101 = next(r for r in doc.section("TASK").rows if r["task_code"] == "T101")
        self.assertEqual(t101["wbs_id"], "999")
        self.assertEqual(feedback["moved_count"], 1)

    # ---- Test 9: no TASK section → ValidationFailure ------------------------

    def test_no_task_section_raises(self):
        """Doc with no TASK section raises ValidationFailure."""
        from xer_io import XerDoc, XerSection

        wbs_field_order = [
            "wbs_id", "proj_id", "wbs_short_name", "wbs_name",
            "parent_wbs_id", "status_code",
        ]
        wbs_section = XerSection(
            name="PROJWBS",
            field_order=wbs_field_order,
            rows=[
                {"wbs_id": "10", "proj_id": "1", "wbs_short_name": "R",
                 "wbs_name": "Root", "parent_wbs_id": "", "status_code": "WS_Open"},
                {"wbs_id": "20", "proj_id": "1", "wbs_short_name": "CA",
                 "wbs_name": "Child A", "parent_wbs_id": "10", "status_code": "WS_Open"},
            ],
            raw_lines=[
                "%R\t10\t1\tR\tRoot\t\tWS_Open",
                "%R\t20\t1\tCA\tChild A\t10\tWS_Open",
            ],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[wbs_section],
        )
        result = apply_changes(
            doc,
            [_move_activities_change(["T101"], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("TASK", result.validation_errors[0].message)

    # ---- Test 10: no PROJWBS section → ValidationFailure --------------------

    def test_no_projwbs_section_raises(self):
        """Doc with no PROJWBS section raises ValidationFailure."""
        from xer_io import XerDoc, XerSection

        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "proj_id", "wbs_id", "task_code",
                         "target_drtn_hr_cnt", "remain_drtn_hr_cnt"],
            rows=[{
                "task_id": "101", "proj_id": "1", "wbs_id": "30",
                "task_code": "T101",
                "target_drtn_hr_cnt": "8", "remain_drtn_hr_cnt": "8",
            }],
            raw_lines=["%R\t101\t1\t30\tT101\t8\t8"],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...",
            encoding="cp1252",
            sections=[task_section],
        )
        result = apply_changes(
            doc,
            [_move_activities_change(["T101"], "20")],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("PROJWBS", result.validation_errors[0].message)

    # ---- Test 11: feedback shape ---------------------------------------------

    def test_feedback_shape(self):
        """Feedback has moved_count, new_wbs_id, and activity_ids (deduped, sorted)."""
        doc = _make_doc_with_wbs_tree()
        # Supply duplicates and unsorted to verify dedup + sort in feedback
        result = apply_changes(
            doc,
            [_move_activities_change(["T102", "T101", "T101"], "20")],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        self.assertIn("moved_count", fb)
        self.assertIn("new_wbs_id", fb)
        self.assertIn("activity_ids", fb)
        self.assertEqual(fb["moved_count"], 2)
        self.assertEqual(fb["new_wbs_id"], "20")
        # activity_ids should be deduped and sorted
        self.assertEqual(fb["activity_ids"], ["T101", "T102"])


# ---------------------------------------------------------------------------
# apply_anchor_absorption
# ---------------------------------------------------------------------------

def _make_cpm_doc():
    """Build a CPM-capable XerDoc in memory.

    Schedule topology: A1000 (10d) -> A2000 (20d) -> M3000 (finish milestone).
    Both task predecessors are on the critical path (TF=0).
    The PROJECT section provides a data_date for CPM.

    A slip against M3000 with slip_days > 0 will produce two suggestions:
        index 0: A2000 (20d, max cut 10d)
        index 1: A1000 (10d, max cut 5d)
    """
    from xer_io import XerDoc, XerSection

    # TASK section — full field set CPM needs
    task_field_order = [
        "task_id", "proj_id", "wbs_id", "clndr_id", "phys_complete_pct",
        "task_type", "duration_type", "status_code", "task_code", "task_name",
        "total_float_hr_cnt", "free_float_hr_cnt",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
        "early_start_date", "early_end_date",
        "late_start_date", "late_end_date",
        "act_start_date", "act_end_date",
    ]
    task_rows = [
        {
            "task_id": "1", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
            "phys_complete_pct": "0", "task_type": "TT_Task",
            "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
            "task_code": "A1000", "task_name": "Activity A",
            "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
            "target_drtn_hr_cnt": "80", "remain_drtn_hr_cnt": "80",
            "early_start_date": "", "early_end_date": "",
            "late_start_date": "", "late_end_date": "",
            "act_start_date": "", "act_end_date": "",
        },
        {
            "task_id": "2", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
            "phys_complete_pct": "0", "task_type": "TT_Task",
            "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
            "task_code": "A2000", "task_name": "Activity B",
            "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
            "target_drtn_hr_cnt": "160", "remain_drtn_hr_cnt": "160",
            "early_start_date": "", "early_end_date": "",
            "late_start_date": "", "late_end_date": "",
            "act_start_date": "", "act_end_date": "",
        },
        {
            "task_id": "3", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
            "phys_complete_pct": "0", "task_type": "TT_FinMile",
            "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
            "task_code": "M3000", "task_name": "Finish Milestone",
            "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
            "target_drtn_hr_cnt": "0", "remain_drtn_hr_cnt": "0",
            "early_start_date": "", "early_end_date": "",
            "late_start_date": "", "late_end_date": "",
            "act_start_date": "", "act_end_date": "",
        },
    ]
    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=task_rows,
        raw_lines=["\t".join(r[f] for f in task_field_order) for r in task_rows],
        e_line=None,
    )

    # TASKPRED: A1000 -> A2000 (FS), A2000 -> M3000 (FS)
    pred_field_order = ["task_pred_id", "task_id", "pred_task_id", "proj_id",
                        "pred_proj_id", "pred_type", "lag_hr_cnt"]
    pred_rows = [
        {"task_pred_id": "1", "task_id": "2", "pred_task_id": "1",
         "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
        {"task_pred_id": "2", "task_id": "3", "pred_task_id": "2",
         "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
    ]
    pred_section = XerSection(
        name="TASKPRED",
        field_order=pred_field_order,
        rows=pred_rows,
        raw_lines=["\t".join(r[f] for f in pred_field_order) for r in pred_rows],
        e_line=None,
    )

    # CALENDAR: minimal 5-day-week definition that calendar_engine can parse
    cal_field_order = ["clndr_id", "default_flag", "clndr_name", "proj_id",
                       "base_clndr_id", "last_chng_date", "clndr_type", "day_hr_cnt"]
    cal_rows = [
        {
            "clndr_id": "100", "default_flag": "Y", "clndr_name": "Standard 5-day",
            "proj_id": "1", "base_clndr_id": "", "last_chng_date": "",
            "clndr_type": "CT_Base", "day_hr_cnt": "8",
        }
    ]
    cal_section = XerSection(
        name="CALENDAR",
        field_order=cal_field_order,
        rows=cal_rows,
        raw_lines=["\t".join(r[f] for f in cal_field_order) for r in cal_rows],
        e_line=None,
    )

    # PROJECT: provides the data_date for CPM
    proj_field_order = ["proj_id", "last_recalc_date", "plan_start_date"]
    proj_rows = [
        {"proj_id": "1", "last_recalc_date": "2026-01-01 08:00", "plan_start_date": ""}
    ]
    proj_section = XerSection(
        name="PROJECT",
        field_order=proj_field_order,
        rows=proj_rows,
        raw_lines=["\t".join(r[f] for f in proj_field_order) for r in proj_rows],
        e_line=None,
    )

    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[task_section, pred_section, cal_section, proj_section],
    )


class TestApplyAnchorAbsorption(unittest.TestCase):
    """Tests for the apply_anchor_absorption composite handler."""

    # ---- Test 1: happy path ------------------------------------------------

    def test_happy_path_lowers_to_set_duration(self):
        """Picking suggestion_index=0 (A2000, 20d, cut 10d) should set A2000 to 10d."""
        doc = _make_cpm_doc()
        anchor_slip = {"task_id": "3", "slip_days": 5}
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": anchor_slip,
              "suggestion_index": 0}],
            strict=False,
            dry_run=False,
        )
        self.assertEqual(result.changes_applied, 1)
        task_section = result.doc.section("TASK")
        # Find A2000 row
        a2000 = next(r for r in task_section.rows if r["task_code"] == "A2000")
        # current=20d, cut=10d → new=10d → 80 hours
        self.assertEqual(a2000["target_drtn_hr_cnt"], "80")
        self.assertEqual(a2000["remain_drtn_hr_cnt"], "80")

    # ---- Test 2: suggestion_index out of range ----------------------------

    def test_suggestion_index_out_of_range(self):
        """suggestion_index beyond the list length raises ValidationFailure
        with the actual count of suggestions mentioned."""
        doc = _make_cpm_doc()
        anchor_slip = {"task_id": "3", "slip_days": 5}
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": anchor_slip,
              "suggestion_index": 99}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("99", result.validation_errors[0].message)
        # The message should mention the actual count available
        self.assertIn("suggestion", result.validation_errors[0].message.lower())

    # ---- Test 3: empty suggestion list -----------------------------------

    def test_empty_suggestion_list_raises(self):
        """When anchor_task has no driving critical predecessors,
        suggest_anchor_absorption returns [] and the handler raises."""
        doc = _make_cpm_doc()
        # Anchor is M3000 (task_id='3'), but we re-use a slip pointing to
        # M3000 with a large slip_days but the anchor task has no
        # non-milestone predecessors with TF > 0 cut headroom — actually in
        # this fixture both tasks ARE critical. To force an empty list we
        # point at task_id='1' (A1000), which has no predecessors.
        anchor_slip = {"task_id": "1", "slip_days": 5}
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": anchor_slip,
              "suggestion_index": 0}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message.lower()
        self.assertIn("no absorption suggestion", err)

    # ---- Test 4: anchor_slip missing task_id -----------------------------

    def test_anchor_slip_missing_task_id(self):
        """anchor_slip without 'task_id' raises ValidationFailure."""
        doc = _make_cpm_doc()
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"slip_days": 5},
              "suggestion_index": 0}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("task_id", result.validation_errors[0].message)

    # ---- Test 5: anchor_slip missing slip_days ---------------------------

    def test_anchor_slip_missing_slip_days(self):
        """anchor_slip without 'slip_days' raises ValidationFailure."""
        doc = _make_cpm_doc()
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "3"},
              "suggestion_index": 0}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("slip_days", result.validation_errors[0].message)

    # ---- Test 6: negative suggestion_index -------------------------------

    def test_negative_suggestion_index(self):
        """Negative suggestion_index raises ValidationFailure."""
        doc = _make_cpm_doc()
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "3", "slip_days": 5},
              "suggestion_index": -1}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("-1", result.validation_errors[0].message)

    # ---- Test 7: unknown suggestion kind ---------------------------------
    # Cannot be triggered by the current cpm_engine (only 'duration_cut' is
    # produced). Marked untested per spec — the validation code path exists
    # and is tested only by inspection of the handler source.

    # ---- Test 8: new_duration < 1 (over-aggressive cut) ------------------

    def test_new_duration_zero_raises(self):
        """When current_duration - suggested_max_cut < 1, raise ValidationFailure.

        Build a doc where A1000 has duration=1d (8h).  suggest_anchor_absorption
        filters tasks with duration < 1d, so we need at least 1d.  We set
        target_drtn_hr_cnt='8' (1d) and set up a chain so that A1000 is the
        only critical predecessor of the anchor.

        The suggestion will compute max_cut = max(1, int(1 * 0.5)) = 1.
        new_duration = 1 - 1 = 0 → ValidationFailure.
        """
        from xer_io import XerDoc, XerSection

        task_field_order = [
            "task_id", "proj_id", "wbs_id", "clndr_id", "phys_complete_pct",
            "task_type", "duration_type", "status_code", "task_code", "task_name",
            "total_float_hr_cnt", "free_float_hr_cnt",
            "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
            "early_start_date", "early_end_date",
            "late_start_date", "late_end_date",
            "act_start_date", "act_end_date",
        ]
        task_rows = [
            {
                "task_id": "1", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
                "phys_complete_pct": "0", "task_type": "TT_Task",
                "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
                "task_code": "A1000", "task_name": "Activity A",
                "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
                # 1 day = 8 hours
                "target_drtn_hr_cnt": "8", "remain_drtn_hr_cnt": "8",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "act_start_date": "", "act_end_date": "",
            },
            {
                "task_id": "2", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
                "phys_complete_pct": "0", "task_type": "TT_FinMile",
                "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
                "task_code": "M2000", "task_name": "Finish Milestone",
                "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
                "target_drtn_hr_cnt": "0", "remain_drtn_hr_cnt": "0",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "act_start_date": "", "act_end_date": "",
            },
        ]
        task_section = XerSection(
            name="TASK", field_order=task_field_order, rows=task_rows,
            raw_lines=["\t".join(r[f] for f in task_field_order) for r in task_rows],
            e_line=None,
        )
        pred_field_order = ["task_pred_id", "task_id", "pred_task_id", "proj_id",
                            "pred_proj_id", "pred_type", "lag_hr_cnt"]
        pred_rows = [
            {"task_pred_id": "1", "task_id": "2", "pred_task_id": "1",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
        ]
        pred_section = XerSection(
            name="TASKPRED", field_order=pred_field_order, rows=pred_rows,
            raw_lines=["\t".join(r[f] for f in pred_field_order) for r in pred_rows],
            e_line=None,
        )
        cal_field_order = ["clndr_id", "default_flag", "clndr_name", "proj_id",
                           "base_clndr_id", "last_chng_date", "clndr_type", "day_hr_cnt"]
        cal_rows = [{
            "clndr_id": "100", "default_flag": "Y", "clndr_name": "Standard",
            "proj_id": "1", "base_clndr_id": "", "last_chng_date": "",
            "clndr_type": "CT_Base", "day_hr_cnt": "8",
        }]
        cal_section = XerSection(
            name="CALENDAR", field_order=cal_field_order, rows=cal_rows,
            raw_lines=["\t".join(r[f] for f in cal_field_order) for r in cal_rows],
            e_line=None,
        )
        proj_field_order = ["proj_id", "last_recalc_date", "plan_start_date"]
        proj_rows = [{"proj_id": "1", "last_recalc_date": "2026-01-01 08:00",
                      "plan_start_date": ""}]
        proj_section = XerSection(
            name="PROJECT", field_order=proj_field_order, rows=proj_rows,
            raw_lines=["\t".join(r[f] for f in proj_field_order) for r in proj_rows],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...", encoding="cp1252",
            sections=[task_section, pred_section, cal_section, proj_section],
        )

        # A1000 is 1d, max_cut=1 → new_duration=0 → ValidationFailure
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "2", "slip_days": 1},
              "suggestion_index": 0}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        err = result.validation_errors[0].message.lower()
        self.assertIn("duration", err)

    # ---- Test 9: missing required sections --------------------------------

    def test_missing_task_section_raises(self):
        """Missing TASK section → ValidationFailure."""
        from xer_io import XerDoc, XerSection
        proj_section = XerSection(
            name="PROJECT", field_order=["proj_id", "last_recalc_date"],
            rows=[{"proj_id": "1", "last_recalc_date": "2026-01-01 08:00"}],
            raw_lines=[""], e_line=None,
        )
        doc = XerDoc(header_line="ERMHDR\t...", encoding="cp1252",
                     sections=[proj_section])
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "1", "slip_days": 5},
              "suggestion_index": 0}],
            strict=False, dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("TASK", result.validation_errors[0].message)

    def test_missing_taskpred_section_raises(self):
        """Missing TASKPRED section → ValidationFailure."""
        from xer_io import XerDoc, XerSection
        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code"],
            rows=[{"task_id": "1", "task_code": "A1000"}],
            raw_lines=[""], e_line=None,
        )
        doc = XerDoc(header_line="ERMHDR\t...", encoding="cp1252",
                     sections=[task_section])
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "1", "slip_days": 5},
              "suggestion_index": 0}],
            strict=False, dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("TASKPRED", result.validation_errors[0].message)

    def test_missing_calendar_section_raises(self):
        """Missing CALENDAR section → ValidationFailure."""
        from xer_io import XerDoc, XerSection
        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code"],
            rows=[{"task_id": "1", "task_code": "A1000"}],
            raw_lines=[""], e_line=None,
        )
        pred_section = XerSection(
            name="TASKPRED",
            field_order=["task_pred_id"],
            rows=[],
            raw_lines=[], e_line=None,
        )
        doc = XerDoc(header_line="ERMHDR\t...", encoding="cp1252",
                     sections=[task_section, pred_section])
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "1", "slip_days": 5},
              "suggestion_index": 0}],
            strict=False, dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("CALENDAR", result.validation_errors[0].message)

    def test_missing_project_section_raises(self):
        """Missing PROJECT section → ValidationFailure."""
        from xer_io import XerDoc, XerSection
        task_section = XerSection(
            name="TASK",
            field_order=["task_id", "task_code"],
            rows=[{"task_id": "1", "task_code": "A1000"}],
            raw_lines=[""], e_line=None,
        )
        pred_section = XerSection(
            name="TASKPRED",
            field_order=["task_pred_id"],
            rows=[],
            raw_lines=[], e_line=None,
        )
        cal_section = XerSection(
            name="CALENDAR",
            field_order=["clndr_id"],
            rows=[{"clndr_id": "100"}],
            raw_lines=[""], e_line=None,
        )
        doc = XerDoc(header_line="ERMHDR\t...", encoding="cp1252",
                     sections=[task_section, pred_section, cal_section])
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "1", "slip_days": 5},
              "suggestion_index": 0}],
            strict=False, dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertIn("PROJECT", result.validation_errors[0].message)

    # ---- Test 10: feedback shape ------------------------------------------

    def test_feedback_shape(self):
        """Feedback dict must have all 8 expected keys."""
        doc = _make_cpm_doc()
        result = apply_changes(
            doc,
            [{"type": "apply_anchor_absorption",
              "anchor_slip": {"task_id": "3", "slip_days": 5},
              "suggestion_index": 0}],
            strict=False,
            dry_run=False,
        )
        fb = result.per_change_feedback[0].feedback
        expected_keys = {
            "suggestion_chosen",
            "total_suggestions",
            "lowered_changes_count",
            "set_duration_feedback",
            "activity_end_before",
            "activity_end_after",
            "milestone_impact_days",
            "now_on_critical_path",
        }
        self.assertEqual(set(fb.keys()), expected_keys)
        self.assertEqual(fb["lowered_changes_count"], 1)
        self.assertIsNotNone(fb["suggestion_chosen"])
        self.assertGreater(fb["total_suggestions"], 0)
        self.assertIsNone(fb["activity_end_before"])
        self.assertIsNone(fb["activity_end_after"])
        self.assertIsNone(fb["milestone_impact_days"])
        self.assertIsNone(fb["now_on_critical_path"])


# ---------------------------------------------------------------------------
# D16: Pass 2 reference resolution + Pass 3 graph checks
# ---------------------------------------------------------------------------

def _make_d16_doc(extra_task_rows=None, extra_taskpred_rows=None):
    """Build a valid two-activity XerDoc suitable for D16 orchestrator tests.

    Contains TASK, TASKPRED, PROJWBS, and CALENDAR sections with proper
    status_code values so xer_validate Pass 3 does not fire spurious errors
    on the pre-existing rows.

    Extra task_rows (dicts) and extra taskpred_rows (dicts) can be appended
    to extend the base fixture.
    """
    from xer_io import XerDoc, XerSection

    base_task_rows = [
        {
            "task_id": "101", "proj_id": "1", "wbs_id": "1000", "clndr_id": "100",
            "task_code": "A1010", "task_name": "Activity A",
            "task_type": "TT_Task", "duration_type": "DT_FixedDUR2",
            "status_code": "TK_NotStart", "complete_pct_type": "CP_Drtn",
            "phys_complete_pct": "0",
            "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40",
        },
        {
            "task_id": "102", "proj_id": "1", "wbs_id": "1000", "clndr_id": "100",
            "task_code": "A1020", "task_name": "Activity B",
            "task_type": "TT_Task", "duration_type": "DT_FixedDUR2",
            "status_code": "TK_NotStart", "complete_pct_type": "CP_Drtn",
            "phys_complete_pct": "0",
            "target_drtn_hr_cnt": "40", "remain_drtn_hr_cnt": "40",
        },
    ]
    if extra_task_rows:
        base_task_rows.extend(extra_task_rows)

    base_taskpred_rows = [
        {
            "task_pred_id": "1", "task_id": "102", "pred_task_id": "101",
            "proj_id": "1", "pred_proj_id": "1",
            "pred_type": "PR_FS", "lag_hr_cnt": "0",
            "comments": "", "float_path": "", "aref": "", "arls": "",
        },
    ]
    if extra_taskpred_rows:
        base_taskpred_rows.extend(extra_taskpred_rows)

    task_field_order = [
        "task_id", "proj_id", "wbs_id", "clndr_id",
        "task_code", "task_name", "task_type", "duration_type",
        "status_code", "complete_pct_type", "phys_complete_pct",
        "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    ]
    taskpred_field_order = [
        "task_pred_id", "task_id", "pred_task_id",
        "proj_id", "pred_proj_id", "pred_type", "lag_hr_cnt",
        "comments", "float_path", "aref", "arls",
    ]
    wbs_field_order = ["wbs_id", "proj_id", "wbs_name"]
    cal_field_order = ["clndr_id", "clndr_name"]

    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=base_task_rows,
        raw_lines=["%R\t" + "\t".join(r.get(f, "") for f in task_field_order) for r in base_task_rows],
        e_line=None,
    )
    taskpred_section = XerSection(
        name="TASKPRED",
        field_order=taskpred_field_order,
        rows=base_taskpred_rows,
        raw_lines=["%R\t" + "\t".join(r.get(f, "") for f in taskpred_field_order) for r in base_taskpred_rows],
        e_line=None,
    )
    wbs_rows = [{"wbs_id": "1000", "proj_id": "1", "wbs_name": "Root"}]
    wbs_section = XerSection(
        name="PROJWBS",
        field_order=wbs_field_order,
        rows=wbs_rows,
        raw_lines=["%R\t" + "\t".join(r.get(f, "") for f in wbs_field_order) for r in wbs_rows],
        e_line=None,
    )
    cal_rows = [{"clndr_id": "100", "clndr_name": "Standard"}]
    cal_section = XerSection(
        name="CALENDAR",
        field_order=cal_field_order,
        rows=cal_rows,
        raw_lines=["%R\t" + "\t".join(r.get(f, "") for f in cal_field_order) for r in cal_rows],
        e_line=None,
    )

    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=[task_section, taskpred_section, wbs_section, cal_section],
    )


class TestD16Pass2Pass3(unittest.TestCase):
    """D16: Pass 2 order-aware reference resolution and Pass 3 graph checks."""

    # ---- (a) Order-aware reference resolution --------------------------------

    def test_add_activity_then_add_logic_forward_ref(self):
        """[add_activity X, add_logic A1020->X] succeeds via state.new_activity_id_map.

        add_logic references X which was added by the preceding add_activity
        in the same call.  Without state.new_activity_id_map propagation in
        _handle_add_logic, this would raise 'not found in TASK section'.
        """
        doc = _make_d16_doc()
        # The base doc has A1010 -> A1020 connected.
        # We add a new activity X and wire A1020 -> X.
        changes = [
            {
                "type": "add_activity",
                "spec": {
                    "code": "X1000",
                    "name": "New Activity X",
                    "duration_days": 3,
                    "calendar_id": "100",
                    "wbs_id": "1000",
                    "activity_type": "TT_Task",
                },
            },
            {
                "type": "add_logic",
                "predecessor_id": "A1020",
                "successor_id": "X1000",
                "relationship": "FS",
                "lag_days": 0,
            },
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=False)
        self.assertEqual(result.changes_applied, 2)
        self.assertIsNotNone(result.doc)
        self.assertEqual(result.validation_errors, [])

        task_section = result.doc.section("TASK")
        codes = {r["task_code"] for r in task_section.rows}
        self.assertIn("X1000", codes)

        tp = result.doc.section("TASKPRED")
        # Original A1010->A1020 edge + new A1020->X1000 edge = 2 rows
        self.assertEqual(len(tp.rows), 2)
        new_edge = tp.rows[1]
        # X1000 was added with task_id = "103" (max(101,102)+1)
        self.assertEqual(new_edge["pred_task_id"], "102")  # A1020
        self.assertEqual(new_edge["task_id"], "103")        # X1000

    # ---- (b) Orphan rule via strict=True -------------------------------------

    def test_add_activity_no_logic_strict_true_blocks(self):
        """[add_activity X] with no logic, strict=True blocks via ORPHAN_ACTIVITY warning.

        xer_validate reports ORPHAN_ACTIVITY as a warning.  With strict=True,
        warnings are promoted to errors and block the apply.
        """
        doc = _make_d16_doc()
        changes = [
            {
                "type": "add_activity",
                "spec": {
                    "code": "X1000",
                    "name": "Orphaned Activity",
                    "duration_days": 3,
                    "calendar_id": "100",
                    "wbs_id": "1000",
                    "activity_type": "TT_Task",
                },
            },
        ]
        result = apply_changes(doc, changes, strict=True, dry_run=False)
        self.assertIsNone(result.doc)
        codes = [e.code for e in result.validation_errors]
        self.assertIn("ORPHAN_ACTIVITY", codes)

    def test_add_activity_no_logic_strict_false_passes_with_warning(self):
        """[add_activity X] with no logic, strict=False — apply succeeds with warning."""
        doc = _make_d16_doc()
        changes = [
            {
                "type": "add_activity",
                "spec": {
                    "code": "X1000",
                    "name": "Orphaned Activity",
                    "duration_days": 3,
                    "calendar_id": "100",
                    "wbs_id": "1000",
                    "activity_type": "TT_Task",
                },
            },
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=False)
        # Orphan is a warning; strict=False lets it through
        self.assertIsNotNone(result.doc)
        self.assertEqual(result.validation_errors, [])
        warn_codes = [w.code for w in result.validation_warnings]
        self.assertIn("ORPHAN_ACTIVITY", warn_codes)

    # ---- (c) Cycle check via Pass 3 ------------------------------------------

    def test_add_logic_creating_cycle_blocked_by_pass3(self):
        """[add_logic A1020->A1010] creates cycle A1010->A1020->A1010.

        Pass 3 detects CIRCULAR_LOGIC (error severity) and blocks the apply.
        """
        doc = _make_d16_doc()
        # The base doc has A1010 -> A1020 (FS).
        # Adding A1020 -> A1010 creates a cycle.
        changes = [
            {
                "type": "add_logic",
                "predecessor_id": "A1020",
                "successor_id": "A1010",
                "relationship": "FS",
                "lag_days": 0,
            },
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=False)
        self.assertIsNone(result.doc)
        codes = [e.code for e in result.validation_errors]
        self.assertIn("CIRCULAR_LOGIC", codes)

    # ---- (d) dry_run path ----------------------------------------------------

    def test_dry_run_success_returns_mutated_doc(self):
        """dry_run=True on a valid change returns the mutated doc for inspection."""
        doc = _make_d16_doc()
        changes = [
            {
                "type": "set_duration",
                "activity_id": "A1010",
                "new_duration_days": 10,
            }
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=True)
        # dry_run with no errors still returns the mutated copy
        self.assertIsNotNone(result.doc)
        self.assertEqual(result.changes_applied, 1)
        task_row = next(
            r for r in result.doc.section("TASK").rows
            if r["task_code"] == "A1010"
        )
        self.assertEqual(task_row["target_drtn_hr_cnt"], "80")  # 10d * 8h

    def test_dry_run_error_returns_none_doc(self):
        """dry_run=True on an invalid change returns doc=None."""
        doc = _make_d16_doc()
        # Cycle: doc already has A1010->A1020, adding reverse creates cycle
        changes = [
            {
                "type": "add_logic",
                "predecessor_id": "A1020",
                "successor_id": "A1010",
                "relationship": "FS",
                "lag_days": 0,
            },
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=True)
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)

    # ---- (e) Original doc is unmodified even on success (deep-copy semantics) -

    def test_original_doc_unmodified_on_success(self):
        """result.doc is a deep copy; the original doc passed in is never mutated."""
        doc = _make_d16_doc()
        original_duration = doc.section("TASK").rows[0]["target_drtn_hr_cnt"]

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1010", "new_duration_days": 20}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNotNone(result.doc)
        # result.doc reflects the change
        mutated_row = next(
            r for r in result.doc.section("TASK").rows if r["task_code"] == "A1010"
        )
        self.assertEqual(mutated_row["target_drtn_hr_cnt"], "160")  # 20d * 8h
        # original doc is unchanged
        orig_row = doc.section("TASK").rows[0]
        self.assertEqual(orig_row["target_drtn_hr_cnt"], original_duration)

    def test_original_doc_unmodified_on_error(self):
        """On Pass 2 error, original doc is still unmodified."""
        doc = _make_d16_doc()
        task_count_before = len(doc.section("TASK").rows)

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "NOTHERE", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertEqual(len(doc.section("TASK").rows), task_count_before)

    # ---- (f) Warning-only with strict=False succeeds -------------------------

    def test_warning_only_strict_false_succeeds(self):
        """ORPHAN_ACTIVITY warning with strict=False: result.doc set, no validation_errors."""
        doc = _make_d16_doc()
        result = apply_changes(
            doc,
            [
                {
                    "type": "add_activity",
                    "spec": {
                        "code": "Z9999",
                        "name": "Isolated",
                        "duration_days": 1,
                        "calendar_id": "100",
                        "wbs_id": "1000",
                        "activity_type": "TT_Task",
                    },
                }
            ],
            strict=False,
            dry_run=False,
        )
        self.assertIsNotNone(result.doc)
        self.assertEqual(result.validation_errors, [])
        warn_codes = [w.code for w in result.validation_warnings]
        self.assertIn("ORPHAN_ACTIVITY", warn_codes)

    # ---- (g) Warning-only with strict=True blocks ----------------------------

    def test_warning_only_strict_true_blocks(self):
        """ORPHAN_ACTIVITY warning with strict=True: result.doc is None."""
        doc = _make_d16_doc()
        result = apply_changes(
            doc,
            [
                {
                    "type": "add_activity",
                    "spec": {
                        "code": "Z9999",
                        "name": "Isolated",
                        "duration_days": 1,
                        "calendar_id": "100",
                        "wbs_id": "1000",
                        "activity_type": "TT_Task",
                    },
                }
            ],
            strict=True,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        codes = [e.code for e in result.validation_errors]
        self.assertIn("ORPHAN_ACTIVITY", codes)

    # ---- (h) Multi-change call succeeds end-to-end ---------------------------

    def test_multi_change_call_succeeds(self):
        """Two changes in one call both applied; post-state is consistent."""
        doc = _make_d16_doc()
        changes = [
            {
                "type": "set_duration",
                "activity_id": "A1010",
                "new_duration_days": 7,
            },
            {
                "type": "set_duration",
                "activity_id": "A1020",
                "new_duration_days": 3,
            },
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=False)
        self.assertEqual(result.changes_applied, 2)
        self.assertIsNotNone(result.doc)
        task = result.doc.section("TASK")
        a1010 = next(r for r in task.rows if r["task_code"] == "A1010")
        a1020 = next(r for r in task.rows if r["task_code"] == "A1020")
        self.assertEqual(a1010["target_drtn_hr_cnt"], "56")   # 7d * 8
        self.assertEqual(a1020["target_drtn_hr_cnt"], "24")   # 3d * 8

    # ---- (i) Pass 1 still raises on unknown type (not caught by Pass 2) ------

    def test_pass1_unknown_type_still_raises(self):
        """Unknown change type still raises ValidationFailure directly."""
        doc = _make_d16_doc()
        with self.assertRaises(ValidationFailure):
            apply_changes(doc, [{"type": "no_such_type"}], strict=False, dry_run=False)

    # ---- (k) result.doc is different object than original doc ----------------

    def test_result_doc_is_different_object(self):
        """On success, result.doc is not the same Python object as the input doc."""
        doc = _make_d16_doc()
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1010", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNotNone(result.doc)
        self.assertIsNot(result.doc, doc)

    # ---- (l) result.doc is None on error; error has correct change_index -----

    def test_result_doc_is_none_on_pass2_error(self):
        """Pass 2 handler error → result.doc is None, validation_errors has change_index=0."""
        doc = _make_d16_doc()
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "NO_SUCH", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        self.assertTrue(result.validation_errors)
        self.assertEqual(result.validation_errors[0].code, "HANDLER_ERROR")
        self.assertEqual(result.validation_errors[0].change_index, 0)

    def test_result_doc_is_none_on_pass3_error(self):
        """Pass 3 error (cycle) → result.doc is None, change_index is None."""
        doc = _make_d16_doc()
        result = apply_changes(
            doc,
            [{"type": "add_logic", "predecessor_id": "A1020", "successor_id": "A1010",
              "relationship": "FS", "lag_days": 0}],
            strict=False,
            dry_run=False,
        )
        self.assertIsNone(result.doc)
        codes = [e.code for e in result.validation_errors]
        self.assertIn("CIRCULAR_LOGIC", codes)
        # Pass 3 errors have change_index=None
        circular_error = next(e for e in result.validation_errors if e.code == "CIRCULAR_LOGIC")
        self.assertIsNone(circular_error.change_index)

    # ---- Extra: add_logic forward ref also works for predecessor -------------

    def test_add_activity_add_logic_predecessor_forward_ref(self):
        """[add_activity X, add_logic X->A1010] — X used as predecessor via state."""
        doc = _make_d16_doc()
        changes = [
            {
                "type": "add_activity",
                "spec": {
                    "code": "X0001",
                    "name": "New Start Activity",
                    "duration_days": 2,
                    "calendar_id": "100",
                    "wbs_id": "1000",
                    "activity_type": "TT_Task",
                },
            },
            {
                "type": "add_logic",
                "predecessor_id": "X0001",
                "successor_id": "A1010",
                "relationship": "FS",
                "lag_days": 0,
            },
        ]
        result = apply_changes(doc, changes, strict=False, dry_run=False)
        self.assertEqual(result.changes_applied, 2)
        self.assertIsNotNone(result.doc)
        tp = result.doc.section("TASKPRED")
        # Should have original A1010->A1020 + new X0001->A1010 = 2 rows
        self.assertEqual(len(tp.rows), 2)
        new_edge = next(
            r for r in tp.rows if r["task_id"] == "101"  # A1010 as successor
        )
        self.assertIsNotNone(new_edge)


# ---------------------------------------------------------------------------
# D17: Post-CPM feedback wiring
# ---------------------------------------------------------------------------

def _make_pre_state_cpm(doc):
    """Run CPM on doc and return the results list (pre-state baseline).

    Mirrors what the MCP layer does before calling apply_changes with
    pre_state_cpm=results.
    """
    import importlib.util, os
    lib_dir = str(Path(__file__).parent.parent / "lib")
    spec = importlib.util.spec_from_file_location(
        "cpm_engine", os.path.join(lib_dir, "cpm_engine.py")
    )
    cpm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cpm)

    task_rows = doc.section("TASK").rows
    pred_rows = doc.section("TASKPRED").rows
    cal_rows = doc.section("CALENDAR").rows
    project_section = doc.section("PROJECT")
    data_date = ""
    if project_section and project_section.rows:
        r = project_section.rows[0]
        data_date = r.get("last_recalc_date") or r.get("plan_start_date") or ""

    results, _ = cpm.schedule_forward_backward(task_rows, pred_rows, cal_rows, data_date)
    return results


class TestD17PostCpmFeedback(unittest.TestCase):
    """D17: post-CPM diff wiring in apply_changes."""

    # ---- Test 1: per-change feedback populated when pre_state_cpm provided ----

    def test_per_change_feedback_populated_with_pre_state_cpm(self):
        """set_duration: activity_end_before/after differ; milestone_impact_days set."""
        import copy
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",  # M3000
        )
        self.assertEqual(result.changes_applied, 1)
        fb = result.per_change_feedback[0].feedback
        # Both dates should be populated
        self.assertIsNotNone(fb["activity_end_before"])
        self.assertIsNotNone(fb["activity_end_after"])
        # Before and after differ (A1000 was shortened)
        self.assertNotEqual(fb["activity_end_before"], fb["activity_end_after"])
        # milestone_impact_days is set (non-None)
        self.assertIsNotNone(fb["milestone_impact_days"])

    # ---- Test 2: per-change feedback stays None when pre_state_cpm is None ---

    def test_per_change_feedback_none_without_pre_state_cpm(self):
        """set_duration: CPM feedback keys remain None when pre_state_cpm not provided."""
        doc = _make_cpm_doc()
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=None,
        )
        self.assertEqual(result.changes_applied, 1)
        fb = result.per_change_feedback[0].feedback
        self.assertIsNone(fb["activity_end_before"])
        self.assertIsNone(fb["activity_end_after"])
        self.assertIsNone(fb["milestone_impact_days"])
        self.assertIsNone(fb["now_on_critical_path"])

    # ---- Test 3: post_cpm_summary populated when pre_state_cpm provided ------

    def test_post_cpm_summary_populated_with_pre_state_cpm(self):
        """All five post_cpm_summary keys are populated when pre_state_cpm provided."""
        import copy
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        s = result.post_cpm_summary
        self.assertIsNotNone(s)
        self.assertIn("target_milestone_id", s)
        self.assertIn("completion_before", s)
        self.assertIn("completion_after", s)
        self.assertIn("net_days_change", s)
        self.assertIn("critical_path_changed", s)
        self.assertIn("substantial_cp_change", s)
        # All values should be set (not all None)
        self.assertIsNotNone(s["completion_before"])
        self.assertIsNotNone(s["completion_after"])
        self.assertIsNotNone(s["net_days_change"])
        self.assertIsInstance(s["critical_path_changed"], bool)
        self.assertIsInstance(s["substantial_cp_change"], bool)

    # ---- Test 4: post_cpm_summary remains None when pre_state_cpm is None ----

    def test_post_cpm_summary_none_without_pre_state_cpm(self):
        """post_cpm_summary stays None when pre_state_cpm is not provided."""
        doc = _make_cpm_doc()
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=None,
        )
        self.assertIsNone(result.post_cpm_summary)

    # ---- Test 5: target_milestone_id auto-detection -------------------------

    def test_target_milestone_auto_detected(self):
        """When target_milestone_id is not provided, the TT_FinMile is auto-selected."""
        import copy
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            # target_milestone_id omitted — auto-detect
        )
        s = result.post_cpm_summary
        self.assertIsNotNone(s)
        # Auto-detected milestone should be M3000 (task_id="3")
        self.assertEqual(s["target_milestone_id"], "3")
        self.assertIsNotNone(s["completion_before"])

    # ---- Test 6: target_milestone_id explicit --------------------------------

    def test_target_milestone_explicit(self):
        """Explicit target_milestone_id is used for milestone impact calculation."""
        import copy
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        s = result.post_cpm_summary
        self.assertIsNotNone(s)
        self.assertEqual(s["target_milestone_id"], "3")

    # ---- Test 7: set_duration impact — net_days_change is negative (pull-in) -

    def test_set_duration_cuts_milestone(self):
        """Cutting A1000 from 10d to 5d pulls the milestone in; net_days_change < 0."""
        import copy
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        s = result.post_cpm_summary
        self.assertIsNotNone(s)
        # The milestone should be pulled in (negative net_days_change)
        self.assertLess(s["net_days_change"], 0)
        # activity_end_after should be earlier than before
        fb = result.per_change_feedback[0].feedback
        self.assertLess(fb["activity_end_after"], fb["activity_end_before"])

    # ---- Test 8: add_activity feedback — before is None, after is populated --

    def test_add_activity_before_none_after_populated(self):
        """add_activity: activity_end_before is None (didn't exist); after keys exist."""
        import copy
        from xer_io import XerSection

        # _make_cpm_doc needs a PROJWBS section for add_activity to succeed
        doc = _make_cpm_doc()
        projwbs_section = XerSection(
            name="PROJWBS",
            field_order=["wbs_id", "proj_id", "wbs_name", "wbs_code",
                         "wbs_short_name", "parent_wbs_id", "status_code"],
            rows=[{
                "wbs_id": "1", "proj_id": "1", "wbs_name": "Root",
                "wbs_code": "ROOT", "wbs_short_name": "RT",
                "parent_wbs_id": "", "status_code": "WS_Open",
            }],
            raw_lines=[""],
            e_line=None,
        )
        doc.sections.append(projwbs_section)

        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{
                "type": "add_activity",
                "spec": {
                    "code": "X9999",
                    "name": "New Activity",
                    "duration_days": 3,
                    "calendar_id": "100",
                    "wbs_id": "1",
                    "activity_type": "TT_Task",
                },
            }],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        self.assertIsNotNone(result.doc)
        fb = result.per_change_feedback[0].feedback
        # Before must be None (activity didn't exist in pre-state)
        self.assertIsNone(fb["activity_end_before"])
        # Keys must exist regardless of after value
        self.assertIn("activity_end_before", fb)
        self.assertIn("activity_end_after", fb)

    # ---- Test 9: remove_activity feedback — before populated, after is None --

    def test_remove_activity_before_populated_after_none(self):
        """remove_activity: before = pre-state EF of removed activity; after = None."""
        import copy
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        result = apply_changes(
            doc,
            [{"type": "remove_activity", "activity_id": "A1000"}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        self.assertIsNotNone(result.doc)
        fb = result.per_change_feedback[0].feedback
        # Before is populated (A1000 existed and had an EF in the pre-state)
        self.assertIsNotNone(fb["activity_end_before"])
        # After is None (activity is gone)
        self.assertIsNone(fb["activity_end_after"])

    # ---- Test 10: WBS handler feedback unchanged ----------------------------

    def test_wbs_handler_feedback_unchanged(self):
        """add_wbs feedback dict has its own keys; CPM keys are absent (not patched)."""
        import copy
        # Use _make_cpm_doc which has a PROJWBS section (wbs_id="1")
        doc = _make_cpm_doc()
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        # Need a PROJWBS section in the doc for add_wbs to work
        from xer_io import XerSection
        projwbs_section = XerSection(
            name="PROJWBS",
            field_order=["wbs_id", "proj_id", "wbs_name", "wbs_code",
                         "wbs_short_name", "parent_wbs_id", "status_code"],
            rows=[{
                "wbs_id": "1", "proj_id": "1", "wbs_name": "Root",
                "wbs_code": "ROOT", "wbs_short_name": "RT",
                "parent_wbs_id": "", "status_code": "WS_Open",
            }],
            raw_lines=[""],
            e_line=None,
        )
        doc.sections.append(projwbs_section)

        result = apply_changes(
            doc,
            [{
                "type": "add_wbs",
                "spec": {
                    "wbs_code": "CHILD",
                    "wbs_name": "Child Node",
                    "parent_wbs_id": "1",
                },
            }],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        self.assertIsNotNone(result.doc)
        fb = result.per_change_feedback[0].feedback
        # WBS handler feedback has its own keys
        self.assertIn("new_wbs_id", fb)
        # CPM keys are NOT present in WBS handler feedback
        self.assertNotIn("activity_end_before", fb)
        self.assertNotIn("activity_end_after", fb)

    # ---- Test 11: critical_path_changed fires when TF crosses threshold ------

    def test_critical_path_changed_fires(self):
        """A task that gains float (and leaves CP) triggers critical_path_changed=True."""
        import copy
        # Use a doc where shortening A1000 causes it to still be critical,
        # but adding float to A2000 would change CP status.
        # Build a doc where A1000 has parallel non-critical path:
        #   A1000 (10d) -FS-> M3000
        #   A1000 (10d) -FS-> A2000 (5d) -FS-> M3000
        # After shortening A2000, it gains float and leaves CP.
        from xer_io import XerDoc, XerSection

        task_field_order = [
            "task_id", "proj_id", "wbs_id", "clndr_id", "phys_complete_pct",
            "task_type", "duration_type", "status_code", "task_code", "task_name",
            "total_float_hr_cnt", "free_float_hr_cnt",
            "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
            "early_start_date", "early_end_date",
            "late_start_date", "late_end_date",
            "act_start_date", "act_end_date",
        ]
        # A1000 (10d) is longer path; A2000 (10d) is parallel; M3000 is terminal
        task_rows = [
            {
                "task_id": "1", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
                "phys_complete_pct": "0", "task_type": "TT_Task",
                "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
                "task_code": "A1000", "task_name": "Path A",
                "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
                "target_drtn_hr_cnt": "80", "remain_drtn_hr_cnt": "80",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "act_start_date": "", "act_end_date": "",
            },
            {
                "task_id": "2", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
                "phys_complete_pct": "0", "task_type": "TT_Task",
                "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
                "task_code": "A2000", "task_name": "Path B (parallel)",
                "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
                "target_drtn_hr_cnt": "80", "remain_drtn_hr_cnt": "80",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "act_start_date": "", "act_end_date": "",
            },
            {
                "task_id": "3", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
                "phys_complete_pct": "0", "task_type": "TT_FinMile",
                "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
                "task_code": "M3000", "task_name": "Finish",
                "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
                "target_drtn_hr_cnt": "0", "remain_drtn_hr_cnt": "0",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "act_start_date": "", "act_end_date": "",
            },
        ]
        pred_field_order = ["task_pred_id", "task_id", "pred_task_id",
                            "proj_id", "pred_proj_id", "pred_type", "lag_hr_cnt"]
        # Both A1000 and A2000 lead to M3000; both start at data_date
        pred_rows = [
            {"task_pred_id": "1", "task_id": "3", "pred_task_id": "1",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
            {"task_pred_id": "2", "task_id": "3", "pred_task_id": "2",
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
        ]
        cal_field_order = ["clndr_id", "default_flag", "clndr_name", "proj_id",
                           "base_clndr_id", "last_chng_date", "clndr_type", "day_hr_cnt"]
        cal_rows = [{
            "clndr_id": "100", "default_flag": "Y", "clndr_name": "Standard",
            "proj_id": "1", "base_clndr_id": "", "last_chng_date": "",
            "clndr_type": "CT_Base", "day_hr_cnt": "8",
        }]
        proj_field_order = ["proj_id", "last_recalc_date", "plan_start_date"]
        proj_rows = [{"proj_id": "1", "last_recalc_date": "2026-01-01 08:00",
                      "plan_start_date": ""}]

        task_section = XerSection(
            name="TASK", field_order=task_field_order, rows=task_rows,
            raw_lines=["\t".join(r[f] for f in task_field_order) for r in task_rows],
            e_line=None,
        )
        pred_section = XerSection(
            name="TASKPRED", field_order=pred_field_order, rows=pred_rows,
            raw_lines=["\t".join(r[f] for f in pred_field_order) for r in pred_rows],
            e_line=None,
        )
        cal_section = XerSection(
            name="CALENDAR", field_order=cal_field_order, rows=cal_rows,
            raw_lines=["\t".join(r[f] for f in cal_field_order) for r in cal_rows],
            e_line=None,
        )
        proj_section = XerSection(
            name="PROJECT", field_order=proj_field_order, rows=proj_rows,
            raw_lines=["\t".join(r[f] for f in proj_field_order) for r in proj_rows],
            e_line=None,
        )
        doc = XerDoc(
            header_line="ERMHDR\t...", encoding="cp1252",
            sections=[task_section, pred_section, cal_section, proj_section],
        )

        # Pre-state: both A1000 and A2000 are critical (parallel same-length)
        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))
        pre_tfs = {r["task_code"]: float(r.get("total_float_hr_cnt") or "0") for r in pre_cpm}
        # Both should be at 0 float (parallel equal paths)
        self.assertLessEqual(pre_tfs.get("A1000", 999), 8)
        self.assertLessEqual(pre_tfs.get("A2000", 999), 8)

        # Shorten A2000 so it gains float and leaves CP
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A2000", "new_duration_days": 5}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="3",
        )
        self.assertIsNotNone(result.doc)
        s = result.post_cpm_summary
        self.assertIsNotNone(s)
        # A2000 left the critical path → critical_path_changed should be True
        self.assertTrue(s["critical_path_changed"])

    # ---- Test 12: substantial_cp_change fires when > 5 activities change -----

    def test_substantial_cp_change_fires(self):
        """Substantial CP change flag fires when > 5 activities move on/off CP."""
        import copy
        from xer_io import XerDoc, XerSection

        # Build a schedule with 7 parallel paths to the milestone.
        # When we shorten one dominant path, the others leave CP.
        # Initial topology: 7 tasks (T1..T7) all 10d long, all FS to M.
        # All are critical (parallel equal paths → TF=0).
        # Shortening T1 to 1d pulls the milestone in by 9 days;
        # T2..T7 gain 9d of float and leave CP (6 tasks change CP status).

        task_field_order = [
            "task_id", "proj_id", "wbs_id", "clndr_id", "phys_complete_pct",
            "task_type", "duration_type", "status_code", "task_code", "task_name",
            "total_float_hr_cnt", "free_float_hr_cnt",
            "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
            "early_start_date", "early_end_date",
            "late_start_date", "late_end_date",
            "act_start_date", "act_end_date",
        ]
        # T0001 = 10 days (drives the milestone); T0002..T0007 = 8 days
        # (16h float in pre-state → NOT critical).  After cutting T0001 to 1d,
        # T0002..T0007 become the driving paths (TF=0, critical) and T0001
        # gains float (non-critical).  7 activities change CP status (>5).
        task_rows = []
        for i in range(1, 8):
            drtn = "80" if i == 1 else "64"  # T0001=10d, T0002..T0007=8d
            task_rows.append({
                "task_id": str(i), "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
                "phys_complete_pct": "0", "task_type": "TT_Task",
                "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
                "task_code": f"T{i:04d}", "task_name": f"Task {i}",
                "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
                "target_drtn_hr_cnt": drtn, "remain_drtn_hr_cnt": drtn,
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "act_start_date": "", "act_end_date": "",
            })
        # Milestone
        task_rows.append({
            "task_id": "99", "proj_id": "1", "wbs_id": "1", "clndr_id": "100",
            "phys_complete_pct": "0", "task_type": "TT_FinMile",
            "duration_type": "DT_FixedDUR2", "status_code": "TK_NotStart",
            "task_code": "M9999", "task_name": "Finish",
            "total_float_hr_cnt": "0", "free_float_hr_cnt": "0",
            "target_drtn_hr_cnt": "0", "remain_drtn_hr_cnt": "0",
            "early_start_date": "", "early_end_date": "",
            "late_start_date": "", "late_end_date": "",
            "act_start_date": "", "act_end_date": "",
        })

        pred_field_order = ["task_pred_id", "task_id", "pred_task_id",
                            "proj_id", "pred_proj_id", "pred_type", "lag_hr_cnt"]
        pred_rows = [
            {"task_pred_id": str(i), "task_id": "99", "pred_task_id": str(i),
             "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_FS", "lag_hr_cnt": "0"}
            for i in range(1, 8)
        ]
        cal_field_order = ["clndr_id", "default_flag", "clndr_name", "proj_id",
                           "base_clndr_id", "last_chng_date", "clndr_type", "day_hr_cnt"]
        cal_rows = [{
            "clndr_id": "100", "default_flag": "Y", "clndr_name": "Standard",
            "proj_id": "1", "base_clndr_id": "", "last_chng_date": "",
            "clndr_type": "CT_Base", "day_hr_cnt": "8",
        }]
        proj_field_order = ["proj_id", "last_recalc_date", "plan_start_date"]
        proj_rows = [{"proj_id": "1", "last_recalc_date": "2026-01-01 08:00",
                      "plan_start_date": ""}]

        def _make_section(name, field_order, rows):
            return XerSection(
                name=name, field_order=field_order, rows=rows,
                raw_lines=["\t".join(r.get(f, "") for f in field_order) for r in rows],
                e_line=None,
            )

        doc = XerDoc(
            header_line="ERMHDR\t...", encoding="cp1252",
            sections=[
                _make_section("TASK", task_field_order, task_rows),
                _make_section("TASKPRED", pred_field_order, pred_rows),
                _make_section("CALENDAR", cal_field_order, cal_rows),
                _make_section("PROJECT", proj_field_order, proj_rows),
            ],
        )

        pre_cpm = _make_pre_state_cpm(copy.deepcopy(doc))

        # Pre-state: only T0001 is critical (it drives the milestone).
        # T0002..T0007 have 16h float (not critical).
        # Shorten T0001 to 1d: T0002..T0007 now drive the milestone (6 gain CP)
        # and T0001 leaves CP.  Total changes = 7 > 5 → substantial_cp_change.
        result = apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "T0001", "new_duration_days": 1}],
            strict=False,
            dry_run=False,
            pre_state_cpm=pre_cpm,
            target_milestone_id="99",
        )
        self.assertIsNotNone(result.doc)
        s = result.post_cpm_summary
        self.assertIsNotNone(s)
        # 7 activities changed CP status (T0001 off + T0002..T0007 on) → > 5
        self.assertTrue(s["substantial_cp_change"])


# ---------------------------------------------------------------------------
# Task F1: create_from_template
# ---------------------------------------------------------------------------

_SKELETON = (
    Path(__file__).parent.parent.parent.parent
    / "mcp-server" / "templates" / "westland-skeleton-v1.xer"
)

_BASE_METADATA = {
    "project_name": "Test Project",
    "project_id":   "TEST-001",
    "planned_start": "2026-06-01",
    "planned_data_date": "2026-06-01 08:00",
}


class TestCreateFromTemplate(unittest.TestCase):
    """Task F1 — create_from_template TDD suite."""

    # ------------------------------------------------------------------
    # Test 1 (verbatim plan test)
    # ------------------------------------------------------------------

    def test_loads_skeleton_and_sets_metadata(self):
        """Verbatim plan test: loads skeleton XER and stamps project_name."""
        skeleton = (Path(__file__).parent.parent.parent.parent
                    / "mcp-server" / "templates" / "westland-skeleton-v1.xer")
        metadata = {
            "project_name": "Test Project",
            "project_id":   "TEST-001",
            "planned_start": "2026-06-01",
            "planned_data_date": "2026-06-01 08:00",
        }
        doc = create_from_template(str(skeleton), metadata)
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["proj_short_name"], "Test Project")

    # ------------------------------------------------------------------
    # Test 2 — proj_id propagation: no lingering "TEMPLATE" tokens
    # ------------------------------------------------------------------

    def test_proj_id_propagated_to_all_sections(self):
        """Every proj_id field across all sections must equal the new project_id."""
        doc = create_from_template(str(_SKELETON), _BASE_METADATA)

        # PROJECT
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["proj_id"], "TEST-001")

        # SCHEDOPTIONS
        sched = doc.section("SCHEDOPTIONS")
        self.assertIsNotNone(sched)
        for row in sched.rows:
            if "proj_id" in row:
                self.assertEqual(row["proj_id"], "TEST-001",
                                 f"SCHEDOPTIONS row still has old proj_id: {row}")

        # PROJWBS — all 21 rows
        projwbs = doc.section("PROJWBS")
        self.assertIsNotNone(projwbs)
        for row in projwbs.rows:
            if "proj_id" in row:
                self.assertEqual(row["proj_id"], "TEST-001",
                                 f"PROJWBS row still has old proj_id: {row.get('wbs_id')}")

        # TASK
        task = doc.section("TASK")
        self.assertIsNotNone(task)
        for row in task.rows:
            if "proj_id" in row:
                self.assertEqual(row["proj_id"], "TEST-001",
                                 f"TASK row still has old proj_id: {row.get('task_code')}")

        # TASKPRED — proj_id AND pred_proj_id
        taskpred = doc.section("TASKPRED")
        self.assertIsNotNone(taskpred)
        for row in taskpred.rows:
            if "proj_id" in row:
                self.assertEqual(row["proj_id"], "TEST-001",
                                 f"TASKPRED row proj_id still old: {row}")
            if "pred_proj_id" in row:
                self.assertEqual(row["pred_proj_id"], "TEST-001",
                                 f"TASKPRED row pred_proj_id still old: {row}")

        # CALENDAR
        calendar = doc.section("CALENDAR")
        self.assertIsNotNone(calendar)
        for row in calendar.rows:
            if "proj_id" in row:
                self.assertEqual(row["proj_id"], "TEST-001",
                                 f"CALENDAR row still has old proj_id: {row}")

        # Confirm nothing in the entire doc still has "TEMPLATE" as a proj_id value
        for section in doc.sections:
            for row in section.rows:
                if row.get("proj_id") == "TEMPLATE":
                    self.fail(
                        f"Lingering 'TEMPLATE' proj_id in section {section.name}: {row}"
                    )
                if row.get("pred_proj_id") == "TEMPLATE":
                    self.fail(
                        f"Lingering 'TEMPLATE' pred_proj_id in section {section.name}: {row}"
                    )

    # ------------------------------------------------------------------
    # Test 3 — planned_start normalization
    # ------------------------------------------------------------------

    def test_planned_start_no_time_appends_0800(self):
        """Date-only string "YYYY-MM-DD" is normalized to "YYYY-MM-DD 08:00"."""
        meta = dict(_BASE_METADATA, planned_start="2026-06-01")
        doc = create_from_template(str(_SKELETON), meta)
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["plan_start_date"], "2026-06-01 08:00")

    def test_planned_start_with_time_preserved_as_is(self):
        """Datetime string "YYYY-MM-DD HH:MM" is used verbatim."""
        meta = dict(_BASE_METADATA, planned_start="2026-06-01 09:30")
        doc = create_from_template(str(_SKELETON), meta)
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["plan_start_date"], "2026-06-01 09:30")

    # ------------------------------------------------------------------
    # Test 4 — planned_data_date
    # ------------------------------------------------------------------

    def test_planned_data_date_sets_last_recalc_date(self):
        """planned_data_date is written to PROJECT.last_recalc_date."""
        meta = dict(_BASE_METADATA, planned_data_date="2026-06-15 08:00")
        doc = create_from_template(str(_SKELETON), meta)
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["last_recalc_date"], "2026-06-15 08:00")

    # ------------------------------------------------------------------
    # Test 5 — missing project_name raises ValidationFailure
    # ------------------------------------------------------------------

    def test_missing_project_name_raises(self):
        """Omitting project_name raises ValidationFailure."""
        meta = {"project_id": "TEST-001"}
        with self.assertRaises(ValidationFailure) as ctx:
            create_from_template(str(_SKELETON), meta)
        self.assertIn("project_name", str(ctx.exception))

    # ------------------------------------------------------------------
    # Test 6 — missing project_id raises ValidationFailure
    # ------------------------------------------------------------------

    def test_missing_project_id_raises(self):
        """Omitting project_id raises ValidationFailure."""
        meta = {"project_name": "Test Project"}
        with self.assertRaises(ValidationFailure) as ctx:
            create_from_template(str(_SKELETON), meta)
        self.assertIn("project_id", str(ctx.exception))

    # ------------------------------------------------------------------
    # Test 7 — round-trip: write to temp file, re-parse, assert persistence
    # ------------------------------------------------------------------

    def test_round_trip_dirty_marking(self):
        """write() + re-parse preserves proj_short_name — proves dirty marking worked."""
        import tempfile
        import os
        from xer_io import write, parse_for_writing

        doc = create_from_template(str(_SKELETON), _BASE_METADATA)

        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            write(doc, tmp_path)
            reparsed = parse_for_writing(tmp_path)
            project_row = reparsed.section("PROJECT").rows[0]
            self.assertEqual(project_row["proj_short_name"], "Test Project")
            # Also verify proj_id propagated through the round-trip
            self.assertEqual(project_row["proj_id"], "TEST-001")
        finally:
            os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Test 8 — validate clean: import_ready True after stamping
    # ------------------------------------------------------------------

    def test_validate_clean(self):
        """xer_validate.validate on the stamped doc yields import_ready=True."""
        # xer_validate is in the lib directory, which is already on sys.path via
        # the LIB insert at the top of this test module.
        from xer_validate import validate  # noqa: PLC0415

        doc = create_from_template(str(_SKELETON), _BASE_METADATA)
        report = validate(doc)
        errors = [i for i in report.issues if i.severity == "error"]
        self.assertTrue(
            report.import_ready,
            f"Expected import_ready=True but got errors: {[i.message for i in errors]}"
        )

    # ------------------------------------------------------------------
    # Test 9 — task_code_prefix optional
    # ------------------------------------------------------------------

    def test_task_code_prefix_omitted_leaves_skeleton_value(self):
        """Omitting task_code_prefix leaves whatever the skeleton had in that field."""
        doc_without = create_from_template(str(_SKELETON), _BASE_METADATA)
        skeleton_doc = __import__("xer_io").parse_for_writing(str(_SKELETON))
        skeleton_prefix = skeleton_doc.section("PROJECT").rows[0].get("task_code_prefix", "")
        stamped_prefix = doc_without.section("PROJECT").rows[0].get("task_code_prefix", "")
        self.assertEqual(stamped_prefix, skeleton_prefix)

    def test_task_code_prefix_provided_is_set(self):
        """Providing task_code_prefix writes it to PROJECT.task_code_prefix."""
        meta = dict(_BASE_METADATA, task_code_prefix="A")
        doc = create_from_template(str(_SKELETON), meta)
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["task_code_prefix"], "A")

    # ------------------------------------------------------------------
    # Test 10 — milestones intact after stamping
    # ------------------------------------------------------------------

    def test_milestones_intact_after_stamping(self):
        """TASK still has MILESTONE-NTP and MILESTONE-SC; TASKPRED has the FS edge."""
        doc = create_from_template(str(_SKELETON), _BASE_METADATA)

        task = doc.section("TASK")
        codes = {row["task_code"] for row in task.rows}
        self.assertIn("MILESTONE-NTP", codes,
                      "MILESTONE-NTP missing from TASK after stamping")
        self.assertIn("MILESTONE-SC", codes,
                      "MILESTONE-SC missing from TASK after stamping")

        taskpred = doc.section("TASKPRED")
        self.assertEqual(len(taskpred.rows), 1,
                         f"Expected 1 TASKPRED row, got {len(taskpred.rows)}")
        edge = taskpred.rows[0]
        self.assertEqual(edge["pred_type"], "PR_FS")


# ---------------------------------------------------------------------------
# TestFixDuplicateIds — tests for fix_duplicate_ids (F2)
# ---------------------------------------------------------------------------

_DUP_FIXTURE = (
    Path(__file__).parent.parent.parent.parent
    / "mcp-server" / "tests" / "fixtures" / "duplicate_ids.xer"
)


def _make_dup_doc(task_rows, taskpred_rows=None):
    """Build an in-memory XerDoc with TASK (and optionally TASKPRED) sections.

    task_rows: list of dicts with at least:
        {"task_id", "task_code", "target_drtn_hr_cnt", "wbs_id"}
    Minimal fields only — enough for fix_duplicate_ids.
    """
    from xer_io import XerDoc, XerSection

    task_field_order = [
        "task_id", "proj_id", "wbs_id", "task_code",
        "task_name", "target_drtn_hr_cnt", "remain_drtn_hr_cnt",
    ]
    task_section = XerSection(
        name="TASK",
        field_order=task_field_order,
        rows=list(task_rows),
        raw_lines=[
            "%R\t{task_id}\t{proj_id}\t{wbs_id}\t{task_code}\t{task_name}"
            "\t{target_drtn_hr_cnt}\t{remain_drtn_hr_cnt}".format(**r)
            for r in task_rows
        ],
        e_line=None,
    )
    sections = [task_section]

    if taskpred_rows is not None:
        taskpred_field_order = [
            "task_pred_id", "task_id", "pred_task_id",
            "proj_id", "pred_proj_id", "pred_type", "lag_hr_cnt",
        ]
        taskpred_section = XerSection(
            name="TASKPRED",
            field_order=taskpred_field_order,
            rows=list(taskpred_rows),
            raw_lines=[
                "%R\t{task_pred_id}\t{task_id}\t{pred_task_id}"
                "\t{proj_id}\t{pred_proj_id}\t{pred_type}\t{lag_hr_cnt}".format(**r)
                for r in taskpred_rows
            ],
            e_line=None,
        )
        sections.append(taskpred_section)

    return XerDoc(
        header_line="ERMHDR\t...",
        encoding="cp1252",
        sections=sections,
    )


def _dup_task_row(task_id, task_code, target_drtn="40", wbs_id="1000",
                  task_name=None):
    if task_name is None:
        task_name = f"Activity {task_code}"
    return {
        "task_id": str(task_id),
        "proj_id": "1",
        "wbs_id": str(wbs_id),
        "task_code": task_code,
        "task_name": task_name,
        "target_drtn_hr_cnt": str(target_drtn),
        "remain_drtn_hr_cnt": str(target_drtn),
    }


def _dup_tp_row(tpid, succ_id, pred_id):
    return {
        "task_pred_id": str(tpid),
        "task_id": str(succ_id),
        "pred_task_id": str(pred_id),
        "proj_id": "1",
        "pred_proj_id": "1",
        "pred_type": "PR_FS",
        "lag_hr_cnt": "0",
    }


class TestFixDuplicateIds(unittest.TestCase):
    """Tests for fix_duplicate_ids (F2 spec)."""

    # ------------------------------------------------------------------
    # Test 1: report_only on fixture — duplicates detected, doc unmutated
    # ------------------------------------------------------------------

    def test_report_only_fixture_detects_duplicates(self):
        """report_only on duplicate_ids.xer: 3-row A1010 group -> 2 renames proposed,
        doc untouched."""
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(_DUP_FIXTURE))

        mutated_doc, result = fix_duplicate_ids(doc, strategy="report_only")

        # 3 rows share A1010 -> 2 are duplicates (the second and third occurrences)
        self.assertEqual(result["duplicates_found"], 2)
        self.assertEqual(len(result["mapping"]), 2)
        self.assertEqual(result["unresolved"], [])

        # mapping entries have required keys
        for entry in result["mapping"]:
            self.assertIn("original_id", entry)
            self.assertIn("new_id", entry)
            self.assertIn("task_name", entry)
            self.assertIn("reason", entry)
            # original_id is A1010 for both
            self.assertEqual(entry["original_id"], "A1010")
            # proposed new_id must differ from A1010
            self.assertNotEqual(entry["new_id"], "A1010")

        # doc must be unmutated: all 3 task_codes still "A1010"
        task = mutated_doc.section("TASK")
        codes = [r["task_code"] for r in task.rows]
        self.assertEqual(codes.count("A1010"), 3,
                         "report_only must not mutate the document")

        # no rows should be dirty
        for i in range(len(task.rows)):
            if task.raw_lines is not None and i < len(task.raw_lines):
                self.assertNotIn(i, task._dirty,
                                 f"Row {i} is dirty but report_only should not mutate")

    # ------------------------------------------------------------------
    # Test 2: renumber on fixture — first A1010 kept, others renamed
    # ------------------------------------------------------------------

    def test_renumber_fixture_resolves_all_duplicates(self):
        """renumber on duplicate_ids.xer: first A1010 kept, 2 others renamed;
        no duplicate codes remain; mapping records both renames."""
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(_DUP_FIXTURE))

        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        self.assertEqual(result["duplicates_found"], 2)
        self.assertEqual(len(result["mapping"]), 2)
        self.assertEqual(result["unresolved"], [])

        # All mapping entries have required shape
        for entry in result["mapping"]:
            self.assertIn("original_id", entry)
            self.assertIn("new_id", entry)
            self.assertIn("task_name", entry)
            self.assertIn("reason", entry)
            self.assertEqual(entry["original_id"], "A1010")
            self.assertNotEqual(entry["new_id"], "A1010")

        # No duplicate task_codes remain in the mutated doc
        task = mutated_doc.section("TASK")
        all_codes = [r["task_code"] for r in task.rows]
        self.assertEqual(len(all_codes), len(set(all_codes)),
                         f"Duplicate codes remain after renumber: {all_codes}")

        # First occurrence of A1010 (row 0) keeps its code
        self.assertEqual(task.rows[0]["task_code"], "A1010")

        # The renamed rows are marked dirty
        # rows[1] and rows[2] were the duplicates — they should be dirty
        self.assertTrue(task.is_dirty(1), "Row 1 (2nd A1010) should be dirty")
        self.assertTrue(task.is_dirty(2), "Row 2 (3rd A1010) should be dirty")

    # ------------------------------------------------------------------
    # Test 3: renumber numeric-suffix policy
    # ------------------------------------------------------------------

    def test_renumber_numeric_suffix_policy(self):
        """codes A1000, A1010, A1010(dup), A1020 -> dup renames to A1030."""
        doc = _make_dup_doc([
            _dup_task_row(1, "A1000"),
            _dup_task_row(2, "A1010"),
            _dup_task_row(3, "A1010"),   # duplicate
            _dup_task_row(4, "A1020"),
        ])

        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        self.assertEqual(result["duplicates_found"], 1)
        task = mutated_doc.section("TASK")
        all_codes = {r["task_code"] for r in task.rows}
        # A1030 should be present (max existing numeric suffix is 20, +10 = 30)
        self.assertIn("A1030", all_codes,
                      f"Expected A1030 in renamed codes but got: {all_codes}")
        # Original A1010 (first occurrence) is kept
        self.assertIn("A1010", all_codes)
        # No duplicate codes
        codes_list = [r["task_code"] for r in task.rows]
        self.assertEqual(len(codes_list), len(set(codes_list)))

    # ------------------------------------------------------------------
    # Test 4: renumber non-numeric code policy
    # ------------------------------------------------------------------

    def test_renumber_non_numeric_policy(self):
        """Non-numeric codes: 'DEMO', 'DEMO'(dup) -> dup renames to 'DEMO-DUP1'."""
        doc = _make_dup_doc([
            _dup_task_row(1, "DEMO"),
            _dup_task_row(2, "DEMO"),   # duplicate
        ])

        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        self.assertEqual(result["duplicates_found"], 1)
        task = mutated_doc.section("TASK")
        all_codes = {r["task_code"] for r in task.rows}
        self.assertIn("DEMO", all_codes)
        self.assertIn("DEMO-DUP1", all_codes)

    # ------------------------------------------------------------------
    # Test 5: renumber collision avoidance
    # ------------------------------------------------------------------

    def test_renumber_collision_avoidance(self):
        """Two independent duplicate groups — no renamed code collides with
        existing codes or with each other."""
        doc = _make_dup_doc([
            _dup_task_row(1, "A1010"),
            _dup_task_row(2, "A1010"),   # dup -> would try A1020 (max+10) but A1020 exists
            _dup_task_row(3, "A1020"),
            _dup_task_row(4, "A1020"),   # dup -> would try A1030
        ])

        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        self.assertEqual(result["duplicates_found"], 2)
        task = mutated_doc.section("TASK")
        codes_list = [r["task_code"] for r in task.rows]
        # No duplicates at all
        self.assertEqual(len(codes_list), len(set(codes_list)),
                         f"Collision not avoided: {codes_list}")

    # ------------------------------------------------------------------
    # Test 6: no duplicates -> early return
    # ------------------------------------------------------------------

    def test_no_duplicates_returns_empty_result(self):
        """Clean doc (no duplicate task_codes) returns duplicates_found=0."""
        doc = _make_dup_doc([
            _dup_task_row(1, "A1010"),
            _dup_task_row(2, "A1020"),
            _dup_task_row(3, "A1030"),
        ])

        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        self.assertEqual(result["duplicates_found"], 0)
        self.assertEqual(result["mapping"], [])
        self.assertEqual(result["unresolved"], [])
        # doc unchanged
        task = mutated_doc.section("TASK")
        codes = [r["task_code"] for r in task.rows]
        self.assertEqual(codes, ["A1010", "A1020", "A1030"])

    # ------------------------------------------------------------------
    # Test 7: unknown strategy -> ValidationFailure
    # ------------------------------------------------------------------

    def test_unknown_strategy_raises(self):
        """Unknown strategy raises ValidationFailure."""
        doc = _make_dup_doc([_dup_task_row(1, "A1010")])
        with self.assertRaises(ValidationFailure):
            fix_duplicate_ids(doc, strategy="delete_all")

    # ------------------------------------------------------------------
    # Test 8: no TASK section -> ValidationFailure
    # ------------------------------------------------------------------

    def test_no_task_section_raises(self):
        """Missing TASK section raises ValidationFailure."""
        from xer_io import XerDoc
        doc = XerDoc(header_line="ERMHDR\t...", encoding="cp1252", sections=[])
        with self.assertRaises(ValidationFailure):
            fix_duplicate_ids(doc, strategy="renumber")

    # ------------------------------------------------------------------
    # Test 9: merge_consolidate true duplicate -> kept + edge rerouted
    # ------------------------------------------------------------------

    def test_merge_consolidate_true_dup_reroutes_edge(self):
        """Two rows same code, same duration, same wbs_id -> merge;
        TASKPRED edge referencing deleted task_id rerouted to kept task_id."""
        # task_id 10 and 20 both have code A1010, same duration, same wbs
        # task_id 30 has code A1020
        # edge: 30 (A1020) depends on 20 (A1010 dup) via FS
        # After merge: row 20 deleted, edge rerouted to task_id 10
        doc = _make_dup_doc(
            task_rows=[
                _dup_task_row(10, "A1010", target_drtn="40", wbs_id="1000"),
                _dup_task_row(20, "A1010", target_drtn="40", wbs_id="1000"),  # true dup
                _dup_task_row(30, "A1020", target_drtn="40", wbs_id="1000"),
            ],
            taskpred_rows=[
                _dup_tp_row(1, succ_id=30, pred_id=20),   # A1020 depends on dup A1010
            ],
        )

        mutated_doc, result = fix_duplicate_ids(doc, strategy="merge_consolidate")

        self.assertEqual(result["duplicates_found"], 1)
        self.assertEqual(result["unresolved"], [])

        task = mutated_doc.section("TASK")
        # Only one A1010 row should remain
        a1010_rows = [r for r in task.rows if r["task_code"] == "A1010"]
        self.assertEqual(len(a1010_rows), 1, "Expected exactly one A1010 row after merge")
        # It should be the FIRST occurrence (task_id "10")
        self.assertEqual(a1010_rows[0]["task_id"], "10")

        # The edge should now reference task_id "10" (the kept row), not "20"
        tp = mutated_doc.section("TASKPRED")
        self.assertIsNotNone(tp, "TASKPRED section should still exist")
        self.assertEqual(len(tp.rows), 1)
        self.assertEqual(tp.rows[0]["pred_task_id"], "10",
                         "Edge must be rerouted from deleted task_id 20 to kept task_id 10")

        # mapping reason mentions merge
        self.assertTrue(any("merged" in e["reason"].lower() for e in result["mapping"]),
                        f"Expected 'merged' in reason: {result['mapping']}")

    # ------------------------------------------------------------------
    # Test 10: merge_consolidate differing rows -> unresolved
    # ------------------------------------------------------------------

    def test_merge_consolidate_differing_rows_goes_to_unresolved(self):
        """Two rows same code but different duration -> unresolved, both rows kept."""
        doc = _make_dup_doc([
            _dup_task_row(10, "A1010", target_drtn="40", wbs_id="1000"),
            _dup_task_row(20, "A1010", target_drtn="80", wbs_id="1000"),   # different duration
        ])

        mutated_doc, result = fix_duplicate_ids(doc, strategy="merge_consolidate")

        # Should be unresolved
        self.assertTrue(len(result["unresolved"]) > 0,
                        "Expected unresolved entry for differing-duration group")
        # Both rows should still be present (untouched)
        task = mutated_doc.section("TASK")
        a1010_rows = [r for r in task.rows if r["task_code"] == "A1010"]
        self.assertEqual(len(a1010_rows), 2, "Both rows should be untouched")

    # ------------------------------------------------------------------
    # Test 11: renumber persists through round-trip (dirty-marking proof)
    # ------------------------------------------------------------------

    def test_renumber_round_trip(self):
        """renumber -> xer_io.write -> re-parse -> renamed codes present."""
        import tempfile
        import os
        from xer_io import parse_for_writing, write

        doc = parse_for_writing(str(_DUP_FIXTURE))

        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        # Write to a temp file
        with tempfile.NamedTemporaryFile(
            suffix=".xer", delete=False, mode="wb"
        ) as tmp:
            tmp_path = tmp.name
        try:
            write(mutated_doc, tmp_path)
            # Re-parse
            reparsed = parse_for_writing(tmp_path)
        finally:
            os.unlink(tmp_path)

        task = reparsed.section("TASK")
        all_codes = [r["task_code"] for r in task.rows]

        # No duplicates in the round-tripped file
        self.assertEqual(len(all_codes), len(set(all_codes)),
                         f"Duplicate codes after round-trip: {all_codes}")

        # The renamed codes from mapping are present
        for entry in result["mapping"]:
            self.assertIn(entry["new_id"], all_codes,
                          f"Renamed code {entry['new_id']!r} missing after round-trip")

    # ------------------------------------------------------------------
    # Test 12: xer_validate clean after renumber
    # ------------------------------------------------------------------

    def test_validate_clean_after_renumber(self):
        """xer_validate on the renumbered doc reports no DUPLICATE_ACTIVITY_ID error."""
        from xer_io import parse_for_writing
        from xer_validate import validate

        doc = parse_for_writing(str(_DUP_FIXTURE))
        mutated_doc, result = fix_duplicate_ids(doc, strategy="renumber")

        report = validate(mutated_doc)
        dup_errors = [
            i for i in report.issues
            if i.code == "DUPLICATE_ACTIVITY_ID"
        ]
        self.assertEqual(dup_errors, [],
                         f"DUPLICATE_ACTIVITY_ID errors remain: {dup_errors}")
