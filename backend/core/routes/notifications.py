"""
Notification endpoints: ring-buffer replay + live SSE tail.

"Seen" state lives client-side (localStorage) — the backend only stores and
streams; there is no mutation endpoint.
"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from core.notifications import hub

router = APIRouter()

# Seconds between keepalive comments while the stream is idle (patchable in tests).
_KEEPALIVE_SECONDS = 15


@router.get("/api/notifications")
async def list_notifications(after: int = 0):
    """Notifications with id > `after`, oldest first."""
    items = hub.list(after_id=after)
    return {"notifications": items, "last_id": items[-1]["id"] if items else after}


async def _stream_notifications(after_id: int):
    # Subscribe BEFORE replaying the ring so nothing falls between replay and
    # tail. The tail forwards every queued item unconditionally: an item with
    # an already-seen id is an UPDATE (e.g. human input resolved) — clients
    # upsert by id, which also makes replay-overlap duplicates harmless.
    queue = hub.subscribe()
    try:
        for item in hub.list(after_id=after_id):
            yield f"id: {item['id']}\ndata: {json.dumps(item, default=str)}\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield f"id: {item['id']}\ndata: {json.dumps(item, default=str)}\n\n"
    finally:
        hub.unsubscribe(queue)


@router.get("/api/notifications/stream")
async def stream_notifications(request: Request, after: int = 0):
    """SSE: replay notifications after `after` (or Last-Event-ID), then tail live."""
    last_event_id = request.headers.get("last-event-id")
    if last_event_id:
        try:
            after = int(last_event_id)
        except ValueError:
            pass
    return StreamingResponse(
        _stream_notifications(after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
