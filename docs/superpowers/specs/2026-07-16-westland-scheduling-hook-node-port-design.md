# Westland + scheduling PreToolUse hooks — Node port / cleanup

**Date:** 2026-07-16
**Plugins:** `westland` (1.6.4 → 1.8.0), `scheduling` (10.0.1 → 10.1.0)
**Branch:** `claude/westland-plugin-hook-fix-f303cf`

## Problem

The same fragile launcher pattern is copied across three PreToolUse hooks (one in
`westland`, two in `scheduling`):

```
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r=$env:CLAUDE_PLUGIN_ROOT; … & \"$r/hooks/run-hook.ps1\" <script>; exit $LASTEXITCODE"
```

Three failures stack up:

1. **Broken command / lingering window.** The command wraps PowerShell in
   escaped quotes (`\"…\"`) and is then run through another shell. In the
   observed environment the hook runs under an msys/bash-style shell (paths
   arrive as `/c/Users/...`; that is what the `$r -match '^/([a-zA-Z])/…'`
   rewrite exists to handle). The nested quoting mangles, PowerShell receives a
   broken `-Command`, and drops into **interactive mode** — the "empty command
   prompt that opens up and stays." It also errors `At line:1 char:68` on every
   matched tool call.
2. **Windows/Python only.** `powershell`, `run-hook.ps1`, and `python.exe` do
   not exist in Cowork's Linux sandbox, so there the hook can only error.
3. **Backwards fail mode.** `run-hook.ps1` exits 2 (blocks *every* Edit/Write/Bash)
   when it can't find a real Python — the opposite of the intended "invisible
   unless it's the Westland share" behavior.

The `Read`/`Grep` error spam the user sees comes from the **scheduling** plugin's
second hook (matcher `Read|Edit|Write|MultiEdit|NotebookEdit|Glob|Grep`): the
broken launcher fires on nearly every tool call and errors *before* the Python
guard runs.

Root cause confirmed empirically:
- `node` is present (v22) and Claude Code ships it; it is the one guaranteed
  cross-platform runtime.
- `node "<path>"` resolves msys `/c/...`, Windows `C:\...`, and Linux paths
  identically, and pipes the stdin JSON envelope correctly.
- A `node "<script>"` hook command has **no nested quotes** for a second shell
  to mangle — which removes the char-68 error and the interactive-window fallback.

## Decisions (from brainstorming)

- **Real users are all on Windows**; the hook must additionally *survive* Cowork's
  Linux sandbox (no error, no window) rather than support Mac/Linux users.
- **Keep** westland's delete protection (Rule 3) — matcher continues to include
  `Bash|PowerShell`.
- **On the Westland share: fail closed for modifications, fail open for new
  files.** The share holds corporate records, so the guard defaults to
  *protective* there — a modification of an existing file (Edit / MultiEdit /
  NotebookEdit, a Write that overwrites, or a delete) that the guard cannot
  evaluate cleanly is **denied** ("blocked for safety — file a bug"), never
  silently allowed. The user's explicit priority: *"I'd rather get bug issues
  than it failing open and editing files we didn't want."* A **brand-new file**
  Write on the share, any path **outside the share**, and the entire **Linux
  sandbox** fail *open* (silent allow) — new content and non-share work must
  never block colleagues. The one residual fail-open is unparseable stdin (a
  rare plumbing failure with no tool/path to classify; blocking there would
  block all work, reintroducing the "block everyone" pain).
- **Rule table is unchanged from the current Python guard** (confirmed during
  review): working artifacts `.html`/`.md`/`.json` → allow; records `.xer` →
  deny (write `-vN` alongside); every other existing file on the share → **ask**
  (human approval retained); new files of any type → allow. This is a faithful
  behavior-preserving port — only the *plumbing* (Node vs PowerShell+Python) and
  the *fail path* (below) change.
- **Drop both scheduling hooks entirely.** They are advisory-only (never block):
  `check_lib_fence` nudges toward MCP tools; `check_html_discipline` nudges away
  from a retired, migrated `project-context.html`. The MCP-first guidance already
  lives in `scheduling/CLAUDE.md`; the retired-html concern is fading. Scheduling
  ships **no** PreToolUse hook after this change.

