"""
Agent management endpoints (CRUD + active agent).
"""
import os
import json
import datetime
import zoneinfo

from fastapi import APIRouter, HTTPException

from core.models import Agent, AgentActiveRequest, GeneratePromptRequest
from core.config import DATA_DIR, load_settings
from core.json_store import JsonStore
from core.llm_providers import generate_response as llm_generate_response

router = APIRouter()

_agents_store = JsonStore(os.path.join(DATA_DIR, "user_agents.json"), cache_ttl=2.0)

# Module-level state
active_agent_id: str | None = None


def load_user_agents() -> list[dict]:
    return _agents_store.load()


def save_user_agents(agents: list[dict]):
    _agents_store.save(agents)


def get_active_agent_data():
    agents = load_user_agents()
    if active_agent_id:
        for a in agents:
            if a["id"] == active_agent_id:
                return a
    if agents:
        return agents[0]
    raise RuntimeError("No agents configured.")


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
    global active_agent_id
    agents = load_user_agents()
    agents = [a for a in agents if a["id"] != agent_id]
    save_user_agents(agents)
    if active_agent_id == agent_id:
        active_agent_id = None
    return {"status": "success"}


@router.get("/api/agents/active")
async def get_active_agent_endpoint():
    try:
        agent = get_active_agent_data()
        return {"active_agent_id": agent["id"]}
    except RuntimeError:
        return {"active_agent_id": None}


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


PROMPT_WRITER_SYSTEM = """You are an elite AI system prompt architect. Your job is to generate high-quality, production-grade system prompts for AI agents.

You approach this in two phases:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1: DEEP ANALYSIS (internal — do NOT output this)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before writing the prompt, silently reason through:

1. **User's Real Intent:** What is the user actually trying to accomplish? Look past the surface description. A "Jira agent" isn't just about reading tickets — it's about saving engineering time by automating triage, surfacing blockers, and writing implementation briefs. Identify the deeper goal.

2. **Tool Capability Mapping:** Study the available tools carefully. For each tool, understand:
   - What it actually does (not just its name)
   - What workflows it enables when combined with other tools
   - What the agent CAN'T do because of missing tools (this defines boundaries)
   Group tools into capability clusters (e.g., "web research" = browser_navigate + browser_snapshot + browser_click; "data processing" = execute_python + parse_xlsx + read_file).

3. **Failure Modes:** What are the most likely ways this agent will produce bad output? (e.g., hallucinating data instead of using tools, giving vague answers, going on tangents, not knowing when to stop)

4. **Agent Type Implications:**
   - `conversational`: Interactive, multi-turn. Must handle follow-ups, clarifications, and context shifts gracefully.
   - `code`: Technical precision required. Must read before writing, verify before claiming, cite file paths and line numbers.
   - `orchestrator`: Coordinates sub-agents. Must decompose tasks, manage handoffs, and synthesize results from multiple sources.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2: GENERATE THE SYSTEM PROMPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Using your analysis, generate a system prompt with ALL of the following sections:

### 1. ROLE & MISSION
- One-paragraph identity: who the agent is, what it exists to do, and what success looks like.
- Frame the mission around the user's real intent, not just the surface task.

### 2. CORE CAPABILITIES
- What the agent can do, organized by capability cluster (not individual tools).
- Reference tool capabilities naturally (e.g., "You can browse the web and extract structured data from any page" — NOT "You have browser_navigate, browser_snapshot").

### 3. APPROACH & METHODOLOGY
This is critical. Define HOW the agent should think and work:
- **Task Decomposition:** How to break down complex requests into steps.
- **Information Gathering Strategy:** When to use tools vs. existing knowledge. What to verify and what to trust.
- **Decision Framework:** How to choose between multiple valid approaches. Favor the simplest approach that fully solves the problem.
- **Iterative Refinement:** When to refine results vs. when "good enough" is good enough.

### 4. REASONING & TRANSPARENCY
Instruct the agent to:
- Briefly explain WHY it chose a particular approach before executing.
- When making judgment calls (e.g., prioritizing one interpretation over another), state the reasoning.
- When tool results are ambiguous or incomplete, acknowledge uncertainty rather than filling gaps with assumptions.
- After completing a multi-step task, provide a brief summary of what was done and why.

### 5. CONSTRAINTS & GUARDRAILS
Explicit rules about what the agent must NOT do. Tailor these to the specific agent type and tools:
- **Data Integrity:** Never fabricate data, statistics, quotes, or file contents. If information isn't available through tools, say so.
- **Scope Boundaries:** Define what's in-scope vs. out-of-scope for this agent. If the user asks for something outside scope, acknowledge it and explain what you CAN do.
- **Tool Discipline:** Never claim to have done something without actually calling the relevant tool. Don't assume tool outputs — always check.
- **Hallucination Prevention:** Specific triggers where this agent type is most likely to hallucinate, and what to do instead.
- Add domain-specific constraints based on the agent's purpose.

### 6. OUTPUT FORMAT & RESPONSE STYLE
- Define the default response structure (use a markdown template if appropriate).
- Specify tone (technical, conversational, formal, etc.) based on the agent's purpose.
- Define different formats for different response types (e.g., quick answers vs. detailed analysis vs. error states).
- Include formatting rules: when to use tables, when to use bullet points, when to use code blocks.
- Instruct the agent to adapt verbosity to complexity — short answers for simple questions, detailed responses for complex ones.

### 7. EDGE CASES & ERROR HANDLING
- What to do when the user's request is ambiguous (ask for clarification vs. make best guess — and when each is appropriate).
- What to do when tools fail or return unexpected results.
- What to do when the task is partially completable — deliver what you can and clearly state what's missing.
- How to handle requests that conflict with the agent's constraints.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT RULES FOR YOU (THE PROMPT WRITER):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Do NOT include any tools section, available tools list, or tool-calling format instructions — these are injected by the system at runtime.
- Do NOT include date/time context — also injected automatically.
- Do NOT list tool names (e.g., "browser_navigate") — instead describe capabilities naturally.
- Make every sentence actionable. No filler like "You are a helpful assistant." Every line should change behavior.
- The prompt must be self-contained and ready to use as-is.
- Use markdown with clear section headers.
- Aim for depth over breadth — a focused, well-reasoned prompt for the specific use case beats a generic one covering everything superficially.

Output ONLY the system prompt text. No explanations, preamble, or wrapping."""


