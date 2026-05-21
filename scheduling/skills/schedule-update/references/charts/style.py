"""Shared visual constants for the schedule update chart renderer.

Pure data — no functions that draw stuff. Each chart in charts.py imports
this module and reads what it needs.
"""

# SmartPM-feeling palette
TEAL      = '#0E7C7B'   # primary (planned, target)
ORANGE    = '#D8732E'   # secondary (actual, variance)
RED       = '#C94444'   # alerts / behind
GREEN     = '#3A9E6B'   # ahead / good
GRAY      = '#6B7280'   # baseline / grid
LIGHT_GRAY = '#E5E7EB'  # gridlines

# Figure geometry — wide-and-short for the email column
FIGSIZE        = (12, 3)
DPI            = 144
FONT_FAMILY    = 'Calibri'   # falls back to mpl default if missing
TITLE_FONTSIZE = 13
LABEL_FONTSIZE = 10
TICK_FONTSIZE  = 9
TITLE_PAD      = 10

SAVEFIG_KWARGS = dict(
    bbox_inches='tight',
    facecolor='white',
    edgecolor='none',
)
