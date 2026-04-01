import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager, AsyncExitStack
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Default timeout for all MCP session requests — prevents any call from hanging
# forever.  Per-request read_timeout_seconds overrides this when supplied.
_SESSION_READ_TIMEOUT = timedelta(seconds=60)

try:
    from core.memory import MemoryStore
except ImportError:
    print("Warning: MemoryStore dependencies not found. Memory disabled.")
    MemoryStore = None

from core.mcp_client import MCPClientManager
from core.config import load_settings
from core.routes.settings import _init_memory_store

# Route routers
from core.routes.auth import router as auth_router
from core.routes.settings import router as settings_router
from core.routes.agents import router as agents_router
from core.routes.tools import router as tools_router
from core.routes.n8n import router as n8n_router
from core.routes.data import router as data_router
from core.routes.chat import router as chat_router
from core.routes.repos import router as repos_router
from core.routes.db_configs import router as db_configs_router
from core.routes.orchestrations import router as orchestrations_router
from core.routes.logs import router as logs_router
from core.routes.messaging import router as messaging_router
from core.routes.sessions import router as sessions_router
from core.routes.usage import router as usage_router
from core.routes.profiling import router as profiling_router
from core.profiling import TimingMiddleware

# Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = "llama3"

# Agent Configuration
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
BACKEND_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = BACKEND_ROOT.parent
_data_dir_env = os.getenv("SYNAPSE_DATA_DIR", "")
if _data_dir_env:
    _data_dir_p = Path(_data_dir_env)
    DATA_DIR = _data_dir_p if _data_dir_p.is_absolute() else _PROJECT_ROOT / _data_dir_p
else:
    DATA_DIR = BACKEND_ROOT / "data"
GOOGLE_CREDENTIALS_DIR = DATA_DIR / "google-credentials"

_settings = load_settings()

# Propagate ollama_base_url from settings to env so llm_providers picks it up
if _settings.get("ollama_base_url"):
    os.environ["OLLAMA_BASE_URL"] = _settings["ollama_base_url"]

TOOLS_LIST = {
    "time": str(TOOLS_DIR / "time.py"),
    "sql": str(TOOLS_DIR / "sql_agent.py"),
    "personal_details": str(TOOLS_DIR / "personal_details.py"),
    "collect_data": str(TOOLS_DIR / "collect_data.py"),
    "pdf_parser": str(TOOLS_DIR / "pdf_parser.py"),
    "xlsx_parser": str(TOOLS_DIR / "xlsx_parser.py"),
    "sandbox": str(TOOLS_DIR / "sandbox.py"),
    "code_search": str(TOOLS_DIR / "code_search.py")
}

REPOS_FILE = DATA_DIR / "repos.json"

def _get_repo_paths() -> list[str]:
    """Load repo paths from repos.json for filesystem MCP server permissions."""
    if not REPOS_FILE.exists():
        return []
    try:
        repos = json.loads(REPOS_FILE.read_text())
        return [r["path"] for r in repos if r.get("path") and os.path.isdir(r["path"])]
    except Exception as e:
        print(f"Warning: Could not load repo paths: {e}")
        return []


