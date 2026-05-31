# install-windows.ps1 - jellyfin-movie-organizer installer for Windows 10/11
# Author: Younes Rahimi
#
# Usage:
#   .\install-windows.ps1                         # install interactively
#   .\install-windows.ps1 -Uninstall              # remove installed files
#   .\install-windows.ps1 -Force                  # reinstall even if present
#   .\install-windows.ps1 -InstallDir C:\Tools    # custom install directory
#   .\install-windows.ps1 -SocksProxy socks5://localhost:10808
#
# What this script does:
#   1. Verifies Python 3.10+ and pip are available.
#   2. Installs pip dependencies from requirements.txt (user-level).
#   3. Creates jmo.cmd/jmo_run.py (organizer) and jmd.cmd/jmd_run.py (downloader)
#      so commands work from any terminal.
#   4. Adds the install directory to the user PATH (permanent, no admin needed).
#
# Execution policy note (run once if needed):
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Force,
    [string]$InstallDir  = "",
    [string]$SocksProxy  = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Helpers --------------------------------------------------------------

function Write-Info { param($msg) Write-Host "[jmo] $msg" -ForegroundColor Green  }
function Write-Warn { param($msg) Write-Host "[jmo] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "[jmo] error: $msg" -ForegroundColor Red; exit 1 }

# -- Defaults -------------------------------------------------------------

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:USERPROFILE "bin"
}

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Requirements = Join-Path $ScriptDir "requirements.txt"
$WrapperCmdOrganizer = Join-Path $InstallDir "jmo.cmd"
$WrapperPyOrganizer  = Join-Path $InstallDir "jmo_run.py"
$WrapperCmdDownloader = Join-Path $InstallDir "jmd.cmd"
$WrapperPyDownloader  = Join-Path $InstallDir "jmd_run.py"

# -- Uninstall ------------------------------------------------------------

if ($Uninstall) {
    Write-Info "Uninstalling jellyfin-movie-organizer..."

    foreach ($f in @($WrapperCmdOrganizer, $WrapperPyOrganizer, $WrapperCmdDownloader, $WrapperPyDownloader)) {
        if (Test-Path $f) {
            Remove-Item $f -Force
            Write-Info "Removed $f"
        } else {
            Write-Warn "Not found, skipping: $f"
        }
    }

    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($currentPath -like "*$InstallDir*") {
        $newPath = ($currentPath -split ";" | Where-Object { $_.Trim() -ne $InstallDir }) -join ";"
        [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
        Write-Info "Removed $InstallDir from user PATH."
    }

    Write-Info "Uninstall complete."
    Write-Info "To remove the source code too, delete: $ScriptDir"
    exit 0
}

# -- Verify Python 3.10+ --------------------------------------------------

Write-Info "Checking Python..."
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $python = $candidate
                Write-Info "Found $candidate : $ver"
                break
            } else {
                Write-Warn "$candidate version $ver is below 3.10 - skipping."
            }
        }
    } catch { }
}

if (-not $python) {
    Write-Fail (
        "Python 3.10+ not found on PATH.`n" +
        "  Download from https://www.python.org/downloads/`n" +
        "  During install check 'Add Python to PATH'."
    )
}

# -- Verify pip -----------------------------------------------------------

try {
    & $python -m pip --version | Out-Null
} catch {
    Write-Fail "pip not found. Run: $python -m ensurepip --upgrade"
}

# -- Verify source layout -------------------------------------------------

if (-not (Test-Path $Requirements)) {
    Write-Fail "requirements.txt not found at $Requirements. Run this script from the project root."
}
if (-not (Test-Path (Join-Path $ScriptDir "src\main.py"))) {
    Write-Fail "src\main.py not found. Run this script from the project root."
}

# -- Install Python dependencies -----------------------------------------

Write-Info "Installing Python dependencies..."
$alreadyInstalled = & $python -c "import requests, bs4, lxml; print('ok')" 2>$null
if ($alreadyInstalled -eq "ok") {
    Write-Info "Dependencies already available."
} else {
    try {
        & $python -m pip install --quiet --user -r $Requirements
        Write-Info "Dependencies installed."
    } catch {
        Write-Fail "Could not install dependencies. Run manually: $python -m pip install -r requirements.txt"
    }
}

