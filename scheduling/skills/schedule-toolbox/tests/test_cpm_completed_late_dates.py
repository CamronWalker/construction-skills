"""Regression tests for completed-task LS/LF preservation.

Pre-fix, ``_backward_pass`` set ``task['_ls'] = task['_es']`` and
``task['_lf'] = task['_ef']`` for any ``TK_Complete`` task. Combined with
the forward pass's floor of ES/EF to data_date for completed tasks, this
collapsed all completed-task late dates onto data_date — a major source
of divergence from P6's own CPM output.

P6 preserves the original baseline late dates for completed tasks (they
encode historical slack against the baseline). The fix mirrors the
forward pass: trust the XER's stored ``late_start_date`` /
``late_end_date`` for completed tasks, falling back to ES/EF only when
the XER doesn't carry late dates.

Validated on QMT-5-26-26 (W1179): all 1045 completed tasks now match
P6's TEST CPM output exactly for LS and LF. Pre-fix: 989 / 1045
completed tasks had LS floored to data_date.
"""
import unittest
from datetime import datetime
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from cpm_engine import schedule_forward_backward


def _task(task_id, code, name, status, **extras):
    base = {
        "task_id": task_id,
        "task_code": code,
        "task_name": name,
        "task_type": "TT_Task",
        "status_code": status,
        "total_float_hr_cnt": "0",
        "target_drtn_hr_cnt": "40",
        "remain_drtn_hr_cnt": "0" if status == "TK_Complete" else "40",
        "cstr_type": "",
        "cstr_type2": "",
        "wbs_id": "",
        "clndr_id": "1",
        "early_start_date": "",
        "early_end_date": "",
        "late_start_date": "",
        "late_end_date": "",
        "target_start_date": "",
        "target_end_date": "",
    }
    base.update(extras)
    return base


def _std_calendar():
    """Mon-Fri 08:00-17:00, 5 working days."""
    return {
        "clndr_id": "1",
        "clndr_name": "Standard",
        "clndr_type": "CA_Base",
        "default_flag": "Y",
        "day_hr_cnt": "8",
        "week_hr_cnt": "40",
        "month_hr_cnt": "172",
        "year_hr_cnt": "2000",
        "clndr_data": (
            "(0||CalendarData(0||DaysOfWeek("
            "(0||1())"
            "(0||2()(0||1(s|08:00|f|17:00)))"
            "(0||3()(0||1(s|08:00|f|17:00)))"
            "(0||4()(0||1(s|08:00|f|17:00)))"
            "(0||5()(0||1(s|08:00|f|17:00)))"
            "(0||6()(0||1(s|08:00|f|17:00)))"
            "(0||7())"
            ")(0||Exceptions())))"
        ),
    }


class TestCompletedTaskLateDatesPreserved(unittest.TestCase):
    """The fix: stored P6 late dates for completed tasks survive CPM."""

    def test_completed_task_keeps_stored_late_dates(self):
        # A task that completed in the past but whose baseline late
        # finish was at a specific historical date. P6 would preserve
        # ``2026-01-15 17:00`` as the LF — pre-fix we'd overwrite with
        # ES = data_date.
        tasks = [
            _task("1", "A1000", "Foundation (complete)", "TK_Complete",
                  early_start_date="2026-01-01 08:00",
                  early_end_date="2026-01-08 17:00",
                  late_start_date="2026-01-05 08:00",
                  late_end_date="2026-01-15 17:00",
                  act_start_date="2026-01-01 08:00",
                  act_end_date="2026-01-08 17:00"),
            _task("2", "A2000", "Framing (in progress)", "TK_Active",
                  early_start_date="2026-05-01 08:00",
                  early_end_date="2026-06-01 17:00"),
        ]
        preds = [{"pred_task_id": "1", "task_id": "2",
                  "pred_type": "PR_FS", "lag_hr_cnt": "0"}]
        cals = [_std_calendar()]

        results, _ = schedule_forward_backward(
            tasks, preds, cals, "2026-05-26 08:00")

        comp = next(t for t in results if t["task_id"] == "1")
        # The completed task carries P6's stored late dates verbatim,
        # not ES/EF (which would be data_date after the floor).
        self.assertEqual(comp["late_start_date"], "2026-01-05 08:00")
        self.assertEqual(comp["late_end_date"], "2026-01-15 17:00")

    def test_completed_task_without_stored_late_dates_falls_back_to_es_ef(self):
        # Edge case: completed task whose XER omits stored late dates.
        # Falls back to ES/EF to keep CPM well-defined.
        tasks = [
            _task("1", "A1000", "Foundation", "TK_Complete",
                  early_start_date="2026-01-01 08:00",
                  early_end_date="2026-01-08 17:00",
                  act_start_date="2026-01-01 08:00",
                  act_end_date="2026-01-08 17:00"),
        ]
        cals = [_std_calendar()]

        results, _ = schedule_forward_backward(
            tasks, [], cals, "2026-05-26 08:00")

        comp = results[0]
        # _ls equals _es when stored late dates are absent — never None.
        self.assertEqual(comp["_ls"], comp["_es"])
        self.assertEqual(comp["_lf"], comp["_ef"])


class TestFsRepresentationSnap(unittest.TestCase):
    """The other fix: predecessor LF on an FS relationship is reported
    at end-of-work-period, not next-day's 08:00. P6 reports e.g. Friday
    17:00, not Monday 08:00, even though they are the same instant in
    work-calendar terms."""

    def test_fs_predecessor_lf_lands_on_period_end(self):
        # Predecessor finishes immediately before successor starts.
        # P6 represents pred's LF at end-of-Friday (e.g., Fri 17:00),
        # not start-of-Monday (Mon 08:00).
        tasks = [
            _task("1", "A1000", "Predecessor", "TK_NotStart"),
            _task("2", "A2000", "Successor", "TK_NotStart"),
        ]
        preds = [{"pred_task_id": "1", "task_id": "2",
                  "pred_type": "PR_FS", "lag_hr_cnt": "0"}]
        cals = [_std_calendar()]

        # Data date Monday morning. Predecessor has 40h duration (= 1 week).
        results, _ = schedule_forward_backward(
            tasks, preds, cals, "2026-06-01 08:00")  # Monday

        pred = next(t for t in results if t["task_id"] == "1")
        # Pred LF must end on an hour:minute that is end-of-work-period,
        # not 08:00 (which is start-of-next-period).
        lf_dt = datetime.strptime(pred["late_end_date"], "%Y-%m-%d %H:%M")
        self.assertEqual(lf_dt.hour, 17,
                         f"Pred LF should land at end-of-work-period (17:00), "
                         f"got {pred['late_end_date']}")


if __name__ == "__main__":
    unittest.main()
