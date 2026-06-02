"""
Parser-only tests for the legacy project-context.html parser.

The generate/parse HTML store was retired in the project-context-supabase
refactor: project identity now lives in the wnd_projects Supabase row, gathered
conversationally and persisted via the upsert_project MCP tool. The
generate_project_context_html.py script is gone.

parse_project_context_html.py is KEPT — lazy migration still parses an
existing project-context.html on a DB miss, maps it into wnd_projects /
wnd_project_log (see project_context_db_mapping.py), and retires the file.
These tests pin the parser on hand-crafted static HTML (no generator
dependency) so the fields migration relies on keep round-tripping out of a
real-world file: scalar bindings, SmartPM fields, recipients, and project log.

Run from repo root:
    python -m unittest scheduling.skills.schedule-project-init.tests.test_project_context_html

or directly:
    python scheduling/skills/schedule-project-init/tests/test_project_context_html.py
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

import parse_project_context_html as parse_mod  # noqa: E402


# A realistic, hand-crafted project-context.html exercising every field
# lazy migration reads. Deliberately authored as static markup (NOT produced
# by a generator) so the parser is tested against the shape colleagues' saved
# files actually have. Past + today log entries, named + bare recipients,
# all scalar bindings.
SAMPLE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>.x{color:red}</style>
<script>window.TODAY='2026-05-07';</script>
</head><body>
  <h1>Lubumbashi DR Congo Temple</h1>
  <input type="text" data-field="project_name" value="Lubumbashi DR Congo Temple">
  <input type="text" data-field="job_number" value="W1177">
  <input type="text" data-field="contractual_completion" value="2027-09-30">
  <input type="text" data-field="smartpm_url" value="https://live.smartpmtech.com/projects/abc/workspace">
  <input type="text" data-field="smartpm_trends_url" value="https://live.smartpmtech.com/projects/abc/trends?tab=Graphs">
  <input type="text" data-field="smartpm_changelog_url" value="https://live.smartpmtech.com/projects/abc/changelog">
  <input type="text" data-field="smartpm_project_name" value="Lubumbashi DR Congo Temple">
  <input type="text" data-field="signer_name" value="Carter Brown">
  <input type="text" data-field="signer_title" value="Project Scheduler">
  <input type="text" data-field="signer_mobile" value="+1 801.555.1234">
  <input type="text" data-field="procore_company_id" value="11093">
  <input type="text" data-field="procore_project_id" value="2646569">
  <input type="text" data-field="procore_documents_folder_id" value="4592384">

  <div class="recipient-group" data-field="to_recipients">
    <div class="recipient-row">
      <input type="text" data-field="recipient_name" value="Owner Rep">
      <input type="text" data-field="recipient_email" value="owner@example.com">
    </div>
    <div class="recipient-row">
      <input type="text" data-field="recipient_name" value="">
      <input type="text" data-field="recipient_email" value="arch@example.com">
    </div>
  </div>

  <div class="recipient-group" data-field="cc_recipients">
    <div class="recipient-row">
      <input type="text" data-field="recipient_name" value="PM">
      <input type="text" data-field="recipient_email" value="pm@westlandconstruction.com">
    </div>
  </div>

  <div class="string-list" data-field="graph_screenshots">
    <div class="string-list-row">
      <input type="text" data-field="item_value" value="06-end-date-variance.png">
    </div>
    <div class="string-list-row">
      <input type="text" data-field="item_value" value="08-velocity.png">
    </div>
  </div>

  <div class="project-log">
    <div class="log-entries">
      <div class="log-entry locked" data-date="2026-04-15">
        <div class="log-body" data-field="log_body" contenteditable="false">EOT #1 filed &mdash; 14 calendar days.</div>
      </div>
      <div class="log-entry" data-date="2026-05-07">
        <div class="log-body" data-field="log_body" contenteditable="true">Re-init context with new signer.</div>
      </div>
    </div>
  </div>
</body></html>
"""


class ParserScalarFieldTests(unittest.TestCase):
    """Scalar bindings the migration upsert payload depends on."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_HTML)
        self.parsed = parse_mod.parse_project_context_html(self.path)

    def test_identity_and_smartpm_scalars(self):
        self.assertEqual(self.parsed['project_name'],
                         'Lubumbashi DR Congo Temple')
        self.assertEqual(self.parsed['job_number'], 'W1177')
        self.assertEqual(self.parsed['contractual_completion'], '2027-09-30')
        self.assertEqual(
            self.parsed['smartpm_url'],
            'https://live.smartpmtech.com/projects/abc/workspace')
        self.assertEqual(
            self.parsed['smartpm_trends_url'],
            'https://live.smartpmtech.com/projects/abc/trends?tab=Graphs')
        self.assertEqual(
            self.parsed['smartpm_changelog_url'],
            'https://live.smartpmtech.com/projects/abc/changelog')
        self.assertEqual(self.parsed['smartpm_project_name'],
                         'Lubumbashi DR Congo Temple')

    def test_signer_scalars(self):
        # Signer fields are dropped before upsert, but the parser must still
        # surface them so the mapping module is the single place that drops.
        self.assertEqual(self.parsed['signer_name'], 'Carter Brown')
        self.assertEqual(self.parsed['signer_title'], 'Project Scheduler')
        self.assertEqual(self.parsed['signer_mobile'], '+1 801.555.1234')

    def test_procore_scalars(self):
        self.assertEqual(self.parsed['procore_company_id'], '11093')
        self.assertEqual(self.parsed['procore_project_id'], '2646569')
        self.assertEqual(self.parsed['procore_documents_folder_id'],
                         '4592384')


class ParserRecipientTests(unittest.TestCase):
    """Recipients are discarded by migration, but the parser must read them
    correctly (named + bare rows) so nothing else upstream breaks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_HTML)
        self.parsed = parse_mod.parse_project_context_html(self.path)

    def test_to_recipients(self):
        self.assertEqual(self.parsed['to_recipients'], [
            {'name': 'Owner Rep', 'email': 'owner@example.com'},
            {'name': '', 'email': 'arch@example.com'},
        ])

    def test_cc_recipients(self):
        self.assertEqual(self.parsed['cc_recipients'], [
            {'name': 'PM', 'email': 'pm@westlandconstruction.com'},
        ])

    def test_compat_string_forms(self):
        self.assertEqual(
            self.parsed['to_recipients_str'],
            'Owner Rep <owner@example.com>; arch@example.com')
        self.assertEqual(
            self.parsed['cc_recipients_str'],
            'PM <pm@westlandconstruction.com>')


