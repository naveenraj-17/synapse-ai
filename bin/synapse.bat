@echo off
REM Synapse AI CLI Wrapper — Activates venv, ensures Node.js is in PATH, runs synapse command
REM Place this script in PATH or run it directly

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_DIR=%%~fI"
set "VENV_DIR=%REPO_DIR%\backend\venv"

if not exist "%VENV_DIR%" (
    echo Error: Virtual environment not found at %VENV_DIR%
    echo Run setup.ps1 first.
    exit /b 1
)

REM ---- Ensure Node.js (npm) is in PATH ----
REM Probe known install locations so this works even when PATH is stale
for %%N in (
    "%ProgramFiles%\nodejs"
    "%ProgramFiles(x86)%\nodejs"
    "%LocalAppData%\Programs\nodejs"
    "%LocalAppData%\nodejs"
) do (
    if exist "%%~N\npm.cmd" (
        set "_NODE_DIR=%%~N"
        goto :found_node
    )
)
:found_node
if defined _NODE_DIR (
    set "PATH=%_NODE_DIR%;%PATH%"
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m synapse %*
