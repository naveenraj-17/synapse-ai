"""
One set of live MCP sessions per tenant, bounded, with idle eviction.

The worker used to call ``WorkerServerModule.build()`` once in ``on_startup`` and
hand the result to every job. One set of MCP sessions, opened from whatever
configuration existed at boot, served every tenant the process ran — which was
correct while a process belonged to one org, and is the last shared-process
assumption in the engine.

The unit is the module, not the session, because ``tool_router`` and
``agent_sessions`` are already per-instance. What was missing is a keyed cache
with a bound and a teardown.

Why bounded
-----------
A fleet sized for a thousand mostly-idle orgs must not hold a thousand live
session sets. Entries are evicted least-recently-used past ``POOL_SIZE``, and on
idle past ``IDLE_TTL`` regardless of size. What a tenant actually costs here is
small — stdio MCP is force-disabled in scale mode, so a tenant's own servers are
remote SSE connections, and the only subprocess is the Filesystem server rooted
at its vault.

**An entry in use is never evicted.** ``max_jobs`` defaults to 10, so several
jobs hold modules concurrently; closing one mid-call would kill the MCP sessions
under a running step.

Why each entry owns a task
--------------------------
anyio requires a cancel scope to be exited by the task that entered it. The
sessions are opened inside an ``AsyncExitStack``, so whichever task ran the build
must be the one to close it. Eviction is triggered by whoever happens to acquire
next — a different task — so an entry keeps a supervisor task that builds,
signals ready, waits, and closes in its own context.

`core/server.py`'s ``_filesystem_mcp_manager`` is the same pattern and carries
the scar that produced it: closing an MCP stack from an HTTP handler propagated a
CancelledError into the lifespan and tore down *every* session in the process.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict

from core.tenancy import get_tenant

#: How many tenants' session sets may be live at once.
_DEFAULT_POOL_SIZE = 32

#: How long an unused entry is kept before its sessions are closed.
_DEFAULT_IDLE_TTL = 900.0


def _pool_size() -> int:
    try:
        return max(1, int(os.getenv("SYNAPSE_MCP_POOL_SIZE", "") or _DEFAULT_POOL_SIZE))
    except (TypeError, ValueError):
        return _DEFAULT_POOL_SIZE


def _idle_ttl() -> float:
    try:
        return float(os.getenv("SYNAPSE_MCP_IDLE_TTL", "") or _DEFAULT_IDLE_TTL)
    except (TypeError, ValueError):
        return _DEFAULT_IDLE_TTL


class _Entry:
    """One tenant's module, and the task that owns its lifetime."""

    __slots__ = ("tenant", "module", "refs", "idle_since", "task", "ready", "closing", "error")

    def __init__(self, tenant: str):
        self.tenant = tenant
        self.module = None
        self.refs = 0
        self.idle_since: float | None = None
        self.task: asyncio.Task | None = None
        self.ready = asyncio.Event()
        self.closing = asyncio.Event()
        self.error: BaseException | None = None


#: tenant -> entry, in least-recently-acquired order.
_entries: "OrderedDict[str, _Entry]" = OrderedDict()

#: Guards `_entries`. Held only across bookkeeping, never across a build.
_lock: asyncio.Lock | None = None

#: The process-wide native tool servers every tenant shares.
_shared = None


def _get_lock() -> asyncio.Lock:
    # Created lazily: a Lock binds to the running loop, and this module is
    # imported long before the worker's loop exists.
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def set_shared(shared) -> None:
    """Install the process-wide native session set, from worker startup."""
    global _shared
    _shared = shared


def get_shared():
    return _shared


async def _build(tenant: str):
    """Build one tenant's module, with the tenant established in this task."""
    from core import tenancy
    from core.scale.worker_server_module import WorkerServerModule

    if tenancy.is_multi_tenant() and tenancy.get_tenant() != tenant:
        with tenancy.tenant_scope(tenant):
            return await WorkerServerModule.build_for_tenant(_shared)
    return await WorkerServerModule.build_for_tenant(_shared)


