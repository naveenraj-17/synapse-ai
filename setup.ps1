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
# Install uv (and uvx) if missing
# ---------------------------------------------------------------------------
function Install-Uv {
    Write-Host ""
    Write-Host "Installing uv (Python package manager)..." -ForegroundColor Cyan

    # Try winget first
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            winget install --id astral-sh.uv -e --accept-source-agreements 2>$null
            Write-Host "[OK] uv installed via winget." -ForegroundColor Green
            Update-Environment
            return
        } catch {
            Write-Host "[WARN] winget install of uv failed, trying pip..." -ForegroundColor Yellow
        }
    }

    # Fallback: install via pip into user site
    if ($global:PYTHON_CMD) {
        try {
            if ($global:PYTHON_CMD -match " ") {
                $parts = $global:PYTHON_CMD -split " "
                & $parts[0] $parts[1..($parts.Length-1)] -m pip install --user uv 2>$null
            } else {
                & $global:PYTHON_CMD -m pip install --user uv 2>$null
            }
            Write-Host "[OK] uv installed via pip." -ForegroundColor Green
            # Add user Scripts dir to PATH for this session
            $userScripts = & $global:PYTHON_CMD -c "import site, os; print(os.path.join(site.getusersitepackages(), '..', 'Scripts'))" 2>$null
            if ($userScripts -and (Test-Path $userScripts)) {
                $env:Path = "$userScripts;$env:Path"
            }
            return
        } catch {
            Write-Host "[WARN] pip install uv failed." -ForegroundColor Yellow
        }
    }

    Write-Host "[WARN] Could not install uv automatically." -ForegroundColor Yellow
    Write-Host "  Install manually: https://github.com/astral-sh/uv or 'pip install uv'" -ForegroundColor Gray
}

function Test-Uv {
    # Check common locations where uv may be installed
    $uvLocations = @(
        (Get-Command uv -ErrorAction SilentlyContinue)?.Source,
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe",
        "$env:APPDATA\Python\Scripts\uv.exe"
    )
    foreach ($loc in $uvLocations) {
        if ($loc -and (Test-Path $loc)) {
            if ($env:Path -notlike "*$(Split-Path $loc)*") {
                $env:Path = "$(Split-Path $loc);$env:Path"
            }
            return $true
        }
    }
    return $false
}

