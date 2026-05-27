"""Friendly error-message wrapping for MCP tool wrappers.

The FastMCP framework catches any exception raised by an ``@mcp.tool()``
function and surfaces its ``str(exc)`` representation to Claude. Without
extra help, Claude sees a one-line summary -- e.g.
``MilestoneAmbiguousError: 2 terminal milestones -- pass milestone_id
explicitly`` -- but no guidance on what to do next, no pointer to the lib
script that produced the error, and no nudge to file a bug report if the
behavior looks wrong.

This module exposes :func:`wrap_tool_errors`, a decorator that wraps an
``@mcp.tool()`` callable, catches every exception, re-raises with the
ORIGINAL exception TYPE (so ``isinstance(e, MilestoneAmbiguousError)``
checks downstream still work), but rewrites the message into a structured
multi-section payload:

* A one-line "what went wrong" summary (taken straight from the original
  exception's args).
* A "What you can try" bullet list, looked up by exception type with a
  small per-error-type table -- :data:`_SUGGESTIONS_BY_TYPE`.
* A pointer to the underlying lib script (per the F1-F8 MCP module
  ``lib_script`` mapping) so Claude can read the source when the hook
  allows it for debugging.
* For SYSTEM errors (anything outside :data:`_USER_ERROR_EXC_NAMES`):
  a standard tail mentioning the ``westland-bug-report`` skill so Camron
  gets notified when an error looks like an MCP bug rather than user
  error. User-error exception types (``ValueError``,
  ``MilestoneAmbiguousError``, etc.) skip this tail because the tool
  worked as designed -- the fix is on the caller's side.

Use:

    @mcp.tool()
    @wrap_tool_errors(
        tool_name="score_schedule",
        lib_script="scheduling/skills/schedule-toolbox/lib/score_schedule.py",
    )
    def score_schedule(xer_path: str, milestone_id: Optional[str] = None) -> dict:
        ...

The decorator preserves ``__name__`` / ``__doc__`` / ``__wrapped__`` via
``functools.wraps`` so FastMCP can introspect the tool the same way it
would without the wrapper.
"""
from __future__ import annotations

import functools
from typing import Callable, Optional


# Tail mentioning the bug-report skill. Kept as a module-level constant so
# the formatter never silently drifts between call sites.
_BUG_REPORT_TAIL = (
    "If this looks like an MCP bug -- wrong output, unexpected exception, "
    "the tool failing on a schedule it should handle -- file a bug report "
    "via the westland-bug-report skill so Camron is notified."
)

_LIB_SCRIPT_PREAMBLE = (
    "If you need to investigate the implementation, the source file is at:"
)

_LIB_SCRIPT_NOTE = (
    "(The lib-fence hook will recommend MCP tools but allow the read for "
    "debugging.)"
)

# Exception class names that represent USER ERROR -- the caller passed bad
# input, missed a required field, asked the tool to overwrite a source XER,
# or failed to disambiguate a multi-terminal schedule. For these, the
# friendly message gives concrete recovery steps but DOES NOT suggest
# filing a bug report -- the tool worked exactly as designed and the fix
# is on the caller's side. Anything not in this set falls through to the
# bug-report tail (unexpected system errors / parser drift / etc.).
_USER_ERROR_EXC_NAMES = frozenset({
    "ValueError",
    "FileNotFoundError",
    "FileExistsError",
    "MilestoneAmbiguousError",
    "MilestoneNotFoundError",
    "XerLockedError",
})


