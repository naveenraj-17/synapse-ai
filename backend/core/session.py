"""
Session and conversation state management.
Extracted from server.py for better readability.
"""
from typing import Any
from collections import deque

from core.models import ChatRequest


# Session-scoped short-term history/state. We intentionally do NOT persist these across reloads;
# the frontend should create a new session_id on page load.
conversation_histories: dict[str, deque] = {}
session_state: dict[str, dict[str, Any]] = {}


def _get_session_id(request: ChatRequest) -> str:
    return request.session_id or "default"

def _get_conversation_history(session_id: str, agent_id: str = None) -> deque:
    key = f"{agent_id}_{session_id}" if agent_id else session_id
    if key not in conversation_histories:
        conversation_histories[key] = deque(maxlen=10)
    return conversation_histories[key]

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


def get_recent_history_messages(session_id: str, agent_id: str = None):
    """Returns a list of message dicts for the chat API, scoped by agent."""
    messages = []
    for turn in _get_conversation_history(session_id, agent_id):
        messages.append({"role": "user", "content": turn['user']})
        # If tools were used, we should ideally represent them, but for now 
        # let's represent the final assistant response to keep context usage expected.
        # Future improvement: Store full turn history including tool_calls and tool_outputs.
        messages.append({"role": "assistant", "content": turn['assistant']})
    return messages
