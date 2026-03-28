# PowerShell script to start Synapse AI services on Windows
# Equivalent to start.sh for cross-platform compatibility

param()

# Get script directory
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

# Global jobs
$BackendJob = $null
$FrontendJob = $null

# Cleanup function
function Cleanup {
    Write-Host ""
    Write-Host "Stopping services..."

    if ($BackendJob) {
        Write-Host "Stopping Backend job..."
        Stop-Job $BackendJob -ErrorAction SilentlyContinue
        Remove-Job $BackendJob -ErrorAction SilentlyContinue
    }

    if ($FrontendJob) {
        Write-Host "Stopping Frontend job..."
        Stop-Job $FrontendJob -ErrorAction SilentlyContinue
        Remove-Job $FrontendJob -ErrorAction SilentlyContinue
    }

    Write-Host "Done."
}

# Trap for cleanup on exit
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Cleanup }

try {
    # Function to check if port is in use
    function Test-Port {
        param([int]$Port)
        try {
            $null = New-Object System.Net.Sockets.TcpClient('localhost', $Port)
            Write-Host "Service on port $Port is already running."
            return $true
        } catch {
            Write-Host "Service on port $Port is NOT running."
            return $false
        }
    }

    # Function to wait for URL
    function Wait-ForUrl {
        param([string]$Url, [string]$Name)
        $maxRetries = 30
        $count = 0

        Write-Host "Waiting for $Name to be ready at $Url..."
        while ($count -lt $maxRetries) {
            try {
                $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    Write-Host "$Name is ready!"
                    return $true
                }
            } catch {
                # Ignore errors
            }
            Write-Host "$Name not ready yet. Retrying in 2s..."
            Start-Sleep -Seconds 2
            $count++
        }
        Write-Host "Timeout waiting for $Name!"
        return $false
    }

    # Check and start Backend (Port 8000)
    Write-Host "Checking Backend..."
    if (-not (Test-Port 8000)) {
        Write-Host "Starting Backend..."
        $BackendJob = Start-Job -ScriptBlock {
            param($Dir)
            . "$Dir\backend\venv\Scripts\activate.ps1"
            python3.11 "$Dir\backend\main.py"
        } -ArgumentList $DIR
        Write-Host "Backend started."
    } else {
        Write-Host "Backend is already running."
    }

    # Always wait for backend
    Wait-ForUrl "http://localhost:8000/api/status" "Backend"

    # Check and start Frontend (Port 3000)
    Write-Host "Checking Frontend..."
    if (-not (Test-Port 3000)) {
        Write-Host "Starting Frontend..."
        $FrontendJob = Start-Job -ScriptBlock {
            param($Dir)
            Set-Location "$Dir\frontend"
            npm run dev
        } -ArgumentList $DIR
        Write-Host "Frontend started."
    } else {
        Write-Host "Frontend is already running."
    }

    # Always wait for frontend
    Wait-ForUrl "http://localhost:3000" "Frontend"

    Write-Host "Launching Browser..."
    python3.11 "$DIR\launch_browser.py"

    Write-Host "Services are running. Press Ctrl+C to stop."
    Wait-Job -Any
} finally {
    Cleanup
}