"""
Synapse AI — Interactive Setup Wizard
Guides the user through configuration, installs dependencies, and starts both servers.
Uses only Python stdlib so it works before the venv exists.
"""
import json
import os
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
DATA_DIR = os.path.join(BACKEND_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

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
        info("Please download and install Node.js from https://nodejs.org/")
        info("Then re-run this setup script.")
        err("Node.js installation required.")
        sys.exit(1)
    elif os_type == "darwin":
        info("Installing Node.js via Homebrew…")
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
            info("Installing Node.js on Ubuntu/Debian…")
            try:
                subprocess.check_call(["sudo", "apt-get", "update"])
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "nodejs", "npm"])
                ok("Node.js installed successfully.")
            except subprocess.CalledProcessError:
                err("Failed to install Node.js.")
                sys.exit(1)
        elif distro in ("fedora", "rhel", "centos"):
            info("Installing Node.js on Fedora/RHEL…")
            try:
                subprocess.check_call(["sudo", "dnf", "install", "-y", "nodejs", "npm"])
                ok("Node.js installed successfully.")
            except subprocess.CalledProcessError:
                err("Failed to install Node.js.")
                sys.exit(1)
        elif distro in ("arch", "manjaro"):
            info("Installing Node.js on Arch/Manjaro…")
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
        info("Please download and install PostgreSQL from https://www.postgresql.org/download/")
        info("Then re-run this setup script.")
        err("PostgreSQL installation required.")
        sys.exit(1)
    elif os_type == "darwin":
        info("Installing PostgreSQL via Homebrew…")
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
            info("Installing PostgreSQL on Ubuntu/Debian…")
            try:
                subprocess.check_call(["sudo", "apt-get", "update"])
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "postgresql", "postgresql-contrib"])
                subprocess.check_call(["sudo", "systemctl", "start", "postgresql"])
                ok("PostgreSQL installed and started.")
            except subprocess.CalledProcessError:
                err("Failed to install PostgreSQL.")
                sys.exit(1)
        elif distro in ("fedora", "rhel", "centos"):
            info("Installing PostgreSQL on Fedora/RHEL…")
            try:
                subprocess.check_call(["sudo", "dnf", "install", "-y", "postgresql-server", "postgresql-contrib"])
                subprocess.check_call(["sudo", "systemctl", "start", "postgresql"])
                ok("PostgreSQL installed and started.")
            except subprocess.CalledProcessError:
                err("Failed to install PostgreSQL.")
                sys.exit(1)
        elif distro in ("arch", "manjaro"):
            info("Installing PostgreSQL on Arch/Manjaro…")
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
        info(f"Creating database '{db_name}' and user '{db_user}'…")
        
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

def check_npm():
    if not shutil.which("npm"):
        warn("npm not found. Attempting to install Node.js and npm automatically…")
        install_npm()
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
        warn("PostgreSQL not found. Installing PostgreSQL…")
        install_postgresql()
        # Use default credentials for auto-installed PostgreSQL
        db_user = "postgres"
        db_password = ""  # Default postgres user usually has no password (peer auth)
        db_name = "synapse"
        ok("Using default PostgreSQL credentials (postgres user, peer authentication).")
    else:
        ok("PostgreSQL is already installed.")
        # Ask for credentials only if user had it pre-installed
        info("Configuring PostgreSQL database for Coding Agent…")
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
        info("Testing PostgreSQL connection…")
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
# Q2 — Report Agent
# ---------------------------------------------------------------------------
def ask_report_agent(cfg):
    step("Report Agent")
    info("Adds a 'Report' agent type with dynamic RAG support for analysis tasks.")
    cfg["report_agent_enabled"] = ask_yn("Enable the Report Agent?")
    status = "enabled" if cfg["report_agent_enabled"] else "disabled"
    ok(f"Report Agent {status}.")

# ---------------------------------------------------------------------------
# Q3 — Agent Name
# ---------------------------------------------------------------------------
def ask_agent_name(cfg):
    step("Agent Name")
    name = ask("Enter a name for your AI agent", default=cfg.get("agent_name") or "Synapse")
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

def _fetch_bedrock_models(api_key, region):
    """Use boto3 with ABSK token to list Bedrock foundation models."""
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
        warn("boto3 not found in system Python — cannot list Bedrock models.")
        return []
    except Exception as e:
        warn(f"Could not fetch Bedrock models: {e}")
        return []

