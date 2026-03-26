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

DATABASE_URL = "postgresql://postgres:root@localhost:5432/cocoindex"

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

                    for row in cur.fetchall():
                        # location may be a psycopg Range object — convert to string
                        loc = row[2]
                        if hasattr(loc, 'lower') and hasattr(loc, 'upper'):
                            loc = f"{loc.lower}-{loc.upper}"
                        else:
                            loc = str(loc) if loc is not None else ""
                        all_results.append({
                            "repo_id": repo_id,
                            "filename": row[0],
                            "code": row[1],
                            "location": loc,
                            "score": round(1.0 - row[3], 5)
                        })
                except Exception as e:
                    sys.stderr.write(f"Error querying {table_name}: {e}\n")

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


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
        )
    ]


@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent]:
    if name != "search_codebase":
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        query = arguments.get("query", "")
        repo_ids = arguments.get("repo_ids", [])
        top_k = arguments.get("top_k", 10)

        if not query or not repo_ids:
            return [types.TextContent(type="text", text=json.dumps({"error": "Both 'query' and 'repo_ids' are required."}))]

        results = _search(query, repo_ids, top_k)
        return [types.TextContent(type="text", text=json.dumps({"results": results}, ensure_ascii=False))]
    except Exception as e:
        sys.stderr.write(f"ERROR: search_codebase error: {e}\n")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
