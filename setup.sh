#!/bin/bash

set -e

# ---------------------------------------------------------------------------
# Detect OS and distribution
# ---------------------------------------------------------------------------
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO=$ID
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    else
        OS="unknown"
    fi
}

# ---------------------------------------------------------------------------
# Install Git if missing
# ---------------------------------------------------------------------------
install_git() {
    echo ""
    echo "Installing Git…"
    
    if [[ "$OS" == "linux" ]]; then
        if [[ "$DISTRO" == "ubuntu" ]] || [[ "$DISTRO" == "debian" ]]; then
            echo "Installing Git on Ubuntu/Debian…"
            sudo apt-get update
            sudo apt-get install -y git
        elif [[ "$DISTRO" == "fedora" ]] || [[ "$DISTRO" == "rhel" ]] || [[ "$DISTRO" == "centos" ]]; then
            echo "Installing Git on Fedora/RHEL…"
            sudo dnf install -y git
        elif [[ "$DISTRO" == "arch" ]] || [[ "$DISTRO" == "manjaro" ]]; then
            echo "Installing Git on Arch/Manjaro…"
            sudo pacman -S --noconfirm git
        else
            echo "Unknown Linux distribution: $DISTRO"
            exit 1
        fi
    elif [[ "$OS" == "macos" ]]; then
        echo "Installing Git via Homebrew…"
        if ! command -v brew &> /dev/null; then
            echo "Homebrew not found. Please install from https://brew.sh"
            exit 1
        fi
        brew install git
    elif [[ "$OS" == "windows" ]]; then
        echo "Please download and install Git from https://git-scm.com/download/win"
        exit 1
    fi
    
    echo "✓ Git installed successfully"
}

# ---------------------------------------------------------------------------
# Install Python if missing
# ---------------------------------------------------------------------------
install_python() {
    echo ""
    echo "Installing Python 3.11+…"
    
    if [[ "$OS" == "linux" ]]; then
        if [[ "$DISTRO" == "ubuntu" ]] || [[ "$DISTRO" == "debian" ]]; then
            echo "Installing Python on Ubuntu/Debian…"
            sudo apt-get update
            sudo apt-get install -y python3 python3-venv python3-pip
        elif [[ "$DISTRO" == "fedora" ]] || [[ "$DISTRO" == "rhel" ]] || [[ "$DISTRO" == "centos" ]]; then
            echo "Installing Python on Fedora/RHEL…"
            sudo dnf install -y python3 python3-pip
        elif [[ "$DISTRO" == "arch" ]] || [[ "$DISTRO" == "manjaro" ]]; then
            echo "Installing Python on Arch/Manjaro…"
            sudo pacman -S --noconfirm python python-pip
        else
            echo "Unknown Linux distribution: $DISTRO"
            exit 1
        fi
    elif [[ "$OS" == "macos" ]]; then
        echo "Installing Python via Homebrew…"
        if ! command -v brew &> /dev/null; then
            echo "Homebrew not found. Please install from https://brew.sh"
            exit 1
        fi
        brew install python@3.12
    elif [[ "$OS" == "windows" ]]; then
        echo "Please download and install Python from https://www.python.org/downloads/"
        echo "Make sure to check 'Add Python to PATH' during installation"
        exit 1
    fi
    
    echo "✓ Python installed successfully"
}

# ---------------------------------------------------------------------------
# Check and validate requirements
# ---------------------------------------------------------------------------

# Returns true (0) if the given python command is >= 3.11
_python_meets_minimum() {
    local cmd="$1"
    command -v "$cmd" &> /dev/null || return 1
    local major minor
    major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
    minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
    [[ -n "$major" && -n "$minor" ]] || return 1
    [[ "$major" -gt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -ge 11 ]]; }
}

# Scans well-known python command names and sets PYTHON_CMD to the first one >= 3.11
_find_python_cmd() {
    PYTHON_CMD=""
    for cmd in python3.13 python3.12 python3.11 python3 python; do
        if _python_meets_minimum "$cmd"; then
            PYTHON_CMD="$cmd"
            return 0
        fi
    done
    return 1
}

check_python() {
    if ! _find_python_cmd; then
        echo "⚠ Python 3.11+ not found. Attempting to install..."
        install_python

        if ! _find_python_cmd; then
            echo "✗ Failed to install Python 3.11+ automatically."
            echo "Please manually install Python 3.11 or higher."
            if [[ "$OS" == "linux" ]] && [[ "$DISTRO" == "ubuntu" ]]; then
                echo ""
                echo "For Ubuntu, you may need to add the deadsnakes PPA:"
                echo "  sudo add-apt-repository ppa:deadsnakes/ppa"
                echo "  sudo apt update"
                echo "  sudo apt install python3.11 python3.11-venv"
            elif [[ "$OS" == "macos" ]]; then
                echo ""
                echo "For macOS, you can use Homebrew:"
                echo "  brew install python@3.11"
            fi
            exit 1
        fi
    fi

    PYTHON_VERSION=$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "✓ Python $PYTHON_VERSION found ($PYTHON_CMD)"
    export PYTHON_CMD
}

check_git() {
    if ! command -v git &> /dev/null; then
        echo "⚠ git not found."
        install_git
    fi
    echo "✓ git found"
}

# ---------------------------------------------------------------------------
# Main setup flow
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "========================================================"
    echo "   Synapse AI — Repository Setup"
    echo "========================================================"
    echo ""
    
    detect_os
    check_git
    check_python
    
    # Clone or update repo
    REPO_URL="https://github.com/naveenraj-17/synapse-ai.git"
    DEST_DIR="synapse-ai"
    
    if [ -d "$DEST_DIR/.git" ]; then
        echo ""
        echo "Repository already exists at ./$DEST_DIR — pulling latest…"
        git -C "$DEST_DIR" pull --ff-only
    else
        echo ""
        echo "Cloning Synapse AI…"
        git clone "$REPO_URL" "$DEST_DIR"
    fi
    
    cd "$DEST_DIR"
    
    echo ""
    if [ -t 1 ]; then
        $PYTHON_CMD setup.py < /dev/tty
    else
        $PYTHON_CMD setup.py
    fi
}

main

