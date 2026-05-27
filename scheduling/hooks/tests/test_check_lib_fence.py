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


def parse_decision(proc):
    """Parse stdout as the PreToolUse hook decision JSON and return the reason text."""
    payload = json.loads(proc.stdout)
    hso = payload['hookSpecificOutput']
    assert hso['hookEventName'] == 'PreToolUse'
    assert hso['permissionDecision'] == 'allow'
    return hso['permissionDecisionReason']


class TestLibFenceRecommends(unittest.TestCase):
    """The hook fires on these paths, exits 0, and emits an allow-with-reason
    JSON decision pointing Claude at the canonical MCP workflow."""

    def test_read_lib_py_recommend_posix_path(self):
        path = '/c/Users/a/construction-skills/scheduling/skills/schedule-toolbox/lib/score_schedule.py'
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        self.assertIn('MCP', reason)
        # score_schedule.py is in the mapping table — its tools should be listed.
        self.assertIn('score_schedule', reason)
        self.assertIn('get_quality_check', reason)

    def test_read_lib_py_recommend_windows_path(self):
        path = r'C:\Users\a\construction-skills\scheduling\skills\schedule-toolbox\lib\cpm_engine.py'
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        self.assertIn('Westland Scheduler', reason)
        # cpm_engine.py is in the mapping table.
        self.assertIn('run_cpm', reason)
        self.assertIn('get_critical_path', reason)

    def test_edit_lib_py_recommend(self):
        path = '/repo/scheduling/skills/schedule-toolbox/lib/quality_checks.py'
        proc = run_hook({
            'tool_name': 'Edit',
            'tool_input': {'file_path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        self.assertIn('get_quality_check', reason)

    def test_write_lib_py_recommend(self):
        """An unknown file (new_file.py) in lib/ still fires; uses the generic
        fallback message rather than a tool list."""
        path = '/repo/scheduling/skills/schedule-toolbox/lib/new_file.py'
        proc = run_hook({
            'tool_name': 'Write',
            'tool_input': {'file_path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        self.assertIn('MCP tool catalog', reason)

    def test_multiedit_lib_py_recommend(self):
        path = '/repo/scheduling/skills/schedule-toolbox/lib/path_analysis.py'
        proc = run_hook({
            'tool_name': 'MultiEdit',
            'tool_input': {'file_path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        # path_analysis.py is in the mapping table.
        self.assertIn('get_milestone_path_coverage', reason)

    def test_notebookedit_lib_py_recommend(self):
        path = '/repo/scheduling/skills/schedule-toolbox/lib/foo.py'
        proc = run_hook({
            'tool_name': 'NotebookEdit',
            'tool_input': {'notebook_path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        self.assertIn('MCP', reason)

    def test_grep_with_lib_path_recommend(self):
        path = '/repo/scheduling/skills/schedule-toolbox/lib'
        proc = run_hook({
            'tool_name': 'Grep',
            'tool_input': {'pattern': 'def ', 'path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        # Discovery-tool variant of the message mentions the matched label.
        self.assertIn(path, reason)
        self.assertIn('MCP', reason)
        self.assertIn('ToolSearch', reason)

    def test_glob_with_lib_pattern_recommend(self):
        pattern = '**/schedule-toolbox/lib/**/*.py'
        proc = run_hook({
            'tool_name': 'Glob',
            'tool_input': {'pattern': pattern},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(pattern, reason)
        self.assertIn('MCP', reason)

    def test_glob_with_lib_path_recommend(self):
        path = '/repo/scheduling/skills/schedule-toolbox/lib'
        proc = run_hook({
            'tool_name': 'Glob',
            'tool_input': {'pattern': '*.py', 'path': path},
        })
        self.assertEqual(proc.returncode, 0)
        reason = parse_decision(proc)
        self.assertIn(path, reason)
        self.assertIn('MCP', reason)


class TestLibFenceAllows(unittest.TestCase):
    """When the hook doesn't match, it exits 0 silently — no JSON output."""

    def test_no_path_passes_silent(self):
        proc = run_hook({'tool_name': 'Read', 'tool_input': {}})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, '')

    def test_unrelated_path_passes_silent(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/some/where/notes.md'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, '')

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
        self.assertEqual(proc.stdout, '')

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
        self.assertEqual(proc.stdout, '')

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
        self.assertEqual(proc.stdout, '')

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
        self.assertEqual(proc.stdout, '')

    def test_unrelated_glob_passes(self):
        proc = run_hook({
            'tool_name': 'Glob',
            'tool_input': {'pattern': '**/*.py', 'path': '/repo/scheduling/mcp-server'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, '')

    def test_bash_passes(self):
        """Bash is not matched by this hook."""
        proc = run_hook({
            'tool_name': 'Bash',
            'tool_input': {'command': 'cat /repo/scheduling/skills/schedule-toolbox/lib/x.py'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')
        self.assertEqual(proc.stdout, '')

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
