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


if __name__ == "__main__":
    unittest.main()
