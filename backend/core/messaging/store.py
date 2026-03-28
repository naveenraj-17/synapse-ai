"""
JSON-backed persistent store for messaging channel configurations.
Saved to DATA_DIR/messaging_channels.json.
"""
import json
import os
import time
import uuid
from typing import Optional

from core.config import DATA_DIR

CHANNELS_FILE = os.path.join(DATA_DIR, "messaging_channels.json")


def _load_raw() -> list[dict]:
    if not os.path.exists(CHANNELS_FILE):
        return []
    try:
        with open(CHANNELS_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_raw(data: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CHANNELS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def list_channels() -> list[dict]:
    """Return all channel configs."""
    return _load_raw()


def get_channel(channel_id: str) -> Optional[dict]:
    """Return one channel by id, or None."""
    return next((c for c in _load_raw() if c["id"] == channel_id), None)


def get_channels_for_agent(agent_id: str) -> list[dict]:
    """Return all channels bound to a specific agent."""
    return [c for c in _load_raw() if c.get("agent_id") == agent_id]


def save_channel(channel: dict) -> dict:
    """Create or update a channel. Auto-assigns id and timestamps."""
    data = _load_raw()
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

    _save_raw(data)
    return channel


def update_channel_status(channel_id: str, status: str, last_error: Optional[str] = None) -> None:
    """Update only the runtime status fields (called by manager)."""
    data = _load_raw()
    for c in data:
        if c["id"] == channel_id:
            c["status"] = status
            c["last_error"] = last_error
            break
    _save_raw(data)


def delete_channel(channel_id: str) -> bool:
    """Delete a channel by id. Returns True if found and removed."""
    data = _load_raw()
    new_data = [c for c in data if c["id"] != channel_id]
    if len(new_data) == len(data):
        return False
    _save_raw(new_data)
    return True
