# Scheduling hook runner -- locate a real Python install (skipping the
# Microsoft Store App Execution Alias stub at WindowsApps\python.exe)
# and invoke the named hook script under .\hooks\.
#
# Why this wrapper exists:
#   Windows ships a 0-byte python.exe stub at
#   %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe (the "Install from
#   Microsoft Store" alias). On Westland machines a real Python install
#   is present too, but PATH order at session-spawn time decides which
#   one a bare `python` invocation resolves to. Sessions launched from
#   File Explorer often hit the stub first; sessions launched from a
#   terminal with venv/uv on PATH hit the real Python first. That made
#   the previous bare `python -c "..."` hook spam every Read/Edit/Write
#   with a "Python was not found" error in roughly half of sessions.
#
#   Get-Command python.exe -All enumerates EVERY python.exe on PATH in
#   PATH order; filtering WindowsApps and taking the first match gives
#   the first REAL Python install regardless of stub ordering.
#
# Exit semantics:
#   - Real Python found -> invoke it with the hook script. Stdin (the
#     PreToolUse JSON envelope) flows through; stdout/stderr flow back
#     to Claude. Exit code is whatever python.exe returned.
#   - Real Python NOT found -> exit code 2. Surfaces as a blocking hook
#     failure so silent no-ops never mask the scheduling-plugin advisory
#     hooks (e.g. HTML discipline steers).

param([Parameter(Mandatory=$true)][string]$Script)

$py = Get-Command python.exe -All -ErrorAction SilentlyContinue |
      Where-Object { $_.Source -notmatch 'WindowsApps' } |
      Select-Object -First 1

if (-not $py) {
    [Console]::Error.WriteLine(
        'Scheduling hook: no real Python install found on PATH. ' +
        'Only the Microsoft Store App Execution Alias stub at ' +
        '%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe was located. ' +
        'Install Python (https://python.org) or contact IT, then reopen ' +
        'Claude Code so this scheduling hook can run.'
    )
    exit 2
}

& $py.Source (Join-Path $PSScriptRoot $Script)
exit $LASTEXITCODE
