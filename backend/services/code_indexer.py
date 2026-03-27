"""
Code indexer service: CocoIndex flow definitions, index management, and DB operations.
Handles repo indexing lifecycle — creation, status, deletion, and background indexing.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from core.config import load_settings

try:
    import cocoindex
    import psycopg
    COCOINDEX_AVAILABLE = True
except ImportError:
    COCOINDEX_AVAILABLE = False

# Lock for repos.json read/write to prevent race conditions during concurrent indexing
_repos_lock = threading.Lock()

# Cache of active CocoIndex Flow objects so we can close them before re-registering
_active_flows: dict[str, object] = {}

# Connect using psycopg pool (CocoIndex prefers standard postgres connections)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/synapse")

# Shared constant — query embedding model must match index embedding model
CODE_EMBEDDING_MODEL = "gemini-embedding-001"
CODE_EMBEDDING_DIM = 768


def _extract_extension(filename: str) -> str:
    return os.path.splitext(filename)[1]


if COCOINDEX_AVAILABLE:
    try:
        extract_extension = cocoindex.op.function()(_extract_extension)
    except RuntimeError:
        # Already registered from a previous import — reuse the plain function
        extract_extension = _extract_extension
else:
    extract_extension = _extract_extension


# Our custom function for embedding via Gemini
def _gemini_embed_batch(texts: list[str]) -> list:
    zeros = [[0.0] * CODE_EMBEDDING_DIM for _ in range(len(texts))]
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("google-genai is not installed, code index embedding will fail.")
        return zeros

    settings = load_settings()
    if not settings.get("gemini_key"):
        print("Gemini API key not found in settings!")
        return zeros

    client = genai.Client(api_key=settings["gemini_key"])

    try:
        result = client.models.embed_content(
            model=CODE_EMBEDDING_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=CODE_EMBEDDING_DIM)
        )
        if not result.embeddings:
            return zeros
        return [em.values for em in result.embeddings]
    except Exception as e:
        import traceback
        print(f"ERROR: calling gemini embeddings failed: {type(e).__name__} {e}")
        traceback.print_exc()
        return zeros


if COCOINDEX_AVAILABLE:
    try:
        gemini_embed_batch = cocoindex.op.function(batching=True, max_batch_size=100)(_gemini_embed_batch)
    except RuntimeError:
        gemini_embed_batch = _gemini_embed_batch
else:
    gemini_embed_batch = _gemini_embed_batch


def get_table_name(repo_id: str) -> str:
    """Return the predictable Postgres table name for a repo's embeddings.

    CocoIndex creates tables as {lowercase_flow_name}__{export_name}.
    We use short names (flow='ci_{repo_id}', export='emb') so the total
    stays well under Postgres' 63-char identifier limit.
    """
    return f"ci_{repo_id}__emb"


def create_repo_flow(repo_id: str, repo_path: str, included_patterns: list[str], excluded_patterns: list[str]):
    """Dynamically create a CocoIndex flow for a specific repo."""
    if not COCOINDEX_AVAILABLE:
        raise RuntimeError("CocoIndex is not installed. Enable the coding agent to use this feature.")

    flow_name = f"ci_{repo_id}"

    # Close previous flow registration if it exists (prevents "already exists" on reindex)
    if flow_name in _active_flows:
        try:
            _active_flows[flow_name].close()
        except Exception:
            pass
        del _active_flows[flow_name]

    @cocoindex.flow_def(name=flow_name)
    def repo_flow(flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope):
        data_scope["files"] = flow_builder.add_source(
            cocoindex.sources.LocalFile(
                path=repo_path,
                included_patterns=included_patterns,
                excluded_patterns=excluded_patterns
            )
        )

        code_embeddings = data_scope.add_collector()

        with data_scope["files"].row() as file:
            file["extension"] = file["filename"].transform(extract_extension)
            file["chunks"] = file["content"].transform(
                cocoindex.functions.SplitRecursively(),
                language=file["extension"],
                chunk_size=1000,
                chunk_overlap=300
            )

            with file["chunks"].row() as chunk:
                chunk["embedding"] = chunk["text"].transform(gemini_embed_batch)
                code_embeddings.collect(
                    filename=file["filename"],
                    location=chunk["location"],
                    code=chunk["text"],
                    embedding=chunk["embedding"]
                )

        code_embeddings.export(
            "emb",
            cocoindex.storages.Postgres(),
            primary_key_fields=["filename", "location"],
            vector_indexes=[cocoindex.index.VectorIndexDef(
                field_name="embedding",
                metric=cocoindex.index.VectorSimilarityMetric.COSINE_SIMILARITY
            )]
        )

    _active_flows[flow_name] = repo_flow
    return repo_flow


def _ensure_database_exists():
    """Create the target database if it doesn't already exist."""
    if not COCOINDEX_AVAILABLE:
        return
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(DATABASE_URL)
    db_name = parsed.path.lstrip("/")

    # Connect to the default 'postgres' maintenance database to run CREATE DATABASE
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    try:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                if not cur.fetchone():
                    cur.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"Created database '{db_name}'.")
    except Exception as e:
        print(f"Warning: could not ensure database exists: {e}")


