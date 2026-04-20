"""
Code indexer agent: search_codebase tool for vector similarity search.
All indexing/management functions live in services/code_indexer.py.
"""
import os
import re
from core.config import load_settings, sanitize_db_url
from services.code_indexer import CODE_EMBEDDING_MODEL, CODE_EMBEDDING_DIM, get_table_name

try:
    from psycopg_pool import ConnectionPool
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

# Module-level lazy connection pool singleton (keyed by URL so it resets if settings change)
_pool = None
_pool_url: str | None = None


def _get_pool():
    global _pool, _pool_url
    if not PSYCOPG_AVAILABLE:
        raise RuntimeError("psycopg_pool is not installed. Enable the coding agent feature.")
    db_url = sanitize_db_url(load_settings().get("sql_connection_string", ""))
    if not db_url:
        raise RuntimeError("No database URL configured. Set sql_connection_string in Settings → General.")
    if _pool is None or _pool_url != db_url:
        _pool = ConnectionPool(db_url, min_size=1, max_size=5)
        _pool_url = db_url
    return _pool


def _get_query_embedding(query: str) -> list[float]:
    """Generate an embedding vector for the search query using Gemini.
    Uses the same model as indexing (CODE_EMBEDDING_MODEL) to ensure dimensions match.
    """
    from google import genai
    from google.genai import types

    settings = load_settings()
    if not settings.get("gemini_key"):
        raise ValueError("Gemini API key not found in settings")

    client = genai.Client(api_key=settings["gemini_key"])
    result = client.models.embed_content(
        model=CODE_EMBEDDING_MODEL,
        contents=[query],
        config=types.EmbedContentConfig(output_dimensionality=CODE_EMBEDDING_DIM)
    )
    return result.embeddings[0].values


_VALID_REPO_ID = re.compile(r'^repo_\d+$')


def search_codebase(query: str, repo_ids: list[str],
                    top_k: int = 10,
                    weights: dict[str, float] | None = None) -> list[dict]:
    """
    Search indexed repos using cosine similarity (<=>).
    """
    try:
        pool = _get_pool()
    except Exception as e:
        print(f"ERROR: Database connection pool failed: {e}")
        return [{"error": f"Database connection failed: {e}"}]

    query_vector = _get_query_embedding(query)
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    all_results = []

    for repo_id in repo_ids:
        if not _VALID_REPO_ID.match(repo_id):
            print(f"WARNING: Invalid repo_id format: {repo_id}, skipping")
            continue

        weight = (weights or {}).get(repo_id, 1.0)

        with pool.connection() as conn:
            with conn.cursor() as cur:
                try:
                    table_name = get_table_name(repo_id)

                    cur.execute(f"""
                        SELECT filename, code, location,
                               embedding <=> %s::vector AS distance
                        FROM "{table_name}"
                        ORDER BY distance
                        LIMIT %s
                    """, (vector_str, top_k))

                    for row in cur.fetchall():
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
                            "score": round((1.0 - row[3]) * weight, 5)
                        })
                except Exception as e:
                    print(f"Error querying {table_name}: {e}")

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]
