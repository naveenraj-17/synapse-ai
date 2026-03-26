"""
Synapse CLI - starts the backend and frontend, then opens the browser.
"""
import os
import sys
import shutil
import signal
import threading
import time
import urllib.request
import urllib.error
import subprocess
import webbrowser
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
# When installed as a package, backend is one level up from synapse/
BACKEND_DIR = PACKAGE_DIR.parent / "backend"
FRONTEND_DIR = PACKAGE_DIR / "_frontend"

DEFAULT_DATA_DIR = Path.home() / ".synapse" / "data"
DATA_DIR = Path(os.getenv("SYNAPSE_DATA_DIR", str(DEFAULT_DATA_DIR)))

BACKEND_PORT = int(os.getenv("SYNAPSE_BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("SYNAPSE_FRONTEND_PORT", "3000"))

DEFAULT_JSON_FILES = {
    "user_agents.json": "[]",
    "orchestrations.json": "[]",
    "repos.json": "[]",
    "mcp_servers.json": "[]",
    "custom_tools.json": "[]",
}


def check_prerequisites():
    errors = []
    if shutil.which("node") is None:
        errors.append("node not found — install Node.js from https://nodejs.org/")
    if shutil.which("npx") is None:
        errors.append("npx not found — install Node.js from https://nodejs.org/")
    if shutil.which("ollama") is None:
        print("Warning: ollama not found. Local models won't work; cloud API models (Anthropic, OpenAI, Gemini) still work.")
    if errors:
        for e in errors:
            print(f"Error: {e}")
        sys.exit(1)


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for subdir in ("vault", "datasets", "orchestration_runs", "orchestration_logs"):
        (DATA_DIR / subdir).mkdir(exist_ok=True)
    for filename, default in DEFAULT_JSON_FILES.items():
        target = DATA_DIR / filename
        if not target.exists():
            target.write_text(default)


def start_backend():
    env = os.environ.copy()
    env["SYNAPSE_DATA_DIR"] = str(DATA_DIR)
    env["PYTHONPATH"] = str(BACKEND_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, str(BACKEND_DIR / "main.py")],
        cwd=str(BACKEND_DIR),
        env=env,
    )


def start_frontend():
    if not FRONTEND_DIR.exists():
        print("Error: bundled frontend not found. This package may need to be rebuilt.")
        print("       Run: bash scripts/build_frontend.sh  (developer only)")
        sys.exit(1)
    env = os.environ.copy()
    env["PORT"] = str(FRONTEND_PORT)
    env["HOSTNAME"] = "0.0.0.0"
    env["BACKEND_URL"] = f"http://127.0.0.1:{BACKEND_PORT}"
    return subprocess.Popen(
        ["node", str(FRONTEND_DIR / "server.js")],
        cwd=str(FRONTEND_DIR),
        env=env,
    )


def wait_for_url(url: str, name: str, timeout: int = 90) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=3)
            print(f"  {name} ready.")
            return True
        except Exception:
            time.sleep(2)
    print(f"  Timeout waiting for {name} at {url}")
    return False


def open_browser(url: str):
    time.sleep(1)
    webbrowser.open(url)


def main():
    print("Starting Synapse...")
    check_prerequisites()
    ensure_data_dir()

    print("Starting backend...")
    backend_proc = start_backend()

    if not wait_for_url(f"http://127.0.0.1:{BACKEND_PORT}/docs", "Backend"):
        backend_proc.terminate()
        sys.exit(1)

    print("Starting frontend...")
    frontend_proc = start_frontend()

    if not wait_for_url(f"http://127.0.0.1:{FRONTEND_PORT}", "Frontend"):
        backend_proc.terminate()
        frontend_proc.terminate()
        sys.exit(1)

    url = f"http://localhost:{FRONTEND_PORT}"
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    print(f"\nSynapse is running at {url}")
    print("Press Ctrl+C to stop.\n")

    def shutdown(sig, frame):
        print("\nStopping Synapse...")
        backend_proc.terminate()
        frontend_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    backend_proc.wait()


if __name__ == "__main__":
    main()
