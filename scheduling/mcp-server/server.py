"""Westland Scheduler Local MCP server entry point."""
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Make sibling modules (cache, tools/) importable when launched as a script.
sys.path.insert(0, str(Path(__file__).parent))

from cache import CpmCache  # noqa: E402
from tools import structure  # noqa: E402

mcp = FastMCP("westland-scheduler-mcp")
_cache = CpmCache()


@mcp.tool()
def ping() -> dict:
    """Health check tool. Always returns {ok: true}."""
    return {"ok": True}


# Register all tool modules.
structure.register(mcp, _cache)


if __name__ == "__main__":
    mcp.run()
