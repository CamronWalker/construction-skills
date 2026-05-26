# scheduling/mcp-server/tests/test_cpm_path.py
"""Tests for the CPM-and-path-analysis MCP tools (F1 batch).

All tools in this module wrap functions from schedule-toolbox/lib/cpm_engine.py
or schedule-toolbox/lib/path_analysis.py. Tests use the shared minimal.xer
fixture (NTP -> SC, single FS predecessor link) so the expected critical path
is unambiguous: SC is the unique terminal milestone, both activities have
TF=0, so the critical chain is [NTP, SC].
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import cpm_path  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestGetCriticalPath(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_critical_path_key(self):
        """Top-level dict has a ``critical_path`` key with a list value."""
        result = cpm_path.get_critical_path_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        self.assertIn("critical_path", result)
        self.assertIsInstance(result["critical_path"], list)

    def test_critical_path_contains_sc_milestone(self):
        """On the minimal fixture, SC sits on the critical chain (TF=0).
        ``_path_task_summary`` emits the task name under the ``name`` key."""
        result = cpm_path.get_critical_path_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        names = {step.get("name") for step in result["critical_path"]}
        self.assertIn("Substantial Completion", names)

    def test_critical_path_with_explicit_milestone_id(self):
        """Passing the SC task_id explicitly produces the same critical chain
        as auto-resolution on the minimal fixture (single terminal). SC's
        task_id in this fixture is ``"10002"``."""
        auto = cpm_path.get_critical_path_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        explicit = cpm_path.get_critical_path_impl(
            str(FIXTURE), milestone_id="10002", cache=self.cache
        )
        self.assertEqual(
            [s.get("task_id") for s in auto["critical_path"]],
            [s.get("task_id") for s in explicit["critical_path"]],
        )

    def test_xer_not_found_raises(self):
        """Missing file -> the underlying os.stat raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            cpm_path.get_critical_path_impl(
                "/definitely/not/a/file.xer", milestone_id=None, cache=self.cache
            )

    def test_each_step_has_task_summary_fields(self):
        """Each critical-path step should include task_id, task_code,
        task_name, total_float_hr_cnt, and early_end_date so callers can
        render a usable summary without going back to the XER."""
        result = cpm_path.get_critical_path_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        self.assertGreater(len(result["critical_path"]), 0)
        for step in result["critical_path"]:
            self.assertIn("task_id", step)
            self.assertIn("name", step)
            self.assertIn("early_start", step)
            self.assertIn("early_end", step)
            self.assertIn("total_float_days", step)


class TestGetDrivingPaths(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_driving_paths_key(self):
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id=None, cache=self.cache
        )
        self.assertIn("driving_paths", result)
        self.assertIsInstance(result["driving_paths"], list)

    def test_no_activity_returns_end_state_paths(self):
        """Without activity_id, the tool exposes extract_paths['driving_paths']
        -- paths walked back from end-states. The minimal fixture has at
        least one (SC milestone is a terminal)."""
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id=None, cache=self.cache
        )
        self.assertGreater(len(result["driving_paths"]), 0)

    def test_with_activity_id_returns_single_forward_chain(self):
        """activity_id='10001' (NTP) traces forward to SC; result is a single-
        element list whose chain ends at the SC task_id."""
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id="10001", cache=self.cache
        )
        self.assertEqual(len(result["driving_paths"]), 1)
        chain = result["driving_paths"][0]["chain"]
        self.assertEqual(chain[0]["task_id"], "10001")
        self.assertEqual(chain[-1]["task_id"], "10002")

    def test_each_path_has_chain_and_end_metadata(self):
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id=None, cache=self.cache
        )
        for p in result["driving_paths"]:
            self.assertIn("chain", p)
            self.assertIn("end_task_id", p)
            self.assertIsInstance(p["chain"], list)


class TestGetNearCriticalChains(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_near_critical_key(self):
        result = cpm_path.get_near_critical_chains_impl(
            str(FIXTURE), tolerance_days=5, cache=self.cache
        )
        self.assertIn("near_critical", result)
        self.assertIsInstance(result["near_critical"], list)

    def test_empty_on_minimal_fixture(self):
        """Both fixture activities have TF=0 -> no near-critical chains."""
        result = cpm_path.get_near_critical_chains_impl(
            str(FIXTURE), tolerance_days=5, cache=self.cache
        )
        self.assertEqual(result["near_critical"], [])

    def test_tolerance_days_param_accepted(self):
        """Passing a smaller tolerance must not error; result is still empty
        on this fixture but the call shape is what's being verified."""
        result = cpm_path.get_near_critical_chains_impl(
            str(FIXTURE), tolerance_days=2, cache=self.cache
        )
        self.assertIn("near_critical", result)


if __name__ == "__main__":
    unittest.main()
