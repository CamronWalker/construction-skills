"""Unit tests for ``activity_roster.py`` — pure functions behind the four
activity-roster MCP tools (list_activities, get_activity, get_wbs_branch,
next_free_activity_code).

All tests run against synthetic table dicts (no XER files). The task dicts
carry CPM-computed date/float fields exactly as ``schedule_forward_backward``
would leave them, so the lib layer never has to know whether it's looking at
imported or computed values.
"""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from activity_roster import (  # noqa: E402
    build_day_hr_index,
    build_task_responsibility,
    build_wbs_path_index,
    branch_activities,
    expand_activity,
    next_free_code,
    resolve_responsibility_type,
    roster_rows,
)


# --- synthetic fixture -------------------------------------------------------

def _projwbs():
    # 1 (root) > 2 (Procurement) > 3 (Steel); 1 > 4 (Construction)
    return [
        {"wbs_id": "1", "parent_wbs_id": "", "proj_node_flag": "Y",
         "wbs_short_name": "CVMC", "wbs_name": "CVMC Nephi"},
        {"wbs_id": "2", "parent_wbs_id": "1", "proj_node_flag": "N",
         "wbs_short_name": "PROC", "wbs_name": "Procurement"},
        {"wbs_id": "3", "parent_wbs_id": "2", "proj_node_flag": "N",
         "wbs_short_name": "STL", "wbs_name": "Steel"},
        {"wbs_id": "4", "parent_wbs_id": "1", "proj_node_flag": "N",
         "wbs_short_name": "CONST", "wbs_name": "Construction"},
    ]


def _tasks():
    # CPM-computed fields present (early/late dates + total_float_hr_cnt).
    return [
        {"task_id": "101", "task_code": "CVMC-1000", "task_name": "Order Steel",
         "task_type": "TT_Task", "status_code": "TK_NotStart", "wbs_id": "3",
         "clndr_id": "100", "early_start_date": "2026-05-25 08:00",
         "early_end_date": "2026-06-01 17:00", "late_start_date": "2026-05-25 08:00",
         "late_end_date": "2026-06-01 17:00", "total_float_hr_cnt": "0"},
        {"task_id": "102", "task_code": "CVMC-1010", "task_name": "Fab Steel",
         "task_type": "TT_Task", "status_code": "TK_NotStart", "wbs_id": "3",
         "clndr_id": "100", "early_start_date": "2026-06-02 08:00",
         "early_end_date": "2026-06-10 17:00", "late_start_date": "2026-06-02 08:00",
         "late_end_date": "2026-06-10 17:00", "total_float_hr_cnt": "0"},
        {"task_id": "103", "task_code": "CVMC-2000", "task_name": "Pour Slab",
         "task_type": "TT_Task", "status_code": "TK_NotStart", "wbs_id": "4",
         "clndr_id": "100", "early_start_date": "2026-06-02 08:00",
         "early_end_date": "2026-06-15 17:00", "late_start_date": "2026-06-10 08:00",
         "late_end_date": "2026-06-23 17:00", "total_float_hr_cnt": "48"},
        {"task_id": "104", "task_code": "CVMC-8320", "task_name": "Substantial Completion",
         "task_type": "TT_FinMile", "status_code": "TK_NotStart", "wbs_id": "1",
         "clndr_id": "100", "early_start_date": "2026-06-15 17:00",
         "early_end_date": "2026-06-15 17:00", "late_start_date": "2026-06-23 17:00",
         "late_end_date": "2026-06-23 17:00", "total_float_hr_cnt": "48"},
        {"task_id": "105", "task_code": "CVMC-8300", "task_name": "Ready for Inspection",
         "task_type": "TT_Mile", "status_code": "TK_NotStart", "wbs_id": "4",
         "clndr_id": "100", "early_start_date": "2026-06-15 17:00",
         "early_end_date": "2026-06-15 17:00", "late_start_date": "2026-06-15 17:00",
         "late_end_date": "2026-06-15 17:00", "total_float_hr_cnt": "0"},
    ]