function Invoke-UvCheck {
    # Refresh PATH to pick up newly installed uv
    Update-Environment
    if (-not (Test-Uv)) {
        Write-Host "[WARN] uv/uvx not found. Attempting to install..." -ForegroundColor Yellow
        Install-Uv
    }
    if (Test-Uv) {
        $uvVer = try { (uv --version 2>$null).Trim() } catch { "unknown" }
        Write-Host "[OK] $uvVer found (uvx available)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] uv/uvx not available. Install from https://astral.sh/uv" -ForegroundColor Yellow
    }
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

    # Check uv / uvx
    Invoke-UvCheck
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
    Write-Host "2. Run the installer and follow the on-screen prompts."
    Write-Host "3. IMPORTANT: Add the PostgreSQL bin directory to your System PATH:"
    Write-Host "   - Search for 'Edit the system environment variables' in the Start menu"
    Write-Host "   - Click 'Environment Variables'"
    Write-Host "   - Under 'System variables', find 'Path' and click 'Edit'"
    Write-Host "   - Click 'New' and add the bin path (e.g. C:\Program Files\PostgreSQL\17\bin)"
    Write-Host "4. Restart your terminal so the updated PATH takes effect."
    Write-Host "5. Verify the installation by running: psql --version"
    Write-Host "   Make sure it prints a version number before continuing."
    Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Main Setup Flow
# ---------------------------------------------------------------------------
function Start-SynapseSetup {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "   Synapse AI - Setup" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host ""

    # Fixed install location — always the same regardless of where the user runs this script
    $InstallDir  = "$env:LOCALAPPDATA\Programs\SynapseAI"
    $MarkerFile  = "$InstallDir\.installed"

    # -----------------------------------------------------------------------
    # Already-installed check
    # -----------------------------------------------------------------------
    if (Test-Path $MarkerFile) {
        Write-Host ""
        Write-Host "======================================================" -ForegroundColor Green
        Write-Host "   Synapse AI is already installed!" -ForegroundColor Green
        Write-Host "======================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "   Location: $InstallDir" -ForegroundColor Cyan
        Write-Host ""

        # ---------------------------------------------------------------
        # 1. Stop any running services
        # ---------------------------------------------------------------
        Write-Host "==> Stopping running services..." -ForegroundColor Cyan
        $SynapseBat = Join-Path $InstallDir "bin\synapse.bat"
        if (Test-Path $SynapseBat) {
            try {
                & $SynapseBat stop 2>&1 | Out-Null
                Write-Host "[OK] Services stopped." -ForegroundColor Green
            } catch {
                Write-Host "[WARN] Could not run synapse stop cleanly." -ForegroundColor Yellow
            }
        }
        # Fallback: kill via PID files
        $RunDir = Join-Path $InstallDir "run"
        foreach ($pidFile in @("backend.pid", "frontend.pid")) {
            $pidPath = Join-Path $RunDir $pidFile
            if (Test-Path $pidPath) {
                try {
                    $pid = [int](Get-Content $pidPath -ErrorAction SilentlyContinue)
                    taskkill /F /T /PID $pid 2>&1 | Out-Null
                    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
                    Write-Host "[OK] Stopped PID $pid ($pidFile)." -ForegroundColor Green
                } catch {
                    Write-Host "[WARN] Could not stop $pidFile process." -ForegroundColor Yellow
                }
            }
        }
        Start-Sleep -Seconds 2

        # ---------------------------------------------------------------
        # 2. Pull latest changes
        # ---------------------------------------------------------------
        Write-Host ""
        Write-Host "==> Pulling latest changes..." -ForegroundColor Cyan
        $pullResult = git -C $InstallDir pull --ff-only 2>&1
        if ($LASTEXITCODE -eq 0) {
            if ($pullResult -match "Already up to date") {
                Write-Host "[OK] Already up to date -- no code changes." -ForegroundColor Green
            } else {
                Write-Host "[OK] Updated to the latest version." -ForegroundColor Green
                Write-Host $pullResult
            }
        } else {
            Write-Host "[WARN] Could not pull latest changes:" -ForegroundColor Yellow
            Write-Host $pullResult
        }

        # ---------------------------------------------------------------
        # 3. Rebuild via setup.py (backend + frontend)
        # ---------------------------------------------------------------
        Write-Host ""
        Write-Host "==> Rebuilding Synapse AI..." -ForegroundColor Cyan
        $SetupScript = Join-Path $InstallDir "setup.py"

        # We need Python and Node to be available for the rebuild.
        # Run a lightweight prerequisite check (no install, just detect).
        Invoke-PrerequisitesCheck

        # Invoke setup.py with the --upgrade flag so it skips the wizard
        # and goes straight to rebuild.
        if ($global:PYTHON_CMD -match " ") {
            $parts = $global:PYTHON_CMD -split " "
            & $parts[0] $parts[1..($parts.Length - 1)] $SetupScript --upgrade
        } else {
            & $global:PYTHON_CMD $SetupScript --upgrade
        }

        # ---------------------------------------------------------------
        # 4. Show instructions
        # ---------------------------------------------------------------
        Write-Host ""
        Write-Host "======================================================" -ForegroundColor Green
        Write-Host "   Synapse AI has been updated and rebuilt!" -ForegroundColor Green
        Write-Host "======================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "To start Synapse:" -ForegroundColor White
        Write-Host "  synapse start" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Other commands:" -ForegroundColor Gray
        Write-Host "  synapse stop      -- stop running services" -ForegroundColor Gray
        Write-Host "  synapse status    -- check service status" -ForegroundColor Gray
        Write-Host "  synapse restart   -- restart services" -ForegroundColor Gray
        Write-Host ""
        exit 0
    }

    Invoke-PrerequisitesCheck

    $RepoUrl = "https://github.com/naveenraj-17/synapse-ai.git"

    # Clone or update at the fixed install location
    if (Test-Path (Join-Path $InstallDir ".git")) {
        Write-Host ""
        Write-Host "Repository found at $InstallDir -- pulling latest changes..."
        git -C $InstallDir pull --ff-only
    } else {
        Write-Host ""
        Write-Host "Installing Synapse AI to: $InstallDir"
        # Create parent directory if needed
        $ParentDir = Split-Path $InstallDir -Parent
        if (-not (Test-Path $ParentDir)) {
            New-Item -ItemType Directory -Path $ParentDir -Force | Out-Null
        }
        git clone $RepoUrl $InstallDir
    }

    if (Test-Path $InstallDir) {
        Write-Host ""
        $SetupScript = Join-Path $InstallDir "setup.py"

        # Handle cases where Python command has arguments (e.g. "py -3.11")
        if ($global:PYTHON_CMD -match " ") {
            $parts = $global:PYTHON_CMD -split " "
            & $parts[0] $parts[1..($parts.Length-1)] $SetupScript
        } else {
            & $global:PYTHON_CMD $SetupScript
        }

        # Add the synapse bin dir to the PowerShell profile for future sessions
        $BinDir      = Join-Path $InstallDir "bin"
        $ProfileFile = $PROFILE.CurrentUserAllHosts
        if (-not (Test-Path $ProfileFile)) {
            New-Item -ItemType File -Path $ProfileFile -Force | Out-Null
        }
        $ProfileContent = Get-Content $ProfileFile -Raw -ErrorAction SilentlyContinue
        if ($ProfileContent -notlike "*SynapseAI*") {
            Add-Content -Path $ProfileFile -Value "`n# Synapse AI`n`$env:Path = `"$BinDir;`$env:Path`""
            Write-Host "[OK] Added Synapse to PowerShell profile ($ProfileFile)" -ForegroundColor Green
        }

        Write-Host ""
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host "   Synapse AI setup complete!" -ForegroundColor Green
        Write-Host "   To start Synapse:  synapse start" -ForegroundColor Cyan
        Write-Host "   Installed at:      $InstallDir" -ForegroundColor Cyan
        Write-Host "========================================================" -ForegroundColor Green
    } else {
        throw "Could not find installation directory: $InstallDir"
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
