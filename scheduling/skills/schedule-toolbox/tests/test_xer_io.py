"""Tests for the round-trip-safe XER I/O module."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_io import XerDoc, XerSection  # noqa: E402


class TestDataModel(unittest.TestCase):
    def test_empty_xerdoc_has_no_sections(self):
        doc = XerDoc(header_line="ERMHDR\t1.0", encoding="cp1252", sections=[])
        self.assertEqual(doc.sections, [])
        self.assertEqual(doc.encoding, "cp1252")

    def test_section_tracks_dirty_bits(self):
        s = XerSection(
            name="TASK",
            field_order=["task_id", "task_name"],
            rows=[{"task_id": "1", "task_name": "Start"}],
            raw_lines=["%R\t1\tStart"],
            e_line="%E",
        )
        self.assertFalse(s.is_dirty(0))
        s.mark_dirty(0)
        self.assertTrue(s.is_dirty(0))

    def test_appending_row_marks_dirty(self):
        s = XerSection(
            name="TASK",
            field_order=["task_id", "task_name"],
            rows=[{"task_id": "1", "task_name": "Start"}],
            raw_lines=["%R\t1\tStart"],
            e_line="%E",
        )
        s.append_row({"task_id": "2", "task_name": "End"})
        self.assertEqual(len(s.rows), 2)
        # New row index 1 has no raw_lines[1] -> always dirty
        self.assertTrue(s.is_dirty(1))


class TestParseForWriting(unittest.TestCase):
    def setUp(self):
        # Use Plan 1's minimal.xer fixture which has known structure
        self.fixture = (
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        )

    def test_parses_header_line(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(self.fixture))
        self.assertTrue(doc.header_line.startswith("ERMHDR"))

    def test_detects_encoding(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(self.fixture))
        self.assertIn(doc.encoding, ("cp1252", "utf-8-sig", "utf-8", "latin-1"))

    def test_preserves_section_order(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(self.fixture))
        names = [s.name for s in doc.sections]
        # PROJECT must come before TASK in every P6 XER
        self.assertLess(names.index("PROJECT"), names.index("TASK"))

    def test_preserves_field_order(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(self.fixture))
        task = doc.section("TASK")
        self.assertIsNotNone(task)
        # task_id is always first in TASK %F
        self.assertEqual(task.field_order[0], "task_id")

    def test_preserves_raw_lines(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(self.fixture))
        task = doc.section("TASK")
        self.assertIsNotNone(task.raw_lines)
        self.assertEqual(len(task.raw_lines), len(task.rows))


if __name__ == "__main__":
    unittest.main()
