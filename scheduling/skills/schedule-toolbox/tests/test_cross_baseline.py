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


class TestComputeFloatConsumption(unittest.TestCase):
    """compute_float_consumption returns per-activity total_float deltas.
    A negative delta means float was consumed (slip risk increased);
    positive means float was added back (schedule healthier)."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.base_path = str(FIXTURES / "cp_baseline.xer")
        cls.curr_path = str(FIXTURES / "cp_shifted.xer")
        cls.base_parsed = cls.cache.get_parsed(cls.base_path)
        cls.curr_parsed = cls.cache.get_parsed(cls.curr_path)
        cls.base_cpm = cls.cache.get_cpm(cls.base_path)
        cls.curr_cpm = cls.cache.get_cpm(cls.curr_path)

    def test_returns_required_keys(self):
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in (
            "milestone_id", "by_activity", "biggest_losers", "biggest_gainers",
        ):
            self.assertIn(key, result)

    def test_by_activity_is_sorted_by_abs_delta_desc(self):
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        deltas = [abs(row["delta_hours"]) for row in result["by_activity"]]
        self.assertEqual(deltas, sorted(deltas, reverse=True))

    def test_b_chain_lost_float(self):
        """B-chain went from 80hr float to 0hr float in cp_shifted (now CP).
        B1000 and B1010 should show up in biggest_losers with negative
        delta_hours of magnitude ~80."""
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        loser_codes = {row["task_code"] for row in result["biggest_losers"]}
        self.assertIn("B1000", loser_codes)
        self.assertIn("B1010", loser_codes)

    def test_a_chain_gained_float(self):
        """A-chain went from 0hr float to >0hr float (still finishes but
        no longer drives). A1000 and A1010 in biggest_gainers."""
        result = compute_float_consumption(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        gainer_codes = {row["task_code"] for row in result["biggest_gainers"]}
        self.assertIn("A1000", gainer_codes)
        self.assertIn("A1010", gainer_codes)


class TestComputeTradeSlipSummary(unittest.TestCase):
    """compute_trade_slip_summary groups date_slippage rows by trade and
    returns per-trade totals. The multi_driver_slip fixture pair has three
    chains, each with a different task_code prefix (A, B, C), used as the
    fallback trade key."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.base_path = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.curr_path = str(FIXTURES / "multi_driver_slip_current.xer")
        cls.base_parsed = cls.cache.get_parsed(cls.base_path)
        cls.curr_parsed = cls.cache.get_parsed(cls.curr_path)
        cls.base_cpm = cls.cache.get_cpm(cls.base_path)
        cls.curr_cpm = cls.cache.get_cpm(cls.curr_path)

    def test_returns_required_keys(self):
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in ("milestone_id", "by_trade"):
            self.assertIn(key, result)

    def test_by_trade_sorted_by_abs_total_slip(self):
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        slips = [abs(row["total_slip_days"]) for row in result["by_trade"]]
        self.assertEqual(slips, sorted(slips, reverse=True))

    def test_three_trades_surface(self):
        """A, B, C task_code prefixes should each appear as a trade with
        nonzero total_slip_days."""
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        trades = {row["trade"] for row in result["by_trade"]}
        self.assertIn("A", trades)
        self.assertIn("B", trades)
        self.assertIn("C", trades)

    def test_explicit_trade_field_used_when_provided(self):
        """If trade_field is provided and the field doesn't exist on tasks,
        every activity falls into UNKNOWN."""
        result = compute_trade_slip_summary(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            trade_field="nonexistent_field",
        )
        trades = {row["trade"] for row in result["by_trade"]}
        self.assertEqual(trades, {"UNKNOWN"})


class TestComputeGainLossAttribution(unittest.TestCase):
    """compute_gain_loss_attribution categorizes SC slip contributors by
    cause. The multi_driver_slip fixture pair has three distinct causes
    (one duration_change on A1000, one logic_change on B1010, one
    operational_slip on C1000) plus operational propagation downstream."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.base_path = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.curr_path = str(FIXTURES / "multi_driver_slip_current.xer")
        cls.base_parsed = cls.cache.get_parsed(cls.base_path)
        cls.curr_parsed = cls.cache.get_parsed(cls.curr_path)
        cls.base_cpm = cls.cache.get_cpm(cls.base_path)
        cls.curr_cpm = cls.cache.get_cpm(cls.curr_path)

    def test_returns_required_top_level_keys(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in (
            "milestone_id", "baseline_completion", "current_completion",
            "net_slip_days", "residual_days", "summary",
            "contributors_by_category", "weekly_email_documentation",
        ):
            self.assertIn(key, result)

    def test_category_buckets_all_present(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        buckets = result["contributors_by_category"]
        for category in (
            "operational_slip", "logic_change", "duration_change",
            "calendar_change", "scope_change",
        ):
            self.assertIn(category, buckets)
            self.assertIsInstance(buckets[category], list)

    def test_net_slip_days_positive(self):
        """multi_driver_slip pair: SC moves from 2026-06-22 to
        2026-06-29 (5 working days = 7 calendar days)."""
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        self.assertGreater(result["net_slip_days"], 0)
        self.assertEqual(result["summary"], "changed")

    def test_duration_change_bucket_has_a1000(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {
            row["task_code"]
            for row in result["contributors_by_category"]["duration_change"]
        }
        self.assertIn("A1000", codes)

    def test_logic_change_bucket_has_b1010(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {
            row["task_code"]
            for row in result["contributors_by_category"]["logic_change"]
        }
        self.assertIn("B1010", codes)

    def test_operational_slip_bucket_has_c1000(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        codes = {
            row["task_code"]
            for row in result["contributors_by_category"]["operational_slip"]
        }
        self.assertIn("C1000", codes)

    def test_no_change_short_circuit(self):
        """When baseline and current are the same XER, summary is no_change."""
        result = compute_gain_loss_attribution(
            self.base_parsed, self.base_parsed,
            self.base_cpm, self.base_cpm,
        )
        self.assertEqual(result["summary"], "no_change")
        self.assertEqual(result["net_slip_days"], 0)

    def test_needs_narrative_includes_scheduler_initiated(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        narrative = result["weekly_email_documentation"]["needs_narrative"]
        narrative_codes = {row["task_code"] for row in narrative}
        # All three scheduler-initiated drivers should appear:
        self.assertIn("A1000", narrative_codes)  # duration_change
        self.assertIn("B1010", narrative_codes)  # logic_change
        # C1000 is operational, should NOT be in needs_narrative.
        self.assertNotIn("C1000", narrative_codes)

    def test_summary_paragraph_seed_is_nonempty_string(self):
        result = compute_gain_loss_attribution(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        seed = result["weekly_email_documentation"]["summary_paragraph_seed"]
        self.assertIsInstance(seed, str)
        self.assertGreater(len(seed), 0)
