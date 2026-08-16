"""
Chat sessions in the store.

One table shared by the standalone server and the scale worker. It replaces two
things at once: the per-session JSON files under `DATA_DIR/chat_sessions`, and
the worker shim that copied history *out* of the database onto the winning
worker's local disk so that `core/session.py` could find it there.

Keyed `(tenant_id, session_id, agent_id)`. See `ChatSessionDB` for why the
agent belongs in the key rather than beside it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from core.tenancy import get_tenant


def _iso(dt: datetime | None) -> str | None:
    """The millisecond stamp `last_updated` has always been."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _to_dict(row) -> dict:
    return {
        "session_id": row.session_id,
        "agent_id": row.agent_id,
        "status": row.status,
        "messages": list(row.messages or []),
        "cli_session_ids": dict(row.cli_session_ids or {}),
        "last_updated": _iso(row.last_message_at),
    }


async def _row(s, session_id: str, agent_id: str):
    from core.store.models import ChatSessionDB

    return (
        await s.execute(
            select(ChatSessionDB).where(
                ChatSessionDB.tenant_id == get_tenant(),
                ChatSessionDB.session_id == session_id,
                ChatSessionDB.agent_id == agent_id,
            )
        )
    ).scalar_one_or_none()


async def get(session_id: str, agent_id: str) -> dict | None:
    from core.store import session

    if not session_id:
        return None
    async with session() as s:
        row = await _row(s, session_id, agent_id)
        return _to_dict(row) if row is not None else None


async def load(agent_id: str | None = None) -> list[dict]:
    """Every session for this tenant, most recently updated first."""
    from core.store import session
    from core.store.models import ChatSessionDB

    stmt = select(ChatSessionDB).where(ChatSessionDB.tenant_id == get_tenant())
    if agent_id:
        stmt = stmt.where(ChatSessionDB.agent_id == agent_id)

    async with session() as s:
        rows = (
            await s.execute(
                stmt.order_by(
                    ChatSessionDB.last_message_at.desc().nullslast(),
                    ChatSessionDB.session_id,
                )
            )
        ).scalars().all()
    return [_to_dict(r) for r in rows]


async def append_turn(session_id: str, agent_id: str, messages: list[dict]) -> None:
    """Append messages to a session, creating it if this is the first turn."""
    from core.store import session
    from core.store.models import ChatSessionDB

    async with session() as s:
        row = await _row(s, session_id, agent_id)
        if row is None:
            s.add(ChatSessionDB(
                tenant_id=get_tenant(),
                session_id=session_id,
                agent_id=agent_id,
                messages=list(messages),
                cli_session_ids={},
                last_message_at=datetime.now(timezone.utc),
            ))
        else:
            # Reassigned rather than mutated in place: SQLAlchemy does not track
            # in-place changes to a JSON column, so `row.messages.append(...)`
            # would be a write that silently does nothing.
            row.messages = list(row.messages or []) + list(messages)
            row.last_message_at = datetime.now(timezone.utc)


async def set_cli_session_id(session_id: str, agent_id: str, provider_key: str, cli_id: str) -> None:
    from core.store import session
    from core.store.models import ChatSessionDB

    async with session() as s:
        row = await _row(s, session_id, agent_id)
        if row is None:
            s.add(ChatSessionDB(
                tenant_id=get_tenant(),
                session_id=session_id,
                agent_id=agent_id,
                messages=[],
                cli_session_ids={provider_key: cli_id},
            ))
        else:
            row.cli_session_ids = {**(row.cli_session_ids or {}), provider_key: cli_id}


async def delete_one(session_id: str, agent_id: str) -> bool:
    from core.store import session
    from core.store.models import ChatSessionDB

    if not session_id:
        return False
    async with session() as s:
        result = await s.execute(
            delete(ChatSessionDB).where(
                ChatSessionDB.tenant_id == get_tenant(),
                ChatSessionDB.session_id == session_id,
                ChatSessionDB.agent_id == agent_id,
            )
        )
    return bool(result.rowcount)


async def clear() -> int:
    """Delete every session for this tenant. Returns how many were removed."""
    from core.store import session
    from core.store.models import ChatSessionDB

    async with session() as s:
        count = (
            await s.execute(
                select(func.count())
                .select_from(ChatSessionDB)
                .where(ChatSessionDB.tenant_id == get_tenant())
            )
        ).scalar() or 0
        await s.execute(
            delete(ChatSessionDB).where(ChatSessionDB.tenant_id == get_tenant())
        )
    return int(count)