def _preds():
    return [
        {"task_pred_id": "1", "task_id": "102", "pred_task_id": "101",
         "pred_type": "PR_FS", "lag_hr_cnt": "0"},
        {"task_pred_id": "2", "task_id": "103", "pred_task_id": "102",
         "pred_type": "PR_SS", "lag_hr_cnt": "16"},   # 2 days @ 8h
        {"task_pred_id": "3", "task_id": "104", "pred_task_id": "103",
         "pred_type": "FS", "lag_hr_cnt": "0"},        # short-code variant
    ]


def _actvtype():
    return [
        # Global Responsibility is the one trade_filter should pick.
        {"actv_code_type_id": "50", "actv_code_type": "Responsibility",
         "actv_code_type_scope": "AS_Global"},
        # A project-scoped type also named Responsibility — global must win.
        {"actv_code_type_id": "52", "actv_code_type": "Responsibility",
         "actv_code_type_scope": "AS_Project"},
        {"actv_code_type_id": "51", "actv_code_type": "Phase",
         "actv_code_type_scope": "AS_Project"},
    ]


def _actvcode():
    return [
        {"actv_code_id": "900", "actv_code_type_id": "50",
         "short_name": "CONC", "actv_code_name": "Concrete"},
        {"actv_code_id": "901", "actv_code_type_id": "50",
         "short_name": "STL", "actv_code_name": "Steel Erection"},
    ]


def _taskactv():
    return [
        {"task_id": "101", "actv_code_type_id": "50", "actv_code_id": "901"},
        {"task_id": "102", "actv_code_type_id": "50", "actv_code_id": "901"},
        {"task_id": "103", "actv_code_type_id": "50", "actv_code_id": "900"},
        # 104, 105 unassigned -> responsibility None
    ]


def _calendars():
    return [{"clndr_id": "100", "day_hr_cnt": "8"}]


class TestWbsPathIndex(unittest.TestCase):
    def test_nested_path(self):
        idx = build_wbs_path_index(_projwbs())
        self.assertEqual(idx["3"], "CVMC Nephi > Procurement > Steel")
        self.assertEqual(idx["2"], "CVMC Nephi > Procurement")
        self.assertEqual(idx["1"], "CVMC Nephi")

    def test_cycle_guard(self):
        # A -> B -> A would infinite-loop a naive walker.
        rows = [
            {"wbs_id": "A", "parent_wbs_id": "B", "wbs_name": "Alpha"},
            {"wbs_id": "B", "parent_wbs_id": "A", "wbs_name": "Beta"},
        ]
        idx = build_wbs_path_index(rows)  # must not hang
        self.assertIn("A", idx)
        self.assertIn("Alpha", idx["A"])

    def test_missing_parent_terminates(self):
        rows = [{"wbs_id": "9", "parent_wbs_id": "does-not-exist", "wbs_name": "Orphan"}]
        idx = build_wbs_path_index(rows)
        self.assertEqual(idx["9"], "Orphan")


class TestResponsibility(unittest.TestCase):
    def test_prefers_global_responsibility(self):
        self.assertEqual(resolve_responsibility_type(_actvtype()), "50")

    def test_matches_responsibility_global_named_type(self):
        # Westland's real global type is literally named "Responsibility - Global".
        rows = [
            {"actv_code_type_id": "148", "actv_code_type": "Responsibility - Global",
             "actv_code_type_scope": "AS_Global"},
            {"actv_code_type_id": "200", "actv_code_type": "Responsibilty",
             "actv_code_type_scope": "AS_Project"},  # typo variant, project scope
        ]
        self.assertEqual(resolve_responsibility_type(rows), "148")

    def test_named_code_type_override(self):
        self.assertEqual(resolve_responsibility_type(_actvtype(), code_type="Phase"), "51")

    def test_none_when_absent(self):
        self.assertIsNone(resolve_responsibility_type([], None))
        self.assertIsNone(resolve_responsibility_type(_actvtype(), code_type="Nope"))

    def test_task_responsibility_map(self):
        resp = build_task_responsibility(_taskactv(), _actvcode(), "50")
        self.assertEqual(resp["101"], {"short": "STL", "name": "Steel Erection"})
        self.assertEqual(resp["103"], {"short": "CONC", "name": "Concrete"})
        self.assertNotIn("104", resp)


