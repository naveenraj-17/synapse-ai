"""
Synapse AI — Interactive Setup Wizard
Guides the user through configuration, installs dependencies, and starts both servers.
Uses only Python stdlib so it works before the venv exists.
"""
import json
import os
import stat
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
ENV_FILE = os.path.join(ROOT_DIR, ".env")

# ---------------------------------------------------------------------------
# Load .env BEFORE computing DATA_DIR so that setup.py and cli.py always
# agree on the same data directory (e.g. SYNAPSE_DATA_DIR=backend/data).
# ---------------------------------------------------------------------------
def _load_dotenv_early(path):
    """Minimal .env loader — only sets vars not already in the environment."""
    if not os.path.exists(path):
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
                if _key and _key not in os.environ:
                    os.environ[_key] = _val
    except Exception:
        pass

_load_dotenv_early(ENV_FILE)

# Resolve DATA_DIR: relative paths are anchored to ROOT_DIR (same logic as cli.py)
_raw_data_dir = os.environ.get("SYNAPSE_DATA_DIR", os.path.join(BACKEND_DIR, "data"))
if not os.path.isabs(_raw_data_dir):
    DATA_DIR = os.path.normpath(os.path.join(ROOT_DIR, _raw_data_dir))
else:
    DATA_DIR = _raw_data_dir

EXAMPLES_DIR = os.path.join(BACKEND_DIR, "examples")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
CREDENTIALS_FILE = os.path.join(DATA_DIR, "credentials.json")

# Port defaults — read from env first so an existing .env is respected
DEFAULT_BACKEND_PORT = int(os.environ.get("SYNAPSE_BACKEND_PORT", "8000"))
DEFAULT_FRONTEND_PORT = int(os.environ.get("SYNAPSE_FRONTEND_PORT", "3000"))

IS_WIN = sys.platform == "win32"
VENV_DIR = os.path.join(BACKEND_DIR, "venv")
PYTHON_EXE = os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "python" + (".exe" if IS_WIN else ""))
PIP_EXE    = os.path.join(VENV_DIR, "Scripts" if IS_WIN else "bin", "pip" + (".exe" if IS_WIN else ""))

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
class C:
    BOLD   = '\033[1m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    RESET  = '\033[0m'

def _c(color, text): return f"{color}{text}{C.RESET}"
def step(msg):    print(f"\n{C.BLUE}{C.BOLD}==> {msg}{C.RESET}")
def ok(msg):      print(f"{C.GREEN}✓  {msg}{C.RESET}")
def warn(msg):    print(f"{C.YELLOW}⚠  {msg}{C.RESET}")
def err(msg):     print(f"{C.RED}✗  {msg}{C.RESET}")
def info(msg):    print(f"   {msg}")

# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"   {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else default

def ask_yn(prompt, default="n"):
    hint = "(Y/n)" if default.lower() == "y" else "(y/N)"
    val = ask(f"{prompt} {hint}", default).lower()
    return val in ("y", "yes")

def ask_choice(prompt, options):
    """Show numbered list and return the chosen item."""
    for i, opt in enumerate(options, 1):
        print(f"   {_c(C.CYAN, str(i))}.  {opt}")
    while True:
        raw = ask(prompt)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        warn(f"Enter a number between 1 and {len(options)}.")

# ---------------------------------------------------------------------------
# OS Detection & Auto-Install Helpers
# ---------------------------------------------------------------------------
def get_os_type():
    """Get OS type: 'linux', 'darwin', 'windows'"""
    return sys.platform

def get_linux_distro():
    """Get Linux distribution type"""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    return line.split("=")[1].strip().strip('"')
    except:
        pass
    return None

def install_npm():
    """Auto-install npm/Node.js if not found"""
    step("Installing Node.js and npm")
    
    os_type = get_os_type()
    
    if IS_WIN:
        info("Please download and install Node.js (v20.9.0 or higher) from https://nodejs.org/")
        info("Then re-run this setup script.")
        err("Node.js installation required.")
        sys.exit(1)
    elif os_type == "darwin":
        info("Installing Node.js via Homebrew...")
        try:
            subprocess.check_call(["brew", "install", "node"])
            ok("Node.js installed successfully.")
        except FileNotFoundError:
            err("Homebrew not found. Please install from https://brew.sh")
            sys.exit(1)
        except subprocess.CalledProcessError:
            err("Failed to install Node.js via Homebrew.")
            sys.exit(1)
    else:  # Linux
        distro = get_linux_distro()
        
        if distro in ("ubuntu", "debian"):
            info("Installing Node.js on Ubuntu/Debian via NodeSource...")
            try:
                # Use NodeSource setup script for latest LTS
                subprocess.check_call(["curl", "-fsSL", "https://deb.nodesource.com/setup_20.x", "-o", "nodesource_setup.sh"])
                subprocess.check_call(["sudo", "bash", "nodesource_setup.sh"])
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "nodejs"])
                subprocess.check_call(["rm", "nodesource_setup.sh"])
                ok("Node.js installed successfully.")
            except Exception as e:
                warn(f"NodeSource installation failed: {e}. Trying default repos...")
                try:
                    subprocess.check_call(["sudo", "apt-get", "update"])
                    subprocess.check_call(["sudo", "apt-get", "install", "-y", "nodejs", "npm"])
                    ok("Node.js installed successfully.")
                except subprocess.CalledProcessError:
                    err("Failed to install Node.js.")
                    sys.exit(1)
        elif distro in ("fedora", "rhel", "centos"):
            info("Installing Node.js on Fedora/RHEL...")
            try:
                subprocess.check_call(["sudo", "dnf", "install", "-y", "nodejs", "npm"])
                ok("Node.js installed successfully.")
            except subprocess.CalledProcessError:
                err("Failed to install Node.js.")
                sys.exit(1)
        elif distro in ("arch", "manjaro"):
            info("Installing Node.js on Arch/Manjaro...")
            try:
                subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "nodejs", "npm"])
                ok("Node.js installed successfully.")
            except subprocess.CalledProcessError:
                err("Failed to install Node.js.")
                sys.exit(1)
        else:
            warn(f"Unknown Linux distribution: {distro}")
            info("Please install Node.js manually from https://nodejs.org/")
            sys.exit(1)

