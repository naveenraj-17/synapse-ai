"""
Everything that hands out a vault path derives it from the blob store.

The vault moved out of `backend/data` when blob storage became tenant-scoped,
but five callers kept computing it from `__file__` or from DATA_DIR. Two of
them are Docker `-v` mounts guarded by `if vault_root.exists()`, so a stale
path does not raise — the sandbox just silently loses its `/data` mount and
tool code stops being able to read vaulted results. The Filesystem MCP server
and the compaction archive had the same drift, without even the guard.

These tests pin the property that fixes them all: a vault path is whatever the
current tenant's blob store says it is, and it moves when the tenant does.
"""
import inspect
import re
from pathlib import Path

import pytest

from core.scale.context import set_resource_provider
from core.tenancy import tenant_scope
from core.vault import _vault_root


class _Provider:
    """Minimal resource provider — registering one is what unlocks tenancy."""

    async def resolve_agent(self, agent_id):
        return None

    async def resolve_orchestration(self, orch_id):
        return None

    async def resolve_custom_tools(self):
        return []

    async def resolve_mcp_servers(self):
        return []


@pytest.fixture
def multi_tenant():
    set_resource_provider(_Provider())
    yield
    set_resource_provider(None)


def test_compaction_archive_is_inside_the_vault():
    from core.compaction import _archive_dir

    assert _archive_dir() == _vault_root() / "compaction_archives"


def test_compaction_archive_follows_the_tenant(multi_tenant):
    from core.compaction import _archive_dir

    with tenant_scope("acme"):
        acme = _archive_dir()
    with tenant_scope("globex"):
        globex = _archive_dir()

    assert acme != globex
    assert "acme" in acme.parts
    assert "globex" in globex.parts


def test_archive_dir_is_not_bound_at_import():
    """A module-level constant would pin every tenant to the first importer."""
    import core.compaction as compaction

    assert not hasattr(compaction, "COMPACT_ARCHIVE_DIR")


@pytest.mark.parametrize(
    "module_name",
    [
        "core.orchestration.steps",
        "core.react_engine",
        "core.server",
        # The stdio tool servers. They are separate processes, so nothing in the
        # rest of the suite would notice them drifting — and `tools/sandbox.py`
        # had in fact never been repointed: it built `backend/data/vault` from
        # `__file__` and mkdir'd it at import, which is what kept recreating
        # `backend/data` on developer machines. The docstring above warned that
        # this list was the gap; these two are it closing.
        "tools.bash",
        "tools.sandbox",
    ],
)
def test_nothing_re_derives_the_old_vault_path(module_name):
    """No module may reconstruct `.../data/vault` from `__file__` or DATA_DIR.

    Source-level because the two sandbox uses are `-v` mounts built inside a
    Docker branch that needs a docker binary, a built image and a live tool to
    reach at runtime — and, being `.exists()`-guarded, a wrong path there raises
    nothing. The regression is textual, so the guard is too.
    """
    import importlib

    module = importlib.import_module(module_name)
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")

    assert not re.search(r'["\']data["\']\s*\)?\s*/\s*["\']vault["\']', source)
    assert "_vault_root()" in source


def test_sandbox_mounts_the_tenant_vault():
    """Both Docker sandboxes mount whatever the blob store calls the vault."""
    import importlib

    for module_name in ("core.orchestration.steps", "core.react_engine"):
        source = Path(
            inspect.getfile(importlib.import_module(module_name))
        ).read_text(encoding="utf-8")
        assert "/data:ro" in source, f"{module_name} lost its read-only vault mount"


def _worker_servers():
    from core.scale.worker_server_module import _get_native_mcp_servers

    backend_root = Path(inspect.getfile(_get_native_mcp_servers)).resolve().parent.parent.parent
    return _get_native_mcp_servers(backend_root / "tools", backend_root)


def test_a_worker_reaches_the_vault_without_a_directory():
    """The vault server is spawned, and it takes no path.

    This replaces an assertion that the Node Filesystem server was rooted at
    `_vault_root()`. That was the right guard for the wrong mechanism: a
    replica's vault directory is a working copy the blob store materialises on
    demand, so rooting a server at it meant reading whatever happened to have
    been hydrated — and on an object store there is no directory at all.

    `tools/vault_fs.py` goes through `core.storage.get_blob_store()`, where
    `tenant_key` applies the tenant inside the store. So the property the old
    test was defending — a shared worker must not expose one tenant's files to
    another — now holds by construction rather than by a path, and what is worth
    asserting is that the server is present and carries no directory argument
    anybody could widen.
    """
    servers = _worker_servers()

    vault = servers.get("vault")
    assert vault is not None, "the vault server is not spawned in a worker"
    assert str(_vault_root()) not in " ".join(vault.args), (
        "the vault server was handed a directory; it addresses the blob store by key"
    )
    assert vault.env.get("SYNAPSE_TENANT_ID") is not None, (
        "the vault server must be told which tenant it serves"
    )


def test_a_worker_spawns_no_npx():
    """No worker MCP server may need Node.

    Every scale-mode image ships Python and no Node, so an `npx` server does not
    degrade — it fails on every tenant's module build, forever, at about seven
    seconds each. That is what `WORKER_NPX_TOOLS` being empty is for, and this
    is the assertion that keeps it empty: a server added back here is a fleet
    that silently loses a tool and gains a stall.
    """
    for name, params in _worker_servers().items():
        assert "npx" not in params.command, f"{name} spawns npx: {params.command}"
