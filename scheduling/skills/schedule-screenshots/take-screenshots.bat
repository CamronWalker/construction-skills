@echo off
REM ============================================================================
REM  SmartPM Screenshot Capture
REM  Westland Construction — Schedule Update Pipeline
REM
REM  Place this file in any schedule update project folder and double-click.
REM  It launches Claude Code to capture SmartPM screenshots via Playwright.
REM
REM  First run: A Chromium browser opens — log in to SmartPM. Your session
REM  is saved so you won't need to log in again on future runs.
REM
REM  Prerequisites:
REM    - Node.js must be installed
REM    - Claude Code CLI must be available in PATH
REM ============================================================================

echo.
echo  ============================================
echo   SmartPM Screenshot Capture
echo   Westland Construction
echo  ============================================
echo.

REM Change to the directory where this bat file lives (the project folder)
cd /d "%~dp0"
echo  Project folder: %cd%
echo.

claude "Use the schedule-screenshots skill to capture all SmartPM screenshots for the project in this folder. Read the project-memory file for the SmartPM URL, or ask me for it if there isn't one. Save screenshots to ./screenshots/."

echo.
echo  ============================================
echo   Done. Check the screenshots\ folder.
echo  ============================================
echo.
pause
