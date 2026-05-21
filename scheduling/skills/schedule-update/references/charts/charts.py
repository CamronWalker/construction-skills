"""One render function per graph. Each takes (data: dict, output_path: str) → None.

Each function is self-contained: it knows its data shape, its chart type, its
title, axes, and styling. They don't share a base function — duplication is
intentional so each chart can be tweaked in isolation without risk of breaking
its neighbors.
"""

from datetime import date, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.dates import DateFormatter
from matplotlib.patches import FancyBboxPatch, Rectangle

from . import style


# SmartPM Velocity chart palette — six bar series + average line + data-date marker.
_VEL_CURR_START_ACTUAL   = '#7CB5EC'   # light blue
_VEL_CURR_FINISH_ACTUAL  = '#1F4E79'   # dark blue
_VEL_BASELINE_START      = '#D9D9D9'   # light gray
_VEL_BASELINE_FINISH     = '#595959'   # dark gray
_VEL_CURR_START_PLANNED  = '#A6E3A6'   # light green
_VEL_CURR_FINISH_PLANNED = '#3F8F3F'   # dark green
_VEL_AVERAGE_LINE        = '#E8A82E'   # orange
_VEL_DATA_DATE_LINE      = '#222222'   # near-black


# SmartPM Summary-style palette — used to match the look of the existing screenshots.
_SMARTPM_RED          = '#C0223A'
_SMARTPM_PINK_FILL    = '#FBE6EA'
_SMARTPM_GREEN_FILL   = '#E8F1ED'
_SMARTPM_LABEL_BG     = '#FBE6EA'

# SmartPM Compression Index palette — green/yellow/red bands. Colors match
# SmartPM's GOOD / FINE / BAD indicator field directly.
_SCI_GREEN    = '#3FA864'   # GOOD
_SCI_YELLOW   = '#E8A82E'   # FINE
_SCI_RED      = '#D8316C'   # BAD
_SCI_WARN_PCT = 15.0        # warning threshold (orange line)
_SCI_DANGER_PCT = 25.0      # danger threshold (red/pink line)

_SCI_INDICATOR_COLOR = {
    'GOOD': _SCI_GREEN,
    'FINE': _SCI_YELLOW,
    'BAD':  _SCI_RED,
}