@router.get("/api/agent-types")
async def get_agent_types():
    """Returns available agent types based on enabled features in settings."""
    s = load_settings()
    types = [
        {"value": "conversational", "label": "Conversational", "description": "General-purpose agent with configurable tools."},
        {"value": "orchestrator", "label": "Orchestrator", "description": "Multi-agent orchestration — deployed from the Orchestrations tab."},
    ]
    if s.get("coding_agent_enabled"):
        types.insert(2, {"value": "code", "label": "Code", "description": "Automatically includes search_codebase for semantic code search."})
    return {"types": types}


def _categorize_tools(tools: list[str]) -> str:
    """Group flat tool list into capability clusters for better LLM understanding."""
    categories = {
        "Web & Browser": [],
        "File System & Code": [],
        "Data Processing": [],
        "Communication & Workspace": [],
        "Database": [],
        "Persistence & Vault": [],
        "Reasoning & Planning": [],
        "Other": [],
    }

    keyword_map = {
        "Web & Browser": ["browser_", "web_", "parse_pdf", "parse_url"],
        "File System & Code": ["read_file", "read_text_file", "read_multiple_files", "read_file_by_lines",
                               "write_file", "list_directory", "directory_tree", "search_files",
                               "get_file_info", "list_allowed_directories", "list_directory_with_sizes",
                               "search_codebase", "grep", "glob", "edit_file", "create_file"],
        "Data Processing": ["execute_python", "parse_xlsx", "parse_csv", "search_embedded_report"],
        "Communication & Workspace": ["gmail_", "gcal_", "gdrive_", "slack_", "jira_", "send_", "google_"],
        "Database": ["run_sql", "list_tables", "get_table_schema", "db_"],
        "Persistence & Vault": ["vault_", "memory_"],
        "Reasoning & Planning": ["sequentialthinking"],
    }

    for tool_entry in tools:
        tool_name = tool_entry.split(" - ")[0].strip().lower()
        placed = False
        for category, keywords in keyword_map.items():
            if any(tool_name.startswith(k) or k in tool_name for k in keywords):
                categories[category].append(tool_entry)
                placed = True
                break
        if not placed:
            categories["Other"].append(tool_entry)

    sections = []
    for category, cat_tools in categories.items():
        if cat_tools:
            tool_lines = "\n".join(f"  - {t}" for t in cat_tools)
            sections.append(f"**{category}:**\n{tool_lines}")

    return "\n\n".join(sections) if sections else "No specific tools selected."