def install_postgresql():
    """Auto-install PostgreSQL if not found"""
    step("Installing PostgreSQL")
    
    os_type = get_os_type()
    
    if IS_WIN:
        info("PostgreSQL installation is required for the Coding Agent on Windows.")
        info("1. Download the installer from: https://www.postgresql.org/download/windows/")
        info("2. Run the installer and follow the instructions.")
        info("3. CRITICAL: Add the PostgreSQL bin directory to your System PATH:")
        info("   - Example: C:\\Program Files\\PostgreSQL\\15\\bin")
        info("   - Search for 'Environment Variables' in Start menu")
        info("   - Edit 'Path' in System Variables and add the bin directory")
        info("4. Verify by opening a NEW command prompt and running: psql --version")
        info("")
        warn("Please complete these steps, then re-run this setup script.")
        err("PostgreSQL installation/PATH configuration required.")
        sys.exit(1)
    elif os_type == "darwin":
        info("Installing PostgreSQL via Homebrew...")
        try:
            subprocess.check_call(["brew", "install", "postgresql@15"])
            subprocess.check_call(["brew", "services", "start", "postgresql@15"])
            ok("PostgreSQL installed and started.")
        except FileNotFoundError:
            err("Homebrew not found. Please install from https://brew.sh")
            sys.exit(1)
        except subprocess.CalledProcessError:
            err("Failed to install PostgreSQL.")
            sys.exit(1)
    else:  # Linux
        distro = get_linux_distro()
        
        if distro in ("ubuntu", "debian"):
            info("Installing PostgreSQL on Ubuntu/Debian...")
            try:
                subprocess.check_call(["sudo", "apt-get", "update"])
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "postgresql", "postgresql-contrib"])
                subprocess.check_call(["sudo", "systemctl", "start", "postgresql"])
                ok("PostgreSQL installed and started.")
            except subprocess.CalledProcessError:
                err("Failed to install PostgreSQL.")
                sys.exit(1)
        elif distro in ("fedora", "rhel", "centos"):
            info("Installing PostgreSQL on Fedora/RHEL...")
            try:
                subprocess.check_call(["sudo", "dnf", "install", "-y", "postgresql-server", "postgresql-contrib"])
                subprocess.check_call(["sudo", "systemctl", "start", "postgresql"])
                ok("PostgreSQL installed and started.")
            except subprocess.CalledProcessError:
                err("Failed to install PostgreSQL.")
                sys.exit(1)
        elif distro in ("arch", "manjaro"):
            info("Installing PostgreSQL on Arch/Manjaro...")
            try:
                subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "postgresql"])
                ok("PostgreSQL installed. Start with: sudo systemctl start postgresql")
            except subprocess.CalledProcessError:
                err("Failed to install PostgreSQL.")
                sys.exit(1)
        else:
            err(f"Unknown Linux distribution: {distro}")
            sys.exit(1)

def install_pgvector():
    """Install pgvector extension in PostgreSQL"""
    step("Installing pgvector Extension")
    
    os_type = get_os_type()
    
    if IS_WIN:
        warn("On Windows, please install pgvector manually or use WSL.")
        return False
    
    distro = get_linux_distro() if os_type != "darwin" else "darwin"
    
    try:
        if os_type == "darwin":
            subprocess.check_call(["brew", "install", "pgvector"])
        elif distro in ("ubuntu", "debian"):
            subprocess.check_call(["sudo", "apt-get", "install", "-y", "postgresql-contrib"])
            subprocess.check_call(["sudo", "apt-get", "install", "-y", "postgresql-15-pgvector"])
        elif distro in ("fedora", "rhel"):
            subprocess.check_call(["sudo", "dnf", "install", "-y", "pgvector"])
        elif distro in ("arch", "manjaro"):
            subprocess.check_call(["sudo", "pacman", "-S", "--noconfirm", "pgvector"])
        else:
            warn(f"pgvector installation not automated for {distro}. Please install manually.")
            return False
        ok("pgvector installed.")
        return True
    except subprocess.CalledProcessError:
        warn("pgvector installation had issues. You may need to install manually.")
        return False