def render_end_date_variance(data, output_path):
    """Chart 06 — End Date Variance, mirroring SmartPM's "End Date Variance" trend.

    Y-axis is *days of variance* (projected_finish − contractual_completion).
    Positive = behind contractual, negative = ahead. Pink shading above zero,
    light green below, bold zero line.

    Each data point gets a pink-background label showing the projected finish
    date for that update — that's how the viewer sees the actual dates.

    Consumes the SmartPM MCP shape (list_scenario_schedules_v2 entries) plus
    a separate contractual_completion field that the phase file looks up from
    the original baseline.

    data shape:
      {
        "updates": [
          {"dataDate": "YYYY-MM-DDTHH:MM:SS", "sourceEndDate": "YYYY-MM-DDTHH:MM:SS", ...},
          ...
        ],
        "contractual_completion": "YYYY-MM-DD"
      }
    """
    all_updates = [u for u in data['updates'] if u.get('sourceEndDate')]
    contractual = date.fromisoformat(data['contractual_completion'])

    # Display only the latest 9 updates. If anything older exists, we'll add
    # an "earlier updates" hint so the viewer knows this is a windowed view.
    visible = all_updates[-9:]
    has_older = len(all_updates) > len(visible)

    xs = [date.fromisoformat(u['dataDate'][:10]) for u in visible]
    finishes = [date.fromisoformat(u['sourceEndDate'][:10]) for u in visible]
    ys = [(f - contractual).days for f in finishes]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    # Background shading: pink above 0 (behind), green below (ahead).
    # Use the x-range of the data plus a touch of padding.
    ax.axhspan(0, 1e6, facecolor=_SMARTPM_PINK_FILL, alpha=1.0, zorder=0)
    ax.axhspan(-1e6, 0, facecolor=_SMARTPM_GREEN_FILL, alpha=1.0, zorder=0)

    # Bold zero (contractual) baseline.
    ax.axhline(y=0, color='black', linewidth=1.5, zorder=2)

    # Variance line — red with circle markers.
    ax.plot(xs, ys, color=_SMARTPM_RED, marker='o', linewidth=2, markersize=5,
            markerfacecolor=_SMARTPM_RED, markeredgecolor=_SMARTPM_RED,
            label='End Date Variance', zorder=3)

    # Small hint that this is a windowed view — only shown if data older than
    # the visible 9 actually exists. New projects with <10 updates don't get
    # the hint, which would otherwise be confusing.
    if has_older:
        ax.text(0.005, 0.97, '◀ earlier updates',
                transform=ax.transAxes,
                fontsize=8, color=style.GRAY,
                va='top', ha='left', style='italic', zorder=5)

    # Pink-background label at each data point showing the projected finish date.
    for x, y, f in zip(xs, ys, finishes):
        ax.annotate(
            f.strftime('%b %d, %Y'),
            xy=(x, y),
            xytext=(0, 12), textcoords='offset points',
            ha='center', va='bottom',
            fontsize=8,
            color=_SMARTPM_RED,
            bbox=dict(boxstyle='round,pad=0.25',
                      facecolor=_SMARTPM_LABEL_BG,
                      edgecolor='none'),
            zorder=4,
        )

    # Anchor y-range so 0 is visible with breathing room on both sides.
    y_min = min(ys + [0])
    y_max = max(ys + [0])
    y_pad = max(15, (y_max - y_min) * 0.35)
    ax.set_ylim(y_min - y_pad, y_max + y_pad)

    # Title — left-aligned, plain. No y-axis label (would duplicate the title).
    ax.set_title('End Date Variance', fontsize=style.TITLE_FONTSIZE,
                 loc='left', pad=style.TITLE_PAD)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)

    # X-axis: a tick at every schedule-update date, "Feb 11, 2026" style.
    ax.set_xticks(xs)
    ax.xaxis.set_major_formatter(DateFormatter('%b %d, %Y'))

    # Light gridlines only on the x direction so the shaded bands stay clean.
    ax.grid(True, axis='x', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    # No legend — single series and the title says what it is.

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def render_schedule_compression_index(data, output_path):
    """Chart 07 — Schedule Compression Index™ Over Time.

    Mirrors SmartPM's "Schedule Compression Index Over Time" trend:
      - Y-axis is percent (0–125%+), with `%` tick suffix
      - Two horizontal dashed threshold lines: warning (15%, orange) and
        danger (25%, red/pink)
      - Line and markers are color-coded by SmartPM's `indicator` field:
        GOOD → green, FINE → yellow/orange, BAD → red/pink
      - Shows full history (no windowing)
      - Null points (no `scheduleCompressionIndex`) are skipped silently

    Accepts the MCP response shape directly:
      {"trend": [
        {
          "dataDate": "YYYY-MM-DDTHH:MM:SS",
          "scheduleCompression": float | null,
          "scheduleCompressionIndex": int | null,    # the percent value
          "indicator": "GOOD" | "FINE" | "BAD" | null
        },
        ...
      ]}
    """
    raw_points = data['trend']
    # Filter out nulls so line segments don't break.
    points = [
        p for p in raw_points
        if p.get('scheduleCompressionIndex') is not None
    ]

    if not points:
        # Empty (or all-null) series — write a blank canvas rather than crash.
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_title('Schedule Compression Index™ Over Time',
                     fontsize=style.TITLE_FONTSIZE, loc='left',
                     pad=style.TITLE_PAD)
        fig.savefig(output_path, **style.SAVEFIG_KWARGS)
        plt.close(fig)
        return

    xs = [date.fromisoformat(p['dataDate'][:10]) for p in points]
    ys = [float(p['scheduleCompressionIndex']) for p in points]
    indicators = [p.get('indicator', 'GOOD') or 'GOOD' for p in points]
    x_nums = [mdates.date2num(x) for x in xs]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    # Dashed horizontal thresholds.
    ax.axhline(y=_SCI_WARN_PCT, color=_SCI_YELLOW, linestyle='--', linewidth=1.2,
               zorder=1)
    ax.axhline(y=_SCI_DANGER_PCT, color=_SCI_RED, linestyle='--', linewidth=1.2,
               zorder=1)

    # Color-coded line via LineCollection — color each segment by the higher
    # severity of its two endpoints (worst-of-two), matching how SmartPM seems
    # to render transitions.
    pts = list(zip(x_nums, ys))
    segments = list(zip(pts[:-1], pts[1:]))
    severity_rank = {'GOOD': 0, 'FINE': 1, 'BAD': 2}
    seg_colors = []
    for i in range(len(segments)):
        a_ind = indicators[i]
        b_ind = indicators[i + 1]
        worst = a_ind if severity_rank[a_ind] >= severity_rank[b_ind] else b_ind
        seg_colors.append(_SCI_INDICATOR_COLOR[worst])
    lc = LineCollection(segments, colors=seg_colors, linewidth=2, zorder=3)
    ax.add_collection(lc)

    # Markers, colored by their own indicator.
    for x_num, y, ind in zip(x_nums, ys, indicators):
        color = _SCI_INDICATOR_COLOR[ind]
        ax.plot(x_num, y, marker='o', markersize=4,
                color=color, markerfacecolor=color, markeredgecolor=color,
                zorder=4)

    # Y-axis: percent. Anchor 0–max with a touch of headroom; min always 0.
    y_max = max(ys + [_SCI_DANGER_PCT * 1.4])
    ax.set_ylim(0, y_max * 1.1)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%d %%'))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(25))

    # X-axis: full data range with a small left/right margin so the first
    # and last points don't sit right on the axis edges. MM/DD/YY style.
    x_span = x_nums[-1] - x_nums[0]
    x_pad = max(7, x_span * 0.015)
    ax.set_xlim(x_nums[0] - x_pad, x_nums[-1] + x_pad)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
    ax.xaxis.set_major_formatter(DateFormatter('%m/%d/%y'))

    # Title.
    ax.set_title('Schedule Compression Index™ Over Time',
                 fontsize=style.TITLE_FONTSIZE, loc='left',
                 pad=style.TITLE_PAD)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)

    # Light horizontal gridlines so the % bands are easy to read.
    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def render_velocity(data, output_path):
    """Chart 08 — Monthly Activity Start & Finish Distribution.

    Mirrors SmartPM's Velocity chart:
      - Six bar series per month: Current Starts/Finishes split into Actual
        (≤ data date) and Planned (> data date), plus Baseline Starts/Finishes.
      - Orange horizontal average line (mean of current finishes where actual).
      - Black vertical line at the project data date, with date label.
      - Title "Monthly Activity Start & Finish Distribution", legend below.

    Consumes the SmartPM MCP shape directly:
      {
        "velocityList": [
          {"date": "YYYY-MM-01T00:00:00",
           "baselineStarts": int, "baselineFinishes": int,
           "currentStarts": int, "currentFinishes": int},
          ...
        ],
        "dataDate": "YYYY-MM-DDTHH:MM:SS"   # project data date
      }

    Non-month-start entries (e.g. a special row stamped at the data date itself)
    are skipped — they're a SmartPM marker, not a monthly bucket.
    """
    raw = data.get('velocityList') or []
    # Only keep first-of-month rows; SmartPM sometimes embeds a marker row at
    # the data date that would otherwise double-count.
    monthly = [
        v for v in raw
        if v.get('date', '').endswith('T00:00:00') and v['date'][8:10] == '01'
    ]
    monthly.sort(key=lambda v: v['date'])

    if not monthly:
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_title('Monthly Activity Start & Finish Distribution (Last 12 Months)',
                     fontsize=style.TITLE_FONTSIZE, loc='left',
                     pad=style.TITLE_PAD)
        fig.savefig(output_path, **style.SAVEFIG_KWARGS)
        plt.close(fig)
        return

    # Window to the trailing 12 months before the data date through the end of
    # the series (so all planned months are kept). Long projects (6+ years here)
    # become unreadable at full width otherwise.
    data_date_str = data.get('dataDate', '')
    if data_date_str:
        dd_full = date.fromisoformat(data_date_str[:10])
        cutoff_year = dd_full.year - 1
        cutoff_month = dd_full.month
        cutoff = date(cutoff_year, cutoff_month, 1)
        monthly = [
            v for v in monthly
            if date.fromisoformat(v['date'][:10]) >= cutoff
        ]

    months = [date.fromisoformat(v['date'][:10]) for v in monthly]
    bl_starts   = [int(v.get('baselineStarts')   or 0) for v in monthly]
    bl_finishes = [int(v.get('baselineFinishes') or 0) for v in monthly]
    cur_starts   = [int(v.get('currentStarts')   or 0) for v in monthly]
    cur_finishes = [int(v.get('currentFinishes') or 0) for v in monthly]

    data_date = date.fromisoformat(data_date_str[:10]) if data_date_str else None
    dd_month = data_date.replace(day=1) if data_date else None

    # Split current series into Actual (months <= data-date month) and Planned (after).
    def split(values):
        actual, planned = [], []
        for m, v in zip(months, values):
            if dd_month is None or m <= dd_month:
                actual.append(v); planned.append(0)
            else:
                actual.append(0); planned.append(v)
        return actual, planned

    cs_actual, cs_planned = split(cur_starts)
    cf_actual, cf_planned = split(cur_finishes)

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    x = np.arange(len(months))
    width = 0.14
    offsets = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]

    ax.bar(x + offsets[0] * width, cs_actual,   width, color=_VEL_CURR_START_ACTUAL,   label='Current Starts (Actual)')
    ax.bar(x + offsets[1] * width, cf_actual,   width, color=_VEL_CURR_FINISH_ACTUAL,  label='Current Finishes (Actual)')
    ax.bar(x + offsets[2] * width, bl_starts,   width, color=_VEL_BASELINE_START,      label='Baseline Starts')
    ax.bar(x + offsets[3] * width, bl_finishes, width, color=_VEL_BASELINE_FINISH,     label='Baseline Finishes')
    ax.bar(x + offsets[4] * width, cs_planned,  width, color=_VEL_CURR_START_PLANNED,  label='Current Starts (Planned)')
    ax.bar(x + offsets[5] * width, cf_planned,  width, color=_VEL_CURR_FINISH_PLANNED, label='Current Finishes (Planned)')

    # Average line — mean of current finishes for actual months only, skipping zeros.
    actual_finishes = [v for v, p in zip(cur_finishes, cf_planned) if p == 0 and v > 0]
    if actual_finishes:
        avg = sum(actual_finishes) / len(actual_finishes)
        ax.axhline(y=avg, color=_VEL_AVERAGE_LINE, linewidth=1.5, label='Average', zorder=3)

    # Data-date vertical line + label.
    if dd_month and dd_month in months:
        dd_idx = months.index(dd_month)
        # Place between the data-date month and the next month so it visually
        # separates actual from planned.
        line_x = dd_idx + 0.5
        ax.axvline(x=line_x, color=_VEL_DATA_DATE_LINE, linewidth=1.2, zorder=2)
        ymin, ymax = ax.get_ylim()
        ax.text(line_x, ymax * 0.96,
                data_date.strftime('%d %b-%y'),
                rotation=90, ha='right', va='top',
                fontsize=8, color=_VEL_DATA_DATE_LINE)

    # X-ticks: every 3 months keeps labels readable across 6+ years.
    tick_step = max(1, len(months) // 24)
    ax.set_xticks(x[::tick_step])
    ax.set_xticklabels([m.strftime('%b-%y') for m in months[::tick_step]],
                       rotation=45, ha='right', fontsize=style.TICK_FONTSIZE)
    ax.tick_params(axis='y', labelsize=style.TICK_FONTSIZE)
    ax.set_xlim(-0.5, len(months) - 0.5)

    ax.set_title('Monthly Activity Start & Finish Distribution (Last 12 Months)',
                 fontsize=style.TITLE_FONTSIZE, loc='left',
                 pad=style.TITLE_PAD)

    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.45),
              ncol=4, fontsize=8, frameon=False)

    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


