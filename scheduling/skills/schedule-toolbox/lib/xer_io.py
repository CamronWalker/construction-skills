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


_ENCODINGS = ("cp1252", "utf-8-sig", "utf-8", "latin-1")


def _detect_decode(raw: bytes) -> tuple[str, str]:
    """Try the encoding fallback chain. Returns (text, encoding_used).

    latin-1 is the guaranteed last entry: it's single-byte and decodes any
    sequence, so the loop always succeeds before exhaustion.
    """
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    # Unreachable in practice (latin-1 in _ENCODINGS never raises), but
    # static analyzers want all paths to return.
    raise RuntimeError(f"Failed to decode XER with any of {_ENCODINGS}")


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

    # Guard against LF-only line endings -- P6 always writes CRLF, but a
    # cross-platform copy via wsl/scp without text-mode translation may have
    # stripped the \r. Silently splitting on \r\n would yield one giant line
    # and an empty XerDoc -- surface the issue instead.
    if "\r\n" in text:
        lines = text.split("\r\n")
    elif "\n" in text:
        # File appears to be LF-only. Either malformed or stripped during
        # transfer. Raise so the caller knows.
        raise ValueError(
            f"XER at {xer_path!r} appears to use LF-only line endings. "
            f"P6 writes CRLF -- re-export from P6 or convert the file."
        )
    else:
        lines = [text]  # single-line file: pathological but parse what we have

    header_line = ""
    sections: list[XerSection] = []
    current: Optional[XerSection] = None

    for line in lines:
        if not line:
            continue
        parts = line.split("\t")
        marker = parts[0]
        if marker == "ERMHDR":
            header_line = line
        elif marker == "%T":
            current = XerSection(
                name=parts[1].strip(),
                field_order=[],
                rows=[],
                raw_lines=[],
                e_line="%E",
            )
            sections.append(current)
        elif marker == "%F" and current is not None:
            current.field_order = [f.strip() for f in parts[1:]]
        elif marker == "%R" and current is not None:
            current.raw_lines.append(line)
            current.rows.append(dict(zip(current.field_order, parts[1:])))
        elif marker == "%E" and current is not None:
            current.e_line = line
            current = None

    return XerDoc(
        header_line=header_line,
        encoding=encoding,
        sections=sections,
    )
