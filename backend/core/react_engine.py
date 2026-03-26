"""
Shared ReAct loop engine used by both /chat and /chat/stream endpoints.
Yields structured event dicts that callers can handle differently
(collect for sync response, or stream as SSE).
"""
import json
import sys
import time

import httpx

from core.config import load_settings
from core.vault import maybe_vault
from core.session import (
    _get_session_id, _get_session_state,
    _apply_sticky_args, _clear_session_embeddings,
    get_recent_history_messages, _get_conversation_history,
)
from core.llm_providers import generate_response as llm_generate_response
from core.tools import aggregate_all_tools, build_system_prompt, DEFAULT_TOOLS_BY_TYPE
from core.routes.agents import load_user_agents, get_active_agent_data, active_agent_id
from core.routes.tools import load_custom_tools

import anyio as _anyio
from datetime import timedelta

MAX_TURNS = 30
REPORT_CHUNK_SIZE = 50
REPORT_SIZE_THRESHOLD = 30000


def parse_tool_call(llm_output: str) -> tuple[dict | None, str | None]:
    """Extract a tool call JSON from LLM text output."""
    cleaned = llm_output.replace("```json", "").replace("```", "").strip()

    if "{" not in cleaned:
        return None, None

    first_brace = cleaned.find("{")
    if first_brace > 20:
        return None, None

    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict) and ("tool" in obj or "name" in obj):
            return obj, None
    except json.JSONDecodeError:
        pass

    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned[first_brace:])
        if isinstance(obj, dict) and ("tool" in obj or "name" in obj):
            return obj, None
    except json.JSONDecodeError:
        pass

    if first_brace == 0:
        return None, "Output starts with '{' but is not a valid tool call JSON"

    return None, None



def _store_tool_in_memory(memory_store, session_id, tool_name, tool_args, raw_output, agent_id):
    """Helper to store a tool execution in memory (non-fatal on error)."""
    if not memory_store:
        return
    try:
        memory_store.add_tool_execution(
            session_id=session_id,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_output=raw_output,
            agent_id=agent_id,
        )
    except Exception as e:
        print(f"DEBUG: Error storing tool execution in memory: {e}")


def _handle_report_auto_embed(memory_store, session_id, raw_output, target_tool, tool_name):
    """Auto-embed report data via RAG and return context-safe output."""
    try:
        parsed_output = json.loads(raw_output)
        if not isinstance(parsed_output, list):
            return raw_output

        context_safe_reports = []
        for idx, report_obj in enumerate(parsed_output):
            if not (isinstance(report_obj, dict) and "data" in report_obj):
                context_safe_reports.append(report_obj)
                continue
            if report_obj.get("is_file"):
                context_safe_reports.append(report_obj)
                continue

            report_type = report_obj.get("report", "unknown")
            report_data = report_obj.get("data", [])

            embed_result = memory_store.embed_report_for_session(
                session_id=session_id,
                report_data=report_data,
                report_type=report_type,
                chunk_size=REPORT_CHUNK_SIZE,
            )
            chunks_count = embed_result.get("chunks_embedded", 0)
            print(f"DEBUG: Embedded {chunks_count} chunks for '{report_type}'")

            # Update session state with report context
            try:
                from core.session import _get_session_state
                ss = _get_session_state(session_id)
                ss["last_report_context"] = {
                    "timestamp": time.time(),
                    "type": report_type,
                    "row_count": len(report_data),
                }
            except Exception as e:
                print(f"DEBUG: Error saving report context: {e}")

            report_json_size = len(json.dumps(report_obj))
            if report_json_size > REPORT_SIZE_THRESHOLD:
                summary = memory_store.generate_report_summary(report_data, report_type)
                context_safe_reports.append(summary)
            else:
                context_safe_reports.append(report_obj)

        return json.dumps(context_safe_reports)
    except Exception as e:
        print(f"DEBUG: Error auto-embedding report: {e}")
        import traceback
        traceback.print_exc()
        return raw_output


def _resolve_agent_by_id(agent_id):
    """Load an agent dict by ID, with fallback to active agent."""
    if agent_id:
        agents = load_user_agents()
        agent = next((a for a in agents if a["id"] == agent_id), None)
        if agent:
            return agent
    return get_active_agent_data()


