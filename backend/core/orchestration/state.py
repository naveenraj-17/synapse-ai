"""
Shared state management and JSON checkpointing for orchestration runs.
"""
# Annotations are evaluated lazily: SharedState defines a `set` method, which
# would otherwise shadow the builtin in annotations like `set[str]`.
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from core.models_orchestration import OrchestrationRun

RUNS_DIR = Path(__file__).parent.parent.parent / "logs" / "orchestration_runs"

# In-memory signal: run IDs that have been cancelled by the cancel endpoint.
# The engine checks this at the start of each step and exits cleanly.
_cancelled_run_ids: set[str] = set()


def _ensure_runs_dir():
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


class SharedState:
    """Thread-safe shared state for an orchestration run with JSON checkpointing."""

    def __init__(self, run: OrchestrationRun):
        self.run = run

    def get(self, key: str, default=None):
        return self.run.shared_state.get(key, default)

    def set(self, key: str, value):
        self.run.shared_state[key] = value

    def update(self, data: dict):
        self.run.shared_state.update(data)

    def checkpoint(self):
        """Persist full run state to disk atomically."""
        _ensure_runs_dir()
        target = RUNS_DIR / f"{self.run.run_id}.json"
        # Atomic write: write to temp, then rename
        fd, tmp_path = tempfile.mkstemp(dir=RUNS_DIR, suffix=".tmp")
        try:
            # encoding="utf-8" is required: model_dump_json emits raw non-ASCII
            # characters, and without an explicit encoding os.fdopen uses the
            # platform default (cp1252 on Windows), which raises
            # UnicodeEncodeError when a run's state contains non-ASCII text.
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self.run.model_dump_json(indent=2))
            os.replace(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @classmethod
    def restore(cls, run_id: str) -> "SharedState":
        """Restore run state from a checkpoint file."""
        path = RUNS_DIR / f"{run_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"No checkpoint found for run {run_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        run = OrchestrationRun.model_validate(data)
        return cls(run)

    @classmethod
    def list_runs(cls, limit: int = 20, orchestration_ids: set[str] | None = None) -> list[dict]:
        """List recent run checkpoints, newest first.

        Skips runs that can never be opened in the UI: builder sessions
        (``builder_*``) and nested sub-orchestration runs (``{parent}__{step}_dN``),
        which are implementation details of a parent run.

        `orchestration_ids`, when given, restricts results to runs whose
        orchestration still exists. The limit is applied *after* filtering — a
        backlog of runs from deleted orchestrations must not crowd live runs
        out of the window.
        """
        _ensure_runs_dir()
        runs = []
        for f in sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(runs) >= limit:
                break
            # The filename is "{run_id}.json", so structural runs are skipped
            # without opening the file.
            if f.stem.startswith("builder_") or "__" in f.stem:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if orchestration_ids is not None and data.get("orchestration_id") not in orchestration_ids:
                    continue
                history = data.get("step_history") or []
                runs.append({
                    "run_id": data.get("run_id"),
                    "orchestration_id": data.get("orchestration_id"),
                    "status": data.get("status"),
                    "started_at": data.get("started_at"),
                    "ended_at": data.get("ended_at"),
                    # Trigger source: "schedule_<id>" (scheduler), a chat
                    # session id (orchestrator agent), or None (manual/API).
                    "session_id": data.get("session_id"),
                    # Live-progress fields for the runs table
                    "current_step_id": data.get("current_step_id"),
                    "steps_completed": len(history),
                    "last_step_name": (history[-1].get("step_name") if history else None),
                    "waiting_for_human": bool(data.get("waiting_for_human")),
                    "total_cost_usd": data.get("total_cost_usd"),
                })
            except Exception:
                continue
        return runs