# SPI palette — same colors as compression bands, but threshold semantics flipped
# (higher SPI is better, lower is worse).
_SPI_GREEN_THRESHOLD  = 0.9   # >= → GOOD (green)
_SPI_YELLOW_THRESHOLD = 0.8   # >= → FINE (yellow); below → BAD (red)


def _spi_color(value):
    if value >= _SPI_GREEN_THRESHOLD:
        return _SCI_GREEN
    if value >= _SPI_YELLOW_THRESHOLD:
        return _SCI_YELLOW
    return _SCI_RED


def render_spi_over_time(data, output_path):
    """Chart 09 — Schedule Performance Index over time.

    Mirrors SmartPM's "SPI Over Time" trend:
      - Y-axis 0 to ~1.25, with 0.25 ticks
      - Two dashed horizontal threshold lines: green at 0.9, yellow at 0.8
      - Line + markers color-coded: green ≥ 0.9, yellow ≥ 0.8, red < 0.8
        (higher is better — opposite direction from compression index)
      - Full history view; small left/right padding so endpoints don't sit
        on the axis edges
      - Title "SPI Over Time"

    Consumes the SmartPM MCP shape directly:
      {"trend": [{"dataDate": "YYYY-MM-DDTHH:MM:SS", "spi": float}, ...]}
    """
    raw_points = data.get('trend') or []
    # Skip any null spi entries; keep 0.0 (it's a legit "no schedule" marker
    # that shows as a sharp dip in the SmartPM chart).
    points = [p for p in raw_points if p.get('spi') is not None]

    if not points:
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_title('SPI Over Time', fontsize=style.TITLE_FONTSIZE,
                     loc='left', pad=style.TITLE_PAD)
        fig.savefig(output_path, **style.SAVEFIG_KWARGS)
        plt.close(fig)
        return

    xs = [date.fromisoformat(p['dataDate'][:10]) for p in points]
    ys = [float(p['spi']) for p in points]
    x_nums = [mdates.date2num(x) for x in xs]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    # Dashed threshold lines.
    ax.axhline(y=_SPI_GREEN_THRESHOLD, color=_SCI_GREEN, linestyle='--',
               linewidth=1.2, zorder=1)
    ax.axhline(y=_SPI_YELLOW_THRESHOLD, color=_SCI_YELLOW, linestyle='--',
               linewidth=1.2, zorder=1)

    # Color-coded line via LineCollection — segment color picks the WORST
    # (lowest) SPI of the two endpoints. Matches the way risk shows in SmartPM.
    pts = list(zip(x_nums, ys))
    segments = list(zip(pts[:-1], pts[1:]))
    severity_rank = {_SCI_RED: 2, _SCI_YELLOW: 1, _SCI_GREEN: 0}
    seg_colors = []
    for a, b in segments:
        col_a, col_b = _spi_color(a[1]), _spi_color(b[1])
        seg_colors.append(col_a if severity_rank[col_a] >= severity_rank[col_b] else col_b)
    lc = LineCollection(segments, colors=seg_colors, linewidth=2, zorder=3)
    ax.add_collection(lc)

    # Markers colored by their own value.
    for x_num, y in zip(x_nums, ys):
        c = _spi_color(y)
        ax.plot(x_num, y, marker='o', markersize=4,
                color=c, markerfacecolor=c, markeredgecolor=c, zorder=4)

    # Y-axis 0 to 1.25 with 0.25 ticks (matches SmartPM).
    ax.set_ylim(0, 1.3)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.25))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

    # X-axis: small left/right padding so endpoints aren't on the axis edges.
    x_span = x_nums[-1] - x_nums[0]
    x_pad = max(7, x_span * 0.015)
    ax.set_xlim(x_nums[0] - x_pad, x_nums[-1] + x_pad)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
    ax.xaxis.set_major_formatter(DateFormatter('%m/%d/%y'))

    ax.set_title('SPI Over Time', fontsize=style.TITLE_FONTSIZE,
                 loc='left', pad=style.TITLE_PAD)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def _render_hit_rate_chart(data, output_path, *, field, title):
    """Shared renderer for the three hit-rate charts (10/11/12).

    Same MCP endpoint (should_start_finish_trend) drives all three; they
    only differ by which field is plotted and what the title says.

    field: one of 'totalOnTimeHitRate', 'startedOnTimeHitRate',
           'finishedOnTimeHitRate'. API returns 0-1 ratios; we multiply
           by 100 for percent display.
    """
    raw = data.get('hitRates') or []
    points = [p for p in raw if p.get(field) is not None]
    if not points:
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_title(title, fontsize=style.TITLE_FONTSIZE, loc='left',
                     pad=style.TITLE_PAD)
        fig.savefig(output_path, **style.SAVEFIG_KWARGS)
        plt.close(fig)
        return

    xs = [date.fromisoformat(p['dataDate'][:10]) for p in points]
    ys = [float(p[field]) * 100 for p in points]
    x_nums = [mdates.date2num(x) for x in xs]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    # Dashed threshold lines at 80% (yellow) and 90% (green).
    ax.axhline(y=80, color=_SCI_YELLOW, linestyle='--', linewidth=1.2, zorder=1)
    ax.axhline(y=90, color=_SCI_GREEN,  linestyle='--', linewidth=1.2, zorder=1)

    # Color-coded line. Higher = better. >=90 green, >=80 yellow, else red.
    def color_for(pct):
        if pct >= 90: return _SCI_GREEN
        if pct >= 80: return _SCI_YELLOW
        return _SCI_RED

    pts = list(zip(x_nums, ys))
    segments = list(zip(pts[:-1], pts[1:]))
    severity_rank = {_SCI_RED: 2, _SCI_YELLOW: 1, _SCI_GREEN: 0}
    seg_colors = []
    for a, b in segments:
        ca, cb = color_for(a[1]), color_for(b[1])
        seg_colors.append(ca if severity_rank[ca] >= severity_rank[cb] else cb)
    lc = LineCollection(segments, colors=seg_colors, linewidth=2, zorder=3)
    ax.add_collection(lc)

    for x_num, y in zip(x_nums, ys):
        c = color_for(y)
        ax.plot(x_num, y, marker='o', markersize=4,
                color=c, markerfacecolor=c, markeredgecolor=c, zorder=4)

    # Y-axis 0 to 100 with 20 ticks.
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(20))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%d %%'))

    # X-axis: small padding so endpoints aren't on the edges.
    x_span = x_nums[-1] - x_nums[0]
    x_pad = max(7, x_span * 0.015)
    ax.set_xlim(x_nums[0] - x_pad, x_nums[-1] + x_pad)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))
    ax.xaxis.set_major_formatter(DateFormatter('%m/%d/%y'))

    ax.set_title(title, fontsize=style.TITLE_FONTSIZE, loc='left',
                 pad=style.TITLE_PAD)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def render_activity_hit_rate(data, output_path):
    """Chart 10 — Activity Hit Rate (%).

    Plots `totalOnTimeHitRate` (×100). Same MCP endpoint as charts 11/12,
    different field. Color thresholds: ≥90 green, ≥80 yellow, else red.
    """
    _render_hit_rate_chart(data, output_path,
                           field='totalOnTimeHitRate',
                           title='Activity Hit Rate (%)')


