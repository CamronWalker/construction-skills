"""Tests for the mutation engine."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_modify import (  # noqa: E402
    apply_changes, ApplyResult, ChangeRecord, ValidationFailure,
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
            apply_changes(doc, [{"type": "wat"}], strict=False, dry_run=False)


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
        apply_changes(
            doc,
            [{"type": "set_duration", "activity_id": "A1010", "new_duration_days": 2}],
            strict=False,
            dry_run=False,
        )
        task_section = doc.section("TASK")
        self.assertTrue(task_section.is_dirty(0))

    def test_activity_not_found_raises(self):
        """set_duration raises ValidationFailure when activity_id not in TASK rows."""
        doc = _make_doc_with_task("A1010", target_drtn="40", remain_drtn="40")
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [{"type": "set_duration", "activity_id": "ZZZZ", "new_duration_days": 5}],
                strict=False,
                dry_run=False,
            )
        self.assertIn("ZZZZ", str(ctx.exception))

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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("ZZZPRED", str(ctx.exception))

    def test_successor_not_found_raises(self):
        """ValidationFailure naming the missing successor activity_id."""
        doc = self._two_activity_doc()
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("ZZZSUCC", str(ctx.exception))

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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        err = str(ctx.exception)
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
        apply_changes(
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
        tp = doc.section("TASKPRED")
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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("ZZZPRED", str(ctx.exception))

    # ---- Test 3: successor not found ----------------------------------------

    def test_successor_not_found_raises(self):
        """ValidationFailure naming the missing successor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("ZZZSUCC", str(ctx.exception))

    # ---- Test 4: edge not found (wrong type) ---------------------------------

    def test_edge_not_found_wrong_type_raises(self):
        """TASKPRED has (A1010→A1020, FS); removing SS raises with triple in message."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        err = str(ctx.exception)
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
        tp = doc.section("TASKPRED")
        self.assertEqual(len(tp.rows), 3)
        self.assertEqual(len(tp.raw_lines), 3)

        apply_changes(
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
        apply_changes(
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

        tp = doc.section("TASKPRED")
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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        err = str(ctx.exception)
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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [{"type": "set_calendar", "activity_id": "ZZZZ", "new_calendar_id": "200"}],
                strict=False,
                dry_run=False,
            )
        self.assertIn("ZZZZ", str(ctx.exception))

    def test_calendar_not_found_raises(self):
        """set_calendar raises ValidationFailure when calendar not in doc and not in state."""
        doc = _make_doc_with_task_and_calendar(
            task_code="A1010",
            target_drtn="40",
            remain_drtn="40",
            calendar_id="200",
        )
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [{"type": "set_calendar", "activity_id": "A1010", "new_calendar_id": "999"}],
                strict=False,
                dry_run=False,
            )
        self.assertIn("999", str(ctx.exception))

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
