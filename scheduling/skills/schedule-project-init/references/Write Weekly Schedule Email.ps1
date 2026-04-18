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

Write-Host "Launching Claude Code with /write-weekly-schedule-email..." -ForegroundColor DarkGray
Write-Host "  claude: $claudePath" -ForegroundColor DarkGray
Write-Host "  folder: $PWD" -ForegroundColor DarkGray
Write-Host ""

& $claudePath --permission-mode auto '/write-weekly-schedule-email'
