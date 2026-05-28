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
