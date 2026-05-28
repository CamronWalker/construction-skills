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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(doc, [change], strict=False, dry_run=False)
        self.assertIn("name", str(ctx.exception))

    # ---- Test 3: duplicate task_code ----------------------------------------

    def test_duplicate_task_code_raises(self):
        """task_code already exists in TASK section; ValidationFailure names the code."""
        doc = _make_doc_with_task_wbs_calendar()
        # A1010 is the existing row's task_code
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [_add_activity_change(code="A1010")],
                strict=False,
                dry_run=False,
            )
        self.assertIn("A1010", str(ctx.exception))

    # ---- Test 4: unknown wbs_id ---------------------------------------------

    def test_unknown_wbs_id_raises(self):
        """wbs_id not in PROJWBS and not in state → ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [_add_activity_change(wbs_id="9999")],
                strict=False,
                dry_run=False,
            )
        self.assertIn("9999", str(ctx.exception))

    # ---- Test 5: unknown calendar_id ----------------------------------------

    def test_unknown_calendar_id_raises(self):
        """calendar_id not in CALENDAR and not in state → ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [_add_activity_change(calendar_id="999")],
                strict=False,
                dry_run=False,
            )
        self.assertIn("999", str(ctx.exception))

    # ---- Test 6: unknown activity_type --------------------------------------

    def test_unknown_activity_type_raises(self):
        """activity_type='TT_Bogus' raises ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [_add_activity_change(activity_type="TT_Bogus")],
                strict=False,
                dry_run=False,
            )
        self.assertIn("TT_Bogus", str(ctx.exception))

    # ---- Test 7: negative duration ------------------------------------------

    def test_negative_duration_raises(self):
        """duration_days=-1 raises ValidationFailure."""
        doc = _make_doc_with_task_wbs_calendar()
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [_add_activity_change(duration_days=-1)],
                strict=False,
                dry_run=False,
            )
        self.assertIn("-1", str(ctx.exception))

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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("modify_logic", str(ctx.exception))

    # ---- Test 5: predecessor not found ---------------------------------------

    def test_predecessor_not_found_raises(self):
        """ValidationFailure naming the missing predecessor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("ZZZPRED", str(ctx.exception))

    # ---- Test 6: successor not found -----------------------------------------

    def test_successor_not_found_raises(self):
        """ValidationFailure naming the missing successor activity_id."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        self.assertIn("ZZZSUCC", str(ctx.exception))

    # ---- Test 7: edge not found (wrong selector type) ------------------------

    def test_edge_not_found_raises(self):
        """TASKPRED has (A1010→A1020, FS); selecting SS raises ValidationFailure."""
        doc = self._two_activity_doc(taskpred_rows=[self._fs_row()])
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        err = str(ctx.exception)
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)

    # ---- Test 8: multiple matching rows → ValidationFailure ------------------

    def test_multiple_matching_rows_raises(self):
        """Two identical (pred, succ, type) rows in TASKPRED → ValidationFailure."""
        dup_a = self._fs_row(tpid="5001", lag="8")
        dup_b = self._fs_row(tpid="5002", lag="16")   # same triple, different lag
        doc = self._two_activity_doc(taskpred_rows=[dup_a, dup_b])
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        err = str(ctx.exception)
        self.assertIn("A1010", err)
        self.assertIn("A1020", err)

    # ---- Test 9: duplicate new edge → ValidationFailure ---------------------

    def test_duplicate_new_edge_raises(self):
        """TASKPRED has (A,B,FS) and (A,B,SS); modify (A,B,FS) → SS would create duplicate."""
        doc = self._two_activity_doc(
            taskpred_rows=[self._fs_row(tpid="5001"), self._ss_row(tpid="5002")]
        )
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
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
        err = str(ctx.exception)
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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [_remove_activity_change("ZZZZ")],
                strict=False,
                dry_run=False,
            )
        self.assertIn("ZZZZ", str(ctx.exception))

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
        apply_changes(
            doc,
            [_remove_activity_change("A1020")],
            strict=False,
            dry_run=False,
        )

        task = doc.section("TASK")
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

        apply_changes(
            doc,
            [_remove_activity_change("TARGET")],
            strict=False,
            dry_run=False,
        )

        tp = doc.section("TASKPRED")
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

        apply_changes(
            doc,
            [_remove_activity_change("A1010")],
            strict=False,
            dry_run=False,
        )

        tp = doc.section("TASKPRED")
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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [{"type": "dissolve_activity", "activity_id": "ZZZZ"}],
                strict=False,
                dry_run=False,
            )
        self.assertIn("ZZZZ", str(ctx.exception))

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
        with self.assertRaises(ValidationFailure) as ctx:
            apply_changes(
                doc,
                [{"type": "dissolve_activity", "activity_id": "D"}],
                strict=False,
                dry_run=False,
            )
        err = str(ctx.exception)
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

        apply_changes(
            doc,
            [{"type": "dissolve_activity", "activity_id": "D"}],
            strict=False,
            dry_run=False,
        )

        tp = doc.section("TASKPRED")
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
