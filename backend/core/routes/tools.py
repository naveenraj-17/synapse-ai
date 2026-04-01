"""
Custom tools and MCP server management endpoints.
"""
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from core.models import AddMCPServerRequest
from core.config import DATA_DIR
from core.json_store import JsonStore
import core.mcp_oauth_state as oauth_state

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
            server_name = name[len("ext_mcp_"):] if is_external else name
            tool_type = "mcp_external" if is_external else "mcp_native"

            # Look up human-friendly label from stored config
            if is_external and _server.mcp_manager:
                cfg = _server.mcp_manager.get_server_config(server_name)
                display_label = (cfg.get("label") or server_name) if cfg else server_name
            else:
                display_label = server_name

            result = await session.list_tools()
            for t in result.tools:
                all_tools.append({
                    "name": f"{server_name}__{t.name}" if is_external else t.name,
                    "description": t.description,
                    "source": server_name,
                    "source_label": display_label,
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

async def _register_session(name: str):
    """Register a newly connected MCP session into the global tool router."""
    import core.server as _server
    session = _server.mcp_manager.sessions.get(name)
    if session:
        agent_key = f"ext_mcp_{name}"
        _server.agent_sessions[agent_key] = session
        tools = await session.list_tools()
        for tool in tools.tools:
            _server.tool_router[f"{name}__{tool.name}"] = (agent_key, tool.name)


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
        result = await _server.mcp_manager.add_server(
            name=req.name,
            label=req.label,
            server_type=req.server_type,
            command=req.command,
            args=req.args,
            env=req.env,
            url=req.url,
            token=req.token,
        )
        status   = result["status"]   # "connected" | "disconnected" | "oauth_pending"
        connected = result["connected"]

        if connected:
            await _register_session(req.name)

        if status == "oauth_pending":
            return {
                "status": "oauth_pending",
                "config": result["config"],
                "connected": False,
                "auth_url": result.get("auth_url"),
                "message": "OAuth required — opening browser. Return here once authorised.",
            }
        return {
            "status": "success" if connected else "saved",
            "config": result["config"],
            "connected": connected,
            "message": "Server connected and saved." if connected else "Config saved. Use Retry to reconnect.",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/mcp/servers/{name}/reconnect")
async def reconnect_mcp_server(name: str):
    import core.server as _server
    if not _server.mcp_manager:
        raise HTTPException(status_code=500, detail="MCP Manager not initialized")
    try:
        connected = await _server.mcp_manager.reconnect_server(name)
        if connected:
            await _register_session(name)
            return {"status": "success", "connected": True, "message": "Reconnected successfully."}
        return {"status": "failed", "connected": False, "message": "Could not reconnect."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/mcp/oauth/callback", response_class=HTMLResponse)
async def mcp_oauth_callback(code: str = None, state: str = None, error: str = None):
    """OAuth redirect URI.  Unblocks the waiting background connection task
    and returns a page that notifies the opener via postMessage then closes."""

    if error or not code or not state:
        err_msg = error or "Missing OAuth parameters"
        html = f"""
        <html><head><title>MCP Auth Failed</title></head><body>
        <p style="font-family:sans-serif;color:#e55">OAuth failed: {err_msg}</p>
        <script>
          if (window.opener) {{
            window.opener.postMessage({{ type:'MCP_OAUTH_COMPLETE', success:false, error:{json.dumps(err_msg)} }}, '*');
            setTimeout(() => window.close(), 2000);
          }}
        </script>
        </body></html>"""
        return HTMLResponse(html, status_code=400)

    found = oauth_state.complete_callback(state, code)
    name  = (oauth_state.get(state) or {}).get("name", "server") if not found else \
            next((v["name"] for k, v in {state: oauth_state.get(state)} .items() if v), "server")

    # Retrieve name before pop happened
    entry = oauth_state.get(state)
    server_name = entry["name"] if entry else "server"
    if not found:
        # state already popped by callback_handler — get name from config
        import core.server as _server
        server_name = next(
            (s["name"] for s in (_server.mcp_manager.servers_config if _server.mcp_manager else [])
             if s.get("status") in ("disconnected", "oauth_pending")),
            "server"
        )

    oauth_state.complete_callback(state, code)   # idempotent if already called

    html = f"""
    <html>
    <head><title>MCP Connected</title>
    <style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
    height:100vh;margin:0;background:#0a0a0a;color:#fff}}
    .box{{text-align:center}}.check{{font-size:3rem;color:#22c55e}}</style>
    </head><body>
    <div class="box">
      <div class="check">&#10003;</div>
      <h2>Connected to {server_name}!</h2>
      <p style="color:#888">This tab will close automatically…</p>
    </div>
    <script>
      const name = {json.dumps(server_name)};
      if (window.opener) {{
        window.opener.postMessage({{ type:'MCP_OAUTH_COMPLETE', success:true, name }}, '*');
        setTimeout(() => window.close(), 1500);
      }}
    </script>
    </body></html>"""
    return HTMLResponse(html)


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
        keys_to_del = [k for k, (ak, _) in _server.tool_router.items() if ak == agent_key]
        for k in keys_to_del:
            del _server.tool_router[k]

        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
