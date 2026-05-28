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
