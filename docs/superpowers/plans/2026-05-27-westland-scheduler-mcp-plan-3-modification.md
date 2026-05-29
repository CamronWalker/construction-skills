# Westland Scheduler Local MCP — Plan 3: Modification + Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Tier 3 modification + generation tools — `validate_xer_structure`, `fix_duplicate_activity_ids`, `apply_xer_changes` (14 change types including the new `dissolve_activity` and `pop_activity`), `create_xer_from_template`, and `invalidate_cache_for` — backed by a round-trip-safe `lib/xer_io.py`, a unified `CpmCache` with pin/recency guards, and a hand-curated `westland-skeleton-v1.xer` template. On release, Claude can answer schedule questions *and* commit changes back to disk, with the same atomicity and cache-awareness as the analytics tools.

**Architecture:** One new I/O foundation (`lib/xer_io.py` — round-trip-safe parser/writer); one new validation engine (`lib/xer_validate.py`); one new mutation engine (`lib/xer_modify.py` — 14 change-type handlers + atomic orchestrator); one cache refactor (single parse pipeline, `XerDoc` rich form, `get_parsed` as projection, pin/unpin/recency, LRU 8→16); five MCP wrappers; one hand-curated `westland-skeleton-v1.xer` + sidecar notes produced via agent-per-table investigation of a 10–15 file Westland corpus.

**Tech Stack:**
- Python 3.10+ (Plan 1 prereq)
- Official `mcp` Python SDK (Plan 1 prereq)
- Standard library `unittest` for tests
- Existing CPM engine, parser, and milestone helpers in `schedule-toolbox/lib/`
- Existing `CpmCache` from Plans 1+2

**Reference spec:** [2026-05-27-scheduler-mcp-tier-3-modification-design.md](../specs/2026-05-27-scheduler-mcp-tier-3-modification-design.md) — read every section before starting.

**Predecessor plans:** [Plan 1 — Foundation](2026-05-24-westland-scheduler-mcp-plan-1-foundation.md) (shipped 7.x), [Plan 2 — Analytics](2026-05-26-westland-scheduler-mcp-plan-2-analytics.md) (shipped 8.x). Both must be merged. Plan 3 picks up the F-batch tools and `CpmCache` as fixed infrastructure.

