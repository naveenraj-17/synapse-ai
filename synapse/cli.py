"""
Synapse CLI - starts the backend and frontend, then opens the browser.
"""
import os
import sys
import stat
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

IS_WIN = sys.platform == "win32"


def _rmtree(path):
    """Remove a directory tree, handling Windows read-only/locked files."""
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=_onerror)

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
    """Minimal .env loader -- only sets vars that are NOT already in the environment."""
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
        pass  # non-fatal -- env vars can still be set manually

_load_dotenv(_ENV_FILE)

DEFAULT_DATA_DIR = Path.home() / ".synapse" / "data"
# Always resolve to absolute path so the value is correct regardless of CWD.
# When SYNAPSE_DATA_DIR is a relative path (e.g. "data" in .env), resolve it
# relative to the project root rather than wherever `synapse` was invoked from.
_raw_data_dir = os.getenv("SYNAPSE_DATA_DIR", str(DEFAULT_DATA_DIR))
if not os.path.isabs(_raw_data_dir):
    DATA_DIR = (ROOT_DIR / _raw_data_dir).resolve()
else:
    DATA_DIR = Path(_raw_data_dir).resolve()

DEFAULT_BACKEND_PORT = int(os.getenv("SYNAPSE_BACKEND_PORT", "8765"))
DEFAULT_FRONTEND_PORT = int(os.getenv("SYNAPSE_FRONTEND_PORT", "3000"))

# Runtime ports (may be overridden by CLI args -- module-level aliases kept for
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


def _find_node_exe_win():
    """Windows: find node.exe by probing known install locations (bypasses stale PATH cache).
    Returns (node_exe_path, bin_dir) or (None, None)."""
    import os as _os
    pf   = _os.environ.get("ProgramFiles",       r"C:\Program Files")
    pf86 = _os.environ.get("ProgramFiles(x86)",  r"C:\Program Files (x86)")
    lad  = _os.environ.get("LocalAppData",        "")
    appd = _os.environ.get("APPDATA",             "")

    candidates = []
    # Standard install dirs
    for d in [
        _os.path.join(pf,   "nodejs"),
        _os.path.join(pf86, "nodejs"),
        _os.path.join(lad,  "Programs", "nodejs"),
        _os.path.join(lad,  "nodejs"),
    ]:
        exe = _os.path.join(d, "node.exe")
        if _os.path.isfile(exe):
            candidates.append((exe, d))
    # nvm-windows
    nvm_root = _os.path.join(appd, "nvm")
    if _os.path.isdir(nvm_root):
        for entry in sorted(_os.listdir(nvm_root), reverse=True):
            exe = _os.path.join(nvm_root, entry, "node.exe")
            if _os.path.isfile(exe):
                candidates.append((exe, _os.path.join(nvm_root, entry)))
    # PATH entries
    for entry in _os.environ.get("PATH", "").split(_os.pathsep):
        exe = _os.path.join(entry.strip(), "node.exe")
        if _os.path.isfile(exe):
            candidates.append((exe, entry.strip()))

    MIN = (20, 9, 0)
    for node_exe, bin_dir in candidates:
        try:
            r = subprocess.run([node_exe, "--version"], capture_output=True, text=True, timeout=5)
            ver_str = r.stdout.strip().lstrip("v")
            ver_tuple = tuple(int(x) for x in ver_str.split(".")[:3])
            if ver_tuple >= MIN:
                return node_exe, bin_dir
        except Exception:
            pass
    return None, None


def _ensure_node_in_path_win():
    """Windows: make sure the Node.js bin dir is in PATH for this process.
    Returns True if a suitable node was found and PATH was updated."""
    node_exe, bin_dir = _find_node_exe_win()
    if node_exe:
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return True
    return False


def _npm_command():
    """Return the correct npm executable for the current OS.
    On Windows, 'npm' is a .cmd file and must be invoked explicitly or via shell."""
    if IS_WIN:
        # npm.cmd is the real entry-point on Windows; avoids needing shell=True
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
        if npm_cmd:
            return npm_cmd
        # Fallback: look next to node.exe
        node_exe, bin_dir = _find_node_exe_win()
        if bin_dir:
            npm_candidate = os.path.join(bin_dir, "npm.cmd")
            if os.path.isfile(npm_candidate):
                return npm_candidate
        return "npm"
    return "npm"


