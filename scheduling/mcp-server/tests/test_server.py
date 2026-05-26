# scheduling/mcp-server/tests/test_server.py
import sys
import unittest
from pathlib import Path

# Add the mcp-server directory to sys.path so we can import server.py
SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

import server  # noqa: E402


class TestServer(unittest.TestCase):
    def test_server_instance_exists(self):
        self.assertIsNotNone(server.mcp)

    def test_ping_tool_registered(self):
        # Verify the ping tool is registered. FastMCP API surface may
        # use a different method name across versions; try the common ones.
        tool_names = self._list_tool_names(server.mcp)
        self.assertIn("ping", tool_names)

    def _list_tool_names(self, mcp_instance):
        # FastMCP API varies. Try the documented methods in order.
        # If the test fails here, inspect the FastMCP API and update.
        if hasattr(mcp_instance, "list_tools"):
            tools = mcp_instance.list_tools()
            # list_tools may be a coroutine in async APIs
            if hasattr(tools, "__await__"):
                import asyncio
                tools = asyncio.run(tools)
            return [t.name for t in tools]
        if hasattr(mcp_instance, "_tools"):
            return list(mcp_instance._tools.keys())
        if hasattr(mcp_instance, "tools"):
            return list(mcp_instance.tools.keys())
        raise AssertionError(f"Cannot enumerate tools on {type(mcp_instance)}")


if __name__ == "__main__":
    unittest.main()
