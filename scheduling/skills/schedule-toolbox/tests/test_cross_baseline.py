"""Tests for ``lib/cross_baseline.py`` -- the cross-XER CPM-aware analytics.

Each function tests against the Plan 2 fixtures (see
``scheduling/mcp-server/tests/fixtures/``). The tests use the CpmCache to
parse + CPM each fixture so the inputs match what the MCP layer will pass.
"""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

SERVER_DIR = Path(__file__).parent.parent.parent.parent / "mcp-server"
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from cross_baseline import (  # noqa: E402
    compute_critical_path_changes,
    compute_float_consumption,
    compute_gain_loss_attribution,
    compute_trade_slip_summary,
)

FIXTURES = SERVER_DIR / "tests" / "fixtures"
