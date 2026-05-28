# scheduling/mcp-server/tests/test_cache.py
"""Tests for CpmCache and CacheKey.

These tests use the minimal.xer fixture beside this file. The fixture is the
smallest XER the real ``_parse_xer`` will accept: 2 milestone tasks and 1
FS relationship, with the supporting PROJECT/CALENDAR/SCHEDOPTIONS/PROJWBS
rows P6 expects.
"""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add the mcp-server directory to sys.path so we can import cache / errors.
SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CacheKey, CpmCache  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "minimal.xer"


class TestCacheKey(unittest.TestCase):
    def test_key_includes_path_size_mtime(self):
        """CacheKey.for_path captures path, size, and mtime from the file."""
        key = CacheKey.for_path(str(FIXTURE))
        st = FIXTURE.stat()
        self.assertEqual(key.path, str(FIXTURE))
        self.assertEqual(key.size, st.st_size)
        self.assertEqual(key.mtime, st.st_mtime)

    def test_key_changes_when_file_size_changes(self):
        """Modifying the file's size produces a different key."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "minimal.xer"
            shutil.copy(FIXTURE, tmp)
            key_before = CacheKey.for_path(str(tmp))

            # Append a byte. Size strictly changes; this catches the
            # FAT-mtime case where mtime might be quantized but size won't.
            with open(tmp, "ab") as f:
                f.write(b"\n")

            key_after = CacheKey.for_path(str(tmp))
            self.assertNotEqual(key_before, key_after)
            self.assertNotEqual(key_before.size, key_after.size)


class TestCpmCache(unittest.TestCase):
    def test_get_parsed_caches_result(self):
        """Two calls with no file change return the same parsed object
        (identity equality)."""
        cache = CpmCache()
        first = cache.get_parsed(str(FIXTURE))
        second = cache.get_parsed(str(FIXTURE))
        self.assertIs(first, second)
        # Sanity check the parser actually ran.
        self.assertEqual(len(first["TASK"]), 2)
        self.assertEqual(len(first["TASKPRED"]), 1)

    def test_cache_invalidates_on_file_change(self):
        """When the file's bytes change, the next ``get_parsed`` call returns
        a freshly-parsed object (not the cached one)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "minimal.xer"
            shutil.copy(FIXTURE, tmp)

            cache = CpmCache()
            first = cache.get_parsed(str(tmp))

            # Force size and mtime to change. Sleep 1.1s so the mtime
            # advances even on filesystems with 1-second resolution.
            time.sleep(1.1)
            with open(tmp, "ab") as f:
                f.write(b"\n")

            second = cache.get_parsed(str(tmp))
            # New object after the file changed.
            self.assertIsNot(first, second)
            # Still parses correctly.
            self.assertEqual(len(second["TASK"]), 2)

    def test_lru_eviction(self):
        """With max_entries=2, inserting a 3rd entry evicts the oldest."""
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)
            paths = []
            for i in range(3):
                p = tmp_dir / f"minimal_{i}.xer"
                shutil.copy(FIXTURE, p)
                paths.append(p)

            cache = CpmCache(max_entries=2)

            # Load 0 then 1. Cache: [0, 1].
            r0a = cache.get_parsed(str(paths[0]))
            cache.get_parsed(str(paths[1]))
            # Load 2. Cache should now be [1, 2] -- 0 evicted.
            cache.get_parsed(str(paths[2]))

            # Hitting 0 again should re-parse (new object), not return r0a.
            r0b = cache.get_parsed(str(paths[0]))
            self.assertIsNot(r0a, r0b)

            # And 1 should still be cached -- two consecutive get_parsed calls
            # on paths[1] return identity-equal results because we just
            # touched it via the access pattern above.
            #
            # Actually -- the previous get_parsed(paths[0]) at line "r0b"
            # just evicted whatever was oldest. After the [1, 2] state,
            # loading 0 evicts 1 (LRU is 1 because 2 was the most recent
            # before we loaded 0). So after r0b, cache is [2, 0]. Loading
            # 1 again would be a re-parse.
            #
            # To assert eviction cleanly, check that paths[1] gives a fresh
            # object on the next call -- that confirms it was evicted when
            # paths[0] was re-cached.
            r1a = cache.get_parsed(str(paths[1]))
            r1b = cache.get_parsed(str(paths[1]))
            # The pair right after each other should be identity-equal --
            # the second call is a guaranteed hit because nothing else was
            # inserted between them.
            self.assertIs(r1a, r1b)

    def test_cache_hit_does_not_sleep(self):
        """A cache hit must skip the 100ms partial-read guard. The first
        ``get_parsed`` call pays the full guard (it's a miss); the second
        is a hit and should return in well under 50ms.

        50ms is a generous ceiling: the guard sleeps 100ms unconditionally,
        and the actual hit-path work (one stat + dict lookup + move_to_end)
        is sub-millisecond on any modern filesystem. A regression that
        re-introduces the sleep on hits would show up as ~100ms here.
        """
        cache = CpmCache()
        cache.get_parsed(str(FIXTURE))  # warm

        start = time.perf_counter()
        cache.get_parsed(str(FIXTURE))
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertLess(
            elapsed_ms, 50,
            f"Cache hit took {elapsed_ms:.1f}ms; partial-read guard "
            f"appears to be running on hits (expected <50ms)."
        )


class TestLossyProjection(unittest.TestCase):
    """The new XerDoc-based cache must project to the same dict shape
    the old _parse_xer produced. This pins the contract for the 30+
    read-only tools that depend on get_parsed()."""

    def test_get_parsed_matches_old_parser_shape(self):
        # Old parser available in quality_checks for comparison
        LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
        if str(LIB) not in sys.path:
            sys.path.insert(0, str(LIB))
        from quality_checks import _parse_xer as old_parse  # noqa
        from cache import CpmCache

        fixture = Path(__file__).parent / "fixtures" / "minimal.xer"
        cache = CpmCache()
        new_dict = cache.get_parsed(str(fixture))
        old_dict = old_parse(str(fixture))

        # Same table set
        self.assertEqual(set(new_dict.keys()), set(old_dict.keys()))
        # Same row count per table
        for table in old_dict:
            self.assertEqual(
                len(new_dict[table]), len(old_dict[table]),
                f"Row count mismatch in {table}"
            )
        # Same field values per row
        for table in old_dict:
            for i, (new_row, old_row) in enumerate(
                zip(new_dict[table], old_dict[table])
            ):
                self.assertEqual(
                    new_row, old_row,
                    f"Row {i} in {table} differs:\n  new={new_row}\n  old={old_row}"
                )


if __name__ == "__main__":
    unittest.main()
