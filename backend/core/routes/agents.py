"""
Agent management endpoints (CRUD + active agent).
"""
import os
import json
import datetime
import zoneinfo

from fastapi import APIRouter, HTTPException

from core.models import Agent, AgentActiveRequest, GeneratePromptRequest
from core.tools import NATIVE_TOOL_SYSTEM_PROMPT
from core.config import DATA_DIR, load_settings
from core.json_store import JsonStore
from core.llm_providers import generate_response as llm_generate_response

router = APIRouter()

_agents_store = JsonStore(os.path.join(DATA_DIR, "user_agents.json"), cache_ttl=2.0)

# Module-level state
active_agent_id = "synapse"  # Default


def load_user_agents() -> list[dict]:
    return _agents_store.load()


def save_user_agents(agents: list[dict]):
    _agents_store.save(agents)


def get_active_agent_data():
    agents = load_user_agents()
    for a in agents:
        if a["id"] == active_agent_id:
            return a
    # Fallback to first or hardcoded default if file empty
    if agents:
        return agents[0]
    return {
        "id": "synapse",
        "name": "Synapse",
        "system_prompt": NATIVE_TOOL_SYSTEM_PROMPT,
        "tools": ["all"]
    }


@router.get("/api/agents")
async def get_agents():
    return load_user_agents()


@router.post("/api/agents")
async def create_agent(agent: Agent):
    agents = load_user_agents()
    # Check if exists
    for i, a in enumerate(agents):
        if a["id"] == agent.id:
            agents[i] = agent.dict()  # Update
            save_user_agents(agents)
            return agent

    agents.append(agent.dict())
    save_user_agents(agents)
    return agent


@router.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    if agent_id == "synapse":
        raise HTTPException(status_code=400, detail="Cannot delete default agent.")
    agents = load_user_agents()
    agents = [a for a in agents if a["id"] != agent_id]
    save_user_agents(agents)
    return {"status": "success"}


@router.get("/api/agents/active")
async def get_active_agent_endpoint():
    return {"active_agent_id": active_agent_id}


@router.post("/api/agents/active")
async def set_active_agent_endpoint(req: AgentActiveRequest):
    global active_agent_id
    # Validate
    agents = load_user_agents()
    ids = [a["id"] for a in agents]
    if req.agent_id not in ids:
        raise HTTPException(status_code=404, detail="Agent not found")

    active_agent_id = req.agent_id
    print(f"Active Agent switched to: {active_agent_id}")
    return {"status": "success", "active_agent_id": active_agent_id}


PROMPT_WRITER_SYSTEM = """You are an expert AI system prompt engineer. Your job is to generate comprehensive, well-structured system prompts for AI agents based on a user's description of what the agent should do.

Given the user's description and agent type, generate an extensive system prompt that includes:

1. **Role & Identity**: Clear definition of who the agent is and its primary purpose
2. **Core Capabilities**: What the agent can do, listed clearly
3. **Operating Rules**: Step-by-step thinking, accuracy guidelines, behavioral constraints
4. **Response Style**: Tone, formatting preferences, how to present information
5. **Edge Cases & Boundaries**: What the agent should NOT do, how to handle ambiguity
6. **Domain-Specific Instructions**: Any specialized knowledge or procedures relevant to the description

IMPORTANT RULES:
- Do NOT include any tools section, available tools list, or tool usage instructions — these are automatically appended by the system at runtime
- Do NOT include date/time context sections — these are also injected automatically
- If a list of available tools is provided, use that context to tailor the prompt — reference tool capabilities where relevant (e.g. "You can search emails" if email tools are available) but do NOT list the tools themselves
- Focus purely on the agent's behavior, personality, knowledge, and instructions
- Make the prompt detailed but practical — avoid fluff
- Use markdown formatting with clear section headers
- The prompt should be ready to use as-is

Output ONLY the system prompt text, no explanations or wrapping."""


@router.get("/api/agent-types")
async def get_agent_types():
    """Returns available agent types based on enabled features in settings."""
    s = load_settings()
    types = [
        {"value": "conversational", "label": "Conversational", "description": "General-purpose agent with configurable tools."},
        {"value": "analysis", "label": "Analysis", "description": "Automatically includes RAG/embedding tools for data exploration."},
        {"value": "workflow", "label": "Workflow", "description": "For orchestration workflows."},
        {"value": "orchestrator", "label": "Orchestrator", "description": "Multi-agent orchestration — deployed from the Orchestrations tab."},
    ]
    if s.get("report_agent_enabled"):
        types.insert(2, {"value": "report", "label": "Report", "description": "Report generation with dynamic RAG support."})
    if s.get("coding_agent_enabled"):
        types.insert(3, {"value": "code", "label": "Code", "description": "Automatically includes search_codebase for semantic code search."})
    return {"types": types}


@router.post("/api/agents/generate-prompt")
async def generate_agent_prompt(req: GeneratePromptRequest):
    """Generate a comprehensive system prompt from a description using the configured LLM."""
    settings = load_settings()
    mode = settings.get("mode", "local")
    model = settings.get("model", "mistral")

    now = datetime.datetime.now(zoneinfo.ZoneInfo("UTC"))
    current_datetime = now.strftime("%B %d, %Y %I:%M %p UTC")

    tools_section = ""
    if req.tools:
        tools_list = "\n".join(f"- {t}" for t in req.tools)
        tools_section = f"\n\nAvailable tools this agent will have access to:\n{tools_list}"

    existing_section = ""
    if req.existing_prompt.strip():
        existing_section = f"\n\nExisting system prompt (improve/refine based on the description above, keep what's good and enhance):\n---\n{req.existing_prompt.strip()}\n---"

    user_message = f"Current Date & Time: {current_datetime}\n\nAgent Type: {req.agent_type}\n\nDescription of what the agent should do:\n{req.description}{tools_section}{existing_section}"

    try:
        result = await llm_generate_response(
            prompt_msg=user_message,
            sys_prompt=PROMPT_WRITER_SYSTEM,
            mode=mode,
            current_model=model,
            current_settings=settings,
        )
        return {"system_prompt": result}
    except Exception as e:
        print(f"Error generating prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate prompt: {str(e)}")
