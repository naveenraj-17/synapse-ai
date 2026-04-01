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
FRONTEND_DIR = PACKAGE_DIR.parent / "frontend"
ROOT_DIR = PACKAGE_DIR.parent

# ---------------------------------------------------------------------------
# Load .env from the project root BEFORE reading port defaults so that values
# set by `synapse setup` (or hand-edited .env) are honoured without the user
# having to export them manually in every shell session.
# ---------------------------------------------------------------------------
_ENV_FILE = ROOT_DIR / ".env"

def _load_dotenv(path: Path):
    """Minimal .env loader — only sets vars that are NOT already in the environment."""
    if not path.exists():
        return
    try:
        with open(path) as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip()
                # Don't override variables already set in the real environment
                if _key and _key not in os.environ:
                    os.environ[_key] = _val
    except Exception:
        pass  # non-fatal — env vars can still be set manually

_load_dotenv(_ENV_FILE)

DEFAULT_DATA_DIR = Path.home() / ".synapse" / "data"
DATA_DIR = Path(os.getenv("SYNAPSE_DATA_DIR", str(DEFAULT_DATA_DIR)))

DEFAULT_BACKEND_PORT = int(os.getenv("SYNAPSE_BACKEND_PORT", "8000"))
DEFAULT_FRONTEND_PORT = int(os.getenv("SYNAPSE_FRONTEND_PORT", "3000"))

# Runtime ports (may be overridden by CLI args — module-level aliases kept for
# backwards compatibility; actual values are resolved in _start_command)
BACKEND_PORT = DEFAULT_BACKEND_PORT
FRONTEND_PORT = DEFAULT_FRONTEND_PORT

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
    if shutil.which("npm") is None:
        errors.append("npm not found — install Node.js from https://nodejs.org/")
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


def start_backend(detach: bool = False, port: int | None = None, profile: bool = False):
    env = os.environ.copy()
    env["SYNAPSE_DATA_DIR"] = str(DATA_DIR)
    env["PYTHONPATH"] = str(BACKEND_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    if port is not None:
        env["SYNAPSE_BACKEND_PORT"] = str(port)
    if profile:
        env["SYNAPSE_PROFILING"] = "true"
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


def start_frontend(detach: bool = False, port: int | None = None, backend_port: int | None = None):
    next_dir = FRONTEND_DIR / ".next"
    if not next_dir.exists():
        print("Error: frontend is not built. Run the following first:")
        print(f"  cd {FRONTEND_DIR} && npm install && npm run build")
        sys.exit(1)
    env = os.environ.copy()
    _backend_port = backend_port if backend_port is not None else DEFAULT_BACKEND_PORT
    _frontend_port = port if port is not None else DEFAULT_FRONTEND_PORT
    # Always set these so Next.js picks up the correct URLs at runtime
    env["BACKEND_URL"] = f"http://127.0.0.1:{_backend_port}"
    env["NEXT_PUBLIC_BACKEND_PORT"] = str(_backend_port)
    env["SYNAPSE_FRONTEND_PORT"] = str(_frontend_port)
    env["SYNAPSE_BACKEND_PORT"] = str(_backend_port)
    kwargs = {}
    if detach:
        if os.name == "posix":
            kwargs["preexec_fn"] = os.setsid
        else:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        ["npm", "start", "--", "-p", str(_frontend_port), "-H", "0.0.0.0"],
        cwd=str(FRONTEND_DIR),
        env=env,
        **kwargs,
    )


def wait_for_url(url: str, name: str, timeout: int = 90) -> bool:
    start = time.time()
    port = url.split(":")[-1].split("/")[0]
    while True:
        elapsed = int(time.time() - start)
        if elapsed >= timeout:
            print()
            print(f"  Timeout waiting for {name} at {url}")
            print(f"  Check that nothing else is using port {port},")
            print(f"  or try 'synapse stop' then 'synapse start'.")
            return False
        try:
            urllib.request.urlopen(url, timeout=3)
            print(f"\r  {name} ready.                    ")
            return True
        except Exception:
            print(f"\r  Waiting for {name}... {elapsed}s", end="", flush=True)
            time.sleep(2)


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


