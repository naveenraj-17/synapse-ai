"""
The small document collections, tenant-scoped.

Repos, database configs, API keys, personal details and messaging channels were
five JSON files behind five `JsonStore` singletons, each bound to a path at
import time. None of them is queried by anything but its own key, so they share
one table rather than getting five schemas — see `CollectionDB`.

The API is deliberately list-shaped, because that is what every caller wants
and what the JSON files provided: `load(name)` returns the items in insertion
order, `save(name, items)` replaces them. The one difference from the files is
that a replace is a diff rather than a truncate-and-rewrite, so two writers do
not silently drop each other's rows for collections that grow.

Singletons — personal details is one document, not a list — use `load_one` /
`save_one`, which store it under an empty key.
"""
from __future__ import annotations

from sqlalchemy import delete, select

from core.tenancy import get_tenant


async def load(name: str) -> list[dict]:
    """Every item in `name`, oldest first."""
    from core.store import session
    from core.store.models import CollectionDB

    async with session() as s:
        rows = (
            await s.execute(
                select(CollectionDB)
                .where(
                    CollectionDB.tenant_id == get_tenant(),
                    CollectionDB.collection == name,
                )
                .order_by(CollectionDB.created_at, CollectionDB.key)
            )
        ).scalars().all()
    return [r.value for r in rows]


async def save(name: str, items: list[dict], key_field: str = "id") -> None:
    """Replace `name` with `items`, keyed by `key_field`.

    Items without the key field fall back to their position, which keeps
    list-shaped collections that never had ids working unchanged.
    """
    from core.store import session, upsert
    from core.store.models import CollectionDB

    tenant = get_tenant()
    keys: list[str] = []

    async with session() as s:
        for index, item in enumerate(items):
            key = str(item.get(key_field) or index) if isinstance(item, dict) else str(index)
            keys.append(key)
            await upsert(
                s,
                CollectionDB,
                values={
                    "tenant_id": tenant,
                    "collection": name,
                    "key": key,
                    "value": item,
                },
                index_elements=["tenant_id", "collection", "key"],
                update=["value"],
            )

        stmt = delete(CollectionDB).where(
            CollectionDB.tenant_id == tenant,
            CollectionDB.collection == name,
        )
        if keys:
            stmt = stmt.where(CollectionDB.key.notin_(keys))
        await s.execute(stmt)


async def load_one(name: str, default: dict | None = None) -> dict:
    """A singleton document, or `default` when nothing is stored."""
    from core.store import session
    from core.store.models import CollectionDB

    async with session() as s:
        row = (
            await s.execute(
                select(CollectionDB).where(
                    CollectionDB.tenant_id == get_tenant(),
                    CollectionDB.collection == name,
                    CollectionDB.key == "",
                )
            )
        ).scalar_one_or_none()
    if row is None:
        return dict(default or {})
    return row.value


async def save_one(name: str, document: dict) -> None:
    from core.store import session, upsert
    from core.store.models import CollectionDB

    async with session() as s:
        await upsert(
            s,
            CollectionDB,
            values={
                "tenant_id": get_tenant(),
                "collection": name,
                "key": "",
                "value": document,
            },
            index_elements=["tenant_id", "collection", "key"],
            update=["value"],
        )
