"""
Builder tools for the Synapse AI Builder agent.

Provides CRUD operations on agents and orchestrations that the builder
meta-agent can call to design and create multi-agent workflows.
"""
import json
import os
import random
import string
import time
import datetime
from typing import Any

from core.config import DATA_DIR
from core.json_store import JsonStore

_repos_store = JsonStore(os.path.join(DATA_DIR, "repos.json"), cache_ttl=5.0)
_db_store = JsonStore(os.path.join(DATA_DIR, "db_configs.json"), cache_ttl=5.0)
_mcp_store = JsonStore(os.path.join(DATA_DIR, "mcp_servers.json"), cache_ttl=5.0)


def _random_id(prefix: str, length: int = 7) -> str:
    chars = string.ascii_lowercase + string.digits
    return prefix + ''.join(random.choices(chars, k=length))


# ─── Tool Schemas ─────────────────────────────────────────────────────────────

BUILDER_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "List all available agents with their id, name, type, and tool count. Use this to understand what agents exist before building an orchestration.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent",
            "description": "Get the full configuration of a specific agent by ID, including its system prompt, tools, and model.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "The agent ID (e.g. agent_1774089682630)"}
                },
                "required": ["agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_agent",
            "description": (
                "Create a new agent and save it. Returns the created agent with its new ID. "
                "Use type='conversational' for general-purpose agents, 'code' for agents that work with repos/files, "
                "'orchestrator' for agents that run orchestrations. "
                "Set tools=['all'] to give access to all tools, or list specific tool names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Display name for the agent"},
                    "description": {"type": "string", "description": "What this agent does"},
                    "type": {
                        "type": "string",
                        "enum": ["conversational", "code", "orchestrator"],
                        "description": "Agent type",
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tool names, or ['all'] for all tools",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "Detailed system instructions for the agent. Be thorough.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Optional LLM model override (e.g. claude-opus-4-6, gemini-2.5-pro). Leave null for system default.",
                    },
                    "repos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of repo IDs (for code agents). Use list_repos to find IDs.",
                    },
                    "db_configs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of DB config IDs (for agents needing database access).",
                    },
                },
                "required": ["name", "description", "type", "tools", "system_prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_agent",
            "description": "Update specific fields of an existing agent. Only the fields you provide will be changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "fields": {
                        "type": "object",
                        "description": "Fields to update (name, description, tools, system_prompt, model, etc.)",
                    },
                },
                "required": ["agent_id", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_tools",
            "description": "List all tools available across all connected MCP servers and custom tools. Use this before assigning tools to agents or deciding if a capability exists.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tools_detail",
            "description": (
                "Get the full details (name, description, and input schema) for a list of tool names. "
                "Use this after list_all_tools to inspect exact parameter schemas before assigning tools to agents or tool steps."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tool names to fetch full details for (e.g. [\"brave_search\", \"read_file\"])",
                    }
                },
                "required": ["tool_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tool_servers",
            "description": "List all configured MCP tool servers with their names, types, and connection status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_repos",
            "description": "List all configured code repositories that can be assigned to code agents.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_db_configs",
            "description": "List all configured database connections that can be assigned to agents.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_orchestrations",
            "description": "List all existing orchestrations with their id, name, description, and step count.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_orchestration",
            "description": "Get the full configuration of an orchestration including all steps and their connections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "orch_id": {"type": "string", "description": "Orchestration ID"}
                },
                "required": ["orch_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_orchestration",
            "description": (
                "Create a complete orchestration workflow and save it. Returns the saved orchestration with its ID. "
                "Each step must have: id (use step_XXXXXXX format), name, type, next_step_id (or null), "
                "and type-specific fields. Always set entry_step_id. "
                "Step types: agent (needs agent_id, prompt_template, input_keys, output_key), "
                "llm (needs prompt_template, model, output_key), "
                "tool (needs forced_tool, output_key), "
                "evaluator (needs route_map, route_descriptions, evaluator_prompt, input_keys), "
                "parallel (needs parallel_branches as list of step-id lists, next_step_id is convergence), "
                "merge (needs input_keys, merge_strategy, output_key), "
                "loop (needs loop_step_ids, loop_count), "
                "human (needs human_prompt, output_key), "
                "transform (needs transform_code), "
                "end (no extra fields). "
                "All steps need: max_turns (15), timeout_seconds (300), max_iterations (3)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Complete list of StepConfig objects",
                    },
                    "entry_step_id": {"type": "string", "description": "ID of the first step to execute"},
                    "state_schema": {
                        "type": "object",
                        "description": "Optional: define named state variables. Each key maps to {type, default, description}",
                    },
                    "max_total_turns": {"type": "integer", "description": "Global turn limit (default 100)"},
                    "timeout_minutes": {"type": "integer", "description": "Overall timeout (default 30)"},
                },
                "required": ["name", "steps", "entry_step_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_orchestration",
            "description": "Update fields of an existing orchestration. Provide orch_id and the fields to change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "orch_id": {"type": "string"},
                    "fields": {
                        "type": "object",
                        "description": "Fields to update: name, description, steps, entry_step_id, state_schema, max_total_turns, timeout_minutes",
                    },
                },
                "required": ["orch_id", "fields"],
            },
        },
    },
]


