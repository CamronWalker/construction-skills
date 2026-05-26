# scheduling/mcp-server/tests/test_update_review.py
"""Tests for the schedule-update-review MCP tools (F3 batch).

All four tools wrap a single underlying library function from
``schedule-toolbox/lib/update_review.py``:

* ``get_activities_to_start`` / ``get_activities_to_finish`` /
  ``get_in_progress_activities`` all project a sub-key from one
  ``expected_updates(tables, future_date, resource_filter=None)`` call.
* ``get_ride_data_date_violations`` wraps ``riding_data_date(tables)``.

The minimal.xer fixture is two milestones (NTP -> SC, both ``TK_NotStart``,
both zero-duration) with NTP at ``2026-05-25 08:00`` and SC at
``2026-06-25 17:00`` per the fixture. The library's ``_activity_filter`` keeps
milestones (it only excludes ``TT_WBS`` / ``TT_LOE``), so both tasks are in
the candidate set. None of them are ``TK_Active``, which makes ``to_finish``
and ``in_progress`` trivially empty on this fixture -- shape verification is
the value, not richer scenarios.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import update_review  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestGetActivitiesToStart(unittest.TestCase):
    """Wraps ``expected_updates(...).to_start``."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_to_start_key(self):
        """Top-level dict has ``to_start`` as a list."""
        result = update_review.get_activities_to_start_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertIn("to_start", result)
        self.assertIsInstance(result["to_start"], list)

    def test_returns_passthrough_metadata_keys(self):
        """The tool projects the lib's metadata keys (``data_date``,
        ``future_date``, ``resource_filter``) verbatim."""
        result = update_review.get_activities_to_start_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertIn("data_date", result)
        self.assertEqual(result["future_date"], "2099-12-31")
        self.assertIsNone(result["resource_filter"])

    def test_far_future_captures_both_milestones(self):
        """Both NTP and SC are ``TK_NotStart`` with early_start before
        2099-12-31 -> both land in to_start. The lib emits each row with
        ``task_id`` plus duration / date fields."""
        result = update_review.get_activities_to_start_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        task_ids = {row["task_id"] for row in result["to_start"]}
        self.assertEqual(task_ids, {"10001", "10002"})
        for row in result["to_start"]:
            self.assertIn("early_start", row)
            self.assertIn("task_code", row)
            self.assertIn("task_name", row)

    def test_past_future_date_yields_empty_to_start(self):
        """``future_date`` before either milestone's early_start excludes
        every candidate. NTP starts 2026-05-25, so 2020-01-01 is before."""
        result = update_review.get_activities_to_start_impl(
            str(FIXTURE),
            future_date="2020-01-01",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertEqual(result["to_start"], [])

    def test_resource_filter_returns_empty_when_no_match(self):
        """The minimal fixture has no resource assignments, so any
        ``resource_filter`` produces an empty list -- but the parameter must
        reach the lib (echoed back via ``resource_filter`` in the output)."""
        result = update_review.get_activities_to_start_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter="ELEC",
            cache=self.cache,
        )
        self.assertEqual(result["resource_filter"], "ELEC")
        self.assertEqual(result["to_start"], [])


class TestGetActivitiesToFinish(unittest.TestCase):
    """Wraps ``expected_updates(...).to_finish``."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_to_finish_key(self):
        result = update_review.get_activities_to_finish_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertIn("to_finish", result)
        self.assertIsInstance(result["to_finish"], list)

    def test_empty_on_minimal_fixture(self):
        """to_finish requires ``TK_Active`` status. Both fixture milestones
        are ``TK_NotStart`` -> empty even with a far-future window."""
        result = update_review.get_activities_to_finish_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertEqual(result["to_finish"], [])

    def test_passthrough_metadata_keys(self):
        result = update_review.get_activities_to_finish_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertIn("data_date", result)
        self.assertEqual(result["future_date"], "2099-12-31")
        self.assertIsNone(result["resource_filter"])

    def test_does_not_include_to_start_or_in_progress_keys(self):
        """The tool projects only its own subkey; sibling lists are not
        echoed back (each tool returns its own focused payload)."""
        result = update_review.get_activities_to_finish_impl(
            str(FIXTURE),
            future_date="2099-12-31",
            resource_filter=None,
            cache=self.cache,
        )
        self.assertNotIn("to_start", result)
        self.assertNotIn("in_progress", result)


class TestGetInProgressActivities(unittest.TestCase):
    """Wraps ``expected_updates(...).in_progress``.

    ``expected_updates`` requires a ``future_date`` argument, but the
    in_progress list isn't filtered by it (just "all ``TK_Active`` tasks").
    The tool hides ``future_date`` from its signature and passes a sentinel
    internally so callers don't have to think about it.
    """

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_in_progress_key(self):
        result = update_review.get_in_progress_activities_impl(
            str(FIXTURE), resource_filter=None, cache=self.cache
        )
        self.assertIn("in_progress", result)
        self.assertIsInstance(result["in_progress"], list)

    def test_empty_on_minimal_fixture(self):
        """No ``TK_Active`` tasks in the fixture -> empty list."""
        result = update_review.get_in_progress_activities_impl(
            str(FIXTURE), resource_filter=None, cache=self.cache
        )
        self.assertEqual(result["in_progress"], [])

    def test_metadata_excludes_future_date(self):
        """``future_date`` is an internal implementation detail; the tool
        output exposes ``data_date`` and ``resource_filter`` but not the
        sentinel ``future_date`` value the impl passed to the lib."""
        result = update_review.get_in_progress_activities_impl(
            str(FIXTURE), resource_filter=None, cache=self.cache
        )
        self.assertIn("data_date", result)
        self.assertIn("resource_filter", result)
        self.assertNotIn("future_date", result)

    def test_resource_filter_propagates(self):
        result = update_review.get_in_progress_activities_impl(
            str(FIXTURE), resource_filter="MECH", cache=self.cache
        )
        self.assertEqual(result["resource_filter"], "MECH")
        self.assertEqual(result["in_progress"], [])


class TestGetRideDataDateViolations(unittest.TestCase):
    """Wraps ``riding_data_date(tables)`` -- not-started activities whose
    logic is complete but held by the data date.

    On the minimal fixture: NTP has no predecessors (the lib's `if not
    task_preds: continue` skips it). SC has NTP as a predecessor, but NTP
    is ``TK_NotStart`` (not ``TK_Complete``), so the "all preds complete"
    branch fails. Result: empty ``tasks`` list, ``count=0``.
    """

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_full_lib_envelope(self):
        """The tool returns the lib's result dict verbatim -- ``data_date``,
        ``count``, ``total_incomplete``, ``pct``, ``tasks``, ``note``."""
        result = update_review.get_ride_data_date_violations_impl(
            str(FIXTURE), cache=self.cache
        )
        for key in (
            "data_date",
            "count",
            "total_incomplete",
            "pct",
            "tasks",
            "note",
        ):
            self.assertIn(key, result)

    def test_empty_on_minimal_fixture(self):
        """No riding tasks on the minimal fixture (see class docstring)."""
        result = update_review.get_ride_data_date_violations_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["tasks"], [])

    def test_total_incomplete_counts_both_milestones(self):
        """Both fixture milestones are incomplete (``TK_NotStart``), so
        the denominator is 2."""
        result = update_review.get_ride_data_date_violations_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["total_incomplete"], 2)


if __name__ == "__main__":
    unittest.main()
