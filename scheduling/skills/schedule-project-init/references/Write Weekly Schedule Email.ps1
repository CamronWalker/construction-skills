# Westland Construction — weekly schedule update email launcher.
#
# Invoked by "Write Weekly Schedule Email.bat" (double-clicked from the
# Schedules root). Runs in a fresh PowerShell window with -NoExit so the
# colleague sees session output and errors.
#
# This launcher is intentionally minimal: the only job is to start Claude
# Code in the Schedules folder and hand off to /write-weekly-schedule-email.
# All workflow details live in the scheduling plugin's schedule-update
# skill — so this file does not go stale when the workflow evolves.

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
    return
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host "  WESTLAND - WEEKLY SCHEDULE UPDATE EMAIL" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  claude: $claudePath" -ForegroundColor DarkGray
Write-Host "  folder: $PWD" -ForegroundColor DarkGray
Write-Host ""

# Minimal initial prompt: invoke the skill and provide an install-help
# fallback. The skill owns everything else (XER policy, MCP calls, seed
# build, cloud editor, .eml, Procore publish).
$initialPrompt = @'
Run /write-weekly-schedule-email.

If the command is not recognized, the scheduling plugin is not installed
on this machine. Guide me through installing the latest scheduling.zip
from Westland's enterprise plugin distribution, then re-run the command.
'@

& $claudePath --permission-mode auto $initialPrompt
