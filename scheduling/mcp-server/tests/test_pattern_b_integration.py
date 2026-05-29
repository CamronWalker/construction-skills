"""End-to-end integration test: skeleton -> Pattern B proposal schedule.

Flow:
  1. create_xer_from_template_impl  - instantiate westland-skeleton-v1
  2. apply_xer_changes_impl         - apply the Pattern B change set
  3. validate_xer_structure_impl    - assert import_ready True
  4. Structural property assertions - parse output XER, verify WBS tree shape

Note on target fixture:
  The plan mentioned a hand-curated wbs_pattern_b_target.xer for byte comparison.
  We intentionally skip that approach.  Byte-comparing a hand-built target couples
  the test to exact id assignment and field-order details that have no bearing on
  correctness.  Structural-property assertions (WBS tree shape, activity count,
  logic count) test the same integration value robustly without the brittleness.

WBS id assignment prediction (verified by reading _handle_add_wbs in xer_modify.py):
  _handle_add_wbs assigns new_wbs_id = str(max(existing projwbs rows) + 1).
  Each add_wbs appends its new row immediately, so each subsequent call sees the
  prior row and the max climbs by 1.  The skeleton's max wbs_id is 21, so:
    Record 0: DEMOLITION (parent="1")           -> wbs_id 22
    Record 1: HAZMAT ABATEMENT (parent="22")    -> 23
    Record 2: UTILITY DISCONNECT (parent="22")  -> 24
    Record 3: BUILDING DEMO (parent="22")       -> 25
    Record 4: GRUB (parent="22")                -> 26
    Record 5: FINAL SITEWORK (parent="22")      -> 27
    Record 6: INITIAL SITEWORK (parent="27")    -> 28
    Record 7: BALANCE OF SITEWORK (parent="27") -> 29
    Record 8: SITEWORK COMPLETION (parent="27") -> 30
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Make mcp-server modules importable.
SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools.xer_modify import apply_xer_changes_impl, create_xer_from_template_impl  # noqa: E402
from tools.xer_validate import validate_xer_structure_impl  # noqa: E402

LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from xer_io import parse_for_writing  # noqa: E402

SKELETON_NAME = "westland-skeleton-v1"

_METADATA = {
    "project_name": "Pattern B Integration Test",
    "project_id": "PTB-001",
    "planned_start": "2026-09-01",
    "planned_data_date": "2026-09-01",
}

# Calendar ID from the skeleton's Standard calendar.
_CALENDAR_ID = "18261"

# WBS id predictions derived from the skeleton's max wbs_id of 21.
# These are used both in the change set below and in structural assertions.
_WBS_DEMOLITION = "22"
_WBS_HAZMAT = "23"
_WBS_UTIL_DISC = "24"
_WBS_BLDG_DEMO = "25"
_WBS_GRUB = "26"
_WBS_FINAL_SITE = "27"
_WBS_INIT_SITE = "28"
_WBS_BAL_SITE = "29"
_WBS_SITE_COMP = "30"

# Pattern B change set.  Order: all add_wbs first, then add_activity, then add_logic.
# This ordering is required so that:
#   - add_activity wbs_id validation can find the new WBS nodes in state.new_wbs_ids
#   - add_logic endpoint validation can find new activities in state.new_activity_id_map
_PATTERN_B_CHANGES = [
    # --- add_wbs (9 nodes) ---
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO",
            "wbs_name": "DEMOLITION",
            "wbs_short_name": "DEMO",
            "parent_wbs_id": "1",
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.HAZMAT",
            "wbs_name": "HAZMAT ABATEMENT",
            "wbs_short_name": "HAZMAT",
            "parent_wbs_id": _WBS_DEMOLITION,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.UTILDISC",
            "wbs_name": "UTILITY DISCONNECT",
            "wbs_short_name": "UTILDISC",
            "parent_wbs_id": _WBS_DEMOLITION,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.BLDGDEMO",
            "wbs_name": "BUILDING DEMO",
            "wbs_short_name": "BLDGDEMO",
            "parent_wbs_id": _WBS_DEMOLITION,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.GRUB",
            "wbs_name": "GRUB",
            "wbs_short_name": "GRUB",
            "parent_wbs_id": _WBS_DEMOLITION,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.FINSITE",
            "wbs_name": "FINAL SITEWORK",
            "wbs_short_name": "FINSITE",
            "parent_wbs_id": _WBS_DEMOLITION,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.FINSITE.INIT",
            "wbs_name": "INITIAL SITEWORK",
            "wbs_short_name": "INITSITE",
            "parent_wbs_id": _WBS_FINAL_SITE,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.FINSITE.BAL",
            "wbs_name": "BALANCE OF SITEWORK",
            "wbs_short_name": "BALSITE",
            "parent_wbs_id": _WBS_FINAL_SITE,
        },
    },
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "DEMO.FINSITE.COMP",
            "wbs_name": "SITEWORK COMPLETION",
            "wbs_short_name": "SITECOMP",
            "parent_wbs_id": _WBS_FINAL_SITE,
        },
    },
    # --- add_activity (8 activities) ---
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-1010",
            "name": "Hazmat Survey & Abatement",
            "duration_days": 10,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_HAZMAT,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-1020",
            "name": "Utility Disconnect & Cap",
            "duration_days": 5,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_UTIL_DISC,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-1030",
            "name": "Demo Main Building",
            "duration_days": 15,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_BLDG_DEMO,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-1040",
            "name": "Demo Annex",
            "duration_days": 8,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_BLDG_DEMO,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-1050",
            "name": "Grub & Clear Site",
            "duration_days": 5,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_GRUB,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-2010",
            "name": "Initial Sitework - Grading & Drainage",
            "duration_days": 12,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_INIT_SITE,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-2020",
            "name": "Balance of Sitework - Paving & Curbs",
            "duration_days": 10,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_BAL_SITE,
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "DEMO-2030",
            "name": "Sitework Completion - Landscaping & Cleanup",
            "duration_days": 7,
            "calendar_id": _CALENDAR_ID,
            "wbs_id": _WBS_SITE_COMP,
            "activity_type": "TT_Task",
        },
    },
    # --- add_logic (9 edges) ---
    # MILESTONE-SC -> DEMO-1010 (demo begins after substantial completion gate)
    {
        "type": "add_logic",
        "predecessor_id": "MILESTONE-SC",
        "successor_id": "DEMO-1010",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Hazmat -> Utility Disconnect
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-1010",
        "successor_id": "DEMO-1020",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Hazmat -> Building Demo (both start after hazmat)
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-1010",
        "successor_id": "DEMO-1030",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Building Demo (main) -> Demo Annex
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-1030",
        "successor_id": "DEMO-1040",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Utility Disconnect -> Grub
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-1020",
        "successor_id": "DEMO-1050",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Demo Annex -> Grub
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-1040",
        "successor_id": "DEMO-1050",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Grub -> Initial Sitework
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-1050",
        "successor_id": "DEMO-2010",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Initial Sitework -> Balance of Sitework
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-2010",
        "successor_id": "DEMO-2020",
        "relationship": "FS",
        "lag_days": 0,
    },
    # Balance of Sitework -> Sitework Completion
    {
        "type": "add_logic",
        "predecessor_id": "DEMO-2020",
        "successor_id": "DEMO-2030",
        "relationship": "FS",
        "lag_days": 0,
    },
]

# Expected counts after apply.
_ORIGINAL_TASK_COUNT = 2       # MILESTONE-NTP, MILESTONE-SC
_ADDED_ACTIVITY_COUNT = 8
_EXPECTED_TASK_COUNT = _ORIGINAL_TASK_COUNT + _ADDED_ACTIVITY_COUNT

_ORIGINAL_PRED_COUNT = 1       # NTP -> SC edge in skeleton
_ADDED_LOGIC_COUNT = 9
_EXPECTED_PRED_COUNT = _ORIGINAL_PRED_COUNT + _ADDED_LOGIC_COUNT


class TestPatternBIntegration(unittest.TestCase):
    """End-to-end: skeleton -> Pattern B -> valid importable XER."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()
        self.proj_xer = os.path.join(self.tmpdir, "proj.xer")
        self.proj_b_xer = os.path.join(self.tmpdir, "proj-b.xer")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Step 1 helpers
    # ------------------------------------------------------------------

    def _step1_create(self):
        """Run create_xer_from_template_impl; return its result dict."""
        return create_xer_from_template_impl(
            SKELETON_NAME,
            _METADATA,
            output_path=self.proj_xer,
            cache=self.cache,
        )

    # ------------------------------------------------------------------
    # Step 2 helpers
    # ------------------------------------------------------------------

    def _step2_apply(self):
        """Run apply_xer_changes_impl; return its result dict."""
        return apply_xer_changes_impl(
            self.proj_xer,
            _PATTERN_B_CHANGES,
            output_path=self.proj_b_xer,
            strict=False,
            dry_run=False,
            cache=self.cache,
        )

    # ------------------------------------------------------------------
    # Step 3 helper
    # ------------------------------------------------------------------

    def _step3_validate(self):
        """Run validate_xer_structure_impl; return its result dict."""
        return validate_xer_structure_impl(self.proj_b_xer, self.cache)

    # ------------------------------------------------------------------
    # Main integration test
    # ------------------------------------------------------------------

    def test_full_pattern_b_flow(self):
        """The full three-step flow produces a valid, structurally correct XER."""

        # Step 1: instantiate the skeleton.
        create_result = self._step1_create()
        self.assertIsNotNone(create_result["output_path"])
        self.assertTrue(os.path.exists(self.proj_xer), "proj.xer must be on disk before apply")
        self.assertTrue(
            create_result["validation"]["import_ready"],
            "Skeleton should be import_ready before any changes",
        )

        # Step 2: apply Pattern B changes.
        apply_result = self._step2_apply()

        # No validation errors — all changes should apply.
        errors = apply_result["summary"]["validation_errors"]
        self.assertEqual(
            errors,
            [],
            f"apply_xer_changes produced unexpected errors: {errors}",
        )
        self.assertIsNotNone(
            apply_result["output_path"],
            "apply_xer_changes must write proj-b.xer",
        )
        self.assertTrue(os.path.exists(self.proj_b_xer))

        # All changes (9 wbs + 8 activities + 9 logic = 26) applied.
        expected_changes = (
            len([c for c in _PATTERN_B_CHANGES if c["type"] == "add_wbs"])
            + len([c for c in _PATTERN_B_CHANGES if c["type"] == "add_activity"])
            + len([c for c in _PATTERN_B_CHANGES if c["type"] == "add_logic"])
        )
        self.assertEqual(apply_result["summary"]["changes_applied"], expected_changes)

        # Step 3: validate the output XER.
        val_result = self._step3_validate()
        error_issues = [i for i in val_result["issues"] if i["severity"] == "error"]
        self.assertEqual(
            error_issues,
            [],
            f"validate_xer_structure found error-severity issues: {error_issues}",
        )
        self.assertTrue(
            val_result["import_ready"],
            f"import_ready must be True; issues: {val_result['issues']}",
        )

        # Step 4: structural assertions on the output XER.
        doc = parse_for_writing(self.proj_b_xer)
        projwbs = doc.section("PROJWBS")
        task_section = doc.section("TASK")
        taskpred = doc.section("TASKPRED")

        self.assertIsNotNone(projwbs)
        self.assertIsNotNone(task_section)
        self.assertIsNotNone(taskpred)

        wbs_by_id = {r["wbs_id"]: r for r in projwbs.rows}
        wbs_by_name = {r["wbs_name"]: r for r in projwbs.rows}

        # DEMOLITION is a top-level node directly under PROJECT root (wbs_id "1").
        self.assertIn("DEMOLITION", wbs_by_name, "DEMOLITION WBS node must exist")
        demo_node = wbs_by_name["DEMOLITION"]
        self.assertEqual(
            demo_node["parent_wbs_id"],
            "1",
            "DEMOLITION must be a direct child of the PROJECT root (wbs_id=1)",
        )
        demo_wbs_id = demo_node["wbs_id"]
        self.assertEqual(demo_wbs_id, _WBS_DEMOLITION, "DEMOLITION wbs_id must match prediction")

        # FINAL SITEWORK is nested under DEMOLITION.
        self.assertIn("FINAL SITEWORK", wbs_by_name)
        finsite_node = wbs_by_name["FINAL SITEWORK"]
        self.assertEqual(
            finsite_node["parent_wbs_id"],
            demo_wbs_id,
            "FINAL SITEWORK must be a child of DEMOLITION",
        )
        finsite_wbs_id = finsite_node["wbs_id"]
        self.assertEqual(finsite_wbs_id, _WBS_FINAL_SITE)

        # INITIAL SITEWORK, BALANCE OF SITEWORK, SITEWORK COMPLETION under FINAL SITEWORK.
        for child_name in ("INITIAL SITEWORK", "BALANCE OF SITEWORK", "SITEWORK COMPLETION"):
            self.assertIn(child_name, wbs_by_name, f"{child_name} must exist in PROJWBS")
            self.assertEqual(
                wbs_by_name[child_name]["parent_wbs_id"],
                finsite_wbs_id,
                f"{child_name} must be a child of FINAL SITEWORK",
            )

        # HAZMAT ABATEMENT, UTILITY DISCONNECT, BUILDING DEMO, GRUB are direct
        # children of DEMOLITION.
        for child_name in (
            "HAZMAT ABATEMENT",
            "UTILITY DISCONNECT",
            "BUILDING DEMO",
            "GRUB",
        ):
            self.assertIn(child_name, wbs_by_name, f"{child_name} must exist in PROJWBS")
            self.assertEqual(
                wbs_by_name[child_name]["parent_wbs_id"],
                demo_wbs_id,
                f"{child_name} must be a direct child of DEMOLITION",
            )

        # TASK count: original 2 + 8 demo activities.
        self.assertEqual(
            len(task_section.rows),
            _EXPECTED_TASK_COUNT,
            f"Expected {_EXPECTED_TASK_COUNT} TASK rows, got {len(task_section.rows)}",
        )

        # All demo activities are assigned to WBS nodes within the DEMOLITION subtree.
        demo_subtree_ids = {
            r["wbs_id"] for r in projwbs.rows
            if r["wbs_id"] == demo_wbs_id or r.get("parent_wbs_id") == demo_wbs_id
            or wbs_by_id.get(r.get("parent_wbs_id"), {}).get("parent_wbs_id") == demo_wbs_id
        }
        added_codes = {
            c["spec"]["code"]
            for c in _PATTERN_B_CHANGES
            if c["type"] == "add_activity"
        }
        for row in task_section.rows:
            if row["task_code"] in added_codes:
                self.assertIn(
                    row["wbs_id"],
                    demo_subtree_ids,
                    f"Activity {row['task_code']!r} wbs_id {row['wbs_id']!r} "
                    f"not in DEMOLITION subtree {demo_subtree_ids}",
                )

        # TASKPRED count: original 1 + 9 new logic edges.
        self.assertEqual(
            len(taskpred.rows),
            _EXPECTED_PRED_COUNT,
            f"Expected {_EXPECTED_PRED_COUNT} TASKPRED rows, got {len(taskpred.rows)}",
        )

    # ------------------------------------------------------------------
    # Individual step smoke tests (catch regressions in isolation)
    # ------------------------------------------------------------------

    def test_step1_skeleton_instantiation(self):
        """Step 1 alone: skeleton creates a valid XER with NTP+SC milestones."""
        result = self._step1_create()
        self.assertTrue(result["validation"]["import_ready"])
        self.assertIsNotNone(result["ntp_milestone"])
        self.assertIsNotNone(result["sc_milestone"])
        self.assertEqual(result["ntp_milestone"]["task_code"], "MILESTONE-NTP")
        self.assertEqual(result["sc_milestone"]["task_code"], "MILESTONE-SC")

    def test_step2_no_validation_errors(self):
        """Step 2 alone: apply produces zero error-severity results."""
        self._step1_create()
        result = self._step2_apply()
        self.assertEqual(result["summary"]["validation_errors"], [])

    def test_step3_import_ready(self):
        """Step 3 alone: validate confirms import_ready True after Pattern B."""
        self._step1_create()
        self._step2_apply()
        result = self._step3_validate()
        self.assertTrue(result["import_ready"])

    def test_wbs_id_prediction_holds(self):
        """Verify that wbs_id assignment matches the predicted values.

        This catches any change to the add_wbs id-generation algorithm that
        would invalidate the static parent_wbs_id references in the change set.
        """
        self._step1_create()
        apply_result = self._step2_apply()

        # Collect new_wbs_id from per_change_feedback for add_wbs records.
        add_wbs_feedback = [
            pcf["feedback"]
            for pcf in apply_result["per_change_feedback"]
            if pcf["type"] == "add_wbs"
        ]
        expected_ids = [
            _WBS_DEMOLITION,   # 22
            _WBS_HAZMAT,       # 23
            _WBS_UTIL_DISC,    # 24
            _WBS_BLDG_DEMO,    # 25
            _WBS_GRUB,         # 26
            _WBS_FINAL_SITE,   # 27
            _WBS_INIT_SITE,    # 28
            _WBS_BAL_SITE,     # 29
            _WBS_SITE_COMP,    # 30
        ]
        self.assertEqual(
            len(add_wbs_feedback),
            len(expected_ids),
            f"Expected {len(expected_ids)} add_wbs feedbacks, got {len(add_wbs_feedback)}",
        )
        for i, (fb, expected) in enumerate(zip(add_wbs_feedback, expected_ids)):
            self.assertEqual(
                fb["new_wbs_id"],
                expected,
                f"add_wbs record {i}: expected new_wbs_id={expected!r}, got {fb['new_wbs_id']!r}",
            )


if __name__ == "__main__":
    unittest.main()
