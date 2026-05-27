# scheduling/mcp-server/tests/test_error_help.py
"""Tests for :mod:`scheduling.mcp-server.error_help`.

The error_help decorator catches exceptions from a wrapped MCP tool
callable and re-raises with an augmented multi-section message. These
tests cover:

* Original exception TYPE is preserved (so downstream ``isinstance``
  checks still work).
* The augmented message contains the original error text, the lib_script
  path, and the ``westland-bug-report`` mention.
* Each known exception type produces a tailored "What you can try"
  bullet block.
* ``MilestoneAmbiguousError`` / ``MilestoneNotFoundError`` surface their
  ``candidates`` list inside the message, and the attribute survives
  the re-raise.
* ``functools.wraps`` metadata (``__name__``, ``__doc__``,
  ``__wrapped__``) is preserved on the wrapped function so FastMCP
  introspection still works.
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SERVER_DIR))

# Inject the lib path so we can import MilestoneAmbiguousError /
# MilestoneNotFoundError -- mirrors what tools/structure.py does.
_LIB = SERVER_DIR.parent / "skills" / "schedule-toolbox" / "lib"
sys.path.insert(0, str(_LIB))

from error_help import (  # noqa: E402
    _format_error,
    _suggestions_for,
    wrap_tool_errors,
)
from errors import XerLockedError  # noqa: E402
from milestones import (  # noqa: E402
    MilestoneAmbiguousError,
    MilestoneNotFoundError,
)

LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/test.py"


class TestWrapToolErrorsBasic(unittest.TestCase):
    """The decorator preserves the original exception TYPE and augments
    the message."""

    def test_no_exception_passes_through(self):
        """When the wrapped callable doesn't raise, the decorator is a
        no-op -- the return value passes through unchanged."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def succeeds(a, b):
            return {"sum": a + b}

        result = succeeds(2, 3)
        self.assertEqual(result, {"sum": 5})

    def test_exception_type_preserved(self):
        """``except ValueError`` still catches the re-raised exception."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise ValueError("original message")

        with self.assertRaises(ValueError):
            fails()

    def test_original_message_included(self):
        """The original exception's ``str()`` is present in the new
        message as the leading summary line."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise ValueError("original message")

        with self.assertRaises(ValueError) as ctx:
            fails()
        self.assertIn("original message", str(ctx.exception))

    def test_lib_script_path_included(self):
        """The lib_script path appears in the augmented message so Claude
        can find the source to debug."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError) as ctx:
            fails()
        self.assertIn(LIB_SCRIPT, str(ctx.exception))

    def test_bug_report_skill_mention_on_system_error(self):
        """SYSTEM error types (RuntimeError, KeyError, generic Exception)
        get the ``westland-bug-report`` tail so Claude knows where to
        escalate. User-error types skip the tail -- covered in
        :class:`TestBugReportTailConditional`."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError) as ctx:
            fails()
        self.assertIn("westland-bug-report", str(ctx.exception))

    def test_what_you_can_try_section_present(self):
        """The augmented message includes the ``What you can try:``
        header so the suggestions render visibly."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError) as ctx:
            fails()
        self.assertIn("What you can try:", str(ctx.exception))

    def test_original_chained_via_from(self):
        """The original exception is chained via ``raise new from exc``
        so ``__cause__`` carries the original for debugging via
        ``traceback``."""

        original = ValueError("inner")

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise original

        with self.assertRaises(ValueError) as ctx:
            fails()
        self.assertIs(ctx.exception.__cause__, original)

    def test_args_and_kwargs_pass_through(self):
        """The decorator accepts arbitrary positional and keyword args
        and forwards them unchanged."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def echo(*args, **kwargs):
            return {"args": args, "kwargs": kwargs}

        result = echo(1, 2, "three", x=4, y="five")
        self.assertEqual(result["args"], (1, 2, "three"))
        self.assertEqual(result["kwargs"], {"x": 4, "y": "five"})


