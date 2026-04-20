"""
Session and conversation state management.
Uses JSON file-backed storage for persistence across server restarts.
"""
import json
import os
from datetime import datetime
from typing import Any

from core.models import ChatRequest

# ---------------------------------------------------------------------------
# Session-scoped in-memory state (non-persistent by design)
# ---------------------------------------------------------------------------
session_state: dict[str, dict[str, Any]] = {}

# Directory where per-session JSON files are stored
_CHAT_SESSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "chat_sessions"
)


def _ensure_sessions_dir():
    os.makedirs(_CHAT_SESSIONS_DIR, exist_ok=True)


def _session_file_path(session_id: str, agent_id: str | None) -> str:
    _ensure_sessions_dir()
    safe_agent = (agent_id or "default").replace("/", "_").replace("\\", "_")
    safe_session = session_id.replace("/", "_").replace("\\", "_")
    return os.path.join(_CHAT_SESSIONS_DIR, f"{safe_agent}_{safe_session}.json")


def _load_session_file(session_id: str, agent_id: str | None) -> dict:
    """Load a session JSON file. Returns empty skeleton if not found."""
    path = _session_file_path(session_id, agent_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"DEBUG: Could not load session file {path}: {e}")
    return {
        "session_id": session_id,
        "agent_id": agent_id or "default",
        "turns": [],
        "last_response": None,
        "last_updated": None,
        "cli_session_ids": {},
    }


def _write_session_file(data: dict, session_id: str, agent_id: str | None):
    """Persist a session dict to disk."""
    path = _session_file_path(session_id, agent_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"DEBUG: Could not write session file {path}: {e}")


# ---------------------------------------------------------------------------
# Public API — used by react_engine and routes
# ---------------------------------------------------------------------------

def _get_session_id(request: ChatRequest) -> str:
    return request.session_id or "default"


def _get_conversation_history(session_id: str, agent_id: str | None = None) -> list[dict]:
    """Return the list of conversation turns for this session (from disk)."""
    data = _load_session_file(session_id, agent_id)
    return data.get("turns", [])


def _save_conversation_turn(
    session_id: str,
    agent_id: str | None,
    user: str,
    assistant: str,
    tools: list[str] | None = None,
):
    """Append a turn to the session JSON file and update last_response."""
    data = _load_session_file(session_id, agent_id)
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    turn = {
        "user": user,
        "assistant": assistant,
        "tools": tools or [],
        "timestamp": now,
    }
    data.setdefault("turns", []).append(turn)
    data["last_response"] = assistant
    data["last_updated"] = now
    data["session_id"] = session_id
    data["agent_id"] = agent_id or "default"
    _write_session_file(data, session_id, agent_id)


def get_cli_session_id(session_id: str, agent_id: str | None, provider_key: str) -> str | None:
    """Return the stored CLI session ID for the given provider, or None."""
    data = _load_session_file(session_id, agent_id)
    return data.get("cli_session_ids", {}).get(provider_key)


def save_cli_session_id(session_id: str, agent_id: str | None, provider_key: str, cli_id: str):
    """Persist a CLI session ID for this agent+session combination and provider."""
    data = _load_session_file(session_id, agent_id)
    data.setdefault("cli_session_ids", {})[provider_key] = cli_id
    _write_session_file(data, session_id, agent_id)


def get_last_response_snapshot(session_id: str, agent_id: str | None = None) -> dict:
    """Return {last_response, last_updated} for a session."""
    data = _load_session_file(session_id, agent_id)
    return {
        "last_response": data.get("last_response"),
        "last_updated": data.get("last_updated"),
    }


def get_recent_history_messages(session_id: str, agent_id: str | None = None) -> list[dict]:
    """Return last N turns as [role/content] message dicts for the LLM API."""
    RECENT_TURNS = 10
    turns = _get_conversation_history(session_id, agent_id)
    recent = turns[-RECENT_TURNS:] if len(turns) > RECENT_TURNS else turns
    messages = []
    for turn in recent:
        messages.append({"role": "user", "content": turn["user"]})
        messages.append({"role": "assistant", "content": turn["assistant"]})
    return messages


def list_chat_sessions(agent_id: str | None = None) -> list[dict]:
    """
    List all persisted chat sessions, sorted by last_updated descending.
    Optionally filter by agent_id.
    """
    _ensure_sessions_dir()
    sessions = []
    try:
        for fname in os.listdir(_CHAT_SESSIONS_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(_CHAT_SESSIONS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if agent_id and data.get("agent_id") != agent_id:
                    continue
                # Build a lightweight summary
                turns = data.get("turns", [])
                sessions.append({
                    "session_id": data.get("session_id"),
                    "agent_id": data.get("agent_id"),
                    "last_response": data.get("last_response"),
                    "last_updated": data.get("last_updated"),
                    "turn_count": len(turns),
                    "first_user_message": turns[0]["user"] if turns else None,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"DEBUG: Error listing sessions: {e}")

    # Sort most recent first
    sessions.sort(key=lambda s: s.get("last_updated") or "", reverse=True)
    return sessions


def delete_chat_session(session_id: str, agent_id: str | None = None) -> bool:
    """Delete a session file. Returns True if deleted."""
    path = _session_file_path(session_id, agent_id)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception as e:
            print(f"DEBUG: Could not delete session file {path}: {e}")
    return False


# ---------------------------------------------------------------------------
# Shared session state (in-memory, ephemeral)
# ---------------------------------------------------------------------------

def _get_session_state(session_id: str) -> dict[str, Any]:
    if session_id not in session_state:
        session_state[session_id] = {}
    return session_state[session_id]


def _apply_sticky_args(session_id: str, tool_name: str, tool_args: Any, tool_schema: dict | None = None) -> Any:
    """Normalize tool arguments. No session state tracking."""
    if not isinstance(tool_args, dict):
        tool_args = {}
    return tool_args


def _clear_session_embeddings(session_id: str):
    """Clear session-scoped embeddings (used internally by report auto-embed)."""
    from core.server import memory_store
    if memory_store:
        memory_store.clear_session_embeddings(session_id)
        print(f"DEBUG: Cleared session embeddings for {session_id}")
