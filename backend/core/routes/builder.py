"""
Builder agent endpoint: POST /api/builder/chat

A meta-agent that lets users design and create agents/orchestrations
through natural-language conversation.  Streams SSE events exactly
like the regular chat endpoint so the frontend can use the same
SSE-handling code, and exposes an additional set of builder-specific
events (orchestration_saved, agent_saved) that the BuilderPanel uses.
"""
import json
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.builder_tools import (
    BUILDER_TOOL_SCHEMAS,
    BUILDER_SYSTEM_PROMPT,
    execute_builder_tool,
)
from core.react_engine import run_agent_step

router = APIRouter()

MAX_BUILDER_TURNS = 15


class BuilderChatRequest(BaseModel):
    message: str
    history: list[dict] = []          # [{role, content}, ...]
    selected_agent_ids: list[str] = []
    can_create_agents: bool = False
    model: str | None = None          # model override
    current_orchestration_id: str | None = None


# ─── Core streaming generator ─────────────────────────────────────────────────

async def run_builder_stream(request: BuilderChatRequest, server_module):
    """
    Thin wrapper around run_agent_step() that wires in builder-specific tools,
    translates events to the shape BuilderPanel.tsx expects, and emits
    orchestration_saved / agent_saved events after relevant tool calls.

    Event types emitted:
      thinking            — planning/status messages
      chunk               — streamed text tokens (simulated word-by-word)
      tool_call           — tool invocation about to happen
      tool_result         — result of the tool call  (field: result, not preview)
      orchestration_saved — an orchestration was created or updated
      agent_saved         — an agent was created or updated
      final               — the final text response
      error               — unrecoverable error
    """
    # ── System prompt context additions ───────────────────────────────────────
    extras = []
    if request.selected_agent_ids:
        extras.append(
            f"The user has pre-selected these agent IDs to include in the orchestration: "
            f"{', '.join(request.selected_agent_ids)}. "
            "Use them directly as step agent_ids when calling create_orchestration or update_orchestration. "
            "Do NOT call get_agent or list_agents first — just use these IDs as provided."
        )
    if request.can_create_agents:
        extras.append("The user has granted you permission to create new agents if needed.")
    else:
        extras.append(
            "The user has NOT granted permission to create new agents. "
            "Only use agents that already exist (call list_agents to see them). "
            "If no suitable agents exist, tell the user and ask them to enable 'Create new agents'."
        )
    if request.current_orchestration_id:
        # Only inject context if the orchestration actually exists in the DB.
        # The frontend may pass a temp unsaved draft ID — silently ignore those.
        from core.routes.orchestrations import load_orchestrations
        saved_orchs = load_orchestrations()
        if any(o.get('id') == request.current_orchestration_id for o in saved_orchs):
            extras.append(
                f"The user is currently viewing orchestration ID: {request.current_orchestration_id}. "
                "ONLY call update_orchestration with this ID if the user EXPLICITLY says they want to "
                "edit, modify, update, or change this specific orchestration. "
                "For any new workflow request or new goal, ALWAYS call create_orchestration — "
                "never assume a new message is a request to update the current one."
            )
        # else: temp/unsaved ID — treat as a brand-new session, add no context
    else:
        extras.append(
            "No orchestration is currently loaded. For any workflow request, use create_orchestration."
        )
    sys_extra = "\n\n".join(extras) or None

    # ── Virtual agent dict (no persistent storage needed) ─────────────────────
    tool_names = [t["function"]["name"] for t in BUILDER_TOOL_SCHEMAS]
    virtual_agent = {
        "id": "builder",
        "type": "builder",
        "name": "AI Builder",
        "system_prompt": BUILDER_SYSTEM_PROMPT,
        "tools": tool_names,
        "model": request.model,
    }

    # ── Post-tool hook: emit orchestration_saved / agent_saved ────────────────
    # Receives the FULL raw_output (before preview truncation) so we can parse
    # the saved object out of the result.
    async def _post_hook(tool_name, raw_output):
        try:
            result_obj = json.loads(raw_output)
            if tool_name in ("create_orchestration", "update_orchestration"):
                orch = result_obj.get("orchestration") or result_obj
                if "id" in orch:
                    yield {"type": "orchestration_saved", "orchestration": orch}
            elif tool_name in ("create_agent", "update_agent"):
                agent_obj = result_obj.get("agent") or result_obj
                if "id" in agent_obj:
                    yield {"type": "agent_saved", "agent": agent_obj}
        except Exception:
            pass  # result was an error string — don't crash

    # ── Delegate to the shared ReAct loop, translate events for BuilderPanel ──
    #
    # run_agent_step emits:           BuilderPanel.tsx expects:
    #   tool_execution                  tool_call
    #   llm_thought                     chunk  (word-by-word streaming)
    #   tool_result {preview:}          tool_result {result:}
    #   final                           final  (same shape)
    #   thinking / error                thinking / error  (pass-through)
    #
    async for event in run_agent_step(
        message=request.message,
        agent_id=None,
        session_id="builder",
        server_module=server_module,
        max_turns=MAX_BUILDER_TURNS,
        source="builder",
        agent_override=virtual_agent,
        tools_override=BUILDER_TOOL_SCHEMAS,
        tool_executor=lambda n, a: execute_builder_tool(n, a, server_module),
        post_tool_hook=_post_hook,
        history_override=list(request.history),
        system_prompt_extra=sys_extra,
    ):
        etype = event["type"]

        if etype == "llm_thought":
            # Never stream LLM thoughts as chat chunks — they include raw tool-call JSON
            # (e.g. {"tool":"list_agents",...}) that would appear as garbage in the chat.
            # Tool-call thoughts are already reflected via tool_call / tool_result events.
            # The final prose response arrives via the "final" event below.
            # Just show the thinking indicator so the user knows work is happening.
            yield {"type": "thinking", "message": "Thinking…"}

        elif etype == "tool_execution":
            # BuilderPanel reads "tool_call", not "tool_execution"
            yield {"type": "tool_call", "tool_name": event["tool_name"], "args": event["args"]}

        elif etype == "tool_result":
            # BuilderPanel reads event.result; run_agent_step emits event.preview
            yield {"type": "tool_result", "tool_name": event["tool_name"], "result": event["preview"]}

        elif etype == "final":
            yield {"type": "final", "response": event["response"]}

        elif etype in ("thinking", "error", "orchestration_saved", "agent_saved"):
            yield event

        # skip: "status" — run_agent_step emits status+thinking; builder only needs thinking


