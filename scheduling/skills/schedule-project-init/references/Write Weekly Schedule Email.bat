@echo off
REM Westland Construction — weekly schedule update email launcher (thin wrapper).
REM
REM Double-click from the Schedules root. Spawns a new PowerShell window and
REM runs "Write Weekly Schedule Email.ps1" sitting next to this .bat. The
REM logic lives in the .ps1 so the cmd quoting stays simple.
REM
REM Uses `start` (not inline) so the PowerShell window is its own process —
REM the cmd shim exits immediately after launch instead of hosting PowerShell
REM inside a cmd window.

start "Weekly Schedule Email" powershell -ExecutionPolicy Bypass -NoExit -File "%~dp0Write Weekly Schedule Email.ps1"
