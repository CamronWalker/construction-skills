"""MCP wrapper tests for validate_xer_structure."""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools.xer_validate import validate_xer_structure_impl  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class TestValidateXerStructureWrapper(unittest.TestCase):
    def test_clean_fixture_is_import_ready(self):
        cache = CpmCache()
        result = validate_xer_structure_impl(str(FIXTURES / "minimal.xer"), cache)
        self.assertTrue(result["import_ready"])
        self.assertEqual(result["summary"]["errors"], 0)

    def test_duplicate_fixture_reports_issue(self):
        cache = CpmCache()
        result = validate_xer_structure_impl(str(FIXTURES / "duplicate_ids.xer"), cache)
        self.assertFalse(result["import_ready"])
        codes = [i["code"] for i in result["issues"]]
        self.assertIn("DUPLICATE_ACTIVITY_ID", codes)

    def test_issue_shape(self):
        cache = CpmCache()
        result = validate_xer_structure_impl(str(FIXTURES / "duplicate_ids.xer"), cache)
        issue = result["issues"][0]
        self.assertIn("severity", issue)
        self.assertIn("category", issue)
        self.assertIn("code", issue)
        self.assertIn("message", issue)
        self.assertIn("affected", issue)


if __name__ == "__main__":
    unittest.main()