class TestRosterRows(unittest.TestCase):
    def setUp(self):
        self.wbs_index = build_wbs_path_index(_projwbs())
        self.day_hr = build_day_hr_index(_calendars())
        self.resp = build_task_responsibility(_taskactv(), _actvcode(), "50")

    def _rows(self, **kw):
        return roster_rows(_tasks(), _preds(), self.wbs_index, self.resp,
                           self.day_hr, **kw)

    def test_all_rows_and_fields(self):
        rows = self._rows()
        self.assertEqual(len(rows), 5)
        required = {
            "task_code", "task_name", "task_type", "status_code", "wbs_id",
            "wbs_path", "responsibility", "responsibility_short",
            "early_start", "early_finish", "late_start", "late_finish",
            "total_float_days", "total_float_hr_cnt", "pred_count", "succ_count",
        }
        for r in rows:
            self.assertTrue(required.issubset(r.keys()),
                            f"missing {required - r.keys()}")

    def test_responsibility_surfaced(self):
        by_code = {r["task_code"]: r for r in self._rows()}
        self.assertEqual(by_code["CVMC-1000"]["responsibility"], "Steel Erection")
        self.assertEqual(by_code["CVMC-1000"]["responsibility_short"], "STL")
        self.assertIsNone(by_code["CVMC-8320"]["responsibility"])

    def test_wbs_path_and_float_days(self):
        by_code = {r["task_code"]: r for r in self._rows()}
        self.assertEqual(by_code["CVMC-1000"]["wbs_path"],
                         "CVMC Nephi > Procurement > Steel")
        # 48h / 8h per day = 6 days
        self.assertEqual(by_code["CVMC-2000"]["total_float_days"], 6.0)
        self.assertEqual(by_code["CVMC-1000"]["total_float_days"], 0.0)

    def test_pred_succ_counts(self):
        by_code = {r["task_code"]: r for r in self._rows()}
        self.assertEqual(by_code["CVMC-1000"]["pred_count"], 0)
        self.assertEqual(by_code["CVMC-1000"]["succ_count"], 1)
        self.assertEqual(by_code["CVMC-1010"]["pred_count"], 1)
        self.assertEqual(by_code["CVMC-1010"]["succ_count"], 1)

    def test_include_logic_false_omits_counts(self):
        rows = self._rows(include_logic=False)
        self.assertNotIn("pred_count", rows[0])
        self.assertNotIn("succ_count", rows[0])

    def test_wbs_filter_branch(self):
        rows = self._rows(wbs_filter="steel")
        codes = {r["task_code"] for r in rows}
        self.assertEqual(codes, {"CVMC-1000", "CVMC-1010"})

    def test_trade_filter_matches_responsibility(self):
        rows = self._rows(trade_filter="concrete")
        self.assertEqual({r["task_code"] for r in rows}, {"CVMC-2000"})
        rows = self._rows(trade_filter="steel")  # Steel Erection responsibility
        self.assertEqual({r["task_code"] for r in rows}, {"CVMC-1000", "CVMC-1010"})

    def test_trade_filter_matches_short_name(self):
        rows = self._rows(trade_filter="conc")
        self.assertEqual({r["task_code"] for r in rows}, {"CVMC-2000"})


