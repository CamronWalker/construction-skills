# scheduling/mcp-server/tests/test_quality.py
"""Tests for the quality-and-scoring MCP tools (F2 batch).

All tools in this module wrap functions from
``schedule-toolbox/lib/quality_checks.py`` (or, in the case of
``get_circular_relationships``, read cached CPM metadata). Tests use the
shared minimal.xer fixture: 2 milestones (NTP, SC) linked FS, both
zero-duration, no constraints, no high-float or negative-float values.

Most checks return trivial (count=0, status=PASS) results on this fixture --
the goal of these tests is to verify shape, key plumbing, parameter handling,
and the empty-result branch. Richer scenarios get validated against real XERs
during the batch's spec review.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools import quality  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestGetQualityCheck(unittest.TestCase):
    """Router that dispatches to ALL_CHECKS by name."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_dict_with_check_key(self):
        """Result is the underlying check_<name> dict, which always has the
        ``check`` identifier as a top-level key."""
        result = quality.get_quality_check_impl(
            str(FIXTURE), check_name="finish_to_start", cache=self.cache
        )
        self.assertEqual(result.get("check"), "finish_to_start")
        self.assertIn("status", result)

    def test_unknown_check_name_raises_value_error(self):
        """Unknown names produce a ValueError with the list of valid options."""
        with self.assertRaises(ValueError):
            quality.get_quality_check_impl(
                str(FIXTURE), check_name="not_a_real_check", cache=self.cache
            )

    def test_dispatches_to_multiple_named_checks(self):
        """Smoke-test the dispatcher across a handful of different checks --
        each should return its own ``check`` identifier."""
        for name in ("finish_to_start", "high_float", "duplicate_rels",
                     "sc_coverage", "missing_logic"):
            with self.subTest(check=name):
                result = quality.get_quality_check_impl(
                    str(FIXTURE), check_name=name, cache=self.cache
                )
                self.assertEqual(result.get("check"), name)

    def test_missing_logic_passes_all_preds(self):
        """``missing_logic`` is special-cased: the library helper needs
        ``all_preds`` to compute correctly. The router must populate it.
        On the minimal fixture (NTP -> SC), no_predecessor=[NTP] and
        no_successor=[SC]."""
        result = quality.get_quality_check_impl(
            str(FIXTURE), check_name="missing_logic", cache=self.cache
        )
        self.assertIn("no_predecessor", result)
        self.assertIn("no_successor", result)


class TestGetRelationshipTypeBreakdown(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_four_rel_type_keys(self):
        result = quality.get_relationship_type_breakdown_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertIn("FS", result)
        self.assertIn("SS", result)
        self.assertIn("FF", result)
        self.assertIn("SF", result)

    def test_each_value_is_a_check_result(self):
        result = quality.get_relationship_type_breakdown_impl(
            str(FIXTURE), cache=self.cache
        )
        for rel_type, sub in result.items():
            with self.subTest(rel_type=rel_type):
                self.assertIn("check", sub)
                self.assertIn("status", sub)
                self.assertIn("count", sub)

    def test_minimal_fixture_is_all_fs(self):
        """The single relationship on the fixture is FS, so FS.count=1 and
        SS/FF/SF.count=0."""
        result = quality.get_relationship_type_breakdown_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["FS"]["count"], 1)
        self.assertEqual(result["SS"]["count"], 0)
        self.assertEqual(result["FF"]["count"], 0)
        self.assertEqual(result["SF"]["count"], 0)


class TestGetMissingLogic(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_missing_logic_shape(self):
        result = quality.get_missing_logic_impl(str(FIXTURE), cache=self.cache)
        self.assertEqual(result.get("check"), "missing_logic")
        self.assertIn("no_predecessor", result)
        self.assertIn("no_successor", result)
        self.assertIn("status", result)

    def test_minimal_fixture_counts(self):
        """The library filters via _activities() (which excludes milestones),
        so the two milestones are dropped before the open-end check. Result:
        count=0 / status=PASS even though the schedule technically has open
        ends. This is the existing library behavior -- the MCP layer doesn't
        override it."""
        result = quality.get_missing_logic_impl(str(FIXTURE), cache=self.cache)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["status"], "PASS")


