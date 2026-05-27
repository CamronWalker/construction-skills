import unittest
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from milestones import get_milestones, MilestoneAmbiguousError
from quality_checks import _parse_xer

FIXTURE = Path(__file__).parent.parent.parent.parent / "mcp-server" / "tests" / "fixtures" / "minimal.xer"


class TestGetMilestones(unittest.TestCase):
    def test_returns_milestone_tasks(self):
        parsed = _parse_xer(str(FIXTURE))
        result = get_milestones(parsed["TASK"])
        self.assertEqual(len(result), 2)
        names = {m["task_name"] for m in result}
        self.assertIn("Substantial Completion", names)

    def test_excludes_wbs_and_loe(self):
        tasks = [
            {"task_id": 1, "task_name": "NTP", "task_type": "TT_Mile", "status_code": "TK_NotStart"},
            {"task_id": 2, "task_name": "WBS Bar", "task_type": "TT_WBS", "status_code": "TK_NotStart"},
            {"task_id": 3, "task_name": "LOE", "task_type": "TT_LOE", "status_code": "TK_NotStart"},
            {"task_id": 4, "task_name": "SC", "task_type": "TT_FinMile", "status_code": "TK_NotStart"},
        ]
        result = get_milestones(tasks)
        task_ids = {m["task_id"] for m in result}
        self.assertEqual(task_ids, {1, 4})

    def test_excludes_complete_milestones_by_default(self):
        tasks = [
            {"task_id": 1, "task_name": "NTP", "task_type": "TT_Mile", "status_code": "TK_Complete"},
            {"task_id": 2, "task_name": "SC", "task_type": "TT_FinMile", "status_code": "TK_NotStart"},
        ]
        result = get_milestones(tasks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["task_id"], 2)

    def test_include_complete_flag(self):
        tasks = [
            {"task_id": 1, "task_name": "NTP", "task_type": "TT_Mile", "status_code": "TK_Complete"},
            {"task_id": 2, "task_name": "SC", "task_type": "TT_FinMile", "status_code": "TK_NotStart"},
        ]
        result = get_milestones(tasks, include_complete=True)
        self.assertEqual(len(result), 2)


class TestMilestoneAmbiguousError(unittest.TestCase):
    def test_carries_candidate_list(self):
        candidates = [{"task_id": 1, "task_name": "A"}, {"task_id": 2, "task_name": "B"}]
        err = MilestoneAmbiguousError("ambiguous", candidates=candidates)
        self.assertEqual(err.candidates, candidates)


if __name__ == "__main__":
    unittest.main()
