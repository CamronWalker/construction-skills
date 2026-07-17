// Westland Project Files PreToolUse guard — the "G drive" guard.
//
// Guards the Westland Project Files share, the canonical project-record store
// (schedules, drawings, contracts, claims evidence). "G drive" is the everyday
// name; the share is reached three ways and all are covered here: the mapped
// G:\ drive, two network UNC mirrors (\\orem-fs, \\westland-local-dfs1), and the
// MSYS `/g/` drive form that Claude Code's Bash tool emits on Windows.
//
// Node port of the retired westland_share_guard.py — behavior-identical rule
// table, run through Node instead of PowerShell+Python so it (a) works on the
// Windows host and in Cowork's Linux sandbox, (b) needs no Python, and (c) is a
// single clean `node "<path>"` hook command with no nested quotes for a second
// shell to mangle (the old command dropped PowerShell into an interactive
// window and errored `At line:1 char:68`).
//
// Rules (only files/commands under a Westland root are in scope):
//   1. Modify — Edit/MultiEdit/NotebookEdit on an existing file, or a Write that
//      overwrites one, asks for confirmation (permissionDecision "ask").
//   2. Versioned types (.xer) — in-place modification is hard-denied; each
//      revision is a new -vN file alongside the original.
//   3. Delete — a Bash/PowerShell delete verb targeting the share is denied
//      (move to _Archive / _to_delete instead).
//   Allowlist (.html/.md/.json) — working artifacts, exempt from rules 1 and 3.
//
// Fail modes:
//   - Outside the share, brand-new files, and the whole Linux sandbox → allow
//     (silent). Never block colleagues on non-record work.
//   - Unparseable stdin → stderr diagnostic, exit 0 (fail open).
//   - Unexpected error while evaluating a *share modification* → deny (fail
//     CLOSED) with a "file a bug" reason. Corporate records are never silently
//     overwritten because the guard hiccuped.
//
// Reads a PreToolUse JSON envelope on stdin, emits a hookSpecificOutput JSON
// decision on stdout (exit 0). Importable for tests (see g-drive-guard.test.mjs).

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const RELEVANT_FILE_TOOLS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit']);

// In-place modification of these is hard-denied (rule 2); revisions go in a new
// -vN file alongside the original.
const VERSIONED_EXTENSIONS = new Set(['.xer']);

// Working-artifact extensions — exempt from rules 1 and 3. Regenerated outputs
// (HTML reports, markdown notes, JSON configs), not audit-trail records.
const ALLOWED_EXTENSIONS = new Set(['.html', '.md', '.json']);

// Microsoft Office documents — age-locked on the share. A settled record (not
// modified in >7 days) is DENIED for in-place overwrite; a recently-modified
// one (a live working doc) prompts; a brand-new file is allowed. This only
// catches writes the hook can see a path for (direct Edit/Write tool calls);
// binary Office files written by scripts (openpyxl / python-docx via Bash)
// carry their path inside the script and are out of the hook's reach — those
// are covered by the standing "don't overwrite Office records" instruction, not
// here. See officeAgeDecision.
const OFFICE_EXTENSIONS = new Set([
  '.xlsx', '.xlsm', '.xlsb', '.xls',
  '.docx', '.docm', '.doc', '.dotx',
  '.pptx', '.pptm', '.ppt',
]);
const OFFICE_LOCK_AGE_MS = 7 * 24 * 60 * 60 * 1000;

// Westland Project Files roots — the protected zone. Covers the mapped drive,
// the two UNC mirrors, and the MSYS drive form.
const WESTLAND_ROOTS = [
  'G:\\Westland Project Files',
  '\\\\orem-fs\\Common\\Westland Project Files',
  '\\\\westland-local-dfs1\\Common\\Westland Project Files',
  '/g/Westland Project Files',
];

function normalizeForRootCheck(s) {
  // Lowercase + collapse `/` to `\` so root prefixes match against arbitrary
  // path/command strings regardless of slash direction or case.
  return s.toLowerCase().split('/').join('\\');
}

const NORMALIZED_ROOTS = WESTLAND_ROOTS.map(normalizeForRootCheck);

function inWestlandRoot(pathOrCommand) {
  if (!pathOrCommand) return false;
  const normalized = normalizeForRootCheck(pathOrCommand);
  return NORMALIZED_ROOTS.some((root) => normalized.includes(root));
}

