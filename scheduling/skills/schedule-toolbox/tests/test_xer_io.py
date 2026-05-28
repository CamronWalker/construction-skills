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


if __name__ == "__main__":
    unittest.main()
