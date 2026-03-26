"""
Custom tools and MCP server management endpoints.
"""
import os
import json

from fastapi import APIRouter, HTTPException

from core.models import AddMCPServerRequest
from core.config import DATA_DIR
from core.json_store import JsonStore

router = APIRouter()

_custom_tools_store = JsonStore(os.path.join(DATA_DIR, "custom_tools.json"), cache_ttl=2.0)


def load_custom_tools():
    return _custom_tools_store.load()


def save_custom_tools(tools):
    _custom_tools_store.save(tools)


@router.get("/api/tools/custom")
async def get_custom_tools():
    return load_custom_tools()


@router.get("/api/tools/available")
async def get_available_tools():
    """List all available tools from all sources (Native Agents, External MCP, Custom HTTP)"""
    import core.server as _server

    all_tools = []

    # 1. Active MCP Sessions (Native + External)
    for name, session in _server.agent_sessions.items():
        try:
            is_external = name.startswith("ext_mcp_")
            source_label = name.replace("ext_mcp_", "") if is_external else name
            tool_type = "mcp_external" if is_external else "mcp_native"

            result = await session.list_tools()
            for t in result.tools:
                all_tools.append({
                    "name": t.name,
                    "description": t.description,
                    "source": source_label,
                    "type": tool_type,
                    "schema": t.inputSchema
                })
        except Exception as e:
            print(f"Error listing tools for agent '{name}': {e}")

    # 2. Custom HTTP Tools
    try:
        custom_tools = load_custom_tools()
        for t in custom_tools:
            all_tools.append({
                "name": t.get("name"),
                "label": t.get("generalName", t.get("name")),
                "description": t.get("description", ""),
                "source": "custom_http",
                "type": "http",
                "schema": t.get("schema")
            })
    except Exception as e:
        print(f"Error listing custom tools: {e}")

    return {"tools": all_tools}


@router.post("/api/tools/custom")
async def create_custom_tool(tool: dict):
    tools = load_custom_tools()
    if any(t['name'] == tool['name'] for t in tools):
        tools = [t if t['name'] != tool['name'] else tool for t in tools]
    else:
        tools.append(tool)
    save_custom_tools(tools)
    return {"status": "success", "tool": tool}


@router.delete("/api/tools/custom/{tool_name}")
async def delete_custom_tool(tool_name: str):
    tools = load_custom_tools()
    tools = [t for t in tools if t['name'] != tool_name]
    save_custom_tools(tools)
    return {"status": "success"}


# --- External MCP Server Management ---

@router.get("/api/mcp/servers")
async def list_mcp_servers():
    import core.server as _server
    if not _server.mcp_manager:
        return []
    return _server.mcp_manager.servers_config


@router.post("/api/mcp/servers")
async def add_mcp_server(req: AddMCPServerRequest):
    import core.server as _server
    if not _server.mcp_manager:
        raise HTTPException(status_code=500, detail="MCP Manager not initialized")
    try:
        config = await _server.mcp_manager.add_server(req.name, req.command, req.args, req.env)
        # Register the new session and tools immediately
        session = _server.mcp_manager.sessions.get(req.name)
        if session:
            agent_key = f"ext_mcp_{req.name}"
            _server.agent_sessions[agent_key] = session
            tools = await session.list_tools()
            for tool in tools.tools:
                _server.tool_router[tool.name] = agent_key
        return {"status": "success", "config": config}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    import core.server as _server
    if not _server.mcp_manager:
        raise HTTPException(status_code=500, detail="MCP Manager not initialized")
    try:
        await _server.mcp_manager.remove_server(name)
        agent_key = f"ext_mcp_{name}"
        if agent_key in _server.agent_sessions:
            del _server.agent_sessions[agent_key]
        keys_to_del = [k for k, v in _server.tool_router.items() if v == agent_key]
        for k in keys_to_del:
            del _server.tool_router[k]

        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