**Open-question resolutions (locked here so the implementation doesn't stall):**

1. **`wbs_short_name` default** — derive from `wbs_name` as the initials of significant words (skip articles: "of", "and", "the"). If derivation yields < 2 chars, error and require the caller pass it explicitly. Implemented in `xer_modify.add_wbs`.
2. **`apply_anchor_absorption` suggestion_index** — `get_anchor_absorption_suggestions` already returns deterministic ordering (by `absorption_potential_days` desc, then `task_id` asc). Plan 3 reuses that ordering as stable. If the ordering changes in a future release, bump to suggestion-by-task-id selectors.
3. **`renumber` strategy namespace** — match existing activity_code pattern. Numeric suffix preserved per prefix (e.g., `A1010` → `A1015` if `A1011-A1014` are occupied). Codes without a numeric suffix append `-DUP1`, `-DUP2`, etc.
4. **Procore-specific UDFs** — included in `westland-skeleton-v1.xer` by default. The Procore import gate in Phase E confirms acceptance.
5. **Pinning over LRU bound** — refuse the 17th pin. `cache.pin(path)` raises `CachePinExhaustedError` when pinned count equals `max_entries`.

---

## File Structure

### New files

| Path | Responsibility |
|------|----------------|
| `scheduling/skills/schedule-toolbox/lib/xer_io.py` | Round-trip-safe XER parser + writer. Defines `XerDoc`, `XerSection`. Exports `parse_for_writing(path) -> XerDoc` and `write(doc, output_path) -> None`. No cache awareness; no semantics. |
| `scheduling/skills/schedule-toolbox/lib/xer_validate.py` | File-integrity check engine. Exports `validate(doc: XerDoc) -> ValidationReport` with issue codes per the spec's Section 4 taxonomy. Read-only. |
| `scheduling/skills/schedule-toolbox/lib/xer_modify.py` | Mutation engine. Exports one handler function per change type + `apply_changes(doc, changes, *, strict, dry_run) -> ApplyResult` orchestrator that runs the 3-pass validation and atomic write. Also exports `fix_duplicate_ids(doc, strategy)` and `create_from_template(template_path, metadata) -> XerDoc`. |
| `scheduling/skills/schedule-toolbox/tests/test_xer_io.py` | Round-trip identity tests against 7 proposal-corpus XERs; mutate-one-field test; new-row test; encoding round-trip test. |
| `scheduling/skills/schedule-toolbox/tests/test_xer_validate.py` | Lib-level tests for issue detection — one per issue code in the taxonomy. |
| `scheduling/skills/schedule-toolbox/tests/test_xer_modify.py` | Lib-level tests for each of the 14 change-type handlers + the orchestrator (success path + each validation-rule failure). |
| `scheduling/mcp-server/tools/xer_validate.py` | MCP wrapper for `validate_xer_structure`. ~30 lines. |
| `scheduling/mcp-server/tools/xer_modify.py` | MCP wrappers for `apply_xer_changes`, `fix_duplicate_activity_ids`, `create_xer_from_template`. Three tools, one module. |
| `scheduling/mcp-server/tests/test_xer_validate_wrapper.py` | MCP-wrapper smoke tests. |
| `scheduling/mcp-server/tests/test_apply_xer_changes.py` | MCP-wrapper tests: dry_run vs commit; pre-CPM and post-CPM cache hits; per-change feedback shape; atomic-on-failure. |
| `scheduling/mcp-server/tests/test_fix_duplicate_ids.py` | Three strategies covered; mapping output shape verified. |
| `scheduling/mcp-server/tests/test_create_xer_from_template.py` | Skeleton load + project-metadata substitution + NTP/SC milestone-id return; subsequent `validate_xer_structure` reports `import_ready: true`. |
| `scheduling/mcp-server/tests/test_cache_pinning.py` | Pin survives LRU pressure; recency window survives; auto-pin/unpin in `apply_xer_changes`; post-write cache hit on output path; `CachePinExhaustedError` at the bound. |
| `scheduling/mcp-server/tests/fixtures/duplicate_ids.xer` | 3 activities with duplicate `task_code` "A1010". Drives `fix_duplicate_activity_ids` strategy tests. |
| `scheduling/mcp-server/tests/fixtures/dangling_refs.xer` | TASKPRED row pointing at non-existent task_id; TASK row pointing at non-existent calendar_id. Drives `DANGLING_*` codes. |
| `scheduling/mcp-server/tests/fixtures/circular_logic.xer` | 3-activity cycle A→B→C→A. Drives `CIRCULAR_LOGIC` detection. |
| `scheduling/mcp-server/tests/fixtures/orphan_branch.xer` | PROJWBS row with no children + no task references. Drives `ORPHANED_WBS_BRANCH` warning. |
| `scheduling/mcp-server/tests/fixtures/multi_edge.xer` | Pair of activities with both FS and SS edges. Drives `remove_logic` / `modify_logic` relationship-selector tests. |
| `scheduling/mcp-server/tests/fixtures/dissolve_fanout.xer` | Activity X with 3 predecessors + 4 successors. Drives cartesian-product dissolve test (12 new edges) and high-fanout warning. |
| `scheduling/mcp-server/tests/fixtures/wbs_pattern_b_target.xer` | Reference XER hand-built to Pattern B layout. Drives "skeleton + change set produces valid Pattern B" integration test. |
| `scheduling/mcp-server/templates/westland-skeleton-v1.xer` | Hand-curated skeleton. Imports cleanly into P6 + Procore. Contains canonical Westland WBS tree + 2 milestones (NTP, SC) + 1 FS edge. |
| `scheduling/mcp-server/templates/westland-skeleton-v1.notes.md` | Sidecar notes: corpus, per-table agent findings, curator judgement calls, drop list, iteration log. |
| `scheduling/mcp-server/templates/__init__.py` | Empty package marker. |

### Modified files

| Path | Change |
|------|--------|
| `scheduling/mcp-server/cache.py` | Switch parser target from `_parse_xer` to `xer_io.parse_for_writing`. Add `get_for_writing(path) -> XerDoc`. Add `pin(path)`, `unpin(path)`, `is_pinned(path)`. Add 30-minute recency guard. Bump `max_entries` 8 → 16. Add `_project_to_lossy(doc)` helper. Raise `CachePinExhaustedError` when pin count == max_entries. |
| `scheduling/mcp-server/errors.py` | Add `CachePinExhaustedError`, `XerValidationError` (wraps the validation report when the MCP needs to error rather than return a structured response), `XerTemplateError`. |
| `scheduling/mcp-server/tools/structure.py` | Add `invalidate_cache_for` MCP tool (~10 lines). |
| `scheduling/mcp-server/server.py` | Register `xer_validate.register()` and `xer_modify.register()` alongside existing module registrations. |
| `scheduling/mcp-server/tests/test_cache.py` | Switch parse expectations to `xer_io.parse_for_writing`; add lossy-projection equivalence test (existing `get_parsed` dict matches old `_parse_xer` output); existing tests continue to pass. |
| `scheduling/mcp-server/tests/test_server.py` | Add `validate_xer_structure`, `apply_xer_changes`, `fix_duplicate_activity_ids`, `create_xer_from_template`, `invalidate_cache_for` to registered-tool assertions. |
| `scheduling/skills/schedule-toolbox/SKILL.md` | Routing table additions for the 5 new MCP tools; new "Modifying XER files" subsection. |
| `scheduling/skills/schedule-toolbox/references/xer-modify.md` | Replace existing guidance with "All XER writes go through `apply_xer_changes` or `create_xer_from_template`." Document each change type briefly with examples. |
| `scheduling/skills/schedule-toolbox/references/xer-generation.md` | Document `create_xer_from_template` as the canonical generation entry point. Note `build_from_raw_template.py` stays in `lib/` as historical reference but is not the recommended path. |
| `scheduling/skills/schedule-create-proposal-schedule/SKILL.md` | Claude-facing phases switch to the compositional flow: `create_xer_from_template` → `apply_xer_changes` with bulk records. `iterate.py` stays unchanged (non-Claude caller). |
| `scheduling/skills/schedule-create-proposal-schedule/references/wbs-patterns.md` | Each pattern (A/B/C) gains a "MCP change records for this pattern" subsection showing the `apply_xer_changes` records needed to convert the v1 skeleton into that pattern. |
| `scheduling/.claude-plugin/plugin.json` | Bump version 8.1.3 → 9.0.0. |
| `.claude-plugin/marketplace.json` | Bump scheduling plugin entry → 9.0.0 (lockstep with `plugin.json`). |

---

## Phase A — `lib/xer_io.py` (round-trip-safe I/O foundation)

Goal: parse an XER preserving everything the lossy `_parse_xer` drops (ERMHDR, per-table `%F` field order, `%E` markers, raw line buffer), and write it back with byte-fidelity for untouched rows. Unblocks every other phase.

### Task A1: Define the `XerDoc` / `XerSection` data model

**Files:**
- Create: `scheduling/skills/schedule-toolbox/lib/xer_io.py`
- Create: `scheduling/skills/schedule-toolbox/tests/test_xer_io.py`

- [ ] **Step 1: Write the data-model unit test**

```python
# scheduling/skills/schedule-toolbox/tests/test_xer_io.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'xer_io'`.

- [ ] **Step 3: Implement the data model**

```python
# scheduling/skills/schedule-toolbox/lib/xer_io.py
"""Round-trip-safe XER parser and writer.

Used by write-path MCP tools (apply_xer_changes, fix_duplicate_activity_ids,
create_xer_from_template). Existing read-only tools project from this rich
form to the lossy {table: [{field: value}, ...]} shape via CpmCache._project_to_lossy.

The module is pure I/O: no cache awareness, no semantics, no validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class XerSection:
    """One %T table block in an XER document.

    Attributes:
        name: Table name as it appears after %T (e.g., "TASK", "PROJWBS").
        field_order: Ordered field names from the %F line; the writer emits
            %R columns in this order. Required for round-trip fidelity.
        rows: Mutable list of row dicts. Keys are field names; values are
            strings (XER is tab-delimited text — all values are strings).
        raw_lines: Original %R lines, byte-for-byte. Used by the writer for
            unchanged rows (zero risk of format drift). None for new sections
            created by create_xer_from_template.
        e_line: Original %E line text (often just "%E" but P6 occasionally
            adds whitespace).
        _dirty: Set of row indices that have been mutated; the writer
            reconstructs these from the dict and ignores raw_lines[i].
    """

    name: str
    field_order: list[str]
    rows: list[dict[str, str]]
    raw_lines: Optional[list[str]]
    e_line: str
    _dirty: set[int] = field(default_factory=set)

    def is_dirty(self, row_index: int) -> bool:
        """Return True iff row at row_index needs reconstruction on write.

        A row is dirty if it was explicitly marked dirty (mutation) OR if
        there is no raw_lines entry for it (newly appended).
        """
        if self.raw_lines is None or row_index >= len(self.raw_lines):
            return True
        return row_index in self._dirty

    def mark_dirty(self, row_index: int) -> None:
        """Mark a row as mutated. The writer will reconstruct it from the
        dict instead of emitting raw_lines[row_index] verbatim."""
        self._dirty.add(row_index)

    def append_row(self, row: dict[str, str]) -> None:
        """Append a new row. New rows have no raw_lines entry and are
        therefore always dirty."""
        self.rows.append(row)


@dataclass
class XerDoc:
    """A parsed XER document with enough fidelity to round-trip to bytes.

    Attributes:
        header_line: The leading ERMHDR\\t... line, verbatim.
        encoding: Detected encoding (one of cp1252 / utf-8-sig / utf-8 /
            latin-1). The writer uses the same encoding for output.
        sections: Ordered list of XerSection — preserves the order P6 emits
            (PROJECT, CALENDAR, PROJWBS, RSRC, ..., TASK, TASKPRED, ...).
    """

    header_line: str
    encoding: str
    sections: list[XerSection]

    def section(self, name: str) -> Optional[XerSection]:
        """Return the named section, or None if not present."""
        for s in self.sections:
            if s.name == name:
                return s
        return None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/xer_io.py \
        scheduling/skills/schedule-toolbox/tests/test_xer_io.py
git commit -m "feat(scheduling): scaffold XerDoc/XerSection data model for round-trip I/O"
```

### Task A2: Implement `parse_for_writing`

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/xer_io.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_xer_io.py`

- [ ] **Step 1: Write the parse test**

Append to `test_xer_io.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io.TestParseForWriting -v
```
Expected: FAIL with `ImportError: cannot import name 'parse_for_writing'`.

- [ ] **Step 3: Implement `parse_for_writing`**

Append to `xer_io.py`:

```python
_ENCODINGS = ("cp1252", "utf-8-sig", "utf-8", "latin-1")


def _detect_decode(raw: bytes) -> tuple[str, str]:
    """Try the encoding fallback chain. Returns (text, encoding_used)."""
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    # Last-resort: latin-1 decodes any byte sequence
    return raw.decode("latin-1"), "latin-1"


def parse_for_writing(xer_path: str) -> XerDoc:
    """Parse an XER preserving everything needed for round-trip output.

    Differences from the existing read-only _parse_xer:
      - Captures the ERMHDR header line verbatim.
      - Captures per-table %F field order (the lossy parser only kept it
        long enough to zip into row dicts).
      - Captures %E markers per section.
      - Captures the raw %R lines so the writer can emit untouched rows
        byte-for-byte.
    """
    with open(xer_path, "rb") as f:
        raw = f.read()
    text, encoding = _detect_decode(raw)

    header_line = ""
    sections: list[XerSection] = []
    current: Optional[XerSection] = None
    current_fields: list[str] = []

    for line in text.split("\r\n"):
        if not line:
            continue
        parts = line.split("\t")
        marker = parts[0]
        if marker == "ERMHDR":
            header_line = line
        elif marker == "%T":
            current_fields = []
            current = XerSection(
                name=parts[1].strip(),
                field_order=[],
                rows=[],
                raw_lines=[],
                e_line="%E",
            )
            sections.append(current)
        elif marker == "%F" and current is not None:
            current_fields = [f.strip() for f in parts[1:]]
            current.field_order = current_fields
        elif marker == "%R" and current is not None:
            current.raw_lines.append(line)
            current.rows.append(dict(zip(current_fields, parts[1:])))
        elif marker == "%E" and current is not None:
            current.e_line = line
            current = None

    return XerDoc(
        header_line=header_line,
        encoding=encoding,
        sections=sections,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io.TestParseForWriting -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/xer_io.py \
        scheduling/skills/schedule-toolbox/tests/test_xer_io.py
git commit -m "feat(scheduling): parse_for_writing — XER → XerDoc with round-trip fidelity"
```

### Task A3: Implement `write` with byte-fidelity for unchanged rows

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/xer_io.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_xer_io.py`

- [ ] **Step 1: Write the round-trip identity test**

Append to `test_xer_io.py`:

```python
import tempfile


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io.TestRoundTrip -v
```
Expected: FAIL with `ImportError: cannot import name 'write'`.

- [ ] **Step 3: Implement `write`**

Append to `xer_io.py`:

```python
def _reconstruct_row(row: dict[str, str], field_order: list[str]) -> str:
    """Build a %R line from a dict, in the section's canonical field order.

    Missing fields are emitted as empty strings — matches how P6 represents
    nulls in tab-delimited XER.
    """
    vals = [str(row.get(f, "")) for f in field_order]
    return "%R\t" + "\t".join(vals)


def write(doc: XerDoc, output_path: str) -> None:
    """Serialize XerDoc to disk.

    Strategy:
      - For each section, for each row index i:
          * if section.is_dirty(i): reconstruct the line from the dict.
          * else: emit raw_lines[i] verbatim. Zero format drift.
      - Sections are emitted in doc.sections order.
      - Encoding matches doc.encoding (default cp1252).
      - Line endings: CRLF. Single trailing "%E\\n" at EOF.
    """
    lines: list[str] = [doc.header_line]
    for section in doc.sections:
        lines.append(f"%T\t{section.name}")
        lines.append("%F\t" + "\t".join(section.field_order))
        for i, row in enumerate(section.rows):
            if section.is_dirty(i):
                lines.append(_reconstruct_row(row, section.field_order))
            else:
                lines.append(section.raw_lines[i])
        lines.append(section.e_line)
    # Trailing newline after final %E -- P6 expects this.
    text = "\r\n".join(lines) + "\r\n"
    with open(output_path, "wb") as f:
        f.write(text.encode(doc.encoding))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io.TestRoundTrip -v
```
Expected: 3 tests PASS. If any byte-mismatch, investigate which marker (probably trailing-newline, encoding-BOM, or `%E` line text) is off.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/xer_io.py \
        scheduling/skills/schedule-toolbox/tests/test_xer_io.py
git commit -m "feat(scheduling): xer_io.write — byte-fidelity for unchanged rows"
```

### Task A4: Mutate-one-field test

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/tests/test_xer_io.py`

- [ ] **Step 1: Write the mutate-one-field test**

Append to `test_xer_io.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes (no impl change needed)**

```bash
python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io.TestMutation -v
```
Expected: 2 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-toolbox/tests/test_xer_io.py
git commit -m "test(scheduling): xer_io mutation + append tests"
```

### Task A5: Run round-trip against 7 proposal-corpus XERs

The corpus lives at `OneDrive - Westland Construction/40 Cowork/training_data/Proposal Schedules/`. These files are gigabytes total and NOT checked into the repo. The test reads them from disk if the environment variable `WESTLAND_CORPUS` is set to the corpus root.

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/tests/test_xer_io.py`

- [ ] **Step 1: Write the corpus round-trip test (skipped if env unset)**

Append to `test_xer_io.py`:

```python
import os


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
```

- [ ] **Step 2: Run locally with corpus env set**

```bash
WESTLAND_CORPUS="$HOME/OneDrive - Westland Construction/40 Cowork/training_data" \
  python -m unittest scheduling.skills.schedule-toolbox.tests.test_xer_io.TestCorpusRoundTrip -v
```

(On Windows PowerShell: `$env:WESTLAND_CORPUS = "$env:USERPROFILE\OneDrive - Westland Construction\40 Cowork\training_data"; python -m unittest ...`)

Expected: all 7 subtests PASS. If any fail, investigate. Common causes:
- Encoding edge case (one file uses a quirky cp1252 character that round-trips differently — extend `_ENCODINGS` order if needed)
- Trailing whitespace on `%E` lines that we're not preserving
- Missing trailing newline in source files (drop the `+ "\r\n"` in `write`)

Iterate on `parse_for_writing` / `write` until all 7 pass. Each fix gets its own commit.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-toolbox/tests/test_xer_io.py
git commit -m "test(scheduling): corpus round-trip suite for xer_io (7 proposal schedules)"
```

---

## Phase B — Cache refactor (unified XerDoc, pin/recency)

Goal: single parse pipeline through `xer_io.parse_for_writing`. `get_parsed` becomes a projection. Add `get_for_writing`, `pin`/`unpin`, recency guard. Bump LRU to 16.

### Task B1: Add `CachePinExhaustedError` to `errors.py`

**Files:**
- Modify: `scheduling/mcp-server/errors.py`

- [ ] **Step 1: Write the error-class test**

Create `scheduling/mcp-server/tests/test_errors.py`:

```python
"""Tests for the new error classes added in Plan 3."""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from errors import (  # noqa: E402
    CachePinExhaustedError,
    XerLockedError,
    XerTemplateError,
    XerValidationError,
)


class TestErrorClasses(unittest.TestCase):
    def test_cache_pin_exhausted_is_exception(self):
        e = CachePinExhaustedError("too many pins")
        self.assertIsInstance(e, Exception)

    def test_xer_validation_error_carries_report(self):
        e = XerValidationError("bad XER", report={"errors": 3})
        self.assertEqual(e.report["errors"], 3)

    def test_xer_template_error_is_exception(self):
        e = XerTemplateError("template not found")
        self.assertIsInstance(e, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_errors -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add the error classes**

Modify `scheduling/mcp-server/errors.py` (append after existing classes):

```python
class CachePinExhaustedError(Exception):
    """Raised when CpmCache.pin() is called but the pinned-entry count
    already equals max_entries. The cache cannot accept another pin without
    risking pin starvation. Callers should unpin something first.
    """


class XerValidationError(Exception):
    """Raised when an MCP tool wants to abort on validation failure rather
    than return the structured validation report. Carries the report in
    .report so the caller can still inspect it.
    """

    def __init__(self, message: str, report: dict | None = None) -> None:
        super().__init__(message)
        self.report = report or {}


class XerTemplateError(Exception):
    """Raised when create_xer_from_template can't load the named template
    (template file missing, malformed, or unknown template_name).
    """
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_errors -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/errors.py scheduling/mcp-server/tests/test_errors.py
git commit -m "feat(scheduling): add CachePinExhausted/XerValidation/XerTemplate error classes"
```

### Task B2: Switch cache parser target to `xer_io.parse_for_writing` + add projection

**Files:**
- Modify: `scheduling/mcp-server/cache.py`
- Modify: `scheduling/mcp-server/tests/test_cache.py`

- [ ] **Step 1: Write the lossy-projection equivalence test**

Append to `scheduling/mcp-server/tests/test_cache.py`:

```python
class TestLossyProjection(unittest.TestCase):
    """The new XerDoc-based cache must project to the same dict shape
    the old _parse_xer produced. This pins the contract for the 30+
    read-only tools that depend on get_parsed()."""

    def test_get_parsed_matches_old_parser_shape(self):
        # Old parser available in quality_checks for comparison
        import sys
        sys.path.insert(0, str(
            Path(__file__).parent.parent.parent
            / "skills" / "schedule-toolbox" / "lib"
        ))
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
```

- [ ] **Step 2: Run test to verify it fails initially**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_cache.TestLossyProjection -v
```
Expected: FAIL — the cache still uses `_parse_xer` directly.

- [ ] **Step 3: Modify `cache.py` to use `xer_io.parse_for_writing`**

In `scheduling/mcp-server/cache.py`:

1. Update the `sys.path` injection block to include both `lib/` (already there) — no change.
2. Replace the `_parse_xer` import:

```python
# OLD:
from quality_checks import _parse_xer  # noqa: E402

# NEW:
from xer_io import parse_for_writing, XerDoc  # noqa: E402
```

3. Add the lossy-projection helper:

```python
def _project_to_lossy(doc: XerDoc) -> dict[str, list[dict]]:
    """Project a rich XerDoc down to the {table: [{field: value}, ...]} shape
    the existing read-only tools expect. Returns copies of row dicts so callers
    can't accidentally mutate cached state."""
    return {
        section.name: [dict(row) for row in section.rows]
        for section in doc.sections
    }
```

4. Replace `_parse`:

```python
def _parse(self, xer_path: str) -> XerDoc:
    """Parse an XER to the rich XerDoc form. Cache stores XerDoc; the
    lossy dict shape is derived on demand via _project_to_lossy."""
    return parse_for_writing(str(xer_path))
```

5. Update payload shape inside the cache: where the old code stored `payload["parsed"]` as a dict, it now stores `payload["doc"]` as `XerDoc`. Add a `payload["parsed"]` *projection* that's lazily computed:

```python
def _ensure_parsed_projection(self, payload: dict) -> dict[str, list[dict]]:
    if "parsed" not in payload:
        payload["parsed"] = _project_to_lossy(payload["doc"])
    return payload["parsed"]
```

6. Rewrite `get_parsed`:

```python
def get_parsed(self, xer_path: str) -> dict[str, list[dict]]:
    tentative = self._tentative_key(xer_path)
    existing = self._entries.get(str(xer_path))
    if existing is not None and existing[0] == tentative:
        self._entries.move_to_end(str(xer_path))
        return self._ensure_parsed_projection(existing[1])

    key = self._safe_key(xer_path)
    doc = self._parse(xer_path)
    self._put(xer_path, key, {"doc": doc})
    return self._ensure_parsed_projection(self._entries[str(xer_path)][1])
```

7. Add `get_for_writing`:

```python
def get_for_writing(self, xer_path: str) -> XerDoc:
    """Return the rich XerDoc form for write-path tools."""
    tentative = self._tentative_key(xer_path)
    existing = self._entries.get(str(xer_path))
    if existing is not None and existing[0] == tentative:
        self._entries.move_to_end(str(xer_path))
        return existing[1]["doc"]

    key = self._safe_key(xer_path)
    doc = self._parse(xer_path)
    self._put(xer_path, key, {"doc": doc})
    return doc
```

8. Update `get_cpm` to read from the new `doc` slot (project to lossy for the CPM engine which still consumes the dict shape):

```python
def get_cpm(self, xer_path: str) -> tuple[list[dict], dict]:
    tentative = self._tentative_key(xer_path)
    existing = self._entries.get(str(xer_path))

    if existing is not None and existing[0] == tentative:
        self._entries.move_to_end(str(xer_path))
        payload = existing[1]
        if "cpm" in payload:
            return payload["cpm"]
        parsed = self._ensure_parsed_projection(payload)
        cpm_result = self._run_cpm(parsed)
        payload["cpm"] = cpm_result
        return cpm_result

    key = self._safe_key(xer_path)
    doc = self._parse(xer_path)
    self._put(xer_path, key, {"doc": doc})
    payload = self._entries[str(xer_path)][1]
    parsed = self._ensure_parsed_projection(payload)
    cpm_result = self._run_cpm(parsed)
    payload["cpm"] = cpm_result
    return cpm_result
```

- [ ] **Step 4: Run all cache tests**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_cache -v
```
Expected: all existing tests PASS + new `TestLossyProjection` PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/cache.py scheduling/mcp-server/tests/test_cache.py
git commit -m "refactor(scheduling): cache parses to XerDoc; get_parsed projects to lossy dict"
```

### Task B3: Add pin/unpin/recency to `CpmCache`

**Files:**
- Modify: `scheduling/mcp-server/cache.py`
- Create: `scheduling/mcp-server/tests/test_cache_pinning.py`

- [ ] **Step 1: Write the pinning tests**

```python
# scheduling/mcp-server/tests/test_cache_pinning.py
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
        cache = CpmCache(max_entries=3)
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
        cache = CpmCache(max_entries=2)
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
        cache = CpmCache(max_entries=2)
        a = str(FIXTURES / "minimal.xer")
        b = str(FIXTURES / "cp_baseline.xer")
        c = str(FIXTURES / "tia_baseline.xer")

        cache.get_parsed(a)
        cache.get_parsed(b)
        cache.pin(a)
        cache.pin(b)
        cache.get_parsed(c)  # would normally cache; but b is pinned, a is pinned
        # The unpinned slot got taken by c; pinning a third path now must error
        with self.assertRaises(CachePinExhaustedError):
            cache.pin(c)


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_cache_pinning -v
```
Expected: FAIL — `pin/unpin/is_pinned` not implemented; `recency_grace_seconds` not a parameter.

- [ ] **Step 3: Implement pinning + recency**

Modify `scheduling/mcp-server/cache.py`:

```python
# Add to imports
from errors import CachePinExhaustedError, XerLockedError  # noqa

# Default recency window (30 minutes), exposed for test override
_DEFAULT_RECENCY_GRACE_SECONDS = 30 * 60


class CpmCache:
    def __init__(
        self,
        max_entries: int = 16,
        recency_grace_seconds: int = _DEFAULT_RECENCY_GRACE_SECONDS,
    ) -> None:
        if max_entries < 1:
            raise ValueError(f"max_entries must be >= 1, got {max_entries}")
        self.max_entries = max_entries
        self.recency_grace_seconds = recency_grace_seconds
        self._entries: "OrderedDict[str, tuple[CacheKey, dict[str, Any]]]" = OrderedDict()
        self._pinned: set[str] = set()
        self._last_access: dict[str, float] = {}

    # ---- pin API ---------------------------------------------------------

    def pin(self, xer_path: str) -> None:
        if len(self._pinned) >= self.max_entries:
            raise CachePinExhaustedError(
                f"Cannot pin {xer_path!r}: {len(self._pinned)} entries already "
                f"pinned (max_entries={self.max_entries}). Unpin something first."
            )
        # Ensure the path is actually in cache
        if str(xer_path) not in self._entries:
            # Force a parse so we have something to protect
            self.get_for_writing(xer_path)
        self._pinned.add(str(xer_path))

    def unpin(self, xer_path: str) -> None:
        self._pinned.discard(str(xer_path))

    def is_pinned(self, xer_path: str) -> bool:
        return str(xer_path) in self._pinned

    # ---- recency tracking ------------------------------------------------

    def _touch(self, xer_path: str) -> None:
        self._last_access[str(xer_path)] = time.time()

    def _is_recent(self, xer_path: str) -> bool:
        last = self._last_access.get(str(xer_path))
        if last is None:
            return False
        return (time.time() - last) < self.recency_grace_seconds
```

Update `_put` to respect pin + recency on eviction:

```python
def _put(self, path: str, key: CacheKey, entry: dict[str, Any]) -> None:
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
            # The pin count limit guarantees this terminates.
            if all(
                p in self._pinned or self._is_recent(p)
                for p in self._entries
            ):
                break
            continue
        self._entries.pop(oldest_path)
        self._last_access.pop(oldest_path, None)
```

Update every `move_to_end` call in `get_parsed`, `get_cpm`, `get_for_writing` to also call `self._touch(xer_path)`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_cache_pinning tests.test_cache -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/cache.py scheduling/mcp-server/tests/test_cache_pinning.py
git commit -m "feat(scheduling): cache pin/unpin/recency guards + LRU bump 8→16"
```

### Task B4: Add `invalidate_cache_for` MCP tool

**Files:**
- Modify: `scheduling/mcp-server/tools/structure.py`
- Modify: `scheduling/mcp-server/tests/test_structure.py`

- [ ] **Step 1: Write the invalidate-tool test**

Append to `tests/test_structure.py`:

```python
class TestInvalidateCacheFor(unittest.TestCase):
    def test_invalidates_an_entry(self):
        from cache import CpmCache
        from tools.structure import invalidate_cache_for_impl

        cache = CpmCache()
        fixture = str(Path(__file__).parent / "fixtures" / "minimal.xer")
        cache.get_parsed(fixture)
        result = invalidate_cache_for_impl(fixture, cache)
        self.assertEqual(result, {"invalidated": True})
        self.assertNotIn(fixture, cache._entries)

    def test_returns_false_when_nothing_to_invalidate(self):
        from cache import CpmCache
        from tools.structure import invalidate_cache_for_impl

        cache = CpmCache()
        fixture = str(Path(__file__).parent / "fixtures" / "minimal.xer")
        result = invalidate_cache_for_impl(fixture, cache)
        self.assertEqual(result, {"invalidated": False})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_structure.TestInvalidateCacheFor -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the tool**

Append to `scheduling/mcp-server/tools/structure.py`:

```python
def invalidate_cache_for_impl(xer_path: str, cache) -> dict:
    """Drop the cache entry for xer_path. Returns {invalidated: bool}."""
    return {"invalidated": cache.invalidate(str(xer_path))}
```

Update the `register(mcp, cache)` function:

```python
@mcp.tool()
@wrap_tool_errors(tool_name="invalidate_cache_for", lib_script=None)
def invalidate_cache_for(xer_path: str) -> dict:
    """Drop the cache entry for the given XER path. Returns
    ``{invalidated: bool}``. Use when an XER has been edited outside the
    MCP and you want to force a fresh parse on the next tool call.
    """
    return invalidate_cache_for_impl(xer_path, cache)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scheduling/mcp-server && python -m unittest tests.test_structure -v
```
Expected: 2 new tests PASS + existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/mcp-server/tools/structure.py scheduling/mcp-server/tests/test_structure.py
git commit -m "feat(scheduling): invalidate_cache_for MCP tool"
```

---

## Phase C — `lib/xer_validate.py` + `validate_xer_structure` MCP wrapper

Goal: file-integrity check engine with the spec's issue-code taxonomy. Read-only. The same engine feeds `apply_xer_changes` post-state validation in Phase D.

### Task C1: Scaffold `xer_validate.py` with the `ValidationReport` shape

**Files:**
- Create: `scheduling/skills/schedule-toolbox/lib/xer_validate.py`
- Create: `scheduling/skills/schedule-toolbox/tests/test_xer_validate.py`

- [ ] **Step 1: Write the data-model test**

```python
# scheduling/skills/schedule-toolbox/tests/test_xer_validate.py
"""Tests for the file-integrity validation engine."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_validate import ValidationIssue, ValidationReport  # noqa: E402


class TestDataModel(unittest.TestCase):
    def test_empty_report_is_import_ready(self):
        r = ValidationReport(issues=[])
        self.assertTrue(r.import_ready)
        self.assertEqual(r.summary, {"errors": 0, "warnings": 0, "info": 0})

    def test_report_with_error_is_not_import_ready(self):
        r = ValidationReport(issues=[
            ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_ACTIVITY_ID",
                message="dup",
                affected=["1", "2"],
            )
        ])
        self.assertFalse(r.import_ready)
        self.assertEqual(r.summary["errors"], 1)

    def test_report_with_only_warnings_is_import_ready(self):
        r = ValidationReport(issues=[
            ValidationIssue(
                severity="warning",
                category="Network",
                code="ORPHAN_ACTIVITY",
                message="orphan",
                affected=["3"],
            )
        ])
        self.assertTrue(r.import_ready)
        self.assertEqual(r.summary["warnings"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd scheduling/skills/schedule-toolbox && python -m unittest tests.test_xer_validate -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the data model**

```python
# scheduling/skills/schedule-toolbox/lib/xer_validate.py
"""File-integrity validation for XER documents.

Distinct from quality_checks (which scores schedule health). This module
answers "will P6/Procore import this file?" Issues are categorized; errors
block import_ready, warnings are advisory.

The same check engine is reused by xer_modify.apply_changes for post-state
validation — that's how a single change_index in the apply output can
carry an issue code from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationIssue:
    """One row in a ValidationReport.

    Attributes:
        severity: "error" blocks import_ready; "warning" is advisory.
        category: One of "Duplicates", "Dangling refs", "Logic", "Data",
            "Network", "Structure", "Status".
        code: Stable enum-like code (e.g., "DUPLICATE_ACTIVITY_ID").
        message: Human-readable description.
        affected: IDs of the affected entities (activity ids, wbs ids, etc.).
    """

    severity: Severity
    category: str
    code: str
    message: str
    affected: list[str]


@dataclass
class ValidationReport:
    """Output of xer_validate.validate(doc). Aggregates issues + import_ready
    flag + summary counts."""

    issues: list[ValidationIssue]

    @property
    def import_ready(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def summary(self) -> dict[str, int]:
        s = {"errors": 0, "warnings": 0, "info": 0}
        for i in self.issues:
            if i.severity == "error":
                s["errors"] += 1
            elif i.severity == "warning":
                s["warnings"] += 1
            else:
                s["info"] += 1
        return s
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd scheduling/skills/schedule-toolbox && python -m unittest tests.test_xer_validate -v
```
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/xer_validate.py \
        scheduling/skills/schedule-toolbox/tests/test_xer_validate.py
git commit -m "feat(scheduling): scaffold xer_validate ValidationIssue/Report model"
```

### Task C2: Implement Duplicates + Dangling-refs categories

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/xer_validate.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_xer_validate.py`
- Create: `scheduling/mcp-server/tests/fixtures/duplicate_ids.xer`
- Create: `scheduling/mcp-server/tests/fixtures/dangling_refs.xer`

- [ ] **Step 1: Build the duplicate_ids and dangling_refs fixtures**

Hand-build by starting from `minimal.xer`, copying its bytes, and modifying:

- `duplicate_ids.xer`: copy 3 TASK rows but reuse the same `task_code` "A1010" on all 3 (different task_ids).
- `dangling_refs.xer`: add a TASKPRED row with `pred_task_id = "99999"` (no matching TASK row), and one TASK row with `clndr_id = "888"` (no matching CALENDAR row).

Verify both fixtures parse without exception:

```bash
cd scheduling/mcp-server && python -c "
import sys
sys.path.insert(0, '../skills/schedule-toolbox/lib')
from xer_io import parse_for_writing
for name in ('duplicate_ids.xer', 'dangling_refs.xer'):
    doc = parse_for_writing(f'tests/fixtures/{name}')
    print(name, 'parsed ok, sections:', [s.name for s in doc.sections])
"
```

- [ ] **Step 2: Write category tests**

Append to `test_xer_validate.py`:

```python
class TestDuplicateChecks(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.dup = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "duplicate_ids.xer"
        ))

    def test_detects_duplicate_activity_id(self):
        from xer_validate import validate
        report = validate(self.dup)
        codes = [i.code for i in report.issues]
        self.assertIn("DUPLICATE_ACTIVITY_ID", codes)
        self.assertFalse(report.import_ready)


class TestDanglingRefs(unittest.TestCase):
    def setUp(self):
        from xer_io import parse_for_writing
        self.dangling = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "dangling_refs.xer"
        ))

    def test_detects_dangling_predecessor(self):
        from xer_validate import validate
        report = validate(self.dangling)
        codes = [i.code for i in report.issues]
        self.assertIn("DANGLING_PREDECESSOR", codes)

    def test_detects_dangling_calendar(self):
        from xer_validate import validate
        report = validate(self.dangling)
        codes = [i.code for i in report.issues]
        self.assertIn("DANGLING_CALENDAR", codes)
