"""
Bash native tool — executes shell commands on the host system.

OS is detected at import time and injected into the tool description so the LLM
always knows what shell syntax to use. Execution is restricted to allowed
directories (linked repos + vault + user-configured bash_allowed_dirs).
"""

import asyncio
import json
import os
import platform
import subprocess
from pathlib import Path

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from core.config import DATA_DIR, load_settings

# ---------------------------------------------------------------------------
# OS detection
# ---------------------------------------------------------------------------

_SYSTEM = platform.system()  # "Linux" | "Darwin" | "Windows"
_IS_WSL = (
    "microsoft" in platform.version().lower()
    or "microsoft" in platform.release().lower()
)
_OS_LABEL = "WSL2 (Linux)" if _IS_WSL else _SYSTEM

# Shell command prefix — chosen once at startup
if _SYSTEM == "Windows" and not _IS_WSL:
    _SHELL_PREFIX = ["cmd", "/c"]
else:
    _SHELL_PREFIX = ["/bin/bash", "-c"]

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def _get_allowed_dirs() -> list[str]:
    """Return all directories the bash tool is allowed to run commands in.

    Always includes:
    - Paths of linked repos (from repos.json)
    - The vault directory
    - Any extra paths the user added via bash_allowed_dirs in settings
    """
    settings = load_settings()
    dirs: list[str] = []

    # 1. Linked repo paths
    repos_file = Path(DATA_DIR) / "repos.json"
    if repos_file.exists():
        try:
            repos = json.loads(repos_file.read_text())
            dirs += [
                r["path"]
                for r in repos
                if r.get("path") and os.path.isdir(r["path"])
            ]
        except Exception:
            pass

    # 2. Vault directory (always present)
    vault = Path(DATA_DIR) / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    dirs.append(str(vault))

    # 3. User-configured extra directories
    dirs += [
        d
        for d in settings.get("bash_allowed_dirs", [])
        if d and os.path.isdir(d)
    ]

    return dirs


def _is_allowed(path: str, allowed: list[str]) -> bool:
    """Check that `path` is inside (or equal to) one of the allowed dirs."""
    try:
        resolved = os.path.realpath(path)
    except Exception:
        return False
    for d in allowed:
        try:
            base = os.path.realpath(d)
        except Exception:
            continue
        if resolved == base or resolved.startswith(base + os.sep):
            return True
    return False


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

app = Server("bash-server")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    allowed = _get_allowed_dirs()
    dir_hint = ", ".join(allowed) if allowed else "(none configured yet)"
    return [
        types.Tool(
            name="run_bash",
            description=(
                f"Run a shell command on the host system (OS: {_OS_LABEL}). "
                f"The command executes in the specified working directory. "
                f"Always use shell syntax appropriate for {_OS_LABEL}. "
                f"Execution is restricted to allowed directories: {dir_hint}. "
                "You can pass a `cwd` to choose which directory to run in. "
                "If no `cwd` is given, the first available allowed directory is used."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "Working directory for the command. "
                            "Must be within one of the allowed directories."
                        ),
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default 30, max 120).",
                    },
                },
                "required": ["command"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "run_bash":
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    command: str = arguments.get("command", "").strip()
    cwd_arg: str | None = arguments.get("cwd")
    timeout: float = float(arguments.get("timeout") or 30)
    timeout = min(max(timeout, 1), 120)

    if not command:
        return [types.TextContent(type="text", text=json.dumps({"error": "No command provided."}))]

    allowed_dirs = _get_allowed_dirs()

    # Resolve working directory
    if cwd_arg:
        cwd = os.path.realpath(os.path.expanduser(cwd_arg))
        if not _is_allowed(cwd, allowed_dirs):
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": (
                            f"Directory '{cwd}' is not in the allowed list. "
                            "Add it via Settings → General → Bash Command Directories, "
                            "or use a linked repo/vault path."
                        ),
                        "allowed_dirs": allowed_dirs,
                    }),
                )
            ]
        if not os.path.isdir(cwd):
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Directory does not exist: {cwd}"}),
                )
            ]
    else:
        # Default to first available allowed dir
        cwd = allowed_dirs[0] if allowed_dirs else DATA_DIR

    # Build the shell invocation
    shell_cmd = _SHELL_PREFIX + [command]

    try:
        result = subprocess.run(
            shell_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "cwd": cwd,
            "os": _OS_LABEL,
            "allowed_dirs": allowed_dirs,
        }
    except subprocess.TimeoutExpired:
        output = {
            "error": f"Command timed out after {timeout}s.",
            "exit_code": -1,
            "cwd": cwd,
            "os": _OS_LABEL,
        }
    except PermissionError as e:
        output = {
            "error": f"Permission denied: {e}",
            "exit_code": -1,
            "cwd": cwd,
            "os": _OS_LABEL,
        }
    except Exception as e:
        output = {
            "error": str(e),
            "exit_code": -1,
            "cwd": cwd,
            "os": _OS_LABEL,
        }

    return [types.TextContent(type="text", text=json.dumps(output))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
