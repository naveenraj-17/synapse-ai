"""
Builder agent endpoint: POST /api/builder/chat

Drives the native `orch_native_builder` orchestration and translates its
engine events into the shape BuilderPanel.tsx expects. Also exposes a
`human_input_required` event so the builder's clarify loop can surface
questions to the user inline.
"""
import json
import asyncio
import uuid
import re

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.models_orchestration import Orchestration
from core.orchestration.engine import OrchestrationEngine
from core.native_builder import NATIVE_BUILDER_ORCH_ID

router = APIRouter()

_SKIP_STEP_TYPES = {"end", "human", "merge", "parallel", "loop"}


def _apply_selected_model(orch: Orchestration, model: str | None) -> None:
    if not model:
        return
    for step in orch.steps:
        if step.type not in _SKIP_STEP_TYPES:
            step.model = model


class BuilderChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    selected_agent_ids: list[str] = []
    can_create_agents: bool = False
    model: str | None = None
    current_orchestration_id: str | None = None


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for m in history:
        role = m.get("role", "user")
        content = m.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _resolve_current_orch_id(raw: str | None) -> str:
    """Only pass through IDs that actually exist — the UI may send temp draft IDs."""
    if not raw:
        return ""
    from core.routes.orchestrations import load_orchestrations
    saved = load_orchestrations()
    if any(o.get("id") == raw for o in saved):
        return raw
    return ""


class BuilderResumeRequest(BaseModel):
    run_id: str
    response: dict = {}
    model: str | None = None


async def _translate_engine_events(event_source, run_id: str):
    """Shared translator: engine events → BuilderPanel events."""
    orchestration_saved_emitted = False
    async for event in event_source:
        etype = event.get("type")

        if etype == "step_start":
            yield {"type": "thinking", "message": f"Running: {event.get('step_name', '')}"}

        elif etype == "thinking":
            yield {"type": "thinking", "message": event.get("message", "Thinking…")}

        elif etype == "tool_execution":
            yield {
                "type": "tool_call",
                "tool_name": event.get("tool_name"),
                "args": event.get("args", {}),
            }

        elif etype == "tool_result":
            tool_name = event.get("tool_name")
            preview = event.get("preview", "")
            yield {"type": "tool_result", "tool_name": tool_name, "result": preview}
            if tool_name in ("create_agent", "update_agent"):
                try:
                    parsed = json.loads(preview)
                    agent_obj = parsed.get("agent") if isinstance(parsed, dict) else None
                    agent_obj = agent_obj or (parsed if isinstance(parsed, dict) and "id" in parsed else None)
                    if agent_obj and "id" in agent_obj:
                        yield {"type": "agent_saved", "agent": agent_obj}
                except Exception:
                    pass
            elif tool_name in ("create_orchestration", "update_orchestration"):
                try:
                    from core.routes.orchestrations import load_orchestrations as _load_orchs
                    orch_id = None
                    try:
                        parsed = json.loads(preview)
                        orch_obj = parsed.get("orchestration") if isinstance(parsed, dict) else None
                        orch_id = orch_obj.get("id") if isinstance(orch_obj, dict) else None
                    except Exception:
                        pass
                    if not orch_id:
                        m = re.search(r'"id"\s*:\s*"(orch_[a-z0-9]+)"', preview)
                        if m:
                            orch_id = m.group(1)
                    if orch_id:
                        full_orch = next((o for o in _load_orchs() if o.get("id") == orch_id), None)
                        if full_orch:
                            yield {"type": "orchestration_saved", "orchestration": full_orch}
                            orchestration_saved_emitted = True
                except Exception:
                    pass

        elif etype == "human_input_required":
            yield {
                "type": "human_input_required",
                "run_id": run_id,
                "orch_step_id": event.get("orch_step_id"),
                "prompt": event.get("prompt"),
                "fields": event.get("fields", []),
            }

        elif etype == "orchestration_complete":
            final_state = event.get("final_state", {}) or {}
            final_orch = final_state.get("final_orch")
            orch_obj = None
            if isinstance(final_orch, dict):
                orch_obj = final_orch.get("orchestration") or (final_orch if "id" in final_orch else None)
            elif isinstance(final_orch, str) and final_orch.strip():
                try:
                    parsed = json.loads(final_orch)
                    orch_obj = parsed.get("orchestration") if isinstance(parsed, dict) else None
                    orch_obj = orch_obj or (parsed if isinstance(parsed, dict) and "id" in parsed else None)
                except Exception:
                    orch_obj = None
            if orch_obj and "id" in orch_obj:
                yield {"type": "orchestration_saved", "orchestration": orch_obj}
                orchestration_saved_emitted = True

        elif etype == "final":
            response = event.get("response", "")
            final_state = (event.get("data") or {}).get("shared_state", {}) or {}
            final_text = _summarize_final(response, final_state, orchestration_saved_emitted)
            yield {"type": "final", "response": final_text}

        elif etype in ("orchestration_error", "step_error"):
            yield {"type": "error", "message": event.get("error", "Unknown error")}