class TestExpandActivity(unittest.TestCase):
    def setUp(self):
        self.wbs_index = build_wbs_path_index(_projwbs())
        self.day_hr = build_day_hr_index(_calendars())
        self.resp = build_task_responsibility(_taskactv(), _actvcode(), "50")

    def _expand(self, ref):
        return expand_activity(ref, _tasks(), _preds(), self.wbs_index,
                               self.resp, self.day_hr)

    def test_by_task_code(self):
        act = self._expand("CVMC-1010")
        self.assertEqual(act["task_code"], "CVMC-1010")
        self.assertEqual([p["task_code"] for p in act["predecessors"]], ["CVMC-1000"])
        self.assertEqual([s["task_code"] for s in act["successors"]], ["CVMC-2000"])

    def test_rel_type_and_lag(self):
        act = self._expand("CVMC-1010")
        succ = act["successors"][0]
        self.assertEqual(succ["rel_type"], "SS")     # PR_SS normalized
        self.assertEqual(succ["lag_hr_cnt"], 16.0)
        self.assertEqual(succ["lag_days"], 2.0)       # 16h / 8h
        self.assertIn("wbs_path", succ)
        pred = act["predecessors"][0]
        self.assertEqual(pred["rel_type"], "FS")      # PR_FS normalized

    def test_short_code_rel_type(self):
        act = self._expand("CVMC-2000")
        # successor CVMC-8320 via short-code "FS"
        self.assertEqual(act["successors"][0]["rel_type"], "FS")

    def test_by_task_id_fallback(self):
        act = self._expand("102")
        self.assertEqual(act["task_code"], "CVMC-1010")

    def test_not_found_returns_none(self):
        self.assertIsNone(self._expand("NOPE"))


class TestBranchActivities(unittest.TestCase):
    def setUp(self):
        self.wbs_index = build_wbs_path_index(_projwbs())
        self.day_hr = build_day_hr_index(_calendars())
        self.resp = build_task_responsibility(_taskactv(), _actvcode(), "50")

    def _branch(self, ref, **kw):
        return branch_activities(ref, _tasks(), _preds(), _projwbs(),
                                 self.wbs_index, self.resp, self.day_hr, **kw)

    def test_descendants_included(self):
        # Procurement (wbs 2) has no direct tasks; Steel (wbs 3) has 101,102.
        br = self._branch("Procurement", include_descendants=True)
        self.assertEqual({a["task_code"] for a in br["activities"]},
                         {"CVMC-1000", "CVMC-1010"})

    def test_descendants_excluded(self):
        br = self._branch("Procurement", include_descendants=False)
        self.assertEqual(br["activities"], [])

    def test_by_wbs_id(self):
        br = self._branch("3", include_descendants=False)
        self.assertEqual({a["task_code"] for a in br["activities"]},
                         {"CVMC-1000", "CVMC-1010"})

    def test_include_logic_expands(self):
        br = self._branch("Steel", include_logic=True)
        act = next(a for a in br["activities"] if a["task_code"] == "CVMC-1010")
        self.assertIn("predecessors", act)
        self.assertEqual(act["predecessors"][0]["task_code"], "CVMC-1000")

    def test_not_found_returns_none(self):
        self.assertIsNone(self._branch("Nonexistent"))


class TestNextFreeCode(unittest.TestCase):
    def test_infers_next_with_trailing_separator_in_prefix(self):
        res = next_free_code(_tasks(), "CVMC-", step=10)
        self.assertEqual(res["max_existing_code"], "CVMC-8320")
        self.assertEqual(res["max_existing_number"], 8320)
        self.assertEqual(res["next_code"], "CVMC-8330")
        self.assertEqual(res["matched_count"], 5)

    def test_infers_separator_when_prefix_excludes_it(self):
        res = next_free_code(_tasks(), "CVMC", step=10)
        self.assertEqual(res["next_code"], "CVMC-8330")

    def test_custom_step(self):
        res = next_free_code(_tasks(), "CVMC-", step=1)
        self.assertEqual(res["next_code"], "CVMC-8321")

    def test_zero_pad_width_preserved(self):
        tasks = [{"task_code": "A-005"}, {"task_code": "A-010"}]
        res = next_free_code(tasks, "A-", step=10)
        self.assertEqual(res["next_code"], "A-020")

    def test_no_matches(self):
        res = next_free_code(_tasks(), "ZZZ", step=10)
        self.assertEqual(res["matched_count"], 0)
        self.assertIsNone(res["next_code"])
        self.assertIsNone(res["max_existing_number"])


if __name__ == "__main__":
    unittest.main()
