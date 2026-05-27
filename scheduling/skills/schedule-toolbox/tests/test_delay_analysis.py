"""Tests for ``lib/delay_analysis.py`` -- Tier 2 forensic calculations."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

SERVER_DIR = Path(__file__).parent.parent.parent.parent / "mcp-server"
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from delay_analysis import (  # noqa: E402
    compute_change_order_delay,
    compute_tia,
    compute_window_analysis,
    find_concurrent_delay_pairs,
)

FIXTURES = SERVER_DIR / "tests" / "fixtures"


class TestComputeTia(unittest.TestCase):
    """compute_tia inserts a delay fragnet, re-runs CPM, returns projected SC."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.path = str(FIXTURES / "tia_baseline.xer")
        cls.parsed = cls.cache.get_parsed(cls.path)
        cls.cpm = cls.cache.get_cpm(cls.path)

    def test_returns_required_keys(self):
        result = compute_tia(
            self.parsed, self.cpm,
            delay_fragment={
                "activity_id": "FRAGNET-1",
                "duration_days": 5,
                "description": "RFI-101 delay",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",  # A1000
            },
        )
        for key in (
            "milestone_id", "baseline_completion", "projected_completion",
            "net_delay_days", "critical_path_changed",
            "new_critical_activities", "removed_critical_activities",
            "affected_activities",
        ):
            self.assertIn(key, result)

    def test_5day_fragnet_pushes_sc_by_5_working_days(self):
        """A 5-working-day fragnet on the critical path should push SC by
        5 working days (= 7 calendar days under the standard 5-day cal)."""
        result = compute_tia(
            self.parsed, self.cpm,
            delay_fragment={
                "activity_id": "FRAGNET-1",
                "duration_days": 5,
                "description": "RFI-101 delay",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",
            },
        )
        # 5 working days = 7 calendar days under 5-day calendar.
        self.assertEqual(result["net_delay_days"], 7)

    def test_zero_day_fragnet_no_delay(self):
        result = compute_tia(
            self.parsed, self.cpm,
            delay_fragment={
                "activity_id": "FRAGNET-0",
                "duration_days": 0,
                "description": "no impact",
                "predecessor_relationship_type": "PR_FS",
                "predecessor_activity_id": "50002",
            },
        )
        self.assertEqual(result["net_delay_days"], 0)


class TestComputeWindowAnalysis(unittest.TestCase):
    """compute_window_analysis groups slip by named time windows."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.base_path = str(FIXTURES / "multi_driver_slip_baseline.xer")
        cls.curr_path = str(FIXTURES / "multi_driver_slip_current.xer")
        cls.base_parsed = cls.cache.get_parsed(cls.base_path)
        cls.curr_parsed = cls.cache.get_parsed(cls.curr_path)
        cls.base_cpm = cls.cache.get_cpm(cls.base_path)
        cls.curr_cpm = cls.cache.get_cpm(cls.curr_path)

    def test_single_window_returns_one_entry(self):
        windows = [{"start": "2026-05-25", "end": "2026-07-01",
                    "label": "May 25 - Jul 1"}]
        result = compute_window_analysis(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            windows=windows,
        )
        self.assertIn("windows", result)
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["label"], "May 25 - Jul 1")

    def test_window_activities_responsible_has_cause_category(self):
        windows = [{"start": "2026-05-25", "end": "2026-07-01",
                    "label": "test"}]
        result = compute_window_analysis(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            windows=windows,
        )
        for activity in result["windows"][0]["activities_responsible"]:
            self.assertIn("cause_category", activity)
            self.assertIn(activity["cause_category"], (
                "operational_slip", "logic_change", "duration_change",
                "calendar_change", "scope_change", "unknown",
            ))


class TestComputeChangeOrderDelay(unittest.TestCase):
    """compute_change_order_delay attributes slip to a change event
    vs other causes."""

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
        result = compute_change_order_delay(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            change_event_date="2026-06-01",
        )
        for key in (
            "milestone_id", "change_event_date", "total_slip_days",
            "attributable_to_change_event", "attributable_to_other_causes",
            "breakdown",
        ):
            self.assertIn(key, result)

    def test_owner_activities_bucketed_as_change_event(self):
        """When C1000 (task_id 40006) is in owner_activities, it lands
        in the change_event bucket in breakdown."""
        result = compute_change_order_delay(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            change_event_date="2026-06-01",
            owner_activities=["40006"],
        )
        c1000_row = next(
            (r for r in result["breakdown"] if r.get("task_code") == "C1000"),
            None,
        )
        self.assertIsNotNone(c1000_row)
        self.assertEqual(c1000_row["attribution"], "change_event")

    def test_breakdown_has_no_duplicate_task_codes(self):
        """Each activity should appear at most once in breakdown -- multi-cause
        activities are deduped via the priority order."""
        result = compute_change_order_delay(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
            change_event_date="2026-06-01",
        )
        codes = [row["task_code"] for row in result["breakdown"]]
        self.assertEqual(len(codes), len(set(codes)),
                         f"Duplicate task_codes in breakdown: {codes}")


class TestFindConcurrentDelayPairs(unittest.TestCase):
    """find_concurrent_delay_pairs surfaces simultaneously slipping
    activities without a logic relationship between them."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.base_path = str(FIXTURES / "concurrent_delay_baseline.xer")
        cls.curr_path = str(FIXTURES / "concurrent_delay_current.xer")
        cls.base_parsed = cls.cache.get_parsed(cls.base_path)
        cls.curr_parsed = cls.cache.get_parsed(cls.curr_path)
        cls.base_cpm = cls.cache.get_cpm(cls.base_path)
        cls.curr_cpm = cls.cache.get_cpm(cls.curr_path)

    def test_returns_required_keys(self):
        result = find_concurrent_delay_pairs(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        for key in ("milestone_id", "concurrent_pairs"):
            self.assertIn(key, result)

    def test_a1000_b1000_in_concurrent_pairs(self):
        """In concurrent_delay_current, A1000 and B1000 both have late
        act_start_dates, no logic relationship between them. They should
        appear as a concurrent pair (in either order)."""
        result = find_concurrent_delay_pairs(
            self.base_parsed, self.curr_parsed,
            self.base_cpm, self.curr_cpm,
        )
        pairs = result["concurrent_pairs"]
        self.assertGreater(len(pairs), 0)
        # Find any pair containing A1000 and B1000 (in any order)
        matched = False
        for p in pairs:
            codes = {p["activity_a"]["task_code"], p["activity_b"]["task_code"]}
            if "A1000" in codes and "B1000" in codes:
                matched = True
                break
        self.assertTrue(matched, f"Expected A1000+B1000 pair, got: {[(p['activity_a']['task_code'], p['activity_b']['task_code']) for p in pairs]}")


if __name__ == "__main__":
    unittest.main()