def create_postgresql_db(db_user, db_password, db_name="synapse"):
    """Create a PostgreSQL database and return the connection URL"""
    step("Setting up PostgreSQL Database")
    
    try:
        # Try to create database and user using psql
        # First, get superuser password or use peer authentication
        info(f"Creating database '{db_name}' and user '{db_user}'...")
        
        # Create user if not exists
        create_user_sql = f"CREATE USER {db_user} PASSWORD '{db_password}';"
        create_db_sql = f"CREATE DATABASE {db_name} OWNER {db_user};"
        alter_priv_sql = f"ALTER ROLE {db_user} CREATEDB;"
        
        try:
            # Try with sudo -u postgres (Linux)
            subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c", alter_priv_sql],
                check=True, capture_output=True, timeout=10
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try direct connection
            pass
        
        try:
            subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c", create_user_sql],
                check=False, capture_output=True, timeout=10
            )
        except:
            pass
        
        try:
            subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-c", create_db_sql],
                check=False, capture_output=True, timeout=10
            )
        except:
            pass
        
        # Try to create vector extension
        try:
            subprocess.run(
                ["sudo", "-u", "postgres", "psql", "-d", db_name, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"],
                check=False, capture_output=True, timeout=10
            )
            ok("Vector extension created.")
        except:
            warn("Could not create vector extension. You may need to do it manually.")
        
        url = f"postgresql+psycopg://{db_user}:{db_password}@localhost:5432/{db_name}"
        return url
    
    except Exception as e:
        err(f"Failed to setup database: {e}")
        return None

# ---------------------------------------------------------------------------
# System checks
# ---------------------------------------------------------------------------
def check_python():
    step("Checking Python version")
    v = sys.version_info
    if v < (3, 11):
        err(f"Python 3.11+ required. You have {v.major}.{v.minor}.{v.micro}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

    # Check that the venv module is available for this Python installation.
    # On some Linux distros (Ubuntu/Debian) it ships as a separate package.
    try:
        import importlib.util
        if importlib.util.find_spec("venv") is None:
            raise ImportError
        ok("venv module available.")
    except ImportError:
        err(f"Python venv module not found for Python {v.major}.{v.minor}.")
        distro = get_linux_distro()
        if distro in ("ubuntu", "debian"):
            info(f"  Install it with:  sudo apt-get install python{v.major}.{v.minor}-venv")
        elif distro in ("fedora", "rhel", "centos"):
            info(f"  Install it with:  sudo dnf install python{v.major}-venv")
        else:
            info(f"  Install the python{v.major}.{v.minor}-venv package for your distribution.")
        sys.exit(1)

def _find_all_node_versions():
    """Return list of (version_tuple, bin_dir) for every discoverable Node install, newest first."""
    candidates = []
    seen = set()

    def _probe(node_path):
        if not node_path or not os.path.isfile(node_path):
            return
        real = os.path.realpath(node_path)
        if real in seen:
            return
        seen.add(real)
        try:
            r = subprocess.run([node_path, "--version"], capture_output=True, text=True, timeout=5)
            ver_str = r.stdout.strip().lstrip("v")
            ver_tuple = tuple(int(x) for x in ver_str.split(".")[:3])
            candidates.append((ver_tuple, os.path.dirname(node_path)))
        except Exception:
            pass

    # nvm
    nvm_versions = os.path.join(
        os.path.expanduser(os.environ.get("NVM_DIR", "~/.nvm")), "versions", "node"
    )
    if os.path.isdir(nvm_versions):
        for entry in sorted(os.listdir(nvm_versions)):
            _probe(os.path.join(nvm_versions, entry, "bin", "node"))

    # fnm
    for fnm_root in [
        os.path.expanduser("~/.local/share/fnm/node-versions"),
        os.path.expanduser("~/.fnm/node-versions"),
    ]:
        if os.path.isdir(fnm_root):
            for entry in sorted(os.listdir(fnm_root)):
                _probe(os.path.join(fnm_root, entry, "installation", "bin", "node"))

    # common system paths
    for p in ["/usr/local/bin/node", "/usr/bin/node", "/opt/homebrew/bin/node"]:
        _probe(p)

    # which -a (Unix) — catches anything else on PATH
    if not IS_WIN:
        try:
            r = subprocess.run(["which", "-a", "node"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.strip().splitlines():
                _probe(line.strip())
        except Exception:
            pass

    candidates.sort(reverse=True)
    return candidates


def _find_all_node_versions_win():
    """Windows-specific: probe all known Node.js install locations.
    Returns list of (version_tuple, node_exe_path, bin_dir) sorted newest-first."""
    candidates = []
    seen = set()

    def _probe(node_exe):
        if not node_exe or not os.path.isfile(node_exe):
            return
        real = os.path.realpath(node_exe).lower()
        if real in seen:
            return
        seen.add(real)
        try:
            r = subprocess.run([node_exe, "--version"], capture_output=True, text=True, timeout=5)
            ver_str = r.stdout.strip().lstrip("v")
            ver_tuple = tuple(int(x) for x in ver_str.split(".")[:3])
            candidates.append((ver_tuple, node_exe, os.path.dirname(node_exe)))
        except Exception:
            pass

    pf   = os.environ.get("ProgramFiles",       r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)",  r"C:\Program Files (x86)")
    lad  = os.environ.get("LocalAppData",        "")
    appd = os.environ.get("APPDATA",             "")

    # Standard winget / MSI install directories
    standard_dirs = [
        os.path.join(pf,   "nodejs"),
        os.path.join(pf86, "nodejs"),
        os.path.join(lad,  "Programs", "nodejs"),
        os.path.join(lad,  "nodejs"),
    ]
    for d in standard_dirs:
        _probe(os.path.join(d, "node.exe"))

    # nvm-windows: %APPDATA%\nvm\<version>\node.exe
    nvm_root = os.path.join(appd, "nvm")
    if os.path.isdir(nvm_root):
        for entry in os.listdir(nvm_root):
            _probe(os.path.join(nvm_root, entry, "node.exe"))

    # fnm on Windows
    for fnm_root in [
        os.path.join(lad, "fnm", "node-versions"),
        os.path.join(lad, ".fnm", "node-versions"),
    ]:
        if os.path.isdir(fnm_root):
            for entry in os.listdir(fnm_root):
                _probe(os.path.join(fnm_root, entry, "installation", "node.exe"))

    # Also walk PATH entries — catches a freshly refreshed PATH
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        _probe(os.path.join(path_dir.strip(), "node.exe"))

    candidates.sort(reverse=True)
    return candidates  # (ver_tuple, node_exe, bin_dir)


def _find_node_exe_win():
    """Return (node_exe, bin_dir) for the best Node >= 20.9.0 on Windows, else (None, None)."""
    MIN = (20, 9, 0)
    for ver_tuple, node_exe, bin_dir in _find_all_node_versions_win():
        if ver_tuple >= MIN:
            return node_exe, bin_dir
    return None, None


def check_npm():
    if IS_WIN:
        # On Windows, shutil.which / os.environ["PATH"] may be stale after a
        # winget install in the same session.  Probe known install paths directly.
        step("Checking Node.js / npm (Windows)")
        node_exe, bin_dir = _find_node_exe_win()
        if node_exe:
            try:
                r = subprocess.run([node_exe, "--version"], capture_output=True, text=True, timeout=5)
                ver_str = r.stdout.strip().lstrip("v")
                ok(f"Node.js v{ver_str} found at {node_exe}")
                # Prepend the bin dir so npm / npx resolve correctly for the rest of setup
                if bin_dir.lower() not in os.environ.get("PATH", "").lower():
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                    info(f"Prepended {bin_dir} to PATH for this session.")
                ok("npm ready")
                return
            except Exception as e:
                warn(f"Failed to invoke node at {node_exe}: {e}")
        # Nothing found — show a clear error
        err("Node.js 20.9.0+ is required but was not found on this Windows system.")
        info("Searched: Program Files\\nodejs, LocalAppData\\Programs\\nodejs, nvm-windows, fnm, PATH.")
        info("Install the latest Node.js LTS from https://nodejs.org/ and re-run setup.")
        sys.exit(1)

    # ---- Non-Windows path (unchanged) ----
    if not shutil.which("npm"):
        warn("npm not found. Attempting to install Node.js and npm automatically...")
        install_npm()

    # Verify the *currently active* Node.js version.
    node_exe = shutil.which("node")
    if node_exe:
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
            version_str = result.stdout.strip().lstrip("v")  # e.g. "18.17.0"
            parts = [int(p) for p in version_str.split(".")[:3]]
            major = parts[0]
            minor = parts[1] if len(parts) > 1 else 0

            # Require >= 20.9.0
            if major < 20 or (major == 20 and minor < 9):
                warn(f"Active Node.js version is v{version_str} (< 20.9.0). Searching for a newer install...")
                all_versions = _find_all_node_versions()
                suitable = [(v, d) for v, d in all_versions if v[0] > 20 or (v[0] == 20 and v[1] >= 9)]
                if suitable:
                    best_ver, best_dir = suitable[0]
                    best_ver_str = ".".join(str(x) for x in best_ver)
                    ok(f"Found Node.js v{best_ver_str} at {best_dir}")
                    # Prepend the better node's bin dir so all subsequent subprocess
                    # calls (npm install, npm run build, ...) use the right version.
                    os.environ["PATH"] = best_dir + os.pathsep + os.environ.get("PATH", "")
                    ok(f"Switched to Node.js v{best_ver_str} for this setup session.")
                else:
                    err(f"Node.js 20.9.0+ required. Active version: v{version_str}, none found ≥ 20.9.0.")
                    info("Install the latest Node.js from https://nodejs.org/ or via nvm/fnm, then re-run setup.")
                    sys.exit(1)
            else:
                ok(f"Node.js v{version_str}")
        except Exception as e:
            warn(f"Could not verify Node.js version: {e}")
    else:
        warn("node executable not found — npm may not work correctly.")

    ok("npm found")

# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "agent_name": "Synapse",
    "model": "",
    "mode": "cloud",
    "openai_key": "",
    "anthropic_key": "",
    "gemini_key": "",
    "deepseek_key": "",
    "xai_key": "",
    "google_maps_api_key": "",
    "bedrock_api_key": "",
    "bedrock_inference_profile": "",
    "embedding_model": "",
    "aws_access_key_id": "",
    "aws_secret_access_key": "",
    "aws_session_token": "",
    "aws_region": "us-east-1",
    "sql_connection_string": "",
    "ollama_base_url": "",
    "n8n_url": "http://localhost:5678",
    "n8n_api_key": "",
    "n8n_table_id": "",
    "global_config": {},
    "vault_enabled": True,
    "vault_threshold": 20000,
    "coding_agent_enabled": False,
    "report_agent_enabled": False,
    "browser_automation_enabled": True,
    "playwright_browsers_path": "",
    "messaging_enabled": False,
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
    except Exception:
        return dict(DEFAULT_SETTINGS)

def save_settings(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=4)
    # Persist the data directory path into .env so cli.py and synapse start
    # always find settings in the same location, even with relative paths.
    _rel = os.path.relpath(DATA_DIR, ROOT_DIR)
    _update_env_file("SYNAPSE_DATA_DIR", _rel)
    # Persist the database URL into .env so backend services that read
    # DATABASE_URL from the environment (code_indexer, code_search) pick it up.
    if cfg.get("sql_connection_string"):
        _update_env_file("DATABASE_URL", cfg["sql_connection_string"])

# ---------------------------------------------------------------------------
# Q1 — Coding Agent
# ---------------------------------------------------------------------------
def ask_coding_agent(cfg):
    step("Coding Agent (PostgreSQL + pgvector)")
    info("Enables semantic code search across your repositories.")
    enabled = ask_yn("Enable the Coding Agent?")
    cfg["coding_agent_enabled"] = enabled

    if not enabled:
        ok("Coding Agent disabled — skipping PostgreSQL setup.")
        return

    # Check if PostgreSQL was already installed by user
    psql_was_preinstalled = shutil.which("psql") is not None

    # Check if PostgreSQL is installed, install if needed
    if not psql_was_preinstalled:
        warn("PostgreSQL not found. Installing PostgreSQL...")
        install_postgresql()
        # Use default credentials for auto-installed PostgreSQL
        db_user = "postgres"
        db_password = ""  # Default postgres user usually has no password (peer auth)
        db_name = "synapse"
        ok("Using default PostgreSQL credentials (postgres user, peer authentication).")
    else:
        ok("PostgreSQL is already installed.")
        # Ask for credentials only if user had it pre-installed
        info("Configuring PostgreSQL database for Coding Agent...")
        db_user = ask("PostgreSQL username", default="postgres")
        db_password = ask("PostgreSQL password", default="")
        db_name = ask("Database name", default="synapse")

    # Try to install pgvector
    install_pgvector()

    # Create database and get URL
    db_url = create_postgresql_db(db_user, db_password, db_name)
    
    if db_url:
        cfg["sql_connection_string"] = db_url
        ok(f"Database URL: {db_url}")
        
        # Test connection
        info("Testing PostgreSQL connection...")
        try:
            import psycopg2  # type: ignore
            try:
                conn = psycopg2.connect(db_url, connect_timeout=5)
                conn.close()
                ok("PostgreSQL connection successful!")
                return
            except Exception as e:
                warn(f"Connection test failed: {e}")
                if ask_yn("Save URL anyway?", default="y"):
                    ok(f"Saved URL (verify before starting server)")
                    return
        except ImportError:
            info("(psycopg2 will be installed with backend dependencies)")
            ok(f"Database URL saved: {db_url}")
            return
    else:
        warn("Could not auto-create database. Please set it up manually.")
        url = ask("PostgreSQL connection URL",
                  default="postgresql://postgres:@localhost:5432/synapse")
        if url.startswith("postgresql"):
            cfg["sql_connection_string"] = url
            ok(f"Saved: {url}")
        else:
            err("Invalid URL format.")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Q2c — Browser Automation
# ---------------------------------------------------------------------------
def ask_browser_automation(cfg):
    step("Browser Automation")
    info("Allows Agents to use the browser and browse the web.")
    if ask_yn("Do your Agents need to use the browser and browse?", default="y"):
        cfg["browser_automation_enabled"] = True
        
        # Determine default playwright path
        system = platform.system()
        user_home = os.path.expanduser("~")
        if system == "Windows":
            default_pw_path = os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(user_home, "AppData", "Local")), "ms-playwright")
        elif system == "Darwin":
            default_pw_path = os.path.join(user_home, "Library", "Caches", "ms-playwright")
        else: # Linux
            default_pw_path = os.path.join(user_home, ".cache", "ms-playwright")

        # Check if playwright browsers already exist
        if os.path.exists(default_pw_path) and os.path.isdir(default_pw_path) and os.listdir(default_pw_path):
            ok(f"Playwright browsers found.")
            cfg["playwright_browsers_path"] = default_pw_path
        else:
            info("Playwright browsers not found. Installing... (this may take a minute)")
            try:
                subprocess.check_call(["npx", "-y", "playwright", "install", "chromium"], shell=IS_WIN)
                ok("Playwright installed successfully.")
                cfg["playwright_browsers_path"] = default_pw_path
            except subprocess.CalledProcessError as e:
                warn(f"Failed to install Playwright browsers automatically: {e}")
                info("You can install it manually by running:")
                info("  npx -y playwright install chromium")
                cfg["playwright_browsers_path"] = default_pw_path
    else:
        cfg["browser_automation_enabled"] = False
        ok("Browser Automation disabled.")



# ---------------------------------------------------------------------------
# Q2d — Messaging App Integration
# ---------------------------------------------------------------------------
def ask_messaging_app(cfg):
    step("Messaging App Integration")
    info("Lets your agents be reached via Telegram, Discord, Slack, Teams, or WhatsApp.")
    info("You will configure individual bots later in Settings → Messaging.")
    enabled = ask_yn("Enable Messaging App support?", default="n")
    cfg["messaging_enabled"] = enabled
    if not enabled:
        ok("Messaging disabled — skipping.")
        return
    ok("Messaging enabled. Messaging libraries will be installed now.")



GOOGLE_APIS = [
    ("Gmail",    "gmail.googleapis.com"),
    ("Drive",    "drive.googleapis.com"),
    ("Calendar", "calendar-json.googleapis.com"),
    ("Docs",     "docs.googleapis.com"),
    ("Sheets",   "sheets.googleapis.com"),
    ("Slides",   "slides.googleapis.com"),
    ("Forms",    "forms.googleapis.com"),
    ("Tasks",    "tasks.googleapis.com"),
    ("Contacts", "people.googleapis.com"),
]

def _gcloud_enable_apis(project_id):
    """Enable the three Google Workspace APIs via gcloud."""
    api_ids = ",".join(api for _, api in GOOGLE_APIS)
    try:
        subprocess.check_call(
            ["gcloud", "services", "enable"] + [api for _, api in GOOGLE_APIS]
            + ["--project", project_id],
            timeout=60
        )
        ok("APIs enabled: Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Tasks, Contacts.")
        return True
    except subprocess.CalledProcessError as e:
        warn(f"gcloud services enable failed: {e}")
        return False


def ask_google_workspace(cfg):
    """Optional step: Set up Google Workspace OAuth credentials."""
    step("Google Workspace Integration")
    info("Powers Gmail, Drive, Calendar, Docs, Tasks, and more in Synapse.")

    # Get backend port from config (or default)
    backend_port = cfg.get("backend_port", DEFAULT_BACKEND_PORT)

    # Skip if credentials already exist
    if os.path.exists(CREDENTIALS_FILE):
        ok(f"credentials.json already exists at {CREDENTIALS_FILE} — skipping.")
        return

    if not ask_yn("Configure Google Workspace now?", default="n"):
        ok("Skipped — you can configure this later in Settings → Integrations.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    has_gcloud = shutil.which("gcloud") is not None

    if has_gcloud:
        info("gcloud CLI detected — using it to streamline setup.")
        step("Step 1/3 — Authenticate with Google")
        info("Running: gcloud auth login")
        try:
            subprocess.check_call(["gcloud", "auth", "login", "--update-adc"])
            ok("Authenticated with Google.")
        except subprocess.CalledProcessError:
            warn("gcloud auth login failed. Continuing to manual step.")

        # List projects
        step("Step 2/3 — Select or create a Google Cloud Project")
        try:
            result = subprocess.run(
                ["gcloud", "projects", "list", "--format=value(projectId,name)"],
                capture_output=True, text=True, timeout=15
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                info("Your projects:")
                for i, line in enumerate(lines, 1):
                    parts = line.split()
                    pid = parts[0] if parts else line
                    name = " ".join(parts[1:]) if len(parts) > 1 else ""
                    print(f"   {_c(C.CYAN, str(i))}.  {pid}  {_c(C.YELLOW, name)}")
                raw = ask("Enter project number or type a project ID")
                if raw.isdigit() and 1 <= int(raw) <= len(lines):
                    project_id = lines[int(raw)-1].split()[0]
                else:
                    project_id = raw.strip()
            else:
                project_id = ask("Enter your Google Cloud project ID")
        except Exception:
            project_id = ask("Enter your Google Cloud project ID")

        if project_id:
            ok(f"Using project: {project_id}")
            step("Step 2b — Enabling Gmail, Drive, Calendar and other APIs")
            _gcloud_enable_apis(project_id)
        else:
            warn("No project selected — skipping API enable.")
            project_id = None

        # Deep link for OAuth client creation
        step("Step 3/3 — Create OAuth 2.0 Client ID (requires browser)")
        console_url = (
            f"https://console.cloud.google.com/apis/credentials/oauthclient?project={project_id}"
            if project_id else
            "https://console.cloud.google.com/apis/credentials"
        )
        info("gcloud CLI cannot create OAuth Desktop App clients automatically.")
        info(f"Open this link to create one (pre-filled to your project):")
        print(f"\n   {_c(C.CYAN, console_url)}\n")
        info("Instructions:")
        info("  1. Choose 'OAuth client ID'")
        info("  2. Application type → 'Web application'")
        info(f"  3. Set 'Authorized redirect URIs' to: http://localhost:{backend_port}/auth/callback")
        info("  4. Ensure OAuth consent screen has all required scopes configured")
        info("  5. Click Create → Download JSON")
    else:
        # No gcloud — full manual flow
        info("gcloud CLI not found — using manual setup.")
        info("Quick link to create OAuth credentials:")
        print(f"\n   {_c(C.CYAN, 'https://console.cloud.google.com/apis/credentials')}\n")
        info("  1. Create Project (or pick existing)")
        print(f"   Enable APIs: {_c(C.CYAN, 'https://console.cloud.google.com/flows/enableapi?apiid=gmail.googleapis.com,drive.googleapis.com,calendar-json.googleapis.com,docs.googleapis.com,sheets.googleapis.com,slides.googleapis.com,forms.googleapis.com,tasks.googleapis.com,people.googleapis.com')}")
        info("  2. Configure OAuth consent screen and add these scopes:")
        info("     userinfo.email, userinfo.profile, gmail.modify, gmail.send, drive, calendar,")
        info("     documents, spreadsheets, presentations, forms, tasks, contacts")
        info("  3. Create Credentials → OAuth Client ID → Web application")
        info(f"  4. Set 'Authorized redirect URIs' to: http://localhost:{backend_port}/auth/callback")
        info("  5. Download JSON and paste below.")

    # Paste area
    print()
    info("Paste the downloaded credentials JSON here (multi-line OK, end with a blank line):")
    lines = []
    try:
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        print()
        warn("No credentials pasted — skipping Google Workspace setup.")
        return

    raw_json = "\n".join(lines).strip()
    if not raw_json:
        warn("Empty input — skipping.")
        return

    try:
        parsed = json.loads(raw_json)
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(parsed, f, indent=4)
        ok(f"credentials.json saved to {CREDENTIALS_FILE}")
        info("After Synapse starts, go to Settings → Integrations → 'Connect Google Account' to complete OAuth.")
    except json.JSONDecodeError as e:
        err(f"Invalid JSON: {e}")
        warn("credentials.json was NOT saved. Configure via Settings → Integrations later.")


# ---------------------------------------------------------------------------
# Q3 — Agent Name
# ---------------------------------------------------------------------------
def ask_agent_name(cfg):
    step("Agent Name")
    name = ask("Enter a name for your AI Setup", default=cfg.get("agent_name") or "Synapse")
    cfg["agent_name"] = name or "Synapse"
    ok(f"Agent name set to: {cfg['agent_name']}")

# ---------------------------------------------------------------------------
# Q4 — LLM Provider / Model
# ---------------------------------------------------------------------------
def _fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())

def _ollama_models():
    """Returns list of installed Ollama model names, or [] on failure."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        models = []
        for line in lines[1:]:  # skip header
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception:
        return []

def _fetch_gemini_models(api_key):
    try:
        data = _fetch_json(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        )
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if "generateContent" in m.get("supportedGenerationMethods", []) and name.startswith("models/"):
                models.append(name.replace("models/", ""))
        return sorted(set(models))
    except Exception as e:
        warn(f"Could not fetch Gemini models: {e}")
        return []

def _fetch_openai_models(api_key):
    try:
        data = _fetch_json(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        models = sorted(set(
            m["id"] for m in data.get("data", [])
            if m.get("id", "").startswith(("gpt-4", "gpt-3.5"))
            and "instruct" not in m.get("id", "")
        ), reverse=True)
        return models
    except Exception as e:
        warn(f"Could not fetch OpenAI models: {e}")
        return []

def _fetch_anthropic_models(api_key):
    try:
        data = _fetch_json(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        )
        models = sorted(set(m["id"] for m in data.get("data", []) if m.get("id")), reverse=True)
        return models
    except Exception as e:
        warn(f"Could not fetch Anthropic models: {e}")
        return []

def _fetch_deepseek_models(api_key):
    try:
        data = _fetch_json(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        models = sorted(set(m["id"] for m in data.get("data", []) if m.get("id")), reverse=True)
        return models
    except Exception as e:
        warn(f"Could not fetch DeepSeek models: {e}")
        return []

def _fetch_grok_models(api_key):
    try:
        data = _fetch_json(
            "https://api.x.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        models = sorted(set(m["id"] for m in data.get("data", []) if m.get("id")), reverse=True)
        return models
    except Exception as e:
        warn(f"Could not fetch Grok models: {e}")
        return []

def _fetch_bedrock_models(api_key, region):
    """List Bedrock foundation models — tries boto3, falls back to direct HTTP."""
    # Try boto3 first
    try:
        import boto3  # type: ignore
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key
        client = boto3.client("bedrock", region_name=region)
        resp = client.list_foundation_models()
        models = sorted(set(
            s["modelId"] for s in resp.get("modelSummaries", [])
            if s.get("modelId")
        ))
        return models
    except ImportError:
        pass  # fall through to HTTP path
    except Exception as e:
        warn(f"boto3 Bedrock listing failed: {e}")
        return []

    # Fallback: direct HTTP with ABSK bearer token
    try:
        import urllib.request
        import json as _json
        url = f"https://bedrock.{region}.amazonaws.com/foundation-models"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = _json.loads(r.read())
        models = sorted(set(
            s["modelId"] for s in data.get("modelSummaries", [])
            if s.get("modelId")
        ))
        return models
    except Exception as e:
        warn(f"Could not fetch Bedrock models: {e}")
        return []

def ask_llm(cfg):
    step("LLM Provider & Model")

    # Try Ollama first
    info("Checking for Ollama...")
    ollama_models = _ollama_models()
    if ollama_models:
        ok(f"Ollama detected with {len(ollama_models)} model(s).")
        model = ask_choice("Select model", ollama_models)
        cfg["model"] = model
        cfg["mode"] = "local"
        ok(f"Model set to: {model}  (can be updated later in Settings)")
        return

    # Ollama not detected — ask if user has it on a custom URL
    if ask_yn("Ollama not detected on default port. Do you have Ollama running?"):
        base_url = ask("Ollama base URL", default="http://127.0.0.1:11434").rstrip("/")
        cfg["ollama_base_url"] = base_url
        os.environ["OLLAMA_HOST"] = base_url  # ollama CLI respects OLLAMA_HOST
        info("Checking for models at that URL...")
        ollama_models = _ollama_models()
        if ollama_models:
            ok(f"Found {len(ollama_models)} model(s).")
            model = ask_choice("Select model", ollama_models)
        else:
            warn("No models found. Enter a model name manually.")
            model = ask("Ollama model name", default="llama3")
        cfg["model"] = model
        cfg["mode"] = "local"
        ok(f"Model set to: {model}  (can be updated later in Settings)")
        return

    info("Select a cloud LLM provider:")
    providers = ["Gemini", "OpenAI", "Claude (Anthropic)", "DeepSeek", "Grok (xAI)", "Bedrock (AWS)"]
    choice = ask_choice("Select provider", providers)

    if choice == "Gemini":
        key = ask("Enter Gemini API key")
        cfg["gemini_key"] = key
        cfg["mode"] = "cloud"
        info("Fetching available models...")
        models = _fetch_gemini_models(key)
        if not models:
            warn("No models returned. Check your key.")
            cfg["model"] = ask("Enter model name manually", default="gemini-2.0-flash")
        else:
            cfg["model"] = ask_choice("Select model", models)

    elif choice == "OpenAI":
        key = ask("Enter OpenAI API key")
        cfg["openai_key"] = key
        cfg["mode"] = "cloud"
        info("Fetching available models...")
        models = _fetch_openai_models(key)
        if not models:
            warn("No models returned. Check your key.")
            cfg["model"] = ask("Enter model name manually", default="gpt-4o")
        else:
            cfg["model"] = ask_choice("Select model", models)

    elif choice == "Claude (Anthropic)":
        key = ask("Enter Anthropic API key")
        cfg["anthropic_key"] = key
        cfg["mode"] = "cloud"
        info("Fetching available models...")
        models = _fetch_anthropic_models(key)
        if not models:
            warn("No models returned. Check your key.")
            cfg["model"] = ask("Enter model name manually", default="claude-sonnet-4-6")
        else:
            cfg["model"] = ask_choice("Select model", models)

    elif choice == "DeepSeek":
        key = ask("Enter DeepSeek API key")
        cfg["deepseek_key"] = key
        cfg["mode"] = "cloud"
        info("Fetching available models...")
        models = _fetch_deepseek_models(key)
        if not models:
            warn("No models returned. Check your key.")
            cfg["model"] = ask("Enter model name manually", default="deepseek-chat")
        else:
            cfg["model"] = ask_choice("Select model", models)

    elif choice == "Grok (xAI)":
        key = ask("Enter xAI API key")
        cfg["xai_key"] = key
        cfg["mode"] = "cloud"
        info("Fetching available models...")
        models = _fetch_grok_models(key)
        if not models:
            warn("No models returned. Check your key.")
            cfg["model"] = ask("Enter model name manually", default="grok-3")
        else:
            cfg["model"] = ask_choice("Select model", models)

    elif choice == "Bedrock (AWS)":
        key = ask("Enter Bedrock API Key (ABSK)")
        region = ask("AWS Region", default=cfg.get("aws_region") or "us-east-1")
        cfg["bedrock_api_key"] = key
        cfg["aws_region"] = region
        cfg["mode"] = "cloud"
        info("Fetching available models...")
        models = _fetch_bedrock_models(key, region)
        if not models:
            model_id = ask("Enter Bedrock model ID manually")
        else:
            model_id = ask_choice("Select model", models)
        cfg["bedrock_inference_profile"] = model_id
        cfg["model"] = model_id

    ok(f"Provider configured. Model: {cfg.get('model', '(not set)')}")

# ---------------------------------------------------------------------------
# Q5 — Import examples
# ---------------------------------------------------------------------------
def ask_examples():
    step("Example Data")
    info("Import example agents, MCP servers, and orchestrations to get started quickly.")
    import_examples = ask_yn("Import example data?", default="y")

    if not import_examples:
        ok("Starting fresh — no example data imported.")
        return

    import glob
    example_files = glob.glob(os.path.join(EXAMPLES_DIR, "*.example.json"))
    if not example_files:
        warn("No *.example.json files found — nothing to import.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    for src in example_files:
        base_name = os.path.basename(src).replace(".example.json", ".json")
        dest = os.path.join(DATA_DIR, base_name)
        if os.path.exists(dest):
            info(f"Skipping (already exists): {base_name}")
        else:
            shutil.copy2(src, dest)
            ok(f"Imported: {base_name}")

# ---------------------------------------------------------------------------
# Install helpers
# ---------------------------------------------------------------------------
def _run_with_retry(cmd, retries=4, delay=5, **kwargs):
    """Run a subprocess command with retries. Output flows to terminal so the user can see progress."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            subprocess.check_call(cmd, **kwargs)
            return
        except subprocess.CalledProcessError as e:
            last_exc = e
            if attempt < retries:
                warn(f"Command failed (attempt {attempt}/{retries}). Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise last_exc

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
def install_backend(coding_enabled, messaging_enabled=False):
    step("Installing Backend Dependencies")

    if os.path.exists(VENV_DIR):
        info("Removing existing virtual environment...")
        shutil.rmtree(VENV_DIR)
    info("Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    info("Installing base requirements...")
    _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "--upgrade", "pip"])
    _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-r", os.path.join(BACKEND_DIR, "requirements.txt")])
    ok("Base dependencies installed.")

    if coding_enabled:
        coding_req = os.path.join(BACKEND_DIR, "requirements-coding.txt")
        if os.path.exists(coding_req):
            info("Installing coding-agent dependencies (cocoindex, psycopg)...")
            _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-r", coding_req])
            ok("Coding-agent dependencies installed.")
        else:
            warn(f"requirements-coding.txt not found at {coding_req}")
    
    if messaging_enabled:
        messaging_req = os.path.join(BACKEND_DIR, "requirements-messaging.txt")
        if os.path.exists(messaging_req):
            info("Installing messaging integration dependencies...")
            _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-r", messaging_req])
            ok("Messaging dependencies installed.")
        else:
            warn(f"requirements-messaging.txt not found at {messaging_req}")

    info("Installing Synapse package (editable mode)...")
    _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-e", ROOT_DIR])
    ok("Synapse package installed.")

def install_frontend():
    step("Installing Frontend Dependencies")
    if not shutil.which("npm"):
        err("npm not found.")
        sys.exit(1)
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if os.path.exists(node_modules):
        info("Removing existing node_modules...")
        shutil.rmtree(node_modules)
    info("Running npm install (this may take a while)...")
    _run_with_retry(["npm", "install"], cwd=FRONTEND_DIR, shell=IS_WIN)
    ok("Frontend dependencies installed.")
    
    info("Building frontend...")
    _run_with_retry(["npm", "run", "build"], cwd=FRONTEND_DIR, shell=IS_WIN)
    ok("Frontend built.")

# ---------------------------------------------------------------------------
# Port Configuration
# ---------------------------------------------------------------------------
def _update_env_file(key: str, value: str):
    """Set KEY=value in the root .env file, creating it if needed."""
    env_lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            env_lines = f.readlines()
        for i, line in enumerate(env_lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}"):
                env_lines[i] = f"{key}={value}\n"
                found = True
                break
    if not found:
        env_lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(env_lines)


def ask_ports(cfg):
    """Ask the user for backend and frontend ports and persist them in .env."""
    step("Server Ports")
    info(f"Backend API server port  (current default: {DEFAULT_BACKEND_PORT})")
    info(f"Frontend web UI port     (current default: {DEFAULT_FRONTEND_PORT})")
    if not ask_yn("Change the default ports?", default="n"):
        ok(f"Keeping backend={DEFAULT_BACKEND_PORT}, frontend={DEFAULT_FRONTEND_PORT}.")
        cfg["backend_port"] = DEFAULT_BACKEND_PORT
        cfg["frontend_port"] = DEFAULT_FRONTEND_PORT
        return

    backend_port = int(ask("Backend port", default=str(DEFAULT_BACKEND_PORT)))
    frontend_port = int(ask("Frontend port", default=str(DEFAULT_FRONTEND_PORT)))

    cfg["backend_port"] = backend_port
    cfg["frontend_port"] = frontend_port

    _update_env_file("SYNAPSE_BACKEND_PORT", str(backend_port))
    _update_env_file("NEXT_PUBLIC_BACKEND_PORT", str(backend_port))
    _update_env_file("SYNAPSE_FRONTEND_PORT", str(frontend_port))
    ok(f"Ports saved to .env — backend={backend_port}, frontend={frontend_port}.")


# ---------------------------------------------------------------------------
# Start servers
# ---------------------------------------------------------------------------
def start_backend(backend_port: int = DEFAULT_BACKEND_PORT):
    step("Starting Backend Server")
    env = os.environ.copy()
    env["SYNAPSE_BACKEND_PORT"] = str(backend_port)
    # Always pass SYNAPSE_DATA_DIR as an absolute path so the backend subprocess
    # resolves it correctly regardless of its working directory.
    env["SYNAPSE_DATA_DIR"] = os.path.abspath(DATA_DIR)
    return subprocess.Popen([PYTHON_EXE, "main.py"], cwd=BACKEND_DIR, env=env)

def start_frontend(frontend_port: int = DEFAULT_FRONTEND_PORT, backend_port: int = DEFAULT_BACKEND_PORT):
    step("Starting Frontend Server")
    env = os.environ.copy()
    env["SYNAPSE_FRONTEND_PORT"] = str(frontend_port)
    env["BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"
    return subprocess.Popen(
        ["npm", "run", "start", "--", "-p", str(frontend_port)],
        cwd=FRONTEND_DIR,
        shell=IS_WIN,
        env=env,
    )

def wait_for_server(url: str, name: str, timeout: int = 60) -> bool:
    """Wait for a server to be ready by checking HTTP status"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=3)
            return True
        except Exception:
            time.sleep(2)
    return False

# ---------------------------------------------------------------------------
# PATH Setup Helpers
# ---------------------------------------------------------------------------
def add_to_bashrc():
    """Add bin directory to PATH and ensure binary is executable"""
    bashrc = os.path.expanduser("~/.bashrc")
    bin_dir = os.path.join(ROOT_DIR, "bin")
    
    # --- NEW: Ensure the binary has execution permissions ---
    synapse_bin = os.path.join(bin_dir, "synapse")
    if os.path.exists(synapse_bin):
        # Get current permissions
        st = os.stat(synapse_bin)
        # Add the 'Executable' bit for the Owner (User), Group, and Others
        # This is the Python equivalent of 'chmod +x'
        os.chmod(synapse_bin, st.st_mode | stat.S_IEXEC)
        ok(f"Set execution permissions for {synapse_bin}")
    # --------------------------------------------------------

    export_line = f"\nexport PATH=\"{bin_dir}:$PATH\"  # Synapse AI"
    
    if not os.path.exists(bashrc):
        with open(bashrc, "w") as f:
            f.write(export_line + "\n")
        ok(f"Created {bashrc} with Synapse PATH")
        return True
    
    with open(bashrc, "r") as f:
        content = f.read()
    
    if "Synapse AI" in content or bin_dir in content:
        ok("Synapse already in PATH (bashrc)")
        return True
    
    with open(bashrc, "a") as f:
        f.write(export_line + "\n")
    ok(f"Added Synapse to PATH (bashrc)")
    return True

def add_to_zshrc():
    """Add bin directory to PATH in ~/.zshrc"""
    zshrc = os.path.expanduser("~/.zshrc")
    if not os.path.exists(zshrc):
        return False
    
    bin_dir = os.path.join(ROOT_DIR, "bin")
    export_line = f"\nexport PATH=\"{bin_dir}:$PATH\"  # Synapse AI"
    
    with open(zshrc, "r") as f:
        content = f.read()
    
    if "Synapse AI" in content or bin_dir in content:
        ok("Synapse already in PATH (zshrc)")
        return True
    
    with open(zshrc, "a") as f:
        f.write(export_line + "\n")
    ok(f"Added Synapse to PATH (zshrc)")
    return True

def setup_path():
    """Setup PATH for the current platform"""
    step("Setting up Synapse command")
    bin_dir = os.path.join(ROOT_DIR, "bin")
    
    if IS_WIN:
        # Windows: Just inform user about python -m synapse start
        info("On Windows, use: python -m synapse start")
        ok("Windows setup complete.")
    else:
        # Unix: Try to add to .bashrc / .zshrc
        info("Checking for shell configuration files...")
        add_to_bashrc()
        add_to_zshrc()
        
        # Update PATH in the current process so synapse is immediately usable
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        ok("PATH setup complete.")

def show_restart_instructions():
    """Show instructions for restarting Synapse"""
    step("To Start Synapse Again Later")
    
    if IS_WIN:
        info("From anywhere in Windows:")
        info(f"  python -m synapse start")
    else:
        info("Simply run:")
        info(f"  synapse start")
        info("")
        info("If the command is not found, either:")
        info(f"  1. Restart your terminal (to reload ~/.bashrc or ~/.zshrc)")
        info(f"  2. Or use: python -m synapse start")
        info("")
        info("Other useful commands:")
        info(f"  synapse stop      # Stop running services")
        info(f"  synapse status    # Check service status")
        info(f"  synapse restart   # Restart services")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 50}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}   Synapse AI — Setup Wizard{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 50}{C.RESET}\n")

    check_python()
    check_npm()

    cfg = load_settings()

    ask_coding_agent(cfg)

    ask_browser_automation(cfg)
    ask_messaging_app(cfg)
    ask_ports(cfg)
    ask_google_workspace(cfg)
    ask_agent_name(cfg)
    ask_llm(cfg)
    ask_examples()

    step("Writing Settings")
    save_settings(cfg)
    ok(f"Settings saved to {SETTINGS_FILE}")

    try:
        install_backend(
            cfg.get("coding_agent_enabled", False),
            cfg.get("messaging_enabled", False),
        )
        install_frontend()
    except subprocess.CalledProcessError as e:
        err(f"Installation failed: {e}")
        sys.exit(1)

    setup_path()

    print()
    start_now = ask_yn("Start Synapse now?", default="y")
    
    if not start_now:
        print()
        show_restart_instructions()
        print(f"\n{C.GREEN}Setup complete! Synapse is ready to use.{C.RESET}\n")
        sys.exit(0)

    _backend_port = cfg.get("backend_port", DEFAULT_BACKEND_PORT)
    _frontend_port = cfg.get("frontend_port", DEFAULT_FRONTEND_PORT)

    backend_proc = start_backend(backend_port=_backend_port)
    frontend_proc = start_frontend(frontend_port=_frontend_port, backend_port=_backend_port)

    if wait_for_server(f"http://127.0.0.1:{_backend_port}/docs", "Backend"):
        ok("Backend is ready.")

    if wait_for_server(f"http://127.0.0.1:{_frontend_port}", "Frontend"):
        ok("Frontend is ready.")

    print(f"\n{C.BOLD}{C.GREEN}Application is running!{C.RESET}")
    print(f"   Frontend: {_c(C.CYAN, f'http://localhost:{_frontend_port}')}")
    print(f"   Backend:  {_c(C.CYAN, f'http://localhost:{_backend_port}')}")
    print(f"\n{C.YELLOW}Press Ctrl+C to stop.{C.RESET}\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                err("Backend crashed! Check the logs above.")
                break
            if frontend_proc.poll() is not None:
                err("Frontend crashed! Check the logs above.")
                break
    except KeyboardInterrupt:
        print("\nStopping servers...")
        backend_proc.terminate()
        if not IS_WIN:
            try:
                os.killpg(os.getpgid(frontend_proc.pid), 15)
            except Exception:
                frontend_proc.terminate()
        else:
            frontend_proc.terminate()
        print("Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