class TestFunctoolsMetadataPreserved(unittest.TestCase):
    """FastMCP may inspect ``__name__`` / ``__doc__`` / ``__wrapped__``
    on the decorated function to derive the MCP tool name. ``functools.
    wraps`` preserves them."""

    def test_name_preserved(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def my_func():
            """Doc string."""
            return None

        self.assertEqual(my_func.__name__, "my_func")

    def test_doc_preserved(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def my_func():
            """Doc string."""
            return None

        self.assertEqual(my_func.__doc__, "Doc string.")

    def test_wrapped_attribute_preserved(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def my_func():
            return None

        # __wrapped__ points back at the original callable
        # (provided by functools.wraps).
        self.assertTrue(hasattr(my_func, "__wrapped__"))


class TestMilestoneAmbiguousError(unittest.TestCase):
    """``MilestoneAmbiguousError`` carries a ``candidates`` list. The
    decorator surfaces a few candidates in the message AND preserves
    the attribute on the re-raised instance."""

    def test_milestone_ambiguous_error_includes_candidates_in_message(self):
        candidates = [
            {"task_id": "A", "task_name": "First"},
            {"task_id": "B", "task_name": "Second"},
        ]
        err = MilestoneAmbiguousError("2 candidates", candidates=candidates)

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise err

        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            fails()

        msg = str(ctx.exception)
        self.assertIn("get_milestones", msg)
        self.assertIn(LIB_SCRIPT, msg)
        # MilestoneAmbiguousError is a user-error type -- the tool worked
        # as designed and the fix is to pass milestone_id. No bug-report
        # escalation prompt for user errors.
        self.assertNotIn("westland-bug-report", msg)
        self.assertIn("First", msg)
        self.assertIn("Second", msg)

    def test_candidates_attribute_preserved_on_reraise(self):
        candidates = [
            {"task_id": "A", "task_name": "First"},
            {"task_id": "B", "task_name": "Second"},
        ]

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise MilestoneAmbiguousError("2 candidates", candidates=candidates)

        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            fails()
        # The candidates list survives the re-raise -- callers reading
        # ``exc.candidates`` still get the structured list.
        self.assertEqual(ctx.exception.candidates, candidates)

    def test_tool_name_appears_in_suggestion(self):
        """The first suggestion bullet refers to the wrapped tool by
        name so Claude knows which tool to re-call."""

        @wrap_tool_errors("get_milestone_path_coverage", LIB_SCRIPT)
        def fails():
            raise MilestoneAmbiguousError("2 candidates", candidates=[])

        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            fails()
        self.assertIn("get_milestone_path_coverage", str(ctx.exception))

    def test_more_than_five_candidates_truncated_with_count(self):
        """When candidates > 5, the message shows the first 5 plus a
        ``(and N more)`` suffix instead of dumping the whole list."""
        candidates = [
            {"task_id": f"T{i}", "task_name": f"Task {i}"} for i in range(8)
        ]

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise MilestoneAmbiguousError("8 candidates", candidates=candidates)

        with self.assertRaises(MilestoneAmbiguousError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertIn("(and 3 more)", msg)


class TestMilestoneNotFoundError(unittest.TestCase):
    """``MilestoneNotFoundError`` parallels MilestoneAmbiguousError --
    same ``candidates`` payload, different framing."""

    def test_includes_get_milestones_call(self):
        candidates = [{"task_id": "X", "task_name": "Substantial Completion"}]
        err = MilestoneNotFoundError("bad id", candidates=candidates)

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise err

        with self.assertRaises(MilestoneNotFoundError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertIn("doesn't exist", msg)
        self.assertIn("get_milestones", msg)
        self.assertIn("Substantial Completion", msg)


class TestFileNotFoundError(unittest.TestCase):
    """The ``FileNotFoundError`` bucket of suggestions points at Glob
    for finding the file and verifies the export is finished."""

    def test_suggests_glob_and_export_check(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise FileNotFoundError("no such file")

        with self.assertRaises(FileNotFoundError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertIn("Glob", msg)
        self.assertIn(".xer", msg)


class TestXerLockedError(unittest.TestCase):
    """``XerLockedError`` (custom Westland exception) tells Claude to
    wait and retry rather than escalate."""

    def test_suggests_retry(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise XerLockedError("size shifted between reads")

        with self.assertRaises(XerLockedError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertIn("retry", msg.lower())
        self.assertIn("P6", msg)


class TestValueErrorBranches(unittest.TestCase):
    """``ValueError`` is the catch-all for input-shape errors. The
    suggestions branch on message content."""

    def test_missing_required_key_routes_to_docstring(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise ValueError("missing required key 'task_id'")

        with self.assertRaises(ValueError) as ctx:
            fails()
        self.assertIn("docstring", str(ctx.exception))

    def test_both_anchors_routes_to_one_or_other(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise ValueError(
                "Pass exactly one of `anchors` or `anchors_path`, not both."
            )

        with self.assertRaises(ValueError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertIn("anchors_path", msg)

    def test_overwrite_routes_to_output_path(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise ValueError("output_path is the same as xer_path; refusing to overwrite the source XER.")

        with self.assertRaises(ValueError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertIn("output_path", msg)

    def test_generic_value_error_falls_back(self):
        """A ValueError whose message doesn't match a known branch still
        gets a reasonable generic suggestion."""

        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise ValueError("totally unknown problem")

        with self.assertRaises(ValueError) as ctx:
            fails()
        # Falls back to the docstring nudge.
        self.assertIn("docstring", str(ctx.exception))


class TestKeyError(unittest.TestCase):
    """``KeyError`` from the parsed XER suggests inspecting the file
    and (if the field really is present) filing a parser bug."""

    def test_keyerror_suggests_inspect_xer(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise KeyError("task_id")

        with self.assertRaises(KeyError) as ctx:
            fails()
        # KeyError(msg) renders as repr(msg) when str()'d, so the message
        # body lives in our wrapper output, not in str(KeyError).
        msg = str(ctx.exception)
        self.assertIn("XER", msg)
        self.assertIn("parser", msg)


class TestFileExistsError(unittest.TestCase):
    """``FileExistsError`` (run_cpm refuses to overwrite) suggests
    deleting or choosing a new path."""

    def test_suggests_delete_or_rename(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise FileExistsError("output exists")

        with self.assertRaises(FileExistsError) as ctx:
            fails()
        msg = str(ctx.exception)
        self.assertTrue("delete" in msg.lower() or "rename" in msg.lower())


class TestGenericException(unittest.TestCase):
    """Any exception type without a specific branch still produces a
    reasonable message -- the formatter falls through to the generic
    branch."""

    def test_generic_exception(self):
        @wrap_tool_errors("test_tool", LIB_SCRIPT)
        def fails():
            raise RuntimeError("something weird happened")

        with self.assertRaises(RuntimeError) as ctx:
            fails()
        msg = str(ctx.exception)
        # Original message present.
        self.assertIn("something weird happened", msg)
        # Generic suggestions present.
        self.assertIn("lib script", msg.lower())
        # Standard tail present.
        self.assertIn("westland-bug-report", msg)


class TestFormatErrorDirect(unittest.TestCase):
    """Direct unit tests for ``_format_error`` -- exercises the layout
    without going through the decorator."""

    def test_layout_sections_present_for_system_error(self):
        """The formatted message for a SYSTEM error type has all four
        sections: summary, suggestions, lib_script pointer, bug-report
        tail."""
        msg = _format_error(
            RuntimeError("boom"), "test_tool", LIB_SCRIPT
        )
        self.assertIn("boom", msg)
        self.assertIn("What you can try:", msg)
        self.assertIn(LIB_SCRIPT, msg)
        self.assertIn("westland-bug-report", msg)

    def test_layout_sections_present_for_user_error_omit_bug_report(self):
        """The formatted message for a USER error type has summary,
        suggestions, and lib_script pointer -- but NO bug-report tail."""
        msg = _format_error(
            ValueError("bad input"), "test_tool", LIB_SCRIPT
        )
        self.assertIn("bad input", msg)
        self.assertIn("What you can try:", msg)
        self.assertIn(LIB_SCRIPT, msg)
        self.assertNotIn("westland-bug-report", msg)

    def test_summary_falls_back_to_type_name_on_empty(self):
        """When the original exception has an empty message, the summary
        line falls back to the exception class name so the message is
        still informative."""
        msg = _format_error(ValueError(""), "test_tool", LIB_SCRIPT)
        self.assertIn("ValueError", msg)


class TestBugReportTailConditional(unittest.TestCase):
    """The bug-report tail is conditional: USER-error exception types skip
    it (the tool worked as designed; fix is on the caller's side), SYSTEM-
    error exception types include it (something unexpected went wrong --
    Camron should know).
    """

    # USER ERROR types -- no bug-report tail.

    def test_value_error_no_bug_report(self):
        msg = _format_error(ValueError("bad input"), "t", LIB_SCRIPT)
        self.assertNotIn("westland-bug-report", msg)

    def test_file_not_found_no_bug_report(self):
        msg = _format_error(FileNotFoundError("no such file"), "t", LIB_SCRIPT)
        self.assertNotIn("westland-bug-report", msg)

    def test_file_exists_no_bug_report(self):
        msg = _format_error(FileExistsError("exists"), "t", LIB_SCRIPT)
        self.assertNotIn("westland-bug-report", msg)

    def test_milestone_ambiguous_no_bug_report(self):
        err = MilestoneAmbiguousError("ambig", candidates=[])
        msg = _format_error(err, "t", LIB_SCRIPT)
        self.assertNotIn("westland-bug-report", msg)

    def test_milestone_not_found_no_bug_report(self):
        err = MilestoneNotFoundError("missing", candidates=[])
        msg = _format_error(err, "t", LIB_SCRIPT)
        self.assertNotIn("westland-bug-report", msg)

    def test_xer_locked_no_bug_report(self):
        msg = _format_error(XerLockedError("size shifted"), "t", LIB_SCRIPT)
        self.assertNotIn("westland-bug-report", msg)

    # SYSTEM ERROR types -- include bug-report tail.

    def test_key_error_includes_bug_report(self):
        msg = _format_error(KeyError("task_id"), "t", LIB_SCRIPT)
        self.assertIn("westland-bug-report", msg)

    def test_runtime_error_includes_bug_report(self):
        msg = _format_error(RuntimeError("boom"), "t", LIB_SCRIPT)
        self.assertIn("westland-bug-report", msg)

    def test_generic_exception_includes_bug_report(self):
        msg = _format_error(Exception("unknown"), "t", LIB_SCRIPT)
        self.assertIn("westland-bug-report", msg)


class TestSuggestionsForDirect(unittest.TestCase):
    """Direct unit tests for ``_suggestions_for`` -- verifies each
    exception type returns the expected bullet text."""

    def test_filenotfound(self):
        bullets = _suggestions_for(FileNotFoundError("x"), "test_tool")
        self.assertTrue(any("Glob" in b for b in bullets))

    def test_xer_locked(self):
        bullets = _suggestions_for(XerLockedError("x"), "test_tool")
        self.assertTrue(any("retry" in b.lower() for b in bullets))

    def test_milestone_ambiguous_with_candidates(self):
        err = MilestoneAmbiguousError(
            "x",
            candidates=[{"task_id": "A", "task_name": "First"}],
        )
        bullets = _suggestions_for(err, "test_tool")
        self.assertEqual(len(bullets), 2)
        self.assertTrue(any("First" in b for b in bullets))

    def test_milestone_ambiguous_without_candidates(self):
        """When ``candidates`` is empty, the candidates bullet is
        omitted -- only the call-get_milestones bullet remains."""
        err = MilestoneAmbiguousError("x", candidates=[])
        bullets = _suggestions_for(err, "test_tool")
        self.assertEqual(len(bullets), 1)

    def test_generic_exception(self):
        bullets = _suggestions_for(Exception("x"), "test_tool")
        self.assertGreaterEqual(len(bullets), 1)


if __name__ == "__main__":
    unittest.main()
