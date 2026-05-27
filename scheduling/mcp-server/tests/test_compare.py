# scheduling/mcp-server/tests/test_compare.py
"""Tests for the XER-pair comparison MCP tools (F4 batch).

All four tools wrap a single underlying library function from
``schedule-toolbox/lib/xer_compare.py`` -- ``compare_xer_pair(old, new,
match_by='task_code', milestone_id=None)`` returns a unified dict; each MCP
tool projects a different subset of keys:

* ``compare_activity_changes`` -> ``added_tasks`` / ``removed_tasks`` /
  ``changed_durations`` / ``status_changes`` (plus the two ``*_data_date``
  metadata keys)
* ``compare_date_slips`` -> ``date_slippage``
* ``compare_milestone_slip`` -> ``sc_date_old`` / ``sc_date_new`` /
  ``sc_slip_days`` / ``sc_info_old`` / ``sc_info_new``
* ``compare_missed_dates`` -> ``missed_starts`` / ``missed_finishes``

The fixture pair is:

* ``minimal.xer`` -- two milestones (NTP -> SC), both ``TK_NotStart``, both
  zero-duration. NTP at ``2026-05-25 08:00`` (early/late/target start+end),
  SC at ``2026-06-25 17:00`` (same six date fields).
* ``minimal_v2.xer`` -- copy of ``minimal.xer`` with SC's six dates pushed
  forward 14 calendar days (``2026-06-25 17:00`` -> ``2026-07-09 17:00``)
  *and* the PROJECT ``scd_end_date`` matched to the new SC date so the
  project metadata stays semantically consistent. NTP is untouched. The
  data_date (``last_recalc_date``) is identical to ``minimal.xer``, which
  keeps ``missed_starts`` / ``missed_finishes`` empty on the pair.

Why "14 days" lands cleanly: ``compare_xer_pair`` runs against the
parsed-table values directly (no CPM recompute in the compare path), so
editing the date strings in the XER text is what makes the slip visible.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import compare  # noqa: E402

FIXTURE_V1 = Path(__file__).parent / "fixtures" / "minimal.xer"
FIXTURE_V2 = Path(__file__).parent / "fixtures" / "minimal_v2.xer"


class TestCompareActivityChanges(unittest.TestCase):
    """Wraps ``compare_xer_pair(...)`` projecting the four activity-set
    subkeys (``added_tasks``, ``removed_tasks``, ``changed_durations``,
    ``status_changes``)."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_projected_keys(self):
        """The output dict carries exactly the projected subset: the two
        ``*_data_date`` metadata keys plus the four activity-set lists.
        Other subkeys from ``compare_xer_pair`` (``date_slippage``,
        ``sc_slip_days``, etc.) must NOT leak through."""
        result = compare.compare_activity_changes_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        for key in (
            "old_data_date",
            "new_data_date",
            "added_tasks",
            "removed_tasks",
            "changed_durations",
            "status_changes",
        ):
            self.assertIn(key, result)
        # Sibling subkeys should not be echoed.
        for forbidden in (
            "date_slippage",
            "missed_starts",
            "sc_slip_days",
        ):
            self.assertNotIn(forbidden, result)

    def test_no_activity_changes_on_v1_v2_pair(self):
        """v1 and v2 have identical task sets (NTP + SC), identical
        durations (both 0), and identical statuses (both TK_NotStart) -- the
        only delta is SC's dates. All four activity-set lists should be
        empty."""
        result = compare.compare_activity_changes_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        self.assertEqual(result["added_tasks"], [])
        self.assertEqual(result["removed_tasks"], [])
        self.assertEqual(result["changed_durations"], [])
        self.assertEqual(result["status_changes"], [])

    def test_match_by_task_id_also_works(self):
        """The ``match_by`` parameter is plumbed through to the lib. Both
        fixtures use the same task_ids so the activity-set is still empty."""
        result = compare.compare_activity_changes_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_id",
            cache=self.cache,
        )
        self.assertEqual(result["added_tasks"], [])
        self.assertEqual(result["removed_tasks"], [])


