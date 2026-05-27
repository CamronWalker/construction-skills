"""Tests for xer_compare's explicit milestone_id contract.

D4 removed the brittle name-based ``_find_sc_milestone`` heuristic from
``xer_compare`` and replaced it with an explicit ``milestone_id`` parameter
on ``compare_xer_pair`` and ``compare_schedules`` plus structural
auto-resolution via ``milestones.resolve_default_milestone``. The F4 MCP
tool batch will surface ``milestone_id`` as a first-class parameter.
"""
import unittest
import copy
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_compare import compare_schedules, compare_xer_pair
from milestones import MilestoneAmbiguousError
from quality_checks import _parse_xer

FIXTURE = Path(__file__).parent.parent.parent.parent / "mcp-server" / "tests" / "fixtures" / "minimal.xer"


def _tables_two_terminals():
    """Synthetic two-terminal schedule for ambiguity tests."""
    return {
        "PROJECT": [{"data_date": "2026-01-01 08:00", "last_recalc_date": "2026-01-01 08:00"}],
        "TASK": [
            {"task_id": "1", "task_code": "A1000", "task_name": "Build",
             "task_type": "TT_Task", "status_code": "TK_NotStart",
             "wbs_id": "", "target_drtn_hr_cnt": "8",
             "early_start_date": "2026-01-02 08:00",
             "early_end_date": "2026-01-03 08:00"},
            {"task_id": "2", "task_code": "M_SC1",
             "task_name": "Substantial Completion Phase 1",
             "task_type": "TT_FinMile", "status_code": "TK_NotStart",
             "wbs_id": "", "target_drtn_hr_cnt": "0",
             "early_start_date": "2026-02-01 08:00",
             "early_end_date": "2026-02-01 08:00"},
            {"task_id": "3", "task_code": "M_SC2",
             "task_name": "Substantial Completion Phase 2",
             "task_type": "TT_FinMile", "status_code": "TK_NotStart",
             "wbs_id": "", "target_drtn_hr_cnt": "0",
             "early_start_date": "2026-03-01 08:00",
             "early_end_date": "2026-03-01 08:00"},
        ],
        "TASKPRED": [
            {"pred_task_id": "1", "task_id": "2", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
            {"pred_task_id": "1", "task_id": "3", "pred_type": "PR_FS", "lag_hr_cnt": "0"},
        ],
        "PROJWBS": [],
    }


class TestExplicitMilestoneId(unittest.TestCase):
    """Caller-provided milestone_id pins SC slip output."""

    def test_explicit_milestone_id_pins_summary(self):
        parsed = _parse_xer(str(FIXTURE))
        # Self-compare with NTP as the pinned terminal.
        result = compare_schedules(parsed, baseline_tables=parsed,
                                    milestone_id="10001")
        self.assertEqual(result["summary"]["sc_task_code"], "M1000")
        self.assertEqual(result["summary"]["sc_task_name"], "Notice to Proceed")

    def test_compare_xer_pair_honors_milestone_id(self):
        parsed = _parse_xer(str(FIXTURE))
        # Pin to NTP via compare_xer_pair directly.
        result = compare_xer_pair(parsed, parsed, milestone_id="10001")
        # When old and new resolve to the same milestone, slip is 0.
        self.assertEqual(result["sc_slip_days"], 0)
        # Check the SC info_new reflects NTP.
        self.assertEqual(result["sc_info_new"]["task_name"], "Notice to Proceed")


class TestAmbiguousMilestoneRaises(unittest.TestCase):
    """Two-terminal schedule with no milestone_id raises on resolution."""

    def test_ambiguous_compare_schedules_raises(self):
        tables = _tables_two_terminals()
        # Auto-resolve picks the unique terminal; with two terminals the
        # resolver raises so the F4 MCP tool can surface a structured prompt.
        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            compare_schedules(tables, baseline_tables=tables)

        candidate_ids = {c["task_id"] for c in ctx.exception.candidates}
        self.assertEqual(candidate_ids, {"2", "3"})

    def test_ambiguous_resolves_with_explicit_id(self):
        tables = _tables_two_terminals()
        # Same ambiguous schedule, but caller pinned the terminal explicitly.
        result = compare_schedules(
            copy.deepcopy(tables), baseline_tables=copy.deepcopy(tables),
            milestone_id="3")
        self.assertEqual(result["summary"]["sc_task_code"], "M_SC2")
        self.assertEqual(result["summary"]["sc_task_name"],
                          "Substantial Completion Phase 2")


class TestUnambiguousAutoResolves(unittest.TestCase):
    """Single-terminal schedule auto-resolves silently."""

    def test_auto_picks_sc(self):
        parsed = _parse_xer(str(FIXTURE))
        result = compare_schedules(parsed, baseline_tables=parsed)
        # Minimal fixture's terminal is "Substantial Completion" (id 10002).
        self.assertEqual(result["summary"]["sc_task_code"], "M2000")
        self.assertEqual(result["summary"]["sc_task_name"], "Substantial Completion")


if __name__ == "__main__":
    unittest.main()