def _render_window_accuracy_chart(data, output_path, *, prefix, title, on_time_label, late_label, missed_label):
    """Shared renderer for the two window-accuracy charts (11/12).

    Both are stacked bar charts with three segments per data date: on-time
    (green), late (yellow), and did-not-start-or-finish (red). The total
    activity count is labeled above each bar.

    prefix selects the field set:
      - 'started'  → startedOnTime / startedLate / didNotStart   (chart 11)
      - 'finished' → finishedOnTime / finishedLate / didNotFinish (chart 12)
    """
    raw = data.get('hitRates') or []
    if not raw:
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_title(title, fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
        fig.savefig(output_path, **style.SAVEFIG_KWARGS)
        plt.close(fig)
        return

    # Window to the trailing 12 months ending at the latest data date. Without
    # this, a multi-year project produces ~120 bars at 12in × 3in — unreadable.
    raw = sorted(raw, key=lambda p: p['dataDate'])
    latest = date.fromisoformat(raw[-1]['dataDate'][:10])
    cutoff = date(latest.year - 1, latest.month, 1)
    raw = [p for p in raw if date.fromisoformat(p['dataDate'][:10]) >= cutoff]

    on_time_field = f'{prefix}OnTime'
    late_field    = f'{prefix}Late'
    missed_field  = 'didNotStart' if prefix == 'started' else 'didNotFinish'

    xs       = [date.fromisoformat(p['dataDate'][:10]) for p in raw]
    on_time  = [int(p.get(on_time_field) or 0) for p in raw]
    late     = [int(p.get(late_field)    or 0) for p in raw]
    missed   = [int(p.get(missed_field)  or 0) for p in raw]
    totals   = [a + b + c for a, b, c in zip(on_time, late, missed)]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    # Ordinal x positions — each update gets one slot, evenly spaced.
    # SmartPM does the same: bars are not time-positioned, they're sequenced.
    # This eliminates the gaps that show up when updates aren't weekly.
    n = len(raw)
    x_idx = list(range(n))
    bar_w = 0.85

    # Stack bottom-up: red (missed) → yellow (late) → green (on time).
    ax.bar(x_idx, missed, bar_w, color=_SCI_RED, edgecolor='none', zorder=2)
    ax.bar(x_idx, late, bar_w, bottom=missed, color=_SCI_YELLOW, edgecolor='none', zorder=2)
    ax.bar(x_idx, on_time, bar_w,
           bottom=[m + l for m, l in zip(missed, late)],
           color=_SCI_GREEN, edgecolor='none', zorder=2)

    # Per-segment count labels — number on top of each colored segment.
    # Skip zero values to avoid clutter.
    y_max = max(totals + [10])
    seg_fontsize = 5
    for i, (m, l, o, t) in enumerate(zip(missed, late, on_time, totals)):
        if m > 0:
            ax.text(i, m / 2, str(m), ha='center', va='center',
                    fontsize=seg_fontsize, color='white', fontweight='bold')
        if l > 0:
            ax.text(i, m + l / 2, str(l), ha='center', va='center',
                    fontsize=seg_fontsize, color='#222')
        if o > 0:
            ax.text(i, m + l + o / 2, str(o), ha='center', va='center',
                    fontsize=seg_fontsize, color='white', fontweight='bold')
        # Total label above the bar.
        if t > 0:
            ax.text(i, t + y_max * 0.015, str(t),
                    ha='center', va='bottom', fontsize=6, color='#333')

    ax.set_ylim(0, max(y_max * 1.1, 100))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(25))

    # X-axis: pick ~14 evenly-spaced tick positions and label them with dates.
    ax.set_xlim(-0.7, n - 0.3)
    tick_step = max(1, n // 14)
    tick_positions = list(range(0, n, tick_step))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [xs[i].strftime('%m/%d/%y') for i in tick_positions],
        rotation=45, ha='right',
    )

    # SmartPM centers the title for these two charts.
    ax.set_title(title, fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    # Legend at the bottom: solid colored swatches.
    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=_SCI_GREEN,  label=on_time_label),
        Patch(facecolor=_SCI_YELLOW, label=late_label),
        Patch(facecolor=_SCI_RED,    label=missed_label),
    ]
    ax.legend(handles=legend_handles, loc='lower center',
              bbox_to_anchor=(0.5, -0.35), ncol=3,
              fontsize=8, frameon=False)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def render_window_start_accuracy(data, output_path):
    """Chart 11 — Window Start Accuracy.

    Stacked bar per data date: Started On Time (green) / Started Late (yellow)
    / Did Not Start (red). Total count labeled above each bar.
    """
    _render_window_accuracy_chart(
        data, output_path,
        prefix='started',
        title='Window Start Accuracy (Last 12 Months)',
        on_time_label='Started On Time',
        late_label='Started Late',
        missed_label='Did Not Start',
    )


