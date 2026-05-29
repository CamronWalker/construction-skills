"""Pin/recency guard tests for CpmCache."""
import sys
import time
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from errors import CachePinExhaustedError  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class TestPinning(unittest.TestCase):
    def test_pin_survives_lru_pressure(self):
        cache = CpmCache(max_entries=3, recency_grace_seconds=0)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")
        d = str(FIXTURES / "cp_shifted.xer")

        cache.get_parsed(a)
        cache.pin(a)
        cache.get_parsed(b)
        cache.get_parsed(c)
        cache.get_parsed(d)  # would evict a if not pinned

        self.assertTrue(cache.is_pinned(a))
        # a is still in cache despite being least-recently-used
        self.assertIn(a, cache._entries)

    def test_unpin_releases_protection(self):
        cache = CpmCache(max_entries=2, recency_grace_seconds=0)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")

        cache.get_parsed(a)
        cache.pin(a)
        cache.unpin(a)
        self.assertFalse(cache.is_pinned(a))

        cache.get_parsed(b)
        cache.get_parsed(c)
        self.assertNotIn(a, cache._entries)

    def test_pin_exhausted_at_max(self):
        cache = CpmCache(max_entries=2, recency_grace_seconds=0)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")

        cache.get_parsed(a)
        cache.get_parsed(b)
        cache.pin(a)
        cache.pin(b)
        # All 2 slots pinned; trying to pin a third path must fail
        with self.assertRaises(CachePinExhaustedError):
            cache.pin(c)

    def test_pin_idempotent_on_already_pinned(self):
        """Pinning an already-pinned path is a no-op, NOT a CachePinExhaustedError."""
        cache = CpmCache(max_entries=2, recency_grace_seconds=0)
        a = str(FIXTURES / "minimal.xer")
        cache.get_parsed(a)
        cache.pin(a)
        cache.pin(a)  # second pin should be safe no-op
        self.assertTrue(cache.is_pinned(a))

    def test_put_never_evicts_self_when_all_others_pinned(self):
        """get_parsed must not KeyError when all existing entries are pinned and grace=0."""
        cache = CpmCache(max_entries=2, recency_grace_seconds=0)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")

        cache.get_parsed(a)
        cache.get_parsed(b)
        cache.pin(a)
        cache.pin(b)
        # All slots pinned; adding c would overflow. _put should NOT evict c.
        result = cache.get_parsed(c)
        self.assertIsInstance(result, dict)
        # And c should be present in the cache (temporary overflow)
        self.assertIn(c, cache._entries)


class TestRecency(unittest.TestCase):
    def test_recently_accessed_survives_eviction(self):
        cache = CpmCache(max_entries=3, recency_grace_seconds=10)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")
        d = str(FIXTURES / "cp_shifted.xer")

        cache.get_parsed(a)
        cache.get_parsed(b)
        cache.get_parsed(c)
        cache.get_parsed(d)  # would evict a if not for recency

        # a was touched <10s ago, recency guard keeps it
        self.assertIn(a, cache._entries)

    def test_recency_zero_means_no_grace(self):
        """recency_grace_seconds=0 effectively disables the recency guard."""
        cache = CpmCache(max_entries=2, recency_grace_seconds=0)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")

        cache.get_parsed(a)
        cache.get_parsed(b)
        cache.get_parsed(c)  # should evict a since recency grace is 0

        self.assertNotIn(a, cache._entries)


class TestDefaults(unittest.TestCase):
    def test_default_max_entries_is_16(self):
        cache = CpmCache()
        self.assertEqual(cache.max_entries, 16)


if __name__ == "__main__":
    unittest.main()