def _suggestions_for(exc: Exception, tool_name: str) -> list:
    """Look up the per-error-type suggestion bullets.

    Returns a list of strings, each rendered as one ``  - <text>`` bullet
    in the formatted message. Falls back to a generic two-bullet
    suggestion for unrecognized exception types.

    Special cases:

    * ``MilestoneAmbiguousError`` and ``MilestoneNotFoundError`` carry a
      ``candidates`` list on the exception instance. The first suggestion
      surfaces a few of those candidates verbatim so Claude can pick one
      without a second tool call.
    * ``ValueError`` branches on message content -- "missing required
      key" gets a docstring nudge, everything else gets a generic input-
      shape hint.
    """
    name = type(exc).__name__

    if name == "FileNotFoundError":
        return [
            "Verify the xer_path exists. Use Glob with `*.xer` under your "
            "project's Schedules folder to find candidate files.",
            "Check that the path uses forward slashes or properly-escaped "
            "backslashes on Windows.",
            "Confirm the .xer file is fully written (not still being "
            "exported from P6).",
        ]

    if name == "XerLockedError":
        return [
            "The XER appears mid-write. Wait a few seconds and retry -- "
            "P6 may still be flushing the file.",
            "If the issue persists, ask the user to confirm the export "
            "from P6 has finished before retrying.",
        ]

    if name == "MilestoneAmbiguousError":
        candidates = getattr(exc, "candidates", []) or []
        first_bullet = (
            "Call `get_milestones(xer_path=...)` first, pick the right "
            "terminal milestone from the candidates, and re-call this "
            f"tool ({tool_name}) with `milestone_id=<chosen>`."
        )
        bullets = [first_bullet]
        if candidates:
            # Surface up to 5 candidates in the message so Claude can
            # often skip the get_milestones call entirely on small
            # schedules. Each entry is rendered as
            # ``<task_id>: <task_name>`` so both useful fields are visible.
            shown = candidates[:5]
            pretty = ", ".join(
                f"{c.get('task_id', '?')}: {c.get('task_name', '?')}"
                for c in shown
            )
            more = (
                ""
                if len(candidates) <= 5
                else f" (and {len(candidates) - 5} more)"
            )
            bullets.append(
                f"Candidates surfaced on this exception: {pretty}{more}."
            )
        return bullets

    if name == "MilestoneNotFoundError":
        candidates = getattr(exc, "candidates", []) or []
        first_bullet = (
            "The milestone_id you passed doesn't exist in the schedule. "
            "Call `get_milestones(xer_path=...)` to see valid candidates, "
            "then re-call this tool with one of those task_ids."
        )
        bullets = [first_bullet]
        if candidates:
            shown = candidates[:5]
            pretty = ", ".join(
                f"{c.get('task_id', '?')}: {c.get('task_name', '?')}"
                for c in shown
            )
            more = (
                ""
                if len(candidates) <= 5
                else f" (and {len(candidates) - 5} more)"
            )
            bullets.append(
                f"Candidates surfaced on this exception: {pretty}{more}."
            )
        return bullets

    if name == "ValueError":
        msg = str(exc).lower()
        if "missing required key" in msg or "required key" in msg:
            return [
                "Check the input dict has all required fields per the "
                "tool's docstring (Args section).",
                "Re-read the tool's docstring -- the exact key names and "
                "shapes are listed there.",
            ]
        if "anchors" in msg and "both" in msg:
            return [
                "Pass exactly one of `anchors` (inline list) or "
                "`anchors_path` (path to a JSON file), not both.",
            ]
        if "anchors" in msg and "either" in msg:
            return [
                "Pass one of `anchors` (inline list) or `anchors_path` "
                "(path to a JSON file with `{\"anchors\": [...]}`).",
            ]
        if "overwrite" in msg:
            return [
                "Use a different output_path -- the tool refuses to "
                "overwrite the source XER or an existing target file.",
                "If you genuinely want to replace the existing file, "
                "delete or rename it first, then re-call this tool.",
            ]
        return [
            "Check the tool's docstring for the expected input shape "
            "(Args section).",
            "If you're passing a dict, verify every required key is "
            "present and has the documented type.",
        ]

    if name == "KeyError":
        return [
            "An expected field is missing from the parsed XER. Inspect "
            "the XER manually with a text editor and verify the table "
            "named in the error contains the missing key.",
            "If the field looks present in the file but the parser still "
            "errors, file a bug report -- the parser may have drifted "
            "from the P6 export format.",
        ]

    if name == "FileExistsError":
        return [
            "The output path already exists. Delete or rename the "
            "existing file first, then re-call this tool.",
            "Or pass a different output_path so the existing file stays "
            "in place.",
        ]

    # Generic fall-through. We can't say much beyond pointing at the lib
    # script and the bug-report skill, so do exactly that.
    return [
        "Something unexpected went wrong in the analysis. Read the lib "
        "script at the path below if you need to debug.",
        "If the input looked correct, the failure is more likely an MCP "
        "bug than a user error -- consider filing one.",
    ]


