"""
Reaching the engine's store from the CLI.

The CLI runs before, and independently of, the backend process — `synapse
setup` configures an install that has never started, and `synapse api-keys`
manages keys while it is stopped. Both need the database the engine reads,
which lives in `backend/core/store/`.

There is no event loop here, so each helper opens one for the duration of a
single call. That is safe precisely because the CLI is short-lived and single
threaded: the engine's warning about binding an async engine to a loop that
later dies applies to a long-running process serving requests, not to a command
that exits immediately afterwards.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent / "backend"


def prepare() -> None:
    """Make `core.*` importable. Call before importing any engine module."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


_prepare = prepare   # internal alias, kept so the helpers below read clearly


def run(coro_factory):
    """Run one store coroutine.

    `get_store()` creates the schema on first use, so simply touching the store
    is what brings a fresh install's database into existence.
    """
    _prepare()

    async def _inner():
        from core.store import get_store

        await get_store()
        return await coro_factory()

    return asyncio.run(_inner())


def load_settings() -> dict:
    """The install's settings, overlaid on the shipped defaults."""
    _prepare()
    from core.config import default_settings

    async def _load():
        from core.store.settings import load_settings_for_tenant
        return await load_settings_for_tenant()

    try:
        return {**default_settings(), **run(_load)}
    except Exception as e:
        print(f"Note: could not read settings from the database ({e}).")
        return default_settings()


def save_settings(values: dict) -> None:
    """Write settings rows."""
    async def _save():
        from core.store.settings import save_many
        await save_many(values)

    run(_save)


def is_configured() -> bool:
    """Whether this install has been set up.

    Replaces the old "does settings.json exist" test, which is what `synapse
    start` used to decide whether to run the wizard.
    """
    _prepare()
    try:
        return bool(run(_settings_present))
    except Exception:
        return False


async def _settings_present() -> bool:
    from sqlalchemy import func, select

    from core.store import session
    from core.store.models import SettingDB

    async with session() as s:
        count = (await s.execute(select(func.count()).select_from(SettingDB))).scalar() or 0
    return count > 0
