"""
Unit tests for the project-context -> Supabase mapping module.

Phase-0 of the project-context-supabase refactor. The mapping module is
the pure, stub-testable seam between the parsed project-context.html dict
and the wnd_projects / wnd_project_log Supabase rows. No network, no MCP
calls live here -- those belong to the calling skill.

Contract pinned by these tests:
  * project_row_to_context  -- DB row -> binding dict (binding keys only;
    NO recipients / signer / graph / contractual keys leak through).
  * parsed_context_to_project_row -- parser dict -> wnd_projects UPSERT
    payload (job_number + binding columns only; every cut field DROPPED).
  * parsed_context_to_log_entries -- parser project_log -> wnd_project_log
    rows ({body, created_at, category}); dates preserved, category 'note'.
  * retire_context_html -- rename project-context.html ->
    project-context-migrated.html; collision-safe; FileNotFoundError on
    missing source.

Run from repo root:
    python -m unittest scheduling.skills.schedule-project-init.tests.test_project_context_db_mapping

or directly:
    python scheduling/skills/schedule-project-init/tests/test_project_context_db_mapping.py
"""

import os
import pathlib
import re
import sys
import tempfile
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import project_context_db_mapping as mapping  # noqa: E402


# The exact set of columns wnd_projects stores from the parsed context
# (server-managed id / spm_project_id / source / created_by_email /
# created_at / updated_at are NOT part of the parser-derived payload).
BINDING_COLUMNS = (
    'project_name',
    'smartpm_url',
    'smartpm_trends_url',
    'smartpm_changelog_url',
    'smartpm_project_name',
    'procore_company_id',
    'procore_project_id',
    'procore_documents_folder_id',
)

# Fields that the approved spec DELIBERATELY drops -- they must never
# appear in a wnd_projects payload nor in the DB-row -> context adapter
# output.
CUT_FIELDS = (
    'to_recipients',
    'cc_recipients',
    'to_recipients_str',
    'cc_recipients_str',
    'signer_name',
    'signer_title',
    'signer_mobile',
    'graph_screenshots',
    'graph_order',
    'contractual_completion',
)


def _full_parsed():
    """A realistic parser output dict -- every key parse_project_context_html
    emits, populated."""
    return {
        'project_name': 'Lubumbashi DR Congo Temple',
        'job_number': 'W1177',
        'contractual_completion': '2027-09-30',
        'smartpm_url': 'https://live.smartpmtech.com/projects/abc/workspace',
        'smartpm_trends_url':
            'https://live.smartpmtech.com/projects/abc/trends?tab=Graphs',
        'smartpm_changelog_url':
            'https://live.smartpmtech.com/projects/abc/changelog',
        'smartpm_project_name': 'Lubumbashi DR Congo Temple',
        'signer_name': 'Carter Brown',
        'signer_title': 'Project Scheduler',
        'signer_mobile': '+1 801.555.1234',
        'procore_company_id': '11093',
        'procore_project_id': '2646569',
        'procore_documents_folder_id': '4592384',
        'graph_screenshots': [
            '06-end-date-variance.png',
            '07-schedule-compression-index-over-time.png',
        ],
        'project_log': [
            {'date': '2026-04-15', 'body': 'EOT #1 filed -- 14 calendar days.'},
            {'date': '2026-05-07', 'body': 'Re-init context with new signer.'},
        ],
        'to_recipients': [
            {'name': 'Owner Rep', 'email': 'owner@example.com'},
            {'name': '', 'email': 'arch@example.com'},
        ],
        'cc_recipients': [
            {'name': 'PM', 'email': 'pm@westlandconstruction.com'},
        ],
        'to_recipients_str': 'Owner Rep <owner@example.com>; arch@example.com',
        'cc_recipients_str': 'pm@westlandconstruction.com',
    }


