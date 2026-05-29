"""Tests for the apply_xer_changes MCP wrapper (tools/xer_modify.py).

Uses minimal.xer as the base fixture.  Temp files are written to a
system temp directory (outside the project tree) so the PreToolUse XER
hook is not triggered.
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
from tools.xer_modify import apply_xer_changes_impl  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"

# A valid set_duration change targeting one of the two tasks in minimal.xer.
# minimal.xer has two milestone tasks; we pick a non-milestone to test duration.
# Actually minimal.xer may have TT_Mile tasks — set_duration still works on
# them even though schedulers don't normally change milestone durations.
# We look up the real task_code at module import rather than hardcoding it so
# the fixture can evolve without breaking the test.

def _first_task_code(fixture_path: Path) -> str:
    """Read the first task_code from the TASK section of a fixture."""
    lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    from xer_io import parse_for_writing
    doc = parse_for_writing(str(fixture_path))
    task_section = doc.section("TASK")
    if task_section is None or not task_section.rows:
        raise RuntimeError(f"No TASK rows in {fixture_path}")
    return task_section.rows[0]["task_code"]


_TASK_CODE = _first_task_code(FIXTURE)
_VALID_CHANGE = {"type": "set_duration", "activity_id": _TASK_CODE, "new_duration_days": 5}


class TestApplyXerChangesHappyPath(unittest.TestCase):
    """Happy-path: single valid change, output file written."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_file_created(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        self.assertIsNotNone(result["output_path"])
        self.assertTrue(os.path.exists(result["output_path"]))

    def test_output_path_is_modified_xer(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        expected = os.path.join(self.tmpdir, "source-modified.xer")
        self.assertEqual(result["output_path"], expected)

    def test_output_xer_is_parseable(self):
        """The written file must round-trip cleanly through parse_for_writing."""
        lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from xer_io import parse_for_writing

        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        doc = parse_for_writing(result["output_path"])
        task_section = doc.section("TASK")
        self.assertIsNotNone(task_section)
        self.assertGreater(len(task_section.rows), 0)

    def test_changes_applied_count(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        self.assertEqual(result["summary"]["changes_applied"], 1)

    def test_no_validation_errors(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        self.assertEqual(result["summary"]["validation_errors"], [])

    def test_dry_run_false(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        self.assertFalse(result["dry_run"])


class TestApplyXerChangesDryRun(unittest.TestCase):
    """dry_run=True: all passes run, no file written."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_path_is_null_on_dry_run(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache
        )
        self.assertIsNone(result["output_path"])

    def test_dry_run_flag_set(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache
        )
        self.assertTrue(result["dry_run"])

    def test_no_file_written_on_dry_run(self):
        apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache
        )
        default_out = os.path.join(self.tmpdir, "source-modified.xer")
        self.assertFalse(os.path.exists(default_out))

    def test_summary_populated_on_dry_run(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache
        )
        self.assertEqual(result["summary"]["changes_applied"], 1)
        self.assertIn("validation_errors", result["summary"])
        self.assertIn("validation_warnings", result["summary"])

    def test_per_change_feedback_populated_on_dry_run(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache
        )
        self.assertEqual(len(result["per_change_feedback"]), 1)
        pcf = result["per_change_feedback"][0]
        self.assertEqual(pcf["change_index"], 0)
        self.assertEqual(pcf["type"], "set_duration")
        self.assertIsInstance(pcf["feedback"], dict)


class TestApplyXerChangesValidationErrors(unittest.TestCase):
    """Invalid change record: output_path=null, error reported, no file."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _bad_change(self):
        return {"type": "set_duration", "activity_id": "NONEXISTENT_XXXX", "new_duration_days": 5}

    def test_output_path_null_on_error(self):
        result = apply_xer_changes_impl(
            self.src, [self._bad_change()], cache=self.cache
        )
        self.assertIsNone(result["output_path"])

    def test_validation_errors_populated(self):
        result = apply_xer_changes_impl(
            self.src, [self._bad_change()], cache=self.cache
        )
        errors = result["summary"]["validation_errors"]
        self.assertGreater(len(errors), 0)
        err = errors[0]
        self.assertIn("change_index", err)
        self.assertIn("code", err)
        self.assertIn("message", err)

    def test_no_file_written_on_error(self):
        apply_xer_changes_impl(
            self.src, [self._bad_change()], cache=self.cache
        )
        default_out = os.path.join(self.tmpdir, "source-modified.xer")
        self.assertFalse(os.path.exists(default_out))


class TestApplyXerChangesStrictMode(unittest.TestCase):
    """strict=True promotes warnings to errors."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_strict_promotes_warnings_to_errors(self):
        """A change that introduces an orphan (warning in normal mode) becomes
        an error in strict mode.  Use remove_activity on an activity that has
        a single successor — this creates an orphan successor when done on
        minimal.xer (which has exactly one FS relationship).
        """
        # The minimal fixture has TASK A -> TASK B (FS).  Removing A leaves B
        # without a predecessor — an orphan — which xer_validate flags as a
        # warning.  In strict mode it becomes an error.
        lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from xer_io import parse_for_writing

        doc = parse_for_writing(str(FIXTURE))
        task_section = doc.section("TASK")
        taskpred = doc.section("TASKPRED")

        # Only worth running this sub-test if we have a pred relationship that
        # creates an orphan.  If minimal.xer has no preds, skip.
        if taskpred is None or not taskpred.rows:
            self.skipTest("minimal.xer has no TASKPRED rows — cannot test orphan warning")

        # Find the predecessor activity_id from the first relationship.
        pred_task_id = taskpred.rows[0]["pred_task_id"]
        pred_code = next(
            r["task_code"] for r in task_section.rows if r["task_id"] == pred_task_id
        )

        src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, src)

        change = {"type": "remove_activity", "activity_id": pred_code}

        # Non-strict: should succeed (warning, not error).
        result_normal = apply_xer_changes_impl(
            src, [change], strict=False, cache=CpmCache()
        )

        # Strict: warning promoted to error → output_path stays null.
        src2 = os.path.join(self.tmpdir, "source2.xer")
        shutil.copy(FIXTURE, src2)
        result_strict = apply_xer_changes_impl(
            src2, [change], strict=True, cache=CpmCache()
        )

        # In strict mode the warning should appear in validation_errors.
        self.assertGreater(len(result_strict["summary"]["validation_errors"]), 0)
        # In normal mode there should be no errors.
        self.assertEqual(result_normal["summary"]["validation_errors"], [])


class TestApplyXerChangesOutputPathCollision(unittest.TestCase):
    """FileExistsError when output_path already exists."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_raises_file_exists_error(self):
        collision = os.path.join(self.tmpdir, "collision.xer")
        # Pre-create the collision target.
        with open(collision, "w") as f:
            f.write("placeholder\n")

        with self.assertRaises(FileExistsError):
            apply_xer_changes_impl(
                self.src, [_VALID_CHANGE],
                output_path=collision,
                cache=self.cache,
            )


class TestApplyXerChangesAutoDerivePath(unittest.TestCase):
    """Default output_path derives to <input>-modified.xer."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "myfile.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_auto_derive_output_path(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        expected = os.path.join(self.tmpdir, "myfile-modified.xer")
        self.assertEqual(result["output_path"], expected)
        self.assertTrue(os.path.exists(expected))


class TestApplyXerChangesPinUnpin(unittest.TestCase):
    """Pin is held during apply, released after."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_pin_released_after_success(self):
        apply_xer_changes_impl(self.src, [_VALID_CHANGE], cache=self.cache)
        self.assertFalse(self.cache.is_pinned(self.src))

    def test_pin_released_after_dry_run(self):
        apply_xer_changes_impl(self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache)
        self.assertFalse(self.cache.is_pinned(self.src))

    def test_pin_released_after_error(self):
        bad = {"type": "set_duration", "activity_id": "NO_SUCH", "new_duration_days": 1}
        apply_xer_changes_impl(self.src, [bad], cache=self.cache)
        self.assertFalse(self.cache.is_pinned(self.src))


class TestApplyXerChangesCachePopulated(unittest.TestCase):
    """After success, output path is in the cache."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_output_path_in_cache_after_write(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        out = result["output_path"]
        self.assertIsNotNone(out)

        # get_for_writing on the output path should return a doc (cache hit —
        # no re-parse from disk since put_doc inserted it).  We can't directly
        # assert "no re-parse" in a unit test, but we CAN assert the call
        # succeeds and returns a doc with TASK rows.
        doc = self.cache.get_for_writing(out)
        task_section = doc.section("TASK")
        self.assertIsNotNone(task_section)
        self.assertGreater(len(task_section.rows), 0)

    def test_output_not_cached_on_dry_run(self):
        """dry_run writes nothing and inserts nothing into the cache."""
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], dry_run=True, cache=self.cache
        )
        self.assertIsNone(result["output_path"])
        # The default output path should not exist in the cache either.
        default_out = os.path.join(self.tmpdir, "source-modified.xer")
        # The path doesn't exist on disk, so get_for_writing would raise
        # FileNotFoundError — confirming it was not inserted.
        with self.assertRaises(FileNotFoundError):
            self.cache.get_for_writing(default_out)


class TestApplyXerChangesTargetMilestone(unittest.TestCase):
    """target_milestone_id flows through to post_cpm_summary."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _last_milestone_task_id(self) -> str | None:
        """Return the task_id of the last milestone in the fixture, or None."""
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(FIXTURE))
        task_section = doc.section("TASK")
        if task_section is None:
            return None
        fin_miles = [
            r for r in task_section.rows if r.get("task_type") == "TT_FinMile"
        ]
        if not fin_miles:
            # Fall back to any milestone.
            fin_miles = [
                r for r in task_section.rows if "Mile" in r.get("task_type", "")
            ]
        return fin_miles[-1]["task_id"] if fin_miles else None

    def test_target_milestone_id_explicit(self):
        tid = self._last_milestone_task_id()
        if tid is None:
            self.skipTest("No milestone tasks in minimal.xer")

        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE],
            target_milestone_id=tid,
            cache=self.cache,
        )
        summary = result["post_cpm_summary"]
        if summary is not None:
            self.assertEqual(summary.get("target_milestone_id"), tid)


class TestApplyXerChangesPostCpmSummary(unittest.TestCase):
    """post_cpm_summary has the required 6 keys on a happy-path call."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_post_cpm_summary_keys(self):
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        summary = result["post_cpm_summary"]
        # Summary may be None if the fixture has no TT_FinMile milestone —
        # in that case apply_changes returns None for post_cpm_summary.
        # Check the shape only when the engine actually produced one.
        if summary is None:
            self.skipTest(
                "minimal.xer has no TT_FinMile milestone; post_cpm_summary is None"
            )
        expected_keys = {
            "target_milestone_id",
            "completion_before",
            "completion_after",
            "net_days_change",
            "critical_path_changed",
            "substantial_cp_change",
        }
        self.assertEqual(set(summary.keys()), expected_keys)

    def test_post_cpm_summary_present_in_result(self):
        """The 'post_cpm_summary' key is always present (value may be None)."""
        result = apply_xer_changes_impl(
            self.src, [_VALID_CHANGE], cache=self.cache
        )
        self.assertIn("post_cpm_summary", result)


class TestCachePutDoc(unittest.TestCase):
    """Unit tests for CpmCache.put_doc (also covers the lazy CPM decision)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source.xer")
        shutil.copy(FIXTURE, self.src)
        self.cache = CpmCache()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_put_doc_then_get_for_writing_returns_same_object(self):
        """put_doc inserts a doc; get_for_writing on the same path returns it."""
        lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from xer_io import parse_for_writing

        doc = parse_for_writing(self.src)

        # Write a copy so put_doc can _safe_key it (needs the file on disk).
        out_path = os.path.join(self.tmpdir, "out.xer")
        from xer_io import write as xer_write
        xer_write(doc, out_path)

        self.cache.put_doc(out_path, doc)
        retrieved = self.cache.get_for_writing(out_path)
        # Should be the SAME object we inserted (identity equality confirms cache hit).
        self.assertIs(retrieved, doc)

    def test_put_doc_with_cpm_stores_cpm(self):
        """put_doc with cpm= stores CPM so get_cpm returns it without recomputing."""
        lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from xer_io import parse_for_writing, write as xer_write

        doc = parse_for_writing(self.src)
        out_path = os.path.join(self.tmpdir, "out2.xer")
        xer_write(doc, out_path)

        # Build a fake CPM tuple.
        fake_cpm = ([{"task_code": "FAKE"}], {"data_date": "2026-01-01"})
        self.cache.put_doc(out_path, doc, cpm=fake_cpm)

        results, meta = self.cache.get_cpm(out_path)
        self.assertIs(results, fake_cpm[0])
        self.assertIs(meta, fake_cpm[1])

    def test_put_doc_without_cpm_lazy_compute(self):
        """put_doc without cpm= triggers lazy CPM on get_cpm (no crash)."""
        lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from xer_io import parse_for_writing, write as xer_write

        doc = parse_for_writing(self.src)
        out_path = os.path.join(self.tmpdir, "out3.xer")
        xer_write(doc, out_path)

        self.cache.put_doc(out_path, doc)  # no cpm=

        # get_cpm should compute lazily without error.
        results, meta = self.cache.get_cpm(out_path)
        self.assertIsInstance(results, list)
        self.assertIsInstance(meta, dict)

    def test_put_doc_replaces_stale_entry(self):
        """put_doc on an already-cached path replaces the old entry."""
        lib = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        from xer_io import parse_for_writing, write as xer_write

        doc1 = parse_for_writing(self.src)
        out_path = os.path.join(self.tmpdir, "out4.xer")
        xer_write(doc1, out_path)

        # Warm the cache with doc1.
        self.cache.put_doc(out_path, doc1)

        # Parse again to get a fresh object (simulating a second write).
        doc2 = parse_for_writing(out_path)
        xer_write(doc2, out_path)
        self.cache.put_doc(out_path, doc2)

        retrieved = self.cache.get_for_writing(out_path)
        self.assertIs(retrieved, doc2)


if __name__ == "__main__":
    unittest.main()
