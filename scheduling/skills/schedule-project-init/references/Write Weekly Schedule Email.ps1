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

# Red pre-launch banner. Visible only until Claude's TUI takes over the
# screen, but useful for colleagues who are watching during startup.
Write-Host ""
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host "  WESTLAND — WEEKLY SCHEDULE UPDATE EMAIL" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  XER POLICY: Read any .xer freely. If schedule changes are" -ForegroundColor Red
Write-Host "  needed, write a NEW versioned file (e.g. '...-v2.xer') —" -ForegroundColor Red
Write-Host "  NEVER edit or overwrite the original master XER." -ForegroundColor Red
Write-Host ""
Write-Host "  claude: $claudePath" -ForegroundColor DarkGray
Write-Host "  folder: $PWD" -ForegroundColor DarkGray
Write-Host ""

# Rich initial prompt — this is what Claude sees as its first user message.
# Lives in Claude's context regardless of whether the scheduling plugin is
# installed, so the XER policy and the install-help path reach the session
# even on first-run / uninstalled-plugin scenarios where the slash command's
# own content can't load.
$initialPrompt = @"
# Weekly Schedule Update Email — launch prompt

## Who you are

You are a Claude Code agent working on behalf of Westland Construction,
helping a colleague complete a weekly project schedule update email. You
were invoked by a double-click .bat launcher sitting at the Schedules
root of a specific project.

## What this workflow is

Westland runs a weekly schedule update cycle for every active construction
project. Each week the team meets, updates the project schedule, exports
a new XER, uploads it to SmartPM, and sends a stakeholder email
summarizing progress, risks, and upcoming key items — plus attachments
(PDFs, Excel reports) and embedded SmartPM trend graphs.

Steps 1-5 of that cycle are the human's job (update the schedule, export,
upload to SmartPM, drop the transcript, create next week's Excel files).
**Your job is steps 6-10**: capture SmartPM graphs, draft the email,
produce an editable HTML preview for the colleague to review, and create
the Outlook draft on approval.

The full workflow lives in the **scheduling plugin's
`/write-weekly-schedule-email` slash command**. That command routes into
the `schedule-update` skill's `report` flow, which owns the details
(SmartPM screenshot capture via Playwright MCP, XER parsing, transcript
mining, HTML preview generation, carry-forward state from last week,
Outlook COM draft).

## Absolute rule — XER file handling

The ``.xer`` files in this folder tree are **master historical records**
of the project's schedule evolution. They are the source of truth for
claims, delay analysis, and contract disputes. You must never
accidentally corrupt or overwrite them.

Policy — what you can and cannot do:

- **READ** any ``.xer`` file freely. Parsing for analysis, metrics,
  comparisons against last week — all fine.
- **WRITE** new ``.xer`` files only with a **version suffix**
  (e.g., ``2026-04-17 NTVS ACME-v2.xer``,
  ``2026-04-17 NTVS ACME-working.xer``) alongside the original. These
  are *your* working copies.
- **EDIT** only the working copies you created in this session. Never
  edit an existing master XER.
- **DELETE** no ``.xer`` file, ever.

This rule overrides any tool call you might consider making that
conflicts with it. If a step seems to require editing a master XER,
stop and ask the colleague — you've misunderstood the workflow.

## How to start

Run the ``/write-weekly-schedule-email`` slash command. It will read
``project-context.html``, verify preflights (Playwright MCP, today's
dated folder), and walk the colleague through the guided flow.

## If the slash command is not recognized

If you get ``Unknown command: /write-weekly-schedule-email``, the
**scheduling plugin is not installed** on this machine. Help the
colleague get it installed — do not attempt the workflow manually
(XER parsing, SmartPM automation, email template, carry-forward logic,
and Outlook COM draft all live in the plugin code; hand-rolling them
will produce a broken result).

To install:

1. **Locate the plugin zip.** Ask the colleague whether they have the
   latest ``scheduling.zip`` from Westland's enterprise plugin
   distribution. Common places: Downloads folder, a shared drive,
   an email from Camron. If they don't have it, tell them to contact
   Camron — he maintains the distribution.
2. **Install via the CLI.** Once they have the path, run (or guide them
   through) the appropriate Claude Code plugin-install command for
   enterprise zips. Ask the colleague to confirm the zip path, then
   execute the install and verify the plugin loaded by re-trying
   ``/write-weekly-schedule-email``.
3. **Re-launch.** After install, either re-run this launcher (close this
   window and double-click the .bat again) or type the slash command
   directly in this session.

Be helpful and concrete during the install — this is a colleague's first
encounter with Claude Code, and a smooth install is the difference
between them trusting the tool and abandoning it.

## Starting context

- **CWD**: the Schedules root folder — should contain ``project-context.html``
  and one or more ``YYYY-MM-DD/`` dated subfolders. Today's dated folder
  should exist and already have the week's XER + PDFs + (optional)
  meeting transcript dropped in.
- **Project grandparent**: folder name matching ``W\d+ - .+``
  (e.g., ``W1134 - Neiafu Tonga Temple Construction``).
- **Permission mode**: ``auto`` — you're expected to execute autonomously
  and minimize interruptions, but still ask before destructive or
  hard-to-reverse actions.

Go.
"@

& $claudePath --permission-mode auto $initialPrompt
