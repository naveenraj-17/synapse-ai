"""
Chat endpoints: /chat and /chat/stream
Thin wrappers around the shared ReAct engine (core.react_engine).
"""
import json
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.models import ChatRequest, ChatResponse
from core.react_engine import run_react_loop, parse_tool_call  # noqa: F401 — re-export for backwards compat

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    import core.server as _server
    if not _server.agent_sessions:
        raise HTTPException(status_code=500, detail="No agents connected")

    final_event = None
    async for event in run_react_loop(request, _server):
        if event["type"] == "final":
            final_event = event
        elif event["type"] == "error":
            raise HTTPException(status_code=500, detail=event["message"])

    if not final_event:
        return ChatResponse(response="I completed the requested actions.", intent="chat", data=None, tool_name=None)

    return ChatResponse(
        response=final_event["response"],
        intent=final_event["intent"],
        data=final_event.get("data"),
        tool_name=final_event.get("tool_name"),
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Real-time streaming endpoint with SSE"""

    async def event_generator():
        import core.server as _server
        try:
            async for event in run_react_loop(request, _server):
                etype = event["type"]

                if etype == "status":
                    yield f"data: {json.dumps({'type': 'status', 'message': event['message']})}\n\n"

                elif etype == "thinking":
                    yield f"data: {json.dumps({'type': 'thinking', 'message': event['message']})}\n\n"

                elif etype == "tool_execution":
                    yield f"data: {json.dumps({'type': 'tool_execution', 'tool_name': event['tool_name'], 'args': event['args']})}\n\n"

                elif etype == "tool_result":
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': event['tool_name'], 'preview': event['preview']})}\n\n"

                elif etype == "final":
                    yield f"data: {json.dumps({'type': 'response', 'content': event['response'], 'intent': event['intent'], 'data': event.get('data'), 'tool_name': event.get('tool_name')})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"

                elif etype == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"

                # Forward orchestration events directly to the frontend
                elif etype in (
                    "orchestration_start", "orchestration_complete", "orchestration_error",
                    "step_start", "step_complete", "step_error",
                    "human_input_required", "loop_limit_reached",
                ):
                    yield f"data: {json.dumps(event, default=str)}\n\n"

                await asyncio.sleep(0)

        except Exception as e:
            print(f"ERROR in SSE stream: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
