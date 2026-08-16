"""
The one-time DATA_DIR import.

Existing installs keep their work as JSON files under DATA_DIR. Those files are
what is being removed, so the upgrade has to bring them across without asking
anyone to run a command — an upgrade step that can be missed becomes a support
thread for every self-hoster who misses it.

The properties that matter are all about not losing or duplicating work:
nothing runs when the store already has content, the folder is renamed so a
second boot does not re-import, and a failure leaves the originals in place.
"""
import json

import pytest
from sqlalchemy import select

from core.store import session
from core.store.importer import (
    import_data_dir,
    import_legacy_data_if_present,
    store_is_empty,
)
from core.store.models import (
    DEFAULT_TENANT,
    AgentDB,
    MCPServerDB,
    OrchestrationDB,
    ScheduleDB,
    SettingDB,
    ToolDB,
)


@pytest.fixture
def data_dir(tmp_path):
    """A DATA_DIR shaped like a real v1.9 install."""
    root = tmp_path / "data"
    root.mkdir()
    (root / "orchestrations.json").write_text(json.dumps([
        {"id": "orch_abc1234", "name": "Nightly report", "description": "runs at 2am",
         "entry_step_id": "s1", "steps": [{"id": "s1", "type": "print"}]},
    ]), encoding="utf-8")
    (root / "user_agents.json").write_text(json.dumps([
        {"id": "agent_1700000000", "name": "Researcher", "model": "gpt-4"},
    ]), encoding="utf-8")
    (root / "custom_tools.json").write_text(json.dumps([
        {"id": "tool_x", "name": "lookup", "code": "return 1"},
    ]), encoding="utf-8")
    (root / "mcp_servers.json").write_text(json.dumps([
        {"name": "github", "label": "GitHub", "url": "https://mcp.example"},
    ]), encoding="utf-8")
    (root / "schedules.json").write_text(json.dumps([
        {"id": "sched_9f1", "name": "Nightly", "enabled": True,
         "target_type": "agent", "target_id": "agent_1700000000", "prompt": "go",
         "schedule_type": "interval", "interval_value": 5, "interval_unit": "minutes",
         "created_at": "2026-01-02T03:04:05Z", "next_run_at": "2026-01-02T03:09:05Z",
         "last_run_at": None},
    ]), encoding="utf-8")
    (root / "settings.json").write_text(json.dumps({
        "model": "claude-x", "vault_threshold": 5000,
    }), encoding="utf-8")
    return root


async def test_everything_comes_across(data_dir):
    counts = await import_data_dir(data_dir)

    assert counts == {
        "orchestrations": 1, "user_agents": 1, "custom_tools": 1,
        "mcp_servers": 1, "schedules": 1, "settings": 2,
    }

    async with session() as s:
        orch = (await s.execute(select(OrchestrationDB))).scalar_one()
        agent = (await s.execute(select(AgentDB))).scalar_one()
        tool = (await s.execute(select(ToolDB))).scalar_one()
        mcp = (await s.execute(select(MCPServerDB))).scalar_one()
        sched = (await s.execute(select(ScheduleDB))).scalar_one()
        settings = {r.key: json.loads(r.value)
                    for r in (await s.execute(select(SettingDB))).scalars()}

    assert orch.name == "Nightly report"
    assert orch.definition["steps"][0]["id"] == "s1"   # the whole definition, not a summary
    assert agent.definition["model"] == "gpt-4"
    assert tool.name == "lookup"
    assert mcp.definition["url"] == "https://mcp.example"
    assert settings == {"model": "claude-x", "vault_threshold": 5000}

    # Schedule state is promoted to columns the tick can query, and the
    # original created_at survives — restamping it with the migration time
    # would lose the ordering the JSON file kept by position.
    assert sched.enabled is True
    assert sched.definition["interval_value"] == 5
    assert sched.next_run_at.replace(tzinfo=None).isoformat() == "2026-01-02T03:09:05"
    assert sched.created_at.replace(tzinfo=None).isoformat() == "2026-01-02T03:04:05"


async def test_imported_rows_land_on_the_single_tenant(data_dir):
    await import_data_dir(data_dir)
    async with session() as s:
        for model in (OrchestrationDB, AgentDB, ToolDB, MCPServerDB, ScheduleDB):
            row = (await s.execute(select(model))).scalar_one()
            assert row.tenant_id == DEFAULT_TENANT


async def test_orchestrations_are_active(data_dir):
    """NULL is_active is not true.

    The engine counts `WHERE is_active`, so an imported orchestration would
    exist, list fine, and be invisible on the screens that count it — the
    workspace reporting itself empty while holding the user's work.
    """
    await import_data_dir(data_dir)
    async with session() as s:
        assert (await s.execute(select(OrchestrationDB))).scalar_one().is_active is True


# ── running it at boot ───────────────────────────────────────────────────────

async def test_first_boot_imports_and_renames(data_dir):
    counts = await import_legacy_data_if_present(data_dir)

    assert counts is not None
    assert not data_dir.exists()
    assert (data_dir.parent / "data.migrated").is_dir()
    # The originals survive the move — nothing is deleted.
    assert (data_dir.parent / "data.migrated" / "orchestrations.json").is_file()


async def test_second_boot_does_nothing(data_dir):
    await import_legacy_data_if_present(data_dir)
    again = await import_legacy_data_if_present(data_dir)
    assert again is None


async def test_a_populated_store_is_never_overwritten(data_dir):
    """The guard that protects work done since the upgrade.

    If the rename failed on the first boot, or the folder was restored from a
    backup, a second import must not clobber what is already there.
    """
    async with session() as s:
        s.add(OrchestrationDB(id="orch_abc1234", tenant_id=DEFAULT_TENANT,
                              name="Edited since upgrade", definition={"v": 2}))
        await s.commit()

    assert await import_legacy_data_if_present(data_dir) is None
    assert data_dir.exists()          # left in place for a human to look at

    async with session() as s:
        row = (await s.execute(select(OrchestrationDB))).scalar_one()
    assert row.name == "Edited since upgrade"


async def test_nothing_happens_without_a_data_dir(tmp_path):
    assert await import_legacy_data_if_present(tmp_path / "absent") is None
    assert await import_legacy_data_if_present(tmp_path) is None   # exists, but empty


async def test_a_corrupt_file_does_not_stop_the_rest(data_dir):
    """A half-written JSON file must not cost the user everything else."""
    (data_dir / "user_agents.json").write_text("{not json", encoding="utf-8")

    counts = await import_data_dir(data_dir)

    assert counts["user_agents"] == 0
    assert counts["orchestrations"] == 1
    assert counts["mcp_servers"] == 1


async def test_settings_alone_do_not_count_as_a_populated_store(tmp_path):
    """A fresh install writes settings before it has any content.

    Treating that as "already populated" would skip the import and strand the
    user's workflows.
    """
    async with session() as s:
        s.add(SettingDB(tenant_id=DEFAULT_TENANT, key="model", value='"x"'))
        await s.commit()

    assert await store_is_empty() is True