def _start_command(
    detach: bool = False,
    no_browser: bool = False,
    backend_port: int | None = None,
    frontend_port: int | None = None,
    profile: bool = False,
):
    # Resolve effective ports: CLI arg > env var > default
    effective_backend_port = backend_port if backend_port is not None else DEFAULT_BACKEND_PORT
    effective_frontend_port = frontend_port if frontend_port is not None else DEFAULT_FRONTEND_PORT

    check_prerequisites()
    ensure_data_dir()

    # Prevent accidental foreground start if processes already running
    if not detach:
        bp = _read_pidfile(BACKEND_PID_FILE)
        fp = _read_pidfile(FRONTEND_PID_FILE)
        if bp and _is_running(bp):
            print(f"Backend already running (pid {bp}).")
            print("Run 'synapse stop' first, or add --detach to run alongside.")
            sys.exit(1)
        if fp and _is_running(fp):
            print(f"Frontend already running (pid {fp}).")
            print("Run 'synapse stop' first, or add --detach to run alongside.")
            sys.exit(1)

    print(f"Starting backend on port {effective_backend_port}...")
    try:
        backend_proc = start_backend(detach=detach, port=effective_backend_port, profile=profile)
        _write_pidfile(BACKEND_PID_FILE, backend_proc.pid)
    except Exception as e:
        print(f"Failed to start backend: {e}")
        sys.exit(1)

    if not wait_for_url(f"http://127.0.0.1:{effective_backend_port}/docs", "Backend"):
        try:
            backend_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    print(f"Starting frontend on port {effective_frontend_port}...")
    try:
        frontend_proc = start_frontend(
            detach=detach,
            port=effective_frontend_port,
            backend_port=effective_backend_port,
        )
        _write_pidfile(FRONTEND_PID_FILE, frontend_proc.pid)
    except Exception as e:
        print(f"Failed to start frontend: {e}")
        try:
            backend_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    if not wait_for_url(f"http://127.0.0.1:{effective_frontend_port}", "Frontend"):
        try:
            backend_proc.terminate()
        except Exception:
            pass
        try:
            frontend_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

    url = f"http://localhost:{effective_frontend_port}"
    if not no_browser and not detach:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    print(f"\nSynapse is running at {url}")
    if detach:
        print(f"  Backend pid:  {_read_pidfile(BACKEND_PID_FILE)}  (port {effective_backend_port})")
        print(f"  Frontend pid: {_read_pidfile(FRONTEND_PID_FILE)}  (port {effective_frontend_port})")
        print()
        print("Run 'synapse stop' to stop  |  'synapse status' to check")
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


def _profile_command(action: str, output: str | None = None, limit: int = 20, duration: int = 30):
    backend_port = int(os.getenv("SYNAPSE_BACKEND_PORT", str(DEFAULT_BACKEND_PORT)))
    base_url = f"http://127.0.0.1:{backend_port}/api/profiling"

    def _api(method: str, path: str, params: str = "") -> dict | str | None:
        url = f"{base_url}{path}"
        if params:
            url += f"?{params}"
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                ct = resp.headers.get("Content-Type", "")
                body = resp.read()
                if "application/json" in ct:
                    import json
                    return json.loads(body)
                return body.decode()
        except urllib.error.HTTPError as e:
            print(f"Error {e.code}: {e.read().decode()}")
            return None
        except Exception as e:
            print(f"Could not reach backend at {url}: {e}")
            print("Make sure Synapse is running (synapse start).")
            return None

    if action == "stats":
        data = _api("GET", "/stats")
        if not data:
            return
        if not data:
            print("No timing data yet. Send some requests first.")
            return
        col_w = max((len(k) for k in data), default=20)
        header = f"{'Endpoint':<{col_w}}  {'Count':>6}  {'Avg ms':>8}  {'p50 ms':>8}  {'p95 ms':>8}  {'p99 ms':>8}  {'Max ms':>8}"
        print(header)
        print("-" * len(header))
        for endpoint, s in sorted(data.items()):
            print(f"{endpoint:<{col_w}}  {s['count']:>6}  {s['avg_ms']:>8.1f}  {s['p50_ms']:>8.1f}  {s['p95_ms']:>8.1f}  {s['p99_ms']:>8.1f}  {s['max_ms']:>8.1f}")

    elif action == "reset":
        result = _api("DELETE", "/stats")
        if result:
            print("Timing stats reset.")

    elif action == "cpu-start":
        result = _api("POST", "/cpu/start")
        if result:
            print(result.get("status") or result.get("error"))

    elif action == "cpu-report":
        fmt = "html" if (output and output.endswith(".html")) else "text"
        result = _api("GET", "/cpu/report", f"format={fmt}")
        if result is None:
            return
        if output:
            Path(output).write_text(result)
            print(f"CPU profile saved to {output}")
        else:
            print(result)

    elif action == "memory-start":
        result = _api("POST", "/memory/start")
        if result:
            print(result.get("status") or result.get("error"))

    elif action == "memory-snapshot":
        data = _api("GET", "/memory/snapshot", f"limit={limit}")
        if not data:
            return
        if "error" in data:
            print(data["error"])
            return
        print(f"Current: {data['current_mb']} MB  |  Peak: {data['peak_mb']} MB\n")
        print(f"{'Size KB':>10}  {'Count':>6}  Location")
        print("-" * 60)
        for alloc in data["top_allocations"]:
            print(f"{alloc['size_kb']:>10.2f}  {alloc['count']:>6}  {alloc['file']}:{alloc['line']}")

    elif action == "spy":
        pid = _read_pidfile(BACKEND_PID_FILE)
        if not pid:
            print("Backend PID not found. Start with: synapse start --detach")
            return
        if not _is_running(pid):
            print(f"Backend process {pid} is not running.")
            return
        out_file = output or "profile.svg"
        cmd = ["py-spy", "record", "-o", out_file, "--pid", str(pid), "--duration", str(duration)]
        print(f"Running: {' '.join(cmd)}")
        print(f"Send requests to the backend during this {duration}s window...")
        try:
            subprocess.run(cmd, check=True)
            print(f"Flame graph saved to {out_file}")
        except FileNotFoundError:
            print("py-spy not found. Install it: pip install py-spy")
        except subprocess.CalledProcessError as e:
            print(f"py-spy failed: {e}")

    else:
        print(f"Unknown profile action: {action}")
        print("Available: stats, reset, cpu-start, cpu-report, memory-start, memory-snapshot, spy")