def render_window_finish_accuracy(data, output_path):
    """Chart 12 — Window Finish Accuracy.

    Stacked bar per data date: Finished On Time (green) / Finished Late
    (yellow) / Did Not Finish (red). Total count labeled above each bar.
    """
    _render_window_accuracy_chart(
        data, output_path,
        prefix='finished',
        title='Window Finish Accuracy (Last 12 Months)',
        on_time_label='Finished On Time',
        late_label='Finished Late',
        missed_label='Did Not Finish',
    )


# Planned vs Actual % Complete palette — matches the SmartPM Summary Report.
_PVA_LATE_PLANNED  = '#C0223A'   # red — Late Date Planned (All Schedules)
_PVA_EARLY_PLANNED = '#3FA864'   # green — Early Date Planned (All Schedules)
_PVA_ACTUAL        = '#2E86C1'   # blue — Actual
_PVA_SCHEDULED     = '#3FA864'   # green — Scheduled Completion (markers only)
_PVA_PREDICTIVE    = '#2E86C1'   # blue — Predictive Completion (markers only)


def render_summary_plan_vs_actual(data, output_path):
    """Summary Report part 1 — Planned VS Actual Percent Complete curve.

    Mirrors the right-side curve in SmartPM's Summary Report. Five series:
      - Late Date Planned (red line)
      - Early Date Planned (green line)
      - Actual (blue line)
      - Scheduled Completion (green triangle markers — only at end of project)
      - Predictive Completion (blue diamond markers — only at end of project)

    Consumes the MCP percent_complete_curve_v2 shape directly:
      {
        "percentCompleteTypes": {...},
        "data": [
          {"DATE": "YYYY-MM-DD",
           "LATE_DATE_PLANNED": float|null,
           "ACTUAL": float|null,
           "SCHEDULED": float|null,
           "PLANNED": float|null,           # = Early Date Planned (display label)
           "PREDICTIVE": float|null},
          ...
        ]
      }
    """
    rows = data.get('data') or []
    if not rows:
        fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
        ax.set_title('Planned VS Actual Percent Complete',
                     fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
        fig.savefig(output_path, **style.SAVEFIG_KWARGS)
        plt.close(fig)
        return

    def series(field):
        """Return (xs, ys) for one series, skipping null entries."""
        xs, ys = [], []
        for r in rows:
            v = r.get(field)
            if v is None:
                continue
            xs.append(date.fromisoformat(r['DATE']))
            ys.append(float(v))
        return xs, ys

    late_xs,  late_ys  = series('LATE_DATE_PLANNED')
    early_xs, early_ys = series('PLANNED')
    act_xs,   act_ys   = series('ACTUAL')
    sch_xs,   sch_ys   = series('SCHEDULED')
    prd_xs,   prd_ys   = series('PREDICTIVE')

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)

    # Gray shaded band between Early Date Planned (green) and Late Date Planned
    # (red) — the "planning window" between the two extremes. Use rows where
    # both series have values so the fill is continuous.
    band_xs, band_lo, band_hi = [], [], []
    for r in rows:
        ldp = r.get('LATE_DATE_PLANNED')
        edp = r.get('PLANNED')
        if ldp is None or edp is None:
            continue
        band_xs.append(date.fromisoformat(r['DATE']))
        lo, hi = sorted((float(ldp), float(edp)))
        band_lo.append(lo)
        band_hi.append(hi)
    if band_xs:
        ax.fill_between(band_xs, band_lo, band_hi,
                        color=style.LIGHT_GRAY, alpha=0.6, zorder=1)

    # Lines.
    if late_xs:
        ax.plot(late_xs, late_ys, color=_PVA_LATE_PLANNED, linewidth=1.8,
                marker='o', markersize=2.5, zorder=3,
                label='Late Date Planned (All Schedules)')
    if early_xs:
        ax.plot(early_xs, early_ys, color=_PVA_EARLY_PLANNED, linewidth=1.8,
                marker='o', markersize=2.5, zorder=3,
                label='Early Date Planned (All Schedules)')
    if act_xs:
        ax.plot(act_xs, act_ys, color=_PVA_ACTUAL, linewidth=1.8,
                marker='s', markersize=2.5, zorder=4, label='Actual')

    # End-of-project markers.
    if sch_xs:
        ax.plot(sch_xs, sch_ys, color=_PVA_SCHEDULED, linestyle='none',
                marker='^', markersize=7, zorder=5, label='Scheduled Completion')
    if prd_xs:
        ax.plot(prd_xs, prd_ys, color=_PVA_PREDICTIVE, linestyle='none',
                marker='D', markersize=6, markerfacecolor='none',
                markeredgewidth=1.5, zorder=5, label='Predictive Completion')

    # Y-axis: percent, 0–105 with 25% ticks.
    ax.set_ylim(-2, 105)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(25))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%d %%'))
    ax.set_ylabel('Values', fontsize=style.LABEL_FONTSIZE)

    # X-axis: cover the full data range with a touch of padding.
    all_xs = late_xs + early_xs + act_xs + sch_xs + prd_xs
    x_min, x_max = min(all_xs), max(all_xs)
    x_pad = max(timedelta(days=7), (x_max - x_min) * 0.015)
    ax.set_xlim(x_min - x_pad, x_max + x_pad)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    ax.xaxis.set_major_formatter(DateFormatter('%m/%d/%y'))

    # SmartPM centers this title.
    ax.set_title('Planned VS Actual Percent Complete',
                 fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.set_axisbelow(True)

    # Legend at the bottom, two rows.
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.42),
              ncol=3, fontsize=7, frameon=False)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def render_summary_cards(data, output_path):
    """Summary Report part 2 — the three top cards as a single PNG.

    Layout: three side-by-side cards at 12in × 2.5in.
      1. Project Health Index — thermometer gauge (red → yellow → green) with
         the value marked by a horizontal indicator and the % label
      2. Schedule Performance — SPI + Planned/Actual bars on the left,
         Critical Path Delay + Planned Impact big-number columns on the right
      3. Schedule Feasibility — three sub-columns: Quality Grade / Compression
         Index / Predicted Completion (with previous date if provided)

    data shape:
      {
        "health": {"value": int (0-100)},
        "spi": float,
        "planned_pct": int, "actual_pct": int,
        "critical_path_delay_days": int,
        "planned_impact_days": int,
        "quality_grade": str (e.g. "A-"),
        "compression_pct": int,
        "predicted_completion": "YYYY-MM-DD",
        "last_predicted_completion": "YYYY-MM-DD"  # optional
      }
    """
    fig = plt.figure(figsize=(12, 2.5), dpi=style.DPI)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 2.2, 2.2], wspace=0.15,
                          left=0.02, right=0.98, top=0.95, bottom=0.05)

    ax_health = fig.add_subplot(gs[0])
    ax_perf   = fig.add_subplot(gs[1])
    ax_feas   = fig.add_subplot(gs[2])

    for ax in (ax_health, ax_perf, ax_feas):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

    card_bg = '#F5F5F5'
    title_y = 0.95
    title_fs = 11

    def rounded_card(ax, x, y, w, h):
        """Add a rounded-corner gray card background."""
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0,rounding_size=0.03",
            facecolor=card_bg, edgecolor='none', zorder=0,
            mutation_aspect=1.0,
        ))

    # ===== Card 1: Project Health Index =====
    ax_health.text(0.5, title_y, 'Project Health Index™',
                   ha='center', va='top',
                   fontsize=title_fs, fontweight='bold')
    # Vertical thermometer: red (0-50), yellow (50-75), green (75-100).
    gx0, gx1 = 0.45, 0.55
    gy0, gy1 = 0.10, 0.85
    bands = [(_SCI_RED, 0.0, 0.50), (_SCI_YELLOW, 0.50, 0.75),
             (_SCI_GREEN, 0.75, 1.00)]
    for color, lo, hi in bands:
        y_lo = gy0 + (gy1 - gy0) * lo
        y_hi = gy0 + (gy1 - gy0) * hi
        ax_health.add_patch(Rectangle((gx0, y_lo), gx1 - gx0, y_hi - y_lo,
                                       facecolor=color, edgecolor='none'))
    # Indicator
    health_val = float(data['health']['value'])
    ind_y = gy0 + (gy1 - gy0) * health_val / 100
    ax_health.plot([gx0 - 0.07, gx1 + 0.07], [ind_y, ind_y],
                   color='#222', linewidth=2.0)
    # Value label to the left in the band's color.
    health_color = (_SCI_GREEN if health_val >= 75
                    else _SCI_YELLOW if health_val >= 50
                    else _SCI_RED)
    ax_health.text(gx0 - 0.10, ind_y, f'{int(health_val)}%',
                   ha='right', va='center', fontsize=14,
                   color=health_color, fontweight='bold')

    # ===== Card 2: Schedule Performance =====
    ax_perf.text(0.03, title_y, 'Schedule Performance', ha='left', va='top',
                 fontsize=title_fs, fontweight='bold')
    rounded_card(ax_perf, 0.01, 0.05, 0.98, 0.78)

    # Shared vertical anchors. Sub-labels are two lines; they're centered
    # vertically on label_y. Big numbers and units sit at their own anchors so
    # everything across cards 2/3 lines up horizontally.
    label_y      = 0.65   # vertical center of all 2-line sub-labels
    big_value_y  = 0.32   # all big numbers sit here
    unit_y       = 0.12   # "Days" / year / delta arrow

    spi_val = float(data['spi'])
    ax_perf.text(0.05, label_y, f'SPI  {spi_val:.2f}', ha='left', va='center',
                 fontsize=11, color='#333', fontweight='bold')

    planned_pct = int(data['planned_pct'])
    actual_pct  = int(data['actual_pct'])
    bar_x0   = 0.05
    bar_w    = 0.35
    # Planned bar (red)
    ax_perf.text(0.05, 0.52, f'Planned ({planned_pct}%)',
                 ha='left', va='center', fontsize=9, color='#444')
    ax_perf.add_patch(Rectangle((bar_x0, 0.40), bar_w * planned_pct / 100, 0.07,
                                 facecolor=_SMARTPM_RED, edgecolor='none', zorder=2))
    # Actual bar (green)
    ax_perf.text(0.05, 0.27, f'Actual ({actual_pct}%)',
                 ha='left', va='center', fontsize=9, color='#444')
    ax_perf.add_patch(Rectangle((bar_x0, 0.15), bar_w * actual_pct / 100, 0.07,
                                 facecolor=_SCI_GREEN, edgecolor='none', zorder=2))

    # Right side: two big-number columns.
    cpd = int(data['critical_path_delay_days'])
    pi  = int(data['planned_impact_days'])
    ax_perf.text(0.62, label_y, 'Critical Path\nDelay',
                 ha='center', va='center', fontsize=9, color='#444',
                 linespacing=1.2)
    ax_perf.text(0.62, big_value_y, str(cpd), ha='center', va='center',
                 fontsize=20, fontweight='bold', color='#222')
    ax_perf.text(0.62, unit_y, 'Days', ha='center', va='center',
                 fontsize=9, color='#444')

    ax_perf.text(0.88, label_y, 'Planned\nImpact',
                 ha='center', va='center', fontsize=9, color='#444',
                 linespacing=1.2)
    ax_perf.text(0.88, big_value_y, str(pi), ha='center', va='center',
                 fontsize=20, fontweight='bold', color='#222')
    ax_perf.text(0.88, unit_y, 'Days', ha='center', va='center',
                 fontsize=9, color='#444')

    # ===== Card 3: Schedule Feasibility =====
    ax_feas.text(0.03, title_y, 'Schedule Feasibility', ha='left', va='top',
                 fontsize=title_fs, fontweight='bold')
    rounded_card(ax_feas, 0.01, 0.05, 0.98, 0.78)

    qg = str(data['quality_grade'])
    comp = int(data['compression_pct'])
    pc_str = data['predicted_completion']
    last_pc_str = data.get('last_predicted_completion')

    # Quality Grade
    ax_feas.text(0.18, label_y, 'Schedule\nQuality Grade™',
                 ha='center', va='center', fontsize=9, color='#444',
                 linespacing=1.2)
    qg_color = _SCI_GREEN if qg.upper().startswith(('A', 'B')) else _SCI_RED
    ax_feas.text(0.18, big_value_y, qg, ha='center', va='center',
                 fontsize=22, fontweight='bold', color=qg_color)

    # Compression Index
    ax_feas.text(0.48, label_y, 'Schedule Compression\nIndex™',
                 ha='center', va='center', fontsize=9, color='#444',
                 linespacing=1.2)
    comp_color = (_SCI_RED if comp >= 25 else
                  _SCI_YELLOW if comp >= 15 else _SCI_GREEN)
    ax_feas.text(0.48, big_value_y, f'{comp}%', ha='center', va='center',
                 fontsize=20, fontweight='bold', color=comp_color)

    # Predicted Completion — headline date in green (matches SmartPM's style),
    # previous date in red+▲ when the schedule slipped (new date later) and
    # green+▼ when it recovered (new date earlier).
    pc = date.fromisoformat(pc_str)
    ax_feas.text(0.80, label_y, 'Predicted\nCompletion',
                 ha='center', va='center', fontsize=9, color='#444',
                 linespacing=1.2)
    ax_feas.text(0.80, big_value_y + 0.16, pc.strftime('%b'),
                 ha='center', va='center', fontsize=10, color=_SCI_GREEN)
    ax_feas.text(0.80, big_value_y, pc.strftime('%d'),
                 ha='center', va='center', fontsize=20, fontweight='bold',
                 color=_SCI_GREEN)
    ax_feas.text(0.80, big_value_y - 0.14, pc.strftime('%Y'),
                 ha='center', va='center', fontsize=9, color=_SCI_GREEN)
    if last_pc_str:
        last_pc = date.fromisoformat(last_pc_str)
        slipped = pc > last_pc       # new predicted date is LATER than last week's
        delta_color = _SCI_RED if slipped else _SCI_GREEN
        arrow = '▲' if slipped else '▼'
        ax_feas.text(0.80, unit_y, f'{arrow} {last_pc.strftime("%b %d, %Y")}',
                     ha='center', va='center', fontsize=8, color=delta_color)

    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


