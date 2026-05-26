"""In-process LRU cache for parsed XER tables and CPM results.

The cache keys on (path, size, mtime) so any modification to the file -- even
one that preserves mtime due to FAT-precision rounding -- still invalidates.
Eviction is strict LRU at ``max_entries``. Parsed tables and CPM results are
stored together under one entry; CPM is computed lazily on the first
``get_cpm`` call and reused thereafter.

The cache imports the existing parser and CPM engine from the schedule-toolbox
skill's ``references/`` directory via ``sys.path`` injection. The rename to
``lib/`` lands in task C1; this path will be updated then.
"""
from __future__ import annotations

import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from errors import XerLockedError

# sys.path injection -- C1 will rename "references" to "lib" and this path
# will be updated. Keep the variable name LIB so the rename is a one-line edit.
LIB = Path(__file__).parent.parent / "skills" / "schedule-toolbox" / "references"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

# These imports trigger when the cache module loads. quality_checks owns the
# XER parser (private name _parse_xer); cpm_engine owns schedule_forward_backward.
from quality_checks import _parse_xer  # noqa: E402
from cpm_engine import schedule_forward_backward  # noqa: E402


# Partial-read guard: two stat reads separated by this delay. If the file is
# still being written by P6 the size will keep growing across the interval.
# 100ms is the value the spec calls out.
_PARTIAL_READ_DELAY_S = 0.1


@dataclass(frozen=True)
class CacheKey:
    """Identity tuple for a cached XER. Two keys are equal iff the file at
    ``path`` has the same size and modification time."""

    path: str
    size: int
    mtime: float

    @classmethod
    def for_path(cls, path: str) -> "CacheKey":
        """Build a key from the file on disk. Reads ``os.stat`` once."""
        st = Path(path).stat()
        return cls(path=str(path), size=st.st_size, mtime=st.st_mtime)