async def _own(entry: _Entry) -> None:
    """Build, stay alive, then close — all in one task. See the module docstring."""
    try:
        entry.module = await _build(entry.tenant)
    except BaseException as exc:  # noqa: BLE001 — reported to the acquirer
        entry.error = exc
        entry.ready.set()
        return

    entry.ready.set()
    try:
        await entry.closing.wait()
    finally:
        module = entry.module
        entry.module = None
        if module is not None:
            await module.close()


async def acquire(tenant: str | None = None):
    """This tenant's server module, building it if the pool does not hold one.

    Every call must be paired with `release()`, or the entry is pinned forever
    and the pool stops being bounded.
    """
    tenant = tenant or get_tenant()
    lock = _get_lock()

    async with lock:
        entry = _entries.get(tenant)
        if entry is None:
            entry = _Entry(tenant)
            _entries[tenant] = entry
            entry.task = asyncio.create_task(
                _own(entry), name=f"mcp-pool[{tenant}]"
            )
        entry.refs += 1
        entry.idle_since = None
        _entries.move_to_end(tenant)

    await entry.ready.wait()

    if entry.error is not None:
        async with lock:
            entry.refs -= 1
            # A build that failed is not cached: the next job for this tenant
            # should try again rather than inherit a permanent failure, which is
            # what a transient MCP outage would otherwise become.
            if _entries.get(tenant) is entry:
                del _entries[tenant]
            entry.closing.set()
        raise entry.error

    await _reap()
    return entry.module


async def release(tenant: str | None = None) -> None:
    """Give back what `acquire()` handed out. Safe to call more than once."""
    tenant = tenant or get_tenant()
    async with _get_lock():
        entry = _entries.get(tenant)
        if entry is None:
            return
        entry.refs = max(0, entry.refs - 1)
        if entry.refs == 0:
            entry.idle_since = time.monotonic()


async def _reap() -> None:
    """Evict idle entries past the TTL, then the oldest unused past the bound."""
    now = time.monotonic()
    ttl = _idle_ttl()
    size = _pool_size()
    doomed: list[_Entry] = []

    async with _get_lock():
        for tenant, entry in list(_entries.items()):
            if entry.refs == 0 and entry.idle_since is not None and (now - entry.idle_since) > ttl:
                doomed.append(_entries.pop(tenant))

        while len(_entries) > size:
            for tenant, entry in _entries.items():
                if entry.refs == 0:
                    doomed.append(_entries.pop(tenant))
                    break
            else:
                # Every entry is in use. Over the bound and nothing to give up —
                # the alternative is closing MCP sessions under a running step.
                break

    for entry in doomed:
        _close(entry)


def _close(entry: _Entry) -> None:
    """Ask an entry's owner task to tear itself down. Does not wait."""
    entry.closing.set()
    if entry.task is not None:
        # Teardown latency belongs to the evicted tenant, not to the job that
        # happened to trigger the reap. Consume the result so a failure is not
        # reported as an un-retrieved task exception.
        entry.task.add_done_callback(lambda t: t.cancelled() or t.exception())


async def drain() -> None:
    """Close every entry and wait for it. From worker shutdown, and from tests."""
    async with _get_lock():
        entries = list(_entries.values())
        _entries.clear()

    for entry in entries:
        entry.closing.set()

    for entry in entries:
        if entry.task is not None:
            try:
                await entry.task
            except Exception:
                pass


def stats() -> dict:
    """What the pool is holding. For tests and for a future health endpoint."""
    return {
        "size": len(_entries),
        "limit": _pool_size(),
        "idle_ttl": _idle_ttl(),
        "tenants": {
            tenant: {"refs": entry.refs, "idle": entry.idle_since is not None}
            for tenant, entry in _entries.items()
        },
    }


def reset_state() -> None:
    """Forget everything without closing anything. For tests only."""
    global _shared, _lock
    _entries.clear()
    _shared = None
    _lock = None