# Set of all builder-tool names. Consumed by tool dispatch paths
# (react_engine, ToolStepExecutor) to route these to execute_builder_tool
# instead of MCP / custom-tool execution, and by aggregate_all_tools to
# expose them as first-class tools that any agent can declare.
BUILDER_TOOL_NAMES = {t["function"]["name"] for t in BUILDER_TOOL_SCHEMAS}


# ─── Tool Implementations ──────────────────────────────────────────────────────

async def execute_builder_tool(tool_name: str, args: dict, server_module: Any) -> str:
    """Dispatch a builder tool call and return a JSON string result."""
    try:
        result = await _dispatch(tool_name, args, server_module)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _dispatch(tool_name: str, args: dict, server_module: Any) -> Any:
    from core.routes.agents import load_user_agents, save_user_agents
    from core.routes.orchestrations import load_orchestrations, save_orchestrations

    if tool_name == "list_agents":
        agents = load_user_agents()
        return [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "type": a.get("type"),
                "description": a.get("description", ""),
                "tool_count": len(a.get("tools", [])),
                "model": a.get("model"),
            }
            for a in agents
            if a.get("type") != "builder"  # hide the builder itself
        ]

    elif tool_name == "get_agent":
        agents = load_user_agents()
        agent = next((a for a in agents if a["id"] == args["agent_id"]), None)
        if not agent:
            return {"error": f"Agent '{args['agent_id']}' not found"}
        return agent

    elif tool_name == "create_agent":
        agents = load_user_agents()
        new_id = f"agent_{int(time.time() * 1000)}"
        agent = {
            "id": new_id,
            "name": args["name"],
            "description": args.get("description", ""),
            "avatar": "default",
            "type": args.get("type", "conversational"),
            "tools": args.get("tools", ["all"]),
            "repos": args.get("repos", []),
            "db_configs": args.get("db_configs", []),
            "system_prompt": args.get("system_prompt", ""),
            "orchestration_id": None,
            "model": args.get("model") or None,
            "provider": None,
            "max_turns": None,
        }
        agents.append(agent)
        save_user_agents(agents)
        return {"status": "created", "agent": agent}

    elif tool_name == "update_agent":
        agents = load_user_agents()
        idx = next((i for i, a in enumerate(agents) if a["id"] == args["agent_id"]), None)
        if idx is None:
            return {"error": f"Agent '{args['agent_id']}' not found"}
        agents[idx].update(args.get("fields", {}))
        save_user_agents(agents)
        return {"status": "updated", "agent": agents[idx]}

    elif tool_name == "list_all_tools":
        try:
            from core.tools import aggregate_all_tools
            from core.routes.tools import load_custom_tools
            from core.routes.agents import load_user_agents as _lau
            _agents = _lau()
            active_agent = next((a for a in _agents if a.get("type") != "builder"), _agents[0] if _agents else {})
            custom_tools = load_custom_tools()
            all_tools, _, _, _ = await aggregate_all_tools(
                server_module.agent_sessions, active_agent, custom_tools
            )
            return [
                {
                    "name": t.name,
                    "description": (t.description or "")[:120],
                }
                for t in all_tools
            ]
        except Exception as e:
            return {"error": f"Could not list tools: {e}"}

    elif tool_name == "get_tools_detail":
        try:
            from core.tools import aggregate_all_tools
            from core.routes.tools import load_custom_tools
            from core.routes.agents import load_user_agents as _lau
            _agents = _lau()
            active_agent = next((a for a in _agents if a.get("type") != "builder"), _agents[0] if _agents else {})
            custom_tools = load_custom_tools()
            all_tools, _, _, _ = await aggregate_all_tools(
                server_module.agent_sessions, active_agent, custom_tools
            )
            requested = set(args.get("tool_names", []))
            result = {}
            for t in all_tools:
                if t.name in requested:
                    result[t.name] = {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
                    }
            missing = requested - result.keys()
            if missing:
                result["_not_found"] = sorted(missing)
            return result
        except Exception as e:
            return {"error": f"Could not fetch tool details: {e}"}

    elif tool_name == "list_tool_servers":
        servers = _mcp_store.load()
        if not isinstance(servers, list):
            servers = []
        return [
            {
                "name": s.get("name"),
                "label": s.get("label", s.get("name")),
                "type": s.get("server_type", "stdio"),
                "status": s.get("status", "unknown"),
            }
            for s in servers
        ]

    elif tool_name == "list_repos":
        repos = _repos_store.load()
        if not isinstance(repos, list):
            return []
        return [
            {"id": r.get("id"), "name": r.get("name", r.get("path", "")), "path": r.get("path", "")}
            for r in repos
        ]

    elif tool_name == "list_db_configs":
        dbs = _db_store.load()
        if not isinstance(dbs, list):
            return []
        return [
            {"id": d.get("id"), "name": d.get("name", ""), "type": d.get("type", "")}
            for d in dbs
        ]

    elif tool_name == "list_orchestrations":
        orchs = load_orchestrations()
        return [
            {
                "id": o.get("id"),
                "name": o.get("name"),
                "description": o.get("description", ""),
                "step_count": len(o.get("steps", [])),
            }
            for o in orchs
        ]

    elif tool_name == "get_orchestration":
        orchs = load_orchestrations()
        orch = next((o for o in orchs if o["id"] == args["orch_id"]), None)
        if not orch:
            return {"error": f"Orchestration '{args['orch_id']}' not found"}
        return orch

    elif tool_name == "create_orchestration":
        orchs = load_orchestrations()
        orch_id = _random_id("orch_")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        steps = args.get("steps", [])
        # Fill defaults for any step missing required fields
        steps = _fill_step_defaults(steps)

        orch = {
            "id": orch_id,
            "name": args["name"],
            "description": args.get("description", ""),
            "avatar": "default",
            "steps": steps,
            "entry_step_id": args["entry_step_id"],
            "state_schema": args.get("state_schema", {}),
            "max_total_turns": args.get("max_total_turns", 100),
            "max_total_cost_usd": None,
            "timeout_minutes": args.get("timeout_minutes", 30),
            "trigger": "manual",
            "created_at": now,
            "updated_at": now,
        }
        orchs.append(orch)
        save_orchestrations(orchs)
        return {"status": "created", "orchestration": orch}

    elif tool_name == "update_orchestration":
        orchs = load_orchestrations()
        idx = next((i for i, o in enumerate(orchs) if o["id"] == args["orch_id"]), None)
        if idx is None:
            return {"error": f"Orchestration '{args['orch_id']}' not found"}
        fields = args.get("fields", {})
        if "steps" in fields:
            fields["steps"] = _fill_step_defaults(fields["steps"])
        orchs[idx].update(fields)
        orchs[idx]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save_orchestrations(orchs)
        return {"status": "updated", "orchestration": orchs[idx]}

    else:
        return {"error": f"Unknown tool: {tool_name}"}