def render_summary_milestones(data, output_path):
    """Summary Report — left-side panel: header + milestones table + changes.

    Recreates the left half of the SmartPM v2 Summary Report card. Layout:

      Header (4 bold-label lines):
        Project Name:     <name>
        Milestone Name:   <scenario name>
        Project Location: <city, state>
        Data Date:        MM/DD/YY

      Milestones table (Order / Milestone / Contractual / Current /
        Days Late / Predicted / Compression). One row per milestone scenario.

      Selected Period Critical Path Delays: <count>
        • <activity bullet>          (one per item)

      Last Period Critical Path Recoveries: <count or N/A>
        • <activity bullet>

      Last Period Schedule Changes
        Total Changes: N    Critical Path Changes: N    Acceleration Days: N

    Most fields are populated from smartpm_post_project_summary called once per
    milestone scenario (the project's defaultScenarioId for row 1, and any
    sibling COMPLETE-type scenarios for additional rows). Project Location
    comes from smartpm_get_project. The critical-path-delay/recovery bullet
    content and the Last Period Schedule Changes triplet aren't exposed by
    the post endpoint — phase file pulls those from
    smartpm_list_scenario_change_log_by_type and passes them in via the
    `critical_path_delays.items` and `last_period_changes` fields.

    data shape:
      {
        "project_name":     str,
        "milestone_name":   str,
        "project_location": str,
        "data_date":        "YYYY-MM-DD",
        "milestones": [
          {"order": int, "name": str,
           "contractual": "YYYY-MM-DD"|null,
           "current":     "YYYY-MM-DD",
           "days_late":   int,
           "predicted":   "YYYY-MM-DD",
           "compression_pct": int},
          ...
        ],
        "critical_path_delays":     {"count": int, "items": [str, ...]},
        "critical_path_recoveries": {"count": int, "items": [str, ...]},
        "last_period_changes": {
          "total": int, "critical_path": int, "acceleration_days": int|null
        }
      }
    """
    milestones = data.get('milestones', [])
    cpd  = data.get('critical_path_delays')     or {'count': 0, 'items': []}
    cpr  = data.get('critical_path_recoveries') or {'count': 0, 'items': []}
    lpc  = data.get('last_period_changes')      or {}

    def _fmt_date(s):
        """ISO YYYY-MM-DD → MM/DD/YY (or 'N/A' for None/empty)."""
        if not s:
            return 'N/A'
        try:
            d = date.fromisoformat(s[:10])
            return d.strftime('%m/%d/%y')
        except Exception:
            return str(s)[:10]

    n_delay_bullets = min(len(cpd.get('items', []) or []), 6)
    n_recov_bullets = min(len(cpr.get('items', []) or []), 6)
    n_milestone_rows = max(1, len(milestones))

    # Heights — header is fixed, table grows with rows, bottom grows with bullets.
    header_h = 0.95
    table_h  = 0.55 + 0.35 * n_milestone_rows
    bottom_h = 1.5 + 0.22 * (n_delay_bullets + n_recov_bullets)
    total_h  = max(4.0, header_h + table_h + bottom_h + 0.4)

    fig = plt.figure(figsize=(12, total_h), dpi=style.DPI)
    gs = fig.add_gridspec(
        3, 1,
        height_ratios=[header_h, table_h, bottom_h],
        hspace=0.15, left=0.02, right=0.98, top=0.97, bottom=0.03,
    )

    # ===== Header (Project Name / Milestone Name / Location / Data Date) =====
    ax_hdr = fig.add_subplot(gs[0])
    ax_hdr.axis('off')
    ax_hdr.set_xlim(0, 1)
    ax_hdr.set_ylim(0, 1)

    header_lines = [
        ('Project Name: ',     data.get('project_name') or ''),
        ('Milestone Name: ',   data.get('milestone_name') or ''),
        ('Project Location: ', data.get('project_location') or ''),
        ('Data Date: ',        _fmt_date(data.get('data_date'))),
    ]
    y = 0.92
    line_gap = 0.22
    for label, value in header_lines:
        ax_hdr.text(0.005, y, label, ha='left', va='top',
                    fontsize=10, fontweight='bold', color='#222')
        # Measure the label width visually by placing the value at a fixed offset.
        ax_hdr.text(0.005 + 0.012 * len(label), y, str(value),
                    ha='left', va='top', fontsize=10, color='#333')
        y -= line_gap

    # ===== Milestones table =====
    ax_tbl = fig.add_subplot(gs[1])
    ax_tbl.axis('off')

    headers = ['Order', 'Milestone', 'Contractual', 'Current', 'Days Late',
               'Predicted', 'Compression']
    cell_text = []
    cell_colors = []
    for m in milestones:
        days_late = m.get('days_late') or 0
        compress  = m.get('compression_pct') or 0

        cell_text.append([
            str(m.get('order', '')),
            m.get('name', ''),
            _fmt_date(m.get('contractual')),
            _fmt_date(m.get('current')),
            str(days_late),
            _fmt_date(m.get('predicted')),
            f"{compress}%",
        ])
        # SmartPM screenshot doesn't tint rows — keep cells plain white.
        cell_colors.append(['white'] * 7)

    if not cell_text:
        cell_text   = [['—'] * 7]
        cell_colors = [['white'] * 7]

    table = ax_tbl.table(
        cellText=cell_text,
        cellColours=cell_colors,
        colLabels=headers,
        cellLoc='left',
        colLoc='left',
        loc='upper center',
        colWidths=[0.06, 0.36, 0.10, 0.10, 0.10, 0.10, 0.12],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)

    for col_idx in range(len(headers)):
        h_cell = table[(0, col_idx)]
        h_cell.set_facecolor('#F2F2F2')
        h_cell.set_text_props(color='#222', fontweight='bold')

    # ===== Bottom: Selected Period delays + Last Period Recoveries + Changes =====
    ax_chg = fig.add_subplot(gs[2])
    ax_chg.axis('off')
    ax_chg.set_xlim(0, 1)
    ax_chg.set_ylim(0, 1)

    y_cursor = 0.95
    row_gap  = 0.11

    # Selected Period Critical Path Delays
    cpd_count = int(cpd.get('count', 0) or 0)
    ax_chg.text(0.005, y_cursor, 'Selected Period Critical Path Delays: ',
                ha='left', va='top', fontsize=10, fontweight='bold', color='#222')
    ax_chg.text(0.30, y_cursor, str(cpd_count),
                ha='left', va='top', fontsize=10, fontweight='bold', color='#222')
    # "Last Period Critical Path Recoveries" lives on the same line, far right.
    cpr_count = int(cpr.get('count', 0) or 0)
    cpr_label = 'N/A' if cpr_count == 0 else str(cpr_count)
    ax_chg.text(0.50, y_cursor, 'Last Period Critical Path Recoveries: ',
                ha='left', va='top', fontsize=10, fontweight='bold', color='#222')
    ax_chg.text(0.83, y_cursor, cpr_label,
                ha='left', va='top', fontsize=10, fontweight='bold', color='#222')
    y_cursor -= row_gap

    # Bullets under each side, max 6 each.
    delay_items = (cpd.get('items') or [])[:6]
    recov_items = (cpr.get('items') or [])[:6]
    n_bullet_rows = max(len(delay_items), len(recov_items))
    for i in range(n_bullet_rows):
        if i < len(delay_items):
            ax_chg.text(0.025, y_cursor, f'•  {delay_items[i]}',
                        ha='left', va='top', fontsize=9, color='#333')
        if i < len(recov_items):
            ax_chg.text(0.52, y_cursor, f'•  {recov_items[i]}',
                        ha='left', va='top', fontsize=9, color='#333')
        y_cursor -= row_gap

    # Last Period Schedule Changes (small header + triplet line)
    y_cursor -= 0.04
    ax_chg.text(0.005, y_cursor, 'Last Period Schedule Changes',
                ha='left', va='top', fontsize=10, fontweight='bold', color='#222')
    y_cursor -= row_gap

    total = lpc.get('total', 0) or 0
    cp    = lpc.get('critical_path', 0) or 0
    accel = lpc.get('acceleration_days')
    accel_str = 'N/A' if accel is None else str(accel)

    ax_chg.text(0.005, y_cursor, f'Total Changes:  {total}',
                ha='left', va='top', fontsize=10, color='#333')
    ax_chg.text(0.30, y_cursor, f'Critical Path Changes:  {cp}',
                ha='left', va='top', fontsize=10, color='#333')
    ax_chg.text(0.60, y_cursor, f'Acceleration Days:  {accel_str}',
                ha='left', va='top', fontsize=10, color='#333')

    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)


