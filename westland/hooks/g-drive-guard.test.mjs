// Tests for g-drive-guard.mjs — the Westland Project Files (G drive) PreToolUse
// guard. Ported 1:1 from the reference corpus in the retired
// westland_share_guard.py self-test, plus fail-mode + path-normalizer cases.
//
// Run: node --test westland/hooks/g-drive-guard.test.mjs
//
// Fixtures inject a tmp dir as an extra Westland root so file-tool cases can use
// real on-disk paths without a real G:\ drive present — same trick the Python
// self-test used.

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  check,
  isShareModification,
  normalizeFsPath,
  addTestRoot,
  clearTestRoots,
} from './g-drive-guard.mjs';

// ---------------------------------------------------------------------------
// Fixtures
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'xer_hook_test_'));
const parent = path.dirname(tmp);

const record       = path.join(tmp, '2026-04-17 Project.xer');
const existing_v2  = path.join(tmp, '2026-04-17 Project-v2.xer');
const new_v3       = path.join(tmp, '2026-04-17 Project-v3.xer'); // not created
const new_other    = path.join(tmp, 'new-file.xer');             // not created
const existing_txt = path.join(tmp, 'notes.txt');
const existing_pdf = path.join(tmp, 'drawing.pdf');
const outside_xer  = path.join(parent, 'xer_hook_outside.xer');
const outside_txt  = path.join(parent, 'xer_hook_outside.txt');
const existing_html = path.join(tmp, 'report.html');
const existing_md   = path.join(tmp, 'notes.md');
const existing_json = path.join(tmp, 'config.json');

for (const f of [record, existing_v2, existing_txt, existing_pdf, outside_xer,
                 outside_txt, existing_html, existing_md, existing_json]) {
  fs.writeFileSync(f, 'X', 'utf8');
}

// Office fixtures for the age-lock: two stale (backdated 8 days), one fresh, one absent.
const office_old = path.join(tmp, 'Budget.xlsx');
const office_old_ppt = path.join(tmp, 'Deck.pptx');
const office_recent = path.join(tmp, 'Report.docx');
const office_new = path.join(tmp, 'BrandNew.xlsx'); // not created
fs.writeFileSync(office_old, 'X', 'utf8');
fs.writeFileSync(office_old_ppt, 'X', 'utf8');
fs.writeFileSync(office_recent, 'X', 'utf8');
const EIGHT_DAYS_AGO = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000);
fs.utimesSync(office_old, EIGHT_DAYS_AGO, EIGHT_DAYS_AGO);
fs.utimesSync(office_old_ppt, EIGHT_DAYS_AGO, EIGHT_DAYS_AGO);

addTestRoot(tmp);

after(() => {
  clearTestRoots();
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.rmSync(outside_xer, { force: true });
  fs.rmSync(outside_txt, { force: true });
});

