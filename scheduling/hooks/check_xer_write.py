"""
Claude Code PreToolUse hook for the Westland scheduling plugin.

Enforces the .xer immutability rule:
  - No in-place edits of any .xer file (Edit / MultiEdit / NotebookEdit).
  - No overwriting an existing .xer (Write on a path that already exists).
  - No deleting any .xer file via Bash (rm / del / Remove-Item / unlink).

Writing a NEW .xer file is allowed — that's how modifications get saved
(convention: use a `-vN.xer` suffix next to the previous version).

Reads a PreToolUse JSON envelope from stdin. Exits 0 to allow, exits 2
with a stderr message to block (Claude Code surfaces the stderr message
to the assistant and cancels the tool call).

Self-test: `python check_xer_write.py --self-test`
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

RELEVANT_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# Bash commands to scan for .xer deletes. Match conservatively — these are
# run against the `command` field of Bash tool calls.
_BASH_DELETE_PATTERNS = [
    # rm / rm -f / rm -rf ... *.xer or specific.xer
    re.compile(r"\brm\b(?:\s+-[rRfFvV]+)*\s+[^|&;<>]*\.xer\b", re.IGNORECASE),
    # cmd del / erase
    re.compile(r"\b(?:del|erase)\b[^|&;<>]*\.xer\b", re.IGNORECASE),
    # PowerShell Remove-Item / ri / rmdir
    re.compile(r"\b(?:Remove-Item|ri)\b[^|&;<>]*\.xer\b", re.IGNORECASE),
    # unlink system call usage
    re.compile(r"\bunlink\b[^|&;<>]*\.xer\b", re.IGNORECASE),
    # find ... -delete targeting .xer
    re.compile(r"\bfind\b[^|]*\*\.xer[^|]*-delete\b", re.IGNORECASE),
]

BLOCK_EDIT_MESSAGE = (
    "XER safety hook: blocked {tool} on '{name}'.\n"
    "\n"
    ".xer files are immutable project records. Every modification must be "
    "saved as a NEW versioned file (e.g. '{stem}-v2.xer') next to the "
    "previous version — never edit in place.\n"
    "\n"
    "To proceed: use Write with a new -vN.xer filename instead of Edit on "
    "an existing .xer."
)

BLOCK_OVERWRITE_MESSAGE = (
    "XER safety hook: blocked Write overwriting existing '{name}'.\n"
    "\n"
    ".xer files are immutable. Write a NEW versioned file (e.g. "
    "'{stem}-v2.xer') instead of replacing the existing one.\n"
    "\n"
    "Detected target: {path}"
)

BLOCK_DELETE_MESSAGE = (
    "XER safety hook: blocked Bash command that deletes a .xer file.\n"
    "\n"
    ".xer files are immutable project records and must never be deleted "
    "— they are the historical record for claims and delay analysis.\n"
    "\n"
    "Blocked command: {command}"
)


def check_file_tool(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """Returns (allow, reason_if_blocked)."""
    if tool_name not in RELEVANT_FILE_TOOLS:
        return True, ""

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return True, ""

    path = Path(file_path)
    if path.suffix.lower() != ".xer":
        return True, ""

    # Edit / MultiEdit / NotebookEdit on any .xer: always blocked.
    if tool_name in ("Edit", "MultiEdit", "NotebookEdit"):
        return False, BLOCK_EDIT_MESSAGE.format(
            tool=tool_name, name=path.name, stem=path.stem
        )

    # Write: blocked if the file already exists (overwrite == modification).
    # Allowed if the file is new (that's how a new -vN.xer gets saved).
    if tool_name == "Write":
        if path.exists():
            return False, BLOCK_OVERWRITE_MESSAGE.format(
                name=path.name, stem=path.stem, path=str(path)
            )
        return True, ""

    return True, ""


def check_bash(tool_input: dict) -> tuple[bool, str]:
    command = tool_input.get("command", "") or ""
    if not command:
        return True, ""

    for pattern in _BASH_DELETE_PATTERNS:
        if pattern.search(command):
            return False, BLOCK_DELETE_MESSAGE.format(command=command)

    return True, ""


def check(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    if tool_name == "Bash":
        return check_bash(tool_input)
    if tool_name in RELEVANT_FILE_TOOLS:
        return check_file_tool(tool_name, tool_input)
    return True, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        # Fail open — never block a tool call because the hook couldn't parse
        # its input. Print diagnostic so a real misconfiguration is visible.
        print(f"check_xer_write: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    allow, reason = check(tool_name, tool_input)
    if allow:
        return 0
    print(reason, file=sys.stderr)
    return 2


def self_test() -> int:
    """Exercise the rule table. Run with `python check_xer_write.py --self-test`."""
    tmp = Path(tempfile.mkdtemp(prefix="xer_hook_test_"))
    failures: list[str] = []

    def case(label: str, tool_name: str, tool_input: dict, should_allow: bool):
        allow, reason = check(tool_name, tool_input)
        ok = allow == should_allow
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok:
            failures.append(f"{label}  (got allow={allow}, want {should_allow})")
            if reason:
                print(f"    reason: {reason.splitlines()[0]}")

    try:
        record = tmp / "2026-04-17 Project.xer"
        record.write_text("X", encoding="utf-8")

        existing_v2 = tmp / "2026-04-17 Project-v2.xer"
        existing_v2.write_text("X", encoding="utf-8")

        new_v3 = tmp / "2026-04-17 Project-v3.xer"  # doesn't exist
        new_other = tmp / "new-file.xer"            # doesn't exist

        txt = tmp / "notes.txt"
        txt.write_text("X", encoding="utf-8")

        print("File-tool cases:")
        case("block Edit on record .xer", "Edit", {"file_path": str(record)}, False)
        case("block Edit on existing v2 .xer", "Edit", {"file_path": str(existing_v2)}, False)
        case("block MultiEdit on record .xer", "MultiEdit", {"file_path": str(record)}, False)
        case("block Write overwriting record", "Write", {"file_path": str(record)}, False)
        case("block Write overwriting existing v2", "Write", {"file_path": str(existing_v2)}, False)
        case("allow Write new -v3.xer", "Write", {"file_path": str(new_v3)}, True)
        case("allow Write brand-new .xer", "Write", {"file_path": str(new_other)}, True)
        case("allow Edit on .txt", "Edit", {"file_path": str(txt)}, True)
        case("allow Write on .txt", "Write", {"file_path": str(tmp / "new.txt")}, True)
        case("allow Edit with no file_path", "Edit", {}, True)

        print("Bash cases:")
        case("block rm *.xer", "Bash", {"command": "rm -f *.xer"}, False)
        case("block rm specific .xer", "Bash", {"command": "rm '2026-04-17 Project.xer'"}, False)
        case("block del record.xer (cmd)", "Bash", {"command": "del record.xer"}, False)
        case("block Remove-Item *.xer", "Bash", {"command": "Remove-Item *.xer"}, False)
        case("block find -name '*.xer' -delete", "Bash", {"command": "find . -name '*.xer' -delete"}, False)
        case("allow rm *.txt", "Bash", {"command": "rm -rf *.txt"}, True)
        case("allow ls *.xer", "Bash", {"command": "ls *.xer"}, True)
        case("allow cat file.xer", "Bash", {"command": "cat file.xer"}, True)
        case("allow mv with .xer (not a delete)", "Bash", {"command": "mv 'a.xer' 'a-v2.xer'"}, True)

        print("Non-relevant tools pass through:")
        case("allow Bash with no command", "Bash", {}, True)
        case("allow Read", "Read", {"file_path": str(record)}, True)
        case("allow Grep", "Grep", {"pattern": "foo"}, True)

    finally:
        for p in tmp.rglob("*"):
            if p.is_file():
                p.unlink()
        tmp.rmdir()

    if failures:
        print(f"\n{len(failures)} failure(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nAll cases passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(self_test())
    sys.exit(main())
