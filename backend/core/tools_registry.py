"""
Shared registry of native MCP tool scripts.
Single source of truth for tool filenames used by both the API server and workers.
Import this instead of hard-coding paths in server.py or worker_server_module.py.
"""
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"

# All native Python-based MCP tools available in the system
ALL_NATIVE_TOOLS: dict[str, str] = {
    "time":              str(_TOOLS_DIR / "time.py"),
    "sql":               str(_TOOLS_DIR / "sql_agent.py"),
    "personal_details":  str(_TOOLS_DIR / "personal_details.py"),
    "collect_data":      str(_TOOLS_DIR / "collect_data.py"),
    "pdf_parser":        str(_TOOLS_DIR / "pdf_parser.py"),
    "xlsx_parser":       str(_TOOLS_DIR / "xlsx_parser.py"),
    "vault_sandbox":     str(_TOOLS_DIR / "sandbox.py"),
    "code_vault_search": str(_TOOLS_DIR / "code_search.py"),
    "web_scraper":       str(_TOOLS_DIR / "web_scraper.py"),
    "bash":              str(_TOOLS_DIR / "bash.py"),
    "file_reader":       str(_TOOLS_DIR / "file_reader.py"),
}

# Tools whose *subprocess* resolves tenant state for itself — the vault, the
# store, or the tenant's settings — rather than being handed what it needs.
#
# A ContextVar does not cross a process boundary, so one of these spawned once
# and shared reads the default tenant's data whoever calls it. They are
# therefore spawned per tenant, with `core/tool_server.py` telling each which
# tenant it serves. Everything not listed here advertises the same behaviour to
# everybody and is shared process-wide.
#
# `tests/install/test_tenant_scoped_tools.py` derives this set from the imports
# and fails if a tool starts reading tenant state without joining it.
TENANT_SCOPED_TOOLS: set[str] = {
    "bash",
    "code_vault_search",
    "file_reader",
    "sql",
    "vault_sandbox",
}

# Tools safe for headless worker processes.
# Excluded from workers: personal_details (UI-only), code_vault_search (large
# index, memory-heavy in workers).
#
# `sql` was excluded too, with the reason "needs DB config injection". That was
# true when a worker had no way to know whose database configs to read — and it
# stopped being true in the tenancy refactor: `tools/sql_agent.py::_load_db_configs`
# reads `collections.load("db_configs")` through the store, `sql` is in
# TENANT_SCOPED_TOOLS below, and `core/tool_server.py::bootstrap` tells each
# subprocess which tenant it serves. Nothing is injected; it resolves its own.
#
# The cost is the one `core/scale/worker_server_module.py` names: one more
# subprocess per tool per live pool entry.
WORKER_NATIVE_TOOLS: set[str] = {
    "time",
    "collect_data",
    "pdf_parser",
    "xlsx_parser",
    "vault_sandbox",
    "web_scraper",
    "bash",
    "file_reader",
    "sql",
}

# npx-based MCP servers available to workers.
# Excluded: Browser Automation (requires local display), Google Workspace (OAuth session).
WORKER_NPX_TOOLS: dict[str, list[str]] = {
    "Sequential Thinking": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
}
