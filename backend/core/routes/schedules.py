"""
Schedules API: CRUD for schedule definitions and manual trigger.
"""
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from core.json_store import JsonStore
from core.models_schedule import ScheduleCreate, ScheduleUpdate
from core.scheduler import compute_next_run, _utc_now, _iso

router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SCHEDULES_FILE = str(_DATA_DIR / "schedules.json")
_store = JsonStore(_SCHEDULES_FILE, default_factory=list)


def _get_manager(request: Request):
    mgr = getattr(request.app.state, "schedule_manager", None)
    if mgr is None:
        raise HTTPException(status_code=503, detail="Schedule manager not available")
    return mgr


# -- List ----------------------------------------------------------------

@router.get("/api/schedules")
async def list_schedules():
    """Return all schedules."""
    return _store.load()


# -- Create --------------------------------------------------------------

@router.post("/api/schedules")
async def create_schedule(body: ScheduleCreate, request: Request):
    """Create a new schedule. Server computes next_run_at."""
    mgr = _get_manager(request)

    schedule = body.model_dump()
    schedule["id"] = f"sched_{uuid.uuid4().hex[:8]}"
    schedule["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    schedule["last_run_at"] = None

    now = _utc_now()
    next_dt = compute_next_run(schedule, now)
    schedule["next_run_at"] = _iso(next_dt)

    schedules = _store.load()
    schedules.append(schedule)
    _store.save(schedules)
    return schedule


# -- Get one -------------------------------------------------------------

@router.get("/api/schedules/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Return a single schedule."""
    schedules = _store.load()
    s = next((x for x in schedules if x["id"] == schedule_id), None)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return s


# -- Full update ----------------------------------------------------------

@router.put("/api/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleCreate, request: Request):
    """Full replacement update. Server recomputes next_run_at."""
    mgr = _get_manager(request)

    schedules = _store.load()
    idx = next((i for i, x in enumerate(schedules) if x["id"] == schedule_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    existing = schedules[idx]
    updated = body.model_dump()
    updated["id"] = schedule_id
    updated["created_at"] = existing.get("created_at", "")
    updated["last_run_at"] = existing.get("last_run_at")

    now = _utc_now()
    next_dt = compute_next_run(updated, now)
    updated["next_run_at"] = _iso(next_dt)

    schedules[idx] = updated
    _store.save(schedules)
    return updated


# -- Partial update (enable/disable, field patch) -------------------------

@router.patch("/api/schedules/{schedule_id}")
async def patch_schedule(schedule_id: str, body: ScheduleUpdate, request: Request):
    """Partial update. If re-enabling, recomputes next_run_at from now."""
    mgr = _get_manager(request)

    schedules = _store.load()
    idx = next((i for i, x in enumerate(schedules) if x["id"] == schedule_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    s = schedules[idx]
    patch = body.model_dump(exclude_none=True)

    was_disabled = not s.get("enabled", True)
    re_enabling = patch.get("enabled") is True and was_disabled

    # Apply patch fields
    for k, v in patch.items():
        s[k] = v

    # If the schedule is being re-enabled or schedule timing changed, recalculate next_run_at
    timing_keys = {"schedule_type", "interval_value", "interval_unit", "cron_expression"}
    if re_enabling or timing_keys.intersection(patch.keys()):
        now = _utc_now()
        next_dt = compute_next_run(s, now)
        s["next_run_at"] = _iso(next_dt)

    schedules[idx] = s
    _store.save(schedules)
    return s


# -- Delete ---------------------------------------------------------------

@router.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule."""
    schedules = _store.load()
    new_list = [x for x in schedules if x["id"] != schedule_id]
    if len(new_list) == len(schedules):
        raise HTTPException(status_code=404, detail="Schedule not found")
    _store.save(new_list)
    return {"status": "deleted", "id": schedule_id}


# -- Manual trigger --------------------------------------------------------

@router.post("/api/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: str, request: Request):
    """Manually trigger a schedule immediately (fire-and-forget). Returns a run_id."""
    mgr = _get_manager(request)

    # Verify schedule exists
    schedules = _store.load()
    s = next((x for x in schedules if x["id"] == schedule_id), None)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")

    run_id = await mgr.trigger_now(schedule_id)
    return {"status": "triggered", "schedule_id": schedule_id, "run_id": run_id}
