"""In-process LRU cache for parsed XER tables and CPM results.

The cache keys on (path, size, mtime) so any modification to the file -- even
one that preserves mtime due to FAT-precision rounding -- still invalidates.
Eviction is strict LRU at ``max_entries``. The payload stores a rich ``XerDoc``
in the ``doc`` slot; the lossy ``{table: [{field: value}, ...]}`` projection used
by read-only tools is derived lazily and stored in ``parsed``. CPM is computed
lazily on the first ``get_cpm`` call and reused thereafter.

Write-path tools (apply_xer_changes, fix_duplicate_activity_ids,
create_xer_from_template) access the rich form via ``get_for_writing()``.
Read-only tools access the projected form via ``get_parsed()`` -- same dict
shape as the old ``_parse_xer`` produced.

The cache imports the CPM engine from the schedule-toolbox skill's ``lib/``
directory via ``sys.path`` injection. ``xer_io`` lives alongside ``cache.py``
in the same ``lib/`` tree and is imported directly.
"""
from __future__ import annotations

import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from errors import CachePinExhaustedError, XerLockedError

# sys.path injection into schedule-toolbox/lib so the parser + CPM engine
# can be imported as top-level modules without packaging them.
LIB = Path(__file__).parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

# These imports trigger when the cache module loads. xer_io provides the
# round-trip-safe parser; cpm_engine owns schedule_forward_backward.
# quality_checks._parse_xer is no longer used here but stays in quality_checks.py
# for its own quality-check callers.
from xer_io import parse_for_writing, XerDoc  # noqa: E402
from cpm_engine import schedule_forward_backward  # noqa: E402


def _project_to_lossy(doc: XerDoc) -> dict[str, list[dict]]:
    """Project a rich XerDoc down to the {table: [{field: value}, ...]} shape
    the existing read-only tools expect. Returns copies of row dicts so callers
    can't accidentally mutate cached state."""
    return {
        section.name: [dict(row) for row in section.rows]
        for section in doc.sections
    }


# Partial-read guard: two stat reads separated by this delay. If the file is
# still being written by P6 the size will keep growing across the interval.
# 100ms is the value the spec calls out.
_PARTIAL_READ_DELAY_S = 0.1

