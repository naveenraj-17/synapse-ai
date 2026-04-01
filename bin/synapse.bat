@echo off
REM Synapse AI CLI Wrapper — Activates venv and runs synapse command
REM Place this script in PATH or run it directly

setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_DIR=%%~fI"
set "VENV_DIR=%REPO_DIR%\backend\venv"

if not exist "%VENV_DIR%" (
    echo Error: Virtual environment not found at %VENV_DIR%
    echo Run setup.ps1 first.
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m synapse %*
