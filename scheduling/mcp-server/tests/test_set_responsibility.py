# scheduling/mcp-server/tests/test_set_responsibility.py
"""Tests for the set_responsibility change type of apply_xer_changes.

Writes the ACTVTYPE -> ACTVCODE -> TASKACTV chain. Uses roster_sample.xer
(has the framework + some existing assignments) and minimal.xer (no activity
codes at all) for the guard path.
"""
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools.xer_modify import apply_xer_changes_impl  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = str(FIXTURES / "roster_sample.xer")
MINIMAL = str(FIXTURES / "minimal.xer")


def _taskactv_for(parsed, task_code):
    tid = next(t["task_id"] for t in parsed["TASK"] if t.get("task_code") == task_code)
    return [a for a in parsed.get("TASKACTV", []) if a.get("task_id") == tid]


def _code_short(parsed, actv_code_id):
    for c in parsed.get("ACTVCODE", []):
        if c.get("actv_code_id") == actv_code_id:
            return c.get("short_name")
    return None


class TestSetResponsibility(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()
        self.tmp = tempfile.mkdtemp()

    def test_assign_new_code_and_replace_existing(self):
        out_path = str(Path(self.tmp) / "sample-coded.xer")
        changes = [
            # M-1000 (unassigned milestone) -> WEST (a code value not yet in the file)
            {"type": "set_responsibility", "activity_id": "M-1000",
             "code": "WEST", "name": "Westland Construction"},
            # A-1000 already carries STL (Steel Erection) -> replace with OWNER
            {"type": "set_responsibility", "activity_id": "A-1000",
             "code": "OWNER", "name": "Owner"},
        ]
        res = apply_xer_changes_impl(SAMPLE, changes, output_path=out_path, cache=self.cache)
        self.assertEqual(res["summary"]["validation_errors"], [], res["summary"])
        self.assertEqual(res["output_path"], out_path)
        self.assertEqual(res["summary"]["changes_applied"], 2)

        parsed = CpmCache().get_parsed(out_path)
        # M-1000 now has exactly one Responsibility assignment -> WEST
        m_rows = _taskactv_for(parsed, "M-1000")
        self.assertEqual(len(m_rows), 1)
        self.assertEqual(_code_short(parsed, m_rows[0]["actv_code_id"]), "WEST")
        # A-1000 replaced STL -> OWNER (still exactly one assignment)
        a_rows = _taskactv_for(parsed, "A-1000")
        self.assertEqual(len(a_rows), 1)
        self.assertEqual(_code_short(parsed, a_rows[0]["actv_code_id"]), "OWNER")
        # The new code values were created under the existing global type
        shorts = {c.get("short_name") for c in parsed["ACTVCODE"]}
        self.assertIn("WEST", shorts)
        self.assertIn("OWNER", shorts)

    def test_per_change_feedback(self):
        out_path = str(Path(self.tmp) / "sample-coded2.xer")
        changes = [{"type": "set_responsibility", "activity_id": "A-1000",
                    "code": "OWNER", "name": "Owner"}]
        res = apply_xer_changes_impl(SAMPLE, changes, output_path=out_path, cache=self.cache)
        fb = res["per_change_feedback"][0]["feedback"]
        self.assertEqual(fb["code"], "OWNER")
        self.assertTrue(fb["replaced_existing"])   # A-1000 had STL
        self.assertTrue(fb["created_code_value"])  # OWNER not previously in dict

    def test_missing_framework_errors(self):
        # minimal.xer has no ACTVTYPE/ACTVCODE/TASKACTV sections.
        out_path = str(Path(self.tmp) / "min-coded.xer")
        changes = [{"type": "set_responsibility", "activity_id": "M1000", "code": "OWNER"}]
        res = apply_xer_changes_impl(MINIMAL, changes, output_path=out_path, cache=self.cache)
        self.assertTrue(res["summary"]["validation_errors"])
        self.assertIsNone(res["output_path"])
        self.assertFalse(Path(out_path).exists())


if __name__ == "__main__":
    unittest.main()
