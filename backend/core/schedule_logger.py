"""
Plain-text debug logging for individual schedule runs.
Mirrors the design of agent_logger.py exactly.
"""
import asyncio
import json
import os
import re
import time
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs" / "schedule_logs"


def _ensure_logs_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _fmt_args(args) -> str:
    try:
        return json.dumps(args, indent=2, default=str)
    except Exception:
        return str(args)


class ScheduleLogger:
    """Appends debug lines to logs/schedule_logs/<run_id>.log for a single schedule execution."""

    def __init__(
        self,
        schedule_id: str,
        schedule_name: str,
        target_type: str,
        target_id: str,
        prompt: str,
    ):
        _ensure_logs_dir()

        # Sanitize schedule_id to prevent taint in self.path
        clean_sched_id = re.sub(r"[^a-zA-Z0-9_\-]", "", schedule_id)
        short_id = clean_sched_id.replace("sched_", "") if clean_sched_id.startswith("sched_") else clean_sched_id
        self.run_id = f"schedulerun_{short_id}_{int(time.time() * 1000)}"
        self.path = LOGS_DIR / f"{self.run_id}.log"
        self._start_time = time.time()

        prompt_preview = prompt[:300] + "..." if len(prompt) > 300 else prompt
        self._write(f"""
{'='*80}
  SCHEDULE RUN LOG
{'='*80}
  Run ID          : {self.run_id}
  Schedule ID     : {schedule_id}
  Schedule Name   : {schedule_name}
  Target Type     : {target_type}
  Target ID       : {target_id}
  Started at      : {_ts()}
  Prompt          : {prompt_preview}
{'='*80}
""")

    # -- Core write -----------------------------------------------------

    def _write(self, text: str):
        """Sync write -- only call from a thread (via _write_bg) or startup."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text)

    def _write_bg(self, text: str):
        """Fire-and-forget write that offloads to a thread so the event loop isn't blocked."""
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._write, text)
        except RuntimeError:
            self._write(text)

    # -- Run lifecycle ---------------------------------------------------

    def run_end(self, status: str):
        elapsed = round(time.time() - self._start_time, 2)
        self._write_bg(f"""
{'='*80}
  SCHEDULE RUN FINISHED
  Status   : {status}
  Ended at : {_ts()}
  Duration : {elapsed}s
{'='*80}
""")

    # -- Event logging ---------------------------------------------------

    def log_event(self, event: dict):
        """Process an SSE event and write relevant info to the log."""
        etype = event.get("type", "")

        if etype == "_log_prompt":
            prompt = event.get("prompt", "")
            self._write_bg(f"""
{'-'*80}
  INPUT PROMPT:
{self._indent(prompt)}
{'-'*80}
""")

        elif etype == "tool_execution":
            tool_name = event.get("tool_name", "")
            args = event.get("args", {})
            self._write_bg(f"""
  TOOL CALL: {tool_name}
     Arguments:
{self._indent(_fmt_args(args), 6)}
""")

        elif etype == "tool_result":
            tool_name = event.get("tool_name", "")
            preview = event.get("preview", "")
            self._write_bg(f"""
  TOOL RESULT: {tool_name}
     Preview: {preview[:500]}
""")

        elif etype in ("step_start", "step_complete", "orchestration_start", "orchestration_complete"):
            name = event.get("step_name") or event.get("orchestration_name") or etype
            self._write_bg(f"\n  [{etype.upper()}] {name}\n")

        elif etype == "final":
            response = event.get("response", "")
            self._write_bg(f"""
  AGENT RESPONSE:
{self._indent(response[:3000])}
""")

        elif etype == "error":
            self._write_bg(f"\n  ERROR: {event.get('message', '')}\n")

        elif etype == "thinking":
            pass  # skip noise

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _indent(text: str, spaces: int = 4) -> str:
        prefix = " " * spaces
        return "\n".join(f"{prefix}{line}" for line in text.split("\n"))

    @staticmethod
    def _safe_log_path(run_id: str) -> Path | None:
        """
        Safely locates a log file by matching run_id against actual file system entries.
        This severs the taint chain for security scanners as the returned Path 
        originates from the OS (iterdir), not user input.
        """
        if not run_id or not isinstance(run_id, str):
            return None

        # 1. Strict regex validation as a first pass
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", run_id):
            return None

        # 2. Iterate and match (Taint-severing strategy)
        try:
            target_filename = f"{run_id}.log"
            for entry in LOGS_DIR.iterdir():
                if entry.is_file() and entry.name == target_filename:
                    return entry
        except Exception:
            pass
        return None

    # -- Query helpers (for API endpoints) -------------------------------

    @staticmethod
    def get_log(run_id: str) -> str | None:
        # Sanitize input immediately to satisfy scanner trace
        if not run_id or not re.match(r"^[a-zA-Z0-9_\-\.]+$", str(run_id)):
            return None

        path = ScheduleLogger._safe_log_path(run_id)
        if not path or not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def list_logs(limit: int = 100, offset: int = 0) -> list[dict]:
        _ensure_logs_dir()
        logs = []
        files = sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[offset: offset + limit]:
            run_id = f.stem
            try:
                head = f.read_text(encoding="utf-8", errors="replace")[:1000]

                def _extract(label: str) -> str:
                    for line in head.split("\n"):
                        if label in line:
                            return line.split(":", 1)[1].strip()
                    return ""

                logs.append({
                    "run_id": run_id,
                    "schedule_name": _extract("Schedule Name   :"),
                    "schedule_id": _extract("Schedule ID     :"),
                    "target_type": _extract("Target Type     :"),
                    "target_id": _extract("Target ID       :"),
                    "started_at": _extract("Started at      :"),
                    "prompt": _extract("Prompt          :")[:200],
                    "file_size_kb": round(f.stat().st_size / 1024, 1),
                })
            except Exception:
                logs.append({"run_id": run_id})
        return logs

    @staticmethod
    def delete_log(run_id: str) -> bool:
        # Sanitize input immediately to satisfy scanner trace
        if not run_id or not re.match(r"^[a-zA-Z0-9_\-\.]+$", str(run_id)):
            return False

        path = ScheduleLogger._safe_log_path(run_id)
        if path and path.exists():
            path.unlink()
            return True
        return False
