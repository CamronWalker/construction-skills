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


if __name__ == "__main__":
    unittest.main()
