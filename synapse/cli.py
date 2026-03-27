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
import argparse
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

# PID files
BACKEND_PID_FILE = DATA_DIR / "backend.pid"
FRONTEND_PID_FILE = DATA_DIR / "frontend.pid"


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


def start_backend(detach: bool = False):
    env = os.environ.copy()
    env["SYNAPSE_DATA_DIR"] = str(DATA_DIR)
    env["PYTHONPATH"] = str(BACKEND_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    kwargs = {}
    if detach:
        if os.name == "posix":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [sys.executable, str(BACKEND_DIR / "main.py")],
        cwd=str(BACKEND_DIR),
        env=env,
        **kwargs,
    )


def start_frontend(detach: bool = False):
    if not FRONTEND_DIR.exists():
        print("Error: bundled frontend not found. This package may need to be rebuilt.")
        print("       Run: bash scripts/build_frontend.sh  (developer only)")
        sys.exit(1)
    env = os.environ.copy()
    env["PORT"] = str(FRONTEND_PORT)
    env["HOSTNAME"] = "0.0.0.0"
    env["BACKEND_URL"] = f"http://127.0.0.1:{BACKEND_PORT}"
    kwargs = {}
    if detach:
        if os.name == "posix":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        ["node", str(FRONTEND_DIR / "server.js")],
        cwd=str(FRONTEND_DIR),
        env=env,
        **kwargs,
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


def _write_pidfile(path: Path, pid: int):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(pid))
    except Exception as e:
        print(f"Warning: could not write pidfile {path}: {e}")


def _read_pidfile(path: Path):
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    return True


def _terminate_pid(pid: int, name: str, timeout: int = 5) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"  Could not signal {name} ({pid}): {e}")
        return False
    start = time.time()
    while time.time() - start < timeout:
        if not _is_running(pid):
            return True
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    return not _is_running(pid)


def _start_command(detach: bool = False, no_browser: bool = False):
    check_prerequisites()
    ensure_data_dir()

    # Prevent accidental foreground start if processes already running
    if not detach:
        bp = _read_pidfile(BACKEND_PID_FILE)
        fp = _read_pidfile(FRONTEND_PID_FILE)
        if (bp and _is_running(bp)) or (fp and _is_running(fp)):
            print("Backend or frontend already running. Stop them first or use --detach.")
            sys.exit(1)

    print("Starting backend...")
    try:
        backend_proc = start_backend(detach=detach)
        _write_pidfile(BACKEND_PID_FILE, backend_proc.pid)
    except Exception as e:
        print(f"Failed to start backend: {e}")
        sys.exit(1)

    if not wait_for_url(f"http://127.0.0.1:{BACKEND_PORT}/docs", "Backend"):
        try:
            backend_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    print("Starting frontend...")
    try:
        frontend_proc = start_frontend(detach=detach)
        _write_pidfile(FRONTEND_PID_FILE, frontend_proc.pid)
    except Exception as e:
        print(f"Failed to start frontend: {e}")
        try:
            backend_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    if not wait_for_url(f"http://127.0.0.1:{FRONTEND_PORT}", "Frontend"):
        try:
            backend_proc.terminate()
        except Exception:
            pass
        try:
            frontend_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    url = f"http://localhost:{FRONTEND_PORT}"
    if not no_browser and not detach:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    print(f"\nSynapse is running at {url}")
    if detach:
        print(f"  Backend pid: {_read_pidfile(BACKEND_PID_FILE)}")
        print(f"  Frontend pid: {_read_pidfile(FRONTEND_PID_FILE)}")
        return

    print("Press Ctrl+C to stop.\n")

    def _shutdown(sig, frame):
        print("\nStopping Synapse...")
        try:
            frontend_proc.terminate()
        except Exception:
            pass
        try:
            backend_proc.terminate()
        except Exception:
            pass
        try:
            if BACKEND_PID_FILE.exists():
                BACKEND_PID_FILE.unlink()
        except Exception:
            pass
        try:
            if FRONTEND_PID_FILE.exists():
                FRONTEND_PID_FILE.unlink()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    backend_proc.wait()


def _stop_command():
    for name, pidfile in (("frontend", FRONTEND_PID_FILE), ("backend", BACKEND_PID_FILE)):
        pid = _read_pidfile(pidfile)
        if not pid:
            print(f"{name.capitalize()}: not running (no pidfile)")
            continue
        if not _is_running(pid):
            print(f"{name.capitalize()}: process {pid} not running; removing pidfile.")
            try:
                pidfile.unlink()
            except Exception:
                pass
            continue
        print(f"Stopping {name} (pid {pid})...")
        ok = _terminate_pid(pid, name)
        if ok:
            print(f"  {name} stopped.")
            try:
                pidfile.unlink()
            except Exception:
                pass
        else:
            print(f"  Failed to stop {name}.")


def _status_command():
    for name, pidfile in (("backend", BACKEND_PID_FILE), ("frontend", FRONTEND_PID_FILE)):
        pid = _read_pidfile(pidfile)
        if not pid:
            print(f"{name}: not running")
            continue
        running = _is_running(pid)
        print(f"{name}: {'running' if running else 'stale pid ' + str(pid)}")


def main():
    parser = argparse.ArgumentParser(prog="synapse", description="Manage Synapse server (backend + frontend)")
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="Start backend and frontend")
    p_start.add_argument("--detach", "-d", action="store_true", help="Run processes in background and write pidfiles")
    p_start.add_argument("--no-browser", action="store_true", help="Do not open a browser on start")

    sub.add_parser("stop", help="Stop running backend and frontend (reads pidfiles)")
    sub.add_parser("status", help="Show status of backend and frontend")

    p_restart = sub.add_parser("restart", help="Restart backend and frontend")
    p_restart.add_argument("--detach", "-d", action="store_true", help="After restart, leave processes detached")
    sub.add_parser("setup", help="Run interactive setup wizard to configure Synapse")

    args = parser.parse_args()

    if args.cmd == "start" or args.cmd is None:
        # default to start when invoked without subcommand to preserve previous behaviour
        _start_command(detach=getattr(args, "detach", False), no_browser=getattr(args, "no_browser", False))
    elif args.cmd == "stop":
        _stop_command()
    elif args.cmd == "setup":
        try:
            from synapse import setup_wizard
            setup_wizard.run()
        except Exception as e:
            print(f"Failed to run setup wizard: {e}")
    elif args.cmd == "status":
        _status_command()
    elif args.cmd == "restart":
        _stop_command()
        _start_command(detach=getattr(args, "detach", False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
