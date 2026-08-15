"""
One-time import of a `backend/data/*.json` install into the store.

Existing installs keep their orchestrations, agents, custom tools, MCP servers
and settings as JSON files under `DATA_DIR`. Those files are the thing being
removed, so upgrading has to bring them across — and it has to do so without
asking the user to run anything, because an upgrade that needs a command
becomes a support thread for every self-hoster who missed it.

Runs at startup. Does nothing at all when the store already holds data, so it
is safe to call on every boot and cannot overwrite work done since the import.
On success the folder is renamed to `data.migrated/` rather than deleted: if
something did not come across, the original is still there, and the rename is
also what stops the import running twice.

Everything lands on the single tenant a self-hosted install has. There is no
tenant dimension in the source files to preserve — that is precisely what made
them a single-machine design.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from core.store.models import DEFAULT_TENANT

#: Source file → the model it populates and the columns to build from each item.
#: Order matters only for readability; the tables are independent.
_SOURCES = ("orchestrations", "user_agents", "custom_tools", "mcp_servers", "settings")


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[import] could not read {path.name}: {exc}", flush=True)
        return None


async def store_is_empty() -> bool:
    """True when no orchestration, agent, tool or MCP server exists.

    Settings are deliberately excluded from the check: a fresh install can
    legitimately have settings (written by the setup screen) and no content,
    and skipping the import in that case would strand the user's workflows.
    """
    from core.store import session
    from core.store.models import AgentDB, MCPServerDB, OrchestrationDB, ToolDB

    async with session() as s:
        for model in (OrchestrationDB, AgentDB, ToolDB, MCPServerDB):
            count = (await s.execute(select(func.count()).select_from(model))).scalar() or 0
            if count:
                return False
    return True


async def import_data_dir(data_dir: str | Path, tenant_id: str = DEFAULT_TENANT) -> dict:
    """Import a DATA_DIR into the store. Returns a per-source count."""
    from core.store import session, upsert
    from core.store.models import (
        AgentDB,
        MCPServerDB,
        OrchestrationDB,
        SettingDB,
        ToolDB,
    )
    from core.store.resources import (
        agent_values,
        mcp_server_values,
        orchestration_values,
        tool_values,
    )

    root = Path(data_dir)
    counts = dict.fromkeys(_SOURCES, 0)

    #: source file → (count key, model, conflict target, row builder, "is this
    #: item importable"). The builders are the same ones the live CRUD path
    #: uses, so an imported install and a natively-created one produce identical
    #: rows — when these drifted, the importer became a second schema.
    collections = (
        ("orchestrations.json", "orchestrations", OrchestrationDB, ["id"],
         orchestration_values, lambda i: bool(i.get("id"))),
        ("user_agents.json", "user_agents", AgentDB, ["id"],
         agent_values, lambda i: bool(i.get("id"))),
        ("custom_tools.json", "custom_tools", ToolDB, ["id"],
         tool_values, lambda i: bool(i.get("id") or i.get("name"))),
        ("mcp_servers.json", "mcp_servers", MCPServerDB, ["tenant_id", "name"],
         mcp_server_values, lambda i: bool(i.get("name"))),
    )

    async with session() as s:
        for filename, count_key, model, index_elements, build, importable in collections:
            items = _read(root / filename) or []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict) or not importable(item):
                    continue
                await upsert(
                    s, model,
                    values=build(item, tenant_id),
                    index_elements=index_elements,
                )
                counts[count_key] += 1

        # ── settings ────────────────────────────────────────────────────────
        settings = _read(root / "settings.json") or {}
        for key, value in (settings.items() if isinstance(settings, dict) else []):
            await upsert(
                s, SettingDB,
                values={"tenant_id": tenant_id, "key": key, "value": json.dumps(value)},
                index_elements=["tenant_id", "key"],
            )
            counts["settings"] += 1

    # These rows went in through upsert() directly rather than through the CRUD
    # helpers, so nothing has invalidated the store's read-through cache.
    from core.store import cache
    cache.invalidate_all()

    return counts


async def import_legacy_data_if_present(data_dir: str | Path) -> dict | None:
    """Import `data_dir` once, on first boot after the upgrade.

    Returns the per-source counts when an import ran, None when there was
    nothing to do. Never raises: a failed import must not stop the process from
    starting, and leaving the folder in place means the next boot retries.
    """
    root = Path(data_dir)
    if not root.is_dir():
        return None
    if not any((root / f"{name}.json").is_file() for name in _SOURCES):
        return None

    try:
        if not await store_is_empty():
            return None
        counts = await import_data_dir(root)
    except Exception as exc:
        print(f"[import] import from {root} failed, leaving it in place: {exc}", flush=True)
        return None

    migrated = root.parent / f"{root.name}.migrated"
    try:
        if migrated.exists():
            # A previous import already claimed the name. Keep both rather than
            # overwriting whatever is in there.
            migrated = root.parent / f"{root.name}.migrated.{int(root.stat().st_mtime)}"
        root.rename(migrated)
    except OSError as exc:
        # The data is in the store either way; the rename is only what stops a
        # second import, and `store_is_empty()` already does that.
        print(f"[import] imported, but could not rename {root}: {exc}", flush=True)

    total = sum(counts.values())
    print(
        f"[import] moved {total} items from {root.name} into the store "
        f"({', '.join(f'{k}={v}' for k, v in counts.items() if v)}). "
        f"The folder is now {migrated.name}.",
        flush=True,
    )
    return counts
