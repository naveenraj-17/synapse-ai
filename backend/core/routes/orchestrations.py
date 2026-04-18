"""
Orchestration management endpoints: CRUD, run, human-input, cancel.
"""
import asyncio
import os
import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.models_orchestration import Orchestration
from core.config import DATA_DIR
from core.json_store import JsonStore

router = APIRouter()

_orch_store = JsonStore(os.path.join(DATA_DIR, "orchestrations.json"), cache_ttl=2.0)

# In-memory registry of active run tasks (for mid-step cancellation)
_active_tasks: dict[str, asyncio.Task] = {}


def load_orchestrations() -> list[dict]:
    return _orch_store.load()


def save_orchestrations(data: list[dict]):
    _orch_store.save(data)


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("/api/orchestrations")
async def list_orchestrations():
    return load_orchestrations()


@router.get("/api/orchestrations/runs")
async def list_runs():
    """List recent orchestration runs."""
    from core.orchestration.state import SharedState
    return SharedState.list_runs()


@router.get("/api/orchestrations/{orch_id}")
async def get_orchestration(orch_id: str):
    orchs = load_orchestrations()
    orch = next((o for o in orchs if o["id"] == orch_id), None)
    if not orch:
        raise HTTPException(status_code=404, detail="Orchestration not found")
    return orch


@router.post("/api/orchestrations")
async def create_or_update_orchestration(orch: Orchestration):
    orchs = load_orchestrations()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for i, o in enumerate(orchs):
        if o["id"] == orch.id:
            data = orch.model_dump()
            data["updated_at"] = now
            data["created_at"] = o.get("created_at", now)
            orchs[i] = data
            save_orchestrations(orchs)
            return data

    data = orch.model_dump()
    data["created_at"] = now
    data["updated_at"] = now
    orchs.append(data)
    save_orchestrations(orchs)
    return data


@router.delete("/api/orchestrations/{orch_id}")
async def delete_orchestration(orch_id: str):
    orchs = load_orchestrations()
    orchs = [o for o in orchs if o["id"] != orch_id]
    save_orchestrations(orchs)
    return {"status": "success"}


# ── Execution ─────────────────────────────────────────────────────

@router.post("/api/orchestrations/{orch_id}/run")
async def run_orchestration(orch_id: str, request: Request):
    """Start an orchestration run. Returns SSE stream.

    The engine runs in a background task so that it continues executing
    (and logging) even if the SSE client disconnects or is slow to read.
    """
    orchs = load_orchestrations()
    orch_data = next((o for o in orchs if o["id"] == orch_id), None)
    if not orch_data:
        raise HTTPException(status_code=404, detail="Orchestration not found")

    body = await request.json()
    user_input = body.get("message", "")
    run_id = f"run_{orch_id}_{int(time.time() * 1000)}"

    orch = Orchestration.model_validate(orch_data)
    server_module = request.app.state.server_module

    from core.orchestration.engine import OrchestrationEngine
    engine = OrchestrationEngine(orch, server_module)

    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    async def _run_engine():
        try:
            async for event in engine.run(user_input, run_id):
                etype = event.get("type", "")
                if etype not in ("chunk", "thinking", "token_usage"):
                    print(f"DEBUG SSE QUEUE: → {etype} step={event.get('orch_step_id', '')}", flush=True)
                await queue.put(event)
                # Yield so event_stream() can dequeue and flush this event
                # to the HTTP response before the next event is enqueued.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            await queue.put({"type": "orchestration_error", "error": "Cancelled"})
        except Exception as e:
            await queue.put({"type": "orchestration_error", "error": str(e)})
        finally:
            _active_tasks.pop(run_id, None)
            print(f"DEBUG SSE QUEUE: sentinel sent, stream closing", flush=True)
            await queue.put(_SENTINEL)

    # Engine runs independently of SSE consumer; store task for cancellation
    task = asyncio.create_task(_run_engine())
    _active_tasks[run_id] = task

    async def event_stream():
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/orchestrations/runs/{run_id}")
async def get_run_status(run_id: str):
    """Get the current state of a run from its checkpoint."""
    from core.orchestration.state import SharedState
    try:
        restored = SharedState.restore(run_id)
        return restored.run.model_dump()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.post("/api/orchestrations/runs/{run_id}/resume")
