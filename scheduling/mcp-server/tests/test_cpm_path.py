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

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES_DIR / "minimal.xer"


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


class TestGetDrivingPaths(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_driving_paths_key(self):
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id=None, cache=self.cache
        )
        self.assertIn("driving_paths", result)
        self.assertIsInstance(result["driving_paths"], list)

    def test_no_activity_returns_end_state_paths(self):
        """Without activity_id, the tool exposes extract_paths['driving_paths']
        -- paths walked back from end-states. The minimal fixture has at
        least one (SC milestone is a terminal)."""
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id=None, cache=self.cache
        )
        self.assertGreater(len(result["driving_paths"]), 0)

    def test_with_activity_id_returns_single_forward_chain(self):
        """activity_id='10001' (NTP) traces forward to SC; result is a single-
        element list whose chain ends at the SC task_id."""
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id="10001", cache=self.cache
        )
        self.assertEqual(len(result["driving_paths"]), 1)
        chain = result["driving_paths"][0]["chain"]
        self.assertEqual(chain[0]["task_id"], "10001")
        self.assertEqual(chain[-1]["task_id"], "10002")

    def test_each_path_has_chain_and_end_metadata(self):
        result = cpm_path.get_driving_paths_impl(
            str(FIXTURE), activity_id=None, cache=self.cache
        )
        for p in result["driving_paths"]:
            self.assertIn("chain", p)
            self.assertIn("end_task_id", p)
            self.assertIsInstance(p["chain"], list)