def ask_llm(cfg):
    step("LLM Provider & Model")

    # Try Ollama first
    info("Checking for Ollama…")
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
        info("Checking for models at that URL…")
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
    providers = ["Gemini", "OpenAI", "Claude (Anthropic)", "Bedrock (AWS)"]
    choice = ask_choice("Select provider", providers)

    if choice == "Gemini":
        key = ask("Enter Gemini API key")
        cfg["gemini_key"] = key
        cfg["mode"] = "cloud"
        info("Fetching available models…")
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
        info("Fetching available models…")
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
        info("Fetching available models…")
        models = _fetch_anthropic_models(key)
        if not models:
            warn("No models returned. Check your key.")
            cfg["model"] = ask("Enter model name manually", default="claude-sonnet-4-6")
        else:
            cfg["model"] = ask_choice("Select model", models)

    elif choice == "Bedrock (AWS)":
        key = ask("Enter Bedrock API Key (ABSK)")
        region = ask("AWS Region", default=cfg.get("aws_region") or "us-east-1")
        cfg["bedrock_api_key"] = key
        cfg["aws_region"] = region
        cfg["mode"] = "cloud"
        info("Fetching available models…")
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
    example_files = glob.glob(os.path.join(DATA_DIR, "*.example.json"))
    if not example_files:
        warn("No *.example.json files found — nothing to import.")
        return

    for src in example_files:
        dest = src.replace(".example.json", ".json")
        if os.path.exists(dest):
            info(f"Skipping (already exists): {os.path.basename(dest)}")
        else:
            shutil.copy2(src, dest)
            ok(f"Imported: {os.path.basename(dest)}")

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
                warn(f"Command failed (attempt {attempt}/{retries}). Retrying in {delay}s…")
                time.sleep(delay)
            else:
                raise last_exc

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
def install_backend(coding_enabled):
    step("Installing Backend Dependencies")

    if not os.path.exists(PIP_EXE):
        if os.path.exists(VENV_DIR):
            info("Removing corrupted virtual environment…")
            shutil.rmtree(VENV_DIR)
        info("Creating virtual environment…")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    info("Installing base requirements…")
    _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "--upgrade", "pip"])
    _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-r", os.path.join(BACKEND_DIR, "requirements.txt")])
    ok("Base dependencies installed.")

    if coding_enabled:
        coding_req = os.path.join(BACKEND_DIR, "requirements-coding.txt")
        if os.path.exists(coding_req):
            info("Installing coding-agent dependencies (cocoindex, psycopg)…")
            _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-r", coding_req])
            ok("Coding-agent dependencies installed.")
        else:
            warn(f"requirements-coding.txt not found at {coding_req}")

    info("Installing Synapse package (editable mode)…")
    _run_with_retry([PYTHON_EXE, "-m", "pip", "install", "-e", ROOT_DIR])
    ok("Synapse package installed.")

def install_frontend():
    step("Installing Frontend Dependencies")
    if not shutil.which("npm"):
        err("npm not found.")
        sys.exit(1)
    info("Running npm install (this may take a while)…")
    _run_with_retry(["npm", "install"], cwd=FRONTEND_DIR, shell=IS_WIN)
    ok("Frontend dependencies installed.")

# ---------------------------------------------------------------------------
# Start servers
# ---------------------------------------------------------------------------
def start_backend():
    step("Starting Backend Server")
    return subprocess.Popen([PYTHON_EXE, "main.py"], cwd=BACKEND_DIR)

def start_frontend():
    step("Starting Frontend Server")
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        shell=IS_WIN
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
    """Add bin directory to PATH in ~/.bashrc"""
    bashrc = os.path.expanduser("~/.bashrc")
    bin_dir = os.path.join(ROOT_DIR, "bin")
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
        info("(Works from anywhere after setup)")
        ok("Windows setup complete.")
    else:
        # Unix: Try to add to .bashrc / .zshrc
        info("Checking for shell configuration files…")
        added_bash = add_to_bashrc()
        added_zsh = add_to_zshrc()
        
        if added_bash or added_zsh:
            info(f"Synapse bin directory: {bin_dir}")
            info("You may need to run: source ~/.bashrc  (or ~/.zshrc for zsh)")
            info("Or restart your terminal.")
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
    ask_report_agent(cfg)
    ask_agent_name(cfg)
    ask_llm(cfg)
    ask_examples()

    step("Writing Settings")
    save_settings(cfg)
    ok(f"Settings saved to {SETTINGS_FILE}")

    try:
        install_backend(cfg.get("coding_agent_enabled", False))
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

    backend_proc = start_backend()
    frontend_proc = start_frontend()

    if wait_for_server("http://127.0.0.1:8000/docs", "Backend"):
        ok("Backend is ready.")

    if wait_for_server("http://127.0.0.1:3000", "Frontend"):
        ok("Frontend is ready.")

    print(f"\n{C.BOLD}{C.GREEN}Application is running!{C.RESET}")
    print(f"   Frontend: {_c(C.CYAN, 'http://localhost:3000')}")
    print(f"   Backend:  {_c(C.CYAN, 'http://localhost:8000')}")
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
        print("\nStopping servers…")
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
