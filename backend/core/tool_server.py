"""
What a native tool server has to do before it serves its first request.

Native tools are MCP servers running as subprocesses. That makes them ordinary
Python processes that happen to have been spawned by the engine — and it means
two things the engine sets up for itself do not reach them:

1. **A ContextVar does not cross a process boundary.** `tools/bash.py` and
   `tools/sandbox.py` call `core.vault._vault_root()`, which resolves
   `get_blob_store().path_for(...)` → `root / get_tenant()`. Inside a subprocess
   that is always the default tenant, whoever called the tool. Harmless in a
   single-tenant install; a cross-tenant read on a shared fleet.

2. **Nobody installs the settings provider.** Only `core/server.py` and
   `core/scale/worker.py` call `settings_runtime.install_provider()`, so
   `load_settings()` in a tool subprocess returns `default_settings()`. That
   became true when `_load_settings_from_disk` was deleted in Phase 6 and went
   unnoticed: `bash_allowed_dirs` and `vault_threshold` quietly stopped being
   honoured wherever a tool read them for itself.

`bootstrap()` fixes both, and every tool server in `TENANT_SCOPED_TOOLS` calls it
as the first thing in `main()`.

`SYNAPSE_TENANT_ID`
-------------------
This module is the only one permitted to read it, in the same way
`core/store/importer.py` is the only module permitted to name
`SYNAPSE_DATA_DIR`. `tests/unit/test_tool_server.py` asserts the allowlist has
one entry, so a second one is a conversation rather than a silent widening.

It is worth being precise about what it does and does not do. It fixes the
tenant of a process that already exists to serve exactly one tenant — the parent
spawns a separate server per tenant and labels each. It does **not** enable
multi-tenancy: `tenant_scope()` is still shut unless an embedder registers a
resource provider, so there is no path from this variable to a process serving
two tenants, and nothing in the shipped product sets it at all.
"""
from __future__ import annotations

import os


def process_tenant() -> str:
    """The tenant this subprocess was spawned to serve, if it was told."""
    return os.getenv("SYNAPSE_TENANT_ID", "").strip()


async def bootstrap() -> None:
    """Adopt the tenant and point `load_settings()` at the store.

    Never raises. A tool server that cannot reach the database is still useful —
    most of its tools do not need it — and failing to start would take the whole
    session set down with it.
    """
    from core import tenancy

    tenancy.adopt_process_tenant(process_tenant())

    try:
        from core import settings_runtime

        settings_runtime.install_provider()
        await settings_runtime.refresh()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        print(f"[tool_server] settings unavailable, using defaults: {exc}", flush=True)
