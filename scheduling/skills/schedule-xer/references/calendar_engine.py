"""
Calendar Engine — Calendar parsing & work-day arithmetic for P6 XER schedules.

Pure function library. No file paths, no config, no globals.
Pass parsed XER calendar data in, get results out.

Usage:
    from calendar_engine import build_calendar_lookup, add_work_hours, subtract_work_hours

    cal_lookup = build_calendar_lookup(tables.get('CALENDAR', tables.get('CLNDR', [])))
    end_dt = add_work_hours(start_dt, duration_hours, cal_lookup[clndr_id])
"""

from datetime import datetime, date, timedelta, time
import re


# ---------------------------------------------------------------------------
# Calendar data parsing
# ---------------------------------------------------------------------------

# P6 clndr_data day numbering: 1=Sunday, 2=Monday, ..., 7=Saturday
# Python weekday(): 0=Monday, 1=Tuesday, ..., 6=Sunday
_P6_DAY_TO_PYTHON_WEEKDAY = {
    1: 6,  # Sunday
    2: 0,  # Monday
    3: 1,  # Tuesday
    4: 2,  # Wednesday
    5: 3,  # Thursday
    6: 4,  # Friday
    7: 5,  # Saturday
}

_EXCEL_EPOCH = date(1899, 12, 30)


def _parse_time(time_str):
    """Parse 'HH:MM' to minutes from midnight."""
    h, m = time_str.split(':')
    return int(h) * 60 + int(m)


