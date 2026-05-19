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
from matplotlib.collections import LineCollection
from matplotlib.dates import DateFormatter

from . import style


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

    data shape:
      {
        "updates": [
          {"data_date": "YYYY-MM-DD", "projected_finish": "YYYY-MM-DD"},
          ...
        ],
        "contractual_completion": "YYYY-MM-DD"
      }
    """
    all_updates = data['updates']
    contractual = date.fromisoformat(data['contractual_completion'])

    # Display only the latest 9 updates. If anything older exists, we'll add
    # an "earlier updates" hint so the viewer knows this is a windowed view.
    visible = all_updates[-9:]
    has_older = len(all_updates) > len(visible)

    xs = [date.fromisoformat(u['data_date']) for u in visible]
    finishes = [date.fromisoformat(u['projected_finish']) for u in visible]
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