def check_prerequisites():
    errors = []
    if IS_WIN:
        # On Windows, PATH may be stale after a fresh install -- probe directly
        if not _ensure_node_in_path_win():
            errors.append("Node.js 20.9.0+ not found -- install from https://nodejs.org/ and re-run.")
    else:
        node = shutil.which("node")
        if node is None:
            errors.append("node not found -- install Node.js 20.9.0+ from https://nodejs.org/")
        else:
            try:
                r = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5)
                ver_str = r.stdout.strip().lstrip("v")
                ver_tuple = tuple(int(x) for x in ver_str.split(".")[:3])
                min_str = ".".join(str(x) for x in MIN_NODE)
                if ver_tuple < MIN_NODE:
                    errors.append(
                        f"Node.js {ver_str} is too old (need {min_str}+) -- "
                        "upgrade from https://nodejs.org/"
                    )
            except Exception:
                pass  # version check failed, proceed and let Node report its own errors
        if shutil.which("npm") is None:
            errors.append(f"npm not found -- install Node.js {'.'.join(str(x) for x in MIN_NODE)}+ from https://nodejs.org/")
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
    npm = _npm_command()
    return subprocess.Popen(
        [npm, "start"],
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


def _kill_proc_tree(proc: subprocess.Popen, timeout: int = 5) -> None:
    """Kill a process AND all its descendants.

    On Windows, terminate() only kills the outermost batch wrapper (.cmd);
    child node.exe processes become orphans.  taskkill /F /T kills the whole
    process tree including every grandchild.

    On Unix, send SIGTERM to the process group so npm -> node children all die.
    """
    if IS_WIN:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    else:
        # Try to kill the entire process group (handles npm -> node chains)
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        # Wait then force-kill if still alive
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _terminate_pid(pid: int, name: str, timeout: int = 5) -> bool:
    """Terminate a process by PID, with fallback to SIGKILL."""
    if IS_WIN:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
            )
            return True
        except Exception as e:
            print(f"  Could not kill {name} ({pid}): {e}")
            return False
    else:
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
        # Kill full process trees -- on Windows terminate() leaves node children alive
        _kill_proc_tree(frontend_proc)
        _kill_proc_tree(backend_proc)
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


def _upgrade_command():
    """Pull latest code, rebuild venv + pip deps, rebuild frontend."""
    print("\n=== Synapse AI -- Upgrade ===")

    # 1. Stop running services first
    print("\nStopping running services...")
    _stop_command()

    # 2. Pull latest code
    print("\n==> Pulling latest code...")
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT_DIR), "pull", "--ff-only"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            output_text = result.stdout.strip()
            if "Already up to date" in output_text:
                print("  Already up to date.")
            else:
                print(f"  Updated:\n{output_text}")
        else:
            print(f"  Warning: git pull failed (exit {result.returncode}).")
            if result.stderr.strip():
                print(f"  {result.stderr.strip()}")
    except FileNotFoundError:
        print("  Warning: git not found -- skipping update.")
    except Exception as e:
        print(f"  Warning: git pull error: {e}")

    # 3. Rebuild Python venv
    print("\n==> Rebuilding backend virtual environment...")
    venv_dir = BACKEND_DIR / "venv"
    python_exe = venv_dir / ("Scripts/python.exe" if IS_WIN else "bin/python")

    # Re-create venv
    if venv_dir.exists():
        print("  Removing old virtual environment...")
        _rmtree(venv_dir)
    print("  Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

    # Upgrade pip
    print("  Upgrading pip...")
    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True)

    # Install requirements
    req_txt = BACKEND_DIR / "requirements.txt"
    if req_txt.exists():
        print("  Installing backend requirements...")
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "-r", str(req_txt)])
    else:
        print(f"  Warning: {req_txt} not found -- skipping requirements.")

    # Re-install synapse package in editable mode
    print("  Reinstalling Synapse package...")
    subprocess.check_call([str(python_exe), "-m", "pip", "install", "-e", str(ROOT_DIR)])
    print("  Backend rebuild complete.")

    # 4. Rebuild frontend
    print("\n==> Rebuilding frontend (npm install + npm run build)...")
    npm = _npm_command()

    # Remove node_modules so we get a clean install
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        print("  Removing old node_modules...")
        _rmtree(node_modules)

    print("  Running npm install...")
    subprocess.check_call([npm, "install"], cwd=str(FRONTEND_DIR))

    print("  Building frontend...")
    subprocess.check_call([npm, "run", "build"], cwd=str(FRONTEND_DIR))
    print("  Frontend rebuild complete.")

    print("\n=== Upgrade complete! ===")
    print("Run 'synapse start' to launch the updated Synapse.")


def _get_synapse_install_dir() -> Path | None:
    """Return the platform-specific SynapseAI install directory written by setup.sh / setup.ps1."""
    if IS_WIN:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            return Path(local_app_data) / "Programs" / "SynapseAI"
        return None
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SynapseAI"
    else:  # Linux
        return Path.home() / ".local" / "share" / "SynapseAI"


