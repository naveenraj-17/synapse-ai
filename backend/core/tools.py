"""
Tool definitions, aggregation, and system prompt construction.
Extracted from server.py to eliminate duplication between chat() and chat_stream().
"""
import json
import time
import datetime
import zoneinfo

import anyio


# Tools auto-injected per agent type. These bypass the agent's tools[] array.
# "all_types" applies to every agent regardless of type.
DEFAULT_TOOLS_BY_TYPE = {
    "all_types": {
        "sequentialthinking",         # multi-step tool execution
        # Filesystem MCP — always available for reading repo + vault files
        "read_file",                  # read any allowed file
        "read_multiple_files",        # batch read
        "search_files",               # recursive pattern search
        "list_directory",             # directory listing
        "get_file_info",              # file metadata
        "grep",
        "glob",
    },
    "code": {
        "search_codebase",
    },
    "orchestrator": set(),  # orchestrator agents delegate to sub-agents; no extra tools needed
}


# System Prompt for Native Tool Calling (Personal Assistant)
NATIVE_TOOL_SYSTEM_PROMPT = """You are a highly capable Personal Intelligent Assistant.
Your mission is to assist the user with everyday tasks, retrieving personal information, and utilizing provided tools to make their life easier.

### CORE OPERATING RULES
1.  **Think Step-by-Step:** Before calling a tool, briefly analyze the user's request.
2.  **Accuracy First:** Never guess IDs. Always use `list_` or `search_` tools to find the real ID first.
3.  **Privacy and Security:** You are operating in a personal environment. Handle personal data with care.

### RESPONSE STYLE
*   **Friendly & Helpful:** Be conversational but concise.
*   **Action-Oriented:** If a task is done, let the user know. If data is retrieved, present it clearly.
"""


# Module-level cache of MCP session tools — populated on first successful list_tools() call.
# Avoids re-querying flaky sessions (e.g. mcp-remote after OAuth state changes) on every agent call.
_session_tools_cache: dict = {}


class VirtualTool:
    """A lightweight tool descriptor that mimics the shape of an MCP tool."""
    def __init__(self, name, description, inputSchema):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema


def build_virtual_tools():
    return []


async def aggregate_all_tools(agent_sessions, active_agent, custom_tools_list):
    """
    Aggregate all available tools: MCP tools + virtual tools + custom tools.
    
    Returns:
        tuple: (all_tools, tool_schema_map, ollama_tools, tools_json)
    """
    all_tools = []
    tool_schema_map = {}  # name -> inputSchema
    
    allowed_tools = active_agent.get("tools", ["all"])

    # Auto-inject default tools based on agent type
    agent_type = active_agent.get("type", "conversational")
    for category in ["all_types", agent_type]:
        for tool_name in DEFAULT_TOOLS_BY_TYPE.get(category, set()):
            if tool_name not in allowed_tools:
                allowed_tools.append(tool_name)
    
    # Standard MCP Tools
    for session_name, session in agent_sessions.items():
        # Use cached tools from previous successful call — avoids hanging on flaky sessions
        if session_name in _session_tools_cache:
            session_tools = _session_tools_cache[session_name]
            print(f"DEBUG: 📦 Using cached tools for '{session_name}' ({len(session_tools)} tools)", flush=True)
        else:
            try:
                # Bounded list_tools() — 15s timeout prevents a single flaky
                # session from blocking all subsequent tool aggregation.
                print(f"DEBUG: 🔄 Fetching tools for '{session_name}'...", flush=True)
                with anyio.fail_after(15):
                    result = await session.list_tools()
                session_tools = result.tools
                _session_tools_cache[session_name] = session_tools
                print(f"DEBUG: ✅ Fetched+cached tools for '{session_name}' ({len(session_tools)} tools)", flush=True)
            except TimeoutError:
                print(f"DEBUG: ⏱ Skipping session '{session_name}' — list_tools timed out after 15s", flush=True)
                continue
            except Exception as e:
                print(f"DEBUG: Skipping session '{session_name}' — list_tools failed: {e}", flush=True)
                continue

        is_external = session_name.startswith("ext_mcp_")
        server_name = session_name[len("ext_mcp_"):] if is_external else None

        if is_external:
            for t in session_tools:
                prefixed = f"{server_name}__{t.name}"
                if "all" in allowed_tools or prefixed in allowed_tools:
                    all_tools.append(VirtualTool(prefixed, t.description, t.inputSchema))
        else:
            if "all" in allowed_tools:
                all_tools.extend(session_tools)
            else:
                for t in session_tools:
                    if t.name in allowed_tools:
                        all_tools.append(t)

    # Populate schema map for MCP tools
    for t in all_tools:
        tool_schema_map[t.name] = t.inputSchema

    # Virtual infrastructure tools (filtered by agent type)
    virtual_tools = build_virtual_tools()
    for vt in virtual_tools:
        all_tools.append(vt)
        tool_schema_map[vt.name] = vt.inputSchema
    
    # Dynamic Custom Tools (n8n/Webhook)
    for ct in custom_tools_list:
        if "all" in allowed_tools or ct['name'] in allowed_tools:
            vt = VirtualTool(ct['name'], ct['description'], ct['inputSchema'])
            all_tools.append(vt)
            tool_schema_map[vt.name] = vt.inputSchema

    # Build Ollama-formatted tools list
    ollama_tools = [
        {
            'type': 'function',
            'function': {
                'name': t.name,
                'description': t.description,
                'parameters': t.inputSchema
            }
        }
        for t in all_tools
    ]
    
    # String version for cloud models (system prompt injection)
    tools_json = str([
        {'tool': t.name, 'description': t.description, 'schema': t.inputSchema}
        for t in all_tools
    ])

    # Debug: Log exactly which tools will be visible to the LLM
    tool_names_for_llm = [t.name for t in all_tools]
    print(f"DEBUG: 🔧 Tools sent to LLM ({len(tool_names_for_llm)}): {tool_names_for_llm}")

    return all_tools, tool_schema_map, ollama_tools, tools_json