## Goals / Non-goals

**Goals**
- Eliminate the lingering empty-prompt window and the char-68 error spam.
- One clean hook command that works on the Windows host and the Linux sandbox.
- Remove the Python + PowerShell dependency chain.
- Preserve westland's guard behavior exactly (rules 1–3, allowlist, share scope).

**Non-goals**
- Mac/Linux *users* / share enforcement on non-Windows mounts.
- Fully eliminating the *brief* subprocess-window flash on the Cowork desktop
  app — that is an upstream Claude Code limitation (it does not set
  `windowsHide`/`CREATE_NO_WINDOW` when spawning hooks;
  <https://github.com/anthropics/claude-code/issues/66540>). Documented, not fixed here.

## Design

### 1. westland — port the guard to Node

**New file:** `westland/hooks/g-drive-guard.mjs` — a behavior-identical port of
`westland_share_guard.py`, written as an importable ES module plus a CLI entry.
(Named for its everyday job — guarding the G drive. A header comment notes the
"G drive" also covers the two UNC mirrors and the msys `/g/` form: same share,
different access paths.)

Behavior to preserve exactly (see the Python source for the reference table):

- **Dispatch (`check`):** `Bash`/`PowerShell` → delete rule only; `Edit`/`Write`/
  `MultiEdit`/`NotebookEdit` → file rules; any other tool → allow.
- **File rules (`check_file_tool`):**
  1. no `file_path`/`notebook_path` → allow
  2. not under a Westland root → allow
  3. allowlisted ext (`.html`/`.md`/`.json`) → allow
  4. versioned ext (`.xer`): Edit/MultiEdit/NotebookEdit → **deny**; Write →
     **deny if the target exists**, else allow (new `-vN.xer` is the intended path)
  5. otherwise (non-versioned, in share): Edit/MultiEdit/NotebookEdit → **ask**;
     Write → **ask if the target exists**, else allow
- **Delete rule (`check_bash`):** no command → allow; command not touching a
  Westland root → allow; not a delete verb → allow; delete whose targets are
  *all* allowlisted ext → allow; otherwise → **deny**.
- **Westland roots (substring, case-insensitive, `/`→`\` normalized):**
  `G:\Westland Project Files`, `\\orem-fs\Common\Westland Project Files`,
  `\\westland-local-dfs1\Common\Westland Project Files`, `/g/Westland Project Files`.
- **Delete verbs:** `rm [-flags] <arg>`, `del`/`erase <arg>`,
  `Remove-Item`/`rmdir <arg>`, `unlink <arg>`, `find … -delete`.
- **Allowlisted-delete enumeration (`_delete_targets_all_allowed_ext`):**
  `find … -delete` → not enumerable → keep deny; collect quoted paths and
  unquoted drive/slash tokens ending in `.ext`; no targets → keep deny; all
  targets allowlisted → allow.
- **Deny/ask messages:** ported verbatim (versioned-edit, versioned-overwrite,
  delete, modify-ask), including the emoji and `{tool}/{name}/{stem}/{ext}/{path}/{command}`
  substitutions.
- **Output:** allow → no stdout, exit 0. deny/ask → print
  `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":…,"permissionDecisionReason":…}}`
  to stdout, exit 0. Invalid stdin JSON → stderr diagnostic, exit 0 (fail open).
- **Guard-error fail mode (try/catch around evaluation):** an unexpected error
  while evaluating a **share modification** — a file-modify tool
  (Edit/MultiEdit/NotebookEdit, or a Write that isn't confirmed-new) or a delete
  verb whose target is under a Westland root — returns **deny** (fail closed)
  with a "guard error — blocked for safety, file a westland-bug-report" reason.
  An unexpected error in any other case → exit 0 (fail open).

**Path parsing:** use `node:path`'s `win32` variants (`path.win32.extname/basename`)
so `\`, `/`, drive-letter, and UNC forms parse the same regardless of the OS Node
runs on — matching Python's `WindowsPath` semantics. **Write overwrite detection**
normalizes drive/UNC forms (`/g/…`→`G:\…`, `//server`→`\\server`) before
`fs.existsSync`, so on the Windows host a share Write is treated as *new* (allow)
only when the file is confirmed absent; if it exists — or existence cannot be
confirmed for a share path — it is treated as an **overwrite** (ask for
non-versioned, **deny** for `.xer`). This closes the latent msys fail-open where
an unresolved `/g/` path made a share overwrite look like a brand-new file.

**Testability:** the module exposes the extra-root injection the Python
`self_test` relied on (append a tmp dir to the roots list) so tests can exercise
real on-disk paths without a `G:\` drive.

**hooks.json** — replace the command, keep the matcher:

```json
{
  "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell",
  "hooks": [{ "type": "command", "command": "node \"${CLAUDE_PLUGIN_ROOT}/hooks/g-drive-guard.mjs\"" }]
}
```

Update the hooks.json `description` to drop the run-hook.ps1 / Python-missing
language and note the Node runner + the known upstream Windows flash limitation.

**Delete:** `westland/hooks/run-hook.ps1`, `westland/hooks/westland_share_guard.py`.

### 1b. Office file age-lock (added during review; westland → 1.8.0)

Microsoft Office files (`.xlsx/.xlsm/.xlsb/.xls/.docx/.docm/.doc/.dotx/.pptx/.pptm/.ppt`)
split into two populations: live working docs (edit freely) and settled project
records (should never change once final). Use **last-modified age** as the proxy,
gated wherever the hook can see the path:

- **new file (ENOENT)** → allow
- **exists, modified within 7 days** → **ask** (live working doc — confirm the overwrite)
- **exists, not modified in >7 days** → **deny** (settled record — locked). To unlock,
  open/save it manually (bumps mtime into the 7-day window → drops back to "ask"),
  or write a versioned copy. This is the user's "make a manual change first" mechanic.
- **can't stat for any reason other than ENOENT** → **deny** (fail closed — record protection).

Age is `Date.now() - stat.mtimeMs` (both available in a normal Node process); the
path is normalized (`/g/`→`G:\`, `//server`→`\\server`) before `statSync`.

**Coverage — the hook sees the extension only when a path is present:**

- **Row 1 — file tools (`Edit/Write/MultiEdit/NotebookEdit`):** path is in the
  envelope → always age-gated. (Rarely fires in practice: binary Office files are
  written by scripts, not the text Write tool — so no workflow friction.)
- **Row 3 — Bash/PowerShell with a path on the command line:** *Considered and
  declined.* A write-intent sniff (`>`/`cp`/`Copy-Item`/`Out-File`…) could gate
  Office paths that appear literally on the command line, but the yield is thin
  (the common write path is row 2, not command-line copies) and the heuristic
  adds false-positive surface (read-with-redirect, cp-source, the `_Archive`
  exception). Not built; the standing instruction below covers it instead.
- **Row 2 — path baked inside a script (`python make_report.py`):** NOT reachable
  by the hook — it receives no path/extension. This is the KPI-workbook /
  monthly-report write path.

**Row 2/3 cover — standing instruction (soft, universal, zero friction).** Since
the hook can't see script writes, the row-2/3 protection is documentation, the
idiomatic "don't edit this" mechanism (Claude reads it and follows by
convention):
- one line in `westland/ORG_PREFERENCES.md` (the claude.ai Organization
  Preferences — read on every response for all Westland users; must be pasted
  live into claude.ai to take effect), next to the existing `.xer` rule;
- depth in the `westland-house-style` skill (what counts as "settled," the
  version-over-overwrite convention, and the explicit note that script-written
  Office files are the hook's blind spot so the convention is their protection).

If a record must be *truly* unclobberable (hard + universal), the only options
are filesystem read-only/deny-write ACLs or version-history/backup recoverability
— out of scope here, noted for the user.

"Created by *this session*" is not detectable from a stateless PreToolUse process,
so recent-modification (<7 days) is the proxy — and recent still resolves to
**ask**, not a free auto-allow, so even a fresh record isn't silently overwritten.

### 2. scheduling — remove both hooks

- Delete `scheduling/hooks/` entirely: `hooks.json`, `run-hook.ps1`,
  `check_html_discipline.py`, `check_lib_fence.py`, and `hooks/tests/`
  (`__init__.py`, `test_check_html_discipline.py`, `test_check_lib_fence.py`).
- **Doc cleanup — `westland-scheduler-mcp-troubleshoot` skill:** the
  "worktree-with-hook-disabled" curator workflow (SKILL.md description line ~11
  and the "Editing lib/ (curator role)" section ~lines 61–72; `diagnose.py:234`)
  only exists because of the lib-fence. Rewrite it: there is no fence to disable;
  editing `schedule-toolbox/lib/*.py` is done directly, with MCP-first still the
  convention for *using* the toolbox. Remove references to `check_lib_fence.py`,
  `--no-hooks`, and "restore the hook on main."

### 3. Rollout (release convention)

- **westland** `plugin.json` 1.6.4 → **1.8.0** (main reached 1.7.0 via #54 after
  this branched, so this lands at 1.8.0; minor: adds the Office record
  age-lock + the standing Office-record instruction); matching `marketplace.json`
  entry to 1.8.0 (lockstep). **Manual step:** paste the updated
  `ORG_PREFERENCES.md` body into claude.ai → Settings → Organization preferences
  for the standing Office-record rule to take effect for everyone.
- **scheduling** `plugin.json` 10.0.1 → **10.1.0**; matching `marketplace.json`
  entry to 10.1.0 (lockstep). Minor: removing a hook is a behavior change.
- One commit with both plugins' changes. CI `version-bump` gate is satisfied
  (both changed plugins bumped, strictly greater, plugin==marketplace).
  `forbid-personal-paths` is satisfied (no `C:\Users\<name>\` in code;
  `g-drive-guard.mjs` uses the same share-root constants, and tests use `os.tmpdir()`).
- Distribution: after merge, `git switch main && git pull --ff-only` in the
  **main checkout** (not this worktree), `python build.py westland scheduling`,
  upload the rebuilt zips. Marketplace bump covers direct-from-repo installs. No
  local `managed-settings.json` exists — the fix lives entirely in plugin source.

## Testing

- **westland:** `westland/hooks/g-drive-guard.test.mjs`, run with `node --test westland/hooks/`.
  Port every case from the Python `self_test` (rules 1–3, allowlist file + delete
  cases, outside-root regressions, heredoc/string-literal false-positives, literal
  `G:\`/UNC/msys `/g/` paths, PowerShell cases, non-relevant-tool passthrough).
  Each case asserts the `check()` decision equals the expected `allow`/`deny`/`ask`.
- **Fail-mode cases:** share Write to a confirmed-new file → allow; share Write
  to an existing file (normalized) → ask (deny for `.xer`); a simulated guard
  error on a share modification → **deny**; a simulated guard error outside the
  share → allow. Exercise the classification helper directly so the error path
  is covered without having to force a real throw.
- **End-to-end smoke:** pipe a sample PreToolUse envelope into
  `node westland/hooks/g-drive-guard.mjs` and confirm: a share `.xer` Edit → deny JSON on
  stdout, exit 0; an outside-root Edit → no stdout, exit 0; malformed stdin →
  stderr diagnostic, exit 0.
- **scheduling:** confirm `scheduling/hooks/` is gone and the plugin loads with no
  PreToolUse hook; confirm the troubleshoot skill no longer references the fence.

## Risks

- **`node` not on PATH in some hook environment.** Mitigated: Node ships with
  Claude Code and is confirmed present (v22). If ever absent, the hook fails
  open (tool proceeds) — no block, no window — which is the desired safe default.
- **Residual window flash on Cowork desktop.** Upstream Claude Code limitation
  (no `windowsHide`); minimized by dropping the powershell→python spawn chain to a
  single `node` spawn. Documented in the hooks.json description.
- **Write overwrite detection on the share.** Addressed in the design: drive/UNC
  forms are normalized before `fs.existsSync`, and any share Write whose absence
  cannot be confirmed is treated as an overwrite (ask / deny), never allowed — so
  an unresolved path can never fail open into overwriting a corporate record.