```

- [ ] **Step 3: Run tests to verify they fail**

Expected: FAIL — `validate` not implemented.

- [ ] **Step 4: Implement duplicate + dangling checks**

Append to `xer_validate.py`:

```python
def _check_duplicate_activity_ids(doc) -> list[ValidationIssue]:
    task = doc.section("TASK")
    if task is None:
        return []
    issues = []
    seen: dict[str, list[str]] = {}
    for row in task.rows:
        code = row.get("task_code", "")
        seen.setdefault(code, []).append(row.get("task_id", ""))
    for code, ids in seen.items():
        if len(ids) > 1:
            issues.append(ValidationIssue(
                severity="error",
                category="Duplicates",
                code="DUPLICATE_ACTIVITY_ID",
                message=f"Activity code {code!r} appears in {len(ids)} rows "
                        f"(task_ids {', '.join(ids)})",
                affected=ids,
            ))
    return issues


def _check_dangling_predecessors(doc) -> list[ValidationIssue]:
    task = doc.section("TASK")
    pred = doc.section("TASKPRED")
    if task is None or pred is None:
        return []
    valid_ids = {r.get("task_id") for r in task.rows}
    issues = []
    for r in pred.rows:
        pid = r.get("pred_task_id")
        sid = r.get("task_id")
        if pid not in valid_ids:
            issues.append(ValidationIssue(
                severity="error",
                category="Dangling refs",
                code="DANGLING_PREDECESSOR",
                message=f"TASKPRED row references non-existent pred_task_id {pid!r}",
                affected=[pid],
            ))
        if sid not in valid_ids:
            issues.append(ValidationIssue(
                severity="error",
                category="Dangling refs",
                code="DANGLING_SUCCESSOR",
                message=f"TASKPRED row references non-existent task_id {sid!r}",
                affected=[sid],
            ))
    return issues