// ---------------------------------------------------------------------------
// Decision cases — {label, tool, input, expected decision}
const cases = [
  // Rule 2 — versioned-type (inside Westland root)
  ['deny Edit on existing .xer record', 'Edit', { file_path: record }, 'deny'],
  ['deny Edit on existing -v2.xer', 'Edit', { file_path: existing_v2 }, 'deny'],
  ['deny MultiEdit on existing .xer', 'MultiEdit', { file_path: record }, 'deny'],
  ['deny Write overwriting existing .xer record', 'Write', { file_path: record }, 'deny'],
  ['deny Write overwriting existing -v2.xer', 'Write', { file_path: existing_v2 }, 'deny'],
  ['allow Write new -v3.xer', 'Write', { file_path: new_v3 }, 'allow'],
  ['allow Write brand-new .xer', 'Write', { file_path: new_other }, 'allow'],

  // Rule 1 — modify-prompt (inside root, non-versioned)
  ['ask on Edit existing .txt', 'Edit', { file_path: existing_txt }, 'ask'],
  ['ask on MultiEdit existing .txt', 'MultiEdit', { file_path: existing_txt }, 'ask'],
  ['ask on Write overwriting existing .txt', 'Write', { file_path: existing_txt }, 'ask'],
  ['ask on Edit existing .pdf (drawing)', 'Edit', { file_path: existing_pdf }, 'ask'],
  ['ask on Write overwriting existing .pdf', 'Write', { file_path: existing_pdf }, 'ask'],
  ['allow Write brand-new .txt', 'Write', { file_path: path.join(tmp, 'new.txt') }, 'allow'],
  ['allow Write brand-new .pdf', 'Write', { file_path: path.join(tmp, 'new.pdf') }, 'allow'],
  ['allow Edit with no file_path', 'Edit', {}, 'allow'],

  // Office file age-lock (records >7 days -> locked; recent -> ask; new -> allow)
  ['deny Edit on Office .xlsx older than 7d (locked record)', 'Edit', { file_path: office_old }, 'deny'],
  ['deny MultiEdit on Office .pptx older than 7d', 'MultiEdit', { file_path: office_old_ppt }, 'deny'],
  ['deny Write overwriting Office .xlsx older than 7d', 'Write', { file_path: office_old }, 'deny'],
  ['ask on Edit Office .docx modified within 7d', 'Edit', { file_path: office_recent }, 'ask'],
  ['ask on Write overwriting recent Office .docx', 'Write', { file_path: office_recent }, 'ask'],
  ['allow Write brand-new Office .xlsx', 'Write', { file_path: office_new }, 'allow'],
  ['allow Edit on Office .xlsx OUTSIDE share (age irrelevant)', 'Edit',
    { file_path: path.join(parent, 'outside-book.xlsx') }, 'allow'],

  // Allowlist — file tools on .html/.md/.json inside root
  ['allow Edit on existing .html', 'Edit', { file_path: existing_html }, 'allow'],
  ['allow Edit on existing .md', 'Edit', { file_path: existing_md }, 'allow'],
  ['allow Edit on existing .json', 'Edit', { file_path: existing_json }, 'allow'],
  ['allow MultiEdit on existing .md', 'MultiEdit', { file_path: existing_md }, 'allow'],
  ['allow Write overwriting existing .html', 'Write', { file_path: existing_html }, 'allow'],
  ['allow Write overwriting existing .json', 'Write', { file_path: existing_json }, 'allow'],
  ['allow Write brand-new .md', 'Write', { file_path: path.join(tmp, 'new.md') }, 'allow'],
  ['allow Edit on literal G:\\Westland Project Files .md', 'Edit',
    { file_path: 'G:\\Westland Project Files\\Job\\notes.md' }, 'allow'],
  ['allow Edit on UNC orem-fs Westland share .json', 'Edit',
    { file_path: '\\\\orem-fs\\Common\\Westland Project Files\\Job\\config.json' }, 'allow'],

  // Allowlist — delete commands on .html/.md/.json inside root
  ['allow rm of .md', 'Bash', { command: `rm -f '${existing_md}'` }, 'allow'],
  ['allow rm of .html', 'Bash', { command: `rm '${existing_html}'` }, 'allow'],
  ['allow Remove-Item of .json', 'PowerShell', { command: `Remove-Item '${existing_json}'` }, 'allow'],
  ['allow del of .html in literal G:\\Westland Project Files', 'Bash',
    { command: "del 'G:\\Westland Project Files\\Job\\report.html'" }, 'allow'],
  ['allow rm of two allowlisted (.md + .json)', 'Bash',
    { command: `rm '${existing_md}' '${existing_json}'` }, 'allow'],
  ['deny rm of mixed allowlisted + .xer', 'Bash',
    { command: `rm '${existing_md}' '${record}'` }, 'deny'],
  ['deny Remove-Item -Recurse of folder (no ext)', 'PowerShell',
    { command: `Remove-Item -Recurse '${tmp}/Job'` }, 'deny'],
  ['deny find -delete even with .md filter', 'Bash',
    { command: `find '${tmp}' -name '*.md' -delete` }, 'deny'],
  ['allow rm of unquoted MSYS-style /g/.../file.md', 'Bash',
    { command: 'rm -f /g/Westland Project Files/Job/notes.md' }, 'allow'],

  // File-tool — outside Westland root
  ['allow Edit on outside .xer', 'Edit', { file_path: outside_xer }, 'allow'],
  ['allow Write overwriting outside .xer', 'Write', { file_path: outside_xer }, 'allow'],
  ['allow Edit on outside .txt', 'Edit', { file_path: outside_txt }, 'allow'],
  ['allow Write overwriting outside .txt', 'Write', { file_path: outside_txt }, 'allow'],
  ['allow Edit on synthetic C:\\ path .xer (outside share)', 'Edit',
    { file_path: 'C:\\Temp\\hook-test-DELETE-ME.xer' }, 'allow'],

  // Rule 3 — delete (inside root)
  ['deny rm of file in root', 'Bash', { command: `rm -f '${record}'` }, 'deny'],
  ['deny rm of non-versioned file in root', 'Bash', { command: `rm '${existing_txt}'` }, 'deny'],
  ['deny Remove-Item of file in root (Bash tool)', 'Bash', { command: `Remove-Item '${record}'` }, 'deny'],
  ['deny cd into root then rm *.xer', 'Bash', { command: `cd '${tmp}' && rm -f *.xer` }, 'deny'],
  ['deny rmdir of folder in root', 'Bash', { command: `rmdir '${tmp}/Job'` }, 'deny'],
  ['deny find -delete in root', 'Bash', { command: `find '${tmp}' -name '*.bak' -delete` }, 'deny'],
  ['deny unlink of file in root', 'Bash', { command: `unlink '${record}'` }, 'deny'],

  // Rule 3 — mv to _Archive / _to_delete (allowed)
  ['allow mv into _Archive folder', 'Bash', { command: `mv '${record}' '${tmp}/_Archive/'` }, 'allow'],
  ['allow mv into _to_delete folder', 'Bash', { command: `mv '${record}' '${tmp}/_to_delete/'` }, 'allow'],

  // Bash — outside root (allowed)
  ['allow rm *.txt outside root', 'Bash', { command: 'rm -rf *.txt' }, 'allow'],
  ['allow ls *.xer', 'Bash', { command: 'ls *.xer' }, 'allow'],
  ['allow cat file.xer', 'Bash', { command: 'cat file.xer' }, 'allow'],
  ['allow rm of unrelated .xer outside root', 'Bash', { command: 'rm -f /tmp/scratch.xer' }, 'allow'],
  ['allow rm of stuck test file outside share', 'Bash',
    { command: "rm 'C:/Temp/hook-test-DELETE-ME.xer'" }, 'allow'],

  // Bash — heredoc / string-literal false-positive regression
  ['allow heredoc mentioning Remove-Item *.xer (unrelated)', 'Bash',
    { command: "cat << 'EOF'\nRemove-Item *.xer would bypass...\nEOF" }, 'allow'],
  ['allow command that merely mentions rm *.xer in a quoted string', 'Bash',
    { command: "echo 'beware: rm *.xer is destructive'" }, 'allow'],

  // Westland scope — literal G:\ and UNC paths
  ['deny Edit on G:\\Westland Project Files .xer', 'Edit',
    { file_path: 'G:\\Westland Project Files\\Job\\schedule.xer' }, 'deny'],
  ['ask on Edit .txt in G:\\Westland Project Files', 'Edit',
    { file_path: 'G:\\Westland Project Files\\Job\\notes.txt' }, 'ask'],
  ['deny rm of file in G:\\Westland Project Files', 'Bash',
    { command: "rm 'G:\\Westland Project Files\\Job\\old.xer'" }, 'deny'],
  ['deny rm of non-versioned file in G:\\Westland Project Files', 'Bash',
    { command: "rm 'G:\\Westland Project Files\\Job\\notes.txt'" }, 'deny'],
  ['deny Edit on UNC orem-fs Westland share', 'Edit',
    { file_path: '\\\\orem-fs\\Common\\Westland Project Files\\Job\\schedule.xer' }, 'deny'],
  ['deny Edit on UNC westland-local-dfs1 share', 'Edit',
    { file_path: '\\\\westland-local-dfs1\\Common\\Westland Project Files\\Job\\schedule.xer' }, 'deny'],
  ['allow Edit on .xer elsewhere on G:\\ (not Westland Project Files)', 'Edit',
    { file_path: 'G:\\Some Other Folder\\test.xer' }, 'allow'],
  ['allow Edit on .xer outside G:\\ entirely (D:\\)', 'Edit',
    { file_path: 'D:\\sandbox\\test.xer' }, 'allow'],

  // MSYS-style bash path regression
  ['deny rm with MSYS-style /g/ path', 'Bash',
    { command: "rm -f '/g/Westland Project Files/Job/old.xer'" }, 'deny'],
  ['deny Edit with MSYS-style /g/ path on file_path', 'Edit',
    { file_path: '/g/Westland Project Files/Job/schedule.xer' }, 'deny'],
  ['deny rm with MSYS-style //orem-fs UNC path', 'Bash',
    { command: "rm -f '//orem-fs/Common/Westland Project Files/Job/old.xer'" }, 'deny'],
  ['ask on Edit existing .txt via MSYS-style /g/ path', 'Edit',
    { file_path: '/g/Westland Project Files/Job/notes.txt' }, 'ask'],

  // PowerShell tool
  ['deny PowerShell Remove-Item of file in root', 'PowerShell', { command: `Remove-Item '${record}'` }, 'deny'],
  ['allow PowerShell rm of unrelated .xer', 'PowerShell',
    { command: "Remove-Item 'C:/Temp/hook-test-DELETE-ME.xer'" }, 'allow'],

  // Non-relevant tools pass through
  ['allow Bash with no command', 'Bash', {}, 'allow'],
  ['allow Read on .xer record (read is fine)', 'Read', { file_path: record }, 'allow'],
  ['allow Grep', 'Grep', { pattern: 'foo' }, 'allow'],
];