function suffix(p) {
  // path.win32 so `\`, `/`, drive-letter, and UNC forms parse the same on any OS.
  return path.win32.extname(p).toLowerCase();
}

function basename(p) {
  return path.win32.basename(p);
}

function stem(p) {
  return path.win32.basename(p, path.win32.extname(p));
}

function isVersioned(p) {
  return VERSIONED_EXTENSIONS.has(suffix(p));
}

function isAllowedExt(p) {
  return ALLOWED_EXTENSIONS.has(suffix(p));
}

function isOffice(p) {
  return OFFICE_EXTENSIONS.has(suffix(p));
}

// Decide an Office file's fate by last-modified age. new (ENOENT) -> allow;
// modified within the lock window -> ask (live working doc); older -> deny
// (settled record). Any stat failure other than "absent" -> deny (fail closed —
// don't let an unreadable record slip through as editable).
function officeAgeDecision(filePath) {
  let st;
  try {
    st = fs.statSync(normalizeFsPath(filePath));
  } catch (e) {
    if (e && e.code === 'ENOENT') return 'allow';
    return 'deny';
  }
  return Date.now() - st.mtimeMs > OFFICE_LOCK_AGE_MS ? 'deny' : 'ask';
}

// Map MSYS/UNC path forms to the native Windows form so fs.existsSync resolves
// reliably (an unresolved `/g/...` used to look absent → a share overwrite could
// slip through as a "new file"). Native paths pass through unchanged.
export function normalizeFsPath(p) {
  if (!p) return p;
  const drive = /^\/([a-zA-Z])\/(.*)$/.exec(p);
  if (drive) return `${drive[1].toUpperCase()}:\\${drive[2]}`;
  if (p.startsWith('//')) return `\\\\${p.slice(2)}`;
  return p;
}

function targetExists(p) {
  try {
    return fs.existsSync(normalizeFsPath(p));
  } catch {
    // Can't determine — treat as existing so a share Write is handled as an
    // overwrite (protective), never waved through as new.
    return true;
  }
}

// Bash / PowerShell delete-verb patterns. Path-scope filter runs first; these
// only classify whether an in-scope command is a delete.
const BASH_DELETE_PATTERNS = [
  /\brm\b(?:\s+-[a-zA-Z]+)*\s+\S/i,       // rm / rm -f / rm -rf <arg>
  /\b(?:del|erase)\b\s+\S/i,               // cmd del / erase <arg>
  /\b(?:Remove-Item|rmdir)\b\s+\S/i,       // PowerShell Remove-Item / rmdir <arg>
  /\bunlink\b\s+\S/i,                      // unlink <arg>
  /\bfind\b[^|]*-delete\b/i,               // find ... -delete
];

function isDeleteCommand(command) {
  return BASH_DELETE_PATTERNS.some((re) => re.test(command));
}

