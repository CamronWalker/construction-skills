# scheduling/mcp-server/tests/test_delay_analysis.py
"""Tests for the Tier 2 forensic-delay-analysis MCP tools (G1+G2 batch).

All four tools are thin adapters around ``schedule-toolbox/lib/
delay_analysis.py`` functions. The tests assert that:

1. Each ``_impl`` returns the expected top-level keys (cache-driven path
   parses + CPMs the XER input(s) and forwards to the lib correctly).
2. Each ``_impl`` returns the expected behaviour against the same
   fixtures used by the lib-level tests, so we know the wrapper actually
   reaches the lib and the kwargs flow through.

Fixtures (shared with ``schedule-toolbox/tests/test_delay_analysis.py``):

* ``tia_baseline.xer`` -- single-chain baseline for fragnet insertion.
* ``multi_driver_slip_{baseline,current}.xer`` -- three independent
  chains with distinct slip drivers; used for window analysis and
  change-order delay.
* ``concurrent_delay_{baseline,current}.xer`` -- A1000 and B1000 both
  slip simultaneously with no logic relationship between them.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import delay_analysis  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


class TestComputeTiaImpl(unittest.TestCase):
    """``compute_tia`` wraps the lib's :func:`compute_tia`. The
    tia_baseline fixture is a single chain ending at A1000 (task_id
    50002); a 5-working-day fragnet inserted in front pushes SC by 5
    working days = 7 calendar days under the standard 5-day cal."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.path = str(FIXTURES / "tia_baseline.xer")

    def test_returns_required_keys(self):
        result = delay_analysis.compute_tia_impl(
            self.path,
            delay_fragment={
                "activity_id": "FRAGNET-1",
                "duration_days": 5,
                "description": "RFI-101 delay",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",
            },
            milestone_id=None,
            cache=self.cache,
        )
        for key in (
            "milestone_id", "baseline_completion", "projected_completion",
            "net_delay_days", "critical_path_changed",
            "new_critical_activities", "removed_critical_activities",
            "affected_activities",
        ):
            self.assertIn(key, result)

    def test_5day_fragnet_pushes_sc_by_5_working_days(self):
        """5 working days on the CP -> 7 calendar days slip under the
        standard 5-day calendar."""
        result = delay_analysis.compute_tia_impl(
            self.path,
            delay_fragment={
                "activity_id": "FRAGNET-1",
                "duration_days": 5,
                "description": "RFI-101 delay",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",
            },
            milestone_id=None,
            cache=self.cache,
        )
        self.assertEqual(result["net_delay_days"], 7)


class TestComputeWindowAnalysisImpl(unittest.TestCase):
    """``compute_window_analysis`` wraps the lib's
    :func:`compute_window_analysis`. The multi_driver_slip pair has
    three slip drivers all finishing in mid-2026, so one wide window
    captures the contributors."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.current = str(FIXTURES / "multi_driver_slip_current.xer")

    def test_returns_required_keys(self):
        windows = [{"start": "2026-05-25", "end": "2026-07-01",
                    "label": "test window"}]
        result = delay_analysis.compute_window_analysis_impl(
            self.baseline, self.current,
            windows=windows, milestone_id=None, cache=self.cache,
        )
        for key in ("milestone_id", "windows"):
            self.assertIn(key, result)
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["label"], "test window")

    def test_window_activities_carry_cause_category(self):
        """The wrapper must pass ``windows`` through verbatim, and every
        activity surfaced inside a window must carry one of the known
        cause-category labels."""
        windows = [{"start": "2026-05-25", "end": "2026-07-01",
                    "label": "test"}]
        result = delay_analysis.compute_window_analysis_impl(
            self.baseline, self.current,
            windows=windows, milestone_id=None, cache=self.cache,
        )
        for activity in result["windows"][0]["activities_responsible"]:
            self.assertIn("cause_category", activity)
            self.assertIn(activity["cause_category"], (
                "operational_slip", "logic_change", "duration_change",
                "calendar_change", "scope_change", "unknown",
            ))


class TestComputeChangeOrderDelayImpl(unittest.TestCase):
    """``compute_change_order_delay`` wraps the lib's
    :func:`compute_change_order_delay`. The multi_driver_slip pair has
    C1000 (task_id 40006) as a slip driver; passing it via
    ``owner_activities`` buckets it as ``change_event``."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.current = str(FIXTURES / "multi_driver_slip_current.xer")

    def test_returns_required_keys(self):
        result = delay_analysis.compute_change_order_delay_impl(
            self.baseline, self.current,
            change_event_date="2026-06-01",
            owner_activities=None, milestone_id=None, cache=self.cache,
        )
        for key in (
            "milestone_id", "change_event_date", "total_slip_days",
            "attributable_to_change_event", "attributable_to_other_causes",
            "breakdown",
        ):
            self.assertIn(key, result)

    def test_owner_activities_bucketed_as_change_event(self):
        """When task_id 40006 (C1000) is passed in ``owner_activities``,
        the C1000 breakdown row gets attribution = ``"change_event"``."""
        result = delay_analysis.compute_change_order_delay_impl(
            self.baseline, self.current,
            change_event_date="2026-06-01",
            owner_activities=["40006"], milestone_id=None, cache=self.cache,
        )
        c1000_row = next(
            (r for r in result["breakdown"] if r.get("task_code") == "C1000"),
            None,
        )
        self.assertIsNotNone(c1000_row)
        self.assertEqual(c1000_row["attribution"], "change_event")


class TestGetConcurrentDelayPairsImpl(unittest.TestCase):
    """``get_concurrent_delay_pairs`` wraps the lib's
    :func:`find_concurrent_delay_pairs`. Note the rename -- the MCP tool
    uses ``get_*`` to match the verb convention of the other read-only
    tools, but the lib function keeps the original ``find_*`` name. The
    concurrent_delay pair surfaces A1000+B1000 (no logic relationship,
    overlapping baseline windows)."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.baseline = str(FIXTURES / "concurrent_delay_baseline.xer")
        cls.current = str(FIXTURES / "concurrent_delay_current.xer")

    def test_returns_required_keys(self):
        result = delay_analysis.get_concurrent_delay_pairs_impl(
            self.baseline, self.current,
            milestone_id=None, cache=self.cache,
        )
        for key in ("milestone_id", "concurrent_pairs"):
            self.assertIn(key, result)

    def test_a1000_b1000_in_concurrent_pairs(self):
        """A1000 and B1000 both slip simultaneously with no logic
        relationship between them -- the canonical concurrent pair."""
        result = delay_analysis.get_concurrent_delay_pairs_impl(
            self.baseline, self.current,
            milestone_id=None, cache=self.cache,
        )
        pairs = result["concurrent_pairs"]
        self.assertGreater(len(pairs), 0)
        matched = False
        for p in pairs:
            codes = {p["activity_a"]["task_code"], p["activity_b"]["task_code"]}
            if "A1000" in codes and "B1000" in codes:
                matched = True
                break
        self.assertTrue(
            matched,
            "Expected A1000+B1000 concurrent pair, got: " + str(
                [(p["activity_a"]["task_code"], p["activity_b"]["task_code"])
                 for p in pairs]
            ),
        )


if __name__ == "__main__":
    unittest.main()
