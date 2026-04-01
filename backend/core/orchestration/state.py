"""
Shared state management and JSON checkpointing for orchestration runs.
"""
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
            with os.fdopen(fd, "w") as f:
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
        data = json.loads(path.read_text())
        run = OrchestrationRun.model_validate(data)
        return cls(run)

    @classmethod
    def list_runs(cls, limit: int = 20) -> list[dict]:
        """List recent run checkpoints."""
        _ensure_runs_dir()
        runs = []
        for f in sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                data = json.loads(f.read_text())
                runs.append({
                    "run_id": data.get("run_id"),
                    "orchestration_id": data.get("orchestration_id"),
                    "status": data.get("status"),
                    "started_at": data.get("started_at"),
                    "ended_at": data.get("ended_at"),
                })
            except Exception:
                continue
        return runs