def main():
    parser = argparse.ArgumentParser(prog="synapse", description="Manage Synapse server (backend + frontend)")
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="Start backend and frontend")
    p_start.add_argument("--detach", "-d", action="store_true", help="Run processes in background and write pidfiles")
    p_start.add_argument("--no-browser", action="store_true", help="Do not open a browser on start")
    p_start.add_argument(
        "--backend-port", type=int, default=None, metavar="PORT",
        help=f"Port for the backend API server (overrides SYNAPSE_BACKEND_PORT env var, default: {DEFAULT_BACKEND_PORT})",
    )
    p_start.add_argument(
        "--frontend-port", type=int, default=None, metavar="PORT",
        help=f"Port for the frontend web UI (overrides SYNAPSE_FRONTEND_PORT env var, default: {DEFAULT_FRONTEND_PORT})",
    )
    p_start.add_argument("--profile", action="store_true", help="Enable performance profiling (sets SYNAPSE_PROFILING=true)")

    sub.add_parser("stop", help="Stop running backend and frontend (reads pidfiles)")
    sub.add_parser("status", help="Show status of backend and frontend")

    p_restart = sub.add_parser("restart", help="Restart backend and frontend")
    p_restart.add_argument("--detach", "-d", action="store_true", help="After restart, leave processes detached")
    p_restart.add_argument(
        "--backend-port", type=int, default=None, metavar="PORT",
        help=f"Port for the backend API server (overrides SYNAPSE_BACKEND_PORT env var, default: {DEFAULT_BACKEND_PORT})",
    )
    p_restart.add_argument(
        "--frontend-port", type=int, default=None, metavar="PORT",
        help=f"Port for the frontend web UI (overrides SYNAPSE_FRONTEND_PORT env var, default: {DEFAULT_FRONTEND_PORT})",
    )
    sub.add_parser("setup", help="Run interactive setup wizard to configure Synapse")

    p_profile = sub.add_parser("profile", help="Query and control backend performance profiling")
    p_profile.add_argument(
        "action",
        choices=["stats", "reset", "cpu-start", "cpu-report", "memory-start", "memory-snapshot", "spy"],
        help="stats: latency table | reset: clear stats | cpu-start/cpu-report: CPU profiling | memory-start/memory-snapshot: memory profiling | spy: py-spy flame graph",
    )
    p_profile.add_argument("--output", "-o", default=None, metavar="FILE", help="Output file (cpu-report: .html, spy: .svg)")
    p_profile.add_argument("--limit", type=int, default=20, metavar="N", help="Number of top allocations to show (memory-snapshot, default: 20)")
    p_profile.add_argument("--duration", type=int, default=30, metavar="SECS", help="Recording duration in seconds (spy, default: 30)")

    args = parser.parse_args()

    if args.cmd == "start" or args.cmd is None:
        # default to start when invoked without subcommand to preserve previous behaviour
        _start_command(
            detach=getattr(args, "detach", False),
            no_browser=getattr(args, "no_browser", False),
            backend_port=getattr(args, "backend_port", None),
            frontend_port=getattr(args, "frontend_port", None),
            profile=getattr(args, "profile", False),
        )
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
        _start_command(
            detach=getattr(args, "detach", False),
            backend_port=getattr(args, "backend_port", None),
            frontend_port=getattr(args, "frontend_port", None),
        )
    elif args.cmd == "profile":
        _profile_command(
            action=args.action,
            output=args.output,
            limit=args.limit,
            duration=args.duration,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
