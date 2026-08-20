"""
A tool subprocess is told which tenant it serves, and that is all it is told.

Native tools are MCP servers running as subprocesses, so a ContextVar does not
reach them: `tools/bash.py` and `tools/sandbox.py` resolved
`core.vault._vault_root()` to the *default* tenant's vault whoever called them,
and `load_settings()` returned the shipped defaults because nothing installs the
settings provider in a subprocess.

`core/tool_server.py` fixes both. It reads `SYNAPSE_TENANT_ID`, and this file
pins the two things that makes true and the one thing it must not:

* it is the only module in the tree allowed to read that variable;
* it fixes the tenant of a process that serves exactly one;
* it does **not** enable multi-tenancy. That still requires an embedder to
  register a resource provider, which is the boundary D30 describes — no
  environment variable can produce a second tenant.
"""
import ast
import os
import pathlib
import subprocess
import sys

import pytest

from core import tenancy, tool_server

_BACKEND = pathlib.Path(__file__).resolve().parent.parent.parent

_VAR = "SYNAPSE_TENANT_ID"

#: The one module permitted to *read* SYNAPSE_TENANT_ID. Same arrangement as
#: core/store/importer.py and SYNAPSE_DATA_DIR: named here so a second entry is
#: a conversation rather than a silent widening.
_READERS = {"core/tool_server.py"}

#: The one module permitted to *write* it, into the environment of a tool server
#: it is spawning. Writing is the other half of the same mechanism and a
#: different permission: it labels a child, it does not change this process.
_WRITERS = {"core/scale/worker_server_module.py"}

_SEARCH_ROOTS = ("core", "tools", "services", "synapse")


def _sources():
    for root in _SEARCH_ROOTS:
        base = _BACKEND / root if root != "synapse" else _BACKEND.parent / "synapse"
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "venv" in path.parts or "__pycache__" in path.parts:
                continue
            yield path


def _is_var(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == _VAR


def _accesses(source: str) -> tuple[bool, bool]:
    """(reads, writes) of the variable in `source`.

    Deliberately AST-based rather than a substring search: prose that explains
    the mechanism is not a use of it, and this file, `core/tenancy.py` and
    `core/tool_server.py` all have to be able to say the name out loud.
    """
    tree = ast.parse(source)
    reads = writes = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"getenv", "get", "pop", "setdefault"} and node.args and _is_var(node.args[0]):
                reads = True
        elif isinstance(node, ast.Subscript) and _is_var(node.slice):
            if isinstance(node.ctx, ast.Store):
                writes = True
            else:
                reads = True

    return reads, writes


def test_only_one_module_reads_the_tenant_variable():
    read_by, written_by = [], []
    for path in _sources():
        source = path.read_text(encoding="utf-8")
        if _VAR not in source:
            continue
        rel = path.relative_to(_BACKEND).as_posix()
        reads, writes = _accesses(source)
        if reads:
            read_by.append(rel)
        if writes:
            written_by.append(rel)

    assert set(read_by) <= _READERS, (
        f"{_VAR} may only be read by {sorted(_READERS)} — the module that exists "
        "to tell a tool subprocess which tenant it serves. Also read by: "
        f"{sorted(set(read_by) - _READERS)}. A second reader is a tenancy "
        "decision, not an import."
    )
    assert set(written_by) <= _WRITERS, (
        f"{_VAR} may only be written by {sorted(_WRITERS)}, where a tool server "
        f"is spawned. Also written by: {sorted(set(written_by) - _WRITERS)}."
    )
    # And the mechanism must still exist — a guard that passes because the thing
    # it guards was deleted is worse than no guard.
    assert set(read_by) == _READERS
    assert set(written_by) == _WRITERS


class TestAdoptingATenant:
    def test_the_tenant_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_TENANT_ID", "acme")
        assert tool_server.process_tenant() == "acme"

    def test_an_unset_variable_leaves_the_default_alone(self, monkeypatch):
        monkeypatch.delenv("SYNAPSE_TENANT_ID", raising=False)
        assert tool_server.process_tenant() == ""

        tenancy.adopt_process_tenant(tool_server.process_tenant())
        assert tenancy.get_tenant() == "default"

    def test_adopting_changes_what_the_vault_resolves_to(self, monkeypatch, tmp_path):
        """The whole point: a subprocess reads *its* tenant's vault."""
        from core.storage import LocalBlobStore, set_blob_store

        set_blob_store(LocalBlobStore(tmp_path))
        try:
            from core.vault import _vault_root

            before = _vault_root()
            tenancy.adopt_process_tenant("acme")
            after = _vault_root()
        finally:
            set_blob_store(None)
            tenancy._current_tenant.set("default")

        assert before != after
        assert after.parts[-2] == "acme"


class TestItIsNotADoorToMultiTenancy:
    """Naveen's condition on this, and the reason it is safe.

    Setting one tenant in a process that serves one tenant is not the same
    capability as switching between two, and only the second is what the OSS
    product withholds.
    """

    def test_adopting_does_not_enable_tenant_scope(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_TENANT_ID", "acme")
        tenancy.adopt_process_tenant(tool_server.process_tenant())
        try:
            assert tenancy.is_multi_tenant() is False
            with pytest.raises(tenancy.SingleTenantError):
                with tenancy.tenant_scope("globex"):
                    pass
        finally:
            tenancy._current_tenant.set("default")

    def test_the_engine_itself_never_reads_the_variable(self, monkeypatch):
        """Importing the engine with it set must change nothing.

        Only a spawned tool server acts on it, and only because its parent put
        it there deliberately.
        """
        program = (
            "import os\n"
            "os.environ['SYNAPSE_TENANT_ID'] = 'globex'\n"
            "from core.tenancy import get_tenant, is_multi_tenant\n"
            "import core.server, core.scale.worker\n"
            "print(get_tenant(), is_multi_tenant())\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_BACKEND)
        result = subprocess.run(
            [sys.executable, "-c", program],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().endswith("default False"), result.stdout


class TestBootstrap:
    async def test_it_installs_the_settings_provider(self, monkeypatch):
        """The Phase 6 regression: a tool subprocess saw the shipped defaults.

        `load_settings()` in a subprocess returned `default_settings()` because
        nothing there ever called `install_provider()`, so `bash_allowed_dirs`
        and `vault_threshold` stopped being honoured wherever a tool read them.
        """
        from core import settings_runtime
        from core.config import get_settings_provider, set_settings_provider

        set_settings_provider(None)
        settings_runtime.reset_state()
        monkeypatch.delenv("SYNAPSE_TENANT_ID", raising=False)
        try:
            assert get_settings_provider() is None
            await tool_server.bootstrap()
            assert get_settings_provider() is not None
        finally:
            set_settings_provider(None)
            settings_runtime.reset_state()

    async def test_it_never_raises(self, monkeypatch):
        """A tool server that cannot reach the database still has to start."""
        from core import settings_runtime
        from core.config import set_settings_provider

        async def _boom(*args, **kwargs):
            raise RuntimeError("no database here")

        monkeypatch.setattr(settings_runtime, "refresh", _boom)
        try:
            await tool_server.bootstrap()  # must not raise
        finally:
            set_settings_provider(None)
            settings_runtime.reset_state()
