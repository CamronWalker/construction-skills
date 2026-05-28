# scheduling/mcp-server/tests/test_structure.py
"""Tests for the ``get_milestones`` MCP tool.

Uses the shared minimal.xer fixture (two milestones with one FS predecessor
linking them: NTP -> SC). The fixture is set up so that NTP has zero
predecessors and SC has one (NTP), and SC has no successors (terminal),
while NTP has SC as a successor (and SC is TT_FinMile, not WBS/LOE) so NTP
is *not* terminal.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import structure  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestGetMilestonesTool(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_milestone_list(self):
        """The minimal fixture has 2 incomplete milestones (NTP + SC)."""
        result = structure.get_milestones_impl(
            str(FIXTURE), include_complete=False, cache=self.cache
        )
        self.assertIn("milestones", result)
        self.assertEqual(len(result["milestones"]), 2)

    def test_each_milestone_has_required_fields(self):
        """Every row must include the base + enriched fields."""
        result = structure.get_milestones_impl(
            str(FIXTURE), include_complete=False, cache=self.cache
        )
        required = {
            "task_id", "task_name", "task_type", "calendar_id",
            "early_finish", "late_finish", "status_code",
            "predecessor_count", "is_terminal",
        }
        for m in result["milestones"]:
            self.assertTrue(
                required.issubset(m.keys()),
                f"Missing fields: {required - m.keys()} (got {m.keys()})",
            )

    def test_sc_milestone_is_terminal(self):
        """Substantial Completion has no successors -> is_terminal=True."""
        result = structure.get_milestones_impl(
            str(FIXTURE), include_complete=False, cache=self.cache
        )
        sc = next(
            m for m in result["milestones"]
            if m["task_name"] == "Substantial Completion"
        )
        self.assertTrue(sc["is_terminal"])
        # And SC has exactly one predecessor (NTP).
        self.assertEqual(sc["predecessor_count"], 1)

    def test_ntp_has_predecessor_count_zero(self):
        """Notice to Proceed has no predecessors -> predecessor_count=0.
        It is also *not* terminal because SC (TT_FinMile, not WBS/LOE)
        is a successor."""
        result = structure.get_milestones_impl(
            str(FIXTURE), include_complete=False, cache=self.cache
        )
        ntp = next(
            m for m in result["milestones"]
            if "NTP" in m["task_name"] or "Notice" in m["task_name"]
        )
        self.assertEqual(ntp["predecessor_count"], 0)
        self.assertFalse(ntp["is_terminal"])


class TestInvalidateCacheFor(unittest.TestCase):
    def test_invalidates_an_entry(self):
        from cache import CpmCache
        from tools.structure import invalidate_cache_for_impl

        cache = CpmCache()
        fixture = str(Path(__file__).parent / "fixtures" / "minimal.xer")
        cache.get_parsed(fixture)
        result = invalidate_cache_for_impl(fixture, cache)
        self.assertEqual(result, {"invalidated": True})
        self.assertNotIn(fixture, cache._entries)

    def test_returns_false_when_nothing_to_invalidate(self):
        from cache import CpmCache
        from tools.structure import invalidate_cache_for_impl

        cache = CpmCache()
        fixture = str(Path(__file__).parent / "fixtures" / "minimal.xer")
        result = invalidate_cache_for_impl(fixture, cache)
        self.assertEqual(result, {"invalidated": False})


if __name__ == "__main__":
    unittest.main()