def _uninstall_command(keep_data: bool = False):
    """Stop services and remove all Synapse AI files."""
    print("\n=== Synapse AI -- Uninstall ===")
    print()

    # Resolve the platform install directory up-front so later steps can reference it.
    platform_install = _get_synapse_install_dir()

    # Confirm
    try:
        answer = input(
            "This will PERMANENTLY remove Synapse AI and all its files.\n"
            "Type 'yes' to confirm: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return

    if answer != "yes":
        print("Aborted.")
        return

    # 1. Stop running services
    print("\nStopping running services...")
    try:
        _stop_command()
    except Exception as e:
        print(f"  Warning: could not stop services cleanly: {e}")

    # 2. Remove startup entries (systemd / LaunchAgent / Registry)
    print("Removing startup registration...")
    _platform = sys.platform
    if IS_WIN:
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, "SynapseAI")
                print("  Removed Windows startup entry.")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass
    elif _platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.synapse-ai.server.plist"
        if plist.exists():
            try:
                subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
                plist.unlink()
                print("  Removed macOS LaunchAgent.")
            except Exception:
                pass
    else:  # Linux
        service = Path.home() / ".config" / "systemd" / "user" / "synapse-ai.service"
        if service.exists():
            try:
                subprocess.run(["systemctl", "--user", "disable", "synapse-ai.service"],
                               check=False, capture_output=True)
                service.unlink()
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
                print("  Removed systemd user service.")
            except Exception:
                pass

    # 3. Remove data directory (optional)
    if not keep_data and DATA_DIR.exists():
        try:
            _rmtree(DATA_DIR)
            print(f"  Removed data directory: {DATA_DIR}")
        except Exception as e:
            print(f"  Warning: could not remove data dir {DATA_DIR}: {e}")
    # Also remove ~/.synapse parent directory (config files, etc.)
    if not keep_data:
        synapse_home = Path.home() / ".synapse"
        if synapse_home.exists():
            try:
                _rmtree(synapse_home)
                print(f"  Removed Synapse home: {synapse_home}")
            except Exception as e:
                print(f"  Warning: could not fully remove {synapse_home}: {e}")

    # 4. Remove the installation directory/directories
    # Collect unique dirs: the running ROOT_DIR plus the platform standard install location
    # (e.g. ~/.local/share/SynapseAI on Linux, %LOCALAPPDATA%\Programs\SynapseAI on Windows).
    _dirs_to_remove: list[Path] = [ROOT_DIR]
    if platform_install and platform_install.resolve() != ROOT_DIR.resolve():
        _dirs_to_remove.append(platform_install)

    for _install_dir in _dirs_to_remove:
        if not _install_dir.exists():
            continue
        print(f"\nRemoving installation directory: {_install_dir}")
        try:
            # Remove large subdirectories first to avoid partial-removal hangs
            for _big in (
                _install_dir / "backend" / "venv",
                _install_dir / "frontend" / "node_modules",
            ):
                if _big.exists():
                    _rmtree(_big)
            _rmtree(_install_dir)
            print("  Removed.")
        except Exception as e:
            print(f"  Warning: could not fully remove {_install_dir}: {e}")
            print("  You may need to delete it manually.")

    # 5. Remove the pip-installed `synapse` console script
    print("\nUninstalling Python package...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "synapse-ai"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("  Removed pip package synapse-ai.")
        else:
            # Try alternate package name
            result2 = subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", "-y", "synapse"],
                capture_output=True, text=True,
            )
            if result2.returncode == 0:
                print("  Removed pip package synapse.")
            else:
                print("  Package not found in pip (may already be removed).")
    except Exception as e:
        print(f"  Warning: pip uninstall failed: {e}")

    # Fallback: remove the synapse executable directly if it still exists on PATH
    synapse_exe = shutil.which("synapse")
    if synapse_exe:
        try:
            Path(synapse_exe).unlink(missing_ok=True)
            print(f"  Removed executable: {synapse_exe}")
        except PermissionError:
            print(f"  Warning: no permission to remove {synapse_exe} -- delete it manually.")
        except Exception as e:
            print(f"  Warning: could not remove {synapse_exe}: {e}")

    # Windows: also scrub leftover files from the Python Scripts directory
    if IS_WIN:
        scripts_dir = Path(sys.executable).parent / "Scripts"
        for name in ("synapse.exe", "synapse-script.py"):
            candidate = scripts_dir / name
            if candidate.exists():
                try:
                    candidate.unlink()
                    print(f"  Removed: {candidate}")
                except Exception as e:
                    print(f"  Warning: could not remove {candidate}: {e}")

    # 6. Clean PATH entries from shell rc files (Unix) / registry + PS profiles (Windows)
    # Build the set of bin-dir strings to purge (covers both ROOT_DIR and the platform
    # install dir written by setup.sh / setup.ps1).
    _bin_dirs_lower = {str(ROOT_DIR / "bin").lower(), str(ROOT_DIR).lower()}
    if platform_install:
        _bin_dirs_lower.add(str(platform_install / "bin").lower())
        _bin_dirs_lower.add(str(platform_install).lower())

    if IS_WIN:
        # --- Windows registry (user PATH) ---
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0, winreg.KEY_READ | winreg.KEY_SET_VALUE,
            )
            try:
                path_val, reg_type = winreg.QueryValueEx(key, "PATH")
                parts = [p for p in path_val.split(";") if p]
                new_parts = [p for p in parts if p.lower() not in _bin_dirs_lower]
                if len(new_parts) != len(parts):
                    winreg.SetValueEx(key, "PATH", 0, reg_type, ";".join(new_parts))
                    print("  Cleaned PATH from Windows user environment registry.")
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass

        # --- Windows PowerShell profiles (written by setup.ps1) ---
        docs = Path.home() / "Documents"
        for ps_dir in ("PowerShell", "WindowsPowerShell"):
            ps_profile = docs / ps_dir / "profile.ps1"
            if not ps_profile.exists():
                continue
            try:
                lines = ps_profile.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                new_lines = [l for l in lines if "SynapseAI" not in l and "Synapse AI" not in l]
                if len(new_lines) != len(lines):
                    ps_profile.write_text("".join(new_lines), encoding="utf-8")
                    print(f"  Cleaned PATH entry from PowerShell profile: {ps_profile}")
            except Exception:
                pass
    else:
        for rc_file in (
            Path.home() / ".bashrc",
            Path.home() / ".zshrc",
            Path.home() / ".bash_profile",
            Path.home() / ".profile",
        ):
            if rc_file.exists():
                try:
                    lines = rc_file.read_text().splitlines(keepends=True)
                    new_lines = [l for l in lines
                                 if "SynapseAI" not in l and "Synapse AI" not in l
                                 and not any(d in l for d in _bin_dirs_lower)]
                    if len(new_lines) != len(lines):
                        rc_file.write_text("".join(new_lines))
                        print(f"  Cleaned PATH entry from {rc_file}")
                except Exception:
                    pass

    print("\n=== Synapse AI has been uninstalled. Goodbye! ===")


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


