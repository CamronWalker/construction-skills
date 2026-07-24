import json, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/ on path
import feedback_ingest as fi


ONLINE = {
    "job_number": "W1234",
    "current_version": "v3",
    "versions": ["v1", "v2", "v3"],
    "comments": [
        {"id": "c1", "version_label": "v2", "task_code": "A0010",
         "task_name_snapshot": "Mobilize", "orig_duration_snapshot": 5,
         "reviewer_id": "r1", "reviewer_name": "Steve Westover",
         "body": "Too short", "suggested_duration_days": 8, "resolved": False,
         "created_at": "2026-07-20T10:00:00Z"},
        {"id": "c2", "version_label": "v2", "task_code": "A0020",
         "task_name_snapshot": "Excavate", "orig_duration_snapshot": 10,
         "reviewer_id": "r1", "reviewer_name": "Steve Westover",
         "body": "ok", "suggested_duration_days": None, "resolved": False,
         "created_at": "2026-07-20T10:05:00Z"},
        {"id": "c3", "version_label": "v3", "task_code": "A0010",
         "task_name_snapshot": "Mobilize", "orig_duration_snapshot": 8,
         "reviewer_id": "r2", "reviewer_name": "Jane PM",
         "body": "resolved note", "suggested_duration_days": None, "resolved": True,
         "created_at": "2026-07-21T09:00:00Z"},
    ],
}


class TestMapOnlineComments(unittest.TestCase):
    def test_groups_by_reviewer_and_version(self):
        payloads = fi.map_online_comments(ONLINE)
        # Steve v2 (2 comments) + Jane v3 excluded (resolved) => 1 payload
        self.assertEqual(len(payloads), 1)
        p = payloads[0]
        self.assertEqual(p["schema"], "westland-reviewer-feedback")
        self.assertEqual(p["reviewer"]["name"], "Steve Westover")
        self.assertEqual(p["version_reviewed"], 2)
        self.assertEqual(len(p["activities"]), 2)

    def test_maps_suggested_duration_to_change(self):
        p = fi.map_online_comments(ONLINE)[0]
        a = next(x for x in p["activities"] if x["task_code"] == "A0010")
        self.assertEqual(a["duration_change"], {"from_days": 5, "to_days": 8})
        self.assertEqual(a["task_snapshot"]["duration_days"], 5)

    def test_include_resolved_flag(self):
        payloads = fi.map_online_comments(ONLINE, include_resolved=True)
        names = sorted(p["reviewer"]["name"] for p in payloads)
        self.assertEqual(names, ["Jane PM", "Steve Westover"])


if __name__ == "__main__":
    unittest.main()