class CpmCache:
    """LRU cache of parsed XER + CPM results, keyed by (path, size, mtime).

    Entries are ``(CacheKey, payload)`` where payload is a dict with optional
    ``parsed`` and ``cpm`` slots. CPM is only computed on first ``get_cpm``;
    callers that only need parsed tables don't pay for the CPM pass.

    Thread-safety: not safe for concurrent access. The MCP server is
    single-threaded; if that changes, wrap method bodies in a lock.
    """

    def __init__(self, max_entries: int = 8) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")
        self.max_entries = max_entries
        # OrderedDict preserves insertion order; move_to_end on access turns
        # it into an LRU. The key is the absolute path string (str), value is
        # (CacheKey, payload-dict).
        self._entries: "OrderedDict[str, tuple[CacheKey, dict[str, Any]]]" = OrderedDict()

    # ---- public API -----------------------------------------------------

    def get_parsed(self, xer_path: str) -> dict[str, list[dict]]:
        """Return parsed XER tables. Parses on miss.

        Cache hits skip the partial-read guard: we take a single quick stat,
        compare against the stored key, and return the cached payload
        directly. Only misses pay the 100ms stability check, since they're
        about to read the whole file anyway.
        """
        tentative = self._tentative_key(xer_path)
        existing = self._entries.get(str(xer_path))
        if existing is not None and existing[0] == tentative:
            # Cache hit. Bump to most-recently-used.
            self._entries.move_to_end(str(xer_path))
            payload = existing[1]
            if "parsed" in payload:
                return payload["parsed"]
            # Same key but parsed slot got dropped somehow -- re-parse and
            # update in place. This is a miss-for-parsed inside a hit-for-key,
            # so verify stability before reading.
            self._verify_stable(xer_path, tentative)
            payload["parsed"] = self._parse(xer_path)
            return payload["parsed"]

        # Miss (no entry, or key mismatch -> file changed). Verify stability
        # before parsing.
        key = self._safe_key(xer_path)
        parsed = self._parse(xer_path)
        self._put(xer_path, key, {"parsed": parsed})
        return parsed

    def get_cpm(self, xer_path: str) -> tuple[list[dict], dict]:
        """Return CPM ``(results, metadata)`` for this XER. Computes on miss,
        which implicitly populates the parsed slot if it isn't already there.

        Cache hits skip the partial-read guard (see ``get_parsed`` for why).
        """
        tentative = self._tentative_key(xer_path)
        existing = self._entries.get(str(xer_path))

        if existing is not None and existing[0] == tentative:
            self._entries.move_to_end(str(xer_path))
            payload = existing[1]
            if "cpm" in payload:
                return payload["cpm"]
            # Have parsed but not CPM (or neither). Verify stability before
            # any fresh disk read, then compute.
            if "parsed" not in payload:
                self._verify_stable(xer_path, tentative)
                payload["parsed"] = self._parse(xer_path)
            cpm_result = self._run_cpm(payload["parsed"])
            payload["cpm"] = cpm_result
            return cpm_result

        # Miss.
        key = self._safe_key(xer_path)
        parsed = self._parse(xer_path)
        cpm_result = self._run_cpm(parsed)
        self._put(xer_path, key, {"parsed": parsed, "cpm": cpm_result})
        return cpm_result

    def invalidate(self, xer_path: str) -> bool:
        """Drop the cache entry for this path. Returns True if an entry was
        removed, False if there was nothing to drop."""
        return self._entries.pop(str(xer_path), None) is not None

    # ---- internals ------------------------------------------------------

    def _tentative_key(self, xer_path: str) -> CacheKey:
        """Cheap single-stat key used to probe the cache before deciding
        whether the partial-read guard is needed. No sleep, no second stat."""
        st = Path(xer_path).stat()
        return CacheKey(path=str(xer_path), size=st.st_size, mtime=st.st_mtime)

    def _verify_stable(self, xer_path: str, tentative: CacheKey) -> None:
        """Sleep + re-stat to confirm a tentatively-keyed file isn't still
        being written. Raises XerLockedError if the size advanced across the
        interval. Doesn't return a key -- the caller already has ``tentative``,
        which is the post-stable key once this returns successfully.
        """
        time.sleep(_PARTIAL_READ_DELAY_S)
        st = Path(xer_path).stat()
        if st.st_size != tentative.size:
            raise XerLockedError(
                f"XER appears mid-write: size changed from {tentative.size} "
                f"to {st.st_size} across a "
                f"{int(_PARTIAL_READ_DELAY_S * 1000)}ms interval "
                f"({xer_path}). Wait for the writer to finish and retry."
            )

    def _safe_key(self, xer_path: str) -> CacheKey:
        """Build a CacheKey, raising XerLockedError if the file's size changes
        between two reads 100ms apart.

        This catches the case where P6 has the file open and is still writing
        to it. We don't try to detect every race -- a stable size across the
        interval is good enough in practice. mtime alone is unreliable because
        Windows FAT filesystems round to 2-second precision.

        Two stat calls total: one before the sleep (to capture the
        pre-stability size) and one after (to capture the verified size +
        mtime). Three stats is what the original code did; the third was
        redundant because the second already had both fields.

        Manual verification (no deterministic test for the sleep):
            1. Open a Python REPL, import cache and time.
            2. In another shell, run a loop that appends 1KB to a file every
               50ms for ~1s.
            3. Call cache._safe_key('that_path') while the loop runs.
            4. It should raise XerLockedError on most attempts.
        """
        p = Path(xer_path)
        s1 = p.stat().st_size
        time.sleep(_PARTIAL_READ_DELAY_S)
        st = p.stat()
        if s1 != st.st_size:
            raise XerLockedError(
                f"XER appears mid-write: size changed from {s1} to "
                f"{st.st_size} across a "
                f"{int(_PARTIAL_READ_DELAY_S * 1000)}ms interval "
                f"({xer_path}). Wait for the writer to finish and retry."
            )
        return CacheKey(path=str(xer_path), size=st.st_size, mtime=st.st_mtime)

    def _put(self, path: str, key: CacheKey, entry: dict[str, Any]) -> None:
        """Insert (or replace) an entry, evicting the oldest if over capacity."""
        # If the path is already there, pop it first so the new insert lands
        # at the most-recently-used end.
        self._entries.pop(str(path), None)
        self._entries[str(path)] = (key, entry)
        while len(self._entries) > self.max_entries:
            # popitem(last=False) -> oldest entry.
            self._entries.popitem(last=False)

    def _parse(self, xer_path: str) -> dict[str, list[dict]]:
        """Parse an XER file to the table dict. Wraps the existing parser
        so call sites can be retargeted in one place if the parser moves."""
        return _parse_xer(str(xer_path))

    def _run_cpm(self, parsed: dict[str, list[dict]]) -> tuple[list[dict], dict]:
        """Run CPM forward+backward against parsed tables. Returns whatever
        ``schedule_forward_backward`` returns -- the cache doesn't reshape it."""
        # ``or [{}]`` handles both the missing-key case and the
        # present-but-empty case (e.g. ``{"PROJECT": []}``). Without it,
        # ``proj[0]`` would IndexError on the empty list.
        proj = parsed.get("PROJECT") or [{}]
        data_date = (proj[0].get("last_recalc_date")
                     or proj[0].get("data_date", ""))
        return schedule_forward_backward(
            parsed.get("TASK", []),
            parsed.get("TASKPRED", []),
            parsed.get("CALENDAR", []),
            data_date,
            schedoptions=parsed.get("SCHEDOPTIONS"),
            project=parsed.get("PROJECT"),
        )
