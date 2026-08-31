"""The native vault MCP server, and the two properties it exists to hold.

`tools/vault_fs.py` replaced the Node `@modelcontextprotocol/server-filesystem`
on the worker path. Both properties below were true of neither predecessor:
the Node server was rooted at a directory (a hydrated working copy, empty on a
replica that had not served the tenant) and it needed an `npx` no scale-mode
image ships, so it never actually ran.
"""

from __future__ import annotations

import json

import pytest

from core.scale.context import set_resource_provider
from core.storage import set_blob_store
from core.storage.base import LocalBlobStore
from core.tenancy import tenant_scope


class _Provider:
    """Enough of a resource provider to unlock `tenant_scope`.

    Tenancy is deliberately coupled to having one — switching tenants without a
    tenant-aware way to resolve resources would give every tenant the same
    agents and tools, so `core/tenancy.py` refuses. See
    `test_tenancy.py::test_registering_a_provider_is_what_unlocks_tenancy`.
    """

    async def resolve_agents(self):
        return []

    async def resolve_custom_tools(self):
        return []

    async def resolve_mcp_servers(self):
        return []


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """A local blob store, which applies `tenant_key` exactly as S3 does."""
    monkeypatch.setenv("SYNAPSE_BLOB_DIR", str(tmp_path))
    store = LocalBlobStore(tmp_path)
    set_blob_store(store)
    set_resource_provider(_Provider())
    yield store
    set_resource_provider(None)
    set_blob_store(None)


async def _call(name: str, arguments: dict) -> dict:
    from tools import vault_fs

    # `ready()` would otherwise run the bootstrap inline against a database that
    # is not here. The tenant is established by the `tenant_scope` in each test.
    async def _noop() -> None:
        return None

    from core import tool_server

    original, tool_server.ready = tool_server.ready, _noop
    try:
        result = await vault_fs.call_tool.__wrapped__(name, arguments)
    except AttributeError:
        result = await vault_fs.call_tool(name, arguments)
    finally:
        tool_server.ready = original
    return json.loads(result[0].text)


@pytest.mark.anyio
async def test_listing_cannot_see_another_tenants_files(vault):
    """The isolation is the blob store's, and this proves it rather than assumes it.

    `core/storage/base.py::tenant_key` prefixes every key with the current
    tenant *inside* the store — the module's own reasoning is that a call site
    which forgets is a cross-tenant read, and `tools/vault_fs.py` is one more
    call site. Nothing in that file mentions a tenant, which is the point; this
    is what makes that safe rather than lucky.
    """
    with tenant_scope("org-a"):
        vault.put("secret.txt", "org a's private notes")

    with tenant_scope("org-b"):
        vault.put("mine.txt", "org b's own file")
        listing = await _call("list_files", {})

    assert listing["files"] == ["mine.txt"], listing
    assert "secret.txt" not in listing["files"]


@pytest.mark.anyio
async def test_read_and_search_go_through_the_store_not_a_path(vault):
    """A key, not a directory — so this works where there is no filesystem."""
    body = "alpha\nbeta\ngamma\ndelta\n"
    with tenant_scope("org-a"):
        vault.put("notes.txt", body)

        chunk = await _call("read_file", {"path": "notes.txt", "start_line": 2, "end_line": 3})
        assert chunk["content"] == "beta\ngamma"
        assert chunk["total_lines"] == 4

        found = await _call("search_files", {"query": "gamma"})

    assert found["files_with_matches"] == 1
    assert found["results"][0]["path"] == "notes.txt"


@pytest.mark.anyio
async def test_a_missing_key_is_an_error_not_a_crash(vault):
    with tenant_scope("org-a"):
        answer = await _call("read_file", {"path": "nope.txt"})
    assert "error" in answer and "Not found" in answer["error"]


@pytest.mark.anyio
async def test_a_multi_tenant_process_builds_no_chroma_index(vault, monkeypatch):
    """One index cannot serve many tenants, so a fleet process holds none.

    `MemoryStore` is ChromaDB, and its index path resolves through
    `get_tenant()`. `build_shared()` runs at worker startup *before any tenant is
    bound*, so the path it computes belongs to the default tenant — and
    `build_for_tenant()` then folds that same store into every tenant's module.
    One index, no tenant dimension, every org sharing it.

    The guard is on `is_multi_tenant()` rather than on an environment variable
    on purpose: it is a correctness rule, not a deployment preference, and a
    variable nothing sets is exactly the class of bug this codebase keeps
    paying for.
    """
    monkeypatch.setenv("SCALE_POSTGRES_URL", "postgresql+asyncpg://nobody@localhost/none")

    from core.scale.worker_server_module import WorkerServerModule

    module = WorkerServerModule()
    module._attach_memory_store()

    assert module.memory_store is None, (
        "a multi-tenant process built a single-index memory store; "
        "every org would share it"
    )
