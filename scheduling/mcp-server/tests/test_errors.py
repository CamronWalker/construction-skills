"""Tests for the new error classes added in Plan 3."""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from errors import (  # noqa: E402
    CachePinExhaustedError,
    XerLockedError,
    XerTemplateError,
    XerValidationError,
)


class TestErrorClasses(unittest.TestCase):
    def test_cache_pin_exhausted_is_exception(self):
        e = CachePinExhaustedError("too many pins")
        self.assertIsInstance(e, Exception)

    def test_xer_validation_error_carries_report(self):
        e = XerValidationError("bad XER", report={"errors": 3})
        self.assertEqual(e.report["errors"], 3)

    def test_xer_validation_error_default_report(self):
        e = XerValidationError("bad XER")
        self.assertEqual(e.report, {})

    def test_xer_template_error_is_exception(self):
        e = XerTemplateError("template not found")
        self.assertIsInstance(e, Exception)

    def test_existing_xer_locked_error_still_works(self):
        # Make sure the new imports don't break existing error class
        e = XerLockedError("locked")
        self.assertIsInstance(e, Exception)


if __name__ == "__main__":
    unittest.main()