def _get_google_oauth_env() -> dict[str, str]:
    """Extract OAuth client_id and client_secret from credentials.json for workspace-mcp.
    Also reads user email from token.json to pass USER_GOOGLE_EMAIL for single-user mode."""
    creds_file = DATA_DIR / "credentials.json"
    token_file = DATA_DIR / "token.json"
    if not creds_file.exists():
        return {}
    try:
        creds = json.loads(creds_file.read_text())
        installed = creds.get("installed", creds.get("web", {}))
        client_id = installed.get("client_id", "")
        client_secret = installed.get("client_secret", "")
        if not (client_id and client_secret):
            return {}

        env = {
            "GOOGLE_OAUTH_CLIENT_ID": client_id,
            "GOOGLE_OAUTH_CLIENT_SECRET": client_secret,
            "OAUTHLIB_INSECURE_TRANSPORT": "1",  # allow http:// redirect URIs for localhost
            "GOOGLE_MCP_CREDENTIALS_DIR": str(GOOGLE_CREDENTIALS_DIR.resolve()),
        }

        # Read user email from token.json so workspace-mcp can skip the email prompt
        if token_file.exists():
            print("token_file", token_file)
            try:
                import base64
                token_data = json.loads(token_file.read_text())
                email = token_data.get("email")
                if not email and token_data.get("token"):
                    id_token = token_data["token"]
                    payload_b64 = id_token.split(".")[1]
                    payload_b64 += "=" * (4 - len(payload_b64) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    email = payload.get("email")
                if email:
                    env["USER_GOOGLE_EMAIL"] = email
            except Exception as e:
                print(f"Warning: Could not read user email from token.json: {e}")

        return env
    except Exception as e:
        print(f"Warning: Could not read Google OAuth credentials: {e}")
    return {}


def _build_native_mcp_servers() -> list[dict]:
    """
    Build the list of native MCP servers to connect at startup.
    Returns a list of dicts with keys: name, command, args, env (optional).
    """
    servers = []

    # --- Filesystem MCP Server ---
    repo_paths = _get_repo_paths()
    vault_path = str(DATA_DIR / "vault")
    # Always start with vault; include any configured repo paths on top.
    fs_paths = repo_paths + [vault_path]
    if not repo_paths:
        print("Warning: No repos configured — starting filesystem MCP server with vault access only.")
    servers.append({
        "name": "Filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"] + fs_paths,
    })

    # --- Playwright MCP Server (browser automation) ---
    if _settings.get("browser_automation_enabled", True):
        env_dict = {}
        pw_path = _settings.get("playwright_browsers_path")
        if pw_path:
            env_dict["PLAYWRIGHT_BROWSERS_PATH"] = pw_path
        else:
            # Fallback for old configs
            env_dict["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expanduser("~/.cache/ms-playwright")

        servers.append({
            "name": "Browser Automation",
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest", "--browser", "chromium"],
            "env": env_dict,
        })

    # --- Google Workspace MCP Server (Gmail, Drive, Calendar) ---
    google_env = _get_google_oauth_env()
    if google_env:
        servers.append({
            "name": "Google Workspace",
            "command": "uvx",
            "args": ["workspace-mcp", "--single-user", "--tools", "gmail", "drive", "calendar"],
            "env": google_env,
        })
    else:
        print("Warning: No Google OAuth credentials found — skipping Google Workspace MCP server.")


    # --- Memory MCP Server ---
    memory_file_path = DATA_DIR / "memory" / "memory.jsonl"
    servers.append({
        "name": "Memory",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {"MEMORY_FILE_PATH": str(memory_file_path)},
    })

    # --- Sequential Thinking MCP Server ---
    servers.append({
        "name": "Sequential Thinking",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
    })

    return servers


# ---------------------------------------------------------------------------
# Module-level mutable state.
# Accessed by routes via `import core.server as _server; _server.agent_sessions`.
# The react_engine receives this module as a parameter for testability.
# ---------------------------------------------------------------------------
agent_sessions: dict[str, ClientSession] = {}   # client_name -> MCP session
tool_router: dict[str, tuple[str, str]] = {}     # tool_key -> (session_name, actual_tool_name)
exit_stack: Optional[AsyncExitStack] = None
memory_store: Any = None
mcp_manager: Optional[MCPClientManager] = None
messaging_manager: Any = None  # MessagingManager (set in lifespan if enabled)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global exit_stack
    print("Starting Multi-Agent Orchestrator...")
    exit_stack = AsyncExitStack()
    
    if _settings.get("coding_agent_enabled"):
        try:
            from services.code_indexer import init_cocoindex
            init_cocoindex()
        except Exception as e:
            print(f"Failed to init cocoindex: {e}")

    try:
        for agent_name, script_path in TOOLS_LIST.items():
            print(f"Connecting to {agent_name} agent at {script_path}...")
            
            # Prepare environment with PYTHONPATH specifically pointing to backend root
            # This is crucial so agents can assume 'services' and 'core' are importable
            env = os.environ.copy()
            env["PYTHONPATH"] = str(BACKEND_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

            server_params = StdioServerParameters(
                command=sys.executable,
                args=[script_path],
                env=env
            )
            
            read, write = await exit_stack.enter_async_context(stdio_client(server_params))
            session = await exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            agent_sessions[agent_name] = session
            
            # Register tools
            tools = await session.list_tools()
            for tool in tools.tools:
                tool_router[tool.name] = (agent_name, tool.name)
                print(f"  Registered tool: {tool.name} -> {agent_name}")

        # --- Initialize Native MCP Servers ---
        for mcp_cfg in _build_native_mcp_servers():
            mcp_name = mcp_cfg["name"]
            cmd = mcp_cfg["command"]

            # Check that the command binary is available
            if not shutil.which(cmd):
                print(f"Warning: '{cmd}' not found — skipping native MCP server '{mcp_name}'.")
                continue

            print(f"Connecting native MCP server '{mcp_name}'...")
            try:
                env = os.environ.copy()
                # Merge any extra env vars from the config (e.g. OAuth credentials)
                env.update(mcp_cfg.get("env", {}))

                server_params = StdioServerParameters(
                    command=cmd,
                    args=mcp_cfg["args"],
                    env=env,
                )
                read, write = await exit_stack.enter_async_context(stdio_client(server_params))
                session = await exit_stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=_SESSION_READ_TIMEOUT)
                )
                await session.initialize()

                agent_sessions[mcp_name] = session

                tools = await session.list_tools()
                for tool in tools.tools:
                    tool_router[tool.name] = (mcp_name, tool.name)
                    print(f"  Registered tool: {tool.name} -> {mcp_name}")
            except Exception as e:
                print(f"  Failed to connect native MCP server '{mcp_name}': {e}")

        # --- Initialize External MCP Servers ---
        global mcp_manager
        mcp_manager = MCPClientManager(exit_stack)
        print("Connecting to external MCP servers...")
        external_sessions = await mcp_manager.connect_all()
        
        for name, session in external_sessions.items():
            # Prefix to avoid collision with internal agents
            agent_key = f"ext_mcp_{name}"
            agent_sessions[agent_key] = session
            print(f"Connected external MCP server: {name}")
            
            try:
                tools = await session.list_tools()
                print(f"  MCP Server '{name}' returned {len(tools.tools)} tools.")
                for tool in tools.tools:
                    tool_router[f"{name}__{tool.name}"] = (agent_key, tool.name)
                    print(f"  Registered external tool: {name}__{tool.name} -> {agent_key}")
            except Exception as e:
                print(f"  Error listing tools for {name}: {e}")
                import traceback
                traceback.print_exc()
                
        # Initialize Memory Store
        if MemoryStore:
            print("Initializing Memory Store...")
            global memory_store
            memory_store = _init_memory_store(load_settings())
            # Clear the legacy chat_history ChromaDB collection — chat turns are
            # now persisted as JSON files. The collection may still contain stale
            # data from before this refactor; clear it once at startup.
            if memory_store:
                try:
                    memory_store.clear_memory()
                    print("INFO: Cleared legacy ChromaDB chat_history collection (chat history is now JSON-persisted).")
                except Exception as _clr_err:
                    print(f"WARNING: Could not clear ChromaDB chat_history: {_clr_err}")

        print("All agents connected.")

        # Expose server module on app.state for orchestration routes
        import core.server as _self_module
        app.state.server_module = _self_module

        # --- Initialize Messaging Manager (if enabled) ---
        if _settings.get("messaging_enabled", False):
            try:
                from core.messaging.manager import MessagingManager
                global messaging_manager
                messaging_manager = MessagingManager(server_module=_self_module)
                await messaging_manager.start_all()
                app.state.messaging_manager = messaging_manager
                print("Messaging manager started.")
            except Exception as e:
                print(f"Warning: Failed to start messaging manager: {e}")
        else:
            app.state.messaging_manager = None

        yield
        
    except Exception as e:
        print(f"Error starting agents: {e}")
        yield
    finally:
        print("Shutting down agents...")
        if messaging_manager:
            try:
                await messaging_manager.stop_all()
            except Exception as e:
                print(f"Warning: Messaging manager shutdown error: {e}")
        if exit_stack:
            await exit_stack.aclose()

