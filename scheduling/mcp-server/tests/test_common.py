"""Tests for the shared helper module ``tools/_common.py``.

The helpers were duplicated across ``quality.py``, ``omnibus.py``, and
``cpm_path.py`` in Plan 1; this module consolidates them. Tests pin the
behavior we're preserving so the duplicated-source removals are safe.
"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from tools._common import (  # noqa: E402
    FUTURE_DATE_SENTINEL,
    data_date_dt,
    data_date_str,
    resolve_metadata_for_milestone,
)


class TestDataDateStr(unittest.TestCase):
    def test_prefers_last_recalc_date(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25", "data_date": ""}]}
        self.assertEqual(data_date_str(parsed), "2026-05-25")

    def test_falls_back_to_data_date(self):
        parsed = {"PROJECT": [{"last_recalc_date": "", "data_date": "2026-05-20"}]}
        self.assertEqual(data_date_str(parsed), "2026-05-20")

    def test_empty_strings_collapse_to_none(self):
        parsed = {"PROJECT": [{"last_recalc_date": "", "data_date": ""}]}
        self.assertIsNone(data_date_str(parsed))

    def test_missing_project_returns_none(self):
        self.assertIsNone(data_date_str({}))

    def test_empty_project_returns_none(self):
        self.assertIsNone(data_date_str({"PROJECT": []}))

    def test_last_recalc_date_wins_when_both_populated(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25", "data_date": "2026-05-20"}]}
        self.assertEqual(data_date_str(parsed), "2026-05-25")


class TestDataDateDt(unittest.TestCase):
    def test_parses_datetime_format(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25 08:00"}]}
        self.assertEqual(data_date_dt(parsed), datetime(2026, 5, 25, 8, 0))

    def test_parses_date_only_format(self):
        parsed = {"PROJECT": [{"last_recalc_date": "2026-05-25"}]}
        self.assertEqual(data_date_dt(parsed), datetime(2026, 5, 25, 0, 0))

    def test_unparseable_returns_none(self):
        parsed = {"PROJECT": [{"last_recalc_date": "not-a-date"}]}
        self.assertIsNone(data_date_dt(parsed))

    def test_none_data_date_returns_none(self):
        self.assertIsNone(data_date_dt({}))


class TestFutureDateSentinel(unittest.TestCase):
    def test_value_matches_spec(self):
        self.assertEqual(FUTURE_DATE_SENTINEL, "2099-12-31")


class TestResolveMetadataForMilestone(unittest.TestCase):
    def test_none_milestone_returns_metadata_unchanged(self):
        metadata = {"sc_milestone_id": "A1000", "sc_milestone_name": "OldName"}
        result = resolve_metadata_for_milestone(metadata, None, [])
        self.assertIs(result, metadata)  # no copy — same object

    def test_explicit_milestone_sets_id(self):
        metadata = {"sc_milestone_id": "A1000"}
        tasks = [{"task_id": "T999", "task_name": "Custom SC", "task_code": "C9",
                  "early_end_date": "2026-12-31 17:00"}]
        result = resolve_metadata_for_milestone(metadata, "T999", tasks)
        self.assertEqual(result["sc_milestone_id"], "T999")
        self.assertEqual(result["sc_milestone_name"], "Custom SC")
        self.assertEqual(result["sc_milestone_code"], "C9")
        self.assertEqual(result["sc_milestone_date"], "2026-12-31 17:00")
        self.assertIsNot(result, metadata)  # shallow copy — original untouched

    def test_explicit_milestone_does_not_mutate_input(self):
        metadata = {"sc_milestone_id": "A1000", "sc_milestone_name": "OldName"}
        tasks = [{"task_id": "T999", "task_name": "Custom SC", "task_code": "C9",
                  "early_end_date": "2026-12-31 17:00"}]
        _ = resolve_metadata_for_milestone(metadata, "T999", tasks)
        self.assertEqual(metadata["sc_milestone_id"], "A1000")
        self.assertEqual(metadata["sc_milestone_name"], "OldName")

    def test_explicit_milestone_not_in_tasks_leaves_name_blank(self):
        metadata = {"sc_milestone_id": "A1000"}
        result = resolve_metadata_for_milestone(metadata, "MISSING", [])
        self.assertEqual(result["sc_milestone_id"], "MISSING")
        self.assertNotIn("sc_milestone_name", result)


if __name__ == "__main__":
    unittest.main()
