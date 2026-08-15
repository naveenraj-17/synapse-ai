"""
Shared state and checkpointing for orchestration runs.

A run's `shared_state` and `step_history` *are* the run: resuming a paused one
means reading them back. Where they live therefore decides which process can
resume a run.

They used to live in `backend/logs/orchestration_runs/{run_id}.json`, on the
local disk of whichever process happened to be executing. That made every run
node-local:

  * a resume job dispatched by ARQ to a different worker than the one that
    paused hit FileNotFoundError, because the queue has no affinity;
  * `list_runs()` globbed a directory, so in a shared process every tenant saw
    every other tenant's runs;
  * `SharedStatePG` existed to fix this, was imported by
    `worker_engine_adapter.py`, and was never once instantiated — its module
    docstring claimed to be a drop-in replacement for a class the engine had no
    way to inject.

Now `SharedState` delegates to a `StateBackend`. The default keeps run state in
the store alongside everything else, so any worker can resume any run. An
embedder can supply its own.

Checkpointing is async because it is I/O on the event loop of a process running
other tenants' jobs; the old blocking `open()`/`write()` stalled all of them.
"""
from __future__ import annotations

from typing import Protocol

from core.models_orchestration import OrchestrationRun
from core.tenancy import get_tenant

# In-memory signal: run IDs cancelled by the cancel endpoint. The engine checks
# this at the start of each step and exits cleanly.
#
# Deliberately still process-local: it is a fast path for the single-process
# case. Distributed cancellation goes through Redis — see core/scale/pubsub.py
# `publish_cancellation` and the engine's `cancel_hook` — because a cancel
# arriving at one API server must reach a run executing on a different worker.
_cancelled_run_ids: set[str] = set()


class StateBackend(Protocol):
    """Where run state is durably kept."""

    async def save(self, run: OrchestrationRun) -> None: ...

    async def load(self, run_id: str) -> OrchestrationRun | None: ...

    async def list_runs(
        self, limit: int = 20, orchestration_ids: set[str] | None = None
    ) -> list[dict]: ...


_backend: StateBackend | None = None


def set_state_backend(backend: StateBackend | None) -> None:
    """Install a state backend. None restores the store-backed default."""
    global _backend
    _backend = backend


def get_state_backend() -> StateBackend:
    global _backend
    if _backend is None:
        from core.orchestration.state_store import StoreStateBackend
        _backend = StoreStateBackend()
    return _backend


class SharedState:
    """A run's mutable state, with durable checkpoints.

    `get`/`set`/`update` are in-memory and synchronous — they are called from
    tight loops in the step executors. `checkpoint()` is the durable write.
    """

    def __init__(self, run: OrchestrationRun):
        self.run = run

    def get(self, key: str, default=None):
        return self.run.shared_state.get(key, default)

    def set(self, key: str, value):
        self.run.shared_state[key] = value

    def update(self, data: dict):
        self.run.shared_state.update(data)

    async def checkpoint(self) -> None:
        """Persist the full run state.

        Async because this runs on an event loop shared with other tenants'
        jobs. The previous synchronous write blocked every one of them for the
        duration of a `json.dumps` plus a disk write, on every step boundary.
        """
        await get_state_backend().save(self.run)

    @classmethod
    async def restore(cls, run_id: str) -> "SharedState":
        """Load a checkpointed run.

        Raises FileNotFoundError when the run is unknown — kept as the
        exception type because callers already handle it, and because the
        meaning ("no checkpoint for this run") did not change when the storage
        did.
        """
        run = await get_state_backend().load(run_id)
        if run is None:
            raise FileNotFoundError(f"No checkpoint found for run {run_id}")
        return cls(run)

    @classmethod
    async def list_runs(
        cls, limit: int = 20, orchestration_ids: set[str] | None = None
    ) -> list[dict]:
        """Recent runs for the current tenant, newest first.

        `orchestration_ids`, when given, restricts results to runs whose
        orchestration still exists. The limit applies *after* filtering — a
        backlog of runs from deleted orchestrations must not crowd live runs
        out of the window.
        """
        return await get_state_backend().list_runs(
            limit=limit, orchestration_ids=orchestration_ids
        )


def current_tenant() -> str:
    """Re-exported so state backends need not import core.tenancy directly."""
    return get_tenant()