def _check_dangling_calendars(doc) -> list[ValidationIssue]:
    task = doc.section("TASK")
    cal = doc.section("CALENDAR")
    if task is None:
        return []
    valid_ids = {r.get("clndr_id") for r in cal.rows} if cal is not None else set()
    issues = []
    for r in task.rows:
        cid = r.get("clndr_id")
        if cid and cid not in valid_ids:
            issues.append(ValidationIssue(
                severity="error",
                category="Dangling refs",
                code="DANGLING_CALENDAR",
                message=f"Task {r.get('task_id')!r} references non-existent "
                        f"clndr_id {cid!r}",
                affected=[r.get("task_id", "")],
            ))
    return issues


def validate(doc) -> ValidationReport:
    """Run all file-integrity checks. Returns a ValidationReport with
    all detected issues. import_ready = no error-severity issues."""
    issues: list[ValidationIssue] = []
    issues.extend(_check_duplicate_activity_ids(doc))
    issues.extend(_check_dangling_predecessors(doc))
    issues.extend(_check_dangling_calendars(doc))
    return ValidationReport(issues=issues)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd scheduling/skills/schedule-toolbox && python -m unittest tests.test_xer_validate -v
```
Expected: 6 tests PASS (3 model + 1 duplicates + 2 dangling).

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/xer_validate.py \
        scheduling/skills/schedule-toolbox/tests/test_xer_validate.py \
        scheduling/mcp-server/tests/fixtures/duplicate_ids.xer \
        scheduling/mcp-server/tests/fixtures/dangling_refs.xer
git commit -m "feat(scheduling): xer_validate duplicate + dangling-ref checks"
```

