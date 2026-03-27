#!/bin/bash

set -e

# Check python3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 could not be found."
    echo ""
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "On Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
        echo "On Fedora: sudo dnf install python3"
        echo "On Arch: sudo pacman -S python"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "On macOS: brew install python3"
    elif [[ "$OSTYPE" == "msys" ]]; then
        echo "On Windows: Download from https://www.python.org/downloads/"
    fi
    exit 1
fi

# Check git
if ! command -v git &> /dev/null; then
    echo "Error: git could not be found. Please install git and try again."
    exit 1
fi

# Clone or update repo
REPO_URL="https://github.com/naveenraj-17/synapse-ai.git"
DEST_DIR="synapse-ai"

if [ -d "$DEST_DIR/.git" ]; then
    echo "Repository already exists at ./$DEST_DIR — pulling latest..."
    git -C "$DEST_DIR" pull --ff-only
else
    echo "Cloning Synapse AI..."
    git clone "$REPO_URL" "$DEST_DIR"
fi

cd "$DEST_DIR"

echo ""
python3 setup.py
