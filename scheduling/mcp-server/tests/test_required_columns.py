"""Regression tests for the P6 import crash (Event Code AVAA0-1866-2).

Root cause: the apply-path row builders (_append_new_task / _handle_add_wbs in
lib/xer_modify.py) created TASK and PROJWBS rows with only a subset of columns
populated, leaving P6-required NOT-NULL scalar columns (bit flags, enums,
quantity decimals, the OBS pointer, EV settings) EMPTY.  Primavera P6
access-violates on import when it dereferences those empties.  The internal
xer_validate was blind to this and reported import_ready=True on every crasher.

These tests pin both halves of the fix:
  1. xer_validate flags incomplete TASK/PROJWBS rows as errors (import_ready
     becomes False) — so a non-importable file can never be rubber-stamped.
  2. Every activity/WBS node the add-handlers generate is fully populated.

Verified against a real, P6-importable Westland export (BTLP.xer): every one of
these columns is populated on all 43 tasks and all 9 WBS nodes, so the guard
does not false-flag genuine exports.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools.xer_modify import apply_xer_changes_impl, create_xer_from_template_impl  # noqa: E402

LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from xer_io import XerDoc, XerSection, parse_for_writing  # noqa: E402
import xer_validate  # noqa: E402

SKELETON_NAME = "westland-skeleton-v1"

_METADATA = {
    "project_name": "Required Columns Test",
    "project_id": "RCT-001",
    "planned_start": "2026-09-01",
    "planned_data_date": "2026-09-01",
}

# One add_wbs + one add_activity + one connecting edge — the minimal reproduction
# of a downstream-generated node and activity.
_CHANGES = [
    {
        "type": "add_wbs",
        "spec": {
            "wbs_code": "TESTNODE",
            "wbs_name": "TEST NODE",
            "wbs_short_name": "TSTNODE",
            "parent_wbs_id": "1",
        },
    },
    {
        "type": "add_activity",
        "spec": {
            "code": "TEST-1010",
            "name": "Test Activity",
            "duration_days": 5,
            "calendar_id": "18261",
            "wbs_id": "22",  # the node added just above (skeleton max wbs_id is 21)
            "activity_type": "TT_Task",
        },
    },
    {
        "type": "add_logic",
        "predecessor_id": "MILESTONE-SC",
        "successor_id": "TEST-1010",
        "relationship": "FS",
        "lag_days": 0,
    },
]


def _make_section(name, field_order, rows):
    """Build an XerSection with raw_lines=None so every row is treated as dirty
    (reconstructed from the dict) — matches how create_from_template builds new
    sections."""
    return XerSection(
        name=name,
        field_order=list(field_order),
        rows=[dict(r) for r in rows],
        raw_lines=None,
        e_line=None,
    )


class TestValidatorFlagsIncompleteRows(unittest.TestCase):
    """xer_validate must flag rows with empty P6-required columns as errors."""

    def _doc_with_task_rows(self, rows):
        task = _make_section("TASK", xer_validate.REQUIRED_TASK_COLUMNS + ("task_id", "task_code", "task_name"), rows)
        return XerDoc(header_line="ERMHDR", encoding="cp1252", sections=[task])

    def test_complete_task_rows_pass(self):
        """A row that fills every required column produces no INCOMPLETE_TASK_ROW."""
        complete = {c: "0" for c in xer_validate.REQUIRED_TASK_COLUMNS}
        complete.update({
            "task_id": "1", "task_code": "A1000", "task_name": "Alpha",
            "task_type": "TT_Task", "status_code": "TK_NotStart",
            "complete_pct_type": "CP_Drtn", "duration_type": "DT_FixedDUR2",
            "rev_fdbk_flag": "N", "lock_plan_flag": "N", "auto_compute_act_flag": "N",
            "priority_type": "PT_Normal", "proj_id": "P1", "wbs_id": "1", "clndr_id": "1",
        })
        report = xer_validate.validate(self._doc_with_task_rows([complete]))
        codes = [i.code for i in report.issues]
        self.assertNotIn("INCOMPLETE_TASK_ROW", codes)

    def test_incomplete_task_row_flagged_as_error(self):
        """A row missing required columns that a sibling populates is an error."""
        complete = {c: "0" for c in xer_validate.REQUIRED_TASK_COLUMNS}
        complete.update({
            "task_id": "1", "task_code": "A1000", "task_name": "Alpha",
            "task_type": "TT_Task", "status_code": "TK_NotStart",
            "complete_pct_type": "CP_Drtn", "duration_type": "DT_FixedDUR2",
            "rev_fdbk_flag": "N", "lock_plan_flag": "N", "auto_compute_act_flag": "N",
            "priority_type": "PT_Normal", "proj_id": "P1", "wbs_id": "1", "clndr_id": "1",
        })
        # Second row leaves the required flags/quantities empty (the bug's signature).
        incomplete = dict(complete)
        incomplete.update({
            "task_id": "2", "task_code": "A2000", "task_name": "Bravo",
            "rev_fdbk_flag": "", "lock_plan_flag": "", "auto_compute_act_flag": "",
            "priority_type": "", "act_work_qty": "", "remain_work_qty": "",
            "target_work_qty": "", "act_equip_qty": "", "remain_equip_qty": "",
            "target_equip_qty": "",
        })
        report = xer_validate.validate(self._doc_with_task_rows([complete, incomplete]))
        errors = [i for i in report.issues if i.severity == "error" and i.code == "INCOMPLETE_TASK_ROW"]
        self.assertTrue(errors, "expected an INCOMPLETE_TASK_ROW error")
        self.assertIn("2", errors[0].affected)
        self.assertFalse(report.import_ready)

    def test_incomplete_wbs_row_flagged_as_error(self):
        cols = xer_validate.REQUIRED_WBS_COLUMNS + ("wbs_id", "wbs_short_name", "wbs_name", "parent_wbs_id")
        complete = {c: "1" for c in cols}
        complete.update({
            "wbs_id": "1", "wbs_short_name": "ROOT", "wbs_name": "ROOT",
            "proj_node_flag": "Y", "sum_data_flag": "N", "status_code": "WS_Open",
            "ev_compute_type": "EC_Cmp_pct", "ev_etc_compute_type": "EE_PF_cpi",
            "parent_wbs_id": "",
        })
        incomplete = dict(complete)
        incomplete.update({
            "wbs_id": "2", "wbs_short_name": "CHILD", "wbs_name": "CHILD",
            "parent_wbs_id": "1",
            "obs_id": "", "proj_node_flag": "", "sum_data_flag": "",
            "ev_compute_type": "", "ev_etc_compute_type": "", "seq_num": "",
        })
        wbs = _make_section("PROJWBS", cols, [complete, incomplete])
        doc = XerDoc(header_line="ERMHDR", encoding="cp1252", sections=[wbs])
        report = xer_validate.validate(doc)
        errors = [i for i in report.issues if i.severity == "error" and i.code == "INCOMPLETE_WBS_ROW"]
        self.assertTrue(errors, "expected an INCOMPLETE_WBS_ROW error")
        self.assertIn("2", errors[0].affected)
        self.assertFalse(report.import_ready)


class TestGeneratedRowsFullyPopulated(unittest.TestCase):
    """Every activity/WBS node the add-handlers create must fill P6-required columns."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()
        self.proj_xer = os.path.join(self.tmpdir, "proj.xer")
        self.proj_b_xer = os.path.join(self.tmpdir, "proj-b.xer")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build(self):
        create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.proj_xer, cache=self.cache
        )
        apply_xer_changes_impl(
            self.proj_xer, _CHANGES, output_path=self.proj_b_xer,
            strict=False, dry_run=False, cache=self.cache,
        )
        return parse_for_writing(self.proj_b_xer)

    def test_added_activity_has_no_empty_required_columns(self):
        doc = self._build()
        task = doc.section("TASK")
        added = [r for r in task.rows if r.get("task_code") == "TEST-1010"]
        self.assertEqual(len(added), 1, "the added activity must be present")
        row = added[0]
        empty = [c for c in xer_validate.REQUIRED_TASK_COLUMNS if not str(row.get(c, "")).strip()]
        self.assertEqual(empty, [], f"added activity left required columns empty: {empty}")

    def test_added_wbs_node_has_no_empty_required_columns(self):
        doc = self._build()
        wbs = doc.section("PROJWBS")
        added = [r for r in wbs.rows if r.get("wbs_name") == "TEST NODE"]
        self.assertEqual(len(added), 1, "the added WBS node must be present")
        row = added[0]
        empty = [c for c in xer_validate.REQUIRED_WBS_COLUMNS if not str(row.get(c, "")).strip()]
        self.assertEqual(empty, [], f"added WBS node left required columns empty: {empty}")
        # OBS pointer must reference an OBS row that exists in the file.
        obs = doc.section("OBS")
        obs_ids = {r.get("obs_id") for r in obs.rows} if obs else set()
        self.assertIn(row.get("obs_id"), obs_ids, "added WBS obs_id must resolve to an OBS row")

    def test_generated_file_is_import_ready(self):
        """The whole point: a generated proposal schedule validates import_ready."""
        self._build()
        report = xer_validate.validate(self.cache.get_for_writing(self.proj_b_xer))
        errors = [i for i in report.issues if i.severity == "error"]
        self.assertEqual(errors, [], f"generated file has errors: {[(e.code, e.message) for e in errors]}")
        self.assertTrue(report.import_ready)