### Task C3: Implement remaining categories — Logic, Data, Network, Structure, Status

For each category, follow the same TDD loop:
1. Build the fixture (`circular_logic.xer`, `orphan_branch.xer`, and corruptions of `minimal.xer` for the Data category).
2. Write a failing test asserting the code is raised on the fixture.
3. Implement the check function.
4. Verify test passes.
5. Commit.

The checks to implement, in order:

- [ ] **`_check_circular_logic`** — DFS on TASKPRED building `pred_task_id → task_id` adjacency. Detect cycles via three-color DFS (white/gray/black). Emit `CIRCULAR_LOGIC` with the cycle path as `affected`. Use `circular_logic.xer` fixture.
- [ ] **`_check_self_loops`** — any TASKPRED row where `pred_task_id == task_id` → `SELF_LOOP` error.
- [ ] **`_check_duplicate_relationships`** — group TASKPRED by `(pred_task_id, task_id, pred_type)`; len > 1 → `DUPLICATE_RELATIONSHIP` error.
- [ ] **`_check_duplicate_calendar_ids`** — group CALENDAR by `clndr_id`; len > 1 → `DUPLICATE_CALENDAR_ID` error.
- [ ] **`_check_duplicate_wbs_codes`** — group PROJWBS by `wbs_short_name` (within same parent); len > 1 → `DUPLICATE_WBS_CODE` error.
- [ ] **`_check_negative_durations`** — TASK rows with `target_drtn_hr_cnt` or `remain_drtn_hr_cnt` < 0 → `NEGATIVE_DURATION` error.
- [ ] **`_check_invalid_dates`** — TASK rows with malformed date fields (not `YYYY-MM-DD HH:MM` or `YYYY-MM-DD`) → `INVALID_DATE` error.
- [ ] **`_check_invalid_relationship_types`** — TASKPRED rows with `pred_type` not in `{PR_FS, PR_SS, PR_FF, PR_SF}` → `INVALID_RELATIONSHIP_TYPE` error.
- [ ] **`_check_invalid_status_codes`** — TASK rows with `status_code` not in `{TK_NotStart, TK_Active, TK_Complete}` → `INVALID_STATUS_CODE` error.
- [ ] **`_check_orphan_activities`** — TASK rows of non-terminal type with zero entries in `pred_task_id`/`task_id` of TASKPRED → `ORPHAN_ACTIVITY` warning.
- [ ] **`_check_orphaned_wbs_branches`** — PROJWBS rows with no child PROJWBS or TASK references → `ORPHANED_WBS_BRANCH` warning. Use `orphan_branch.xer` fixture.
- [ ] **`_check_missing_or_multiple_project_rows`** — `MISSING_PROJECT_ROW` error if zero PROJECT rows; `MULTIPLE_PROJECT_ROWS` warning if >1.
- [ ] **`_check_status_date_mismatch`** — `status_code == TK_Complete` but no `act_end_date` → `STATUS_DATE_MISMATCH` warning.
- [ ] **`_check_actual_after_data_date`** — `act_start_date` or `act_end_date` later than PROJECT's `last_recalc_date` → `ACTUAL_AFTER_DATA_DATE` warning.

After each implementation:

```bash
cd scheduling/skills/schedule-toolbox && python -m unittest tests.test_xer_validate -v
```

Commit each category as its own commit:

```bash
git commit -m "feat(scheduling): xer_validate <category> checks"
```

### Task C4: Wrap validate as the `validate_xer_structure` MCP tool

**Files:**
- Create: `scheduling/mcp-server/tools/xer_validate.py`
- Create: `scheduling/mcp-server/tests/test_xer_validate_wrapper.py`

- [ ] **Step 1: Write the MCP-wrapper test**