class ParserProjectLogTests(unittest.TestCase):
    """Project log is what migration replays into wnd_project_log via
    append_project_log — the dates must survive."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_HTML)
        self.parsed = parse_mod.parse_project_context_html(self.path)

    def test_log_entries_parsed_with_dates(self):
        by_date = {e['date']: e['body'] for e in self.parsed['project_log']}
        self.assertIn('2026-04-15', by_date)
        self.assertIn('2026-05-07', by_date)
        # &mdash; entity decoded by the parser.
        self.assertEqual(by_date['2026-04-15'],
                         'EOT #1 filed — 14 calendar days.')
        self.assertEqual(by_date['2026-05-07'],
                         'Re-init context with new signer.')

    def test_graph_screenshots_parsed(self):
        self.assertEqual(self.parsed['graph_screenshots'],
                         ['06-end-date-variance.png', '08-velocity.png'])


class ProcoreDocumentsFolderTests(unittest.TestCase):
    """Field added 2026-05 for the Procore Documents upload workflow.
    Parser must read it from real-world saved HTML and tolerate its
    absence in older files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')

    def _parse_static(self, html):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        return parse_mod.parse_project_context_html(self.path)

    def test_parser_reads_field_from_static_html(self):
        parsed = self._parse_static(
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="procore_documents_folder_id" '
            'value="4592384">'
            '</body></html>'
        )
        self.assertEqual(parsed['procore_documents_folder_id'], '4592384')

    def test_field_defaults_empty_on_missing(self):
        # Older HTML written before the field existed: parser must not
        # KeyError and must default the binding to ''.
        parsed = self._parse_static(
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="project_name" value="Old Job">'
            '</body></html>'
        )
        self.assertEqual(parsed['procore_documents_folder_id'], '')

    def test_user_blanks_field_to_re_trigger_discovery(self):
        # The Procore phase blanks this field when the user wants to
        # switch folders. Round-trip an empty value via static HTML.
        parsed = self._parse_static(
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="procore_documents_folder_id" '
            'value="">'
            '</body></html>'
        )
        self.assertEqual(parsed['procore_documents_folder_id'], '')


class ParserSpecialCharTests(unittest.TestCase):
    """HTML entities in saved values must decode on read so the migrated
    upsert payload carries clean text, not encoded entities."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')

    def test_entities_in_scalar_values_decode(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="project_name" '
            'value="A &lt;weird&gt; project &amp; co.">'
            '<input type="text" data-field="signer_title" '
            'value="Director of &quot;Special&quot; Projects &amp; Ops">'
            '</body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['project_name'], 'A <weird> project & co.')
        self.assertEqual(parsed['signer_title'],
                         'Director of "Special" Projects & Ops')


class LoadProjectContextHelperTests(unittest.TestCase):
    """load_project_context(root): the convenience the lazy-migration path
    uses to find a legacy file in the Schedules root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_returns_none_when_missing(self):
        ctx, path = parse_mod.load_project_context(self.root)
        self.assertIsNone(ctx)
        self.assertIsNone(path)

    def test_returns_parsed_dict_when_present(self):
        html_path = os.path.join(self.root, 'project-context.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_HTML)
        ctx, path = parse_mod.load_project_context(self.root)
        self.assertIsNotNone(ctx)
        self.assertEqual(path, html_path)
        self.assertEqual(ctx['job_number'], 'W1177')


class Python310CompatTests(unittest.TestCase):
    """The cowork sandbox runs Python 3.10. The parser (kept for migration)
    must parse and import there. PEP 701 (Python 3.12) relaxed f-string
    grammar to allow backslash-escaped quotes inside expression braces —
    using that syntax silently breaks cowork. Guard against reintroduction
    in the kept parser module."""

    def test_parser_has_no_backslash_quotes_inside_fstrings(self):
        src = (_REFS / 'parse_project_context_html.py').read_text(
            encoding='utf-8')
        src = re.sub(r'r"""[\s\S]*?"""', '', src)
        src = re.sub(r"r'''[\s\S]*?'''", '', src)
        bad_single = re.findall(r"""f'[^'\n]*\\"[^'\n]*'""", src)
        bad_double = re.findall(r'''f"[^"\n]*\\'[^"\n]*"''', src)
        self.assertEqual(
            bad_single + bad_double, [],
            'Found f-string with backslash-escaped quote inside braces in '
            'parse_project_context_html.py. Requires Python 3.12+ (PEP 701); '
            'cowork ships 3.10. Hoist the expression out of the f-string.',
        )


if __name__ == '__main__':
    unittest.main()
