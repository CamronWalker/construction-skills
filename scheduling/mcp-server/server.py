"""Westland Scheduler Local MCP server entry point."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("westland-scheduler-mcp")


@mcp.tool()
def ping() -> dict:
    """Health check tool. Always returns {ok: true}."""
    return {"ok": True}


if __name__ == "__main__":
    mcp.run()
