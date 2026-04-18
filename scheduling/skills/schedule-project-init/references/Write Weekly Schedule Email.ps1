# Westland Construction — weekly schedule update email launcher.
#
# Invoked by "Write Weekly Schedule Email.bat" (double-clicked from the
# Schedules root). Runs in a fresh PowerShell window with -NoExit so the
# colleague sees session output and errors.
#
# Implementation notes (mirrors the Iris task-watcher agent launcher):
#   - Clear inherited Claude env vars so a parent Claude session's state
#     can't leak into this one.
#   - Set-Location $PSScriptRoot — this script lives next to project-context.html
#     at the Schedules root, which is the folder /write-weekly-schedule-email expects.
#   - --permission-mode auto keeps the session autonomous while still
#     respecting permission boundaries.
#
# Robust `claude` discovery: on some machines the installer adds the full
# exe path (not its folder) to PATH, which breaks `Get-Command`. We fall
# back to a list of known install locations before giving up.

$env:PROMPT = $null
$env:CLAUDECODE = $null
$env:CLAUDE_CODE_ENTRYPOINT = $null

Set-Location $PSScriptRoot

function Find-ClaudeCli {
    $fromPath = Get-Command claude -ErrorAction SilentlyContinue
    if ($fromPath) { return $fromPath.Source }

    $candidates = @(
        "$env:USERPROFILE\.local\bin\claude.exe",
        "$env:LOCALAPPDATA\Programs\claude-code\claude.exe",
        "$env:LOCALAPPDATA\Programs\claude\claude.exe",
        "$env:APPDATA\npm\claude.cmd",
        "$env:APPDATA\npm\claude.exe",
        "$env:ProgramFiles\Claude\claude.exe",
        "${env:ProgramFiles(x86)}\Claude\claude.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

$claudePath = Find-ClaudeCli

if (-not $claudePath) {
    Write-Host ""
    Write-Host "ERROR: Claude Code CLI not found." -ForegroundColor Red
    Write-Host "Install from https://claude.com/claude-code and re-run this launcher."
    Write-Host ""
    Write-Host "Checked: PATH and these common locations:" -ForegroundColor DarkGray
    Write-Host "  $env:USERPROFILE\.local\bin\claude.exe" -ForegroundColor DarkGray
    Write-Host "  $env:LOCALAPPDATA\Programs\claude-code\claude.exe" -ForegroundColor DarkGray
    Write-Host "  $env:APPDATA\npm\claude.cmd" -ForegroundColor DarkGray
    Write-Host ""
    return
}

# Safety banner — printed BEFORE Claude clears the screen, but also queued
# into the initial prompt below so Claude sees it even after the TUI takes over.
Write-Host ""
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host "  WESTLAND — WEEKLY SCHEDULE UPDATE EMAIL" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  ABSOLUTE RULE: .XER FILES ARE READ-ONLY MASTER RECORDS." -ForegroundColor Red
Write-Host "  Never edit or overwrite an existing .xer file in place." -ForegroundColor Red
Write-Host "  Save modified/regenerated XERs as NEW files with a version" -ForegroundColor Red
Write-Host "  suffix (e.g., '2026-04-17 NTVS ACME-v2.xer')." -ForegroundColor Red
Write-Host ""
Write-Host "  claude: $claudePath" -ForegroundColor DarkGray
Write-Host "  folder: $PWD" -ForegroundColor DarkGray
Write-Host ""

# Initial prompt — used instead of the bare slash command so we can:
#   1. Restate the XER safety rule in Claude's context (critical if the
#      scheduling plugin isn't installed and the command file doesn't load).
#   2. Give Claude a clear fallback: install instructions if the plugin
#      isn't available. A bare "/write-weekly-schedule-email" on an
#      uninstalled plugin just returns "Unknown command" and waits.
#   3. Trigger the slash command on the happy path — if the plugin is
#      installed, Claude will read the command's content (which also
#      carries the safety rules) and execute the report flow.
$initialPrompt = @"
WESTLAND WEEKLY SCHEDULE UPDATE EMAIL — LAUNCHED VIA DOUBLE-CLICK .BAT

ABSOLUTE SAFETY RULE — XER FILES ARE READ-ONLY:

The .xer files in this folder and its subfolders are MASTER HISTORICAL
RECORDS of the project schedule. NEVER edit, overwrite, resave, or
``clean up'' an existing .xer in place under any circumstances. This
is non-negotiable — our historical record of the project's schedule
evolution must not be accidentally modified.

If the workflow needs a modified, regenerated, or repaired XER, write
it as a NEW file with a version suffix alongside the original:
  original: ``2026-04-17 NTVS ACME.xer''
  new:     ``2026-04-17 NTVS ACME-v2.xer''

This rule applies to every kind of write: edits, format conversions,
auto-fixes, cleanup, tool output. Always-new-file, never-in-place.

TASK:

Run the /write-weekly-schedule-email slash command to start the weekly
update email flow (steps 6-10 of the Westland weekly update pipeline).

If the slash command returns ``Unknown command: /write-weekly-schedule-email'',
the scheduling plugin is not installed on this machine. In that case:
  1. Tell the colleague the plugin needs to be installed.
  2. Ask them to contact Camron for the latest ``scheduling.zip'' from
     the enterprise plugin distribution.
  3. After it's installed, they can re-run this launcher or type the
     slash command themselves.
  Do NOT attempt the email workflow manually without the plugin — the
  plugin contains the proper XER parsing, email template, SmartPM
  screenshot automation, and Outlook draft logic.

Starting context: CWD should be the Schedules root (next to
project-context.html). Today's YYYY-MM-DD dated folder should already
exist — steps 1-5 of the weekly update are done by the human.
"@

& $claudePath --permission-mode auto $initialPrompt