AGENT_TYPE_CONTEXT = {
    "conversational": (
        "This is a CONVERSATIONAL agent — it interacts directly with users in multi-turn dialogue. "
        "It should handle follow-up questions, context shifts, and clarification requests gracefully. "
        "The prompt should optimize for helpful, accurate, and well-structured responses."
    ),
    "code": (
        "This is a CODE agent — it works with codebases, repositories, and technical tasks. "
        "It has access to semantic code search across indexed repos, file reading, and grep/glob. "
        "The prompt should emphasize: read before modifying, cite file paths and line numbers, "
        "verify assumptions by reading code rather than guessing, and technical precision."
    ),
    "orchestrator": (
        "This is an ORCHESTRATOR agent — it coordinates multi-step workflows across sub-agents. "
        "It receives context from previous steps and must produce structured outputs for downstream steps. "
        "The prompt should emphasize: clear task decomposition, structured output formats, "
        "and awareness that its output feeds into other agents."
    ),
}


@router.post("/api/agents/generate-prompt")
async def generate_agent_prompt(req: GeneratePromptRequest):
    """Generate a comprehensive system prompt from a description using the configured LLM."""
    settings = load_settings()
    mode = settings.get("mode", "local")
    model = settings.get("model", "mistral")

    now = datetime.datetime.now(zoneinfo.ZoneInfo("UTC"))
    current_datetime = now.strftime("%B %d, %Y %I:%M %p UTC")

    # Build structured tool context
    tools_section = ""
    if req.tools:
        categorized = _categorize_tools(req.tools)
        tools_section = (
            f"\n\n━━━ AVAILABLE TOOLS (grouped by capability) ━━━\n"
            f"{categorized}\n"
            f"\nThe agent should leverage these tools strategically. "
            f"Understand what workflows become possible by COMBINING tools "
            f"(e.g., browser tools + vault = research with persistent notes; "
            f"file reading + execute_python = data analysis pipeline). "
            f"Also note what the agent CANNOT do based on which tools are absent."
        )

    # Build agent type context
    type_context = AGENT_TYPE_CONTEXT.get(req.agent_type, "")

    # Build existing prompt section for refinement
    existing_section = ""
    if req.existing_prompt.strip():
        existing_section = (
            f"\n\n━━━ EXISTING PROMPT TO REFINE ━━━\n"
            f"The user already has a system prompt and wants it improved. "
            f"Preserve what works well, fix weaknesses, and enhance with the sections "
            f"defined in your instructions. Here is the current prompt:\n"
            f"---\n{req.existing_prompt.strip()}\n---"
        )

    user_message = (
        f"Current Date & Time: {current_datetime}\n\n"
        f"━━━ AGENT TYPE ━━━\n"
        f"Type: {req.agent_type}\n"
        f"{type_context}\n\n"
        f"━━━ USER'S DESCRIPTION ━━━\n"
        f"{req.description}\n"
        f"\nAnalyze this description carefully. What is the user's REAL goal? "
        f"What problem are they trying to solve? What would make this agent "
        f"genuinely useful vs. just technically correct?"
        f"{tools_section}"
        f"{existing_section}"
    )

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