class TestCleanSkeletonNotFalseFlagged(unittest.TestCase):
    """The bare skeleton (all rows fully populated) must stay import_ready."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()
        self.output_path = os.path.join(self.tmpdir, "output.xer")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_bare_skeleton_import_ready(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        self.assertTrue(
            result["validation"]["import_ready"],
            "the bare skeleton must not be flagged by the incomplete-column guard",
        )


class TestCreatePathGate(unittest.TestCase):
    """create_xer_from_template validates BEFORE writing and refuses to persist a
    file that would fail P6 import (mirrors the apply-path Pass-3 gate)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()
        self.output_path = os.path.join(self.tmpdir, "gated.xer")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_refuses_to_write_when_validation_fails(self):
        import tools.xer_modify as txm

        real_validate = txm.xer_validate.validate

        class _Issue:
            severity = "error"
            code = "SYNTHETIC"
            message = "synthetic failure"

        class _Report:
            import_ready = False
            issues = [_Issue()]
            summary = {"errors": 1, "warnings": 0, "info": 0}

        txm.xer_validate.validate = lambda doc: _Report()
        try:
            with self.assertRaises(Exception):
                txm.create_xer_from_template_impl(
                    SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
                )
            # The malformed file must NOT have been written to disk.
            self.assertFalse(os.path.exists(self.output_path))
        finally:
            txm.xer_validate.validate = real_validate