def _inject_db_context(agent_data, system_template):
    """Inject linked DB schema context into system prompt for code agents. Returns updated template."""
    if agent_data.get("type") != "code":
        return system_template
    db_configs_list = agent_data.get("db_configs", [])
    if not db_configs_list:
        return system_template
    try:
        from core.routes.db_configs import load_db_configs
        all_configs = load_db_configs()
        linked_configs = [c for c in all_configs if c.get("id") in db_configs_list]
        if not linked_configs:
            return system_template

        allow_db_write = load_settings().get("allow_db_write", False)

        db_context = (
            "\n\n### LINKED DATABASES ###\n"
            "The following databases are associated with this codebase. "
            "When calling `list_tables`, `get_table_schema`, or `run_sql_query`, "
            "you MUST pass the `db_id` field matching the database you want to query.\n\n"
        )
        for c in linked_configs:
            db_context += f"**DB Name:** {c.get('name')}\n"
            db_context += f"**DB ID:** `{c.get('id')}`  ← pass this as db_id in SQL tool calls\n"
            db_context += f"**Type:** {c.get('db_type')}\n"
            if c.get("description"):
                db_context += f"**Description:** {c.get('description')}\n"
            if c.get("schema_info"):
                db_context += f"**Schema:**\n{c.get('schema_info')}\n"
            db_context += "---\n"

        if allow_db_write:
            db_context += (
                "\n**DB WRITE RULES (MANDATORY):**\n"
                "- Write queries (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, etc.) ARE permitted.\n"
                "- You MUST explicitly state the exact query you intend to run and ask the user for confirmation BEFORE calling `run_sql_query` with any write query.\n"
                "- Never assume consent. Even for seemingly safe updates, always confirm first.\n"
            )
        else:
            db_context += (
                "\n**DB READ-ONLY MODE (MANDATORY):**\n"
                "- You are STRICTLY limited to SELECT, SHOW, and DESCRIBE queries.\n"
                "- NEVER attempt INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or any other write operation.\n"
                "- If the user asks you to modify data, inform them that DB write access is disabled in General Settings.\n"
            )

        return system_template + db_context
    except Exception as e:
        print(f"DEBUG: Failed to load db context: {e}")
        return system_template


def _inject_repo_context(agent_data, system_template):
    """Inject repo context into system prompt for code agents. Returns updated template."""
    if agent_data.get("type") != "code":
        return system_template
    repos_list = agent_data.get("repos", [])
    if not repos_list:
        return system_template
    try:
        from core.routes.repos import load_repos
        all_repos = load_repos()
        linked_repos = [r for r in all_repos if r.get("id") in repos_list]
        repo_context = (
            "\n\n### LINKED CODE REPOSITORIES ###\n"
            "You have access to search the following indexed code repositories "
            "using the `search_codebase` tool. When searching, you MUST provide "
            "the specific `repo_id` (from the list below) that you wish to search, "
            "along with your natural language query.\n\n"
        )
        for r in linked_repos:
            repo_context += f"**Repo Name:** {r.get('name')}\n"
            repo_context += f"**Repo ID:** {r.get('id')}\n"
            if r.get("description"):
                repo_context += f"**Description & Interconnections:** {r.get('description')}\n"
            repo_context += "---\n"
        return system_template + repo_context
    except Exception as e:
        print(f"DEBUG: Failed to load repo context: {e}")
        return system_template


