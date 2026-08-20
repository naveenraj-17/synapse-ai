"""
Minimal stub of core.server's server_module interface for use inside worker processes.
Workers don't have a running FastAPI app or interactive MCP session setup,
so this builds a lightweight equivalent that satisfies OrchestrationEngine.

Two halves, because only one of them depends on whose job is running
---------------------------------------------------------------------
``build_shared()`` connects the native tool servers, which are the same for
everybody: `time`, `pdf_parser`, `web_scraper` and the rest advertise the same
tools whoever calls them. It runs once, at worker startup.

``build_for_tenant()`` connects what is *not* the same for everybody — the
Filesystem MCP server, which is rooted at the calling tenant's vault, and that
tenant's own MCP servers. It runs per tenant, behind the bounded pool in
`core/scale/mcp_pool.py`, and the module it returns presents the shared sessions
and its own as one set so nothing downstream has to know about the split.

This used to be a single ``build()`` called once at startup, whose result was
stored on the ARQ context and handed to every job. That meant one set of live
MCP sessions, opened from whatever configuration existed at boot, serving every
tenant — and a Filesystem server rooted at whichever vault `get_tenant()`
resolved to at startup, which is the default tenant's.
"""
import asyncio
import platform
import sys
from pathlib import Path

from core.tool_router import ToolRouter

_IS_WIN = platform.system() == "Windows"
_NPX_CMD = "npx.cmd" if _IS_WIN else "npx"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS_DIR = _BACKEND_ROOT / "tools"