```python
# scheduling/mcp-server/tests/test_xer_validate_wrapper.py
"""MCP wrapper tests for validate_xer_structure."""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

from cache import CpmCache  # noqa: E402
from tools.xer_validate import validate_xer_structure_impl  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class TestValidateXerStructureWrapper(unittest.TestCase):
    def test_clean_fixture_is_import_ready(self):
        cache = CpmCache()
        result = validate_xer_structure_impl(str(FIXTURES / "minimal.xer"), cache)
        self.assertTrue(result["import_ready"])
        self.assertEqual(result["summary"]["errors"], 0)

    def test_duplicate_fixture_reports_issue(self):
        cache = CpmCache()
        result = validate_xer_structure_impl(str(FIXTURES / "duplicate_ids.xer"), cache)
        self.assertFalse(result["import_ready"])
        codes = [i["code"] for i in result["issues"]]
        self.assertIn("DUPLICATE_ACTIVITY_ID", codes)

    def test_issue_shape(self):
        cache = CpmCache()
        result = validate_xer_structure_impl(str(FIXTURES / "duplicate_ids.xer"), cache)
        issue = result["issues"][0]
        self.assertIn("severity", issue)
        self.assertIn("category", issue)
        self.assertIn("code", issue)
        self.assertIn("message", issue)
        self.assertIn("affected", issue)
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the wrapper**

```python
# scheduling/mcp-server/tools/xer_validate.py
"""MCP wrapper for validate_xer_structure."""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from xer_validate import validate  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402

_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/xer_validate.py"


def validate_xer_structure_impl(xer_path: str, cache) -> dict:
    """Run file-integrity validation against the XER at xer_path."""
    doc = cache.get_for_writing(xer_path)
    report = validate(doc)
    return {
        "import_ready": report.import_ready,
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "code": i.code,
                "message": i.message,
                "affected": list(i.affected),
            }
            for i in report.issues
        ],
        "summary": report.summary,
    }


def register(mcp, cache):
    @mcp.tool()
    @wrap_tool_errors(tool_name="validate_xer_structure", lib_script=_LIB_SCRIPT)
    def validate_xer_structure(xer_path: str) -> dict:
        """Comprehensive file-integrity validation.

        Distinct from quality_checks (schedule health). Answers "will P6/Procore
        import this file?"

        Returns:
            ``{import_ready: bool, issues: [{severity, category, code, message,
            affected}], summary: {errors, warnings, info}}``
        """
        return validate_xer_structure_impl(xer_path, cache)
```

- [ ] **Step 4: Register in server.py**

```python
# scheduling/mcp-server/server.py — add to existing imports
from tools import (  # noqa: E402
    compare, cpm_path, delay_analysis, omnibus, quality,
    structure, update_analytics, update_review,
    xer_validate,  # NEW
)

# After existing register() calls
xer_validate.register(mcp, _cache)
```

- [ ] **Step 5: Update `test_server.py`**

Append a test assertion that `validate_xer_structure` is in the discovered tool list.

- [ ] **Step 6: Run all tests**

```bash
cd scheduling/mcp-server && python -m unittest discover -s tests -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scheduling/mcp-server/tools/xer_validate.py \
        scheduling/mcp-server/tests/test_xer_validate_wrapper.py \
        scheduling/mcp-server/server.py \
        scheduling/mcp-server/tests/test_server.py
git commit -m "feat(scheduling): validate_xer_structure MCP tool wired into server"
```

---

## Phase D — `lib/xer_modify.py` + `apply_xer_changes`

The biggest phase. Each of the 14 change types gets its own TDD task; then the orchestrator wires them together.

### Task D1: Scaffold `xer_modify.py` with the orchestrator shell

**Files:**
- Create: `scheduling/skills/schedule-toolbox/lib/xer_modify.py`
- Create: `scheduling/skills/schedule-toolbox/tests/test_xer_modify.py`

- [ ] **Step 1: Write the orchestrator-shell test**

```python
# scheduling/skills/schedule-toolbox/tests/test_xer_modify.py
"""Tests for the mutation engine."""
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(LIB))

from xer_modify import (  # noqa: E402
    apply_changes, ApplyResult, ChangeRecord, ValidationFailure,
)


class TestOrchestratorShell(unittest.TestCase):
    def test_empty_changes_returns_no_op(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        ))
        result = apply_changes(doc, [], strict=False, dry_run=False)
        self.assertIsInstance(result, ApplyResult)
        self.assertEqual(result.changes_applied, 0)
        self.assertEqual(result.validation_errors, [])

    def test_unknown_change_type_raises(self):
        from xer_io import parse_for_writing
        doc = parse_for_writing(str(
            Path(__file__).parent.parent.parent.parent
            / "mcp-server" / "tests" / "fixtures" / "minimal.xer"
        ))
        with self.assertRaises(ValidationFailure):
            apply_changes(doc, [{"type": "wat"}], strict=False, dry_run=False)
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the orchestrator shell**

```python
# scheduling/skills/schedule-toolbox/lib/xer_modify.py
"""Mutation engine for XerDoc.

One handler function per change type plus an orchestrator that runs the
3-pass validation and atomic write.

Public API:
    apply_changes(doc, changes, *, strict, dry_run) -> ApplyResult
    fix_duplicate_ids(doc, strategy) -> tuple[XerDoc, dict]
    create_from_template(template_path, metadata) -> XerDoc

Each change-type handler has the signature:
    handler(doc: XerDoc, change: dict, state: ChangeState) -> dict
where state carries cross-change accumulators (newly-added IDs, etc.) and
the return value populates per_change_feedback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---- public types -----------------------------------------------------------


ChangeRecord = dict  # tagged-union shape; validated per type


@dataclass
class ValidationIssueLite:
    """Lite version of the issue shape — keyed to a change_index so the MCP
    can map errors back to specific records."""

    change_index: int | None
    code: str
    message: str


@dataclass
class PerChangeFeedback:
    change_index: int
    type: str
    feedback: dict


@dataclass
class ApplyResult:
    """Output of apply_changes."""

    doc: object | None        # mutated XerDoc; None on validation failure
    changes_applied: int
    validation_errors: list[ValidationIssueLite] = field(default_factory=list)
    validation_warnings: list[ValidationIssueLite] = field(default_factory=list)
    per_change_feedback: list[PerChangeFeedback] = field(default_factory=list)


class ValidationFailure(Exception):
    """Raised by apply_changes when a change record is structurally malformed
    (unknown type, missing required field). Distinguishes 'caller bug' from
    'business rule violation' (which is reported via validation_errors)."""


# ---- handler registry -------------------------------------------------------

_HANDLERS: dict[str, Any] = {}


def _register_handler(change_type: str):
    def decorator(fn):
        _HANDLERS[change_type] = fn
        return fn
    return decorator


# ---- orchestrator -----------------------------------------------------------


@dataclass
class ChangeState:
    """Cross-change accumulator passed to each handler. Tracks new IDs so a
    later add_logic can reference an activity added earlier in the call."""

    new_activity_ids: set[str] = field(default_factory=set)
    new_calendar_ids: set[str] = field(default_factory=set)
    new_wbs_ids: set[str] = field(default_factory=set)
    removed_activity_ids: set[str] = field(default_factory=set)
    removed_wbs_ids: set[str] = field(default_factory=set)


def apply_changes(
    doc,
    changes: list[ChangeRecord],
    *,
    strict: bool,
    dry_run: bool,
) -> ApplyResult:
    """3-pass atomic application of changes to doc.

    Pass 1: syntactic check (per-record required fields, enum validity).
    Pass 2: order-aware reference resolution (apply changes against an
            in-memory copy; track new IDs).
    Pass 3: post-state graph check (orphan rule, cycle check, dup-edge).

    On error: no mutation persisted, errors returned.
    On success (or dry_run): mutations applied to doc; ApplyResult populated.
    """
    result = ApplyResult(doc=None, changes_applied=0)

    # Pass 1: syntactic
    for i, change in enumerate(changes):
        ct = change.get("type")
        if ct not in _HANDLERS:
            raise ValidationFailure(f"Unknown change type at index {i}: {ct!r}")

    if not changes:
        result.doc = doc
        return result

    # Pass 2+3: deferred to D-N tasks
    state = ChangeState()
    for i, change in enumerate(changes):
        handler = _HANDLERS[change["type"]]
        feedback = handler(doc, change, state)
        result.per_change_feedback.append(PerChangeFeedback(
            change_index=i, type=change["type"], feedback=feedback,
        ))
        result.changes_applied += 1

    result.doc = doc
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-toolbox/lib/xer_modify.py \
        scheduling/skills/schedule-toolbox/tests/test_xer_modify.py
git commit -m "feat(scheduling): xer_modify orchestrator shell + handler registry"
```

### Tasks D2–D15: Implement each change-type handler

Each handler follows the same TDD pattern:
1. Write a failing test that exercises the change against a fixture or in-memory `XerDoc`.
2. Implement the handler in `xer_modify.py`.
3. Decorate with `@_register_handler("<change_type>")`.
4. Verify the test passes.
5. Commit.

The change types, in implementation order (simplest first):

- [ ] **D2: `set_duration`** — find TASK row by `activity_id` (matched to `task_code`), set `target_drtn_hr_cnt` and `remain_drtn_hr_cnt` to `new_duration_days * 8.0` (Westland 8h workday), `mark_dirty`. Feedback shape: `{activity_end_before, activity_end_after, milestone_impact_days, now_on_critical_path}` — `activity_end_*` and `milestone_impact_days` populated post-CPM in the orchestrator's final pass (D17); for now stub them as `None`.

