"""
Code search MCP agent: vector similarity search over indexed code repositories.
Uses Gemini embeddings + pgvector for semantic code search.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/synapse")


def _load_repo_paths() -> dict[str, str]:
    """Load repo_id → absolute_path mapping from repos.json (via core.config DATA_DIR)."""
    try:
        from core.config import DATA_DIR
        repos_file = os.path.join(DATA_DIR, "repos.json")
        with open(repos_file) as f:
            repos = json.load(f)
        return {r["id"]: r["path"].rstrip("/") for r in repos if r.get("id") and r.get("path")}
    except Exception:
        return {}


# Must match the indexing config in services/code_indexer.py
CODE_EMBEDDING_MODEL = "gemini-embedding-001"
CODE_EMBEDDING_DIM = 768

_pool: ConnectionPool | None = None
_VALID_REPO_ID = re.compile(r'^repo_\d+$')

app = Server("code-search-server")


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


def _get_query_embedding(query: str) -> list[float]:
    """Generate an embedding vector for the search query using Gemini."""
    from google import genai
    from google.genai import types as gtypes

    # load_settings returns a dict
    from core.config import load_settings
    settings = load_settings()
    api_key = settings.get("gemini_key", "")
    if not api_key:
        raise ValueError("Gemini API key not found in settings")

    client = genai.Client(api_key=api_key)
    result = client.models.embed_content(
        model=CODE_EMBEDDING_MODEL,
        contents=[query],
        config=gtypes.EmbedContentConfig(output_dimensionality=CODE_EMBEDDING_DIM)
    )
    return result.embeddings[0].values


def _get_table_name(repo_id: str) -> str:
    return f"ci_{repo_id}__emb"


def _search(query: str, repo_ids: list[str], top_k: int = 10) -> list[dict]:
    """Search indexed repos using cosine similarity."""
    try:
        pool = _get_pool()
    except Exception as e:
        return [{"error": f"Database connection failed: {e}"}]

    repo_path_map = _load_repo_paths()
    query_vector = _get_query_embedding(query)
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    all_results = []

    for repo_id in repo_ids:
        if not _VALID_REPO_ID.match(repo_id):
            continue

        with pool.connection() as conn:
            with conn.cursor() as cur:
                try:
                    table_name = _get_table_name(repo_id)
                    cur.execute(f"""
                        SELECT filename, code, location,
                               embedding <=> %s::vector AS distance
                        FROM "{table_name}"
                        ORDER BY distance
                        LIMIT %s
                    """, (vector_str, top_k))

                    repo_root = repo_path_map.get(repo_id, "")
                    for row in cur.fetchall():
                        # location may be a psycopg Range object — convert to string
                        loc = row[2]
                        if hasattr(loc, 'lower') and hasattr(loc, 'upper'):
                            loc = f"{loc.lower}-{loc.upper}"
                        else:
                            loc = str(loc) if loc is not None else ""
                        filename = row[0].lstrip("/")
                        full_path = f"{repo_root}/{filename}" if repo_root else filename
                        all_results.append({
                            "repo_id": repo_id,
                            "filename": filename,
                            "full_path": full_path,
                            "code": row[1],
                            "location": loc,
                            "score": round(1.0 - row[3], 5)
                        })
                except Exception as e:
                    sys.stderr.write(f"Error querying {table_name}: {e}\n")

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


def _grep_file(
    file_path: str,
    pattern: str,
    ignore_case: bool = False,
    fixed: bool = False,
    context: int = 0,
    max_matches: int = 1000,
) -> list[dict]:
    """Search for a pattern inside a single file (grep-like behavior).

    - `pattern` is treated as a regular expression unless `fixed` is True (literal match).
    - `ignore_case` enables case-insensitive matching.
    - `context` returns that many lines before/after each match.
    """
    resolved = file_path if os.path.isabs(file_path) else os.path.join(os.getcwd(), file_path)

    if not os.path.exists(resolved):
        return [{"error": f"File not found: {file_path}. Use an absolute path (e.g. as returned by list_directory or search_files)."}]
    if not os.path.isfile(resolved):
        return [{"error": f"Not a file: {file_path}. Use an absolute path to a file."}]

    # Detect binary files (simple heuristic)
    try:
        with open(resolved, "rb") as f:
            sample = f.read(1024)
            if b"\x00" in sample:
                return [{"error": f"Binary file: {file_path}"}]
    except Exception as e:
        return [{"error": str(e)}]

    flags = re.MULTILINE
    if ignore_case:
        flags |= re.IGNORECASE

    pat = re.escape(pattern) if fixed else pattern
    try:
        regex = re.compile(pat, flags)
    except re.error as e:
        return [{"error": f"Invalid regular expression: {e}"}]

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return [{"error": str(e)}]

    results: list[dict] = []
    for i, line in enumerate(lines):
        for m in regex.finditer(line):
            item: dict = {
                "filename": file_path,
                "line_number": i + 1,
                "line": line.rstrip("\n"),
                "match": m.group(0),
                "start": m.start(),
                "end": m.end(),
            }
            if context > 0:
                start_ctx = max(0, i - context)
                end_ctx = min(len(lines), i + context + 1)
                item["pre_context"] = [l.rstrip("\n") for l in lines[start_ctx:i]]
                item["post_context"] = [l.rstrip("\n") for l in lines[i+1:end_ctx]]

            results.append(item)
            if len(results) >= max_matches:
                return results

    return results


def _glob_files(
    folder_path: str,
    pattern: str = "**/*",
    recursive: bool = True,
    include_dirs: bool = False,
    include_hidden: bool = True,
    max_results: int = 1000,
) -> list[dict] | list[str]:
    """List files under `folder_path` matching `pattern` using Python glob rules.

    Returns relative paths from `folder_path`. Uses `glob` and supports `**` for recursion.
    """
    resolved = folder_path if os.path.isabs(folder_path) else os.path.join(os.getcwd(), folder_path)

    if not os.path.exists(resolved):
        return [{"error": f"Folder not found: {folder_path}. Use an absolute path (e.g. as returned by list_allowed_directories or list_directory)."}]
    if not os.path.isdir(resolved):
        return [{"error": f"Not a directory: {folder_path}. Use an absolute path to a folder."}]

    import glob as _glob

    search_pattern = os.path.join(resolved, pattern)
    iterator = _glob.iglob(search_pattern, recursive=recursive)

    results: list[str] = []
    for p in iterator:
        name = os.path.basename(p)
        if not include_hidden and name.startswith("."):
            continue
        if include_dirs or os.path.isfile(p):
            results.append(os.path.relpath(p, resolved))
            if len(results) >= max_results:
                break

    results.sort()
    return results


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_codebase",
            description=(
                "Search indexed code repositories for relevant code snippets using semantic vector search. "
                "Returns matching code with filename, location, and relevance score. "
                "You MUST provide repo_ids — check the LINKED CODE REPOSITORIES section in your system prompt for available repo IDs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language or code search query"
                    },
                    "repo_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of repo IDs to search"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 10)",
                        "default": 10
                    }
                },
                "required": ["query", "repo_ids"]
            },
        ),
        types.Tool(
            name="grep",
            description=(
                "Search inside a single file for a pattern (grep-like). Pattern is a regex by default; "
                "set `fixed` to true for literal matching. Returns matches with line numbers. "
                "IMPORTANT: `file_path` must be an absolute path (e.g. as returned by list_directory or search_files)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the file to search (must be absolute, not relative)"},
                    "pattern": {"type": "string", "description": "Regex or literal pattern to search for"},
                    "ignore_case": {"type": "boolean", "default": False},
                    "fixed": {"type": "boolean", "description": "Treat pattern as literal substring (like grep -F)", "default": False},
                    "context": {"type": "integer", "description": "Number of context lines before/after each match", "default": 0},
                    "max_matches": {"type": "integer", "default": 1000}
                },
                "required": ["file_path", "pattern"]
            },
        ),
        types.Tool(
            name="glob",
            description=(
                "List files under a folder matching a glob pattern. Returns paths relative to the provided folder. "
                "IMPORTANT: `folder_path` must be an absolute path (e.g. from list_allowed_directories or list_directory)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "Absolute path to the folder to search in (must be absolute, not relative)"},
                    "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')", "default": "**/*"},
                    "recursive": {"type": "boolean", "default": True},
                    "include_dirs": {"type": "boolean", "default": False},
                    "include_hidden": {"type": "boolean", "default": True},
                    "max_results": {"type": "integer", "default": 1000}
                },
                "required": ["folder_path"]
            },
        ),
    ]


@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent]:
    try:
        if name == "search_codebase":
            query = arguments.get("query", "")
            repo_ids = arguments.get("repo_ids", [])
            top_k = arguments.get("top_k", 10)

            if not query or not repo_ids:
                return [types.TextContent(type="text", text=json.dumps({"error": "Both 'query' and 'repo_ids' are required."}))]

            results = _search(query, repo_ids, top_k)
            return [types.TextContent(type="text", text=json.dumps({"results": results}, ensure_ascii=False))]

        if name == "grep":
            file_path = arguments.get("file_path")
            pattern = arguments.get("pattern", "")
            if not file_path or pattern == "":
                return [types.TextContent(type="text", text=json.dumps({"error": "Both 'file_path' and 'pattern' are required."}))]

            ignore_case = bool(arguments.get("ignore_case", False))
            fixed = bool(arguments.get("fixed", False))
            context = int(arguments.get("context", 0))
            max_matches = int(arguments.get("max_matches", 1000))

            results = _grep_file(file_path, pattern, ignore_case=ignore_case, fixed=fixed, context=context, max_matches=max_matches)
            return [types.TextContent(type="text", text=json.dumps({"results": results}, ensure_ascii=False))]

        if name == "glob":
            folder_path = arguments.get("folder_path")
            if not folder_path:
                return [types.TextContent(type="text", text=json.dumps({"error": "'folder_path' is required."}))]

            pattern = arguments.get("pattern", "**/*")
            recursive = bool(arguments.get("recursive", True))
            include_dirs = bool(arguments.get("include_dirs", False))
            include_hidden = bool(arguments.get("include_hidden", True))
            max_results = int(arguments.get("max_results", 1000))

            results = _glob_files(folder_path, pattern=pattern, recursive=recursive, include_dirs=include_dirs, include_hidden=include_hidden, max_results=max_results)
            return [types.TextContent(type="text", text=json.dumps({"results": results}, ensure_ascii=False))]

        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    except Exception as e:
        sys.stderr.write(f"ERROR: call_tool error: {e}\n")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
