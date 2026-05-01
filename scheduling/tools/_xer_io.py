"""Shared XER read/write helpers for the proposal-iterate CLI tools.

Centralizes parse_xer + write_xer_with_updates so each CLI doesn't
re-implement the table-tracking write-back loop. Westland rule: never
overwrite the input. write_xer_with_updates always writes to a new path.
"""

from pathlib import Path
import re


_XER_ENCODINGS = ('cp1252', 'utf-8-sig', 'utf-8', 'latin-1')


def parse_xer(path):
    """Parse a P6 XER file. Returns (tables, table_fields, original_text).

    tables: {table_name: [row_dict, ...]}
    table_fields: {table_name: [field_name, ...]}
    original_text: the decoded source string, preserved for write-back.
    """
    raw = Path(path).read_bytes()
    text = None
    for enc in _XER_ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        raise ValueError(f"Could not decode XER {path} with any of {_XER_ENCODINGS}")

    tables = {}
    table_fields = {}
    current = None
    fields = []
    for line in text.split('\r\n'):
        if line.startswith('%T'):
            current = line.split('\t')[1].strip()
            tables[current] = []
        elif line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
            table_fields[current] = fields
        elif line.startswith('%R') and current:
            tables[current].append(dict(zip(fields, line.split('\t')[1:])))
    return tables, table_fields, text


def find_latest_xer(project_folder):
    """Return (path, version_int) of the latest -v{N}.xer in the project folder.

    Looks under <project>/Proposal Schedule/ (the Westland convention).
    Returns None if no -v{N}.xer is present.
    """
    proposal_dir = Path(project_folder) / 'Proposal Schedule'
    if not proposal_dir.is_dir():
        proposal_dir = Path(project_folder)
    pattern = re.compile(r'-v(\d+)\.xer$', re.IGNORECASE)
    best = None
    for f in proposal_dir.glob('*.xer'):
        m = pattern.search(f.name)
        if not m:
            continue
        v = int(m.group(1))
        if best is None or v > best[1]:
            best = (f, v)
    return best


def next_xer_path(latest_path, latest_version):
    """Given the current `-v{N}.xer` path, return the `-v{N+1}.xer` path."""
    p = Path(latest_path)
    new_name = re.sub(
        rf'-v{latest_version}\.xer$',
        f'-v{latest_version + 1}.xer',
        p.name,
        flags=re.IGNORECASE,
    )
    return p.with_name(new_name)


def write_xer_with_updates(original_text, table_fields, updates_by_table, output_path):
    """Re-emit an XER, replacing %R rows in the named tables.

    updates_by_table: {table_name: {row_key_field: {field: new_value, ...}, ...}}
        For TASK, row_key_field is implicitly 'task_id'. For other tables the
        caller passes (table_name, key_field) tuples wrapping the dict.

    To keep the API simple, callers should structure updates_by_table as:
        {'TASK': ('task_id', {tid: {...}, ...})}

    Lines outside the targeted tables are passed through unchanged so
    untouched tables stay byte-identical.
    """
    out_lines = []
    current = None
    fields = []
    table_update_spec = updates_by_table  # alias

    for line in original_text.split('\r\n'):
        if line.startswith('%T'):
            current = line.split('\t')[1].strip()
            out_lines.append(line)
            continue
        if line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
            out_lines.append(line)
            continue
        if line.startswith('%R') and current and current in table_update_spec:
            key_field, row_updates = table_update_spec[current]
            parts = line.split('\t')[1:]
            row = dict(zip(fields, parts))
            key = row.get(key_field, '')
            if key in row_updates:
                row.update(row_updates[key])
            new_line = '%R\t' + '\t'.join(row.get(f, '') for f in fields)
            out_lines.append(new_line)
            continue
        out_lines.append(line)

    output = '\r\n'.join(out_lines)
    if not output.endswith('\r\n'):
        output += '\r\n'
    Path(output_path).write_bytes(output.encode('cp1252'))
