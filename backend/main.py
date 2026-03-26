import uvicorn
import os
import sys

# Add the current directory to sys.path so we can import from core, agents, etc.
# This assumes main.py is located at backend/main.py and run from there or project root.
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from core.server import app

if __name__ == "__main__":
    print(f"Starting Backend Agent Server from {current_dir}...")
    # Enable hot reload for development
    uvicorn.run("core.server:app", host="0.0.0.0", port=8000, reload=True)