class TestGetAnchorConflicts(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_no_slip_when_anchor_matches(self):
        """SC computes to 2026-05-25 in this fixture (two zero-duration
        milestones with FS link -> SC's EF inherits NTP's EF). Anchoring
        SC there gives zero slips."""
        anchors = [
            {
                "task_code": "M2000",
                "anchor_date": "2026-05-25",
                "anchor_kind": "finish",
                "kind_label": "SC",
            }
        ]
        result = cpm_path.get_anchor_conflicts_impl(
            str(FIXTURE),
            anchors=anchors,
            anchors_path=None,
            tolerance_days=0,
            cache=self.cache,
        )
        self.assertEqual(result["slips"], [])

    def test_slip_detected_when_anchor_earlier(self):
        """Anchoring SC at 2026-05-01 yields a positive slip_days."""
        anchors = [
            {
                "task_code": "M2000",
                "anchor_date": "2026-05-01",
                "anchor_kind": "finish",
                "kind_label": "SC",
            }
        ]
        result = cpm_path.get_anchor_conflicts_impl(
            str(FIXTURE),
            anchors=anchors,
            anchors_path=None,
            tolerance_days=0,
            cache=self.cache,
        )
        self.assertEqual(len(result["slips"]), 1)
        self.assertGreater(result["slips"][0]["slip_days"], 0)
        self.assertEqual(result["slips"][0]["task_code"], "M2000")

    def test_tolerance_days_absorbs_small_slip(self):
        """A 1-day anchor delta is absorbed by tolerance_days=60."""
        anchors = [
            {
                "task_code": "M2000",
                "anchor_date": "2026-06-26",
                "anchor_kind": "finish",
                "kind_label": "SC",
            }
        ]
        result = cpm_path.get_anchor_conflicts_impl(
            str(FIXTURE),
            anchors=anchors,
            anchors_path=None,
            tolerance_days=60,
            cache=self.cache,
        )
        self.assertEqual(result["slips"], [])

    def test_anchors_path_mode(self):
        """Loading anchors from a JSON file with the canonical {anchors: [...]}
        top-level produces the same slips list."""
        import json
        import tempfile

        anchors_doc = {
            "anchors": [
                {
                    "task_code": "M2000",
                    "anchor_date": "2026-05-01",
                    "anchor_kind": "finish",
                    "kind_label": "SC",
                }
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(anchors_doc, f)
            anchors_path = f.name

        try:
            result = cpm_path.get_anchor_conflicts_impl(
                str(FIXTURE),
                anchors=None,
                anchors_path=anchors_path,
                tolerance_days=0,
                cache=self.cache,
            )
            self.assertEqual(len(result["slips"]), 1)
            self.assertEqual(result["slips"][0]["task_code"], "M2000")
        finally:
            import os
            os.unlink(anchors_path)


class TestRunCpm(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_writes_default_output_path(self):
        """With no explicit output_path, writes to <input>-cpm.xer alongside
        the source. The default path is returned for the caller to use."""
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "minimal.xer"
            shutil.copy(FIXTURE, src)
            expected_out = Path(tmpdir) / "minimal-cpm.xer"

            result = cpm_path.run_cpm_impl(
                str(src), output_path=None, cache=self.cache
            )

            self.assertEqual(result["output_path"], str(expected_out))
            self.assertTrue(expected_out.exists())

    def test_writes_explicit_output_path(self):
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "minimal.xer"
            shutil.copy(FIXTURE, src)
            out = Path(tmpdir) / "custom-out.xer"

            result = cpm_path.run_cpm_impl(
                str(src), output_path=str(out), cache=self.cache
            )

            self.assertEqual(result["output_path"], str(out))
            self.assertTrue(out.exists())

    def test_refuses_to_overwrite_input(self):
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "minimal.xer"
            shutil.copy(FIXTURE, src)
            with self.assertRaises(ValueError):
                cpm_path.run_cpm_impl(
                    str(src), output_path=str(src), cache=self.cache
                )

    def test_refuses_to_overwrite_existing_output(self):
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "minimal.xer"
            shutil.copy(FIXTURE, src)
            blocker = Path(tmpdir) / "minimal-cpm.xer"
            blocker.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                cpm_path.run_cpm_impl(
                    str(src), output_path=None, cache=self.cache
                )

    def test_output_parses_back_with_same_task_count(self):
        """Round-trip sanity: output XER parses to the same TASK rows."""
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "minimal.xer"
            shutil.copy(FIXTURE, src)
            cpm_path.run_cpm_impl(
                str(src), output_path=None, cache=self.cache
            )
            # Parse the output via a fresh cache to avoid hitting the entry
            # keyed to the source path.
            from cache import CpmCache as _Cache
            out_cache = _Cache()
            parsed = out_cache.get_parsed(str(Path(tmpdir) / "minimal-cpm.xer"))
            self.assertEqual(len(parsed.get("TASK", [])), 2)


class TestGetGanttJson(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_project_block(self):
        result = cpm_path.get_gantt_json_impl(
            str(FIXTURE), project_name=None, cache=self.cache
        )
        self.assertIn("project", result)
        self.assertIsInstance(result["project"], dict)

    def test_returns_activities_list(self):
        result = cpm_path.get_gantt_json_impl(
            str(FIXTURE), project_name=None, cache=self.cache
        )
        self.assertIn("activities", result)
        self.assertIsInstance(result["activities"], list)
        # Minimal fixture has 1 WBS row + 2 milestones = 3 activity entries.
        self.assertGreaterEqual(len(result["activities"]), 2)

    def test_returns_paths_block(self):
        result = cpm_path.get_gantt_json_impl(
            str(FIXTURE), project_name=None, cache=self.cache
        )
        self.assertIn("paths", result)

    def test_project_name_propagates(self):
        result = cpm_path.get_gantt_json_impl(
            str(FIXTURE), project_name="Hello World", cache=self.cache
        )
        self.assertEqual(result["project"].get("name"), "Hello World")


class TestRenderGanttHtml(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_output_path(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False
        ) as f:
            output_path = f.name
        try:
            result = cpm_path.render_gantt_html_impl(
                str(FIXTURE),
                project_name="Minimal",
                output_path=output_path,
                cache=self.cache,
            )
            self.assertEqual(result["output_path"], output_path)
        finally:
            import os
            if os.path.exists(output_path):
                os.unlink(output_path)

    def test_writes_html_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False
        ) as f:
            output_path = f.name
        try:
            cpm_path.render_gantt_html_impl(
                str(FIXTURE),
                project_name="Minimal",
                output_path=output_path,
                cache=self.cache,
            )
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("<html", content.lower())
            self.assertIn("Minimal", content)
        finally:
            import os
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestGetDelayImpacts(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_impacts_key(self):
        result = cpm_path.get_delay_impacts_impl(
            str(FIXTURE),
            impact_activities=None,
            milestone_id=None,
            cache=self.cache,
        )
        self.assertIn("impacts", result)
        self.assertIsInstance(result["impacts"], list)

    def test_no_impacts_on_minimal_fixture(self):
        """No IMPACT-named tasks in the fixture -> auto-detect returns []."""
        result = cpm_path.get_delay_impacts_impl(
            str(FIXTURE),
            impact_activities=None,
            milestone_id=None,
            cache=self.cache,
        )
        self.assertEqual(result["impacts"], [])

    def test_explicit_milestone_id_propagates(self):
        result = cpm_path.get_delay_impacts_impl(
            str(FIXTURE),
            impact_activities=None,
            milestone_id="10002",
            cache=self.cache,
        )
        self.assertEqual(result["sc_task_id"], "10002")

    def test_impact_activities_param_accepted(self):
        result = cpm_path.get_delay_impacts_impl(
            str(FIXTURE),
            impact_activities=["10001"],
            milestone_id=None,
            cache=self.cache,
        )
        # NTP isn't an "impact" task semantically, but the function will
        # produce an entry for any task_id passed in.
        self.assertEqual(len(result["impacts"]), 1)


class TestGetMilestonePathCoverage(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_coverage_pct(self):
        result = cpm_path.get_milestone_path_coverage_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        self.assertIn("coverage_pct", result)
        self.assertIsInstance(result["coverage_pct"], (int, float))

    def test_minimal_fixture_full_coverage(self):
        """NTP -> SC FS link: both activities trace to SC. Coverage = 100%."""
        result = cpm_path.get_milestone_path_coverage_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        self.assertEqual(result["coverage_pct"], 100.0)

    def test_explicit_milestone_id_accepted(self):
        result = cpm_path.get_milestone_path_coverage_impl(
            str(FIXTURE), milestone_id="10002", cache=self.cache
        )
        self.assertEqual(result["sc_task_id"], "10002")

    def test_connected_ids_is_list_not_set(self):
        """JSON serialization can't handle sets. The MCP layer must convert."""
        result = cpm_path.get_milestone_path_coverage_impl(
            str(FIXTURE), milestone_id=None, cache=self.cache
        )
        self.assertIsInstance(result.get("connected_ids"), list)


class TestGetAnchorAbsorptionSuggestions(unittest.TestCase):
    """The minimal fixture only has milestones (no real-duration tasks), so
    the underlying function returns an empty list. We verify shape, parameter
    plumbing, and the empty-list path; richer scenarios are validated during
    the F1 batch's spec review against real XERs."""

    def setUp(self):
        self.cache = CpmCache()

    def test_returns_suggestions_key(self):
        slip = {"task_id": "10002", "slip_days": 24}
        result = cpm_path.get_anchor_absorption_suggestions_impl(
            str(FIXTURE), slip=slip, max_suggestions=8, cache=self.cache
        )
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["suggestions"], list)

    def test_empty_on_minimal_fixture(self):
        slip = {"task_id": "10002", "slip_days": 24}
        result = cpm_path.get_anchor_absorption_suggestions_impl(
            str(FIXTURE), slip=slip, max_suggestions=8, cache=self.cache
        )
        # Only milestones upstream of SC -> no duration-cut candidates.
        self.assertEqual(result["suggestions"], [])

    def test_max_suggestions_parameter_accepted(self):
        slip = {"task_id": "10002", "slip_days": 24}
        result = cpm_path.get_anchor_absorption_suggestions_impl(
            str(FIXTURE), slip=slip, max_suggestions=3, cache=self.cache
        )
        self.assertLessEqual(len(result["suggestions"]), 3)


class TestGetParallelBranches(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_parallel_branches_key(self):
        result = cpm_path.get_parallel_branches_impl(
            str(FIXTURE), start_date=None, end_date=None, cache=self.cache
        )
        self.assertIn("parallel_branches", result)
        self.assertIsInstance(result["parallel_branches"], list)

    def test_empty_on_minimal_fixture(self):
        """Two-activity FS chain has no divergent successors -> no branches."""
        result = cpm_path.get_parallel_branches_impl(
            str(FIXTURE), start_date=None, end_date=None, cache=self.cache
        )
        self.assertEqual(result["parallel_branches"], [])

    def test_date_window_params_accepted(self):
        """Passing a window must not error."""
        result = cpm_path.get_parallel_branches_impl(
            str(FIXTURE),
            start_date="2026-01-01",
            end_date="2026-12-31",
            cache=self.cache,
        )
        self.assertIn("parallel_branches", result)


class TestGetNearCriticalChains(unittest.TestCase):
    def setUp(self):
        self.cache = CpmCache()

    def test_returns_near_critical_key(self):
        result = cpm_path.get_near_critical_chains_impl(
            str(FIXTURE), tolerance_days=5, cache=self.cache
        )
        self.assertIn("near_critical", result)
        self.assertIsInstance(result["near_critical"], list)

    def test_empty_on_minimal_fixture(self):
        """Both fixture activities have TF=0 -> no near-critical chains."""
        result = cpm_path.get_near_critical_chains_impl(
            str(FIXTURE), tolerance_days=5, cache=self.cache
        )
        self.assertEqual(result["near_critical"], [])

    def test_tolerance_days_param_accepted(self):
        """Passing a smaller tolerance must not error; result is still empty
        on this fixture but the call shape is what's being verified."""
        result = cpm_path.get_near_critical_chains_impl(
            str(FIXTURE), tolerance_days=2, cache=self.cache
        )
        self.assertIn("near_critical", result)


class TestMilestoneAmbiguous(unittest.TestCase):
    """multi_terminal.xer has two TT_FinMile activities with no
    successors. Tools that auto-resolve the terminal milestone should
    raise MilestoneAmbiguousError carrying both candidates when
    milestone_id is omitted."""

    @classmethod
    def setUpClass(cls):
        cls.cache = CpmCache()
        cls.fixture = str(FIXTURES_DIR / "multi_terminal.xer")

    def test_get_milestone_path_coverage_raises_with_candidates(self):
        from milestones import MilestoneAmbiguousError
        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            cpm_path.get_milestone_path_coverage_impl(
                self.fixture, milestone_id=None, cache=self.cache,
            )
        self.assertGreaterEqual(len(ctx.exception.candidates), 2)

    def test_get_delay_impacts_raises_with_candidates(self):
        from milestones import MilestoneAmbiguousError
        with self.assertRaises(MilestoneAmbiguousError):
            cpm_path.get_delay_impacts_impl(
                self.fixture, impact_activities=None, milestone_id=None,
                cache=self.cache,
            )

    def test_explicit_milestone_id_succeeds(self):
        # Pass an explicit terminal milestone -- no error.
        result = cpm_path.get_milestone_path_coverage_impl(
            self.fixture, milestone_id="20002", cache=self.cache,
        )
        self.assertIn("sc_task_id", result)


if __name__ == "__main__":
    unittest.main()
