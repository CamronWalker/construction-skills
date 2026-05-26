"""Tests for score_schedule's explicit milestone_id contract.

D2 removed the brittle name-based ``find_sc_milestone`` heuristic and
replaced it with an explicit ``milestone_id`` parameter + an auto-resolver
that picks the unique terminal milestone or raises
``MilestoneAmbiguousError`` with the candidate list.
"""
import unittest
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from score_schedule import compute_quality_score, _resolve_default_milestone
from milestones import MilestoneAmbiguousError
from quality_checks import _parse_xer

FIXTURE = Path(__file__).parent.parent.parent.parent / "mcp-server" / "tests" / "fixtures" / "minimal.xer"


def _task(task_id, code, name, task_type="TT_Task", status="TK_NotStart", **extras):
    """Build a synthetic task dict matching the XER row shape."""
    base = {
        "task_id": task_id,
        "task_code": code,
        "task_name": name,
        "task_type": task_type,
        "status_code": status,
        "total_float_hr_cnt": "0",
        "target_drtn_hr_cnt": "8",
        "remain_drtn_hr_cnt": "8",
        "cstr_type": "",
        "cstr_type2": "",
    }
    base.update(extras)
    return base


def _pred(pred_id, succ_id, pred_type="PR_FS", lag="0"):
    return {
        "pred_task_id": pred_id,
        "task_id": succ_id,
        "pred_type": pred_type,
        "lag_hr_cnt": lag,
    }


class TestExplicitMilestoneId(unittest.TestCase):
    """When caller passes milestone_id, it is used directly without auto-resolution."""

    def test_explicit_milestone_id_used(self):
        parsed = _parse_xer(str(FIXTURE))
        tasks = parsed["TASK"]
        preds = parsed["TASKPRED"]

        # NTP is id=10001, SC is id=10002 in the minimal fixture. Pass NTP
        # explicitly even though SC is the natural terminal — the scorer
        # must honor what the caller passed.
        result = compute_quality_score(tasks, preds, None, milestone_id="10001")
        score, grade, scored, info, deductions, scope, details = result
        self.assertEqual(scope["milestone_id"], "10001")

    def test_explicit_milestone_id_skips_resolution(self):
        # Build a synthetic schedule with TWO terminal milestones — would
        # raise without an explicit milestone_id — and verify the explicit
        # path skips the auto-resolver entirely.
        tasks = [
            _task("1", "A1000", "Start activity"),
            _task("2", "M_A", "Milestone A", task_type="TT_FinMile"),
            _task("3", "M_B", "Milestone B", task_type="TT_FinMile"),
        ]
        preds = [_pred("1", "2"), _pred("1", "3")]

        result = compute_quality_score(tasks, preds, None, milestone_id="2")
        score, grade, scored, info, deductions, scope, details = result
        self.assertEqual(scope["milestone_id"], "2")


class TestAmbiguousMilestoneRaises(unittest.TestCase):
    """Two-terminal-milestone schedule with no explicit pick must raise."""

    def test_ambiguous_raises_with_candidates(self):
        tasks = [
            _task("1", "A1000", "Build foundation"),
            _task("2", "M_SC1", "Substantial Completion Phase 1", task_type="TT_FinMile"),
            _task("3", "M_SC2", "Substantial Completion Phase 2", task_type="TT_FinMile"),
        ]
        # Both milestones have a predecessor but no successors → both
        # terminal. _resolve_default_milestone should raise.
        preds = [_pred("1", "2"), _pred("1", "3")]

        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            compute_quality_score(tasks, preds, None)

        self.assertEqual(len(ctx.exception.candidates), 2)
        candidate_ids = {c["task_id"] for c in ctx.exception.candidates}
        self.assertEqual(candidate_ids, {"2", "3"})


class TestUnambiguousAutoSelects(unittest.TestCase):
    """Single-terminal-milestone schedule auto-resolves silently."""

    def test_unambiguous_auto_selects(self):
        # Use the minimal fixture — exactly one terminal milestone (SC).
        parsed = _parse_xer(str(FIXTURE))
        result = compute_quality_score(parsed["TASK"], parsed["TASKPRED"], None)
        score, grade, scored, info, deductions, scope, details = result
        self.assertEqual(scope["milestone_id"], "10002")

    def test_resolver_returns_none_when_no_milestones(self):
        # Schedule with no milestones at all — resolver returns None,
        # scorer falls back to full-incomplete-scope mode (no raise).
        tasks = [
            _task("1", "A1000", "Build"),
            _task("2", "A1010", "Finish"),
        ]
        preds = [_pred("1", "2")]
        self.assertIsNone(_resolve_default_milestone(tasks, preds))

        # And compute_quality_score still works.
        result = compute_quality_score(tasks, preds, None)
        score, grade, scored, info, deductions, scope, details = result
        self.assertIsNone(scope["milestone_id"])


if __name__ == "__main__":
    unittest.main()