class TestGuardCoverageExtensions(unittest.TestCase):
    """The integer-id and bare-datetime guards cover the activity-code tables and
    all datetime columns in the derived schema."""

    def test_actvcode_taskactv_covered_by_integer_id_guard(self):
        self.assertIn("ACTVCODE", xer_validate._INTEGER_ID_COLUMNS)
        self.assertIn("TASKACTV", xer_validate._INTEGER_ID_COLUMNS)
        actvcode = _make_section(
            "ACTVCODE", ("actv_code_id", "actv_code_type_id", "short_name"),
            [{"actv_code_id": "NOTNUM", "actv_code_type_id": "10309", "short_name": "ELEC"}],
        )
        doc = XerDoc(header_line="ERMHDR", encoding="cp1252", sections=[actvcode])
        codes = [i.code for i in xer_validate.validate(doc).issues if i.severity == "error"]
        self.assertIn("NON_NUMERIC_ID", codes)

    def test_audit_dates_covered_by_bare_datetime_guard(self):
        for col in ("create_date", "update_date"):
            self.assertIn(col, xer_validate._DATE_FIELDS)
        for col in ("add_date", "sum_refresh_date"):
            self.assertIn(col, xer_validate._PROJECT_DATE_FIELDS)


class TestDatetimeNormalization(unittest.TestCase):
    """create_from_template must stamp full 'YYYY-MM-DD HH:MM' datetimes.

    A bare 'YYYY-MM-DD' data date crashed P6 import (AVAA0-1866-2) and was
    rejected by SmartPM ('Unsupported datetime format: 2026-08-03').  Only
    planned_start was normalized historically; planned_data_date shipped bare
    into PROJECT.last_recalc_date.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()
        self.output_path = os.path.join(self.tmpdir, "output.xer")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_data_date_gets_time_component(self):
        md = {
            "project_name": "DT Test", "project_id": "DTT-001",
            "planned_start": "2026-08-03", "planned_data_date": "2026-08-03",
        }
        create_xer_from_template_impl(SKELETON_NAME, md, output_path=self.output_path, cache=self.cache)
        proj = parse_for_writing(self.output_path).section("PROJECT").rows[0]
        self.assertEqual(proj["plan_start_date"], "2026-08-03 08:00")
        self.assertEqual(
            proj["last_recalc_date"], "2026-08-03 08:00",
            "planned_data_date must be normalized to a full datetime (was shipping bare)",
        )

    def test_validator_flags_bare_datetime(self):
        """A bare PROJECT date is a MALFORMED_DATETIME error -> not import_ready."""
        cols = ("proj_id", "clndr_id", "last_recalc_date", "plan_start_date")
        proj = _make_section("PROJECT", cols, [{
            "proj_id": "P1", "clndr_id": "1",
            "last_recalc_date": "2026-08-03",       # bare -> should be flagged
            "plan_start_date": "2026-08-03 08:00",  # ok
        }])
        report = xer_validate.validate(XerDoc(header_line="ERMHDR", encoding="cp1252", sections=[proj]))
        codes = [i.code for i in report.issues if i.severity == "error"]
        self.assertIn("MALFORMED_DATETIME", codes)
        self.assertFalse(report.import_ready)


if __name__ == "__main__":
    unittest.main()
