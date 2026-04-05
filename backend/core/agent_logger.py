"""
Plain-text debug logging for individual agent runs.
Logs each call to an agent (from chat or orchestration) including all tools
used and their responses, in the same terminal-style format as orchestration logs.
"""
import asyncio
import json
import time
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs" / "agent_logs"


def _ensure_logs_dir():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _fmt_args(args) -> str:
    try:
        return json.dumps(args, indent=2, default=str)
    except Exception:
        return str(args)


class AgentLogger:
    """Appends debug lines to logs/agent_logs/<run_id>.log for a single agent execution."""

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        session_id: str,
        source: str,
        user_message: str,
    ):
        _ensure_logs_dir()
        # run_id encodes the agent and timestamp for easy identification
        short_id = agent_id.replace("agent_", "") if agent_id.startswith("agent_") else agent_id
        self.run_id = f"agentrun_{short_id}_{int(time.time() * 1000)}"
        self.path = LOGS_DIR / f"{self.run_id}.log"
        self._start_time = time.time()

        self._write(f"""
{'='*80}
  AGENT RUN LOG
{'='*80}
  Run ID          : {self.run_id}
  Agent ID        : {agent_id}
  Agent Name      : {agent_name}
  Session ID      : {session_id}
  Source          : {source}
  Started at      : {_ts()}
  User Input      : {user_message}
{'='*80}
""")

    # ── Core write ─────────────────────────────────────────────────

    def _write(self, text: str):
        """Sync write — only call from a thread (via _write_async) or startup."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(text)

    def _write_bg(self, text: str):
        """Fire-and-forget write that offloads to a thread so the event loop isn't blocked."""
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._write, text)
        except RuntimeError:
            # No running loop (e.g. called from sync context at startup)
            self._write(text)

    # ── Run lifecycle ──────────────────────────────────────────────

    def run_end(self, status: str):
        elapsed = round(time.time() - self._start_time, 2)
        self._write_bg(f"""
{'='*80}
  AGENT RUN FINISHED
  Status   : {status}
  Ended at : {_ts()}
  Duration : {elapsed}s
{'='*80}
""")

    # ── Event logging ──────────────────────────────────────────────

    def log_event(self, event: dict):
        """Process an SSE event and write relevant info to the log."""
        etype = event.get("type", "")

        if etype == "_log_prompt":
            prompt = event.get("prompt", "")
            self._write_bg(f"""
{'─'*80}
  📝 INPUT PROMPT:
{self._indent(prompt)}
{'─'*80}
""")

        elif etype == "tool_execution":
            tool_name = event.get("tool_name", "")
            args = event.get("args", {})
            self._write_bg(f"""
  🔧 TOOL CALL: {tool_name}
     Arguments:
{self._indent(_fmt_args(args), 6)}
""")

        elif etype == "tool_result":
            tool_name = event.get("tool_name", "")
            preview = event.get("preview", "")
            self._write_bg(f"""
  📤 TOOL RESULT: {tool_name}
     Preview: {preview}
""")

        elif etype == "llm_thought":
            thought = event.get("thought", "")
            turn = event.get("turn", "")
            self._write_bg(f"""
  🧠 LLM THOUGHT (turn {turn}):
{self._indent(thought)}
""")

        elif etype == "final":
            response = event.get("response", "")
            self._write_bg(f"""
  ✅ AGENT RESPONSE:
{self._indent(response)}
""")

        elif etype == "error":
            self._write_bg(f"\n  ❌ ERROR: {event.get('message', '')}\n")

        elif etype == "thinking":
            pass  # skip noise

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _indent(text: str, spaces: int = 4) -> str:
        prefix = " " * spaces
        return "\n".join(f"{prefix}{line}" for line in text.split("\n"))

    # ── Query helpers (for API endpoints) ──────────────────────────

    @staticmethod
    def get_log(run_id: str) -> str | None:
        path = LOGS_DIR / f"{run_id}.log"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def list_logs(limit: int = 100, offset: int = 0) -> list[dict]:
        _ensure_logs_dir()
        logs = []
        files = sorted(LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[offset : offset + limit]:
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
                    "agent_name": _extract("Agent Name      :"),
                    "agent_id": _extract("Agent ID        :"),
                    "source": _extract("Source          :"),
                    "session_id": _extract("Session ID      :"),
                    "started_at": _extract("Started at      :"),
                    "user_input": _extract("User Input      :")[:200],
                    "file_size_kb": round(f.stat().st_size / 1024, 1),
                })
            except Exception:
                logs.append({"run_id": run_id})
        return logs

    @staticmethod
    def delete_log(run_id: str) -> bool:
        path = LOGS_DIR / f"{run_id}.log"
        if path.exists():
            path.unlink()
            return True
        return False
