"""
Vault: Automatically saves large tool outputs to files and provides tools to query them.
Also resolves @[path] vault file mentions in user messages before they reach the LLM.

When any tool returns more than VAULT_THRESHOLD characters, the output is saved to
the vault and the LLM receives only the file path + metadata. The LLM can then use
the Filesystem MCP tools (read_file, search_files) to access parts of the file
without flooding its context window.

The vault root comes from the blob store, which scopes it to the current tenant —
so two tenants running in one process cannot read each other's tool output, and
there is no DATA_DIR involved.

The vault hands *filesystem paths* to the LLM and to the Filesystem MCP server,
so it always needs a real directory. Whether that directory *is* the vault or a
working copy of one is `core/vault_backend.py`'s decision, taken from whether the
blob store can offer a path: a local install gets its folder, an object store
gets a materialised working copy under the scratch root, hydrated on demand.

That note used to read "the vault falls back to a local root ... a deliberate
design decision and not made here". The decision has now been made, because the
fallback was writing an object-store deployment's vault to the pod's own disk.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from core.vault_backend import get_vault

VAULT_THRESHOLD = 100000  # characters (fallback default)


def _vault_root() -> Path:
    """The current tenant's vault directory.

    A real directory either way, because the Filesystem MCP server and the
    sandbox mount need one. What differs is whether it *is* the vault or a
    working copy of it — see `core/vault_backend.py`. It used to fall back to a
    plain `LocalBlobStore()` when the store had no path, which meant a
    deployment on object storage wrote its vault to the pod's own disk and lost
    it when the pod went away.
    """
    return get_vault().root


def _vault_outputs_dir() -> Path:
    return _vault_root() / "tool_outputs"


def _make_vault_path(tool_name: str, ext: str) -> Path:
    """Generate a unique, safe vault file path."""
    vault_dir = _vault_outputs_dir()
    vault_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
    safe_name = re.sub(r"[^\w]", "_", tool_name)[:40]
    return vault_dir / f"{safe_name}_{timestamp}.{ext}"


def maybe_vault(tool_name: str, raw_output: str) -> str:
    """
    If raw_output exceeds the vault threshold (from settings), persist it to vault and return a
    compact JSON reference the LLM can act on with the vault read/search tools.
    Returns raw_output unchanged when under the threshold or vault is disabled.

    In scale mode with S3 configured, the file is also uploaded to S3 for durability
    and cross-worker access (the local path remains valid for the duration of the run).
    """
    from core.config import load_settings
    settings = load_settings()
    if not settings.get("vault_enabled", True):
        return raw_output
    threshold = settings.get("vault_threshold", VAULT_THRESHOLD)
    if len(raw_output) <= threshold:
        return raw_output

    # Decide extension: JSON gets pretty-validated, everything else is text.
    try:
        parsed = json.loads(raw_output)
        ext = "json"
        content = json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        ext = "txt"
        content = raw_output

    # One write, and the backend decides what durable means. On a plain install
    # that is the file. On object storage it is the object, and a failure to
    # store it raises rather than being swallowed — the reference below tells
    # the model the output is saved, and it has to be true.
    path = _make_vault_path(tool_name, ext)
    get_vault().write(path, content)

    total_lines = content.count("\n") + 1
    return json.dumps({
        "vault_file": str(path),
        "file_type": ext,
        "size_chars": len(raw_output),
        "total_lines": total_lines,
        "content_preview": content[:500],
        "message": (
            f"Output too large ({len(raw_output):,} chars, {total_lines:,} lines). Saved to vault at: {path}. "
            f"Instead: use read_file_by_lines with start_line/end_line to read a slice, "
            f"or grep to search for specific values."
        ),
    })


# ---------------------------------------------------------------------------
# Vault tool implementations — called directly by react_engine.py
# ---------------------------------------------------------------------------




def expand_vault_mentions(message: str) -> str:
    """
    Replace every @[relative/path] vault mention in the user message with the
    file's actual content, so the LLM receives the data inline.

    Example:
        "Log a job. Config: @[jobs-filepath.json]"
        →
        "Log a job. Config: @[jobs-filepath.json]\n<file content here>"
    """
    def _replace(match: re.Match) -> str:
        rel = match.group(1).strip()

        # Prevent path traversal
        try:
            resolved = (_vault_root() / rel).resolve()
            if not str(resolved).startswith(str(_vault_root().resolve())):
                return match.group(0)
        except Exception:
            return match.group(0)

        content: str | None = None

        # Materialise it if this replica does not have it. One question to the
        # backend, rather than asking `core.s3_storage` directly and treating a
        # second answer to "is this cloud" as authoritative.
        try:
            resolved = Path(get_vault().ensure_local(resolved))
        except Exception:
            pass

        if content is None:
            if not resolved.exists() or not resolved.is_file():
                return match.group(0)
            try:
                content = resolved.read_text(encoding="utf-8")
            except Exception:
                return match.group(0)

        return f"@[{rel}]\n```\n{content}\n```"

    return re.sub(r"@\[([^\]]+)\]", _replace, message)


def _safe_path(path: str) -> Path:
    """Return Path, rejecting obvious traversal attempts."""
    p = Path(path).resolve()
    return p


def _ensure_local_path(path: str) -> str:
    """Materialise a vault file this replica does not have yet.

    A no-op on a plain install, where the file is simply there. On object
    storage the backend pulls it into the working copy — **at its real path**,
    not into a mangled name under the system temp directory as this used to do.
    That matters: the path is handed to the model and to the Filesystem MCP
    server, and one that has been flattened to `tool_outputs_thing.json` in
    /tmp is not a path any of the vault's own guards will accept afterwards.
    """
    try:
        return str(get_vault().ensure_local(Path(path)))
    except Exception:
        return path


def tool_read_file_chunk(path: str, start_line: int, end_line: int) -> str:
    """Read lines [start_line, end_line] (1-indexed, inclusive) from any file."""
    try:
        path = _ensure_local_path(path)
        p = _safe_path(path)
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        lines = p.read_text(encoding="utf-8").splitlines()
        total = len(lines)
        s = max(1, start_line) - 1      # 0-indexed
        e = min(end_line, total)
        chunk = lines[s:e]
        return json.dumps({
            "path": path,
            "start_line": s + 1,
            "end_line": e,
            "total_lines": total,
            "content": "\n".join(chunk),
        })
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def tool_search_file(path: str, query: str, context_lines: int = 5) -> str:
    """Grep-like search: returns matching lines with ±context_lines of surrounding context."""
    try:
        path = _ensure_local_path(path)
        p = _safe_path(path)
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        lines = p.read_text(encoding="utf-8").splitlines()
        q = query.lower()
        results = []
        covered: set[int] = set()

        for i, line in enumerate(lines):
            if q not in line.lower():
                continue
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            if i in covered:
                continue
            covered.update(range(start, end))
            block = []
            for j in range(start, end):
                prefix = ">>>" if j == i else "   "
                block.append(f"{prefix} [L{j + 1}] {lines[j]}")
            results.append({
                "match_line": i + 1,
                "match": line,
                "context": "\n".join(block),
            })
            if len(results) >= 20:
                break

        return json.dumps({
            "path": path,
            "query": query,
            "matches_found": len(results),
            "results": results,
        })
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def tool_read_json_chunk(path: str, offset: int = 0, limit: int = 50) -> str:
    """
    Read a slice of a JSON vault file.
    - Array root  → returns items[offset : offset+limit]
    - Object root → returns keys[offset : offset+limit] with their values
    """
    try:
        path = _ensure_local_path(path)
        p = _safe_path(path)
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        data = json.loads(p.read_text(encoding="utf-8"))

        if isinstance(data, list):
            total = len(data)
            chunk = data[offset: offset + limit]
            return json.dumps({
                "path": path,
                "root_type": "array",
                "total_items": total,
                "offset": offset,
                "limit": limit,
                "returned": len(chunk),
                "data": chunk,
            }, default=str)

        if isinstance(data, dict):
            keys = list(data.keys())
            total = len(keys)
            chunk_keys = keys[offset: offset + limit]
            chunk = {k: data[k] for k in chunk_keys}
            return json.dumps({
                "path": path,
                "root_type": "object",
                "total_keys": total,
                "all_keys": keys,
                "offset": offset,
                "limit": limit,
                "returned": len(chunk_keys),
                "data": chunk,
            }, default=str)

        # Scalar / other
        return json.dumps({
            "path": path,
            "root_type": type(data).__name__,
            "data": data,
        }, default=str)

    except Exception as ex:
        return json.dumps({"error": str(ex)})


def tool_search_json(path: str, query: str) -> str:
    """
    Recursively search JSON values for query string.
    Returns up to 20 matching {json_path, value} pairs.
    """
    try:
        path = _ensure_local_path(path)
        p = _safe_path(path)
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        data = json.loads(p.read_text(encoding="utf-8"))
        q = query.lower()
        results: list[dict] = []

        def _recurse(obj, jpath: str):
            if len(results) >= 20:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _recurse(v, f"{jpath}.{k}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _recurse(item, f"{jpath}[{i}]")
            else:
                val_str = str(obj)
                if q in val_str.lower():
                    results.append({"json_path": jpath, "value": val_str[:500]})

        _recurse(data, "$")
        return json.dumps({
            "path": path,
            "query": query,
            "matches_found": len(results),
            "results": results,
        })
    except Exception as ex:
        return json.dumps({"error": str(ex)})
