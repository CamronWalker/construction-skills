"""Tests for cpm_engine's explicit milestone_id contract.

D4 removed the brittle name-based ``_find_sc_milestone`` heuristic from
``cpm_engine`` and replaced it with an explicit ``milestone_id`` parameter
plus structural auto-resolution via ``milestones.resolve_default_milestone``.

CPM correctness does not depend on the milestone -- it only populates the
informational ``sc_milestone_*`` metadata fields. Multi-terminal schedules
therefore *silently* fall through to None metadata rather than raise, so
transitive callers that don't care about SC keep working.
"""
import unittest
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from cpm_engine import schedule_forward_backward
from quality_checks import _parse_xer

FIXTURE = Path(__file__).parent.parent.parent.parent / "mcp-server" / "tests" / "fixtures" / "minimal.xer"


def _task(task_id, code, name, task_type="TT_Task", status="TK_NotStart", **extras):
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
        "clndr_id": "1",
        "early_start_date": "",
        "early_end_date": "",
        "late_start_date": "",
        "late_end_date": "",
        "target_start_date": "",
        "target_end_date": "",
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


class TestExplicitMilestoneIdInCpm(unittest.TestCase):
    """When caller passes milestone_id, metadata reflects it."""

    def test_explicit_milestone_id_used_in_metadata(self):
        parsed = _parse_xer(str(FIXTURE))
        data_date = parsed["PROJECT"][0].get("last_recalc_date", "") if parsed.get("PROJECT") else ""

        # Override SC = NTP (id 10001). Even though SC is the natural
        # terminal, metadata must reflect what the caller passed.
        results, meta = schedule_forward_backward(
            parsed["TASK"], parsed["TASKPRED"], parsed["CALENDAR"],
            data_date,
            schedoptions=parsed.get("SCHEDOPTIONS"),
            project=parsed.get("PROJECT"),
            milestone_id="10001",
        )
        self.assertEqual(meta["sc_milestone_id"], "10001")
        self.assertEqual(meta["sc_milestone_name"], "Notice to Proceed")

    def test_default_resolves_to_terminal_milestone(self):
        parsed = _parse_xer(str(FIXTURE))
        data_date = parsed["PROJECT"][0].get("last_recalc_date", "") if parsed.get("PROJECT") else ""

        results, meta = schedule_forward_backward(
            parsed["TASK"], parsed["TASKPRED"], parsed["CALENDAR"],
            data_date,
            schedoptions=parsed.get("SCHEDOPTIONS"),
            project=parsed.get("PROJECT"),
        )
        # minimal fixture has exactly one terminal milestone: SC (id 10002).
        self.assertEqual(meta["sc_milestone_id"], "10002")
        self.assertEqual(meta["sc_milestone_name"], "Substantial Completion")


class TestAmbiguousIsSwallowed(unittest.TestCase):
    """CPM is foundational -- multi-terminal schedules can't break it."""

    def test_two_terminals_no_milestone_id_yields_none_metadata(self):
        # Two terminal milestones, neither sharing a successor.
        # path_analysis / score_schedule would raise here; cpm_engine
        # swallows so transitive callers that don't care still work.
        tasks = [
            _task("1", "A1000", "Build foundation"),
            _task("2", "M_SC1", "Substantial Completion Phase 1", task_type="TT_FinMile"),
            _task("3", "M_SC2", "Substantial Completion Phase 2", task_type="TT_FinMile"),
        ]
        preds = [_pred("1", "2"), _pred("1", "3")]
        calendars = []

        # Should NOT raise. Returns metadata with None SC fields.
        results, meta = schedule_forward_backward(
            tasks, preds, calendars, "2026-01-01 08:00")

        # Multi-terminal -> SC swallowed to None (informational only).
        self.assertIsNone(meta["sc_milestone_id"])

    def test_two_terminals_with_explicit_milestone_id_resolves(self):
        # Same ambiguous schedule -- but caller pinned one explicitly.
        tasks = [
            _task("1", "A1000", "Build foundation"),
            _task("2", "M_SC1", "Substantial Completion Phase 1", task_type="TT_FinMile"),
            _task("3", "M_SC2", "Substantial Completion Phase 2", task_type="TT_FinMile"),
        ]
        preds = [_pred("1", "2"), _pred("1", "3")]
        calendars = []

        results, meta = schedule_forward_backward(
            tasks, preds, calendars, "2026-01-01 08:00",
            milestone_id="3")

        self.assertEqual(meta["sc_milestone_id"], "3")
        self.assertEqual(meta["sc_milestone_name"], "Substantial Completion Phase 2")


if __name__ == "__main__":
    unittest.main()