# -- Create install directory --------------------------------------------

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir | Out-Null
    Write-Info "Created $InstallDir"
}

# -- Write wrapper files --------------------------------------------------

function Ensure-Wrapper {
    param(
        [string]$CmdPath,
        [string]$PyPath,
        [string]$Module,
        [string]$Label
    )

    if ((Test-Path $CmdPath) -and (Test-Path $PyPath) -and -not $Force) {
        Write-Info "Wrappers already installed for $Label (use -Force to reinstall)."
        return
    }

    $pyLeaf = Split-Path -Leaf $PyPath
    $cmdContent = @"
@echo off
python "%~dp0$pyLeaf" %*
"@
    $cmdContent | Set-Content -Path $CmdPath -Encoding ASCII
    Write-Info "Created $CmdPath"

    $escapedSrc = $ScriptDir.Replace("\", "\\")
    $pyContent = @"
#!/usr/bin/env python3
"""$Label - installed by install-windows.ps1"""
import sys, os
_src = r"$escapedSrc"
if _src not in sys.path:
    sys.path.insert(0, _src)
from $Module import main
main()
"@
    $pyContent | Set-Content -Path $PyPath -Encoding UTF8
    Write-Info "Created $PyPath"
}

Ensure-Wrapper -CmdPath $WrapperCmdOrganizer -PyPath $WrapperPyOrganizer -Module "src.main" -Label "jellyfin-movie-organizer (jmo)"
Ensure-Wrapper -CmdPath $WrapperCmdDownloader -PyPath $WrapperPyDownloader -Module "src.download" -Label "jellyfin-movie-downloader (jmd)"

# -- Update user PATH -----------------------------------------------------

$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($currentPath -notlike "*$InstallDir*") {
    $newPath = "$InstallDir;$currentPath"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Info "Added $InstallDir to user PATH."
    Write-Warn "Restart your terminal for the PATH change to take effect."
} else {
    Write-Info "$InstallDir is already on user PATH."
}

# -- Proxy reminder -------------------------------------------------------

if ($SocksProxy) {
    Write-Host ""
    Write-Host "== Proxy Setup ==================================================" -ForegroundColor Cyan
    Write-Host "  To route Python requests through your SOCKS proxy, set:" -ForegroundColor Cyan
    Write-Host "    `$env:ALL_PROXY   = '$SocksProxy'"
    Write-Host "    `$env:HTTPS_PROXY = '$SocksProxy'"
    Write-Host "  Or add them permanently via System Properties > Environment Variables."
    Write-Host "=================================================================" -ForegroundColor Cyan
}

# -- Windows Defender / antivirus note -----------------------------------

Write-Host ""
Write-Host "== Windows Note =================================================" -ForegroundColor Cyan
Write-Host "  If 'jmo' is flagged by Windows Defender, add an exclusion for:"
Write-Host "    $InstallDir"
Write-Host "  Settings > Windows Security > Virus & threat protection > Exclusions"
Write-Host "=================================================================" -ForegroundColor Cyan

# -- Done ----------------------------------------------------------------

Write-Info ""
Write-Info "Installation complete!"
Write-Info ""
Write-Info "Next steps:"
Write-Info "  1. Restart your terminal (PowerShell or cmd.exe)."
Write-Info "  2. Organise a movie directory:  jmo C:\Movies"
Write-Info "  3. Download from Filimo:        jmd aVmdY --output C:\Movies"
Write-Info "  4. Preview only (dry run):      jmo C:\Movies --dry-run"
Write-Info "  5. Skip specific tasks:         jmo C:\Movies --skip-rename --skip-backdrop"
Write-Info "  6. Verbose logs:                jmo C:\Movies -v"
Write-Info ""
Write-Info "To uninstall: .\install-windows.ps1 -Uninstall"