- [ ] **D3: `set_calendar`** — validate new calendar exists in state OR in `doc.section("CALENDAR")`; set `clndr_id` on TASK; mark dirty.

- [ ] **D4: `add_logic`** — append row to TASKPRED with `pred_task_id`, `task_id`, `pred_type` from `relationship` (map `"FS"` → `"PR_FS"`, etc.), `lag_hr_cnt = lag_days * 8.0`. Validate (pred, succ, type) doesn't already exist. Generate next `task_pred_id` (max existing + 1).

- [ ] **D5: `remove_logic`** — find row matching `(pred_task_id, task_id, pred_type)` exactly; remove; mark section dirty (which means rebuilding raw_lines is needed — re-index `_dirty`).

- [ ] **D6: `modify_logic`** — find row matching `(pred_task_id, task_id, pred_type)`; update `pred_type` and/or `lag_hr_cnt`; mark dirty.

- [ ] **D7: `add_activity`** — generate task_id (max + 1) and task_code per renumber policy; append TASK row with required fields + defaults; track in `state.new_activity_ids`.

- [ ] **D8: `remove_activity`** — find TASK row by activity_id; remove; also remove all TASKPRED rows referencing it; track in `state.removed_activity_ids`.

- [ ] **D9: `dissolve_activity`** — for each (pred, succ) pair where dissolved task is the connection, create new edge `pred -FS+(pred_lag + dissolved_duration + succ_lag)-> succ` with relationship type derived from P6 dissolve rules (FS×FS → FS, FS×SS → SS, etc.). Use `dissolve_fanout.xer` fixture. Warn if new edges > 20.

- [ ] **D10: `pop_activity`** — validate `(pred, succ)` edge exists; remove it; add new activity X; add A→X and X→B edges per `split_lag` policy.

- [ ] **D11: `add_wbs`** — generate wbs_id; derive `wbs_short_name` if omitted; append PROJWBS row.

- [ ] **D12: `remove_wbs`** — handle `cascade` enum; check referenced-by-activity if `fail_if_used`; reparent if `move_to_parent`.

- [ ] **D13: `modify_wbs`** — update fields; check cycle on parent change.

- [ ] **D14: `move_activities_to_wbs`** — bulk set TASK.wbs_id.

- [ ] **D15: `apply_anchor_absorption`** — re-invoke the anchor-absorption-suggestion logic from `path_analysis`/`cpm_engine`; lower the chosen suggestion to one or more `set_duration` changes; delegate to those handlers.

Each task: write failing test, implement, pass test, commit. Approximate effort: 30 min – 2 hr each, longer for D9 (dissolve) and D10 (pop) due to relationship-type math.

### Task D16: Implement Pass 2 reference resolution + Pass 3 graph checks

**Files:**
- Modify: `scheduling/skills/schedule-toolbox/lib/xer_modify.py`
- Modify: `scheduling/skills/schedule-toolbox/tests/test_xer_modify.py`

- [ ] **Step 1: Write the validation tests**

Cover: (a) order-aware reference resolution (add_activity at index 0, add_logic referencing it at index 1 — should succeed); (b) orphan rule (add_activity with no add_logic — should error); (c) cycle check (add_logic introducing a cycle — should error); (d) dry_run path (errors prevented from writing doc).

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement Pass 2 and Pass 3**

Wrap the handler loop in a try/except; collect errors per-change; if any errors and `dry_run=False`, return `ApplyResult` with `doc=None`. If `strict=True`, treat warnings as errors. After successful pass, run `xer_validate.validate` on the mutated doc (Pass 3) and treat any new error-severity issues as orchestrator errors.

- [ ] **Step 4: Verify tests pass**

- [ ] **Step 5: Commit**

### Task D17: Wire per-change feedback to post-CPM diff

After the orchestrator completes Pass 3 successfully (and not dry_run), invoke `cpm_engine.schedule_forward_backward` on the post-state. Compare against the cached pre-state CPM (passed in from the MCP layer). Populate the previously-stubbed feedback fields (`activity_end_before`, `activity_end_after`, `milestone_impact_days`, `critical_path_changed`, etc.).

- [ ] **Step 1: Test feedback shape**
- [ ] **Step 2: Implement feedback computation**
- [ ] **Step 3: Verify**
- [ ] **Step 4: Commit**

### Task D18: MCP wrapper `apply_xer_changes`

**Files:**
- Create: `scheduling/mcp-server/tools/xer_modify.py`
- Create: `scheduling/mcp-server/tests/test_apply_xer_changes.py`

Wrapper responsibilities:
1. `cache.pin(xer_path)` on entry, `cache.unpin(xer_path)` in `finally`.
2. `cache.get_for_writing(xer_path)` — get doc.
3. Call `apply_changes(doc, changes, strict=strict, dry_run=dry_run)`.
4. If success and not dry_run: derive `output_path` (caller-supplied or `<input>-modified.xer`); refuse collision; call `xer_io.write(doc, output_path)`.
5. Insert mutated doc + post-CPM into cache under output path.
6. Marshal `ApplyResult` into the spec's output JSON shape (with `post_cpm_summary`, etc.).

Follow the TDD pattern. Reuse the existing `error_help.wrap_tool_errors` decorator.

- [ ] **Steps 1–5: TDD loop + commit**

### Task D19: Register `apply_xer_changes` in server.py + test_server.py

- [ ] **Step 1: Add `from tools import xer_modify` + `xer_modify.register(mcp, _cache)`.**
- [ ] **Step 2: Update `test_server.py` to assert `apply_xer_changes` is in tool list.**
- [ ] **Step 3: Run full suite. Commit.**

---

## Phase E — Skeleton extraction

Goal: `westland-skeleton-v1.xer` + `westland-skeleton-v1.notes.md` produced via agent-per-table investigation of 10–15 corpus XERs. Commits before Phase F (which depends on the skeleton existing).

### Task E1: Pull corpus + run agent-per-table investigation

This task is research, not code. Run in the user's local environment with `WESTLAND_CORPUS` set.

- [ ] **Step 1: Confirm corpus availability**

```powershell
$env:WESTLAND_CORPUS = "$env:USERPROFILE\OneDrive - Westland Construction\40 Cowork\training_data"
Get-ChildItem "$env:WESTLAND_CORPUS\Proposal Schedules\*.xer"
Get-ChildItem "$env:WESTLAND_CORPUS\Schedules & Schedule Grades\*.xer"
```

Expected: ≥ 7 files in Proposal Schedules. At least 5 readable XERs in Schedules & Schedule Grades.

- [ ] **Step 2: Dispatch agent-per-table investigation**

Use the `Agent` tool with the `Explore` subagent type. One dispatch per table:

```
For each table in [PROJECT, CALENDAR, PROJWBS, RSRC, ACTVTYPE, ACTVCODE,
                   UDFTYPE, SCHEDOPTIONS, FINDATES, ROLES, "everything else"]:
  Dispatch Explore agent with prompt:
    "Read the raw %T <TABLE> block from every .xer in
     <corpus_root>/Proposal Schedules/ and <corpus_root>/Schedules & Schedule Grades/.
     Report:
       1. Which fields are populated in every file (always present, non-empty).
       2. Which fields hold identical values across all files (true constants).
       3. Which fields vary by project (parameters for create_xer_from_template).
       4. Text-level quirks: whitespace, sentinel values (Yes/No vs Y/N vs 1/0),
          encoding artifacts, field-order conventions.
       5. Anomalies — a field populated in only 1 file (probably project-specific).
     Output structured prose, ~500 words max, ready for a human curator to act on."
```

Collect all 11 reports under `/tmp/skeleton-investigation/` or similar.

- [ ] **Step 3: Commit the reports**

```bash
mkdir -p scheduling/mcp-server/templates/.investigation
# Copy reports in
git add scheduling/mcp-server/templates/.investigation/
git commit -m "investigate(scheduling): agent-per-table corpus analysis for skeleton v1"
```

### Task E2: Curate `westland-skeleton-v1.xer`

This is human-driven. Read all 11 investigation reports + the existing Westland docs (`wbs-patterns.md`, `westland-procedures-summary.md`, `westland-procedures.md`, `xer-generation.md`, `build_from_raw_template.py` comments).

Process:

1. Pick a base donor (likely `BTLP.xer` — the cleanest proposal in the corpus).
2. Copy its bytes to `scheduling/mcp-server/templates/westland-skeleton-v1.xer`.
3. Hand-edit:
   - Strip all activity content except 2 milestones (NTP, SC) and 1 FS edge.
   - Set PROJECT row to template placeholders (project_id = "TEMPLATE", project_name = "TEMPLATE", etc.) — `create_xer_from_template` substitutes these.
   - Apply constants identified per-table in investigation reports.
   - Set WBS to canonical Westland tree (no DEMOLITION branch).
4. Write the sidecar notes file documenting every decision.

- [ ] **Step 1: Curate**

- [ ] **Step 2: Verify round-trip + validate**

