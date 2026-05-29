"""Tests for the create_xer_from_template MCP wrapper (tools/xer_modify.py).

Uses westland-skeleton-v1.xer as the source fixture.  Temp files are written to
a system temp directory (outside the project tree) so the PreToolUse XER hook
is not triggered.
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
from tools.xer_modify import create_xer_from_template_impl  # noqa: E402

LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from xer_io import parse_for_writing  # noqa: E402

SKELETON_NAME = "westland-skeleton-v1"

_METADATA = {
    "project_name": "Test Project Alpha",
    "project_id": "TPA-001",
    "planned_start": "2026-07-01",
    "planned_data_date": "2026-07-01",
}


class TestCreateXerFromTemplateHappyPath(unittest.TestCase):
    """Happy-path: skeleton instantiated and written successfully."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.tmpdir, "output.xer")
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_file_created(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        self.assertIsNotNone(result["output_path"])
        self.assertTrue(os.path.exists(result["output_path"]))

    def test_output_path_returned(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        self.assertEqual(result["output_path"], self.output_path)

    def test_project_name_in_result(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        self.assertEqual(result["project_name"], _METADATA["project_name"])

    def test_proj_short_name_propagated(self):
        """Re-parse the output and confirm proj_short_name matches project_name."""
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        doc = parse_for_writing(result["output_path"])
        proj_section = doc.section("PROJECT")
        self.assertIsNotNone(proj_section)
        self.assertGreater(len(proj_section.rows), 0)
        self.assertEqual(
            proj_section.rows[0]["proj_short_name"], _METADATA["project_name"]
        )

    def test_proj_id_propagated(self):
        """Re-parse the output and confirm proj_id matches metadata."""
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        doc = parse_for_writing(result["output_path"])
        proj_section = doc.section("PROJECT")
        self.assertEqual(proj_section.rows[0]["proj_id"], _METADATA["project_id"])


class TestCreateXerFromTemplateMilestones(unittest.TestCase):
    """NTP and SC milestone task_ids are returned correctly."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.tmpdir, "output.xer")
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ntp_milestone_task_id_returned(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        ntp = result["ntp_milestone"]
        self.assertIsNotNone(ntp)
        self.assertIn("task_id", ntp)
        self.assertEqual(ntp["task_code"], "MILESTONE-NTP")

    def test_sc_milestone_task_id_returned(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        sc = result["sc_milestone"]
        self.assertIsNotNone(sc)
        self.assertIn("task_id", sc)
        self.assertEqual(sc["task_code"], "MILESTONE-SC")

    def test_milestone_task_ids_match_doc(self):
        """Verify returned task_ids actually exist in the written file."""
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        doc = parse_for_writing(result["output_path"])
        task_section = doc.section("TASK")
        all_ids = {row["task_id"] for row in task_section.rows}
        self.assertIn(result["ntp_milestone"]["task_id"], all_ids)
        self.assertIn(result["sc_milestone"]["task_id"], all_ids)


class TestCreateXerFromTemplateValidation(unittest.TestCase):
    """Validation block is present and import_ready is True for a clean skeleton."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.tmpdir, "output.xer")
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_validation_import_ready(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        self.assertTrue(result["validation"]["import_ready"])

    def test_validation_summary_keys(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        summary = result["validation"]["summary"]
        self.assertIn("errors", summary)
        self.assertIn("warnings", summary)
        self.assertIn("info", summary)


class TestCreateXerFromTemplateAutoDerivePath(unittest.TestCase):
    """Default output_path is {project_name}.xer (sanitized) in cwd."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        self.cache = CpmCache()

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_auto_derive_output_path(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, cache=self.cache
        )
        expected = os.path.join(self.tmpdir, "Test Project Alpha.xer")
        self.assertEqual(result["output_path"], expected)
        self.assertTrue(os.path.exists(expected))

    def test_sanitized_name_replaces_slash(self):
        """Slashes in project_name are replaced with underscore."""
        metadata = dict(_METADATA, project_name="A/B Test")
        result = create_xer_from_template_impl(
            SKELETON_NAME, metadata, cache=self.cache
        )
        self.assertIn("A_B Test.xer", result["output_path"])
        self.assertTrue(os.path.exists(result["output_path"]))


class TestCreateXerFromTemplateCollision(unittest.TestCase):
    """FileExistsError raised when the output path already exists."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_raises_file_exists_error(self):
        collision = os.path.join(self.tmpdir, "collision.xer")
        with open(collision, "w") as f:
            f.write("placeholder\n")

        with self.assertRaises(FileExistsError):
            create_xer_from_template_impl(
                SKELETON_NAME, _METADATA, output_path=collision, cache=self.cache
            )


class TestCreateXerFromTemplateUnknownSkeleton(unittest.TestCase):
    """FileNotFoundError raised for an unknown skeleton_name."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_raises_file_not_found(self):
        output = os.path.join(self.tmpdir, "output.xer")
        with self.assertRaises(FileNotFoundError) as ctx:
            create_xer_from_template_impl(
                "nonexistent-skeleton-xyz", _METADATA, output_path=output, cache=self.cache
            )
        # Error message should mention available skeletons.
        self.assertIn("Available skeletons", str(ctx.exception))

    def test_error_mentions_known_skeleton(self):
        output = os.path.join(self.tmpdir, "output.xer")
        with self.assertRaises(FileNotFoundError) as ctx:
            create_xer_from_template_impl(
                "no-such-skeleton", _METADATA, output_path=output, cache=self.cache
            )
        # At least the real skeleton should appear in the error.
        self.assertIn(SKELETON_NAME, str(ctx.exception))


class TestCreateXerFromTemplateCachePopulated(unittest.TestCase):
    """After success the output path is queryable from the cache."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.tmpdir, "output.xer")
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cache_populated_after_write(self):
        result = create_xer_from_template_impl(
            SKELETON_NAME, _METADATA, output_path=self.output_path, cache=self.cache
        )
        out = result["output_path"]
        self.assertIsNotNone(out)
        doc = self.cache.get_for_writing(out)
        task_section = doc.section("TASK")
        self.assertIsNotNone(task_section)
        self.assertGreater(len(task_section.rows), 0)


class TestCreateXerFromTemplateMissingProjectName(unittest.TestCase):
    """Missing project_name in metadata propagates ValidationFailure from lib."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.tmpdir, "output.xer")
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_missing_project_name_raises(self):
        bad_metadata = {"project_id": "TPA-001"}
        # The lib raises ValidationFailure; we just confirm something is raised.
        with self.assertRaises(Exception):
            create_xer_from_template_impl(
                SKELETON_NAME, bad_metadata, output_path=self.output_path, cache=self.cache
            )


if __name__ == "__main__":
    unittest.main()
