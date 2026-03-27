# Synapse AI Setup Script for Windows
# Run with: irm https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.ps1 | iex

$ErrorActionPreference = "Stop"

# Check python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: python could not be found."
    Write-Host "Download from https://www.python.org/downloads/ (3.11+ required)"
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