def _full_db_row():
    """A wnd_projects row as get_project would return it -- binding columns
    plus the server-managed fields the adapter must ignore."""
    return {
        'id': 42,
        'spm_project_id': 9001,
        'source': 'project-context.html',
        'created_by_email': 'camron@westlandconstruction.com',
        'created_at': '2026-05-07T12:00:00Z',
        'updated_at': '2026-05-07T12:00:00Z',
        'job_number': 'W1177',
        'project_name': 'Lubumbashi DR Congo Temple',
        'smartpm_url': 'https://live.smartpmtech.com/projects/abc/workspace',
        'smartpm_trends_url':
            'https://live.smartpmtech.com/projects/abc/trends?tab=Graphs',
        'smartpm_changelog_url':
            'https://live.smartpmtech.com/projects/abc/changelog',
        'smartpm_project_name': 'Lubumbashi DR Congo Temple',
        'procore_company_id': '11093',
        'procore_project_id': '2646569',
        'procore_documents_folder_id': '4592384',
    }


class ProjectRowToContextTests(unittest.TestCase):
    """DB row -> binding dict. Binding keys round-trip; cut keys never
    appear."""

    def test_all_bindings_round_trip(self):
        row = _full_db_row()
        ctx = mapping.project_row_to_context(row)
        for col in BINDING_COLUMNS:
            self.assertEqual(
                ctx[col], row[col],
                'binding %r did not round-trip through adapter' % col,
            )

    def test_no_cut_field_leaks(self):
        ctx = mapping.project_row_to_context(_full_db_row())
        for cut in CUT_FIELDS:
            self.assertNotIn(
                cut, ctx,
                'cut field %r must not appear in adapter output' % cut,
            )

    def test_server_managed_fields_not_emitted_as_bindings(self):
        # job_number is a key column but is NOT one of the binding keys the
        # parser uses for template substitution; the adapter emits only the
        # binding set, so server-managed and key columns stay out of the
        # binding dict.
        ctx = mapping.project_row_to_context(_full_db_row())
        for k in ('id', 'spm_project_id', 'source', 'created_by_email',
                  'created_at', 'updated_at'):
            self.assertNotIn(k, ctx)

    def test_output_keys_are_exactly_the_binding_set(self):
        ctx = mapping.project_row_to_context(_full_db_row())
        self.assertEqual(set(ctx.keys()), set(BINDING_COLUMNS))

    def test_missing_columns_default_to_empty_string(self):
        # get_project may return a sparse row; the adapter must not KeyError.
        ctx = mapping.project_row_to_context({'project_name': 'X'})
        self.assertEqual(ctx['project_name'], 'X')
        for col in BINDING_COLUMNS:
            self.assertIn(col, ctx)
        self.assertEqual(ctx['smartpm_url'], '')
        self.assertEqual(ctx['procore_documents_folder_id'], '')

    def test_none_values_normalize_to_empty_string(self):
        row = _full_db_row()
        row['smartpm_trends_url'] = None
        row['procore_documents_folder_id'] = None
        ctx = mapping.project_row_to_context(row)
        self.assertEqual(ctx['smartpm_trends_url'], '')
        self.assertEqual(ctx['procore_documents_folder_id'], '')

    def test_empty_row_is_safe(self):
        ctx = mapping.project_row_to_context({})
        self.assertEqual(set(ctx.keys()), set(BINDING_COLUMNS))
        self.assertTrue(all(v == '' for v in ctx.values()))


