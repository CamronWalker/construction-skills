# westland-scheduler-mcp launcher -- locate a real Python install
# (skipping the Microsoft Store App Execution Alias stub at
# WindowsApps\python.exe) and exec the MCP server script with stdio
# piping intact for MCP protocol traffic.
#
# Why this wrapper exists:
#   See ..\..\hooks\run-hook.ps1 for the full rationale. Same root cause:
#   a 0-byte Microsoft Store python.exe alias may sit in front of the
#   real Python on PATH, and a bare `python` invocation in the MCP
#   server config would fail to start the server on those sessions.
#
# Exit semantics:
#   - Real Python found -> exec it with server.py. Stdin/stdout flow
#     through for MCP traffic; stderr surfaces in Claude Code's MCP log.
#     Process exits with whatever python.exe returned.
#   - Real Python NOT found -> exit 2 with a clear message. Claude Code
#     will log the MCP server as failed-to-start with the message
#     visible, prompting the user to install Python.

$py = Get-Command python.exe -All -ErrorAction SilentlyContinue |
      Where-Object { $_.Source -notmatch 'WindowsApps' } |
      Select-Object -First 1

if (-not $py) {
    [Console]::Error.WriteLine(
        'westland-scheduler-mcp: no real Python install found on PATH. ' +
        'Only the Microsoft Store App Execution Alias stub at ' +
        '%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe was located. ' +
        'Install Python (https://python.org) or contact IT, then restart ' +
        'Claude Code so the MCP server can launch.'
    )
    exit 2
}

& $py.Source (Join-Path $PSScriptRoot 'server.py')
exit $LASTEXITCODE
