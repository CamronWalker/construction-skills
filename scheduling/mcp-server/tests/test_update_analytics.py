# scheduling/mcp-server/tests/test_update_analytics.py
"""Tests for the Tier 1 update-analytics MCP tools (D1+D2 batch).

All four tools are thin adapters around ``schedule-toolbox/lib/
cross_baseline.py`` functions. The tests assert that:

1. Each ``_impl`` returns the expected top-level keys (cache-driven path
   parses + CPMs both XERs and forwards to the lib correctly).
2. Each ``_impl`` returns nonempty data against the fixture pair the
   lib-level tests use, so we know the wrapper actually reaches the lib
   and isn't silently returning empty dicts.

Fixture pairs:
* ``cp_baseline.xer`` / ``cp_shifted.xer`` -- engineered so the entire
  critical path shifts from the A-chain to the B-chain. Used for
  ``get_critical_path_changes`` and ``get_float_consumption``.
* ``multi_driver_slip_baseline.xer`` / ``multi_driver_slip_current.xer``
  -- three independent chains with distinct slip drivers
  (duration_change, logic_change, operational_slip). Used for
  ``get_trade_slip_summary`` and ``get_gain_loss_attribution``.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import update_analytics  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class TestGetCriticalPathChangesImpl(unittest.TestCase):
    """``get_critical_path_changes`` wraps ``compute_critical_path_changes``.
    The cp_baseline -> cp_shifted pair moves the entire CP from the
    A-chain to the B-chain, so moved_off carries A1000/A1010 and
    moved_on carries B1000/B1010."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "cp_baseline.xer")
        cls.current = str(FIXTURES / "cp_shifted.xer")

    def test_returns_required_keys(self):
        result = update_analytics.get_critical_path_changes_impl(
            self.baseline, self.current, milestone_id=None, cache=self.cache,
        )
        for key in (
            "milestone_id", "baseline_cp", "current_cp",
            "moved_on", "moved_off", "stable_count",
        ):
            self.assertIn(key, result)

    def test_returns_cp_shift(self):
        result = update_analytics.get_critical_path_changes_impl(
            self.baseline, self.current, milestone_id=None, cache=self.cache,
        )
        moved_off_codes = {t["task_code"] for t in result["moved_off"]}
        moved_on_codes = {t["task_code"] for t in result["moved_on"]}
        # cp_baseline -> cp_shifted moves A-chain off and B-chain on.
        self.assertTrue(moved_off_codes & {"A1000", "A1010"})
        self.assertTrue(moved_on_codes & {"B1000", "B1010"})


class TestGetFloatConsumptionImpl(unittest.TestCase):
    """``get_float_consumption`` wraps ``compute_float_consumption``. The
    cp_baseline -> cp_shifted pair drains B-chain float to zero (now CP)
    and adds float to A-chain (no longer driving), so B activities show
    up as biggest_losers and A activities as biggest_gainers."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "cp_baseline.xer")
        cls.current = str(FIXTURES / "cp_shifted.xer")

    def test_returns_required_keys(self):
        result = update_analytics.get_float_consumption_impl(
            self.baseline, self.current, milestone_id=None, cache=self.cache,
        )
        for key in (
            "milestone_id", "by_activity",
            "biggest_losers", "biggest_gainers",
        ):
            self.assertIn(key, result)

    def test_b_chain_lost_float_a_chain_gained(self):
        result = update_analytics.get_float_consumption_impl(
            self.baseline, self.current, milestone_id=None, cache=self.cache,
        )
        loser_codes = {row["task_code"] for row in result["biggest_losers"]}
        gainer_codes = {row["task_code"] for row in result["biggest_gainers"]}
        # B-chain drained from 80hr float to 0hr (became CP).
        self.assertTrue(loser_codes & {"B1000", "B1010"})
        # A-chain went from 0hr float to >0hr (off CP).
        self.assertTrue(gainer_codes & {"A1000", "A1010"})


class TestGetTradeSlipSummaryImpl(unittest.TestCase):
    """``get_trade_slip_summary`` wraps ``compute_trade_slip_summary``.
    The multi_driver_slip pair has three independent chains with A/B/C
    task_code prefixes, each contributing to overall slip. With no
    ``trade_field`` provided, the lib's task_code-prefix fallback
    surfaces three trades."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.current = str(FIXTURES / "multi_driver_slip_current.xer")

    def test_returns_required_keys(self):
        result = update_analytics.get_trade_slip_summary_impl(
            self.baseline, self.current,
            milestone_id=None, trade_field=None, cache=self.cache,
        )
        for key in ("milestone_id", "by_trade"):
            self.assertIn(key, result)

    def test_three_trades_surface(self):
        result = update_analytics.get_trade_slip_summary_impl(
            self.baseline, self.current,
            milestone_id=None, trade_field=None, cache=self.cache,
        )
        trades = {row["trade"] for row in result["by_trade"]}
        # A, B, C prefixes each slip.
        self.assertIn("A", trades)
        self.assertIn("B", trades)
        self.assertIn("C", trades)

    def test_trade_field_passthrough(self):
        """When ``trade_field`` names a field absent from TASK rows,
        every activity collapses to ``"UNKNOWN"`` -- proves the kwarg
        actually flows through to the lib (not silently dropped)."""
        result = update_analytics.get_trade_slip_summary_impl(
            self.baseline, self.current,
            milestone_id=None, trade_field="nonexistent_field",
            cache=self.cache,
        )
        trades = {row["trade"] for row in result["by_trade"]}
        self.assertEqual(trades, {"UNKNOWN"})


class TestGetGainLossAttributionImpl(unittest.TestCase):
    """``get_gain_loss_attribution`` wraps
    ``compute_gain_loss_attribution``. The multi_driver_slip pair was
    engineered to surface one contributor per scheduler-initiated
    category (A1000 duration_change, B1010 logic_change) plus an
    operational driver (C1000)."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.current = str(FIXTURES / "multi_driver_slip_current.xer")

    def test_returns_required_top_level_keys(self):
        result = update_analytics.get_gain_loss_attribution_impl(
            self.baseline, self.current, milestone_id=None, cache=self.cache,
        )
        for key in (
            "milestone_id", "baseline_completion", "current_completion",
            "net_slip_days", "residual_days", "summary",
            "contributors_by_category", "weekly_email_documentation",
        ):
            self.assertIn(key, result)

    def test_net_slip_positive_and_categories_populated(self):
        result = update_analytics.get_gain_loss_attribution_impl(
            self.baseline, self.current, milestone_id=None, cache=self.cache,
        )
        self.assertGreater(result["net_slip_days"], 0)
        self.assertEqual(result["summary"], "changed")
        buckets = result["contributors_by_category"]
        # All five categories present (some may be empty lists).
        for category in (
            "operational_slip", "logic_change", "duration_change",
            "calendar_change", "scope_change",
        ):
            self.assertIn(category, buckets)


if __name__ == "__main__":
    unittest.main()
