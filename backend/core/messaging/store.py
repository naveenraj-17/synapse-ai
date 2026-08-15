"""
JSON-backed persistent store for messaging channel configurations.
Saved to the `messaging_channels` collection in the store, per tenant.
"""
import json
import os
import time
import uuid
from typing import Optional


_COLLECTION = "messaging_channels"


async def _load_raw() -> list[dict]:
    from core.store import collections
    return await collections.load(_COLLECTION)


async def _save_raw(data: list[dict]) -> None:
    from core.store import collections
    await collections.save(_COLLECTION, data)


async def list_channels() -> list[dict]:
    """Return all channel configs."""
    return await _load_raw()


async def get_channel(channel_id: str) -> Optional[dict]:
    """Return one channel by id, or None."""
    return next((c for c in await _load_raw() if c["id"] == channel_id), None)


async def get_channels_for_agent(agent_id: str) -> list[dict]:
    """Return all channels bound to a specific agent."""
    return [c for c in await _load_raw() if c.get("agent_id") == agent_id]


async def save_channel(channel: dict) -> dict:
    """Create or update a channel. Auto-assigns id and timestamps."""
    data = await _load_raw()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if not channel.get("id"):
        channel["id"] = f"chn_{uuid.uuid4().hex[:8]}"
        channel["created_at"] = now

    channel["updated_at"] = now
    # Set defaults
    channel.setdefault("status", "stopped")
    channel.setdefault("last_error", None)
    channel.setdefault("enabled", True)
    channel.setdefault("multi_agent_mode", False)

    idx = next((i for i, c in enumerate(data) if c["id"] == channel["id"]), None)
    if idx is not None:
        # Preserve runtime-only fields from existing record
        existing = data[idx]
        channel["created_at"] = existing.get("created_at", now)
        data[idx] = channel
    else:
        data.append(channel)

    await _save_raw(data)
    return channel


async def update_channel_status(channel_id: str, status: str, last_error: Optional[str] = None) -> None:
    """Update only the runtime status fields (called by manager)."""
    data = await _load_raw()
    for c in data:
        if c["id"] == channel_id:
            c["status"] = status
            c["last_error"] = last_error
            break
    await _save_raw(data)


async def delete_channel(channel_id: str) -> bool:
    """Delete a channel by id. Returns True if found and removed."""
    data = await _load_raw()
    new_data = [c for c in data if c["id"] != channel_id]
    if len(new_data) == len(data):
        return False
    await _save_raw(new_data)
    return True
