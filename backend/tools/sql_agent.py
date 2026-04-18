
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
import asyncio
import json
import os
from sqlalchemy import create_engine, inspect, text
from core.config import load_settings, DATA_DIR, sanitize_db_url

# Initialize MCP Server
app = Server("sql-mcp-server")

# Per-db_id engine cache: db_id -> (engine, inspector)
_engines: dict[str, tuple] = {}

# Mutation keywords that indicate a write operation
_WRITE_KEYWORDS = {
    "insert", "update", "delete", "drop", "create", "alter",
    "truncate", "replace", "merge", "upsert", "grant", "revoke",
}


def _is_write_query(query: str) -> bool:
    first_word = query.strip().split()[0].lower() if query.strip() else ""
    return first_word in _WRITE_KEYWORDS


def _load_db_configs() -> list[dict]:
    """Load db_configs.json from the data directory."""
    path = os.path.join(DATA_DIR, "db_configs.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def get_db_engine(db_id: str | None = None):
    """Return (engine, inspector) for the given db_id, or fall back to global setting."""
    global _engines

    if db_id:
        if db_id in _engines:
            return _engines[db_id]
        configs = _load_db_configs()
        config = next((c for c in configs if c.get("id") == db_id), None)
        if not config:
            raise ValueError(f"No database config found for db_id='{db_id}'.")
        conn_str = config.get("connection_string", "")
        if not conn_str:
            raise ValueError(f"Database config '{db_id}' has no connection string.")
        engine = create_engine(conn_str, echo=False)
        inspector = inspect(engine)
        _engines[db_id] = (engine, inspector)
        return engine, inspector

    # Fallback: global sql_connection_string from settings
    settings = load_settings()
    db_url = sanitize_db_url(settings.get("sql_connection_string", ""))
    if not db_url:
        raise ValueError("No db_id provided and no global SQL connection string found in settings.")
    cache_key = "__global__"
    if cache_key in _engines:
        return _engines[cache_key]
    engine = create_engine(db_url, echo=False)
    inspector = inspect(engine)
    _engines[cache_key] = (engine, inspector)
    return engine, inspector


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    db_id_prop = {
        "db_id": {
            "type": "string",
            "description": "The ID of the database config to use (from LINKED DATABASES in your system prompt). Required when multiple databases are configured."
        }
    }
    return [
        types.Tool(
            name="list_tables",
            description="List all tables in a database. Provide db_id when multiple databases are linked.",
            inputSchema={
                "type": "object",
                "properties": db_id_prop,
            }
        ),
        types.Tool(
            name="get_table_schema",
            description="Get the detailed schema (columns, types, foreign keys) for specific table(s). Provide db_id when multiple databases are linked.",
            inputSchema={
                "type": "object",
                "properties": {
                    **db_id_prop,
                    "table_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of table names to inspect."
                    }
                },
                "required": ["table_names"]
            }
        ),
        types.Tool(
            name="run_sql_query",
            description=(
                "Execute a SQL query against a linked database. "
                "Provide db_id when multiple databases are linked. "
                "Write queries (INSERT/UPDATE/DELETE/DROP/etc.) require allow_db_write to be enabled in settings "
                "AND explicit user confirmation BEFORE calling this tool."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    **db_id_prop,
                    "query": {
                        "type": "string",
                        "description": "The SQL query to execute."
                    }
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    try:
        db_id = arguments.get("db_id") or None
        engine, inspector = get_db_engine(db_id)

        if name == "list_tables":
            tables = inspector.get_table_names()
            return [types.TextContent(
                type="text",
                text=f"Found {len(tables)} tables:\n" + "\n".join([f"- {t}" for t in tables])
            )]

        elif name == "get_table_schema":
            table_names = arguments.get("table_names", [])
            schemas = []
            for table in table_names:
                try:
                    columns = inspector.get_columns(table)
                    fks = inspector.get_foreign_keys(table)
                    pk = inspector.get_pk_constraint(table)
                    col_strings = []
                    for col in columns:
                        nullable = "NULL" if col['nullable'] else "NOT NULL"
                        is_pk = " (PK)" if col['name'] in pk.get('constrained_columns', []) else ""
                        col_strings.append(f"- {col['name']} ({col['type']}) {nullable}{is_pk}")
                    fk_strings = [
                        f"-> FK to {fk['referred_table']}.{fk['referred_columns'][0]} on {fk['constrained_columns'][0]}"
                        for fk in fks
                    ]
                    schema_text = (
                        f"**Table: {table}**\nColumns:\n" + "\n".join(col_strings) +
                        ("\nForeign Keys:\n" + "\n".join(fk_strings) if fk_strings else "")
                    )
                    schemas.append(schema_text)
                except Exception as e:
                    schemas.append(f"Error inspecting table {table}: {str(e)}")
            return [types.TextContent(type="text", text="\n\n".join(schemas))]

        elif name == "run_sql_query":
            query = arguments.get("query", "").strip()

            if _is_write_query(query):
                settings = load_settings()
                allow_db_write = settings.get("allow_db_write", False)
                if not allow_db_write:
                    return [types.TextContent(
                        type="text",
                        text=(
                            "BLOCKED: This query modifies the database and DB write access is currently disabled. "
                            "A user with admin access must enable 'Allow agents to modify database' in General Settings."
                        )
                    )]

            with engine.connect() as connection:
                result = connection.execute(text(query))
                # Commit for write operations so changes persist
                if _is_write_query(query):
                    connection.commit()
                    return [types.TextContent(
                        type="text",
                        text=f"Query executed successfully. Rows affected: {result.rowcount}"
                    )]
                keys = list(result.keys())
                rows = [dict(zip(keys, row)) for row in result.fetchall()]
                if len(rows) > 50:
                    rows = rows[:50]
                    suffix = "\n...(Truncated to 50 rows)"
                else:
                    suffix = ""
                return [types.TextContent(
                    type="text",
                    text=json.dumps(rows, default=str, indent=2) + suffix
                )]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