# Default recency window (30 minutes), exposed for test override
_DEFAULT_RECENCY_GRACE_SECONDS = 30 * 60


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

    Entries are ``(CacheKey, payload)`` where payload is a dict with slots:
      - ``doc``    — XerDoc (always present after first parse)
      - ``parsed`` — lossy dict projection (lazily computed on first access)
      - ``cpm``    — CPM result tuple (lazily computed on first get_cpm call)

    Read-only tools call ``get_parsed()`` to get the ``{table: [dict]}`` shape.
    Write-path tools call ``get_for_writing()`` to get the rich ``XerDoc``.
    CPM is only computed on first ``get_cpm``; callers that only need parsed
    tables don't pay for the CPM pass.

    Thread-safety: not safe for concurrent access. The MCP server is
    single-threaded; if that changes, wrap method bodies in a lock.
    """

    def __init__(
        self,
        max_entries: int = 16,
        recency_grace_seconds: int = _DEFAULT_RECENCY_GRACE_SECONDS,
    ) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")
        self.max_entries = max_entries
        self.recency_grace_seconds = recency_grace_seconds
        # OrderedDict preserves insertion order; move_to_end on access turns
        # it into an LRU. The key is the absolute path string (str), value is
        # (CacheKey, payload-dict).
        self._entries: "OrderedDict[str, tuple[CacheKey, dict[str, Any]]]" = OrderedDict()
        self._pinned: set[str] = set()
        self._last_access: dict[str, float] = {}

    # ---- public API -----------------------------------------------------

    def get_parsed(self, xer_path: str) -> dict[str, list[dict]]:
        """Return parsed XER tables (lossy dict shape). Parses on miss.

        Cache hits skip the partial-read guard: we take a single quick stat,
        compare against the stored key, and return the cached payload
        directly. Only misses pay the 100ms stability check, since they're
        about to read the whole file anyway.
        """
        tentative = self._tentative_key(xer_path)
        existing = self._entries.get(str(xer_path))
        if existing is not None and existing[0] == tentative:
            # Cache hit. Bump LRU.
            self._entries.move_to_end(str(xer_path))
            self._touch(xer_path)
            return self._ensure_parsed_projection(existing[1])

        # Miss. Verify stability before parsing.
        key = self._safe_key(xer_path)
        doc = self._parse(xer_path)
        self._put(xer_path, key, {"doc": doc})
        return self._ensure_parsed_projection(self._entries[str(xer_path)][1])

    def get_cpm(self, xer_path: str) -> tuple[list[dict], dict]:
        """Return CPM ``(results, metadata)`` for this XER. Computes on miss.

        Cache hits skip the partial-read guard (see ``get_parsed`` for why).
        """
        tentative = self._tentative_key(xer_path)
        existing = self._entries.get(str(xer_path))

        if existing is not None and existing[0] == tentative:
            self._entries.move_to_end(str(xer_path))
            self._touch(xer_path)
            payload = existing[1]
            if "cpm" in payload:
                return payload["cpm"]
            # CPM not yet computed; need lossy projection for the CPM engine.
            parsed = self._ensure_parsed_projection(payload)
            cpm_result = self._run_cpm(parsed)
            payload["cpm"] = cpm_result
            return cpm_result

        # Miss.
        key = self._safe_key(xer_path)
        doc = self._parse(xer_path)
        self._put(xer_path, key, {"doc": doc})
        payload = self._entries[str(xer_path)][1]
        parsed = self._ensure_parsed_projection(payload)
        cpm_result = self._run_cpm(parsed)
        payload["cpm"] = cpm_result
        return cpm_result

    def get_for_writing(self, xer_path: str) -> XerDoc:
        """Return the rich XerDoc form. Used by write-path tools that need
        full byte-fidelity (apply_xer_changes, fix_duplicate_activity_ids,
        create_xer_from_template)."""
        tentative = self._tentative_key(xer_path)
        existing = self._entries.get(str(xer_path))
        if existing is not None and existing[0] == tentative:
            self._entries.move_to_end(str(xer_path))
            self._touch(xer_path)
            return existing[1]["doc"]

        key = self._safe_key(xer_path)
        doc = self._parse(xer_path)
        self._put(xer_path, key, {"doc": doc})
        return doc

    def invalidate(self, xer_path: str) -> bool:
        """Drop the cache entry for this path. Returns True if an entry was
        removed, False if there was nothing to drop."""
        self._pinned.discard(str(xer_path))
        self._last_access.pop(str(xer_path), None)
        return self._entries.pop(str(xer_path), None) is not None

    # ---- pin / recency API ----------------------------------------------

    def pin(self, xer_path: str) -> None:
        """Pin an entry against LRU eviction. Raises CachePinExhaustedError when
        the cache already has max_entries pinned paths.

        Idempotent: pinning an already-pinned path is a safe no-op.
        """
        key = str(xer_path)
        if key in self._pinned:
            return  # idempotent
        if len(self._pinned) >= self.max_entries:
            raise CachePinExhaustedError(
                f"Cannot pin {xer_path!r}: {len(self._pinned)} entries already "
                f"pinned (max_entries={self.max_entries}). Unpin something first."
            )
        # Ensure the path is actually in cache (force parse if not)
        if key not in self._entries:
            self.get_for_writing(xer_path)
        self._pinned.add(key)

    def unpin(self, xer_path: str) -> None:
        """Release a pin. Safe no-op if the path was not pinned."""
        self._pinned.discard(str(xer_path))

    def is_pinned(self, xer_path: str) -> bool:
        """Return True if the path is currently pinned."""
        return str(xer_path) in self._pinned

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

    def _touch(self, xer_path: str) -> None:
        """Record an access timestamp for recency tracking."""
        self._last_access[str(xer_path)] = time.time()

    def _is_recent(self, xer_path: str) -> bool:
        """Return True iff the path was accessed within recency_grace_seconds."""
        last = self._last_access.get(str(xer_path))
        if last is None:
            return False
        return (time.time() - last) < self.recency_grace_seconds

    def _put(self, path: str, key: CacheKey, entry: dict[str, Any]) -> None:
        """Insert (or replace) an entry, evicting per LRU + pin + recency rules."""
        self._entries.pop(str(path), None)
        self._entries[str(path)] = (key, entry)
        self._touch(path)
        # Evict from front (oldest) while over capacity, skipping pinned/recent
        while len(self._entries) > self.max_entries:
            oldest_path = next(iter(self._entries))
            if oldest_path in self._pinned or self._is_recent(oldest_path):
                # Skip this one; rotate to back so we don't re-examine immediately.
                self._entries.move_to_end(oldest_path)
                # Safety: if every remaining entry is protected, stop trying.
                # The pin count limit guarantees this terminates for purely-pinned
                # case; recency-only case may briefly exceed capacity until
                # entries age out, which is acceptable.
                if all(
                    p in self._pinned or self._is_recent(p)
                    for p in self._entries
                ):
                    break
                continue
            self._entries.pop(oldest_path)
            self._last_access.pop(oldest_path, None)

    def _ensure_parsed_projection(self, payload: dict) -> dict[str, list[dict]]:
        """Lazily compute the lossy projection and cache it in the payload."""
        if "parsed" not in payload:
            payload["parsed"] = _project_to_lossy(payload["doc"])
        return payload["parsed"]

    def _parse(self, xer_path: str) -> XerDoc:
        """Parse an XER to the rich XerDoc form. Cache stores XerDoc; the
        lossy dict shape is derived on demand via _project_to_lossy."""
        return parse_for_writing(str(xer_path))

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
