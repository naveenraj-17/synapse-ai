"""
Synapse AI — Interactive Setup Wizard
Guides the user through configuration, installs dependencies, and starts both servers.
Uses only Python stdlib so it works before the venv exists.
"""
import json
import os
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
        err("npm not found. Please install Node.js and npm.")
        sys.exit(1)
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

    # Ask for DB URL, try to validate
    while True:
        url = ask("PostgreSQL connection URL",
                  default=cfg.get("sql_connection_string") or "postgresql://user:pass@localhost:5432/synapse")
        if not url.startswith("postgresql"):
            warn("URL must start with postgresql:// or postgresql+psycopg://")
            continue

        info("Testing connection…")
        # Try psycopg2 (may already be system-installed)
        try:
            import psycopg2  # type: ignore
            try:
                conn = psycopg2.connect(url, connect_timeout=5)
                conn.close()
                cfg["sql_connection_string"] = url
                ok("Database connection successful.")
                return
            except Exception as e:
                warn(f"Connection failed: {e}")
                if not ask_yn("Try a different URL?", default="y"):
                    cfg["sql_connection_string"] = url
                    warn("Saved URL anyway — verify before starting the server.")
                    return
        except ImportError:
            # psycopg2 not available yet — accept URL without validation
            cfg["sql_connection_string"] = url
            info("(Connection will be validated after install.)")
            ok(f"Saved: {url}")
            return

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
        info("Available models:")
        model = ask_choice("Select model", ollama_models)
        cfg["model"] = model
        cfg["mode"] = "local"
        ok(f"Model set to: {model}  (can be updated later in Settings)")
        return

    info("Ollama not found. Select a cloud LLM provider:")
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
    subprocess.check_call(
        [PIP_EXE, "install", "--upgrade", "pip", "-q"],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )
    subprocess.check_call(
        [PIP_EXE, "install", "-r", os.path.join(BACKEND_DIR, "requirements.txt"), "-q"],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )
    ok("Base dependencies installed.")

    if coding_enabled:
        coding_req = os.path.join(BACKEND_DIR, "requirements-coding.txt")
        if os.path.exists(coding_req):
            info("Installing coding-agent dependencies (cocoindex, psycopg)…")
            subprocess.check_call(
                [PIP_EXE, "install", "-r", coding_req, "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
            )
            ok("Coding-agent dependencies installed.")
        else:
            warn(f"requirements-coding.txt not found at {coding_req}")

def install_frontend():
    step("Installing Frontend Dependencies")
    if not shutil.which("npm"):
        err("npm not found.")
        sys.exit(1)
    info("Running npm install (this may take a while)…")
    subprocess.check_call(
        ["npm", "install"],
        cwd=FRONTEND_DIR,
        shell=IS_WIN,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )
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

    backend_proc = start_backend()
    frontend_proc = start_frontend()

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
