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

`SYNAPSE_TENANT_ID` and `SYNAPSE_DOCUMENT_RESOLVER`
---------------------------------------------------
This module is the only one permitted to read them, in the same way
`core/store/importer.py` is the only module permitted to name
`SYNAPSE_DATA_DIR`. `tests/unit/test_tool_server.py` asserts the allowlist, so a
third one is a conversation rather than a silent widening.

`SYNAPSE_DOCUMENT_RESOLVER` names an import path — `package.module:function` —
installed as `core/store/collections.py`'s document resolver. It exists because
a tool subprocess reads the store *itself*: an embedder that keeps credentials
outside `collections` and stores references cannot swap them in the parent, so
the subprocess has to be told how. Unset in the shipped product, where documents
hold their own values and there is nothing to resolve.

It names code to import, so whatever can set it can already run code in this
process — it widens nothing that spawning the subprocess did not already.

It is worth being precise about what it does and does not do. It fixes the
tenant of a process that already exists to serve exactly one tenant — the parent
spawns a separate server per tenant and labels each. It does **not** enable
multi-tenancy: `tenant_scope()` is still shut unless an embedder registers a
resource provider, so there is no path from this variable to a process serving
two tenants, and nothing in the shipped product sets it at all.
"""
from __future__ import annotations

import os
import sys


def process_tenant() -> str:
    """The tenant this subprocess was spawned to serve, if it was told."""
    return os.getenv("SYNAPSE_TENANT_ID", "").strip()


def _install_document_resolver() -> None:
    """Point `collections` at the embedder's resolver, if one was named."""
    spec = os.getenv("SYNAPSE_DOCUMENT_RESOLVER", "").strip()
    if not spec or ":" not in spec:
        return

    import importlib

    module_name, _, attribute = spec.partition(":")
    from core.store import collections

    collections.set_document_resolver(getattr(importlib.import_module(module_name), attribute))


def _attach_store() -> None:
    """Bind the store without letting this process create the schema.

    `get_store()` is lazy and runs `init_db()` — `create_all` plus migrations —
    on first use. **A tool server must never be the process that does that.** It
    is spawned by a server or a worker that already owns the schema, so any DDL
    from here is at best redundant and at worst wrong: an embedder whose tables
    carry columns and policies the engine does not know about (a tenant column,
    a foreign key, a row-level security policy) would get a second, unpoliced
    set created underneath it. That is the same hazard the scale worker's
    `set_store()` call exists to prevent, one process further out.

    In the cloud fleet this surfaced as `permission denied for schema public`:
    the tool subprocess connects as an application role that deliberately cannot
    CREATE, so `collections.load()` raised before any tool ran and every
    database-backed tool was dead. The grant was doing its job; this is the
    thing it was standing in for.

    `set_store()` installs the factory directly, which is what makes `init_db()`
    unreachable — see `core/store/engine.py::get_store`.
    """
    from core.store import set_store
    from core.store.engine import build_engine, build_session_factory, default_url

    set_store(build_session_factory(build_engine(default_url())))


#: Where a diagnostic goes when this process IS an MCP stdio server.
#:
#: **stdout is the JSONRPC channel.** Anything written there is parsed as a
#: protocol message, so a single `print()` corrupts the stream and the client
#: fails with "Failed to parse JSONRPC message from server" — while the real
#: error, the one the print was trying to report, is consumed by the parser and
#: never reaches a log. The failure that follows is a chat turn that simply
#: never starts.
#:
#: The three calls below are deliberately non-fatal and deliberately loud; loud
#: has to mean stderr here, which the parent captures and which no protocol
#: reads.
def _diagnostic(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


async def bootstrap() -> None:
    """Adopt the tenant and point `load_settings()` at the store.

    Never raises. A tool server that cannot reach the database is still useful —
    most of its tools do not need it — and failing to start would take the whole
    session set down with it.
    """
    from core import tenancy

    tenancy.adopt_process_tenant(process_tenant())

    try:
        # Before anything can reach the store lazily, for the same reason
        # `set_store` is first in the scale worker's startup.
        _attach_store()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        _diagnostic(f"[tool_server] store unavailable: {exc}")

    try:
        _install_document_resolver()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        # Deliberately not fatal, and deliberately loud. A tool whose documents
        # carry unresolvable references fails at the point of use with a real
        # error; a tool server that refused to start would take every other
        # tool in the set down with it.
        _diagnostic(f"[tool_server] document resolver unavailable: {exc}")

    try:
        from core import settings_runtime

        settings_runtime.install_provider()
        await settings_runtime.refresh()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        _diagnostic(f"[tool_server] settings unavailable, using defaults: {exc}")