# ─── Compat wrapper (used by chat.py for main-chat routing) ───────────────────

async def run_builder_stream_compat(request, server_module):
    """
    Wraps run_builder_stream and converts events to the standard
    data: {...}\\n\\n SSE format used by the main chat endpoint so
    the frontend page.tsx processMessageSSE() needs zero changes.

    Builder-specific events are translated:
      orchestration_saved → tool_result preview + woven into final response
      agent_saved         → tool_result preview
      tool_call           → tool_execution (same shape as react_engine)
      chunk               → chunk (passthrough)
    """
    # Build a minimal BuilderChatRequest from the ChatRequest
    builder_req = BuilderChatRequest(
        message=request.message,
        history=getattr(request, "history_messages", []) or [],
        can_create_agents=True,
        model=getattr(request, "model", None),
    )

    async for event in run_builder_stream(builder_req, server_module):
        etype = event["type"]

        if etype == "thinking":
            yield f"data: {json.dumps({'type': 'status', 'message': event['message']})}\n\n"

        elif etype == "chunk":
            yield f"data: {json.dumps({'type': 'chunk', 'content': event['content']})}\n\n"

        elif etype == "tool_call":
            yield f"data: {json.dumps({'type': 'tool_execution', 'tool_name': event['tool_name'], 'args': event['args']})}\n\n"

        elif etype == "tool_result":
            try:
                result_obj = json.loads(event["result"])
                preview = json.dumps(result_obj)[:200]
            except Exception:
                preview = str(event["result"])[:200]
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': event['tool_name'], 'preview': preview})}\n\n"

        elif etype == "orchestration_saved":
            orch = event["orchestration"]
            preview = f"✓ Orchestration '{orch.get('name', orch.get('id', ''))}' saved"
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': 'orchestration_saved', 'preview': preview})}\n\n"

        elif etype == "agent_saved":
            agent = event["agent"]
            preview = f"✓ Agent '{agent.get('name', agent.get('id', ''))}' saved"
            yield f"data: {json.dumps({'type': 'tool_result', 'tool_name': 'agent_saved', 'preview': preview})}\n\n"

        elif etype == "final":
            yield f"data: {json.dumps({'type': 'response', 'content': event['response'], 'intent': 'chat', 'data': None, 'tool_name': None}, default=str)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        elif etype == "error":
            yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"

        await asyncio.sleep(0)


# ─── FastAPI route ─────────────────────────────────────────────────────────────

@router.post("/api/builder/chat")
async def builder_chat(request: BuilderChatRequest, http_request: Request):
    """
    SSE endpoint for the AI Builder panel.

    Streams builder events as Server-Sent Events.  The BuilderPanel
    frontend component reads these directly; the main chat is routed
    here transparently via run_builder_stream_compat().
    """
    server_module = http_request.app.state.server_module

    async def event_generator():
        try:
            async for event in run_builder_stream(request, server_module):
                yield f"data: {json.dumps(event, default=str)}\n\n"
                await asyncio.sleep(0)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
