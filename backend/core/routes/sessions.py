"""
Session history REST API.

GET  /api/sessions                          → list all sessions (sorted by last_updated desc)
GET  /api/sessions?agent_id={id}            → filter by agent
GET  /api/sessions/{session_id}/history     → full turn list for a session
GET  /api/sessions/{session_id}/snapshot    → {last_response, last_updated}
DELETE /api/sessions/{session_id}           → delete session file
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.session import (
    list_chat_sessions,
    _get_conversation_history,
    get_last_response_snapshot,
    delete_chat_session,
)

router = APIRouter()


@router.get("/api/sessions")
async def get_sessions(agent_id: str | None = Query(default=None)):
    """List all persisted chat sessions, newest first."""
    return list_chat_sessions(agent_id=agent_id)


@router.get("/api/sessions/{session_id}/history")
async def get_session_history(session_id: str, agent_id: str | None = Query(default=None)):
    """Return the full list of turns for a session."""
    turns = _get_conversation_history(session_id, agent_id=agent_id)
    return {"session_id": session_id, "agent_id": agent_id, "turns": turns}


@router.get("/api/sessions/{session_id}/snapshot")
async def get_session_snapshot(session_id: str, agent_id: str | None = Query(default=None)):
    """Return just the last response and timestamp."""
    return get_last_response_snapshot(session_id, agent_id=agent_id)


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, agent_id: str | None = Query(default=None)):
    """Delete a session's persisted history file."""
    deleted = delete_chat_session(session_id, agent_id=agent_id)
    if deleted:
        return {"status": "deleted", "session_id": session_id}
    return JSONResponse(status_code=404, content={"detail": "Session not found"})