function deleteTargetsAllAllowedExt(command) {
  // find -delete walks the tree at runtime; can't enumerate → keep deny.
  if (/\bfind\b[^|]*-delete\b/i.test(command)) return false;

  const targets = [];
  // Quoted paths (single or double quotes) — the most reliable path signal.
  for (const m of command.matchAll(/['"]([^'"]+)['"]/g)) targets.push(m[1]);
  // Unquoted tokens starting with a drive letter or leading slash and ending in
  // a .ext — catches `rm /g/path/file.md` without requiring quotes.
  for (const m of command.matchAll(/(?:[A-Za-z]:|\/)[^\s'"]*\.[A-Za-z0-9]+/g)) targets.push(m[0]);

  if (targets.length === 0) return false;
  return targets.every(isAllowedExt);
}

// --- messages (ported verbatim) --------------------------------------------

const denyVersionedEdit = ({ tool, name, stem: s, ext }) =>
`⚠️ Westland version-controlled file: ${tool} on an existing ${ext} file is rejected.

${ext} files in the Westland Project Files share are immutable project records — source of truth for claims, delay analysis, and contract disputes. The original cannot be modified in place.

Instead of editing the existing file:
  Write a new versioned file alongside it.

Example:
  UNSAFE (rejected): ${tool} on "${name}"
  SAFE:              Write to "${s}-v2${ext}"
                     (then -v3, -v4, etc. for subsequent revisions)

If a step seems to require editing an existing ${ext}, you've misunderstood the workflow — stop and ask the colleague.`;

const denyVersionedOverwrite = ({ name, stem: s, ext, path: p }) =>
`⚠️ Westland version-controlled file: Write overwriting an existing ${ext} file is rejected.

${ext} files in the Westland Project Files share are immutable project records — source of truth for claims, delay analysis, and contract disputes. They cannot be replaced in place.

Instead of overwriting:
  Write a new versioned file alongside the existing one.

Example:
  UNSAFE (rejected): Write to "${name}" (already exists at ${p})
  SAFE:              Write to "${s}-v2${ext}"
                     (then -v3, -v4, etc. for subsequent revisions)

If a step seems to require overwriting an existing ${ext}, you've misunderstood the workflow — stop and ask the colleague.`;

const denyDelete = ({ command }) =>
`⚠️ Westland Project Files: deleting files in the Westland share is not allowed.

Files in the Westland Project Files share are project records — drawings, schedules, contracts, claims evidence. Deletes can't be reversed and may erase audit trail. Camron's policy: deletes must go through human review.

Exception: deletes whose targets all carry a working-artifact extension (.html, .md, .json) are allowed without prompting.

Instead of deleting:
  Move the file or folder into an _Archive or _to_delete folder so a human can review and remove it later.

Example:
  UNSAFE (rejected): rm "G:\\Westland Project Files\\Job\\old.xer"
  SAFE:              move into "G:\\Westland Project Files\\Job\\_to_delete\\old.xer"

Blocked command: ${command}`;

const askModify = ({ name, path: p }) =>
`Modifying an existing file in the Westland Project Files share — '${name}' at ${p}.

Files in this share are project records. Auto-mode cannot auto-approve modifications here; please confirm you intend to overwrite this file. If you meant to write a new file alongside the original (a -v2 / -vN copy), cancel and rename the target.`;

const denyOfficeLocked = ({ name, stem: s, ext, path: p }) =>
`⚠️ Westland record lock: '${name}' is an Office file on the Westland share that hasn't changed in over 7 days, so it's treated as a settled project record and can't be overwritten in place.

Path: ${p}

To change it, either:
  • Open and save it manually first — that resets its clock, and this drops to a confirmation prompt instead of a block, OR
  • Write your changes to a new versioned copy: "${s}-v2${ext}" (then -v3, etc.).

If you didn't mean to overwrite a settled record, stop and ask the colleague.`;

const askOfficeRecent = ({ name, path: p }) =>
`Overwriting a recently-modified Office file on the Westland share — '${name}' at ${p}.

This file changed within the last 7 days, so it's treated as a live working document rather than a settled record. Confirm you intend to overwrite it (or write a new -v2 copy alongside instead).`;

const GUARD_ERROR_MESSAGE =
`⚠️ Westland guard error: this Westland Project Files modification was blocked for safety.

The guard hit an unexpected error while evaluating this call, so it failed closed rather than risk silently overwriting a project record. Nothing was changed. Retry the operation; if it keeps failing, run westland-bug-report so the guard can be fixed. (Brand-new files and anything outside the share are unaffected.)`;

// --- rule evaluation --------------------------------------------------------

function checkFileTool(toolName, toolInput) {
  if (!RELEVANT_FILE_TOOLS.has(toolName)) return ['allow', ''];

  const filePath = toolInput.file_path || toolInput.notebook_path || '';
  if (!filePath) return ['allow', ''];

  // Path-scope filter: only Westland Project Files are protected.
  if (!inWestlandRoot(filePath)) return ['allow', ''];

  // Allowlist: working artifacts are freely editable/overwritable.
  if (isAllowedExt(filePath)) return ['allow', ''];

  const ext = suffix(filePath);

  // Rule 2: versioned types are hard-denied for in-place modification.
  if (isVersioned(filePath)) {
    if (toolName === 'Edit' || toolName === 'MultiEdit' || toolName === 'NotebookEdit') {
      return ['deny', denyVersionedEdit({ tool: toolName, name: basename(filePath), stem: stem(filePath), ext })];
    }
    if (toolName === 'Write') {
      if (targetExists(filePath)) {
        return ['deny', denyVersionedOverwrite({ name: basename(filePath), stem: stem(filePath), ext, path: filePath })];
      }
      return ['allow', '']; // new -vN.xer is the intended revision path
    }
  }

  // Office documents: age-lock. Settled records (>7 days) are denied; recent
  // working docs prompt; new files are allowed. Only fires on direct Edit/Write
  // tool calls (script writes carry their path internally and aren't seen here).
  if (isOffice(filePath)) {
    const decision = officeAgeDecision(filePath);
    if (decision === 'deny') {
      return ['deny', denyOfficeLocked({ name: basename(filePath), stem: stem(filePath), ext, path: filePath })];
    }
    if (decision === 'ask') {
      return ['ask', askOfficeRecent({ name: basename(filePath), path: filePath })];
    }
    return ['allow', ''];
  }

  // Rule 1: any other existing file in the share requires confirmation.
  if (toolName === 'Edit' || toolName === 'MultiEdit' || toolName === 'NotebookEdit') {
    return ['ask', askModify({ name: basename(filePath), path: filePath })];
  }
  if (toolName === 'Write') {
    if (targetExists(filePath)) {
      return ['ask', askModify({ name: basename(filePath), path: filePath })];
    }
    return ['allow', ''];
  }

  return ['allow', ''];
}

function checkBash(toolInput) {
  const command = toolInput.command || '';
  if (!command) return ['allow', ''];

  // Only deletes that touch the share matter — kills false positives from
  // heredocs, string literals, and unrelated paths that merely mention a verb.
  if (!inWestlandRoot(command)) return ['allow', ''];
  if (!isDeleteCommand(command)) return ['allow', ''];
  if (deleteTargetsAllAllowedExt(command)) return ['allow', ''];

  return ['deny', denyDelete({ command })];
}

export function check(toolName, toolInput) {
  const input = toolInput || {};
  try {
    if (toolName === 'Bash' || toolName === 'PowerShell') return checkBash(input);
    if (RELEVANT_FILE_TOOLS.has(toolName)) return checkFileTool(toolName, input);
    return ['allow', ''];
  } catch {
    // Fail CLOSED for share modifications; fail open for everything else.
    if (isShareModification(toolName, input)) return ['deny', GUARD_ERROR_MESSAGE];
    return ['allow', ''];
  }
}

// True when the call would modify an existing thing on the share — used by the
// fail-closed error path. Kept minimal and self-defending so it can't itself
// throw the guard into a bad state.
export function isShareModification(toolName, toolInput) {
  try {
    const input = toolInput || {};
    if (RELEVANT_FILE_TOOLS.has(toolName)) {
      const filePath = input.file_path || input.notebook_path || '';
      return inWestlandRoot(filePath);
    }
    if (toolName === 'Bash' || toolName === 'PowerShell') {
      const command = input.command || '';
      return inWestlandRoot(command) && isDeleteCommand(command);
    }
    return false;
  } catch {
    return false;
  }
}

// --- test hooks -------------------------------------------------------------

const injectedRoots = [];

export function addTestRoot(rawPath) {
  const normalized = normalizeForRootCheck(rawPath);
  injectedRoots.push(normalized);
  NORMALIZED_ROOTS.push(normalized);
}

export function clearTestRoots() {
  for (const r of injectedRoots) {
    const i = NORMALIZED_ROOTS.indexOf(r);
    if (i !== -1) NORMALIZED_ROOTS.splice(i, 1);
  }
  injectedRoots.length = 0;
}

// --- CLI entry (PreToolUse hook) --------------------------------------------

function emitDecision(decision, reason) {
  if (decision === 'allow') return 0;
  const payload = {
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: decision,
      permissionDecisionReason: reason,
    },
  };
  process.stdout.write(JSON.stringify(payload));
  return 0;
}

async function runCli() {
  let raw = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) raw += chunk;

  let payload;
  try {
    payload = JSON.parse(raw || '{}');
  } catch (err) {
    // Fail open — never block a tool because the hook couldn't parse its input.
    process.stderr.write(`g-drive-guard: invalid JSON on stdin: ${err}\n`);
    process.exit(0);
  }

  const [decision, reason] = check(payload.tool_name || '', payload.tool_input || {});
  process.exit(emitDecision(decision, reason));
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  runCli();
}
