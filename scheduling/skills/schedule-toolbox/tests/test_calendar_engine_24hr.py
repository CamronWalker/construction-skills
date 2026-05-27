"""Regression tests for the P6 24-hour-calendar boundary case.

P6 schedules can set ``sched_calendar_on_relationship_lag = rcal_24Hour``
in SCHEDOPTIONS. ``cpm_engine._get_lag_calendar`` then returns a synthetic
calendar with periods ``(0, 1440)`` — work runs from minute 0 to minute
1440 (= 24:00) of every day. Calendar math that lands exactly on a
period end produces a minutes-from-midnight value of 1440, which is
outside Python's ``time(hour=0..23)`` range.

Pre-fix, ``_minutes_to_time(1440)`` raised ``ValueError: hour must be in
0..23, not 24`` and broke every ``run_cpm`` call on schedules using the
24-hour lag option. These tests pin the rollover behavior introduced by
``_combine_date_minutes`` (1440-minute boundary collapses into the next
day's 00:00, matching P6's own semantics).
"""
import unittest
from datetime import datetime
from pathlib import Path
import sys

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from calendar_engine import (
    add_work_hours,
    subtract_work_hours,
    work_hours_between,
)
from cpm_engine import schedule_forward_backward


def _cal_24hr():
    """Synthetic 24-hour calendar — matches the rcal_24Hour branch in cpm_engine."""
    return {
        "work_week": {i: [(0, 1440)] for i in range(7)},
        "exceptions": {},
        "hours_per_day": 24.0,
    }


class TestAddWorkHoursOn24HourCalendar(unittest.TestCase):
    def test_exact_24_hour_advance_rolls_to_next_midnight(self):
        start = datetime(2026, 5, 14, 0, 0)
        # Advancing 24 working hours on a 24-hour calendar should land
        # exactly on the next day's 00:00 — not crash with hour=24.
        result = add_work_hours(start, 24.0, _cal_24hr())
        self.assertEqual(result, datetime(2026, 5, 15, 0, 0))

    def test_partial_day_advance_stays_within_day(self):
        start = datetime(2026, 5, 14, 0, 0)
        result = add_work_hours(start, 8.0, _cal_24hr())
        self.assertEqual(result, datetime(2026, 5, 14, 8, 0))

    def test_multi_day_advance(self):
        start = datetime(2026, 5, 14, 0, 0)
        # 48 hours = exactly two full days on a 24-hour calendar.
        result = add_work_hours(start, 48.0, _cal_24hr())
        self.assertEqual(result, datetime(2026, 5, 16, 0, 0))

    def test_advance_from_midday(self):
        start = datetime(2026, 5, 14, 12, 0)
        result = add_work_hours(start, 12.0, _cal_24hr())
        self.assertEqual(result, datetime(2026, 5, 15, 0, 0))


class TestSubtractWorkHoursOn24HourCalendar(unittest.TestCase):
    def test_subtract_24_hours_lands_on_prior_midnight(self):
        end = datetime(2026, 5, 15, 0, 0)
        result = subtract_work_hours(end, 24.0, _cal_24hr())
        self.assertEqual(result, datetime(2026, 5, 14, 0, 0))

    def test_subtract_partial_day(self):
        end = datetime(2026, 5, 15, 12, 0)
        result = subtract_work_hours(end, 12.0, _cal_24hr())
        self.assertEqual(result, datetime(2026, 5, 15, 0, 0))


class TestWorkHoursBetweenOn24HourCalendar(unittest.TestCase):
    def test_full_day_is_24_hours(self):
        a = datetime(2026, 5, 14, 0, 0)
        b = datetime(2026, 5, 15, 0, 0)
        self.assertAlmostEqual(work_hours_between(a, b, _cal_24hr()), 24.0)


class TestForwardBackwardWith24HourLagOption(unittest.TestCase):
    """End-to-end: an SS-with-lag relationship under rcal_24Hour
    forced add_work_hours through the 1440-minute boundary and crashed
    ``run_cpm`` on the QMT 5-14 / 5-19 / 5-26 weekly exports."""

    def test_ss_with_positive_lag_under_rcal_24hour_does_not_crash(self):
        # Minimal two-activity schedule with an SS+24h lag — the exact
        # shape that triggered the bug in QMT.
        tasks = [
            {
                "task_id": "1", "task_code": "A1", "task_name": "Predecessor",
                "task_type": "TT_Task", "status_code": "TK_NotStart",
                "target_drtn_hr_cnt": "48", "remain_drtn_hr_cnt": "48",
                "total_float_hr_cnt": "0", "clndr_id": "1",
                "cstr_type": "", "cstr_type2": "", "wbs_id": "",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "target_start_date": "", "target_end_date": "",
            },
            {
                "task_id": "2", "task_code": "A2", "task_name": "Successor",
                "task_type": "TT_Task", "status_code": "TK_NotStart",
                "target_drtn_hr_cnt": "48", "remain_drtn_hr_cnt": "48",
                "total_float_hr_cnt": "0", "clndr_id": "1",
                "cstr_type": "", "cstr_type2": "", "wbs_id": "",
                "early_start_date": "", "early_end_date": "",
                "late_start_date": "", "late_end_date": "",
                "target_start_date": "", "target_end_date": "",
            },
        ]
        preds = [{
            "pred_task_id": "1", "task_id": "2",
            "pred_type": "PR_SS", "lag_hr_cnt": "24",
        }]
        # Real 5-day calendar for the activities themselves...
        calendars = [{
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
                "(0||1())"  # Sunday off
                "(0||2()(0||1(s|08:00|f|17:00)))"
                "(0||3()(0||1(s|08:00|f|17:00)))"
                "(0||4()(0||1(s|08:00|f|17:00)))"
                "(0||5()(0||1(s|08:00|f|17:00)))"
                "(0||6()(0||1(s|08:00|f|17:00)))"
                "(0||7())"  # Saturday off
                ")(0||Exceptions())))"
            ),
        }]
        # ...but the 24-hour lag option that triggered the crash.
        schedoptions = [{"sched_calendar_on_relationship_lag": "rcal_24Hour"}]

        # Pre-fix: this raised "hour must be in 0..23, not 24".
        results, meta = schedule_forward_backward(
            tasks, preds, calendars, "2026-05-14 08:00",
            schedoptions=schedoptions,
        )
        # Both tasks scheduled.
        self.assertEqual(len(results), 2)
        succ = next(t for t in results if t["task_id"] == "2")
        self.assertIsNotNone(succ.get("_es"))


if __name__ == "__main__":
    unittest.main()