def _format_error(exc: Exception, tool_name: str, lib_script: str) -> str:
    """Build the multi-section friendly message.

    Layout (matches the task spec):

        <one-line summary>

        What you can try:
          - <suggestion 1>
          - <suggestion 2>
          ...

        If you need to investigate the implementation, the source file is at:
          <lib_script path>
        (The lib-fence hook will recommend MCP tools but allow the read for
        debugging.)

        If this looks like an MCP bug -- wrong output, unexpected exception,
        the tool failing on a schedule it should handle -- file a bug report
        via the westland-bug-report skill so Camron is notified.

    The summary line is taken from ``str(exc)`` directly. If the original
    message is multi-line we keep it intact -- truncating would drop
    useful context (e.g. the MilestoneAmbiguousError lib message lists
    candidate task_ids in the message itself).

    The bug-report tail is conditional: USER ERROR exception types
    (:data:`_USER_ERROR_EXC_NAMES`) get the suggestions + lib-script
    pointer only -- no escalation prompt, because the tool worked as
    designed and the fix is on the caller's side. Everything else
    (unexpected system errors, parser drift, generic exceptions) gets
    the bug-report tail so Camron is notified.
    """
    summary = str(exc).strip() or type(exc).__name__
    suggestions = _suggestions_for(exc, tool_name)
    bullets = "\n".join(f"  - {s}" for s in suggestions)

    body = (
        f"{summary}\n"
        f"\n"
        f"What you can try:\n"
        f"{bullets}\n"
        f"\n"
        f"{_LIB_SCRIPT_PREAMBLE}\n"
        f"  {lib_script}\n"
        f"{_LIB_SCRIPT_NOTE}"
    )

    if type(exc).__name__ not in _USER_ERROR_EXC_NAMES:
        body = f"{body}\n\n{_BUG_REPORT_TAIL}"

    return body


def _reraise_with_message(exc: Exception, new_message: str) -> None:
    """Re-raise ``exc`` with ``new_message`` substituted for the original.

    Preserves the original exception TYPE so downstream ``isinstance``
    checks (e.g. ``except MilestoneAmbiguousError``) still work. Carries
    forward the ``candidates`` attribute on milestone errors so callers
    that want the structured candidate list can still read it.

    The two-arg constructor variant on ``MilestoneAmbiguousError`` /
    ``MilestoneNotFoundError`` requires ``candidates``; we hand-build a
    fresh instance for those specifically so the attribute survives the
    re-raise. For everything else, ``type(exc)(new_message)`` works
    because the standard exception constructors accept a single string.
    """
    name = type(exc).__name__
    new_exc: Optional[BaseException] = None

    if name in ("MilestoneAmbiguousError", "MilestoneNotFoundError"):
        candidates = getattr(exc, "candidates", []) or []
        try:
            new_exc = type(exc)(new_message, candidates=candidates)
        except TypeError:
            # Fallback if the constructor signature ever changes.
            new_exc = type(exc)(new_message)
            try:
                setattr(new_exc, "candidates", candidates)
            except Exception:
                pass
    else:
        try:
            new_exc = type(exc)(new_message)
        except TypeError:
            # Some exception subclasses have unusual constructors. Fall
            # back to a bare Exception with the same name so the message
            # still reaches Claude.
            new_exc = Exception(new_message)

    raise new_exc from exc


def wrap_tool_errors(tool_name: str, lib_script: str) -> Callable:
    """Decorator: wrap an MCP tool callable with friendly error formatting.

    Args:
        tool_name: Name of the MCP tool, used in the suggestion text
            (e.g. "score_schedule"). This is the name Claude sees when
            calling the tool.
        lib_script: Relative path from the worktree root to the lib
            script that implements the analysis (e.g.
            ``"scheduling/skills/schedule-toolbox/lib/score_schedule.py"``).
            Surfaced verbatim in the error message so Claude can read
            the source for debugging.

    Returns:
        A decorator that wraps the passed-in callable. The wrapped
        callable has the same signature and ``functools.wraps`` metadata
        as the original; on exception it re-raises with the augmented
        message but preserves the original exception type so downstream
        ``isinstance`` checks still work.
    """

    def decorator(impl_fn: Callable) -> Callable:
        @functools.wraps(impl_fn)
        def wrapped(*args, **kwargs):
            try:
                return impl_fn(*args, **kwargs)
            except Exception as exc:
                friendly = _format_error(exc, tool_name, lib_script)
                _reraise_with_message(exc, friendly)

        return wrapped

    return decorator
