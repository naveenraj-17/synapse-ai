# Synapse AI Setup Script for Windows
# Run with: irm https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.ps1 | iex

$ErrorActionPreference = "Stop"

# Check python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python could not be found. Python 3.11 or higher is required."
    Write-Host ""
    Write-Host "Install Python using one of the following methods:"
    Write-Host ""
    Write-Host "  Option 1 - winget (recommended):"
    Write-Host "    winget install Python.Python.3.11"
    Write-Host ""
    Write-Host "  Option 2 - Official installer:"
    Write-Host "    https://www.python.org/downloads/"
    Write-Host "    (Check 'Add Python to PATH' during installation)"
    Write-Host ""
    Write-Host "  Option 3 - Microsoft Store:"
    Write-Host "    ms-windows-store://pdp/?ProductId=9NRWMJP3717K"
    Write-Host ""
    Write-Host "After installing, restart PowerShell and run this script again."
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
