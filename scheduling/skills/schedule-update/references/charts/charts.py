"""One render function per graph. Each takes (data: dict, output_path: str) → None.

Each function is self-contained: it knows its data shape, its chart type, its
title, axes, and styling. They don't share a base function — duplication is
intentional so each chart can be tweaked in isolation without risk of breaking
its neighbors.
"""

from datetime import date, timedelta

import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

from . import style


# SmartPM Summary-style palette — used to match the look of the existing screenshots.
_SMARTPM_RED          = '#C0223A'
_SMARTPM_PINK_FILL    = '#FBE6EA'
_SMARTPM_GREEN_FILL   = '#E8F1ED'
_SMARTPM_LABEL_BG     = '#FBE6EA'


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
