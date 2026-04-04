# Synapse AI Setup Script for Windows
# Run with: irm https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.ps1 | iex

$ErrorActionPreference = "Stop"

function Update-Environment {
    try {
        Write-Host "Refreshing PATH environment variable..." -ForegroundColor Cyan
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", [System.EnvironmentVariableTarget]::Machine)
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", [System.EnvironmentVariableTarget]::User)
        $env:Path = "$machinePath;$userPath"
    } catch {
        Write-Host "[WARN] Failed to refresh environment variables automatically." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# Install Git if missing
# ---------------------------------------------------------------------------
function Install-Git {
    Write-Host ""
    Write-Host "Installing Git..." -ForegroundColor Cyan
    
    # Check if winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Git via winget..."
        winget install --id Git.Git -e --accept-source-agreements
        Write-Host "[OK] Git installed successfully" -ForegroundColor Green
        Update-Environment
    } else {
        Write-Host "[WARN] winget not found. Please install Git manually:" -ForegroundColor Yellow
        Write-Host "  https://git-scm.com/download/win"
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Install Node.js if missing or too old
# ---------------------------------------------------------------------------
function Install-NodeJS {
    Write-Host ""
    Write-Host "Installing Node.js 20+ (LTS)..." -ForegroundColor Cyan
    
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Node.js via winget..."
        winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements
        Write-Host "[OK] Node.js installed (via winget). Refreshing PATH..." -ForegroundColor Green
        # Give the installer a moment to finish writing files
        Start-Sleep -Seconds 3
        Update-Environment
        # Force-add all known Node.js install locations to current session PATH
        $knownNodeDirs = @(
            "$env:ProgramFiles\nodejs",
            "$env:ProgramFiles(x86)\nodejs",
            "$env:LocalAppData\Programs\nodejs",
            "$env:AppData\npm"
        )
        foreach ($dir in $knownNodeDirs) {
            if ((Test-Path $dir) -and ($env:Path -notlike "*$dir*")) {
                Write-Host "[INFO] Prepending $dir to session PATH" -ForegroundColor Cyan
                $env:Path = "$dir;$env:Path"
            }
        }
    } else {
        Write-Host "[WARN] winget not found. Please install Node.js manually (v20.9.0 or higher):" -ForegroundColor Yellow
        Write-Host "  https://nodejs.org/"
        throw "winget not available for Node.js installation."
    }
}

function Find-NodeExe {
    # Returns the full path to node.exe if found in known locations, or $null
    $candidates = @(
        "$env:ProgramFiles\nodejs\node.exe",
        "$env:ProgramFiles(x86)\nodejs\node.exe",
        "$env:LocalAppData\Programs\nodejs\node.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    # Also try resolving via PATH (may be cached, so use Get-Command -All)
    try {
        $cmds = Get-Command node -All -ErrorAction SilentlyContinue
        foreach ($c in $cmds) {
            if ($c.Source -and (Test-Path $c.Source)) { return $c.Source }
        }
    } catch {}
    return $null
}

function Test-NodeVersion {
    try {
        # Always probe known paths directly to bypass Get-Command caching
        $nodeExe = Find-NodeExe
        if ($nodeExe) {
            $nodeDir = [System.IO.Path]::GetDirectoryName($nodeExe)
            if ($env:Path -notlike "*$nodeDir*") {
                Write-Host "[INFO] Adding $nodeDir to current session PATH" -ForegroundColor Cyan
                $env:Path = "$nodeDir;$env:Path"
            }
        } else {
            return $false
        }

        $verStr = & $nodeExe -v 2>$null
        if (-not $verStr) { return $false }
        # Remove 'v' prefix if present
        if ($verStr.TrimStart().StartsWith("v")) {
            $verStr = $verStr.TrimStart().SubString(1)
        }
        $version = [version]$verStr.Trim()
        # Check for 20.9.0 or higher
        return ($version -ge [version]"20.9.0")
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------------------
# Install Python if missing
# ---------------------------------------------------------------------------
function Install-Python {
    Write-Host ""
    Write-Host "Installing Python 3.11+..." -ForegroundColor Cyan
    
    # Check if winget is available
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Python 3.11 via winget..."
        winget install --id Python.Python.3.11 -e --accept-source-agreements
        Write-Host "[OK] Python installed successfully" -ForegroundColor Green
        Update-Environment
    } else {
        Write-Host "[WARN] winget not found. Please install Python manually:" -ForegroundColor Yellow
        Write-Host "  https://www.python.org/downloads/"
        Write-Host "  CRITICAL: Check 'Add Python to PATH' during installation"
        exit 1
    }
}

function Test-PythonVersion {
    param([string]$cmd)
    try {
        # We use double quotes for the -c argument as it's more reliable on Windows.
        # Python will exit with 0 if version >= 3.11, and 1 otherwise.
        $check = "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
        
        # Use Start-Process or direct execution with 2>$null
        # We check $LASTEXITCODE to determine compatibility
        $null = & {
            $ErrorActionPreference = 'Continue'
            if ($cmd -match " ") {
                # Handle cases like "py -3.11"
                $parts = $cmd -split " "
                & $parts[0] $parts[1..($parts.Length-1)] -c "$check" 2>$null
            } else {
                & $cmd -c "$check" 2>$null
            }
        }
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-PythonPath {
    # 1. Check py launcher (most reliable on Windows)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        if (Test-PythonVersion "py -3.11") { return "py -3.11" }
        if (Test-PythonVersion "py -3") { return "py -3" }
    }

    # 2. Check candidates in PATH
    $candidates = @("python3.11", "python", "python3", "python3.12", "python3.13")
    foreach ($cmd in $candidates) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            # Skip Windows Store placeholders
            if ((Get-Command $cmd).Source -match "WindowsApps") { continue }
            if (Test-PythonVersion $cmd) { return $cmd }
        }
    }

    # 3. Check Registry
    $regPaths = @(
        "HKCU:\Software\Python\PythonCore",
        "HKLM:\SOFTWARE\Python\PythonCore"
    )
    foreach ($reg in $regPaths) {
        if (Test-Path $reg) {
            $versions = Get-ChildItem $reg | Select-Object -ExpandProperty PSChildName
            foreach ($v in $versions) {
                try {
                    $installPath = Get-ItemPropertyValue "$reg\$v\InstallPath" -Name "(Default)" -ErrorAction SilentlyContinue
                    $exe = "$installPath\python.exe"
                    if ($installPath -and (Test-Path $exe)) {
                        if (Test-PythonVersion "$exe") { return "$exe" }
                    }
                } catch {}
            }
        }
    }

    # 4. Check common directories
    $dirCandidates = @(
        "$env:SystemDrive\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe"
    )
    foreach ($path in $dirCandidates) {
        if (Test-Path $path) {
            if (Test-PythonVersion "$path") { return "$path" }
        }
    }

    return $null
}

# ---------------------------------------------------------------------------
# Check and Install Requirements
# ---------------------------------------------------------------------------
function Invoke-PrerequisitesCheck {
    # Check python
    $global:PYTHON_CMD = Get-PythonPath

    if (-not $global:PYTHON_CMD) {
        Write-Host "[WARN] Python 3.11+ could not be found." -ForegroundColor Yellow
        Write-Host "Attempting to install Python 3.11..."
        Install-Python
        
        $global:PYTHON_CMD = Get-PythonPath
        if (-not $global:PYTHON_CMD) {
        throw "Failed to install Python 3.11+ automatically. Please manually install Python 3.11 or higher."
    }
}

Write-Host "[OK] Python found ($global:PYTHON_CMD)" -ForegroundColor Green

    # Check git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "[WARN] git not found." -ForegroundColor Yellow
        Write-Host "Attempting to install Git..."
        Install-Git
        
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "Failed to install Git automatically. Please manually install Git and add it to your PATH."
        }
    }

    Write-Host "[OK] git found" -ForegroundColor Green

    # Check node
    if (-not (Test-NodeVersion)) {
        Write-Host "[WARN] Node.js 20.9.0+ not found." -ForegroundColor Yellow
        Install-NodeJS
        
        if (-not (Test-NodeVersion)) {
            throw "Failed to install Node.js 20.9.0+ automatically. Please manually install Node.js (v20.9.0 or higher)."
        }
    }

    $nodeVer = try { (node -v).Trim() } catch { "Unknown" }
    Write-Host "[OK] Node.js found ($nodeVer)" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Instructions for manual installs
# ---------------------------------------------------------------------------
function Show-PostgresInstructions {
    Write-Host ""
    Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "   PostgreSQL Installation Instructions for Windows" -ForegroundColor Yellow
    Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "1. Download the installer from:"
    Write-Host "   https://www.postgresql.org/download/windows/"
    Write-Host "2. Run the installer and follow the prompts."
    Write-Host "3. CRITICAL: Add the PostgreSQL bin directory to your PATH:"
    Write-Host "   - Open 'Edit the system environment variables'"
    Write-Host "   - Click 'Environment Variables'"
    Write-Host "   - Under 'System variables', find 'Path' and click 'Edit'"
    Write-Host "   - Click 'New' and add the path (e.g., C:\Program Files\PostgreSQL\15\bin)"
    Write-Host "4. Verify the installation by opening a NEW terminal and running:"
    Write-Host "   psql --version"
    Write-Host "   Make sure it returns a version before trying setup again."
    Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Main Setup Flow
# ---------------------------------------------------------------------------
function Start-SynapseSetup {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "   Synapse AI - Repository Setup" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host ""

    Invoke-PrerequisitesCheck

    $RepoUrl = "https://github.com/naveenraj-17/synapse-ai.git"
    $DestDir = "synapse-ai"

    if (Test-Path "$DestDir\.git") {
        Write-Host ""
        Write-Host "Repository already exists at .\$DestDir -- pulling latest..."
        git -C $DestDir pull --ff-only
    } else {
        Write-Host ""
        Write-Host "Cloning Synapse AI..."
        git clone $RepoUrl $DestDir
    }

    if (Test-Path $DestDir) {
        Set-Location $DestDir
        Write-Host ""
        
        # We need to handle cases where the command has arguments like "py -3.11"
        if ($global:PYTHON_CMD -match " ") {
            $parts = $global:PYTHON_CMD -split " "
            & $parts[0] $parts[1..($parts.Length-1)] setup.py
        } else {
            & $global:PYTHON_CMD setup.py
        }
    } else {
        throw "Could not find repository directory: $DestDir"
    }
}

# Run the setup
try {
    Start-SynapseSetup
} catch {
    Write-Host ""
    Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
    Write-Host "   CRITICAL ERROR OCCURRED" -ForegroundColor Red
    Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Red
    Write-Host ""
    Write-Host "$($_.Exception.Message)"
    Write-Host ""
    if ($_.ScriptStackTrace) {
        Write-Host "Stack Trace:" -ForegroundColor Gray
        Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "The setup script has failed. Please capture the error above."
    Write-Host "Press Enter to exit..."
    $null = Read-Host
    exit 1
}