def build_system_prompt(agent_system_template, tools_json, session_id, session_state_getter, memory_store, agent_id=None, turns_remaining=None, max_turns=None):
    """
    Construct the final system prompt with tool info, date/time, session context, 
    and recent tool outputs injected.
    
    Args:
        agent_system_template: The base system prompt (tools/datetime are appended automatically)
        tools_json: String representation of available tools
        session_id: Current session ID
        session_state_getter: Function that returns session state dict for a session_id
        memory_store: Memory store instance (or None)
        agent_id: Optional agent ID for scoping memory queries
    
    Returns:
        str: The fully constructed system prompt
    """
    # Get current date/time for context injection
    now = datetime.datetime.now(zoneinfo.ZoneInfo("UTC"))
    current_date = now.strftime("%B %d, %Y")
    current_time = now.strftime("%I:%M %p")
    timezone = "UTC"

    # Start with the user's system prompt as-is
    system_prompt_text = agent_system_template.strip()

    # --- INJECT GOOGLE WORKSPACE EMAIL ---
    try:
        from core.config import TOKEN_FILE
        import os
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r") as f:
                token_data = json.load(f)
                email = token_data.get("email")
                if not email and token_data.get("id_token"):
                    import base64
                    id_token = token_data["id_token"]
                    payload_b64 = id_token.split(".")[1]
                    payload_b64 += "=" * (4 - len(payload_b64) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    email = payload.get("email")
                if email:
                    system_prompt_text += f"\n\n### GOOGLE WORKSPACE CONTEXT\nYou are authenticated with Google Workspace as **{email}**. Whenever a tool requires `user_google_email` or similar, ALWAYS use {email}.\n"
    except Exception as e:
        print(f"DEBUG: Error injecting Google Workspace Email: {e}")

#     # --- TURN AWARENESS ---
#     turns_block = ""
#     if turns_remaining is not None and max_turns is not None:
#         if turns_remaining <= 0:
#             turns_block = f"""

# ### ⚠️ TURN LIMIT REACHED — FINAL RESPONSE REQUIRED
# You have used all {max_turns} available turns. You MUST stop calling tools and provide your **final answer now** based on everything gathered so far.
# - Summarize what you did and what you found.
# - If the task is incomplete, clearly state what could not be completed and why.
# - Do NOT call any more tools.
# """
#         elif turns_remaining == 1:
#             turns_block = f"""

# ### ⚠️ LAST TURN — RESPOND NOW
# This is your **final turn** (Turn {max_turns}/{max_turns}). You MUST provide your final answer now. Do NOT call any more tools.
# - If you have enough information, give the complete answer.
# - If you don't have enough information, say so clearly and summarize what you were able to find.
# - Provide a brief summary of all steps taken so far.
# """
#         else:
#             turns_block = f"""

# ### TURN BUDGET
# You have **{turns_remaining} turn(s) remaining** out of {max_turns} total.
# - Plan your tool calls efficiently — prioritize the most impactful steps first.
# - If you cannot complete the task within the remaining turns, provide a partial answer and summarize what was accomplished so far.
# - On the last turn you MUST answer in plain text (no tool calls), even if the task is not fully complete.
# """

    # Append tools, date/time, and instructions at the end
    system_prompt_text += f"""

### CURRENT DATE & TIME CONTEXT
**Current Date:** {current_date}
**Current Time:** {current_time}
**Timezone:** {timezone}

**IMPORTANT:** When tools return dates or timestamps, DO NOT add your own temporal context. Simply present the date/time returned by the tool. If you need to calculate relative time, use the appropriate tool or state the exact difference in days/weeks/months by doing simple math with the current date above.

### TOOLS
You have access to the following tools:
{tools_json}

**CODE & FILE NAVIGATION — EFFICIENCY FIRST:**
When exploring or reading code/files, always reason: *"Can I find this with a search instead of reading the whole file?"* Follow this strict priority order:
1. **`search_codebase` / `grep`** — use these first to locate symbols, patterns, function definitions, imports, or any text across files. This is almost always faster and more targeted than opening files.
2. **`glob`** — use to discover file paths by pattern (e.g. `**/*.py`, `src/**/*.ts`) before reading any file.
3. **Read / open a file** — only after you have identified the exact file and approximate line range via search. Read only the relevant slice, not the entire file.
4. **Any other tool** — only when search/glob/read are genuinely insufficient.

**Never read a file in full when you can grep for the specific symbol or section you need.** If you find yourself about to read more than one file without first searching, stop and use `search_codebase` or `grep` instead. This is the most efficient path and minimizes unnecessary context.

**SEQUENTIALTHINKING (OPTIONAL — USE SPARINGLY):**
`sequentialthinking` is a lightweight planning aid. If the request is complex, you MAY call it to outline your plan or refine your thinking — up to **5 times** per task. After each call you MUST make progress with real action tools (browser, search, data tool, etc.). Never call `sequentialthinking` more than 5 times per task, and never call it in place of a real tool — it cannot fetch data, browse the web, or do anything productive by itself.

### LINKS & REFERENCES
Whenever a tool returns URLs, source links, documentation references, or any other hyperlinks — **always include them in your response**. Present them clearly so the user can visit them directly. If you know of relevant official documentation, articles, or resources that would help the user, proactively include those links even if not explicitly returned by a tool.

### RESPONSE FORMAT INSTRUCTIONS
If you need to use a specific tool from the list above, you MUST respond with **ONLY** a valid JSON object in the following format:
{{ "tool": "tool_name", "arguments": {{ "key": "value" }} }}

Do NOT output any other text or markdown when calling a tool.
If you do not need to use a tool, reply in plain text.
"""

    # system_prompt_text += turns_block
    
    # --- DYNAMIC RAG INJECTION ---
    # If we have active embeddings, force the LLM to know about them
    try:
        ss = session_state_getter(session_id)
        last_report = ss.get("last_report_context")
        if last_report and (time.time() - last_report.get("timestamp", 0) < 600):  # 10 mins validity
            rag_context_msg = f"""
### ACTIVE RAG CONTEXT (AUTOMATICALLY INJECTED)
You have {last_report.get('row_count', 'some')} items of '{last_report.get('type', 'data')}' embedded in memory (generated {int(time.time() - last_report.get('timestamp', 0))}s ago).

**HOW TO ANSWER QUESTIONS ABOUT THIS DATA:**
1. **AGGREGATION QUESTIONS** (totals, averages, counts, min/max): If a SUMMARY with `numeric_aggregations` is in the tool output above, use those pre-computed values directly. They are accurate.
2. **SPECIFIC LOOKUPS** (e.g., "email from John", "meeting tomorrow", "flight details"): Call `search_embedded_report` with a descriptive query. The full data is embedded in RAG memory.
3. **PATTERN/TREND QUESTIONS** (e.g., "frequent topics", "common contacts"): Call `search_embedded_report` with the pattern description.
4. **DO NOT RE-RUN TOOL FOR EXISTING DATA:** The data is already here. Only call tools if the user explicitly asks for NEW/DIFFERENT data (e.g., "refresh", "different date", "different query").
"""
            system_prompt_text += rag_context_msg
            print(f"DEBUG: 💉 Injected RAG context into system prompt")
    except Exception as e:
        print(f"DEBUG: Error injecting RAG prompt: {e}")
    
    return system_prompt_text
