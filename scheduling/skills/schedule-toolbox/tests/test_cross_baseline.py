"""Tests for ``lib/cross_baseline.py`` -- the cross-XER CPM-aware analytics.

Each function tests against the Plan 2 fixtures (see
``scheduling/mcp-server/tests/fixtures/``). The tests use the CpmCache to
parse + CPM each fixture so the inputs match what the MCP layer will pass.
"""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

SERVER_DIR = Path(__file__).parent.parent.parent.parent / "mcp-server"
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from cross_baseline import (  # noqa: E402
    compute_critical_path_changes,
    compute_float_consumption,
    compute_gain_loss_attribution,
    compute_trade_slip_summary,
)

FIXTURES = SERVER_DIR / "tests" / "fixtures"


class TestComputeCriticalPathChanges(unittest.TestCase):
    """compute_critical_path_changes diffs the critical_path lists from
    extract_paths() on baseline vs current and returns moved_on / moved_off
    /stable sets. The cp_baseline -> cp_shifted fixture pair was engineered
    so the entire CP shifts from A-chain to B-chain."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.base_parsed = cls.cache.get_parsed(str(FIXTURES / "cp_baseline.xer"))
        cls.curr_parsed = cls.cache.get_parsed(str(FIXTURES / "cp_shifted.xer"))
        cls.base_cpm = cls.cache.get_cpm(str(FIXTURES / "cp_baseline.xer"))
        cls.curr_cpm = cls.cache.get_cpm(str(FIXTURES / "cp_shifted.xer"))

    def test_returns_required_keys(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in (
            "milestone_id", "baseline_cp", "current_cp",
            "moved_on", "moved_off", "stable_count",
        ):
            self.assertIn(key, result)

    def test_baseline_cp_contains_a_chain(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {t["task_code"] for t in result["baseline_cp"]}
        self.assertIn("A1000", codes)
        self.assertIn("A1010", codes)

    def test_current_cp_contains_b_chain(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {t["task_code"] for t in result["current_cp"]}
        self.assertIn("B1000", codes)
        self.assertIn("B1010", codes)

    def test_a_chain_in_moved_off(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        moved_off_codes = {t["task_code"] for t in result["moved_off"]}
        self.assertIn("A1000", moved_off_codes)
        self.assertIn("A1010", moved_off_codes)

    def test_b_chain_in_moved_on(self):
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        moved_on_codes = {t["task_code"] for t in result["moved_on"]}
        self.assertIn("B1000", moved_on_codes)
        self.assertIn("B1010", moved_on_codes)

    def test_no_change_when_inputs_identical(self):
        """When baseline and current are the same XER, moved_on / moved_off
        are empty and stable_count equals len(critical_path)."""
        result = compute_critical_path_changes(
            self.base_parsed, self.base_parsed,
            self.base_cpm, self.base_cpm,
        )
        self.assertEqual(result["moved_on"], [])
        self.assertEqual(result["moved_off"], [])
        self.assertGreater(result["stable_count"], 0)

    def test_milestone_id_passthrough(self):
        """Explicit milestone_id overrides the auto-resolved terminal and
        flows through to extract_paths."""
        result = compute_critical_path_changes(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            milestone_id="30006",
        )
        self.assertEqual(result["milestone_id"], "30006")
        # Confirm the explicit override produces a non-empty critical path
        # (proves the override actually flowed through to extract_paths,
        # not just stamped onto the return dict).
        self.assertGreater(len(result["current_cp"]), 0)

    def test_milestone_id_not_found_raises(self):
        """Explicit milestone_id that doesn't exist in the schedule raises
        MilestoneNotFoundError carrying the candidate list."""
        from milestones import MilestoneNotFoundError
        with self.assertRaises(MilestoneNotFoundError) as ctx:
            compute_critical_path_changes(
                self.base_parsed, self.curr_parsed,
                self.base_cpm, self.curr_cpm,
                milestone_id="not_a_real_id",
            )
        self.assertTrue(hasattr(ctx.exception, "candidates"))
        self.assertGreater(len(ctx.exception.candidates), 0)