async def run_builder_stream(request: BuilderChatRequest, server_module):
    """Drive the native builder orchestration and emit BuilderPanel events.

    Event types yielded:
      thinking             — step_start / engine status messages
      tool_call            — tool about to execute (name + args)
      tool_result          — result of a tool call (name + result preview)
      orchestration_saved  — derived from final_state.final_orch at completion
      agent_saved          — derived from create_agent / update_agent tool_result
      human_input_required — analyst wants more info; frontend surfaces a reply box
      final                — final text response
      error                — unrecoverable error
    """
    from core.routes.orchestrations import load_orchestrations

    orchs = load_orchestrations()
    orch_data = next((o for o in orchs if o.get("id") == NATIVE_BUILDER_ORCH_ID), None)
    if not orch_data:
        yield {"type": "error", "message": f"Native builder orchestration '{NATIVE_BUILDER_ORCH_ID}' not found. Seed it first."}
        return

    orch = Orchestration.model_validate(orch_data)

    # Propagate the frontend-selected model to every step that runs an LLM.
    # `end`/`human` steps don't take a model; everything else (agent, evaluator,
    # tool, llm, transform-with-llm) reads step.model and falls back to settings.
    _apply_selected_model(orch, request.model)

    engine = OrchestrationEngine(orch, server_module)

    initial_state = {
        "user_message": request.message,
        "chat_history": _format_history(request.history),
        "selected_agent_ids": list(request.selected_agent_ids or []),
        "can_create_agents": bool(request.can_create_agents),
        "current_orchestration_id": _resolve_current_orch_id(request.current_orchestration_id),
        "requirements": "",
        "human_response": "",
        "plan": "",
        "final_orch": {},
    }

    run_id = f"builder_{uuid.uuid4().hex[:12]}"
    session_id = "builder"

    engine_stream = engine.run(
        initial_input=request.message,
        run_id=run_id,
        session_id=session_id,
        initial_state=initial_state,
    )
    async for out in _translate_engine_events(engine_stream, run_id):
        yield out


async def run_builder_resume_stream(
    run_id: str,
    human_response: dict,
    server_module,
    model: str | None = None,
):
    """Resume a paused builder run and translate events for BuilderPanel.

    Mirrors OrchestrationEngine.resume, but reapplies the frontend-selected
    model to the freshly-loaded orch so every step after the human-clarify
    resume uses the user's picked model (not just the first leg of the run).
    """
    from core.orchestration.state import SharedState as SS
    from core.orchestration.logger import OrchestrationLogger
    from core.routes.orchestrations import load_orchestrations

    async def _event_source():
        restored = SS.restore(run_id)
        run = restored.run

        orchestrations = load_orchestrations()
        orch_data = next((o for o in orchestrations if o["id"] == run.orchestration_id), None)
        if not orch_data:
            yield {"type": "orchestration_error", "error": f"Orchestration '{run.orchestration_id}' not found"}
            return

        orch = Orchestration.model_validate(orch_data)
        _apply_selected_model(orch, model)
        engine = OrchestrationEngine(orch, server_module)

        engine.logger = OrchestrationLogger(
            run_id=run_id,
            orchestration_id=run.orchestration_id,
            orchestration_name=orch.name,
            user_input=f"(resumed) human_response={human_response}",
            session_id=run.session_id,
        )

        current_step = engine.step_map.get(run.current_step_id)
        output_key = (current_step.output_key if current_step else None) or "human_response"
        run.shared_state[output_key] = human_response
        if output_key != "human_response":
            run.shared_state["human_response"] = human_response

        run.waiting_for_human = False
        run.status = "running"

        if current_step:
            next_id, _ = engine._resolve_next(current_step, run)
            run.current_step_id = next_id

        state = SS(run)
        async for event in engine._execute_loop(run, state):
            yield event

    async for out in _translate_engine_events(_event_source(), run_id):
        yield out


def _summarize_final(raw_response: str, final_state: dict, orch_saved: bool) -> str:
    """Turn the engine's raw final output into a user-facing builder reply."""
    # If we paused for a human clarification, surface the analyst's question.
    requirements = final_state.get("requirements")
    if requirements and not final_state.get("plan") and not final_state.get("final_orch"):
        return str(requirements)

    final_orch = final_state.get("final_orch")
    if orch_saved and isinstance(final_orch, dict):
        orch_obj = final_orch.get("orchestration") or final_orch
        name = orch_obj.get("name") or orch_obj.get("id") or "orchestration"
        step_count = len(orch_obj.get("steps", []))
        return f"✓ Orchestration **{name}** saved ({step_count} steps). You can open it from the orchestrations tab."

    return str(raw_response or "Done.")


async def run_builder_stream_compat(request, server_module):
    """SSE pass-through for the main chat endpoint (page.tsx uses this)."""
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

        elif etype == "human_input_required":
            # Main chat has no inline reply box — surface as a normal assistant message.
            yield f"data: {json.dumps({'type': 'response', 'content': event.get('prompt', ''), 'intent': 'chat', 'data': None, 'tool_name': None}, default=str)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        elif etype == "final":
            yield f"data: {json.dumps({'type': 'response', 'content': event['response'], 'intent': 'chat', 'data': None, 'tool_name': None}, default=str)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        elif etype == "error":
            yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"

        await asyncio.sleep(0)


@router.post("/api/builder/chat")
async def builder_chat(request: BuilderChatRequest, http_request: Request):
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


@router.post("/api/builder/resume")
async def builder_resume(request: BuilderResumeRequest, http_request: Request):
    """Resume a paused builder run after the user submits a clarification."""
    server_module = http_request.app.state.server_module

    async def event_generator():
        try:
            async for event in run_builder_resume_stream(request.run_id, request.response, server_module, model=request.model):
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