class ParsedContextToProjectRowTests(unittest.TestCase):
    """Parser dict -> wnd_projects UPSERT payload."""

    def test_keeps_every_binding(self):
        parsed = _full_parsed()
        row = mapping.parsed_context_to_project_row(parsed)
        for col in BINDING_COLUMNS:
            self.assertEqual(
                row[col], parsed[col],
                'binding column %r missing/wrong in upsert payload' % col,
            )

    def test_keeps_job_number(self):
        row = mapping.parsed_context_to_project_row(_full_parsed())
        self.assertEqual(row['job_number'], 'W1177')

    def test_drops_every_cut_field(self):
        row = mapping.parsed_context_to_project_row(_full_parsed())
        for cut in CUT_FIELDS:
            self.assertNotIn(
                cut, row,
                'cut field %r must be DROPPED from upsert payload' % cut,
            )

    def test_drops_project_log(self):
        # project_log goes to the SEPARATE wnd_project_log table, never into
        # the wnd_projects row.
        row = mapping.parsed_context_to_project_row(_full_parsed())
        self.assertNotIn('project_log', row)

    def test_payload_keys_are_exactly_job_number_plus_bindings(self):
        row = mapping.parsed_context_to_project_row(_full_parsed())
        self.assertEqual(
            set(row.keys()), set(('job_number',)) | set(BINDING_COLUMNS),
        )

    def test_job_number_from_caller_when_absent_in_parsed(self):
        parsed = _full_parsed()
        parsed.pop('job_number', None)
        row = mapping.parsed_context_to_project_row(parsed, job_number='W9999')
        self.assertEqual(row['job_number'], 'W9999')

    def test_explicit_job_number_overrides_parsed(self):
        row = mapping.parsed_context_to_project_row(
            _full_parsed(), job_number='W0001',
        )
        self.assertEqual(row['job_number'], 'W0001')

    def test_graph_filenames_not_carried(self):
        # graph_screenshots-style filenames are never carried into the row.
        row = mapping.parsed_context_to_project_row(_full_parsed())
        flat = ' '.join(str(v) for v in row.values())
        self.assertNotIn('.png', flat)

    def test_missing_bindings_default_empty(self):
        row = mapping.parsed_context_to_project_row(
            {'job_number': 'W1234', 'project_name': 'Sparse'},
        )
        self.assertEqual(row['project_name'], 'Sparse')
        self.assertEqual(row['smartpm_url'], '')
        self.assertEqual(row['procore_documents_folder_id'], '')

    def test_none_bindings_normalize_to_empty_string(self):
        parsed = _full_parsed()
        parsed['smartpm_changelog_url'] = None
        row = mapping.parsed_context_to_project_row(parsed)
        self.assertEqual(row['smartpm_changelog_url'], '')


class ParsedContextToLogEntriesTests(unittest.TestCase):
    """Parser project_log -> wnd_project_log rows."""

    def test_maps_each_entry(self):
        entries = mapping.parsed_context_to_log_entries(_full_parsed())
        self.assertEqual(len(entries), 2)

    def test_body_and_date_preserved(self):
        entries = mapping.parsed_context_to_log_entries(_full_parsed())
        by_date = {e['created_at']: e['body'] for e in entries}
        self.assertEqual(
            by_date['2026-04-15'], 'EOT #1 filed -- 14 calendar days.',
        )
        self.assertEqual(
            by_date['2026-05-07'], 'Re-init context with new signer.',
        )

    def test_category_defaults_to_note(self):
        entries = mapping.parsed_context_to_log_entries(_full_parsed())
        for e in entries:
            self.assertEqual(e['category'], 'note')

    def test_entry_shape_is_exact(self):
        entries = mapping.parsed_context_to_log_entries(_full_parsed())
        for e in entries:
            self.assertEqual(set(e.keys()), {'body', 'created_at', 'category'})

    def test_missing_date_becomes_none(self):
        parsed = {'project_log': [{'body': 'No date here'}]}
        entries = mapping.parsed_context_to_log_entries(parsed)
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]['created_at'])
        self.assertEqual(entries[0]['body'], 'No date here')
        self.assertEqual(entries[0]['category'], 'note')

    def test_empty_date_becomes_none(self):
        parsed = {'project_log': [{'date': '', 'body': 'Blank date'}]}
        entries = mapping.parsed_context_to_log_entries(parsed)
        self.assertIsNone(entries[0]['created_at'])

    def test_no_log_key_returns_empty_list(self):
        self.assertEqual(mapping.parsed_context_to_log_entries({}), [])

    def test_empty_log_returns_empty_list(self):
        self.assertEqual(
            mapping.parsed_context_to_log_entries({'project_log': []}), [],
        )

    def test_missing_body_defaults_to_empty_string(self):
        parsed = {'project_log': [{'date': '2026-01-01'}]}
        entries = mapping.parsed_context_to_log_entries(parsed)
        self.assertEqual(entries[0]['body'], '')
        self.assertEqual(entries[0]['created_at'], '2026-01-01')

    def test_order_preserved(self):
        parsed = {'project_log': [
            {'date': '2026-01-01', 'body': 'first'},
            {'date': '2026-02-02', 'body': 'second'},
            {'date': '2026-03-03', 'body': 'third'},
        ]}
        entries = mapping.parsed_context_to_log_entries(parsed)
        self.assertEqual([e['body'] for e in entries],
                         ['first', 'second', 'third'])


