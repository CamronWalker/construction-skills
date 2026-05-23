import json
import subprocess
import sys
import unittest
from pathlib import Path


HOOK = Path(__file__).resolve().parent.parent / 'check_html_discipline.py'


def run_hook(payload):
    """Invoke the hook script as a subprocess with the given JSON payload on stdin."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=5,
    )
    return proc


class TestHookAdvisory(unittest.TestCase):
    def test_no_path_exits_zero_silent(self):
        proc = run_hook({'tool_name': 'Read', 'tool_input': {}})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_unrelated_path_exits_zero_silent(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/some/where/notes.md'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_read_project_context_warns(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': r'G:\some\Schedules\project-context.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertIn('parse_project_context_html', proc.stderr)
        self.assertNotIn('generate_', proc.stderr)

    def test_edit_project_context_uses_write_message(self):
        proc = run_hook({
            'tool_name': 'Edit',
            'tool_input': {'file_path': '/c/Users/a/project-context.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertIn('generate_project_context_html', proc.stderr)

    def test_email_preview_html_no_longer_matches(self):
        """The pre-cloud-editor *-email-preview.html artifact is gone; the
        hook should not fire on it (the weekly email lives in -email.json now)."""
        proc = run_hook({
            'tool_name': 'Write',
            'tool_input': {'file_path': r'G:\proj\Schedules\2026-05-19\2026-05-19-email-preview.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_changes_report_html_does_not_match(self):
        """Other HTML files in the pipeline (e.g. changes-report HTML) must not trigger this hook."""
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/x/2026-05-19 Schedule Update Email (Change Report).html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')


if __name__ == '__main__':
    unittest.main()
