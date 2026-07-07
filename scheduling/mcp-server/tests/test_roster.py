# scheduling/mcp-server/tests/test_roster.py
"""Integration tests for the activity-roster MCP tools.

Exercises the impls through the real ``CpmCache`` seam against fixtures:

* ``roster_sample.xer`` — a 3-level WBS with a Responsibility global activity
  code and linked tasks (NTP -> Order Steel -> Fab Steel -SS-> Pour Slab -> SC).
  Proves CPM date flow, WBS paths, pred/succ counts, trade filtering,
  adjacency, branch descendants, and next_free_activity_code.
* ``minimal.xer`` — no activity codes; proves the responsibility=None path.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import roster  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = str(FIXTURES / "roster_sample.xer")
MINIMAL = str(FIXTURES / "minimal.xer")


class TestListActivities(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def _list(self, **kw):
        kw.setdefault("wbs_filter", None)
        kw.setdefault("trade_filter", None)
        kw.setdefault("code_type", None)
        kw.setdefault("include_logic", True)
        return roster.list_activities_impl(SAMPLE, cache=self.cache, **kw)

    def test_returns_all_activities(self):
        res = self._list()
        self.assertEqual(res["activity_count"], 5)
        self.assertIsNotNone(res["data_date"])

    def test_cpm_dates_populated(self):
        by_code = {r["task_code"]: r for r in self._list()["activities"]}
        # CPM computes dates from durations; the fixture ships them blank.
        self.assertTrue(by_code["A-1000"]["early_start"])
        self.assertTrue(by_code["A-1000"]["early_finish"])

    def test_wbs_path_and_responsibility(self):
        by_code = {r["task_code"]: r for r in self._list()["activities"]}
        self.assertEqual(by_code["A-1000"]["wbs_path"],
                         "CVMC Nephi > Procurement > Steel")
        self.assertEqual(by_code["A-1000"]["responsibility"], "Steel Erection")
        self.assertEqual(by_code["A-2000"]["responsibility"], "Concrete")
        self.assertIsNone(by_code["M-9000"]["responsibility"])

    def test_pred_succ_counts(self):
        by_code = {r["task_code"]: r for r in self._list()["activities"]}
        self.assertEqual(by_code["M-1000"]["pred_count"], 0)
        self.assertEqual(by_code["M-1000"]["succ_count"], 1)
        self.assertEqual(by_code["M-9000"]["succ_count"], 0)

    def test_wbs_filter(self):
        codes = {r["task_code"] for r in self._list(wbs_filter="steel")["activities"]}
        self.assertEqual(codes, {"A-1000", "A-1010"})

    def test_trade_filter_end_to_end(self):
        codes = {r["task_code"] for r in self._list(trade_filter="concrete")["activities"]}
        self.assertEqual(codes, {"A-2000"})
        codes = {r["task_code"] for r in self._list(trade_filter="steel")["activities"]}
        self.assertEqual(codes, {"A-1000", "A-1010"})

    def test_include_logic_false(self):
        rows = self._list(include_logic=False)["activities"]
        self.assertNotIn("pred_count", rows[0])

    def test_minimal_no_activity_codes(self):
        res = roster.list_activities_impl(
            MINIMAL, wbs_filter=None, trade_filter=None, code_type=None,
            include_logic=True, cache=self.cache)
        self.assertTrue(all(r["responsibility"] is None for r in res["activities"]))


class TestGetActivity(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_expanded_logic(self):
        act = roster.get_activity_impl(SAMPLE, "A-1010", cache=self.cache)
        self.assertEqual(act["task_code"], "A-1010")
        self.assertEqual([p["task_code"] for p in act["predecessors"]], ["A-1000"])
        succ = act["successors"][0]
        self.assertEqual(succ["task_code"], "A-2000")
        self.assertEqual(succ["rel_type"], "SS")
        self.assertEqual(succ["lag_days"], 2.0)

    def test_not_found_raises_with_hint(self):
        with self.assertRaises(ValueError) as ctx:
            roster.get_activity_impl(SAMPLE, "A-9999", cache=self.cache)
        # difflib should surface the near-miss numeric codes.
        self.assertIn("A-", str(ctx.exception))


class TestGetWbsBranch(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_branch_with_descendants(self):
        br = roster.get_wbs_branch_impl(
            SAMPLE, "Procurement", include_descendants=True,
            include_logic=True, cache=self.cache)
        self.assertEqual({a["task_code"] for a in br["activities"]},
                         {"A-1000", "A-1010"})
        act = next(a for a in br["activities"] if a["task_code"] == "A-1010")
        self.assertIn("predecessors", act)

    def test_branch_without_descendants(self):
        br = roster.get_wbs_branch_impl(
            SAMPLE, "Procurement", include_descendants=False,
            include_logic=False, cache=self.cache)
        self.assertEqual(br["activities"], [])

    def test_not_found_raises(self):
        with self.assertRaises(ValueError):
            roster.get_wbs_branch_impl(
                SAMPLE, "Nonexistent WBS", include_descendants=True,
                include_logic=True, cache=self.cache)


class TestNextFreeActivityCode(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_next_a_series(self):
        res = roster.next_free_activity_code_impl(SAMPLE, "A-", step=10, cache=self.cache)
        self.assertEqual(res["max_existing_code"], "A-2000")
        self.assertEqual(res["next_code"], "A-2010")

    def test_next_m_series(self):
        res = roster.next_free_activity_code_impl(SAMPLE, "M-", step=10, cache=self.cache)
        self.assertEqual(res["next_code"], "M-9010")

    def test_no_match(self):
        res = roster.next_free_activity_code_impl(SAMPLE, "ZZ", step=10, cache=self.cache)
        self.assertEqual(res["matched_count"], 0)
        self.assertIsNone(res["next_code"])


if __name__ == "__main__":
    unittest.main()