for (const [label, tool, input, expected] of cases) {
  test(label, () => {
    const [decision] = check(tool, input);
    assert.equal(decision, expected, `${label}: got '${decision}', want '${expected}'`);
  });
}

// ---------------------------------------------------------------------------
// Fail-mode classifier — isShareModification (drives the fail-closed deny)
test('isShareModification: Edit on share path → true', () => {
  assert.equal(isShareModification('Edit', { file_path: record }), true);
});
test('isShareModification: Write on share path → true', () => {
  assert.equal(isShareModification('Write', { file_path: existing_txt }), true);
});
test('isShareModification: Bash rm on share → true', () => {
  assert.equal(isShareModification('Bash', { command: `rm -f '${record}'` }), true);
});
test('isShareModification: Edit outside share → false', () => {
  assert.equal(isShareModification('Edit', { file_path: outside_xer }), false);
});
test('isShareModification: Read on share → false', () => {
  assert.equal(isShareModification('Read', { file_path: record }), false);
});
test('isShareModification: Bash non-delete (ls) on share → false', () => {
  assert.equal(isShareModification('Bash', { command: `ls '${tmp}'` }), false);
});

// ---------------------------------------------------------------------------
// Path normalizer — makes fs.existsSync reliable for overwrite detection
test('normalizeFsPath: MSYS /g/ → G:\\', () => {
  assert.equal(normalizeFsPath('/g/Westland Project Files/x.xer'),
    'G:\\Westland Project Files/x.xer');
});
test('normalizeFsPath: //server → \\\\server (UNC)', () => {
  assert.equal(normalizeFsPath('//orem-fs/Common/x.json'),
    '\\\\orem-fs/Common/x.json');
});
test('normalizeFsPath: native C:\\ unchanged', () => {
  assert.equal(normalizeFsPath('C:\\data\\reports\\x.txt'),
    'C:\\data\\reports\\x.txt');
});
