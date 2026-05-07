r"""
Claude Code PreToolUse hook for the Westland organizational plugin.

Enforces three rules across the Westland Project Files share (the mapped
G:\ drive plus the two network UNC mirrors). The share is the canonical
project record store -- schedules, drawings, contracts, claims evidence
-- and these rules prevent accidental loss in Claude Code auto-mode.

Rule 1 -- Modify (any file type): every Edit / MultiEdit / NotebookEdit
on an existing file, and every Write that overwrites an existing file,
asks the user for explicit permission via permissionDecision: "ask".
Auto-approve modes do not auto-approve these calls. Brand-new file
writes are allowed (creating new content is fine).

Rule 2 -- Version-controlled types: file extensions in
_VERSIONED_EXTENSIONS (currently .xer) are hard-denied for in-place
modification. The original is immutable; each revision goes in a new
-vN file alongside it. Writing a new -vN file is allowed.

Rule 3 -- Delete: any Bash / PowerShell command that contains a
Westland-root path AND a delete verb (rm, del, erase, Remove-Item,
rmdir, unlink, find -delete) is hard-denied. Move the file or folder
into an _Archive or _to_delete folder for human review instead.

Allowlist: working-artifact extensions in _ALLOWED_EXTENSIONS
(.html, .md, .json) are exempt from rules 1 and 3. They can be edited,
overwritten, and deleted in the share without prompting -- they're
regenerated artifacts (HTML reports, markdown notes, JSON configs)
rather than audit-trail records.

Files outside the Westland Project Files share (different drive, the
user's home, OneDrive personal sync, /tmp, etc.) are not protected by
any rule -- the hook returns allow.

Reads a PreToolUse JSON envelope from stdin. Emits a JSON response on
stdout per Claude Code's hookSpecificOutput format (exit 0). Legacy
exit-2/stderr is still used on JSON parse failure for compatibility.

Self-test: `python check_xer_write.py --self-test`
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

RELEVANT_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# File extensions whose existing files are hard-denied for in-place
# modification (rule 2). Each revision gets a new -vN file alongside the
# original. Add more extensions here as the company adopts versioning
# discipline for them.
_VERSIONED_EXTENSIONS: frozenset[str] = frozenset({".xer"})

# Working-artifact extensions exempt from rules 1 and 3. Files of these
# types can be freely edited, overwritten, or deleted in the Westland
# share -- they're regenerated from source data (HTML reports, markdown
# notes, JSON configs) and don't carry the audit-trail weight that
# drawings, contracts, and schedules do. Allowlist takes precedence over
# both the modify-prompt and the delete-deny.
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".html", ".md", ".json"})

# Westland Project Files roots -- the protected zone. Only files under
# one of these prefixes are subject to the three rules. The prefix list
# covers the share's three access paths: the mapped G:\ drive on Camron's
# machine, and the two network share UNC mirrors. OneDrive personal sync
# is intentionally excluded.
_WESTLAND_ROOTS: list[str] = [
    r"G:\Westland Project Files",
    r"\\orem-fs\Common\Westland Project Files",
    r"\\westland-local-dfs1\Common\Westland Project Files",
    # MSYS-style mapped drive form. Claude Code's Bash tool runs through
    # MSYS on Windows, so commands appear with paths like
    # "/g/Westland Project Files/...". The UNC roots above already
    # collapse to the same normalized form whether spelled \\server or
    # //server, but the drive form needs its own entry.
    "/g/Westland Project Files",
]


def _normalize_for_root_check(s: str) -> str:
    """Lowercase + collapse path separators. Used for substring matching
    the Westland root prefixes against arbitrary path or command strings."""
    return s.lower().replace("/", "\\")


_NORMALIZED_ROOTS: list[str] = [_normalize_for_root_check(r) for r in _WESTLAND_ROOTS]


def _in_westland_root(path_or_command: str) -> bool:
    """True if the given path or command string contains a Westland project
    root prefix. Case-insensitive; tolerates forward or backward slashes."""
    if not path_or_command:
        return False
    normalized = _normalize_for_root_check(path_or_command)
    return any(root in normalized for root in _NORMALIZED_ROOTS)


def _is_versioned(path: Path) -> bool:
    return path.suffix.lower() in _VERSIONED_EXTENSIONS


def _is_allowed_ext(path_or_str) -> bool:
    """True if the given Path or path-like string has an extension in the
    allowlist. Used to short-circuit both the modify-prompt rule and the
    delete-deny rule for working artifacts (.html, .md, .json)."""
    if isinstance(path_or_str, Path):
        return path_or_str.suffix.lower() in _ALLOWED_EXTENSIONS
    return Path(path_or_str).suffix.lower() in _ALLOWED_EXTENSIONS


def _delete_targets_all_allowed_ext(command: str) -> bool:
    """For a delete command that touches the Westland share, return True if
    every file-like target argument has an extension in _ALLOWED_EXTENSIONS.

    Conservative -- returns False for forms we can't enumerate confidently
    (find -delete, recursive folder removes, bare unquoted globs that
    don't include a path prefix). Those keep the deny.
    """
    # find -delete walks the tree at runtime; we can't know what gets matched.
    if re.search(r"\bfind\b[^|]*-delete\b", command, re.IGNORECASE):
        return False

    targets: list[str] = []

    # Quoted paths (single or double quotes). The most reliable signal of
    # "here's a path argument."
    targets.extend(re.findall(r"""['"]([^'"]+)['"]""", command))

    # Unquoted tokens that begin with a drive letter (C:\) or leading slash
    # (/g/ or /Users/) AND end with a .ext. Catches `rm /g/path/file.md`
    # without forcing the user to quote.
    targets.extend(
        re.findall(r"""(?:[A-Za-z]:|/)[^\s'"]*\.[A-Za-z0-9]+""", command)
    )

    if not targets:
        return False

    return all(_is_allowed_ext(t) for t in targets)


# Bash / PowerShell delete-verb patterns. The path-scope filter (the
# command must contain a Westland-root prefix) runs first; these patterns
# then identify whether the command is a delete.
_BASH_DELETE_PATTERNS = [
    # rm / rm -f / rm -rf followed by an argument
    re.compile(r"\brm\b(?:\s+-[a-zA-Z]+)*\s+\S", re.IGNORECASE),
    # cmd del / erase followed by an argument
    re.compile(r"\b(?:del|erase)\b\s+\S", re.IGNORECASE),
    # PowerShell Remove-Item / rmdir followed by an argument
    re.compile(r"\b(?:Remove-Item|rmdir)\b\s+\S", re.IGNORECASE),
    # unlink followed by an argument
    re.compile(r"\bunlink\b\s+\S", re.IGNORECASE),
    # find ... -delete
    re.compile(r"\bfind\b[^|]*-delete\b", re.IGNORECASE),
]


DENY_VERSIONED_EDIT_MESSAGE = """⚠️ Westland version-controlled file: {tool} on an existing {ext} file is rejected.

{ext} files in the Westland Project Files share are immutable project records — source of truth for claims, delay analysis, and contract disputes. The original cannot be modified in place.

Instead of editing the existing file:
  Write a new versioned file alongside it.

Example:
  UNSAFE (rejected): {tool} on "{name}"
  SAFE:              Write to "{stem}-v2{ext}"
                     (then -v3, -v4, etc. for subsequent revisions)

If a step seems to require editing an existing {ext}, you've misunderstood the workflow — stop and ask the colleague."""

DENY_VERSIONED_OVERWRITE_MESSAGE = """⚠️ Westland version-controlled file: Write overwriting an existing {ext} file is rejected.

{ext} files in the Westland Project Files share are immutable project records — source of truth for claims, delay analysis, and contract disputes. They cannot be replaced in place.

Instead of overwriting:
  Write a new versioned file alongside the existing one.

Example:
  UNSAFE (rejected): Write to "{name}" (already exists at {path})
  SAFE:              Write to "{stem}-v2{ext}"
                     (then -v3, -v4, etc. for subsequent revisions)

If a step seems to require overwriting an existing {ext}, you've misunderstood the workflow — stop and ask the colleague."""

DENY_DELETE_MESSAGE = """⚠️ Westland Project Files: deleting files in the Westland share is not allowed.

Files in the Westland Project Files share are project records — drawings, schedules, contracts, claims evidence. Deletes can't be reversed and may erase audit trail. Camron's policy: deletes must go through human review.

Exception: deletes whose targets all carry a working-artifact extension (.html, .md, .json) are allowed without prompting.

Instead of deleting:
  Move the file or folder into an _Archive or _to_delete folder so a human can review and remove it later.

Example:
  UNSAFE (rejected): rm "G:\\Westland Project Files\\Job\\old.xer"
  SAFE:              move into "G:\\Westland Project Files\\Job\\_to_delete\\old.xer"

Blocked command: {command}"""

ASK_MODIFY_MESSAGE = """Modifying an existing file in the Westland Project Files share — '{name}' at {path}.

Files in this share are project records. Auto-mode cannot auto-approve modifications here; please confirm you intend to overwrite this file. If you meant to write a new file alongside the original (a -v2 / -vN copy), cancel and rename the target."""


def check_file_tool(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """Returns (decision, reason). decision in {'allow', 'deny', 'ask'}."""
    if tool_name not in RELEVANT_FILE_TOOLS:
        return "allow", ""

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not file_path:
        return "allow", ""

    path = Path(file_path)

    # Path-scope filter: only Westland Project Files are protected.
    if not _in_westland_root(file_path):
        return "allow", ""

    # Allowlist: working-artifact extensions are freely editable and
    # overwritable. Bypasses both rule 1 (modify-prompt) and rule 2
    # (versioned-deny) -- though no allowlisted ext is currently versioned.
    if _is_allowed_ext(path):
        return "allow", ""

    # Rule 2: version-controlled types are hard-denied for in-place
    # modification.
    if _is_versioned(path):
        ext = path.suffix.lower()
        if tool_name in ("Edit", "MultiEdit", "NotebookEdit"):
            return "deny", DENY_VERSIONED_EDIT_MESSAGE.format(
                tool=tool_name, name=path.name, stem=path.stem, ext=ext
            )
        if tool_name == "Write":
            if path.exists():
                return "deny", DENY_VERSIONED_OVERWRITE_MESSAGE.format(
                    name=path.name, stem=path.stem, ext=ext, path=str(path)
                )
            # New -vN.xer is the intended path for revisions.
            return "allow", ""

    # Rule 1: any other file in the Westland share requires user
    # confirmation for modification. Edit / MultiEdit / NotebookEdit
    # imply the file already exists; Write is only a modification when
    # the target already exists.
    if tool_name in ("Edit", "MultiEdit", "NotebookEdit"):
        return "ask", ASK_MODIFY_MESSAGE.format(name=path.name, path=str(path))
    if tool_name == "Write":
        if path.exists():
            return "ask", ASK_MODIFY_MESSAGE.format(name=path.name, path=str(path))
        return "allow", ""

    return "allow", ""


def check_bash(tool_input: dict) -> tuple[str, str]:
    """Returns (decision, reason). decision in {'allow', 'deny'}.

    The ask path doesn't apply to Bash / PowerShell -- the modify rule is
    enforced through the file-tool path. Bash sees only the delete rule.
    """
    command = tool_input.get("command", "") or ""
    if not command:
        return "allow", ""

    # Path-scope filter: a delete command only matters if it touches the
    # Westland share. This kills false positives from heredocs, string
    # literals, and unrelated paths that merely *mention* a delete verb.
    if not _in_westland_root(command):
        return "allow", ""

    is_delete = any(p.search(command) for p in _BASH_DELETE_PATTERNS)
    if not is_delete:
        return "allow", ""

    # Allowlist: a delete that targets only working-artifact extensions
    # (.html, .md, .json) is permitted. Anything that isn't clearly
    # restricted to those extensions falls through to the deny.
    if _delete_targets_all_allowed_ext(command):
        return "allow", ""

    return "deny", DENY_DELETE_MESSAGE.format(command=command)


def check(tool_name: str, tool_input: dict) -> tuple[str, str]:
    # Bash and PowerShell both expose a `command` field; treat them the same.
    if tool_name in ("Bash", "PowerShell"):
        return check_bash(tool_input)
    if tool_name in RELEVANT_FILE_TOOLS:
        return check_file_tool(tool_name, tool_input)
    return "allow", ""


def _emit_decision(decision: str, reason: str) -> int:
    """Emit a Claude Code PreToolUse hook decision via the JSON output
    format and return the exit code. For 'allow', no output is emitted
    (exit 0 alone is sufficient)."""
    if decision == "allow":
        return 0
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload))
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        # Fail open — never block a tool call because the hook couldn't
        # parse its input. Print diagnostic so a real misconfiguration is
        # visible.
        print(f"check_xer_write: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    decision, reason = check(tool_name, tool_input)
    return _emit_decision(decision, reason)


def self_test() -> int:
    r"""Exercise the rule table. Run with `python check_xer_write.py --self-test`.

    Tests inject the tmp directory as an additional Westland root so file
    operations on real on-disk paths exercise the path-scope predicate
    without needing an actual G:\ drive present.
    """
    tmp = Path(tempfile.mkdtemp(prefix="xer_hook_test_"))
    failures: list[str] = []

    # Inject the tmp dir as an additional Westland root for the duration
    # of the test, so file-tool tests can use real on-disk paths under
    # tmp without manufacturing a G:\ drive.
    original_roots = list(_NORMALIZED_ROOTS)
    _NORMALIZED_ROOTS.append(_normalize_for_root_check(str(tmp)))

    def case(label: str, tool_name: str, tool_input: dict, expected: str):
        decision, reason = check(tool_name, tool_input)
        ok = decision == expected
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok:
            failures.append(
                f"{label}  (got decision={decision!r}, want {expected!r})"
            )
            if reason:
                print(f"    reason: {reason.splitlines()[0]}")

    try:
        record = tmp / "2026-04-17 Project.xer"
        record.write_text("X", encoding="utf-8")

        existing_v2 = tmp / "2026-04-17 Project-v2.xer"
        existing_v2.write_text("X", encoding="utf-8")

        new_v3 = tmp / "2026-04-17 Project-v3.xer"  # doesn't exist
        new_other = tmp / "new-file.xer"            # doesn't exist

        existing_txt = tmp / "notes.txt"
        existing_txt.write_text("X", encoding="utf-8")

        existing_pdf = tmp / "drawing.pdf"
        existing_pdf.write_text("X", encoding="utf-8")

        # Outside-root paths -- not under any Westland root.
        outside_existing = tmp.parent / "xer_hook_outside.xer"
        outside_existing.write_text("X", encoding="utf-8")

        outside_txt = tmp.parent / "xer_hook_outside.txt"
        outside_txt.write_text("X", encoding="utf-8")

        # ------------------------------------------------------------------
        print("Rule 2 -- versioned-type cases (inside Westland root):")
        case("deny Edit on existing .xer record", "Edit", {"file_path": str(record)}, "deny")
        case("deny Edit on existing -v2.xer", "Edit", {"file_path": str(existing_v2)}, "deny")
        case("deny MultiEdit on existing .xer", "MultiEdit", {"file_path": str(record)}, "deny")
        case("deny Write overwriting existing .xer record", "Write", {"file_path": str(record)}, "deny")
        case("deny Write overwriting existing -v2.xer", "Write", {"file_path": str(existing_v2)}, "deny")
        case("allow Write new -v3.xer", "Write", {"file_path": str(new_v3)}, "allow")
        case("allow Write brand-new .xer", "Write", {"file_path": str(new_other)}, "allow")

        # ------------------------------------------------------------------
        print("Rule 1 -- modify-prompt cases (inside Westland root, non-versioned):")
        case("ask on Edit existing .txt", "Edit", {"file_path": str(existing_txt)}, "ask")
        case("ask on MultiEdit existing .txt", "MultiEdit", {"file_path": str(existing_txt)}, "ask")
        case("ask on Write overwriting existing .txt", "Write", {"file_path": str(existing_txt)}, "ask")
        case("ask on Edit existing .pdf (drawing)", "Edit", {"file_path": str(existing_pdf)}, "ask")
        case("ask on Write overwriting existing .pdf", "Write", {"file_path": str(existing_pdf)}, "ask")
        case("allow Write brand-new .txt (creating new content)", "Write", {"file_path": str(tmp / "new.txt")}, "allow")
        case("allow Write brand-new .pdf", "Write", {"file_path": str(tmp / "new.pdf")}, "allow")
        case("allow Edit with no file_path", "Edit", {}, "allow")

        # ------------------------------------------------------------------
        print("Allowlist cases (file tools on .html / .md / .json inside Westland root):")
        existing_html = tmp / "report.html"
        existing_html.write_text("X", encoding="utf-8")
        existing_md = tmp / "notes.md"
        existing_md.write_text("X", encoding="utf-8")
        existing_json = tmp / "config.json"
        existing_json.write_text("X", encoding="utf-8")

        case("allow Edit on existing .html in Westland root", "Edit", {"file_path": str(existing_html)}, "allow")
        case("allow Edit on existing .md in Westland root", "Edit", {"file_path": str(existing_md)}, "allow")
        case("allow Edit on existing .json in Westland root", "Edit", {"file_path": str(existing_json)}, "allow")
        case("allow MultiEdit on existing .md in Westland root", "MultiEdit", {"file_path": str(existing_md)}, "allow")
        case("allow Write overwriting existing .html in Westland root", "Write", {"file_path": str(existing_html)}, "allow")
        case("allow Write overwriting existing .json in Westland root", "Write", {"file_path": str(existing_json)}, "allow")
        case("allow Write brand-new .md in Westland root", "Write", {"file_path": str(tmp / "new.md")}, "allow")
        case(
            "allow Edit on G:\\Westland Project Files\\ .md (literal path)",
            "Edit",
            {"file_path": r"G:\Westland Project Files\Job\notes.md"},
            "allow",
        )
        case(
            "allow Edit on UNC orem-fs Westland share .json",
            "Edit",
            {"file_path": r"\\orem-fs\Common\Westland Project Files\Job\config.json"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("Allowlist cases (delete commands on .html / .md / .json inside Westland root):")
        case(
            "allow rm of .md in Westland root",
            "Bash",
            {"command": f"rm -f '{existing_md}'"},
            "allow",
        )
        case(
            "allow rm of .html in Westland root",
            "Bash",
            {"command": f"rm '{existing_html}'"},
            "allow",
        )
        case(
            "allow Remove-Item of .json in Westland root",
            "PowerShell",
            {"command": f"Remove-Item '{existing_json}'"},
            "allow",
        )
        case(
            "allow del of .html in literal G:\\Westland Project Files",
            "Bash",
            {"command": r"del 'G:\Westland Project Files\Job\report.html'"},
            "allow",
        )
        case(
            "allow rm of two allowlisted files (mixed .md + .json)",
            "Bash",
            {"command": f"rm '{existing_md}' '{existing_json}'"},
            "allow",
        )
        case(
            "deny rm of mixed allowlisted + .xer (any non-allowlisted target re-arms deny)",
            "Bash",
            {"command": f"rm '{existing_md}' '{record}'"},
            "deny",
        )
        case(
            "deny Remove-Item -Recurse of folder in Westland root (no extension)",
            "PowerShell",
            {"command": f"Remove-Item -Recurse '{tmp}/Job'"},
            "deny",
        )
        case(
            "deny find -delete in Westland root even with .md filter (we can't enumerate)",
            "Bash",
            {"command": f"find '{tmp}' -name '*.md' -delete"},
            "deny",
        )
        case(
            "allow rm of unquoted MSYS-style /g/.../file.md",
            "Bash",
            {"command": "rm -f /g/Westland Project Files/Job/notes.md"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("File-tool cases (outside Westland root -- false-positive scope regression):")
        case("allow Edit on outside .xer", "Edit", {"file_path": str(outside_existing)}, "allow")
        case("allow Write overwriting outside .xer", "Write", {"file_path": str(outside_existing)}, "allow")
        case("allow Edit on outside .txt", "Edit", {"file_path": str(outside_txt)}, "allow")
        case("allow Write overwriting outside .txt", "Write", {"file_path": str(outside_txt)}, "allow")
        case(
            "allow Edit on synthetic C:\\Users\\...\\hook-test.xer",
            "Edit",
            {"file_path": r"C:\Users\camron\hook-test-DELETE-ME.xer"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("Rule 3 -- delete cases (inside Westland root):")
        case(
            "deny rm of file in Westland root",
            "Bash",
            {"command": f"rm -f '{record}'"},
            "deny",
        )
        case(
            "deny rm of non-versioned file in Westland root (rule 3 covers any file)",
            "Bash",
            {"command": f"rm '{existing_txt}'"},
            "deny",
        )
        case(
            "deny Remove-Item of file in Westland root",
            "Bash",
            {"command": f"Remove-Item '{record}'"},
            "deny",
        )
        case(
            "deny cd into Westland root then rm *.xer",
            "Bash",
            {"command": f"cd '{tmp}' && rm -f *.xer"},
            "deny",
        )
        case(
            "deny rmdir of folder in Westland root",
            "Bash",
            {"command": f"rmdir '{tmp}/Job'"},
            "deny",
        )
        case(
            "deny find -delete in Westland root",
            "Bash",
            {"command": f"find '{tmp}' -name '*.bak' -delete"},
            "deny",
        )
        case(
            "deny unlink of file in Westland root",
            "Bash",
            {"command": f"unlink '{record}'"},
            "deny",
        )

        # ------------------------------------------------------------------
        print("Rule 3 -- mv to _Archive / _to_delete (allowed):")
        case(
            "allow mv into _Archive folder",
            "Bash",
            {"command": f"mv '{record}' '{tmp}/_Archive/'"},
            "allow",
        )
        case(
            "allow mv into _to_delete folder",
            "Bash",
            {"command": f"mv '{record}' '{tmp}/_to_delete/'"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("Bash cases (outside Westland root -- allowed):")
        case("allow rm *.txt outside root", "Bash", {"command": "rm -rf *.txt"}, "allow")
        case("allow ls *.xer", "Bash", {"command": "ls *.xer"}, "allow")
        case("allow cat file.xer", "Bash", {"command": "cat file.xer"}, "allow")
        case(
            "allow rm of unrelated .xer outside Westland root",
            "Bash",
            {"command": "rm -f /tmp/scratch.xer"},
            "allow",
        )
        case(
            "allow rm of stuck test file in user home",
            "Bash",
            {"command": "rm 'C:/Users/camron/hook-test-DELETE-ME.xer'"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("Bash cases (heredoc / string-literal false-positive regression):")
        case(
            "allow heredoc that merely describes 'Remove-Item *.xer' in unrelated path",
            "Bash",
            {"command": "cat << 'EOF'\nRemove-Item *.xer would bypass...\nEOF"},
            "allow",
        )
        case(
            "allow command that merely mentions rm *.xer in a quoted string",
            "Bash",
            {"command": "echo 'beware: rm *.xer is destructive'"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("Westland Project Files scope cases (literal G:\\ and UNC paths):")
        case(
            "deny Edit on G:\\Westland Project Files\\ .xer",
            "Edit",
            {"file_path": r"G:\Westland Project Files\Job\schedule.xer"},
            "deny",
        )
        case(
            "ask on Edit existing .txt in G:\\Westland Project Files\\",
            "Edit",
            {"file_path": r"G:\Westland Project Files\Job\notes.txt"},
            "ask",
        )
        case(
            "deny rm of file in G:\\Westland Project Files\\",
            "Bash",
            {"command": r"rm 'G:\Westland Project Files\Job\old.xer'"},
            "deny",
        )
        case(
            "deny rm of non-versioned file in G:\\Westland Project Files\\",
            "Bash",
            {"command": r"rm 'G:\Westland Project Files\Job\notes.txt'"},
            "deny",
        )
        case(
            "deny Edit on UNC orem-fs Westland share",
            "Edit",
            {"file_path": r"\\orem-fs\Common\Westland Project Files\Job\schedule.xer"},
            "deny",
        )
        case(
            "deny Edit on UNC westland-local-dfs1 share",
            "Edit",
            {"file_path": r"\\westland-local-dfs1\Common\Westland Project Files\Job\schedule.xer"},
            "deny",
        )
        case(
            "allow Edit on .xer elsewhere on G:\\ (not Westland Project Files)",
            "Edit",
            {"file_path": r"G:\Some Other Folder\test.xer"},
            "allow",
        )
        case(
            "allow Edit on .xer outside G:\\ entirely (e.g. D:\\)",
            "Edit",
            {"file_path": r"D:\sandbox\test.xer"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("MSYS-style bash path regression (Claude's Bash tool emits these on Windows):")
        case(
            "deny rm with MSYS-style /g/ path",
            "Bash",
            {"command": "rm -f '/g/Westland Project Files/Job/old.xer'"},
            "deny",
        )
        case(
            "deny Edit with MSYS-style /g/ path on file_path",
            "Edit",
            {"file_path": "/g/Westland Project Files/Job/schedule.xer"},
            "deny",
        )
        case(
            "deny rm with MSYS-style //orem-fs UNC path",
            "Bash",
            {"command": "rm -f '//orem-fs/Common/Westland Project Files/Job/old.xer'"},
            "deny",
        )
        case(
            "ask on Edit existing .txt via MSYS-style /g/ path",
            "Edit",
            {"file_path": "/g/Westland Project Files/Job/notes.txt"},
            "ask",
        )

        # ------------------------------------------------------------------
        print("PowerShell cases (newly covered tool):")
        case(
            "deny PowerShell Remove-Item of file in Westland root",
            "PowerShell",
            {"command": f"Remove-Item '{record}'"},
            "deny",
        )
        case(
            "allow PowerShell rm of unrelated .xer",
            "PowerShell",
            {"command": "Remove-Item 'C:/Users/camron/hook-test-DELETE-ME.xer'"},
            "allow",
        )

        # ------------------------------------------------------------------
        print("Non-relevant tools pass through:")
        case("allow Bash with no command", "Bash", {}, "allow")
        case("allow Read on .xer record (read is fine)", "Read", {"file_path": str(record)}, "allow")
        case("allow Grep", "Grep", {"pattern": "foo"}, "allow")

    finally:
        # Restore the original root list so this function is idempotent
        # if called twice in the same process.
        _NORMALIZED_ROOTS[:] = original_roots
        for p in tmp.rglob("*"):
            if p.is_file():
                p.unlink()
        tmp.rmdir()
        for extra in (outside_existing, outside_txt):
            try:
                extra.unlink()
            except (OSError, NameError):
                pass

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