async def resume_failed_run(run_id: str, request: Request):
    """Resume a failed or cancelled orchestration from where it stopped. Returns SSE stream."""
    server_module = request.app.state.server_module

    from core.orchestration.engine import OrchestrationEngine

    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    async def _run_engine():
        try:
            async for event in OrchestrationEngine.resume_failed(run_id, server_module):
                await queue.put(event)
                await asyncio.sleep(0)
        except FileNotFoundError:
            await queue.put({"type": "orchestration_error", "error": "Run not found"})
        except Exception as e:
            await queue.put({"type": "orchestration_error", "error": str(e)})
        finally:
            _active_tasks.pop(run_id, None)
            await queue.put(_SENTINEL)

    task = asyncio.create_task(_run_engine())
    _active_tasks[run_id] = task

    async def event_stream():
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/api/orchestrations/runs/{run_id}/human-input")
async def submit_human_input(run_id: str, request: Request):
    """Submit human input and resume the orchestration. Returns SSE stream.

    Also resolves any pending messaging-channel Future for this run
    (first-response-wins: if the messaging app already answered, this
    call is a no-op for the Future but still streams the resumed run).
    """
    body = await request.json()
    human_response = body.get("response", {})
    step_id = body.get("step_id", "")  # optional, sent by frontend

    server_module = request.app.state.server_module

    # Try to resolve messaging Future (first-wins).  If the Future was
    # already resolved by the messaging adapter, this is a no-op.
    messaging_manager = getattr(request.app.state, "messaging_manager", None)
    if messaging_manager and step_id:
        key = f"{run_id}:{step_id}"
        # Flatten response to string for messaging resolution
        response_text = ""
        if isinstance(human_response, dict):
            response_text = " ".join(str(v) for v in human_response.values())
        else:
            response_text = str(human_response)
        messaging_manager.resolve_human_input_by_key(key, response_text)

    from core.orchestration.engine import OrchestrationEngine

    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    async def _run_engine():
        try:
            async for event in OrchestrationEngine.resume(run_id, human_response, server_module):
                await queue.put(event)
                await asyncio.sleep(0)
        except FileNotFoundError:
            await queue.put({"type": "orchestration_error", "error": "Run not found"})
        except Exception as e:
            await queue.put({"type": "orchestration_error", "error": str(e)})
        finally:
            await queue.put(_SENTINEL)

    asyncio.create_task(_run_engine())

    async def event_stream():
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield f"data: {json.dumps(event, default=str)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/api/orchestrations/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Cancel a running orchestration."""
    from core.orchestration.state import SharedState, _cancelled_run_ids

    # Signal the engine loop to exit on its next iteration
    _cancelled_run_ids.add(run_id)

    # Cancel the asyncio task to interrupt any in-progress await (e.g. LLM call)
    task = _active_tasks.pop(run_id, None)
    if task and not task.done():
        task.cancel()

    # Persist cancelled status to disk
    try:
        restored = SharedState.restore(run_id)
        restored.run.status = "cancelled"
        restored.run.ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        restored.checkpoint()
    except FileNotFoundError:
        pass  # Run may not have checkpointed yet; that's fine

    return {"status": "cancelled", "run_id": run_id}


# ── Logs ───────────────────────────────────────────────────────

@router.get("/api/orchestrations/logs")
async def list_orchestration_logs(limit: int = 20):
    """List recent orchestration run logs (summary only)."""
    from core.orchestration.logger import OrchestrationLogger
    return OrchestrationLogger.list_logs(limit=limit)


@router.get("/api/orchestrations/logs/{run_id}")
async def get_orchestration_log(run_id: str):
    """Get full detailed log for a specific orchestration run (plain text)."""
    from core.orchestration.logger import OrchestrationLogger
    from fastapi.responses import PlainTextResponse
    log = OrchestrationLogger.get_log(run_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return PlainTextResponse(log)


@router.delete("/api/orchestrations/logs/{run_id}")
async def delete_orchestration_log(run_id: str):
    """Delete a specific orchestration log."""
    from core.orchestration.logger import OrchestrationLogger
    if OrchestrationLogger.delete_log(run_id):
        return {"status": "deleted", "run_id": run_id}
    raise HTTPException(status_code=404, detail="Log not found")


# ── Deploy ─────────────────────────────────────────────────────

@router.post("/api/orchestrations/{orch_id}/deploy")
async def deploy_as_agent(orch_id: str):
    """Create an orchestrator-type agent from this orchestration."""
    orchs = load_orchestrations()
    orch_data = next((o for o in orchs if o["id"] == orch_id), None)
    if not orch_data:
        raise HTTPException(status_code=404, detail="Orchestration not found")

    from core.routes.agents import load_user_agents, save_user_agents

    agents = load_user_agents()

    # Check if already deployed
    existing = next((a for a in agents if a.get("orchestration_id") == orch_id), None)
    if existing:
        return {"status": "already_deployed", "agent_id": existing["id"]}

    agent_id = f"orch_agent_{orch_id}"
    agent = {
        "id": agent_id,
        "name": orch_data["name"],
        "description": orch_data.get("description", ""),
        "avatar": orch_data.get("avatar", "default"),
        "type": "orchestrator",
        "tools": [],
        "repos": [],
        "system_prompt": f"This is an orchestrator agent for '{orch_data['name']}'. It runs automatically.",
        "orchestration_id": orch_id,
    }

    agents.append(agent)
    save_user_agents(agents)

    return {"status": "deployed", "agent_id": agent_id, "agent": agent}
