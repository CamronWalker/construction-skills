# scheduling/mcp-server/tests/test_responsibility.py
"""Tests for the suggest_responsibility MCP tool.

Uses a lightweight fake cache returning a hand-built parsed dict, so the test
exercises the tool wiring (resolve type, skip already-assigned, bucket
assigned/unsure) against the REAL shipped keyword map without needing an XER
fixture.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from tools import responsibility  # noqa: E402


class FakeCache:
    def __init__(self, parsed):
        self._parsed = parsed

    def get_parsed(self, _xer_path):
        return self._parsed


def _parsed(tasks, taskactv=None, actvtype=None):
    return {
        "TASK": tasks,
        "TASKACTV": taskactv or [],
        "ACTVTYPE": actvtype if actvtype is not None else [
            {"actv_code_type_id": "148", "actv_code_type": "Responsibility - Global",
             "actv_code_type_scope": "AS_Global"},
        ],
    }


class TestSuggestResponsibility(unittest.TestCase):
    def _run(self, parsed, **kw):
        return responsibility.suggest_responsibility_impl(
            "dummy.xer", kw.get("only_unassigned", True),
            kw.get("code_type", None), FakeCache(parsed))

    def test_confident_and_unsure_buckets(self):
        tasks = [
            {"task_id": "1", "task_code": "A-1", "task_name": "Rough-In Electrical Level 2",
             "task_type": "TT_Task"},
            {"task_id": "2", "task_code": "A-2", "task_name": "Hang and Tape Drywall",
             "task_type": "TT_Task"},
            {"task_id": "3", "task_code": "A-3", "task_name": "Install Fire Sprinkler Mains",
             "task_type": "TT_Task"},
            {"task_id": "4", "task_code": "A-4", "task_name": "General Mobilization",
             "task_type": "TT_Task"},
        ]
        res = self._run(_parsed(tasks))
        assigned = {a["task_code"]: a["suggested_code"] for a in res["assigned"]}
        self.assertEqual(assigned.get("A-1"), "ELEC")
        self.assertEqual(assigned.get("A-2"), "DRYW")
        self.assertEqual(assigned.get("A-3"), "FIRE")
        self.assertIn("A-4", {u["task_code"] for u in res["unsure"]})
        self.assertEqual(res["code_type_name"], "Responsibility - Global")
        self.assertTrue(res["responsibility_type_present"])
        # full code list is surfaced for adjudication
        self.assertTrue(any(c["code"] == "STR-STEEL" for c in res["all_codes"]))

    def test_skips_wbs_and_loe_rows(self):
        tasks = [
            {"task_id": "1", "task_code": "W-1", "task_name": "Building Summary",
             "task_type": "TT_WBS"},
            {"task_id": "2", "task_code": "A-2", "task_name": "Install Electrical",
             "task_type": "TT_Task"},
        ]
        res = self._run(_parsed(tasks))
        self.assertEqual(res["total_activities"], 1)

    def test_only_unassigned_skips_already_coded(self):
        tasks = [
            {"task_id": "1", "task_code": "A-1", "task_name": "Install Electrical",
             "task_type": "TT_Task"},
            {"task_id": "2", "task_code": "A-2", "task_name": "Hang Drywall",
             "task_type": "TT_Task"},
        ]
        # A-1 (task_id 1) already has a Responsibility-Global assignment
        taskactv = [{"task_id": "1", "actv_code_type_id": "148", "actv_code_id": "900"}]
        res = self._run(_parsed(tasks, taskactv=taskactv))
        self.assertEqual(res["already_assigned"], 1)
        seen = {a["task_code"] for a in res["assigned"]} | {u["task_code"] for u in res["unsure"]}
        self.assertNotIn("A-1", seen)
        self.assertIn("A-2", seen)

    def test_only_unassigned_false_considers_all(self):
        tasks = [
            {"task_id": "1", "task_code": "A-1", "task_name": "Install Electrical",
             "task_type": "TT_Task"},
        ]
        taskactv = [{"task_id": "1", "actv_code_type_id": "148", "actv_code_id": "900"}]
        res = self._run(_parsed(tasks, taskactv=taskactv), only_unassigned=False)
        self.assertEqual(res["already_assigned"], 0)
        self.assertEqual(res["assigned_count"] + res["unsure_count"], 1)


if __name__ == "__main__":
    unittest.main()
