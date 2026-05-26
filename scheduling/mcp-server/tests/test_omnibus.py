# scheduling/mcp-server/tests/test_omnibus.py
"""Tests for the omnibus / composition MCP tools (F5 batch).

The three omnibus tools each call into one or more library functions and
project / combine their results into a single response dict. They DO NOT
delegate to other MCP tools' ``_impl`` functions -- to keep the modules
independent and the call graph flat, ``omnibus.py`` calls
``compute_quality_score``, ``compare_xer_pair``, ``expected_updates``,
``check_missing_logic``, ``check_high_float``, and ``check_anchor_dates``
directly.

* :func:`score_schedule` -- unpacks the 7-tuple from
  ``score_schedule.compute_quality_score`` into a flat dict
  ``{score, grade, scored, info, deductions, scope, details}``. Accepts an
  optional ``milestone_id`` (passed through unchanged).
* :func:`weekly_update_review` -- composes one ``compare_xer_pair`` call
  (reused for both activity_changes and milestone_slip slices), one
  ``expected_updates`` call (reused for both activities_to_start and
  activities_to_finish slices), and a ``compute_quality_score`` call on
  each side for a DCMA-delta. Plan-2 fields (``critical_path_changes``,
  ``gain_loss_attribution``) are stubbed to ``None`` with a
  ``pending_plan_2: True`` flag.
* :func:`proposal_schedule_health` -- composes ``compute_quality_score``
  (as ``score_summary``), ``check_missing_logic``, ``check_high_float``,
  and ``check_anchor_dates``. Anchor conflicts return ``None`` when no
  anchors are passed.

Fixtures:

* ``minimal.xer`` -- 2 milestones (NTP -> SC FS link), both
  ``TK_NotStart``, both zero-duration. SC at ``2026-06-25 17:00``.
* ``minimal_v2.xer`` -- copy of ``minimal.xer`` with SC's six date fields
  pushed +14 calendar days. The data_date is identical to minimal.xer.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import omnibus  # noqa: E402

FIXTURE_V1 = Path(__file__).parent / "fixtures" / "minimal.xer"
FIXTURE_V2 = Path(__file__).parent / "fixtures" / "minimal_v2.xer"


class TestScoreSchedule(unittest.TestCase):
    """Composes ``compute_quality_score(tasks, preds, data_date, milestone_id)``
    and unpacks the 7-tuple into a flat dict."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_seven_expected_keys(self):
        """The output dict has all seven keys from the 7-tuple unpack."""
        result = omnibus.score_schedule_impl(
            str(FIXTURE_V1), milestone_id=None, cache=self.cache
        )
        for key in (
            "score",
            "grade",
            "scored",
            "info",
            "deductions",
            "scope",
            "details",
        ):
            self.assertIn(key, result)

    def test_score_is_numeric_in_range(self):
        """``score`` is a number in [0, 100]."""
        result = omnibus.score_schedule_impl(
            str(FIXTURE_V1), milestone_id=None, cache=self.cache
        )
        self.assertIsInstance(result["score"], (int, float))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_grade_is_non_empty_string(self):
        """``grade`` is a non-empty letter grade string (e.g. ``A-``)."""
        result = omnibus.score_schedule_impl(
            str(FIXTURE_V1), milestone_id=None, cache=self.cache
        )
        self.assertIsInstance(result["grade"], str)
        self.assertTrue(result["grade"])

    def test_scope_carries_milestone_id(self):
        """``compute_quality_score`` stamps the resolved milestone_id into
        ``scope['milestone_id']``. On minimal.xer, that's the SC task_id."""
        result = omnibus.score_schedule_impl(
            str(FIXTURE_V1), milestone_id=None, cache=self.cache
        )
        self.assertEqual(result["scope"].get("milestone_id"), "10002")

    def test_explicit_milestone_id_matches_auto_resolution(self):
        """Passing ``milestone_id='10002'`` produces the same score as
        omitting it (minimal.xer auto-resolves to that milestone)."""
        auto = omnibus.score_schedule_impl(
            str(FIXTURE_V1), milestone_id=None, cache=self.cache
        )
        explicit = omnibus.score_schedule_impl(
            str(FIXTURE_V1), milestone_id="10002", cache=self.cache
        )
        self.assertEqual(auto["score"], explicit["score"])
        self.assertEqual(auto["grade"], explicit["grade"])