# =====================================================================
# Stubs for the 9 non-default trend graphs (slugs 01-05 and 13-16).
#
# v1 ships the 7 default trends (06-12) + the SmartPM Summary Report parts
# (smartpm-summary-{curve,cards,milestones}). A project whose
# graph_screenshots list includes a non-default slug hits one of these
# stubs, which fail loudly with a NotImplementedError pointing at
# `/schedule-update screenshots --legacy` as the fallback path.
# Implement the real render functions in place of each stub as needed.
# =====================================================================

def _stub(slug, description):
    """Build a stub render function that raises NotImplementedError with a
    clear path forward (use --legacy)."""
    def _render(data, output_path):
        raise NotImplementedError(
            f'Chart {slug} ({description}) is not yet implemented in the '
            f'matplotlib path. Use `/schedule-update screenshots --legacy` '
            f'to capture this chart via Playwright until a render function '
            f'is added.'
        )
    _render.__name__ = f'render_{slug.replace("-", "_")}'
    return _render


render_planned_vs_actual_percent_complete = _stub(
    '01-planned-vs-actual-percent-complete',
    'Planned VS Actual Percent Complete')
render_schedule_quality_grade_over_time = _stub(
    '02-schedule-quality-grade-over-time',
    'Schedule Quality Grade Over Time')
render_project_health_index_over_time = _stub(
    '03-project-health-index-over-time',
    'Project Health Index Over Time')
render_schedule_changes_over_time = _stub(
    '04-schedule-changes-over-time',
    'Schedule Changes Over Time')
render_schedule_delay_over_time = _stub(
    '05-schedule-delay-over-time',
    'Schedule Delay Over Time')
render_missing_logic = _stub(
    '13-missing-logic', 'Missing Logic')
render_average_total_float = _stub(
    '14-average-total-float', 'Average Total Float')
render_high_total_float = _stub(
    '15-high-total-float', 'High Total Float')
render_critical_path_percentage = _stub(
    '16-critical-path-percentage', 'Critical Path Percentage')
