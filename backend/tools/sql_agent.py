
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
import asyncio
import json
import sqlalchemy
from sqlalchemy import create_engine, inspect, text
from core.config import load_settings

# Initialize MCP Server
app = Server("sql-mcp-server")

# Global Engine
engine = None
inspector = None

def get_db_engine():
    global engine, inspector
    settings = load_settings()
    db_url = settings.get("sql_connection_string", "")
    
    if not db_url:
        raise ValueError("No SQL Connection String found in settings.")
    
    if engine is None:
        # Create engine
        # echo=False to avoid cluttering logs
        engine = create_engine(db_url, echo=False)
        inspector = inspect(engine)
    
    return engine, inspector

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_tables",
            description="List all tables in the database to understand the schema overview.",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        types.Tool(
            name="get_table_schema",
            description="Get the detailed schema (columns, types, foreign keys) for specific table(s).",
            inputSchema={
                "type": "object",
                "properties": {
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
            description="Execute a SQL SELECT query. Read-only access recommended. Returns the rows.",
            inputSchema={
                "type": "object",
                "properties": {
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
        engine, inspector = get_db_engine()
        
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
                    
                    # Format nicely
                    col_strings = []
                    for col in columns:
                        nullable = "NULL" if col['nullable'] else "NOT NULL"
                        is_pk = " (PK)" if col['name'] in pk.get('constrained_columns', []) else ""
                        col_strings.append(f"- {col['name']} ({col['type']}) {nullable}{is_pk}")
                    
                    fk_strings = []
                    for fk in fks:
                        fk_strings.append(f"-> FK to {fk['referred_table']}.{fk['referred_columns'][0]} on {fk['constrained_columns'][0]}")
                        
                    schema_text = f"**Table: {table}**\n" + \
                                  "Columns:\n" + "\n".join(col_strings) + "\n" + \
                                  ("Foreign Keys:\n" + "\n".join(fk_strings) if fk_strings else "")
                    schemas.append(schema_text)
                except Exception as e:
                    schemas.append(f"Error inspecting table {table}: {str(e)}")
            
            return [types.TextContent(
                type="text",
                text="\n\n".join(schemas)
            )]

        elif name == "run_sql_query":
            query = arguments.get("query", "")
            if not query.strip().lower().startswith("select") and not query.strip().lower().startswith("show") and not query.strip().lower().startswith("desc"):
                return [types.TextContent(
                    type="text",
                    text="Error: Only SELECT/SHOW/DESCRIBE queries are allowed for safety."
                )]
            
            with engine.connect() as connection:
                result = connection.execute(text(query))
                keys = result.keys()
                rows = [dict(zip(keys, row)) for row in result.fetchall()]
                
                # Limit output size for context window
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
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
