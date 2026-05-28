<#
.SYNOPSIS
  Sweep Westland project Schedules folders for stale schedule-update
  launchers and rewrite them to the current minimal form.

.DESCRIPTION
  Walks $ProjectsRoot (default: G:\Common\Westland Project Files) and
  finds existing launcher copies:

    - "Write Weekly Schedule Email.bat"
    - "Write Weekly Schedule Email.ps1"
    - "take-screenshots.bat"   (retired in scheduling 8.2.0; deleted)

  For each, compares against the canonical templates in this repo at
    scheduling/skills/schedule-project-init/references/
  Files that differ from canonical are replaced (and optionally backed
  up). The retired take-screenshots.bat is deleted entirely.

  Run with -DryRun first to see what would change.

.EXAMPLE
  .\scripts\update-westland-schedule-launchers.ps1 -DryRun

.EXAMPLE
  .\scripts\update-westland-schedule-launchers.ps1 -Backup

.PARAMETER ProjectsRoot
  Root of the Westland project files share.

.PARAMETER RepoRoot
  Path to this construction-skills repo. Defaults to the parent of this
  script's directory.

.PARAMETER DryRun
  List what would change without modifying any files.

.PARAMETER Backup
  Save .bak copies before replacing or deleting.
#>

[CmdletBinding()]
param(
    [string]$ProjectsRoot = 'G:\Common\Westland Project Files',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$DryRun,
    [switch]$Backup
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $ProjectsRoot)) {
    Write-Error "ProjectsRoot not reachable: $ProjectsRoot. Pass -ProjectsRoot to override."
    return
}

$templateDir = Join-Path $RepoRoot 'scheduling\skills\schedule-project-init\references'
$templateBat = Join-Path $templateDir 'Write Weekly Schedule Email.bat'
$templatePs1 = Join-Path $templateDir 'Write Weekly Schedule Email.ps1'

foreach ($t in @($templateBat, $templatePs1)) {
    if (-not (Test-Path $t)) {
        Write-Error "Canonical template missing: $t. Pass -RepoRoot to override."
        return
    }
}

# Read canonical content; normalize to LF for comparison.
$canonicalBat = (Get-Content $templateBat -Raw) -replace "`r`n", "`n"
$canonicalPs1 = (Get-Content $templatePs1 -Raw) -replace "`r`n", "`n"

function Write-LauncherFile {
    param([string]$Path, [string]$Content)
    # UTF-8 without BOM; Windows-friendly CRLF endings. .bat files in
    # particular dislike BOMs (cmd.exe interprets them as command bytes).
    $crlf = $Content -replace "`n", "`r`n"
    [System.IO.File]::WriteAllText(
        $Path, $crlf, [System.Text.UTF8Encoding]::new($false)
    )
}

$summary = [ordered]@{
    Scanned = 0
    AlreadyCurrent = 0
    Updated = 0
    DeletedRetired = 0
    Errors = 0
}

Write-Host "Sweeping $ProjectsRoot for stale schedule-update launchers..."
Write-Host "Templates from $templateDir"
Write-Host ""

$targets = Get-ChildItem -Path $ProjectsRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -in @(
            'Write Weekly Schedule Email.bat',
            'Write Weekly Schedule Email.ps1',
            'take-screenshots.bat'
        )
    }

if (-not $targets) {
    Write-Host "No launcher files found. Nothing to do." -ForegroundColor Green
    return
}

foreach ($file in $targets) {
    $summary.Scanned++
    try {
        if ($file.Name -eq 'take-screenshots.bat') {
            Write-Host "[retired] $($file.FullName)" -ForegroundColor Yellow
            if (-not $DryRun) {
                if ($Backup) {
                    Copy-Item -Path $file.FullName -Destination "$($file.FullName).bak" -Force
                }
                Remove-Item -Path $file.FullName -Force
            }
            $summary.DeletedRetired++
            continue
        }

        $current = (Get-Content $file.FullName -Raw -ErrorAction Stop) -replace "`r`n", "`n"
        $canonical = if ($file.Extension -ieq '.bat') { $canonicalBat } else { $canonicalPs1 }

        if ($current -eq $canonical) {
            Write-Host "[ok]      $($file.FullName)" -ForegroundColor DarkGray
            $summary.AlreadyCurrent++
            continue
        }

        Write-Host "[stale]   $($file.FullName)" -ForegroundColor Cyan
        if (-not $DryRun) {
            if ($Backup) {
                Copy-Item -Path $file.FullName -Destination "$($file.FullName).bak" -Force
            }
            Write-LauncherFile -Path $file.FullName -Content $canonical
        }
        $summary.Updated++
    } catch {
        Write-Host "[error]   $($file.FullName): $_" -ForegroundColor Red
        $summary.Errors++
    }
}

Write-Host ""
Write-Host "Summary:" -ForegroundColor Green
$summary.GetEnumerator() | ForEach-Object {
    Write-Host ("  {0,-16} {1}" -f $_.Key, $_.Value)
}

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run - no files modified. Re-run without -DryRun to apply." -ForegroundColor Yellow
}