class TestCompareDateSlips(unittest.TestCase):
    """Wraps ``compare_xer_pair(...).date_slippage``."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_projected_keys(self):
        result = compare.compare_date_slips_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        self.assertIn("old_data_date", result)
        self.assertIn("new_data_date", result)
        self.assertIn("date_slippage", result)
        self.assertIsInstance(result["date_slippage"], list)
        self.assertNotIn("sc_slip_days", result)
        self.assertNotIn("added_tasks", result)

    def test_sc_appears_with_14_day_slip(self):
        """SC's six date fields all moved 14 days. NTP's didn't move.
        ``date_slippage`` should have exactly one row keyed by SC's
        task_code (M2000), with both ``es_slip_days`` and ``ef_slip_days``
        equal to 14."""
        result = compare.compare_date_slips_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        rows = result["date_slippage"]
        # NTP didn't slip; SC did. Lib filters out tasks with |es| < 1 AND
        # |ef| < 1, so only SC remains.
        sc_rows = [r for r in rows if r["task_code"] == "M2000"]
        self.assertEqual(len(sc_rows), 1)
        sc = sc_rows[0]
        self.assertEqual(sc["es_slip_days"], 14)
        self.assertEqual(sc["ef_slip_days"], 14)
        # NTP must not be present.
        self.assertEqual(
            [r for r in rows if r["task_code"] == "M1000"], []
        )

    def test_inverse_slip_when_swapped(self):
        """Swapping baseline<->current produces -14 day slips on the same
        row."""
        result = compare.compare_date_slips_impl(
            str(FIXTURE_V2), str(FIXTURE_V1), match_by="task_code",
            cache=self.cache,
        )
        sc_rows = [r for r in result["date_slippage"]
                   if r["task_code"] == "M2000"]
        self.assertEqual(len(sc_rows), 1)
        self.assertEqual(sc_rows[0]["es_slip_days"], -14)
        self.assertEqual(sc_rows[0]["ef_slip_days"], -14)


class TestCompareMilestoneSlip(unittest.TestCase):
    """Wraps ``compare_xer_pair(...)`` projecting the SC-slip subkeys.

    The library function resolves the terminal milestone against the *new*
    schedule and mirrors to the old by ``match_by`` key. On this fixture pair
    SC (TT_FinMile, the single non-WBS/non-LOE terminal milestone) auto-
    resolves both with and without an explicit ``milestone_id``.
    """

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_projected_keys(self):
        result = compare.compare_milestone_slip_impl(
            str(FIXTURE_V1), str(FIXTURE_V2),
            milestone_id=None, match_by="task_code", cache=self.cache,
        )
        for key in (
            "sc_date_old",
            "sc_date_new",
            "sc_slip_days",
            "sc_info_old",
            "sc_info_new",
        ):
            self.assertIn(key, result)
        self.assertNotIn("added_tasks", result)
        self.assertNotIn("date_slippage", result)

    def test_sc_slip_days_is_14(self):
        """SC moved from 2026-06-25 -> 2026-07-09 (14 days forward)."""
        result = compare.compare_milestone_slip_impl(
            str(FIXTURE_V1), str(FIXTURE_V2),
            milestone_id=None, match_by="task_code", cache=self.cache,
        )
        self.assertEqual(result["sc_slip_days"], 14)
        self.assertEqual(result["sc_date_old"], "2026-06-25")
        self.assertEqual(result["sc_date_new"], "2026-07-09")

    def test_explicit_milestone_id_same_result(self):
        """Passing SC's task_id ('10002') explicitly produces the same
        14-day slip as auto-resolution does."""
        result = compare.compare_milestone_slip_impl(
            str(FIXTURE_V1), str(FIXTURE_V2),
            milestone_id="10002", match_by="task_code", cache=self.cache,
        )
        self.assertEqual(result["sc_slip_days"], 14)

    def test_inverse_slip_when_swapped(self):
        """Swap baseline<->current: SC now moves backward 14 days."""
        result = compare.compare_milestone_slip_impl(
            str(FIXTURE_V2), str(FIXTURE_V1),
            milestone_id=None, match_by="task_code", cache=self.cache,
        )
        self.assertEqual(result["sc_slip_days"], -14)


class TestCompareMissedDates(unittest.TestCase):
    """Wraps ``compare_xer_pair(...)`` projecting the missed-date subkeys.

    Missed starts/finishes are computed against the *new* data date: a task
    is "missed" if its planned start (per the old schedule) is on or before
    the new data date but it hasn't actually started/finished yet. The
    fixture pair shares the same ``last_recalc_date`` (``2026-05-25 11:12``),
    which is two days before NTP's planned start of ``2026-05-25 08:00`` --
    wait, those are the same calendar day but the time-of-day difference
    matters less than the fact that nothing has progressed. The library's
    missed-date helpers require missing both old and new act_start fields
    to count as missed; both fixtures have NTP and SC un-started.

    On this fixture the lists are expected to be empty because neither
    fixture's data_date has advanced past unstarted activities in a way that
    flags as "missed" (NTP starts ON the data_date, not before it).
    """

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_projected_keys(self):
        result = compare.compare_missed_dates_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        for key in (
            "old_data_date",
            "new_data_date",
            "missed_starts",
            "missed_finishes",
        ):
            self.assertIn(key, result)
        self.assertNotIn("date_slippage", result)
        self.assertNotIn("sc_slip_days", result)
        self.assertNotIn("added_tasks", result)

    def test_data_dates_match(self):
        """``minimal_v2.xer`` keeps the same ``last_recalc_date`` as
        ``minimal.xer`` -- only SC's task-row dates moved."""
        result = compare.compare_missed_dates_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        self.assertEqual(result["old_data_date"], result["new_data_date"])

    def test_lists_are_lists(self):
        """Shape sanity: both missed-date entries are lists (possibly empty
        on this fixture pair)."""
        result = compare.compare_missed_dates_impl(
            str(FIXTURE_V1), str(FIXTURE_V2), match_by="task_code",
            cache=self.cache,
        )
        self.assertIsInstance(result["missed_starts"], list)
        self.assertIsInstance(result["missed_finishes"], list)


if __name__ == "__main__":
    unittest.main()