class WorkerServerModule:
    """
    Satisfies the server_module interface expected by OrchestrationEngine and
    step executors. Only connects to Python-native tools and locally-available
    MCP servers; silently skips anything that can't connect.
    """

    def __init__(self):
        self.agent_sessions: dict = {}     # mcp_server_name -> ClientSession
        self.tool_router = ToolRouter()    # {server}__{tool} -> (session_name, tool_name)
        self._session_tools: dict = {}     # session name -> tools it advertised
        self.memory_store = None           # workers don't maintain long-term memory store
        self.mcp_disabled: list[str] = []  # names of MCP servers that failed to connect
        self._exit_stack = None

    @classmethod
    async def build_shared(
        cls,
        disabled_mcp_names: list[str] | None = None,
    ) -> "WorkerServerModule":
        """The tenant-independent native tool servers. Once per process.

        Everything here advertises the same tools to everybody, so one set is
        shared by every tenant the process serves. The Filesystem server is
        excluded: it is rooted at a vault, and a vault belongs to a tenant.
        """
        instance = cls()
        await instance._connect_native(
            _get_native_mcp_servers(_TOOLS_DIR, _BACKEND_ROOT, scope="shared"),
            set(disabled_mcp_names or []),
        )
        instance._attach_memory_store()
        return instance

    @classmethod
    async def build_for_tenant(
        cls,
        shared: "WorkerServerModule | None" = None,
        disabled_mcp_names: list[str] | None = None,
    ) -> "WorkerServerModule":
        """The current tenant's MCP: its vault-rooted Filesystem, its own servers.

        `shared` is folded into the returned module's sessions and router so
        callers see one set. Its sessions are *referenced*, never owned — this
        module's `close()` only closes what this module opened.
        """
        instance = cls()
        disabled = set(disabled_mcp_names or [])

        # If the vault is an object store, this replica's working copy of it may
        # be empty — a pod that has never served this tenant, or one that was
        # replaced. Materialise it before rooting the Filesystem MCP server at
        # it, or the tenant's own `search_files` reports an empty vault. A no-op
        # on a plain install, where the directory *is* the vault.
        from core.vault_backend import get_vault

        vault = get_vault()
        if getattr(vault, "materialises", False):
            try:
                pulled = vault.hydrate()
                if pulled:
                    print(
                        f"[worker_server_module] materialised {pulled} vault file(s)",
                        flush=True,
                    )
            except Exception as exc:
                # A cold working copy degrades the vault; it must not stop the
                # tenant's session set from being built.
                print(f"[worker_server_module] vault hydration failed: {exc}", flush=True)

        if shared is not None:
            instance.agent_sessions.update(shared.agent_sessions)
            instance._session_tools.update(shared._session_tools)
            for key, value in shared.tool_router.items():
                instance.tool_router[key] = value
            instance.mcp_disabled.extend(shared.mcp_disabled)
            instance.memory_store = shared.memory_store

        # The Filesystem server, rooted at *this* tenant's vault.
        await instance._connect_native(
            _get_native_mcp_servers(_TOOLS_DIR, _BACKEND_ROOT, scope="tenant"), disabled
        )
        await instance._connect_user_mcp(disabled)
        if shared is None:
            instance._attach_memory_store()
        return instance

    # ── connection helpers ───────────────────────────────────────────────────

    async def _connect_native(self, native_servers: dict, disabled: set) -> None:
        from contextlib import AsyncExitStack
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from datetime import timedelta
        from core.config import MCP_SESSION_READ_TIMEOUT

        instance = self
        if instance._exit_stack is None:
            instance._exit_stack = AsyncExitStack()
        exit_stack = instance._exit_stack

        _SESSION_READ_TIMEOUT = timedelta(seconds=MCP_SESSION_READ_TIMEOUT)

        for server_name, params in native_servers.items():
            if server_name in disabled:
                instance.mcp_disabled.append(server_name)
                continue
            try:
                read, write = await exit_stack.enter_async_context(
                    stdio_client(params)
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=_SESSION_READ_TIMEOUT)
                )
                await session.initialize()
                instance.agent_sessions[server_name] = session
                # Register tools into the router as {server}__{tool}, with the
                # bare name kept as an alias — see core/tool_router.py. The
                # worker used to key native *and* user MCP on the bare name, so
                # a tenant's own server could shadow a native tool.
                tools_result = await session.list_tools()
                # Cached here rather than on first use: this call has already
                # been made, and every tenant folding in the shared module then
                # inherits the answer instead of re-listing eight servers.
                instance._session_tools[server_name] = tools_result.tools
                for tool in tools_result.tools:
                    instance.tool_router.register(server_name, tool.name)
            except Exception as e:
                print(
                    f"[worker_server_module] Skipping MCP server '{server_name}': {e}",
                    flush=True,
                )
                instance.mcp_disabled.append(server_name)

    async def _connect_user_mcp(self, disabled: set) -> None:
        """This tenant's own MCP servers.

        In scale mode `stdio_mcp_allowed()` is force-disabled, so in practice
        these are remote (SSE) sessions — no subprocess, which is what makes a
        per-tenant set affordable at fleet scale.
        """
        from contextlib import AsyncExitStack
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from datetime import timedelta
        from core.config import MCP_SESSION_READ_TIMEOUT

        instance = self
        if instance._exit_stack is None:
            instance._exit_stack = AsyncExitStack()
        exit_stack = instance._exit_stack

        _SESSION_READ_TIMEOUT = timedelta(seconds=MCP_SESSION_READ_TIMEOUT)

        # Browser Automation (playwright) requires a local browser install — skip in workers.
        _BROWSER_MCP_NAMES = {"Browser Automation", "browser", "playwright"}
        _BROWSER_MCP_PKGS = {"@playwright/mcp", "playwright-mcp"}

        from core.scale.context import resolve_mcp_servers
        user_mcp_configs = await resolve_mcp_servers()
        for cfg in user_mcp_configs:
            server_name = cfg.get("name", "")
            if not server_name or server_name in disabled:
                continue
            if not cfg.get("enabled", True):
                continue
            # Skip native servers already connected above
            if server_name in instance.agent_sessions:
                continue
            # Skip browser/playwright MCP — requires a local browser install
            if server_name in _BROWSER_MCP_NAMES:
                instance.mcp_disabled.append(server_name)
                continue
            args_str = " ".join(str(a) for a in cfg.get("args", []))
            if any(pkg in args_str for pkg in _BROWSER_MCP_PKGS):
                instance.mcp_disabled.append(server_name)
                continue
            server_type = cfg.get("server_type", "stdio")
            try:
                if server_type == "remote":
                    params = _build_remote_mcp_params(cfg)
                    if params is None:
                        instance.mcp_disabled.append(server_name)
                        continue
                    from mcp.client.sse import sse_client
                    read, write = await exit_stack.enter_async_context(
                        sse_client(params["url"], headers=params.get("headers", {}))
                    )
                else:
                    params = _build_stdio_mcp_params(cfg)
                    if params is None:
                        instance.mcp_disabled.append(server_name)
                        continue
                    read, write = await exit_stack.enter_async_context(
                        stdio_client(params)
                    )
                session = await exit_stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=_SESSION_READ_TIMEOUT)
                )
                await session.initialize()
                # `ext_mcp_` is how the rest of the engine spells "this session
                # belongs to a user-configured MCP server" — core/server.py:563,
                # routes/tools.py, mcp_client.py, and the three sites in
                # react_engine.py that strip it back off to name the server in an
                # error. The worker used its bare name instead, so a user MCP
                # tool was declared to the model as `sometool` here and as
                # `myserver__sometool` on the API server: an agent's stored
                # tools[] array could only ever match in one of the two places,
                # and on a worker it silently matched nothing.
                agent_key = f"ext_mcp_{server_name}"
                instance.agent_sessions[agent_key] = session
                tools_result = await session.list_tools()
                instance._session_tools[agent_key] = tools_result.tools
                for tool in tools_result.tools:
                    # alias=False: a tenant's own MCP server must not be able to
                    # take over a native tool's bare name for that tenant's runs.
                    instance.tool_router.register(
                        server_name, tool.name, session_key=agent_key, alias=False
                    )
                print(f"[worker_server_module] Connected user MCP '{server_name}'", flush=True)
            except Exception as e:
                print(
                    f"[worker_server_module] Skipping user MCP '{server_name}': {e}",
                    flush=True,
                )
                instance.mcp_disabled.append(server_name)

    def _attach_memory_store(self) -> None:
        """Postgres-backed long-term memory, if this deployment has one."""
        try:
            import os
            pg_url = os.getenv("SCALE_POSTGRES_URL", "")
            if pg_url:
                from core.memory import MemoryStore
                self.memory_store = MemoryStore()
        except Exception:
            pass

    async def close(self) -> None:
        """Close what this module opened. Never what it borrowed.

        MUST be awaited from the task that ran the build — anyio requires a
        cancel scope to be exited by the task that entered it, and closing an
        MCP stack from another task propagates a CancelledError that tears down
        unrelated sessions. `core/server.py`'s `_filesystem_mcp_manager` carries
        the same warning and the scar that produced it; `core/scale/mcp_pool.py`
        is what guarantees it here.
        """
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._exit_stack = None