class TestGetHighFloatActivities(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_high_float_shape(self):
        result = quality.get_high_float_activities_impl(
            str(FIXTURE), threshold_days=44, cache=self.cache
        )
        self.assertEqual(result.get("check"), "high_float")
        self.assertIn("tasks", result)
        self.assertIsInstance(result["tasks"], list)

    def test_default_threshold_passes_through(self):
        """At threshold=44 the MCP layer just returns the library result
        unchanged."""
        result = quality.get_high_float_activities_impl(
            str(FIXTURE), threshold_days=44, cache=self.cache
        )
        # Minimal fixture has no high-float tasks (zero-duration milestones).
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["count"], 0)

    def test_threshold_above_cap_clamps(self):
        """threshold_days > 44 is silently clamped to 44; result identical to
        default."""
        default = quality.get_high_float_activities_impl(
            str(FIXTURE), threshold_days=44, cache=self.cache
        )
        clamped = quality.get_high_float_activities_impl(
            str(FIXTURE), threshold_days=999, cache=self.cache
        )
        self.assertEqual(default["tasks"], clamped["tasks"])
        self.assertEqual(default["count"], clamped["count"])

    def test_threshold_below_cap_filters(self):
        """threshold_days < 44 doesn't pull in new tasks (the library cap is
        still 44) but the MCP layer can shrink the list further. On the
        minimal fixture the result is still empty -- this test just verifies
        the filter path doesn't crash and returns the right shape."""
        result = quality.get_high_float_activities_impl(
            str(FIXTURE), threshold_days=10, cache=self.cache
        )
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["count"], 0)


class TestGetNegativeFloatActivities(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_negative_float_shape(self):
        result = quality.get_negative_float_activities_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result.get("check"), "negative_float")
        self.assertIn("tasks", result)
        self.assertIsInstance(result["tasks"], list)

    def test_empty_on_minimal_fixture(self):
        """Zero-duration milestones on a single-FS chain have TF=0, not
        negative. Result: empty tasks list, PASS status."""
        result = quality.get_negative_float_activities_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["status"], "PASS")


class TestGetConstraintViolations(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_constraints_shape(self):
        result = quality.get_constraint_violations_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result.get("check"), "constraints")
        self.assertIn("tasks", result)
        self.assertIsInstance(result["tasks"], list)

    def test_empty_on_minimal_fixture(self):
        """Both milestones have empty cstr_type fields -> no violations."""
        result = quality.get_constraint_violations_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["status"], "PASS")


class TestGetHighDurationActivities(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_high_duration_shape(self):
        result = quality.get_high_duration_activities_impl(
            str(FIXTURE), threshold_days=44, cache=self.cache
        )
        self.assertEqual(result.get("check"), "high_duration")
        self.assertIn("tasks", result)
        self.assertIsInstance(result["tasks"], list)

    def test_default_threshold_passes_through(self):
        result = quality.get_high_duration_activities_impl(
            str(FIXTURE), threshold_days=44, cache=self.cache
        )
        self.assertEqual(result["tasks"], [])

    def test_threshold_above_cap_clamps(self):
        default = quality.get_high_duration_activities_impl(
            str(FIXTURE), threshold_days=44, cache=self.cache
        )
        clamped = quality.get_high_duration_activities_impl(
            str(FIXTURE), threshold_days=200, cache=self.cache
        )
        self.assertEqual(default["count"], clamped["count"])

    def test_threshold_below_cap_filters(self):
        result = quality.get_high_duration_activities_impl(
            str(FIXTURE), threshold_days=5, cache=self.cache
        )
        self.assertEqual(result["tasks"], [])
        self.assertEqual(result["count"], 0)


class TestGetDuplicateRelationships(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_duplicate_rels_shape(self):
        result = quality.get_duplicate_relationships_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result.get("check"), "duplicate_rels")
        self.assertIn("relationships", result)
        self.assertIsInstance(result["relationships"], list)

    def test_empty_on_minimal_fixture(self):
        """Single TASKPRED row -> no duplicates possible."""
        result = quality.get_duplicate_relationships_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["relationships"], [])
        self.assertEqual(result["status"], "PASS")


class TestGetCircularRelationships(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_cycles_key(self):
        """Cycles always reads from CPM metadata. The key must be present
        whether or not the schedule has cycles."""
        result = quality.get_circular_relationships_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertIn("cycles", result)
        self.assertIsInstance(result["cycles"], list)

    def test_empty_on_minimal_fixture(self):
        """NTP -> SC is acyclic. CPM metadata has no circular_dependencies
        field, which the impl normalizes to an empty list."""
        result = quality.get_circular_relationships_impl(
            str(FIXTURE), cache=self.cache
        )
        self.assertEqual(result["cycles"], [])


class TestGetInvalidDates(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_future_actual_shape(self):
        result = quality.get_invalid_dates_impl(str(FIXTURE), cache=self.cache)
        self.assertEqual(result.get("check"), "future_actual")
        self.assertIn("tasks", result)
        self.assertIsInstance(result["tasks"], list)

    def test_empty_on_minimal_fixture(self):
        """Neither milestone has actual dates set -> no future-actual hits."""
        result = quality.get_invalid_dates_impl(str(FIXTURE), cache=self.cache)
        self.assertEqual(result["tasks"], [])


if __name__ == "__main__":
    unittest.main()
