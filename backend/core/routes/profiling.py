"""
Profiling API routes.

Timing stats: always available (GET /api/profiling/stats).
CPU / memory endpoints: require SYNAPSE_PROFILING=true.
"""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from core.profiling import (
    PROFILING_ENABLED,
    get_stats,
    reset_stats,
    start_cpu_profiling,
    stop_cpu_profiling,
    is_cpu_profiling,
    start_memory_profiling,
    get_memory_snapshot,
    stop_memory_profiling,
    is_memory_profiling,
)

router = APIRouter(prefix="/api/profiling", tags=["profiling"])


@router.get("/stats")
def profiling_stats():
    """Request latency stats per endpoint (always available)."""
    return get_stats()


@router.delete("/stats")
def reset_profiling_stats():
    """Clear all timing data."""
    reset_stats()
    return {"status": "reset"}


@router.get("/status")
def profiling_status():
    return {
        "profiling_enabled": PROFILING_ENABLED,
        "cpu_profiling_active": is_cpu_profiling(),
        "memory_profiling_active": is_memory_profiling(),
    }


# ---------------------------------------------------------------------------
# CPU profiling
# ---------------------------------------------------------------------------

@router.post("/cpu/start")
def cpu_start():
    return start_cpu_profiling()


@router.get("/cpu/report")
def cpu_report(format: str = Query("text", pattern="^(text|html)$")):
    result = stop_cpu_profiling(output_format=format)
    if "error" in result:
        return result
    if format == "html":
        return HTMLResponse(content=result["report"])
    return PlainTextResponse(content=result["report"])


# ---------------------------------------------------------------------------
# Memory profiling
# ---------------------------------------------------------------------------

@router.post("/memory/start")
def memory_start():
    return start_memory_profiling()


@router.get("/memory/snapshot")
def memory_snapshot(limit: int = Query(20, ge=1, le=200)):
    return get_memory_snapshot(limit=limit)


@router.delete("/memory")
def memory_reset():
    return stop_memory_profiling()