def _get_native_mcp_servers(
    tools_dir: Path, backend_root: Path, scope: str = "all"
) -> dict:
    """Return native MCP server configs for the worker process.

    Uses core.tools_registry as the single source of truth for tool filenames.
    WORKER_NATIVE_TOOLS / WORKER_NPX_TOOLS control what runs in workers vs. not.

    `scope` splits them by whether they depend on who is calling:

        "shared"  everything that advertises the same tools to everybody
        "tenant"  the Filesystem server, rooted at the caller's vault
        "all"     both, which is what a single-tenant process wants
    """
    import os
    from pathlib import Path as _Path
    from mcp import StdioServerParameters
    from core.tools_registry import (
        ALL_NATIVE_TOOLS,
        TENANT_SCOPED_TOOLS,
        WORKER_NATIVE_TOOLS,
        WORKER_NPX_TOOLS,
    )

    if scope not in ("shared", "tenant", "all"):
        raise ValueError(f"unknown scope {scope!r}")

    # Tool subprocesses need the backend root on PYTHONPATH so they can do
    # `from core.config import ...` — same as when the main server spawns them.
    tool_env = os.environ.copy()
    existing_pp = tool_env.get("PYTHONPATH", "")
    backend_root_str = str(backend_root)
    tool_env["PYTHONPATH"] = f"{backend_root_str}{os.pathsep}{existing_pp}" if existing_pp else backend_root_str

    servers = {}

    def _python_tool(name: str, env: dict) -> None:
        script = _Path(ALL_NATIVE_TOOLS[name])
        if script.exists():
            servers[name] = StdioServerParameters(command=sys.executable, args=[str(script)], env=env)
        else:
            print(f"[worker_server_module] Tool script not found, skipping '{name}': {script}", flush=True)

    if scope in ("shared", "all"):
        # Python-native tools (subset safe for headless worker processes) that
        # advertise the same behaviour to everybody.
        for name in sorted(WORKER_NATIVE_TOOLS - TENANT_SCOPED_TOOLS):
            _python_tool(name, tool_env)

        # npx-based tools available to workers
        for name, args in WORKER_NPX_TOOLS.items():
            servers[name] = StdioServerParameters(command=_NPX_CMD, args=args)

    if scope in ("tenant", "all"):
        # Tools whose subprocess resolves the vault, the store or settings for
        # itself. A ContextVar does not survive a fork+exec, so one of these
        # spawned once and shared reads the *default* tenant's data whoever
        # calls it. Spawned per tenant instead, told who they serve.
        #
        # The arithmetic is worth knowing: this is one extra subprocess per tool
        # per live pool entry. In the shipped single-tenant product that is the
        # same count as before. On a cloud worker `sql` and `code_vault_search`
        # are already excluded, and D8 drops `bash` and `vault_sandbox`, which
        # leaves `file_reader` — one process, plus the Filesystem server below.
        from core.tenancy import get_tenant

        tenant_env = dict(tool_env)
        tenant_env["SYNAPSE_TENANT_ID"] = get_tenant()
        for name in sorted(WORKER_NATIVE_TOOLS & TENANT_SCOPED_TOOLS):
            _python_tool(name, tenant_env)

        # Filesystem MCP (Node.js) — rooted at the current tenant's vault, which
        # is the only directory a worker has any business exposing. It used to be
        # SYNAPSE_DATA_DIR, i.e. every tenant's config and credentials on a
        # shared worker, and that variable is going away besides.
        #
        # This is *why* the split exists: `_vault_root()` reads the tenant from
        # the context, so a server built once at startup is rooted at whichever
        # tenant happened to be current then — the default one.
        from core.vault import _vault_root
        worker_fs_paths = os.getenv("WORKER_FILESYSTEM_PATHS", str(_vault_root()))
        filesystem_paths = [p.strip() for p in worker_fs_paths.split(",") if p.strip()]
        if filesystem_paths:
            servers["filesystem"] = StdioServerParameters(
                command=_NPX_CMD,
                args=["-y", "@modelcontextprotocol/server-filesystem"] + filesystem_paths,
            )

    return servers


