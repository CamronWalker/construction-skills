"""Tests for the fix_duplicate_activity_ids MCP wrapper (tools/xer_modify.py).

Uses duplicate_ids.xer as the fixture.  That fixture has three TASK rows all
sharing task_code "A1010".  Temp files are written to a system temp directory
(outside the project tree) so the PreToolUse XER hook is not triggered.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Make mcp-server modules importable.
SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools.xer_modify import fix_duplicate_activity_ids_impl  # noqa: E402

LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from xer_io import parse_for_writing  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "duplicate_ids.xer"


class TestFixDuplicateActivityIdsReportOnly(unittest.TestCase):
    """report_only: no file written, mapping populated, input unchanged."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_path_null(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="report_only", cache=self.cache
        )
        self.assertIsNone(result["output_path"])

    def test_duplicates_found_greater_than_zero(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="report_only", cache=self.cache
        )
        self.assertGreater(result["duplicates_found"], 0)

    def test_mapping_populated(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="report_only", cache=self.cache
        )
        self.assertIsInstance(result["mapping"], list)
        self.assertGreater(len(result["mapping"]), 0)
        entry = result["mapping"][0]
        self.assertIn("original_id", entry)
        self.assertIn("new_id", entry)
        self.assertIn("task_name", entry)
        self.assertIn("reason", entry)

    def test_no_file_written(self):
        fix_duplicate_activity_ids_impl(
            self.src, strategy="report_only", cache=self.cache
        )
        default_out = os.path.join(self.tmpdir, "source-fixed.xer")
        self.assertFalse(os.path.exists(default_out))

    def test_input_file_unchanged(self):
        original_size = os.path.getsize(self.src)
        fix_duplicate_activity_ids_impl(
            self.src, strategy="report_only", cache=self.cache
        )
        self.assertEqual(os.path.getsize(self.src), original_size)


class TestFixDuplicateActivityIdsRenumber(unittest.TestCase):
    """renumber: output file written with no duplicate task_codes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_file_created(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        self.assertIsNotNone(result["output_path"])
        self.assertTrue(os.path.exists(result["output_path"]))

    def test_output_path_returned(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        expected = os.path.join(self.tmpdir, "source-fixed.xer")
        self.assertEqual(result["output_path"], expected)

    def test_mapping_records_renames(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        self.assertGreater(len(result["mapping"]), 0)

    def test_no_duplicate_task_codes_in_output(self):
        """Re-parse the output and confirm all task_codes are unique."""
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        doc = parse_for_writing(result["output_path"])
        task_section = doc.section("TASK")
        codes = [row["task_code"] for row in task_section.rows]
        self.assertEqual(len(codes), len(set(codes)))

    def test_strategy_in_result(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        self.assertEqual(result["strategy"], "renumber")


class TestFixDuplicateActivityIdsAutoDerivePath(unittest.TestCase):
    """Default output_path is <input>-fixed.xer."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "myfile.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_auto_derive_output_path(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, cache=self.cache
        )
        expected = os.path.join(self.tmpdir, "myfile-fixed.xer")
        self.assertEqual(result["output_path"], expected)
        self.assertTrue(os.path.exists(expected))


class TestFixDuplicateActivityIdsCollision(unittest.TestCase):
    """FileExistsError raised when output_path already exists."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_raises_file_exists_error(self):
        collision = os.path.join(self.tmpdir, "collision.xer")
        with open(collision, "w") as f:
            f.write("placeholder\n")

        with self.assertRaises(FileExistsError):
            fix_duplicate_activity_ids_impl(
                self.src, strategy="renumber", output_path=collision, cache=self.cache
            )


class TestFixDuplicateActivityIdsMergeConsolidate(unittest.TestCase):
    """merge_consolidate: returns a well-formed result regardless of row identity."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_result_shape(self):
        """merge_consolidate returns all required keys regardless of dup type."""
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="merge_consolidate", cache=self.cache
        )
        self.assertEqual(result["strategy"], "merge_consolidate")
        self.assertIn("duplicates_found", result)
        self.assertIsInstance(result["mapping"], list)
        self.assertIsInstance(result["unresolved"], list)
        # mapping + unresolved together must account for all duplicate rows
        total_handled = len(result["mapping"]) + len(result["unresolved"])
        self.assertEqual(total_handled, result["duplicates_found"])

    def test_unresolved_entry_shape(self):
        """If any rows end up in unresolved, they carry original_id and reason."""
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="merge_consolidate", cache=self.cache
        )
        for entry in result["unresolved"]:
            self.assertIn("original_id", entry)
            self.assertIn("reason", entry)


class TestFixDuplicateActivityIdsCachePopulated(unittest.TestCase):
    """After renumber, the output path is queryable from the cache."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cache_populated_after_renumber(self):
        result = fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        out = result["output_path"]
        self.assertIsNotNone(out)
        doc = self.cache.get_for_writing(out)
        task_section = doc.section("TASK")
        self.assertIsNotNone(task_section)
        self.assertGreater(len(task_section.rows), 0)


class TestFixDuplicateActivityIdsPinUnpin(unittest.TestCase):
    """Input is pinned during execution and released afterwards."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_pin_released_after_renumber(self):
        fix_duplicate_activity_ids_impl(
            self.src, strategy="renumber", cache=self.cache
        )
        self.assertFalse(self.cache.is_pinned(self.src))

    def test_pin_released_after_report_only(self):
        fix_duplicate_activity_ids_impl(
            self.src, strategy="report_only", cache=self.cache
        )
        self.assertFalse(self.cache.is_pinned(self.src))


class TestFixDuplicateActivityIdsUnknownStrategy(unittest.TestCase):
    """An unknown strategy propagates ValidationFailure from the lib."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_unknown_strategy_raises(self):
        with self.assertRaises(Exception):
            fix_duplicate_activity_ids_impl(
                self.src, strategy="totally_invalid_strategy", cache=self.cache
            )


if __name__ == "__main__":
    unittest.main()