app = FastAPI(lifespan=lifespan)

_frontend_port = os.getenv("SYNAPSE_FRONTEND_PORT", "3000")
_backend_port_cors = os.getenv("SYNAPSE_BACKEND_PORT", "8000")
_cors_defaults = {
    f"http://localhost:{_frontend_port}",
    "http://localhost:3000",
    "http://localhost:5173",
    f"http://localhost:{_backend_port_cors}",
}
CORS_ORIGINS = os.getenv("CORS_ORIGINS", ",".join(_cors_defaults)).split(",")

class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    """
    Chrome's Private Network Access (PNA) protection blocks external OAuth
    providers from redirecting back to localhost unless the server explicitly
    opts in via the Access-Control-Allow-Private-Network header.

    This middleware:
    1. Responds to Chrome's PNA preflight (OPTIONS with
       Access-Control-Request-Private-Network: true) with a 200 + the
       Allow-Private-Network header so the real request is permitted.
    2. Injects Access-Control-Allow-Private-Network: true on every response
       so Chrome allows the subsequent navigation.
    """
    async def dispatch(self, request: Request, call_next):
        # PNA preflight: Chrome sends OPTIONS with this header before the real
        # document navigation from a public origin → localhost.
        if (
            request.method == "OPTIONS"
            and request.headers.get("access-control-request-private-network") == "true"
        ):
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Private-Network": "true",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                },
            )
        response = await call_next(request)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


app.add_middleware(PrivateNetworkAccessMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)

# --- Include Route Routers ---
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(agents_router)
app.include_router(tools_router)
app.include_router(n8n_router)
app.include_router(data_router)
app.include_router(chat_router)
app.include_router(repos_router)
app.include_router(db_configs_router)
app.include_router(orchestrations_router)
app.include_router(logs_router)
app.include_router(messaging_router)
app.include_router(sessions_router)
app.include_router(usage_router)
app.include_router(profiling_router)

if __name__ == "__main__":
    import uvicorn
    _port = int(os.getenv("SYNAPSE_BACKEND_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=_port)
