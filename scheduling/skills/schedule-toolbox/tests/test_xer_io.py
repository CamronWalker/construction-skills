"""Tests for the round-trip-safe XER I/O module."""
import os
import sys
import tempfile
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


class TestRoundTrip(unittest.TestCase):
    """Zero-mutation = zero-byte-change. Parse and rewrite each corpus
    XER, assert the bytes are byte-identical."""

    def setUp(self):
        self.fixture_root = (
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures"
        )

    def _round_trip(self, name: str):
        from xer_io import parse_for_writing, write
        src = self.fixture_root / name
        doc = parse_for_writing(str(src))
        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            write(doc, str(out))
            self.assertEqual(src.read_bytes(), out.read_bytes(),
                             f"{name} did not round-trip byte-identical")
        finally:
            out.unlink(missing_ok=True)

    def test_minimal_round_trip(self):
        self._round_trip("minimal.xer")

    def test_cp_baseline_round_trip(self):
        self._round_trip("cp_baseline.xer")

    def test_tia_baseline_round_trip(self):
        self._round_trip("tia_baseline.xer")


class TestMutation(unittest.TestCase):
    def test_mutating_one_field_preserves_everything_else(self):
        from xer_io import parse_for_writing, write
        src = (
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        )
        doc1 = parse_for_writing(str(src))
        # Mutate task_name of first task; mark dirty
        task = doc1.section("TASK")
        original_name = task.rows[0]["task_name"]
        task.rows[0]["task_name"] = "MUTATED"
        task.mark_dirty(0)

        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            write(doc1, str(out))
            doc2 = parse_for_writing(str(out))
            self.assertEqual(doc2.section("TASK").rows[0]["task_name"], "MUTATED")
            # Every other row in TASK should be byte-identical to source
            src_doc = parse_for_writing(str(src))
            src_task = src_doc.section("TASK")
            for i in range(1, len(task.rows)):
                self.assertEqual(task.rows[i], src_task.rows[i],
                                 f"row {i} was unexpectedly mutated")
        finally:
            out.unlink(missing_ok=True)

    def test_appending_row_writes_back_correctly(self):
        from xer_io import parse_for_writing, write
        src = (
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        )
        doc1 = parse_for_writing(str(src))
        task = doc1.section("TASK")
        new_row = {f: "" for f in task.field_order}
        new_row["task_id"] = "99999"
        new_row["task_name"] = "Appended Task"
        new_row["task_code"] = "A9999"
        task.append_row(new_row)

        with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            write(doc1, str(out))
            doc2 = parse_for_writing(str(out))
            ids = [r["task_id"] for r in doc2.section("TASK").rows]
            self.assertIn("99999", ids)
        finally:
            out.unlink(missing_ok=True)


class TestCorpusRoundTrip(unittest.TestCase):
    """Round-trips every proposal corpus XER. Skipped in CI; runs locally
    when WESTLAND_CORPUS env var points at the corpus root."""

    CORPUS_FILES = [
        "BTLP.xer", "CVTH.xer", "MMHS.xer", "NSD-WE.xer",
        "NSSD-HS-AC.xer", "RCSP.xer", "TES-BESD.xer",
    ]

    @unittest.skipUnless(
        os.environ.get("WESTLAND_CORPUS"),
        "Set WESTLAND_CORPUS to corpus root to run corpus round-trip tests"
    )
    def test_all_corpus_files_round_trip(self):
        from xer_io import parse_for_writing, write
        corpus_root = Path(os.environ["WESTLAND_CORPUS"]) / "Proposal Schedules"
        for name in self.CORPUS_FILES:
            with self.subTest(file=name):
                src = corpus_root / name
                if not src.exists():
                    self.skipTest(f"{name} not in corpus")
                doc = parse_for_writing(str(src))
                with tempfile.NamedTemporaryFile(suffix=".xer", delete=False) as tmp:
                    out = Path(tmp.name)
                try:
                    write(doc, str(out))
                    self.assertEqual(src.read_bytes(), out.read_bytes(),
                                     f"{name} did not round-trip byte-identical")
                finally:
                    out.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
