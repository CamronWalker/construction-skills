import json
import subprocess
import sys
import unittest
from pathlib import Path


HOOK = Path(__file__).resolve().parent.parent / 'check_lib_fence.py'


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


class TestLibFenceBlocks(unittest.TestCase):
    def test_read_lib_py_blocked_posix_path(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {
                'file_path': '/c/Users/a/construction-skills/scheduling/skills/schedule-toolbox/lib/score_schedule.py',
            },
        })
        self.assertEqual(proc.returncode, 2)
        self.assertIn('schedule-toolbox/lib', proc.stderr)
        self.assertIn('MCP', proc.stderr)

    def test_read_lib_py_blocked_windows_path(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {
                'file_path': r'C:\Users\a\construction-skills\scheduling\skills\schedule-toolbox\lib\cpm_engine.py',
            },
        })
        self.assertEqual(proc.returncode, 2)
        self.assertIn('schedule-toolbox', proc.stderr)

    def test_edit_lib_py_blocked(self):
        proc = run_hook({
            'tool_name': 'Edit',
            'tool_input': {
                'file_path': '/repo/scheduling/skills/schedule-toolbox/lib/quality_checks.py',
            },
        })
        self.assertEqual(proc.returncode, 2)

    def test_write_lib_py_blocked(self):
        proc = run_hook({
            'tool_name': 'Write',
            'tool_input': {
                'file_path': '/repo/scheduling/skills/schedule-toolbox/lib/new_file.py',
            },
        })
        self.assertEqual(proc.returncode, 2)

    def test_multiedit_lib_py_blocked(self):
        proc = run_hook({
            'tool_name': 'MultiEdit',
            'tool_input': {
                'file_path': '/repo/scheduling/skills/schedule-toolbox/lib/path_analysis.py',
            },
        })
        self.assertEqual(proc.returncode, 2)

    def test_notebookedit_lib_py_blocked(self):
        proc = run_hook({
            'tool_name': 'NotebookEdit',
            'tool_input': {
                'notebook_path': '/repo/scheduling/skills/schedule-toolbox/lib/foo.py',
            },
        })
        self.assertEqual(proc.returncode, 2)

    def test_grep_with_lib_path_blocked(self):
        proc = run_hook({
            'tool_name': 'Grep',
            'tool_input': {
                'pattern': 'def ',
                'path': '/repo/scheduling/skills/schedule-toolbox/lib',
            },
        })
        self.assertEqual(proc.returncode, 2)

    def test_glob_with_lib_pattern_blocked(self):
        proc = run_hook({
            'tool_name': 'Glob',
            'tool_input': {
                'pattern': '**/schedule-toolbox/lib/**/*.py',
            },
        })
        self.assertEqual(proc.returncode, 2)

    def test_glob_with_lib_path_blocked(self):
        proc = run_hook({
            'tool_name': 'Glob',
            'tool_input': {
                'pattern': '*.py',
                'path': '/repo/scheduling/skills/schedule-toolbox/lib',
            },
        })
        self.assertEqual(proc.returncode, 2)


class TestLibFenceAllows(unittest.TestCase):
    def test_no_path_passes_silent(self):
        proc = run_hook({'tool_name': 'Read', 'tool_input': {}})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_unrelated_path_passes_silent(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/some/where/notes.md'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_references_md_passes(self):
        """References dir still has .md files — those are allowed."""
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {
                'file_path': '/repo/scheduling/skills/schedule-toolbox/references/quality-checks.md',
            },
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_lib_non_py_passes(self):
        """Non-.py file in lib/ (unusual but possible) — only .py files are fenced."""
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {
                'file_path': '/repo/scheduling/skills/schedule-toolbox/lib/README.md',
            },
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_other_lib_dir_passes(self):
        """A lib/ directory in some other skill must NOT be fenced."""
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {
                'file_path': '/repo/scheduling/skills/schedule-update/lib/email_draft_io.py',
            },
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_unrelated_grep_passes(self):
        proc = run_hook({
            'tool_name': 'Grep',
            'tool_input': {
                'pattern': 'def ',
                'path': '/repo/scheduling/mcp-server',
            },
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_unrelated_glob_passes(self):
        proc = run_hook({
            'tool_name': 'Glob',
            'tool_input': {'pattern': '**/*.py', 'path': '/repo/scheduling/mcp-server'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_bash_passes(self):
        """Bash is not matched by this hook."""
        proc = run_hook({
            'tool_name': 'Bash',
            'tool_input': {'command': 'cat /repo/scheduling/skills/schedule-toolbox/lib/x.py'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_malformed_payload_silent(self):
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input='not json',
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == '__main__':
    unittest.main()
