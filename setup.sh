#!/bin/bash

# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 could not be found."
    echo ""
    echo "Please install Python 3 to continue."
    
    # Detect OS for helpful messages
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

echo "Python 3 found. Starting setup..."
python3 setup.py