class TestWeeklyUpdateReview(unittest.TestCase):
    """Composes ``compare_xer_pair`` + ``expected_updates`` +
    ``compute_quality_score`` (both sides) and stubs the two Plan-2 fields."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_all_top_level_keys(self):
        """All composition subkeys plus Plan-2 stubs are present."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        for key in (
            "baseline_xer_path",
            "current_xer_path",
            "activity_changes",
            "milestone_slip",
            "activities_to_start",
            "activities_to_finish",
            "dcma_delta",
            "critical_path_changes",
            "gain_loss_attribution",
            "pending_plan_2",
        ):
            self.assertIn(key, result)

    def test_milestone_slip_is_fourteen_days(self):
        """v1 -> v2 moved SC's six dates +14 days; the milestone_slip
        subdict should reflect that exactly."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        slip = result["milestone_slip"]
        self.assertEqual(slip["sc_slip_days"], 14)
        self.assertEqual(slip["sc_date_old"], "2026-06-25")
        self.assertEqual(slip["sc_date_new"], "2026-07-09")

    def test_activity_changes_subkeys(self):
        """``activity_changes`` has the four list subkeys (added_tasks,
        removed_tasks, changed_durations, status_changes). v1 and v2 share
        identical task sets, so all four are empty."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        changes = result["activity_changes"]
        for key in (
            "added_tasks",
            "removed_tasks",
            "changed_durations",
            "status_changes",
        ):
            self.assertIn(key, changes)
            self.assertEqual(changes[key], [])

    def test_plan_2_stubs_present(self):
        """Plan-2 fields are explicitly stubbed: critical_path_changes and
        gain_loss_attribution are None, pending_plan_2 is True."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        self.assertIsNone(result["critical_path_changes"])
        self.assertIsNone(result["gain_loss_attribution"])
        self.assertTrue(result["pending_plan_2"])

    def test_dcma_delta_shape(self):
        """``dcma_delta`` is either a dict with the 5 expected keys OR None
        (when ``MilestoneAmbiguousError`` is raised on either side). On
        minimal.xer / minimal_v2.xer (both single-terminal), it's the dict."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        dd = result["dcma_delta"]
        if dd is not None:
            for key in (
                "baseline_score",
                "current_score",
                "score_delta",
                "baseline_grade",
                "current_grade",
            ):
                self.assertIn(key, dd)
            # delta is current - baseline (both numeric).
            self.assertEqual(
                round(dd["score_delta"], 6),
                round(dd["current_score"] - dd["baseline_score"], 6),
            )

    def test_activities_lists_are_lists(self):
        """The two activities_to_* subkeys are lists (possibly empty)."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        self.assertIsInstance(result["activities_to_start"], list)
        self.assertIsInstance(result["activities_to_finish"], list)

    def test_passes_through_paths(self):
        """The two xer_path arguments are echoed back unchanged."""
        result = omnibus.weekly_update_review_impl(
            baseline_xer_path=str(FIXTURE_V1),
            current_xer_path=str(FIXTURE_V2),
            milestone_id=None,
            future_date=None,
            cache=self.cache,
        )
        self.assertEqual(result["baseline_xer_path"], str(FIXTURE_V1))
        self.assertEqual(result["current_xer_path"], str(FIXTURE_V2))


class TestProposalScheduleHealth(unittest.TestCase):
    """Composes ``compute_quality_score`` + ``check_missing_logic`` +
    ``check_high_float`` + ``check_anchor_dates``."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_all_top_level_keys(self):
        """All four sub-call keys are present."""
        result = omnibus.proposal_schedule_health_impl(
            xer_path=str(FIXTURE_V1),
            milestone_id=None,
            anchors_path=None,
            anchors=None,
            cache=self.cache,
        )
        for key in (
            "xer_path",
            "score_summary",
            "missing_logic",
            "high_float",
            "anchor_conflicts",
        ):
            self.assertIn(key, result)

    def test_score_summary_has_score_grade(self):
        """``score_summary`` carries the same 7-key shape as the
        score_schedule tool: score, grade, scored, info, deductions, scope,
        details."""
        result = omnibus.proposal_schedule_health_impl(
            xer_path=str(FIXTURE_V1),
            milestone_id=None,
            anchors_path=None,
            anchors=None,
            cache=self.cache,
        )
        summary = result["score_summary"]
        for key in (
            "score",
            "grade",
            "scored",
            "info",
            "deductions",
            "scope",
            "details",
        ):
            self.assertIn(key, summary)

    def test_missing_logic_is_result_envelope(self):
        """``missing_logic`` is the standard ``_result`` envelope from the
        library, with ``check`` / ``status`` / ``no_predecessor`` /
        ``no_successor`` keys."""
        result = omnibus.proposal_schedule_health_impl(
            xer_path=str(FIXTURE_V1),
            milestone_id=None,
            anchors_path=None,
            anchors=None,
            cache=self.cache,
        )
        ml = result["missing_logic"]
        self.assertEqual(ml.get("check"), "missing_logic")
        self.assertIn("no_predecessor", ml)
        self.assertIn("no_successor", ml)

    def test_high_float_is_result_envelope(self):
        """``high_float`` is the standard ``_result`` envelope with
        ``check`` / ``tasks`` keys."""
        result = omnibus.proposal_schedule_health_impl(
            xer_path=str(FIXTURE_V1),
            milestone_id=None,
            anchors_path=None,
            anchors=None,
            cache=self.cache,
        )
        hf = result["high_float"]
        self.assertEqual(hf.get("check"), "high_float")
        self.assertIn("tasks", hf)

    def test_anchor_conflicts_none_when_no_anchors(self):
        """When neither ``anchors`` nor ``anchors_path`` is provided,
        ``anchor_conflicts`` is None (no anchors -> no conflicts to check)."""
        result = omnibus.proposal_schedule_health_impl(
            xer_path=str(FIXTURE_V1),
            milestone_id=None,
            anchors_path=None,
            anchors=None,
            cache=self.cache,
        )
        self.assertIsNone(result["anchor_conflicts"])

    def test_anchor_conflicts_with_inline_anchors(self):
        """When ``anchors`` is provided inline, ``anchor_conflicts`` is a
        dict with a ``slips`` key (list, possibly empty). Use an SC anchor
        that should slip relative to the CPM-computed SC date."""
        anchors = [
            {
                "task_code": "M2000",
                "anchor_date": "2026-06-01",
                "anchor_kind": "finish",
                "kind_label": "SC",
            }
        ]
        result = omnibus.proposal_schedule_health_impl(
            xer_path=str(FIXTURE_V1),
            milestone_id=None,
            anchors_path=None,
            anchors=anchors,
            cache=self.cache,
        )
        ac = result["anchor_conflicts"]
        self.assertIsNotNone(ac)
        self.assertIn("slips", ac)
        self.assertIsInstance(ac["slips"], list)


if __name__ == "__main__":
    unittest.main()