class RetireContextHtmlTests(unittest.TestCase):
    """Rename project-context.html -> project-context-migrated.html."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, 'project-context.html')

    def _write(self, path, body='<html></html>'):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(body)

    def test_renames_to_migrated(self):
        self._write(self.src, '<html>original</html>')
        new_path = mapping.retire_context_html(self.src)
        self.assertEqual(
            os.path.basename(new_path), 'project-context-migrated.html',
        )
        self.assertTrue(os.path.isfile(new_path))
        self.assertFalse(os.path.isfile(self.src))
        with open(new_path, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), '<html>original</html>')

    def test_new_path_is_in_same_dir(self):
        self._write(self.src)
        new_path = mapping.retire_context_html(self.src)
        self.assertEqual(
            os.path.dirname(os.path.abspath(new_path)),
            os.path.dirname(os.path.abspath(self.src)),
        )

    def test_collision_appends_numeric_suffix(self):
        self._write(self.src, 'second-migration')
        # A migrated file already exists from a prior run.
        existing = os.path.join(
            self.tmp.name, 'project-context-migrated.html',
        )
        self._write(existing, 'first-migration')
        new_path = mapping.retire_context_html(self.src)
        # Must NOT clobber the existing migrated file.
        self.assertNotEqual(
            os.path.abspath(new_path), os.path.abspath(existing),
        )
        self.assertTrue(os.path.isfile(new_path))
        with open(existing, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'first-migration')
        with open(new_path, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'second-migration')
        # Suffix form: project-context-migrated-2.html (or similar numeric).
        self.assertRegex(
            os.path.basename(new_path),
            r'^project-context-migrated-\d+\.html$',
        )

    def test_second_collision_keeps_incrementing(self):
        self._write(os.path.join(
            self.tmp.name, 'project-context-migrated.html'), 'a')
        self._write(os.path.join(
            self.tmp.name, 'project-context-migrated-2.html'), 'b')
        self._write(self.src, 'third')
        new_path = mapping.retire_context_html(self.src)
        self.assertTrue(os.path.isfile(new_path))
        self.assertEqual(
            os.path.basename(new_path), 'project-context-migrated-3.html',
        )
        with open(new_path, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), 'third')

    def test_missing_source_raises_file_not_found(self):
        missing = os.path.join(self.tmp.name, 'does-not-exist.html')
        with self.assertRaises(FileNotFoundError):
            mapping.retire_context_html(missing)

    def test_returns_string_path(self):
        self._write(self.src)
        new_path = mapping.retire_context_html(self.src)
        self.assertIsInstance(new_path, str)


class Python310CompatTests(unittest.TestCase):
    """The cowork sandbox runs Python 3.10. The mapping module must parse
    and import there. PEP 701 (Python 3.12) relaxed f-string grammar to
    allow backslash-escaped quotes inside expression braces -- using that
    syntax silently breaks cowork. Guard against reintroduction in BOTH the
    module under test and this test file."""

    def _scan(self, path):
        src = pathlib.Path(path).read_text(encoding='utf-8')
        # Strip raw-string blocks so legitimate escaped content there does
        # not trip the scan.
        src = re.sub(r'r"""[\s\S]*?"""', '', src)
        src = re.sub(r"r'''[\s\S]*?'''", '', src)
        bad_single = re.findall(r"""f'[^'\n]*\\"[^'\n]*'""", src)
        bad_double = re.findall(r'''f"[^"\n]*\\'[^"\n]*"''', src)
        return bad_single + bad_double

    def test_module_has_no_backslash_quotes_inside_fstrings(self):
        bad = self._scan(_REFS / 'project_context_db_mapping.py')
        self.assertEqual(
            bad, [],
            'Found f-string with backslash-escaped quote inside braces in '
            'project_context_db_mapping.py. Requires Python 3.12+ (PEP 701); '
            'cowork ships 3.10. Hoist the expression out of the f-string.',
        )

    def test_test_file_has_no_backslash_quotes_inside_fstrings(self):
        bad = self._scan(__file__)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
