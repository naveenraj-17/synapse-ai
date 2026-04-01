import os
import sys
from pathlib import Path

# Load the project-root .env before anything else so that SYNAPSE_BACKEND_PORT
# and other vars are available even when running `python main.py` directly.
_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ROOT_ENV, override=False)  # override=False: real env vars win
except ImportError:
    pass  # dotenv not installed — env vars must be set manually

import uvicorn

# Add the current directory to sys.path so we can import from core, agents, etc.
# This assumes main.py is located at backend/main.py and run from there or project root.
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from core.server import app

if __name__ == "__main__":
    port = int(os.getenv("SYNAPSE_BACKEND_PORT", "8000"))
    print(f"Starting Backend Agent Server from {current_dir} on port {port}...")
    # Enable hot reload for development
    uvicorn.run("core.server:app", host="0.0.0.0", port=port, reload=True)
