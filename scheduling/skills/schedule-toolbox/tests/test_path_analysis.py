"""Tests for path_analysis's explicit milestone_id contract.

D3 removed the brittle name-based ``_find_sc_milestone`` heuristic from
``path_analysis`` and replaced it with an explicit ``milestone_id``
parameter + the shared auto-resolver from ``milestones`` that picks the
unique terminal milestone or raises ``MilestoneAmbiguousError`` with the
candidate list.
"""
import unittest
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from path_analysis import analyze_sc_path_coverage
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
        "wbs_id": "",
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
        # explicitly even though SC is the natural terminal — the analysis
        # must honor what the caller passed.
        result = analyze_sc_path_coverage(tasks, preds, milestone_id="10001")
        self.assertEqual(result["sc_task_id"], "10001")
        self.assertEqual(result["sc_task_name"], "Notice to Proceed")

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

        result = analyze_sc_path_coverage(tasks, preds, milestone_id="2")
        self.assertEqual(result["sc_task_id"], "2")
        self.assertEqual(result["sc_task_name"], "Milestone A")


class TestAmbiguousMilestoneRaises(unittest.TestCase):
    """Two-terminal-milestone schedule with no explicit pick must raise."""

    def test_ambiguous_raises_with_candidates(self):
        tasks = [
            _task("1", "A1000", "Build foundation"),
            _task("2", "M_SC1", "Substantial Completion Phase 1", task_type="TT_FinMile"),
            _task("3", "M_SC2", "Substantial Completion Phase 2", task_type="TT_FinMile"),
        ]
        # Both milestones have a predecessor but no successors → both
        # terminal. resolve_default_milestone should raise.
        preds = [_pred("1", "2"), _pred("1", "3")]

        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            analyze_sc_path_coverage(tasks, preds)

        self.assertEqual(len(ctx.exception.candidates), 2)
        candidate_ids = {c["task_id"] for c in ctx.exception.candidates}
        self.assertEqual(candidate_ids, {"2", "3"})


class TestUnambiguousAutoSelects(unittest.TestCase):
    """Single-terminal-milestone schedule auto-resolves silently."""

    def test_unambiguous_auto_selects(self):
        # Use the minimal fixture — exactly one terminal milestone (SC,
        # task_id 10002). The other milestone (NTP, 10001) has SC as a
        # successor, so it's not terminal.
        parsed = _parse_xer(str(FIXTURE))
        result = analyze_sc_path_coverage(parsed["TASK"], parsed["TASKPRED"])
        self.assertEqual(result["sc_task_id"], "10002")
        self.assertEqual(result["sc_task_name"], "Substantial Completion")

    def test_no_milestones_returns_empty_coverage(self):
        # Schedule with no milestones at all — resolver returns None,
        # analyzer returns a "no SC milestone found" recommendation
        # (same behavior the old heuristic gave when it whiffed).
        tasks = [
            _task("1", "A1000", "Build"),
            _task("2", "A1010", "Finish"),
        ]
        preds = [_pred("1", "2")]

        result = analyze_sc_path_coverage(tasks, preds)
        self.assertIsNone(result["sc_task_id"])
        self.assertEqual(result["coverage_pct"], 0.0)
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertIn("terminal milestone", result["recommendations"][0].lower())


if __name__ == "__main__":
    unittest.main()