def init_cocoindex():
    if not COCOINDEX_AVAILABLE:
        return
    _ensure_database_exists()
    os.environ["COCOINDEX_DATABASE_URL"] = DATABASE_URL
    print("CocoIndex init check done.")


def get_index_status(repo_id: str) -> dict:
    if not COCOINDEX_AVAILABLE:
        return {"status": "unavailable", "count": 0}
    table_name = get_table_name(repo_id)
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s);", (f"public.{table_name}",))
                if not cur.fetchone()[0]:
                    return {"status": "pending", "count": 0}

                cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                count = cur.fetchone()[0]
                return {"status": "indexed", "count": count}
    except Exception as e:
        print(f"Error checking index {repo_id}: {e}")
        return {"status": "error", "message": str(e), "count": 0}


def drop_index(repo_id: str):
    if not COCOINDEX_AVAILABLE:
        return
    table_name = get_table_name(repo_id)
    tracking = f"ci_{repo_id}__cocoindex_tracking"
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
                cur.execute(f'DROP TABLE IF EXISTS "{tracking}" CASCADE;')
                conn.commit()
    except Exception as e:
        print(f"Error dropping table {table_name}: {e}")


def _update_repo_status(repo_id: str, **fields):
    """Thread-safe update of a repo's metadata in repos.json."""
    repos_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "repos.json")
    if not os.path.exists(repos_file):
        return
    with _repos_lock:
        with open(repos_file, 'r') as f:
            repos = json.load(f)
        for r in repos:
            if r["id"] == repo_id:
                r.update(fields)
                break
        with open(repos_file, 'w') as f:
            json.dump(repos, f, indent=4)


def run_index_task(repo_id: str, repo_path: str, included_patterns: list[str], excluded_patterns: list[str]):
    if not COCOINDEX_AVAILABLE:
        print("CocoIndex not available — skipping index task.")
        return
    print(f"Starting index builder for {repo_id}...")
    try:
        repo_flow = create_repo_flow(repo_id, repo_path, included_patterns, excluded_patterns)
        os.environ["COCOINDEX_DATABASE_URL"] = DATABASE_URL
        cocoindex.init()
        repo_flow.setup()
        repo_flow.update(full_reprocess=True)

        stats = get_index_status(repo_id)
        _update_repo_status(
            repo_id,
            status=stats["status"],
            file_count=stats["count"],
            last_indexed=datetime.now().isoformat(),
            error_message=None,
        )
        print(f"Finished index builder for {repo_id}")
    except Exception as e:
        print(f"Error running index builder for {repo_id}: {e}")
        _update_repo_status(
            repo_id,
            status="error",
            error_message=str(e)[:500],
        )


def run_index(repo_id: str, repo_path: str, included_patterns: list[str], excluded_patterns: list[str]):
    t = threading.Thread(target=run_index_task, args=(repo_id, repo_path, included_patterns, excluded_patterns))
    t.start()