def _fill_step_defaults(steps: list) -> list:
    """Ensure every step has the required default fields."""
    result = []
    for i, step in enumerate(steps):
        s = dict(step)
        # Generate ID if missing
        if not s.get("id"):
            s["id"] = _random_id("step_")
        # Canvas positions: simple left-to-right layout
        if "position_x" not in s:
            s["position_x"] = -600 + i * 350
        if "position_y" not in s:
            s["position_y"] = 0.0
        # Defaults
        s.setdefault("agent_id", None)
        s.setdefault("prompt_template", None)
        s.setdefault("route_map", {})
        s.setdefault("route_descriptions", {})
        s.setdefault("evaluator_prompt", None)
        s.setdefault("model", None)
        s.setdefault("parallel_branches", [])
        s.setdefault("merge_strategy", "list")
        s.setdefault("loop_count", 3)
        s.setdefault("loop_step_ids", [])
        s.setdefault("transform_code", None)
        s.setdefault("human_prompt", None)
        s.setdefault("human_fields", [])
        s.setdefault("human_channel_id", None)
        s.setdefault("human_timeout_seconds", 3600)
        s.setdefault("input_keys", [])
        s.setdefault("output_key", None)
        s.setdefault("forced_tool", None)
        s.setdefault("max_turns", 15)
        s.setdefault("timeout_seconds", 300)
        s.setdefault("allowed_tools", None)
        s.setdefault("next_step_id", None)
        s.setdefault("max_iterations", 3)
        result.append(s)
    return result


