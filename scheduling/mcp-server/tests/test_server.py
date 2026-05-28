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

    def test_one_tool_from_each_module_is_registered(self):
        """Catches typos in server.py's register() calls. If a module's
        register(mcp, cache) gets dropped, this fails immediately rather
        than waiting for an end-to-end smoke test."""
        tool_names = self._list_tool_names(server.mcp)
        expected_representatives = {
            "structure": "get_milestones",
            "structure_invalidate": "invalidate_cache_for",
            "cpm_path": "get_critical_path",
            "quality": "get_quality_check",
            "update_review": "get_activities_to_start",
            "compare": "compare_activity_changes",
            "omnibus": "weekly_update_review",
            "update_analytics": "get_critical_path_changes",   # Plan 2
            "delay_analysis": "compute_tia",                   # Plan 2
            "xer_validate_main": "validate_xer_structure",     # Plan 3
            "xer_modify": "apply_xer_changes",                  # Plan 3
        }
        missing = [
            name for name in expected_representatives.values()
            if name not in tool_names
        ]
        self.assertEqual(
            missing, [],
            f"Tools missing from server registration: {missing}. "
            f"Check server.py imports + register() calls.",
        )

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