async def run_agent_step(
    message,
    agent_id,
    session_id,
    server_module,
    max_turns=None,
    allowed_tools_override=None,
):
    """Lower-level single-agent ReAct execution.

    Used by both run_react_loop (chat) and the orchestration engine (per-step).
    Yields the same structured events as run_react_loop.
    """
    from core.tools import NATIVE_TOOL_SYSTEM_PROMPT

    if max_turns is None:
        max_turns = MAX_TURNS

    # Resolve agent
    active_agent = _resolve_agent_by_id(agent_id)
    agent_id_for_session = active_agent.get("id", agent_id or "default")

    # Build system prompt with repo and DB context injection
    agent_system_template = active_agent.get("system_prompt", NATIVE_TOOL_SYSTEM_PROMPT)
    agent_system_template = _inject_repo_context(active_agent, agent_system_template)
    agent_system_template = _inject_db_context(active_agent, agent_system_template)

    # Aggregate tools & build system prompt
    custom_tools = load_custom_tools()
    print(f"DEBUG RUN_AGENT: start agent_id={agent_id_for_session}, sessions={list(server_module.agent_sessions.keys())}", flush=True)
    all_tools, tool_schema_map, ollama_tools, tools_json = await aggregate_all_tools(
        server_module.agent_sessions, active_agent, custom_tools
    )
    print(f"DEBUG RUN_AGENT: aggregate_all_tools done, tool_count={len(all_tools)}", flush=True)
    allowed_tools = list(allowed_tools_override) if allowed_tools_override else active_agent.get("tools", ["all"])

    system_prompt_text = build_system_prompt(
        agent_system_template, tools_json, session_id,
        _get_session_state, server_module.memory_store, agent_id=agent_id_for_session,
    )

    current_settings = load_settings()
    # Per-agent model override: use agent's model if set, else fall back to default
    agent_model = active_agent.get("model")
    current_model = agent_model if agent_model else current_settings.get("model", "mistral")
    # Auto-detect mode from model name instead of relying on global mode
    from core.llm_providers import detect_mode_from_model
    mode = detect_mode_from_model(current_model)

    async def generate_response(prompt_msg, sys_prompt, tools=None, history_messages=None, memory_context_text=""):
        return await llm_generate_response(
            prompt_msg=prompt_msg,
            sys_prompt=sys_prompt,
            mode=mode,
            current_model=current_model,
            current_settings=current_settings,
            tools=tools,
            history_messages=history_messages,
            memory_context_text=memory_context_text,
        )

    # ReAct loop state
    user_message = message
    memory_context = ""
    recent_history_messages = get_recent_history_messages(session_id, agent_id=agent_id_for_session)
    current_context_text = f"User Request: {user_message}\n"
    final_response = ""
    last_intent = "chat"
    last_data = None
    tool_name = None
    tools_used_summary = []
    tool_repetition_counts = {}

    # Build type-aware set of always-allowed tools
    agent_type = active_agent.get("type", "conversational")
    always_allowed = set(DEFAULT_TOOLS_BY_TYPE.get("all_types", set()))
    always_allowed |= set(DEFAULT_TOOLS_BY_TYPE.get(agent_type, set()))

    MAX_PROMPT_CHARS = 400000
    MAX_TOOL_OUTPUT_CHARS = 8000  # Per-tool output limit for context

    # Browser tools produce DOM snapshots that are only useful for the current turn.
    # Previous snapshots become stale the moment the page changes, so we skip
    # appending them to the accumulated context and only keep a short summary.
    BROWSER_TOOL_PREFIXES = ("browser_",)

    def _truncate_tool_output(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
        """Truncate tool output to prevent context bloat."""
        if len(text) <= limit:
            return text
        return text[:limit] + f"...(truncated {len(text) - limit} chars)"

    def _is_browser_tool(name: str) -> bool:
        return name.startswith(BROWSER_TOOL_PREFIXES)

    async with httpx.AsyncClient() as client:
        for turn in range(max_turns):
            print(f"\n{'#'*60}\n### TURN {turn + 1}/{max_turns} ###\n{'#'*60}\n")

            yield {"type": "thinking", "message": "Analyzing your request..."}

            # Determine prompt
            if turn == 0:
                active_sys_prompt = system_prompt_text
                active_prompt = user_message
                active_history = recent_history_messages
            else:
                active_sys_prompt = system_prompt_text
                active_prompt = current_context_text
                active_history = []

            # Safety guard: truncate if too long
            total_prompt_chars = len(active_prompt) + len(active_sys_prompt) + len(memory_context)
            print(f"DEBUG: 📊 Context size — prompt: {len(active_prompt)} | system: {len(active_sys_prompt)} | memory: {len(memory_context)} | total: {total_prompt_chars} chars")
            if total_prompt_chars > MAX_PROMPT_CHARS:
                overflow = total_prompt_chars - MAX_PROMPT_CHARS
                active_prompt = active_prompt[: len(active_prompt) - overflow]
                print(f"DEBUG: ⚠️ Truncated prompt by {overflow} chars")

            # Ask LLM
            print(f"DEBUG: 🔄 Calling LLM...", flush=True)
            _llm_start = time.time()
            try:
                llm_output = await generate_response(
                    active_prompt, active_sys_prompt,
                    tools=ollama_tools, history_messages=active_history,
                    memory_context_text=memory_context,
                )
            except Exception as llm_err:
                _llm_duration = round(time.time() - _llm_start, 1)
                error_msg = f"LLM Error ({_llm_duration}s): {llm_err}"
                print(f"DEBUG: ❌ {error_msg}", flush=True)
                final_response = str(llm_err)
                yield {"type": "error", "message": str(llm_err)}
                break
            _llm_duration = round(time.time() - _llm_start, 1)
            print(f"DEBUG: 🤖 LLM Response ({_llm_duration}s): {llm_output[:500]}{'...(truncated)' if len(llm_output) > 500 else ''}")

            # Parse tool call
            tool_call, json_error = parse_tool_call(llm_output)

            if json_error:
                current_context_text += f"\nSystem: JSON Parsing Error: {json_error}. Please Try Again with valid JSON.\n"
                continue

            if tool_call is None:
                final_response = llm_output
                break

            if tool_call and isinstance(tool_call, dict):
                tool_name = tool_call.get("tool") or tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                # Apply sticky args
                tool_schema = tool_schema_map.get(tool_name)
                tool_args = _apply_sticky_args(session_id, tool_name, tool_args, tool_schema)

                yield {"type": "tool_execution", "tool_name": tool_name, "args": tool_args}
                print(f"DEBUG: 🔧 Tool Call: {tool_name}")
                print(f"DEBUG: 📥 Args: {json.dumps(tool_args, indent=2, default=str)[:1000]}")

                # Loop guard
                current_tool_signature = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                tool_repetition_counts[current_tool_signature] = tool_repetition_counts.get(current_tool_signature, 0) + 1
                _rep_count = tool_repetition_counts[current_tool_signature]
                if _rep_count > 3:
                    _loop_msg = f"Tool '{tool_name}' has been called {_rep_count} times with identical arguments and will not execute again. You are stuck in a loop. Stop calling this tool and synthesize the results you already have."
                    print(f"DEBUG: 🔁 Loop guard fired for '{tool_name}' (called {_rep_count}x with same args — blocked)", flush=True)
                    current_context_text += f"\nSystem: {_loop_msg}\n"
                    yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Blocked: called {_rep_count}x with same args (loop guard)"}
                    continue

                # Execution guard
                if "all" not in allowed_tools and tool_name not in allowed_tools and tool_name not in always_allowed:
                    block_msg = f"Tool '{tool_name}' is not available for this agent. Available tools: {', '.join(allowed_tools)}."
                    current_context_text += f"\nSystem: {block_msg}\n"
                    yield {"type": "tool_result", "tool_name": tool_name, "preview": "Blocked: Tool not available for this agent"}
                    continue

                # ===== INTERNAL TOOLS =====

                if tool_name == "decide_search_or_analyze":
                    try:
                        user_query = tool_args.get("user_query", "").lower()
                        report_size = tool_args.get("report_size", 0)
                        if not isinstance(report_size, int):
                            report_size = 0
                        search_keywords = ["pattern", "trend", "concern", "similar", "unusual", "most", "least", "compare", "correlation"]
                        use_search = any(kw in user_query for kw in search_keywords) or report_size > 200
                        result = {
                            "use_search": use_search,
                            "approach": "search_embedded_report" if use_search else "direct_analysis",
                            "reason": "Exploratory/correlation query detected" if use_search else "Specific query - direct analysis sufficient",
                        }
                        raw_output = json.dumps(result)
                        print(f"DEBUG: 📤 Tool Result ({tool_name}): {raw_output}")
                        current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                        tools_used_summary.append(f"{tool_name}: use_search={use_search}")
                        _store_tool_in_memory(server_module.memory_store, session_id, tool_name, tool_args, raw_output, agent_id_for_session)
                        yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Decision: {result['approach']}"}
                        last_intent = "query_decision"
                        last_data = result
                    except Exception as e:
                        raw_output = json.dumps({"error": str(e)})
                        current_context_text += f"\nTool '{tool_name}' Error: {raw_output}\n"
                    continue

                if tool_name == "embed_report_for_exploration":
                    try:
                        if not isinstance(tool_args, dict):
                            raise ValueError("tool_args must be a dict")
                        report_obj = tool_args.get("report_data")
                        if not report_obj or not isinstance(report_obj, dict):
                            raise ValueError("report_data must be a dict")
                        report_type = report_obj.get("report_type", "unknown")
                        report_data = report_obj.get("sample_data" if report_obj.get("is_chunked") else "data", [])
                        if not report_data:
                            raise ValueError("No data found in report")
                        result = server_module.memory_store.embed_report_for_session(
                            session_id=session_id, report_data=report_data,
                            report_type=report_type, chunk_size=REPORT_CHUNK_SIZE,
                        )
                        raw_output = json.dumps(result)
                        print(f"DEBUG: 📤 Tool Result ({tool_name}): {raw_output}")
                        current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                        tools_used_summary.append(f"{tool_name}: Embedded {result.get('chunks_embedded', 0)} chunks")
                        yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Embedded {result.get('chunks_embedded', 0)} chunks"}
                        last_intent = "embed_report"
                        last_data = result
                    except Exception as e:
                        raw_output = json.dumps({"error": str(e)})
                        current_context_text += f"\nTool '{tool_name}' Error: {raw_output}\n"
                    continue

                if tool_name == "search_embedded_report":
                    try:
                        if not isinstance(tool_args, dict):
                            raise ValueError("tool_args must be a dict")
                        query = tool_args.get("query", "").strip()
                        if not query:
                            raise ValueError("query parameter is required")
                        n_results = tool_args.get("n_results", 3)
                        if not isinstance(n_results, int):
                            n_results = 3
                        results = server_module.memory_store.search_embedded_report(
                            session_id=session_id, query=query, n_results=n_results,
                        )
                        results_list = results.get("results", [])
                        result = {"query": query, "results_found": len(results_list), "chunks": results_list}
                        raw_output = json.dumps(result, default=str)
                        print(f"DEBUG: 📤 Tool Result ({tool_name}): {raw_output[:500]}{'...(truncated)' if len(raw_output) > 500 else ''}")
                        current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                        tools_used_summary.append(f"{tool_name}('{query}'): Found {len(results_list)} chunks")
                        yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Found {len(results_list)} relevant chunks"}
                        last_intent = "search_embeddings"
                        last_data = result
                    except Exception as e:
                        raw_output = json.dumps({"error": str(e)})
                        current_context_text += f"\nTool '{tool_name}' Error: {raw_output}\n"
                    continue

                if tool_name == "query_past_conversations":
                    try:
                        query = ""
                        if isinstance(tool_args, dict):
                            query = str(tool_args.get("query") or "").strip()
                        n_results = 5
                        scope = "all"
                        if isinstance(tool_args, dict):
                            if tool_args.get("n_results") is not None:
                                try:
                                    n_results = int(tool_args["n_results"])
                                except Exception:
                                    n_results = 5
                            if tool_args.get("scope") in ("all", "session"):
                                scope = tool_args["scope"]

                        if not query:
                            raw_output = json.dumps({"memories": [], "error": "missing_query"})
                            current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                            tools_used_summary.append(f"{tool_name}: {raw_output}")
                            last_intent = "memory_query"
                            last_data = {"memories": [], "error": "missing_query"}
                            continue

                        if not server_module.memory_store:
                            raw_output = json.dumps({"memories": [], "error": "memory_disabled"})
                            current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                            tools_used_summary.append(f"{tool_name}: {raw_output}")
                            last_intent = "memory_query"
                            last_data = {"memories": [], "error": "memory_disabled"}
                            continue

                        where = {"session_id": session_id} if scope == "session" else None
                        memories = server_module.memory_store.query_memory(query, n_results=n_results, where=where)
                        raw_output = json.dumps({"memories": memories, "scope": scope})
                        print(f"DEBUG: 📤 Tool Result ({tool_name}): {raw_output[:500]}{'...(truncated)' if len(raw_output) > 500 else ''}")
                        current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                        tools_used_summary.append(f"{tool_name}: {raw_output[:500]}...")
                        yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Found {len(memories)} memories"}
                        last_intent = "memory_query"
                        last_data = {"memories": memories, "scope": scope}
                        continue
                    except Exception as e:
                        current_context_text += f"\nSystem: Error executing internal tool {tool_name}: {str(e)}\n"
                        continue

                # ===== CUSTOM TOOLS (Webhook) =====

                if tool_name not in server_module.tool_router:
                    custom_tools_list = load_custom_tools()
                    target_tool = next((t for t in custom_tools_list if t["name"] == tool_name), None)

                    # Report throttling
                    if target_tool and target_tool.get("tool_type") == "report":
                        try:
                            ss = _get_session_state(session_id)
                            last_report = ss.get("last_report_context")
                            if last_report and (time.time() - last_report.get("timestamp", 0) < 300):
                                cached_msg = {
                                    "status": "skipped",
                                    "message": f"REPORT ALREADY GENERATED ({int(time.time() - last_report.get('timestamp', 0))}s ago). Data is already in context. Use 'search_embedded_report' for patterns.",
                                }
                                raw_output = json.dumps(cached_msg)
                                current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                                yield {"type": "tool_result", "tool_name": tool_name, "preview": "Skipped (Data already in context)"}
                                continue
                        except Exception as e:
                            print(f"DEBUG: Error in report throttling: {e}")

                    if target_tool:
                        try:
                            method = target_tool.get("method", "POST")
                            url = target_tool.get("url")
                            headers = target_tool.get("headers", {})
                            if not url:
                                raise ValueError("No URL configured for this tool.")

                            resp = await client.request(method, url, json=tool_args, headers=headers, timeout=30.0)

                            json_resp = None
                            try:
                                json_resp = resp.json()
                                output_schema = target_tool.get("outputSchema", {})
                                if output_schema and "properties" in output_schema and isinstance(json_resp, dict):
                                    filtered = {k: json_resp[k] for k in output_schema["properties"] if k in json_resp}
                                    if filtered:
                                        json_resp = filtered
                                raw_output = json.dumps(json_resp)
                            except Exception:
                                raw_output = resp.text or json.dumps({"error": f"Empty response (Status: {resp.status_code})"})

                            # Smart report embedding
                            if server_module.memory_store:
                                try:
                                    if target_tool.get("tool_type") == "report":
                                        raw_output = _handle_report_auto_embed(
                                            server_module.memory_store, session_id, raw_output, target_tool, tool_name,
                                        )
                                    else:
                                        _store_tool_in_memory(server_module.memory_store, session_id, tool_name, tool_args, raw_output, agent_id_for_session)
                                except Exception as e:
                                    print(f"DEBUG: Error storing custom tool in memory: {e}")

                            # Vault large outputs
                            raw_output = maybe_vault(tool_name, raw_output)

                            current_context_text += f"\nTool '{tool_name}' Output: {_truncate_tool_output(raw_output)}\n"
                            tools_used_summary.append(f"{tool_name}: {raw_output[:500]}...")
                            print(f"DEBUG: 📤 Tool Result ({tool_name}): {raw_output[:500]}{'...(truncated)' if len(raw_output) > 500 else ''}")
                            preview = raw_output[:100] + "..." if len(raw_output) > 100 else raw_output
                            yield {"type": "tool_result", "tool_name": tool_name, "preview": preview}

                            last_intent = "custom_tool"
                            last_data = json_resp if json_resp is not None else {"output": raw_output}
                            continue
                        except Exception as e:
                            current_context_text += f"\nSystem: Error executing custom tool {tool_name}: {str(e)}\n"
                            continue

                    # Hallucinated / unknown tool
                    available_tool_names = [t.name for t in all_tools]
                    names_str = ", ".join(available_tool_names[:30])
                    if len(available_tool_names) > 30:
                        names_str += f" ... ({len(available_tool_names)} total)"
                    print(f"DEBUG: ❓ Tool '{tool_name}' not found in any registered source (hallucinated or unregistered)", flush=True)
                    current_context_text += (
                        f"\nSystem: Tool '{tool_name}' does not exist and cannot be called. "
                        f"Do not attempt to call it again. "
                        f"Available tools: {names_str}. "
                        f"Use one of these tools, or respond with plain text if no tool is needed.\n"
                    )
                    yield {"type": "tool_result", "tool_name": tool_name, "preview": "Error: tool not found"}
                    continue

                # ===== MCP TOOLS =====

                agent_name = server_module.tool_router[tool_name]
                session = server_module.agent_sessions[agent_name]

                try:
                    # Force event-loop checkpoint before MCP operations.
                    # The MCP stdio transport uses 0-buffer memory streams
                    # (rendezvous channels) — background tasks (_receive_loop,
                    # stdout_reader, stdin_writer) need event-loop ticks to
                    # drain pending data.  In orchestration mode the deeply
                    # nested async-generator chain can starve these tasks.
                    # An explicit checkpoint here ensures they get a turn
                    # before we send a new request.
                    await _anyio.sleep(0)

                    _mcp_t0 = time.time()
                    print(f"DEBUG MCP: ▶ session='{agent_name}' tool='{tool_name}' — ping starting", flush=True)

                    # Health check: ping the session before committing to a blocking
                    # call_tool().
                    try:
                        with _anyio.fail_after(5):
                            await session.send_ping()
                    except (TimeoutError, Exception) as _ping_err:
                        _ping_msg = f"MCP session '{agent_name}' unresponsive (ping: {_ping_err}). Skipping '{tool_name}'."
                        print(f"DEBUG MCP: ⚠️ {_ping_msg} [{round(time.time()-_mcp_t0,2)}s]", flush=True)
                        current_context_text += f"\nSystem: Error — {_ping_msg}\n"
                        yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Error: session unresponsive"}
                        continue

                    print(f"DEBUG MCP: ✓ ping OK [{round(time.time()-_mcp_t0,2)}s] — call_tool starting", flush=True)

                    _timeout = timedelta(seconds=45) if tool_name.startswith("browser_") else timedelta(seconds=30)

                    # Checkpoint again right before the actual call_tool —
                    # gives background transport tasks one more scheduling
                    # opportunity after the ping round-trip.
                    await _anyio.sleep(0)

                    with _anyio.fail_after(_timeout.total_seconds() + 5):
                        result = await session.call_tool(tool_name, tool_args, read_timeout_seconds=_timeout)
                        raw_output = result.content[0].text

                    print(f"DEBUG MCP: ✓ call_tool OK [{round(time.time()-_mcp_t0,2)}s] tool='{tool_name}'", flush=True)

                    # Vault large outputs before any further processing
                    raw_output = maybe_vault(tool_name, raw_output)

                    try:
                        parsed = json.loads(raw_output)
                        if "error" in parsed and parsed["error"] == "auth_required":
                            yield {"type": "final", "response": "Authentication required.", "intent": "request_auth", "data": parsed, "tool_name": tool_name}
                            return

                        # Set intent for frontend UI rendering.
                        # Map MCP tool names to the intents the frontend expects.
                        TOOL_INTENT_MAP = {
                            "list_gmail_messages": "list_emails",
                            "search_gmail_messages": "list_emails",
                            "get_message": "read_email",
                            "list_drive_files": "list_files",
                            "get_drive_file": "read_file",
                            "list_calendar_events": "list_events",
                            "create_calendar_event": "create_event",
                            "list_directory": "list_local_files",
                        }
                        intent = TOOL_INTENT_MAP.get(tool_name, tool_name)
                        if intent.startswith(("list_", "read_", "create_")):
                            last_intent = intent
                            last_data = parsed
                        if tool_name == "collect_data":
                            last_intent = "collect_data"
                            last_data = parsed
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass

                    if _is_browser_tool(tool_name):
                        # Browser snapshots go stale on every navigation/click.
                        # Replace previous browser block with only the latest result.
                        BROWSER_MARKER = "\n<<BROWSER_STATE>>\n"
                        BROWSER_END = "\n<</BROWSER_STATE>>\n"
                        # Remove previous browser block if present
                        bstart = current_context_text.find(BROWSER_MARKER)
                        if bstart != -1:
                            bend = current_context_text.find(BROWSER_END, bstart)
                            if bend != -1:
                                current_context_text = current_context_text[:bstart] + current_context_text[bend + len(BROWSER_END):]
                        # Append latest browser result (truncated)
                        brief = _truncate_tool_output(raw_output, 5000)
                        current_context_text += f"{BROWSER_MARKER}Tool '{tool_name}' Output: {brief}{BROWSER_END}"
                        print(f"DEBUG: 📤 Tool Result ({tool_name}): [browser, {len(raw_output)} chars → {len(brief)} in context]")
                    else:
                        display_output = _truncate_tool_output(raw_output)
                        current_context_text += f"\nTool '{tool_name}' Output: {display_output}\n"
                        print(f"DEBUG: 📤 Tool Result ({tool_name}): {display_output[:500]}{'...(truncated)' if len(display_output) > 500 else ''}")

                    _store_tool_in_memory(server_module.memory_store, session_id, tool_name, tool_args, raw_output, agent_id_for_session)
                    preview = raw_output[:100] + "..." if len(raw_output) > 100 else raw_output
                    yield {"type": "tool_result", "tool_name": tool_name, "preview": preview}
                    tools_used_summary.append(f"{tool_name}: {raw_output[:200]}...")
                except Exception as e:
                    error_msg = str(e)
                    print(f"DEBUG: ❌ Tool '{tool_name}' failed: {error_msg}", flush=True)
                    current_context_text += f"\nSystem: Error executing tool {tool_name}: {error_msg}\n"
                    yield {"type": "tool_result", "tool_name": tool_name, "preview": f"Error: {error_msg}"}

            else:
                # No tool call, final answer
                final_response = llm_output
                break

    if not final_response:
        final_response = "I completed the requested actions."

    # Save to memory
    if server_module.memory_store and final_response:
        try:
            server_module.memory_store.add_memory("user", user_message, metadata={"session_id": session_id, "agent_id": agent_id_for_session})
            server_module.memory_store.add_memory("assistant", final_response, metadata={"session_id": session_id, "agent_id": agent_id_for_session})
        except Exception as mem_err:
            print(f"WARNING: Memory save failed (non-fatal): {mem_err}")

    # Save to short-term history
    _get_conversation_history(session_id, agent_id=agent_id_for_session).append({
        "user": user_message,
        "assistant": final_response,
        "tools": tools_used_summary,
    })

    yield {"type": "final", "response": final_response, "intent": last_intent, "data": last_data, "tool_name": tool_name}


async def run_react_loop(request, server_module):
    """Async generator that runs the ReAct loop and yields structured events.

    This is the top-level entry point called by /chat and /chat/stream.
    It resolves the active agent, checks for orchestrator type, and delegates
    to either the orchestration engine or run_agent_step().

    Event types:
        {"type": "status", "message": str}
        {"type": "thinking", "message": str}
        {"type": "tool_execution", "tool_name": str, "args": dict}
        {"type": "tool_result", "tool_name": str, "preview": str}
        {"type": "final", "response": str, "intent": str, "data": Any, "tool_name": str|None}
        {"type": "error", "message": str}
    """
    if not server_module.agent_sessions:
        yield {"type": "error", "message": "No agents connected"}
        return

    session_id = _get_session_id(request)
    user_message = request.message

    # Merge client state
    ss = _get_session_state(session_id)
    if request.client_state and isinstance(request.client_state, dict):
        for key, value in request.client_state.items():
            if value:
                ss[key] = str(value)

    yield {"type": "status", "message": "Processing your request..."}

    # Resolve active agent
    active_agent = _resolve_agent_by_id(request.agent_id)

    # --- Orchestrator delegation ---
    if active_agent.get("type") == "orchestrator":
        orch_id = active_agent.get("orchestration_id")
        if orch_id:
            try:
                from core.routes.orchestrations import load_orchestrations
                from core.models_orchestration import Orchestration
                from core.orchestration.engine import OrchestrationEngine

                orchs = load_orchestrations()
                orch_data = next((o for o in orchs if o["id"] == orch_id), None)
                if orch_data:
                    orch = Orchestration.model_validate(orch_data)
                    engine = OrchestrationEngine(orch, server_module)
                    run_id = f"run_{orch_id}_{int(time.time() * 1000)}"
                    async for event in engine.run(user_message, run_id):
                        yield event
                    return
                else:
                    yield {"type": "error", "message": f"Orchestration '{orch_id}' not found"}
                    return
            except Exception as e:
                yield {"type": "error", "message": f"Orchestration error: {e}"}
                return
        else:
            yield {"type": "error", "message": "Orchestrator agent has no orchestration_id configured"}
            return

    # --- Standard single-agent ReAct loop ---
    from core.agent_logger import AgentLogger
    _agent_log = AgentLogger(
        agent_id=active_agent.get("id", "default"),
        agent_name=active_agent.get("name", "Unknown Agent"),
        session_id=session_id,
        source="chat",
        user_message=user_message,
    )
    _log_status = "completed"
    try:
        async for event in run_agent_step(
            message=user_message,
            agent_id=active_agent.get("id"),
            session_id=session_id,
            server_module=server_module,
        ):
            _agent_log.log_event(event)
            yield event
    except Exception:
        _log_status = "error"
        raise
    finally:
        _agent_log.run_end(_log_status)
