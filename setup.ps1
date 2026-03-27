# Synapse AI Setup Script for Windows
# Run with: irm https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.ps1 | iex

$ErrorActionPreference = "Stop"

# Check python and filter out the fake Windows Store alias
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$isFakePython = $pythonCmd.Source -match "WindowsApps"

if (-not $pythonCmd -or $isFakePython) {
    Write-Host "Error: Python could not be found or is blocked by Windows App Aliases. Python 3.11+ is required." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Python using one of the following methods:"
    Write-Host ""
    Write-Host "  Option 1 - winget (recommended):"
    Write-Host "    winget install Python.Python.3.11"
    Write-Host ""
    Write-Host "  Option 2 - Official installer:"
    Write-Host "    https://www.python.org/downloads/"
    Write-Host "    (CRITICAL: Check 'Add python.exe to PATH' during installation)"
    Write-Host ""
    Write-Host "If Python is already installed, turn off the App Aliases:"
    Write-Host "  1. Search 'Manage app execution aliases' in the Windows Start menu."
    Write-Host "  2. Turn OFF 'App Installer (python.exe)' and '(python3.exe)'."
    Write-Host ""
    Write-Host "After fixing, restart PowerShell and run this script again."
    exit 1
}

# Check git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Error: git could not be found."
    Write-Host "Download from https://git-scm.com/download/win"
    exit 1
}

$RepoUrl = "https://github.com/naveenraj-17/synapse-ai.git"
$DestDir = "synapse-ai"

if (Test-Path "$DestDir\.git") {
    Write-Host "Repository already exists at .\$DestDir -- pulling latest..."
    git -C $DestDir pull --ff-only
} else {
    Write-Host "Cloning Synapse AI..."
    git clone $RepoUrl $DestDir
}

Set-Location $DestDir

Write-Host ""
python setup.py