def _build_stdio_mcp_params(cfg: dict):
    """Build StdioServerParameters from a saved mcp_servers.json config dict.

    Returns None when this deployment must not spawn user-supplied stdio servers.
    Workers run in scale mode, where ``stdio_mcp_allowed()`` is force-disabled —
    this is a second, independent spawn sink from
    ``MCPClientManager.connect_stdio_server``, so it needs its own gate rather
    than inheriting one.
    """
    import shlex
    from mcp import StdioServerParameters
    from core.mcp_client import stdio_mcp_allowed, check_stdio_command_allowed

    command = cfg.get("command", "")
    if not command:
        return None

    if not stdio_mcp_allowed():
        print(f"[worker] Refusing to spawn stdio MCP server "
              f"'{cfg.get('name', '?')}': stdio MCP is disabled on this deployment.",
              flush=True)
        return None
    try:
        check_stdio_command_allowed(command)
    except ValueError as e:
        print(f"[worker] Refusing to spawn stdio MCP server "
              f"'{cfg.get('name', '?')}': {e}", flush=True)
        return None

    args_raw = cfg.get("args", [])
    # Support both list and space-separated string for args
    if isinstance(args_raw, str):
        args_raw = shlex.split(args_raw)
    env = cfg.get("env") or {}
    return StdioServerParameters(command=command, args=list(args_raw), env=env or None)


def _build_remote_mcp_params(cfg: dict) -> dict | None:
    """Build connection params dict for an SSE/HTTP MCP server."""
    url = cfg.get("url", "")
    if not url:
        return None
    # Token was stripped during sync; if present (JSON fallback path), include it
    token = cfg.get("token", "")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return {"url": url, "headers": headers}