MIN_PYTHON = (3, 11)
MIN_NODE   = (20, 9, 0)


def _warn_versions():
    """Warn (non-fatally) if Python or Node.js versions are below the minimum required."""
    # ── Python ───────────────────────────────────────────────────────────────
    py = sys.version_info[:2]
    if py < MIN_PYTHON:
        print(
            f"Warning: Python {py[0]}.{py[1]} detected -- "
            f"Synapse requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+.\n"
            "  Please switch to Python 3.11 or newer (https://www.python.org/downloads/)\n"
            "  and reinstall: pip install synapse-ai"
        )

    # ── Node.js ───────────────────────────────────────────────────────────────
    node = None
    if IS_WIN:
        node, _ = _find_node_exe_win()
        if node is None:
            node = shutil.which("node")
    else:
        node = shutil.which("node")

    if node is None:
        print(
            f"Warning: node not found -- Node.js {'.'.join(str(x) for x in MIN_NODE)}+ is required.\n"
            "  Install from https://nodejs.org/"
        )
    else:
        try:
            r = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5)
            ver_str = r.stdout.strip().lstrip("v")
            ver_tuple = tuple(int(x) for x in ver_str.split(".")[:3])
            if ver_tuple < MIN_NODE:
                min_str = ".".join(str(x) for x in MIN_NODE)
                print(
                    f"Warning: Node.js {ver_str} detected -- "
                    f"Synapse requires Node.js {min_str}+.\n"
                    f"  Please upgrade from https://nodejs.org/\n"
                    f"  After upgrading, rebuild the frontend:\n"
                    f"    cd {FRONTEND_DIR} && npm install && npm run build"
                )
        except Exception:
            pass  # version check failed; let downstream tools surface the error


def main():
    _warn_versions()
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

    # upgrade: pull code and rebuild everything
    sub.add_parser(
        "upgrade",
        help="Pull latest code, rebuild backend venv + requirements, rebuild frontend (npm install + npm run build)",
    )

    # uninstall: stop + wipe everything
    p_uninstall = sub.add_parser("uninstall", help="Stop services and remove all Synapse AI files")
    p_uninstall.add_argument(
        "--keep-data", action="store_true",
        help="Keep the data directory (~/.synapse) when uninstalling",
    )

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
    elif args.cmd == "upgrade":
        _upgrade_command()
    elif args.cmd == "uninstall":
        _uninstall_command(keep_data=getattr(args, "keep_data", False))
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