```bash
python -c "
import sys
sys.path.insert(0, 'scheduling/skills/schedule-toolbox/lib')
from xer_io import parse_for_writing, write
from xer_validate import validate
doc = parse_for_writing('scheduling/mcp-server/templates/westland-skeleton-v1.xer')
write(doc, '/tmp/skeleton-rt.xer')

import filecmp
assert filecmp.cmp('scheduling/mcp-server/templates/westland-skeleton-v1.xer',
                   '/tmp/skeleton-rt.xer', shallow=False), 'round-trip failed'

report = validate(doc)
print('import_ready:', report.import_ready)
print('summary:', report.summary)
for i in report.issues:
    print(f'  {i.severity:7} {i.code}: {i.message}')
assert report.import_ready, 'skeleton not import-ready'
"
```

Expected: round-trip identical, `import_ready: true`, 0 errors. Iterate until clean.

- [ ] **Step 3: Manual P6 + Procore import gate**

Open `westland-skeleton-v1.xer` in:
- Primavera P6: File → Import → XER → confirm no warnings about missing tables.
- Procore: Project → Schedule → Import → confirm clean import.

If either reports an issue, return to Step 1, fix, repeat.

- [ ] **Step 4: Commit**

```bash
git add scheduling/mcp-server/templates/westland-skeleton-v1.xer \
        scheduling/mcp-server/templates/westland-skeleton-v1.notes.md \
        scheduling/mcp-server/templates/__init__.py
git commit -m "feat(scheduling): hand-curated westland-skeleton-v1 + curation notes"
```

---

## Phase F — `create_xer_from_template` + `fix_duplicate_activity_ids`

### Task F1: Implement `create_from_template` in `xer_modify.py`

- [ ] **Step 1: Write the test**

```python
class TestCreateFromTemplate(unittest.TestCase):
    def test_loads_skeleton_and_sets_metadata(self):
        from xer_modify import create_from_template
        skeleton = (Path(__file__).parent.parent.parent.parent
                    / "mcp-server" / "templates" / "westland-skeleton-v1.xer")
        metadata = {
            "project_name": "Test Project",
            "project_id":   "TEST-001",
            "planned_start": "2026-06-01",
            "planned_data_date": "2026-06-01 08:00",
        }
        doc = create_from_template(str(skeleton), metadata)
        project_row = doc.section("PROJECT").rows[0]
        self.assertEqual(project_row["proj_short_name"], "Test Project")
        # NTP and SC milestone IDs are returned via separate API
```

- [ ] **Steps 2–5: implement, verify, commit**

### Task F2: Implement `fix_duplicate_ids` in `xer_modify.py`

Renumber strategy per open-question #3. Strategies: `renumber` (default), `report_only`, `merge_consolidate`. Return `(mutated_doc, mapping_dict)`.

- [ ] **Steps 1–5: TDD loop + commit**

### Task F3: MCP wrappers for `create_xer_from_template` + `fix_duplicate_activity_ids`

In `scheduling/mcp-server/tools/xer_modify.py` (the same module that already wraps `apply_xer_changes`):

- [ ] **Steps 1–5: implement wrappers, register, test, commit**

### Task F4: End-to-end skeleton → Pattern B integration test

Build a hand-curated `wbs_pattern_b_target.xer` fixture (Section 7 of spec). Write an integration test that:

1. Calls `create_xer_from_template` with sample metadata.
2. Calls `apply_xer_changes` with a Pattern B change set: `add_wbs` × 5 (DEMOLITION + 5 sub-branches) + `add_activity` × ~10 (demolition activities) + `add_logic` × ~12 (FS chains).
3. Calls `validate_xer_structure` → expects `import_ready: true`.
4. Compares the output structure (WBS tree, activity count) to `wbs_pattern_b_target.xer`.

- [ ] **Steps 1–5: write fixture + test + commit**

---

## Phase G — Skill updates

### Task G1: Update `schedule-toolbox/SKILL.md` routing table

- [ ] **Step 1: Read existing SKILL.md to see current routing-table format.**
- [ ] **Step 2: Add the 5 new MCP tool names to the routing table.**
- [ ] **Step 3: Add new "Modifying XER files" subsection per spec Section 8.**
- [ ] **Step 4: Commit.**

### Task G2: Update `schedule-toolbox/references/xer-modify.md`

- [ ] **Step 1: Read current xer-modify.md.**
- [ ] **Step 2: Replace guidance with `apply_xer_changes` + each change-type example.**
- [ ] **Step 3: Commit.**

### Task G3: Update `schedule-toolbox/references/xer-generation.md`

- [ ] **Step 1: Document `create_xer_from_template` as the canonical entry point.**
- [ ] **Step 2: Note `build_from_raw_template.py` is historical reference.**
- [ ] **Step 3: Commit.**

### Task G4: Update `schedule-create-proposal-schedule` skill

- [ ] **Step 1: Read SKILL.md and `wbs-patterns.md`.**
- [ ] **Step 2: Update Claude-facing phases to use the compositional flow (`create_xer_from_template` → `apply_xer_changes`).**
- [ ] **Step 3: Each pattern in `wbs-patterns.md` gains a "MCP change records for this pattern" subsection.**
- [ ] **Step 4: Commit.**

---

## Phase H — End-to-end smoke + release

### Task H1: Bump versions

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Bump `scheduling/.claude-plugin/plugin.json` version 8.1.3 → 9.0.0.**
- [ ] **Step 2: Bump `.claude-plugin/marketplace.json` scheduling entry to 9.0.0.**
- [ ] **Step 3: Commit.**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore(scheduling): release 9.0.0 (Tier 3 modification + generation)"
```

### Task H2: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd scheduling/skills/schedule-toolbox && python -m unittest discover -s tests -v
cd ../../mcp-server && python -m unittest discover -s tests -v
```

Expected: all PASS.

- [ ] **Step 2: Run corpus round-trip suite locally**

```powershell
$env:WESTLAND_CORPUS = "$env:USERPROFILE\OneDrive - Westland Construction\40 Cowork\training_data"
cd scheduling/skills/schedule-toolbox
python -m unittest tests.test_xer_io.TestCorpusRoundTrip -v
```

Expected: 7 subtests PASS.

### Task H3: End-to-end smoke against a real project

Per Section 7 of the spec:

- [ ] **Smoke 1: Skeleton-to-proposal.** Pick a real proposal-stage project. Generate a Pattern B schedule via `create_xer_from_template` + `apply_xer_changes`. Validate. Manually import into P6 + Procore. Confirm tree layout, milestones, dates.

- [ ] **Smoke 2: Modify-existing.** Pick a current Westland project XER. Apply a 5-change mixed set. Open in P6. Confirm changes landed cleanly.

- [ ] **Smoke 3: Validation.** Run `validate_xer_structure` against the same Wellington XER. Confirm `import_ready: true`. Hand-corrupt a copy. Re-run. Confirm correct codes and `affected` arrays.

- [ ] **Document smoke results in the release PR description.**

### Task H4: Open the PR

- [ ] **Step 1: Push branch and open PR with smoke results in the description.**
- [ ] **Step 2: Wait for CI (version-bump check + personal-path lint).**
- [ ] **Step 3: Merge after review.**

### Task H5: Build and distribute

From the main repo working tree (NOT a worktree):

```bash
cd ~/code/construction-skills
git switch main
git pull --ff-only
python build.py scheduling
```

- [ ] **Step 1: Confirm `src/scheduling.zip` was rebuilt.**
- [ ] **Step 2: Distribute to the 4 schedulers via enterprise install.**

---

## Self-Review checklist

After completing the plan, verify against the spec:

**Spec coverage** — every section in `2026-05-27-scheduler-mcp-tier-3-modification-design.md`:
- Section 1 (Scope) → Phases A, B, C, D, F (tools), E (skeleton)
- Section 2 (14 change types) → Tasks D2–D15
- Section 3 (Validation + output) → Tasks D16, D17, D18
- Section 4 (validate + fix_duplicates) → Phase C + Tasks F2, F3
- Section 5 (xer_io + cache) → Phases A, B
- Section 6 (skeleton extraction) → Phase E
- Section 7 (tests + fixtures + smoke) → All TDD steps + Task H3
- Section 8 (integration + release) → Phase G + Tasks H1, H4, H5
- Risk table → Manual smoke (H3) addresses each
- Open Questions → Resolved at top of this plan

**Placeholder scan** — no TBD/TODO/FIXME in this document. Tasks D2–D15 (the 14 handlers) leave implementation skeleton-level intentionally; each task has explicit TDD steps but the full handler body is left for the executor to write per the test it just wrote. This is consistent with the per-handler tests pinning the behavior contract.

**Type consistency:**
- `XerDoc` / `XerSection` / `ChangeRecord` / `ApplyResult` / `ValidationIssue` / `ValidationReport` defined once, referenced consistently.
- `cache.get_for_writing` returns `XerDoc`; matches what every write-path tool calls.
- `apply_changes` signature: `(doc, changes, *, strict, dry_run)` — matches in Task D1 and Task D18 (MCP wrapper).

**Spec requirement audit:**
- Five MCP tools (validate_xer_structure, apply_xer_changes, fix_duplicate_activity_ids, create_xer_from_template, invalidate_cache_for) → ✓
- 14 change types → D2–D15 ✓
- 3-pass validation + dry_run + strict → D16 ✓
- Per-change feedback via single CPM run → D17 ✓
- xer_io round-trip identity on 7 corpus XERs → A5 ✓
- Cache pin/unpin/recency + auto-pin during writes → B3, D18 ✓
- Skeleton + notes + Westland default WBS → E1, E2 ✓
- All change types tested at lib + wrapper layers → D2–D15 + D18 ✓
- 9.0.0 release with manual smoke → H1, H3 ✓

Plan complete.