def _minutes_to_time(minutes):
    """Convert minutes from midnight to time object."""
    return time(minutes // 60, minutes % 60)


def _extract_work_periods(text):
    """
    Extract work periods from a day's content.
    Handles both orderings: (s|08:00|f|12:00) and (f|12:00|s|08:00).
    Returns list of (start_minutes, end_minutes) tuples sorted by start.
    """
    periods = []
    # Standard order: s|start|f|finish
    for m in re.finditer(r's\|(\d{2}:\d{2})\|f\|(\d{2}:\d{2})', text):
        start = _parse_time(m.group(1))
        end = _parse_time(m.group(2))
        if end > start:
            periods.append((start, end))
    # Reversed order: f|finish|s|start (seen in some P6 calendars)
    for m in re.finditer(r'f\|(\d{2}:\d{2})\|s\|(\d{2}:\d{2})', text):
        end = _parse_time(m.group(1))
        start = _parse_time(m.group(2))
        if end > start:
            periods.append((start, end))
    periods.sort()
    return periods


def _parse_days_of_week(dow_text):
    """
    Parse the DaysOfWeek section.
    Returns dict: python_weekday (0=Mon) -> [(start_min, end_min), ...]
    """
    work_week = {i: [] for i in range(7)}  # 0=Mon through 6=Sun

    # Find each day entry: (0||N()(...)...) where N is 1-7
    # We need to find balanced parentheses for each day
    day_pattern = re.compile(r'\(0\|\|(\d)\(\)')
    for m in day_pattern.finditer(dow_text):
        p6_day = int(m.group(1))
        if p6_day not in _P6_DAY_TO_PYTHON_WEEKDAY:
            continue
        py_weekday = _P6_DAY_TO_PYTHON_WEEKDAY[p6_day]

        # Extract the content after this day marker until the next day or end
        start_pos = m.end()
        # Find balanced content - count parens
        depth = 0
        end_pos = start_pos
        for i in range(start_pos, len(dow_text)):
            if dow_text[i] == '(':
                depth += 1
            elif dow_text[i] == ')':
                if depth == 0:
                    end_pos = i
                    break
                depth -= 1

        day_content = dow_text[start_pos:end_pos]
        work_week[py_weekday] = _extract_work_periods(day_content)

    return work_week


def _parse_exceptions(exc_text):
    """
    Parse the Exceptions section.
    Returns dict: date -> [(start_min, end_min), ...] (empty list = holiday)

    Exception structure:
      (0||INDEX(d|SERIAL)( work_periods_content ))
    The work periods are in the second child group AFTER the (d|SERIAL) child.
    We need to find the ENTIRE exception entry to extract work periods from it.
    """
    exceptions = {}

    # Find each exception entry: (0||INDEX(d|SERIAL)(...))
    # We locate each d|SERIAL and then find the enclosing exception entry
    # by scanning backward to find the entry start and forward to find the entry end.
    for m in re.finditer(r'd\|(\d+)', exc_text):
        serial = int(m.group(1))
        exc_date = _EXCEL_EPOCH + timedelta(days=serial)

        # Find the enclosing exception entry — scan forward from just past d|SERIAL
        # to find the full content including work period children.
        # The exception entry looks like: (0||N(d|SERIAL)( ... work periods ... ))
        # We need to find the outermost closing )) of this entry.
        # Start from the position of (0||N which precedes d|SERIAL
        entry_start = exc_text.rfind('(0||', 0, m.start())
        if entry_start == -1:
            entry_start = m.start()

        # Find balanced end from entry_start
        depth = 0
        entry_end = entry_start
        for i in range(entry_start, len(exc_text)):
            if exc_text[i] == '(':
                depth += 1
            elif exc_text[i] == ')':
                depth -= 1
                if depth == 0:
                    entry_end = i + 1
                    break

        entry_content = exc_text[entry_start:entry_end]
        periods = _extract_work_periods(entry_content)
        exceptions[exc_date] = periods  # empty = non-working (holiday)

    return exceptions


def parse_calendar_data(clndr_data):
    """
    Parse the nested parenthetical clndr_data string into a structured dict.

    Args:
        clndr_data: The raw clndr_data string from the XER CALENDAR/CLNDR table.

    Returns:
        {
            'work_week': {
                0: [(480, 720), (780, 1020)],  # Monday work periods (minutes from midnight)
                1: [(480, 720), (780, 1020)],  # Tuesday
                ...
                6: [],                          # Sunday (non-working)
            },
            'exceptions': {
                date(2026, 1, 1): [],           # Holiday
            },
            'hours_per_day': 8.0,  # Derived from typical working day
        }
    """
    if not clndr_data or not clndr_data.strip():
        return _default_calendar()

    try:
        # Find DaysOfWeek section
        dow_start = clndr_data.find('DaysOfWeek')
        exc_start = clndr_data.find('Exceptions')

        if dow_start == -1:
            return _default_calendar()

        # Extract DaysOfWeek content
        if exc_start > dow_start:
            dow_text = clndr_data[dow_start:exc_start]
        else:
            dow_text = clndr_data[dow_start:]

        work_week = _parse_days_of_week(dow_text)

        # Extract Exceptions content
        exceptions = {}
        if exc_start != -1:
            exc_text = clndr_data[exc_start:]
            exceptions = _parse_exceptions(exc_text)

        # Derive hours_per_day from the first working day found
        hours_per_day = 8.0  # default
        for day_periods in work_week.values():
            if day_periods:
                total_minutes = sum(end - start for start, end in day_periods)
                hours_per_day = total_minutes / 60.0
                break

        return {
            'work_week': work_week,
            'exceptions': exceptions,
            'hours_per_day': hours_per_day,
        }
    except Exception:
        return _default_calendar()


def _default_calendar():
    """5-day, 8-hour default calendar (Mon-Fri, 08:00-17:00 with lunch)."""
    work_periods = [(480, 720), (780, 1020)]  # 08:00-12:00, 13:00-17:00
    return {
        'work_week': {
            0: work_periods[:],  # Monday
            1: work_periods[:],  # Tuesday
            2: work_periods[:],  # Wednesday
            3: work_periods[:],  # Thursday
            4: work_periods[:],  # Friday
            5: [],               # Saturday
            6: [],               # Sunday
        },
        'exceptions': {},
        'hours_per_day': 8.0,
    }


def build_calendar_lookup(calendars):
    """
    Build a lookup dict from raw CALENDAR/CLNDR table rows.
    Handles calendar inheritance: child calendars inherit exceptions
    from their base_clndr_id parent (P6 calendar hierarchy).

    Args:
        calendars: List of row dicts from the parsed XER CALENDAR or CLNDR table.

    Returns:
        { clndr_id: parsed_calendar_dict, ... }
    """
    lookup = {}
    base_map = {}  # child_id -> parent_id

    for cal in calendars:
        cid = cal.get('clndr_id', '')
        data = cal.get('clndr_data', '')
        parsed = parse_calendar_data(data)

        # Also store the raw metadata for reference
        parsed['clndr_id'] = cid
        parsed['clndr_name'] = cal.get('clndr_name', '')
        parsed['day_hr_cnt'] = _safe_float(cal.get('day_hr_cnt', '8'))
        parsed['week_hr_cnt'] = _safe_float(cal.get('week_hr_cnt', '40'))

        lookup[cid] = parsed

        base_id = (cal.get('base_clndr_id', '') or '').strip()
        if base_id:
            base_map[cid] = base_id

    # Merge parent calendar exceptions into children.
    # P6 inherits holidays from the base calendar — child exceptions
    # override parent for the same date, but parent holidays that don't
    # exist in the child are inherited.
    for child_id, parent_id in base_map.items():
        if parent_id not in lookup or child_id not in lookup:
            continue
        parent_exc = lookup[parent_id].get('exceptions', {})
        child_exc = lookup[child_id].get('exceptions', {})
        # Merge: parent exceptions that aren't overridden by child
        merged = dict(parent_exc)
        merged.update(child_exc)  # child overrides parent
        lookup[child_id]['exceptions'] = merged

    # Always have a fallback
    if '' not in lookup:
        lookup[''] = _default_calendar()

    return lookup


# ---------------------------------------------------------------------------
# Work-day queries
# ---------------------------------------------------------------------------

def _get_work_periods(dt_date, cal):
    """Get work periods for a specific date, respecting exceptions."""
    if dt_date in cal.get('exceptions', {}):
        return cal['exceptions'][dt_date]
    return cal['work_week'].get(dt_date.weekday(), [])


def is_working_day(dt_date, cal):
    """Check if a date is a working day on the given calendar."""
    periods = _get_work_periods(dt_date, cal)
    return len(periods) > 0


def get_work_hours_on_day(dt_date, cal):
    """Return number of work hours available on a specific date."""
    periods = _get_work_periods(dt_date, cal)
    return sum(end - start for start, end in periods) / 60.0


def next_work_start(dt, cal):
    """
    Find the next working-day start time on or after dt.
    If dt is before the first work period of a working day, returns that day's start.
    If dt is during or after work periods, advances to next working day.
    """
    current_date = dt.date()
    current_minutes = dt.hour * 60 + dt.minute

    # Check if current day has remaining work
    periods = _get_work_periods(current_date, cal)
    for start, end in periods:
        if current_minutes <= start:
            return datetime.combine(current_date, _minutes_to_time(start))

    # Advance to next working day
    for offset in range(1, 1000):  # Safety limit
        next_date = current_date + timedelta(days=offset)
        periods = _get_work_periods(next_date, cal)
        if periods:
            return datetime.combine(next_date, _minutes_to_time(periods[0][0]))

    # Fallback — should never reach here with a valid calendar
    return dt


def snap_to_work_time(dt, cal):
    """
    Snap a datetime to valid work time. Unlike next_work_start() which always
    returns a period START, this preserves mid-period times.

    - If dt is within a work period (start <= min < end), returns dt unchanged.
    - If dt is between periods on a working day, returns next period start.
    - If dt is after all periods or on a non-working day, advances to next working day start.
    """
    current_date = dt.date()
    current_minutes = dt.hour * 60 + dt.minute

    periods = _get_work_periods(current_date, cal)
    for start, end in periods:
        if start <= current_minutes < end:
            return dt  # Already within a work period
        if current_minutes < start:
            return datetime.combine(current_date, _minutes_to_time(start))

    # After all periods or non-working day — advance to next working day
    for offset in range(1, 1000):
        next_date = current_date + timedelta(days=offset)
        periods = _get_work_periods(next_date, cal)
        if periods:
            return datetime.combine(next_date, _minutes_to_time(periods[0][0]))

    return dt


def prev_work_end(dt, cal):
    """
    Find the previous working-day end time on or before dt.
    If dt is after the last work period of a working day, returns that day's end.
    If dt is before or during first work period, goes to previous working day.
    """
    current_date = dt.date()
    current_minutes = dt.hour * 60 + dt.minute

    # Check if current day has work ending before or at current time
    periods = _get_work_periods(current_date, cal)
    for start, end in reversed(periods):
        if current_minutes >= end:
            return datetime.combine(current_date, _minutes_to_time(end))

    # Go to previous working day
    for offset in range(1, 1000):
        prev_date = current_date - timedelta(days=offset)
        periods = _get_work_periods(prev_date, cal)
        if periods:
            last_end = periods[-1][1]
            return datetime.combine(prev_date, _minutes_to_time(last_end))

    return dt


# ---------------------------------------------------------------------------
# Work-hour arithmetic
# ---------------------------------------------------------------------------

def add_work_hours(start, hours, cal):
    """
    Starting from start datetime, advance by `hours` of working time.
    Returns the resulting datetime, skipping non-working days/hours.

    If hours is 0, returns start snapped to next work start if needed.
    If hours is negative, delegates to subtract_work_hours.
    """
    if hours < 0:
        return subtract_work_hours(start, -hours, cal)
    if hours == 0:
        # For milestones — snap to work time if needed
        current_date = start.date()
        current_min = start.hour * 60 + start.minute
        periods = _get_work_periods(current_date, cal)
        for s, e in periods:
            if s <= current_min <= e:
                return start  # Already in work time
        return next_work_start(start, cal)

    remaining_minutes = hours * 60.0
    current_date = start.date()
    current_min = start.hour * 60 + start.minute

    # Handle case where start is not on a working day or is outside work hours
    periods = _get_work_periods(current_date, cal)
    started = False

    if periods:
        for i, (p_start, p_end) in enumerate(periods):
            if current_min < p_start and not started:
                # Before this period — snap to period start
                current_min = p_start
                started = True
            if p_start <= current_min <= p_end:
                started = True
                available = p_end - current_min
                if remaining_minutes <= available:
                    result_min = current_min + remaining_minutes
                    return datetime.combine(current_date, _minutes_to_time(int(result_min)))
                remaining_minutes -= available
                current_min = p_end
            elif current_min < p_start and started:
                # Between periods (lunch break) — snap to next period
                current_min = p_start
                available = p_end - p_start
                if remaining_minutes <= available:
                    result_min = p_start + remaining_minutes
                    return datetime.combine(current_date, _minutes_to_time(int(result_min)))
                remaining_minutes -= available
                current_min = p_end

    # Continue to subsequent days
    for offset in range(1, 5000):  # Safety limit for very long durations
        next_date = current_date + timedelta(days=offset)
        periods = _get_work_periods(next_date, cal)
        if not periods:
            continue
        for p_start, p_end in periods:
            available = p_end - p_start
            if remaining_minutes <= available:
                result_min = p_start + remaining_minutes
                return datetime.combine(next_date, _minutes_to_time(int(result_min)))
            remaining_minutes -= available

    # Should never reach here
    return start + timedelta(hours=hours)


def subtract_work_hours(end, hours, cal):
    """
    From end datetime, walk backward by `hours` of working time.
    Returns the resulting datetime.

    If hours is 0, returns end snapped to prev work end if needed.
    If hours is negative, delegates to add_work_hours.
    """
    if hours < 0:
        return add_work_hours(end, -hours, cal)
    if hours == 0:
        current_date = end.date()
        current_min = end.hour * 60 + end.minute
        periods = _get_work_periods(current_date, cal)
        for s, e in periods:
            if s <= current_min <= e:
                return end
        return prev_work_end(end, cal)

    remaining_minutes = hours * 60.0
    current_date = end.date()
    current_min = end.hour * 60 + end.minute

    # Handle current day
    periods = _get_work_periods(current_date, cal)
    if periods:
        for p_start, p_end in reversed(periods):
            if current_min > p_end:
                # After this period — snap to period end
                current_min = p_end
            if p_start <= current_min <= p_end:
                available = current_min - p_start
                if remaining_minutes <= available:
                    result_min = current_min - remaining_minutes
                    return datetime.combine(current_date, _minutes_to_time(int(result_min)))
                remaining_minutes -= available
                current_min = p_start
            elif current_min > p_start:
                # We're between periods going backward, skip to this period end
                pass

    # Continue to previous days
    for offset in range(1, 5000):
        prev_date = current_date - timedelta(days=offset)
        periods = _get_work_periods(prev_date, cal)
        if not periods:
            continue
        for p_start, p_end in reversed(periods):
            available = p_end - p_start
            if remaining_minutes <= available:
                result_min = p_end - remaining_minutes
                return datetime.combine(prev_date, _minutes_to_time(int(result_min)))
            remaining_minutes -= available

    return end - timedelta(hours=hours)


def work_hours_between(start, end, cal):
    """
    Calculate total working hours between two datetimes.
    Returns positive if end > start, negative if end < start.
    """
    if start == end:
        return 0.0
    if end < start:
        return -work_hours_between(end, start, cal)

    total_minutes = 0.0
    current_date = start.date()
    end_date = end.date()
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute

    if current_date == end_date:
        # Same day
        periods = _get_work_periods(current_date, cal)
        for p_start, p_end in periods:
            overlap_start = max(start_min, p_start)
            overlap_end = min(end_min, p_end)
            if overlap_end > overlap_start:
                total_minutes += overlap_end - overlap_start
        return total_minutes / 60.0

    # First day (partial)
    periods = _get_work_periods(current_date, cal)
    for p_start, p_end in periods:
        overlap_start = max(start_min, p_start)
        if p_end > overlap_start:
            total_minutes += p_end - overlap_start

    # Full days in between
    day = current_date + timedelta(days=1)
    while day < end_date:
        periods = _get_work_periods(day, cal)
        for p_start, p_end in periods:
            total_minutes += p_end - p_start
        day += timedelta(days=1)

    # Last day (partial)
    periods = _get_work_periods(end_date, cal)
    for p_start, p_end in periods:
        overlap_end = min(end_min, p_end)
        if overlap_end > p_start:
            total_minutes += overlap_end - p_start

    return total_minutes / 60.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default
