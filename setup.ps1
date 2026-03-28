# Synapse AI Setup Script for Windows
# Run with: irm https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.ps1 | iex

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Install Git if missing
# ---------------------------------------------------------------------------
function Install-Git {
    Write-Host ""
    Write-Host "Installing Git…" -ForegroundColor Cyan
    
    # Check if winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Git via winget…"
        winget install --id Git.Git -e --accept-source-agreements
        Write-Host "✓ Git installed successfully" -ForegroundColor Green
    } else {
        Write-Host "⚠ winget not found. Please install Git manually:" -ForegroundColor Yellow
        Write-Host "  https://git-scm.com/download/win"
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Install Python if missing
# ---------------------------------------------------------------------------
function Install-Python {
    Write-Host ""
    Write-Host "Installing Python 3.11+…" -ForegroundColor Cyan
    
    # Check if winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Python 3.11 via winget…"
        winget install --id Python.Python.3.11 -e --accept-source-agreements
        Write-Host "✓ Python installed successfully" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠ Please restart PowerShell for the new Python installation to be recognized."
        exit 1
    } else {
        Write-Host "⚠ winget not found. Please install Python manually:" -ForegroundColor Yellow
        Write-Host "  https://www.python.org/downloads/"
        Write-Host "  CRITICAL: Check 'Add Python to PATH' during installation"
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Check and Install Requirements
# ---------------------------------------------------------------------------
function Check-And-Install {
    # Check python
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $isFakePython = if ($pythonCmd) { $pythonCmd.Source -match "WindowsApps" } else { $false }

    if (-not $pythonCmd -or $isFakePython) {
        Write-Host "⚠ Python could not be found or is blocked by Windows App Aliases." -ForegroundColor Yellow
        Write-Host "Attempting to install Python 3.11…"
        Install-Python
    }

    Write-Host "✓ Python found" -ForegroundColor Green

    # Check git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "⚠ git not found." -ForegroundColor Yellow
        Write-Host "Attempting to install Git…"
        Install-Git
    }

    Write-Host "✓ git found" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Main Setup Flow
# ---------------------------------------------------------------------------
function Main {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "   Synapse AI — Repository Setup" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host ""

    Check-And-Install

    $RepoUrl = "https://github.com/naveenraj-17/synapse-ai.git"
    $DestDir = "synapse-ai"

    if (Test-Path "$DestDir\.git") {
        Write-Host ""
        Write-Host "Repository already exists at .\$DestDir -- pulling latest…"
        git -C $DestDir pull --ff-only
    } else {
        Write-Host ""
        Write-Host "Cloning Synapse AI…"
        git clone $RepoUrl $DestDir
    }

    Set-Location $DestDir

    Write-Host ""
    python setup.py
}

# Run the setup
Main
