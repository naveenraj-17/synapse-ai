"""
Additive schema migrations, run after ``create_all``.

``Base.metadata.create_all`` creates tables that do not exist and then stops.
It never inspects an existing table, so a column added to a model after someone
has already booted the build is invisible to them for good: no error, no
migration, just a query selecting a column the database does not have.

There is no Alembic in this repo, and adding one for a handful of columns would
put a migrations directory, a version table and an offline/online split in the
way of a single-file SQLite install. Instead this module runs idempotent
``ADD COLUMN`` statements at startup.

The scope is deliberately one statement type. ``ALTER TABLE ... ADD COLUMN`` is
the one form SQLite and Postgres spell identically and both apply cheaply. Any
change that renames, drops, retypes or backfills needs a real migration tool —
if this file ever wants one of those, that is the signal to bring in Alembic
rather than to widen this.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

#: (table, column, DDL type, backfill-from) — appended to, never edited. The
#: type is written in the portable spelling both dialects accept; `TIMESTAMP` is
#: what `DateTime(timezone=True)` renders to on SQLite and Postgres accepts it.
#:
#: `backfill_from` names an existing column to seed the new one from, for
#: columns that are sorted on. Added-but-empty would otherwise leave every
#: pre-existing row NULL, and the two dialects disagree about where NULLs sort
#: (SQLite first, Postgres last), so the ordering bug would simply change shape
#: instead of being fixed.
_ADDITIONS: tuple[tuple[str, str, str, str | None], ...] = (
    # Stable list ordering. `agents[0]` is the documented fallback for "the
    # user's default agent" in two places, and rows come back in whatever order
    # the database likes — so without a creation timestamp to sort on, a user's
    # default agent changes between restarts.
    ("agents", "created_at", "TIMESTAMP", "updated_at"),
    ("tools", "created_at", "TIMESTAMP", "updated_at"),
    ("mcp_servers", "created_at", "TIMESTAMP", "updated_at"),
)


async def run_migrations(engine: AsyncEngine) -> list[str]:
    """Apply any missing additive changes. Returns what was applied."""
    applied: list[str] = []

    async with engine.begin() as conn:
        existing = await conn.run_sync(_existing_columns)

        for table, column, ddl_type, backfill_from in _ADDITIONS:
            if table not in existing:
                # create_all just made it from the current model, so the column
                # is already there.
                continue
            if column in existing[table]:
                continue
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
            if backfill_from and backfill_from in existing[table]:
                await conn.execute(
                    text(
                        f"UPDATE {table} SET {column} = {backfill_from} "
                        f"WHERE {column} IS NULL"
                    )
                )
            applied.append(f"{table}.{column}")

    if applied:
        print(f"[store] added missing columns: {', '.join(applied)}", flush=True)
    return applied


def _existing_columns(sync_conn) -> dict[str, set[str]]:
    inspector = inspect(sync_conn)
    return {
        name: {c["name"] for c in inspector.get_columns(name)}
        for name in inspector.get_table_names()
    }
