@echo off
REM Westland Construction — weekly schedule update email launcher.
REM
REM Double-click this file from the Schedules root to hand the week's update
REM off to Claude Code. Launches Claude Code CLI in auto mode with the
REM /write-weekly-schedule-email slash command queued — a colleague doesn't
REM need to know Cowork, Claude Code, or slash commands.
REM
REM Implementation mirrors the Iris task-watcher agent launcher pattern:
REM   - PowerShell, not Git bash ("No bash, no MSYS2 DLL issues.")
REM   - -NoExit keeps the window open so colleagues see the session / errors
REM   - Clears inherited $env:PROMPT / CLAUDECODE / CLAUDE_CODE_ENTRYPOINT
REM     so a parent Claude session's state can't leak into this one
REM   - Set-Location '%~dp0' points CWD at this script's folder (the
REM     Schedules root, next to project-context.html)
REM   - --permission-mode auto = autonomous session with permission boundaries
REM
REM First-run check: if the Claude Code CLI isn't on PATH, prints an install
REM link and stops instead of flashing away.
REM
REM Prereqs (not installed by this script — one-time per machine):
REM   - Claude Code CLI: https://claude.com/claude-code
REM   - Playwright MCP: enable in the CLI so SmartPM screenshots work
REM   - Classic Outlook: open and signed in for the email draft step

powershell -ExecutionPolicy Bypass -NoExit -Command "$env:PROMPT=$null; $env:CLAUDECODE=$null; $env:CLAUDE_CODE_ENTRYPOINT=$null; Set-Location '%~dp0'; if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { Write-Host ''; Write-Host 'ERROR: Claude Code CLI not found on PATH.' -ForegroundColor Red; Write-Host 'Install from https://claude.com/claude-code and re-run this launcher.'; Write-Host ''; return }; claude --permission-mode auto '/write-weekly-schedule-email'"
