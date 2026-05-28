"""Westland Scheduler Local MCP server entry point."""
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Make sibling modules (cache, tools/) importable when launched as a script.
sys.path.insert(0, str(Path(__file__).parent))

from cache import CpmCache  # noqa: E402
from tools import (  # noqa: E402
    compare,
    cpm_path,
    delay_analysis,
    omnibus,
    quality,
    structure,
    update_analytics,
    update_review,
    xer_validate,
)

mcp = FastMCP("westland-scheduler-mcp")
_cache = CpmCache()


@mcp.tool()
def ping() -> dict:
    """Health check tool. Always returns {ok: true}."""
    return {"ok": True}


# Register all tool modules.
structure.register(mcp, _cache)
cpm_path.register(mcp, _cache)
update_analytics.register(mcp, _cache)
delay_analysis.register(mcp, _cache)
quality.register(mcp, _cache)
update_review.register(mcp, _cache)
compare.register(mcp, _cache)
omnibus.register(mcp, _cache)
xer_validate.register(mcp, _cache)


if __name__ == "__main__":
    mcp.run()
