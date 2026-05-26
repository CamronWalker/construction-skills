"""Cross-baseline (week-over-week) CPM-aware analytics.

The functions in this module take pre-parsed and pre-CPM'd table dicts for
both a baseline and a current XER and return structured analytics dicts.
They DO NOT parse XERs or run CPM themselves -- callers (the MCP cache, the
schedule-update phase scripts, ad-hoc REPL usage) are responsible for
producing the inputs. That separation keeps the lib functions cheap to
unit-test in isolation: pass two parsed dicts + two CPM result tuples + a
milestone_id and assert the output dict.

The four functions in this module each answer a different update-analytics
question:

* :func:`compute_critical_path_changes` -- which activities moved on/off
  the critical path week over week.
* :func:`compute_float_consumption` -- per-activity float delta.
* :func:`compute_trade_slip_summary` -- group date-slip rows by trade
  (resolved from an activity-code field).
* :func:`compute_gain_loss_attribution` -- categorize SC-milestone slip
  contributors by cause (operational realized delay vs. plan-change delay).
"""
from __future__ import annotations

from typing import Optional

from cpm_engine import extract_paths
from milestones import MilestoneAmbiguousError, get_milestones
from xer_compare import compare_xer_pair
