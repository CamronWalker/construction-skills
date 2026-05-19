"""Schedule update chart renderer — MCP JSON → matplotlib PNG."""

import matplotlib
matplotlib.use('Agg')  # headless; must be set before pyplot is imported anywhere
