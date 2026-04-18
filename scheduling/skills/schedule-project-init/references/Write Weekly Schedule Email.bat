@echo off
REM Westland Construction — weekly schedule update email launcher.
REM Double-click this file from the Schedules root to hand the week's update
REM off to Claude Code. The script cd's to its own folder (so Claude sees
REM project-context.html) and queues the /write-weekly-schedule-email slash
REM command with permissions auto-accepted for the session.
REM
REM Prereqs (checked by the skill, not here):
REM   - Claude Code CLI installed and on PATH (https://claude.com/claude-code)
REM   - Node.js installed (for SmartPM screenshot capture via Playwright)
REM   - Classic Outlook installed and signed in (for the Outlook draft step)
REM
REM If Claude Code is missing, the `claude` call will fail — install it from
REM the link above and re-run.

cd /d "%~dp0"
claude --permission-mode auto "/write-weekly-schedule-email"
