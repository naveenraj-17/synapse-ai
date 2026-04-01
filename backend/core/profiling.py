"""
Performance profiling utilities for the Synapse backend.

- TimingMiddleware: always-on request latency tracking (adds X-Process-Time header)
- CPU profiling: on-demand pyinstrument profiler (requires SYNAPSE_PROFILING=true)
- Memory profiling: on-demand tracemalloc snapshots (requires SYNAPSE_PROFILING=true)
"""

import os
import time
import tracemalloc
import statistics
from collections import defaultdict, deque
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

PROFILING_ENABLED = os.getenv("SYNAPSE_PROFILING", "false").lower() == "true"

# Rolling buffer: endpoint (method + path) → last 1000 latencies in ms
_timing_stats: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

# CPU profiler state
_cpu_profiler = None
_cpu_profiling_active = False

# Memory profiler state
_memory_profiling_active = False


class TimingMiddleware(BaseHTTPMiddleware):
    """Records per-request latency and adds X-Process-Time header. Always active."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        key = f"{request.method} {request.url.path}"
        _timing_stats[key].append(elapsed_ms)
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
        return response


def get_stats() -> dict:
    """Return avg, p50, p95, p99, max, count per endpoint."""
    result = {}
    for endpoint, latencies in _timing_stats.items():
        if not latencies:
            continue
        sorted_vals = sorted(latencies)
        n = len(sorted_vals)
        result[endpoint] = {
            "count": n,
            "avg_ms": round(statistics.mean(sorted_vals), 2),
            "p50_ms": round(sorted_vals[int(n * 0.50)], 2),
            "p95_ms": round(sorted_vals[int(n * 0.95)], 2),
            "p99_ms": round(sorted_vals[min(int(n * 0.99), n - 1)], 2),
            "max_ms": round(sorted_vals[-1], 2),
        }
    return result


def reset_stats() -> None:
    """Clear all timing data."""
    _timing_stats.clear()


# ---------------------------------------------------------------------------
# CPU profiling (pyinstrument) — only when SYNAPSE_PROFILING=true
# ---------------------------------------------------------------------------

def start_cpu_profiling() -> dict:
    global _cpu_profiler, _cpu_profiling_active
    if not PROFILING_ENABLED:
        return {"error": "Set SYNAPSE_PROFILING=true to enable CPU profiling"}
    if _cpu_profiling_active:
        return {"status": "already_running"}
    try:
        from pyinstrument import Profiler
        _cpu_profiler = Profiler()
        _cpu_profiler.start()
        _cpu_profiling_active = True
        return {"status": "started"}
    except ImportError:
        return {"error": "pyinstrument not installed — run: pip install pyinstrument"}


def stop_cpu_profiling(output_format: str = "text") -> dict:
    global _cpu_profiler, _cpu_profiling_active
    if not PROFILING_ENABLED:
        return {"error": "Set SYNAPSE_PROFILING=true to enable CPU profiling"}
    if not _cpu_profiling_active or _cpu_profiler is None:
        return {"error": "CPU profiling not started"}
    _cpu_profiler.stop()
    _cpu_profiling_active = False
    if output_format == "html":
        report = _cpu_profiler.output_html()
        _cpu_profiler = None
        return {"format": "html", "report": report}
    else:
        report = _cpu_profiler.output_text(unicode=True, color=False)
        _cpu_profiler = None
        return {"format": "text", "report": report}


def is_cpu_profiling() -> bool:
    return _cpu_profiling_active


# ---------------------------------------------------------------------------
# Memory profiling (tracemalloc) — only when SYNAPSE_PROFILING=true
# ---------------------------------------------------------------------------

def start_memory_profiling() -> dict:
    global _memory_profiling_active
    if not PROFILING_ENABLED:
        return {"error": "Set SYNAPSE_PROFILING=true to enable memory profiling"}
    if _memory_profiling_active:
        return {"status": "already_running"}
    tracemalloc.start()
    _memory_profiling_active = True
    return {"status": "started"}


def get_memory_snapshot(limit: int = 20) -> dict:
    if not PROFILING_ENABLED:
        return {"error": "Set SYNAPSE_PROFILING=true to enable memory profiling"}
    if not _memory_profiling_active:
        return {"error": "Memory profiling not started"}
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")
    allocations = []
    for stat in top_stats[:limit]:
        frame = stat.traceback[0]
        allocations.append({
            "file": frame.filename,
            "line": frame.lineno,
            "size_kb": round(stat.size / 1024, 2),
            "count": stat.count,
        })
    current, peak = tracemalloc.get_traced_memory()
    return {
        "current_mb": round(current / 1024 / 1024, 2),
        "peak_mb": round(peak / 1024 / 1024, 2),
        "top_allocations": allocations,
    }


def stop_memory_profiling() -> dict:
    global _memory_profiling_active
    if not _memory_profiling_active:
        return {"status": "not_running"}
    tracemalloc.stop()
    _memory_profiling_active = False
    return {"status": "stopped"}


def is_memory_profiling() -> bool:
    return _memory_profiling_active
