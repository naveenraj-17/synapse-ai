# Synapse AI — A Multi-Agent Orchestrator

*A tool becomes an agent. An agent becomes a pipeline.*
*A pipeline becomes whatever you were too busy to build.*

**Build AI agents that actually do things.** Synapse is an open-source platform for creating, connecting, and orchestrating AI agents powered by any LLM — local or cloud. Agents use real tools: browsing the web, querying databases, executing code, reading files, managing emails, trading stocks, and anything else you can expose through an MCP server, a webhook, or a Python script — if you can write it, agents can use it.

---

## Install

### Quick Setup Script (recommended)
The easiest way to get started is to run the automated setup script. This will clone the repository, install all necessary dependencies, verify your environment, and start both the backend and frontend servers.

**macOS / Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/naveenraj-17/synapse-ai/main/setup.ps1 | iex
```

---

## CLI

Once installed, use the `synapse` command to manage the server:

```bash
synapse start     # start backend + frontend, open browser
synapse stop      # stop background processes
synapse upgrade   # upgrade to the latest version
synapse uninstall # remove Synapse and clean up installed files
```

---

## What Makes Synapse Different

Most AI agent frameworks give you a loop and a few toy tools. Synapse gives you a production-grade platform:

- **ReAct reasoning engine** — agents think, act, observe, and iterate for any number of turns per task
- **8 built-in tool servers** ready to use out of the box
- **Advanced Python Tool** — dynamically write and execute Python code in a secure sandbox
- **Schedule Agents** — trigger agents and orchestrations automatically using a cron schedule
- **Messaging Apps** — effortlessly connect agents to messaging platforms like Slack and Discord
- **Import & Export** — portably share orchestrations, agents, and MCP server configs
- **Plug in any MCP server** — local stdio or remote HTTP, added in seconds via the UI
- **Build custom tools with Webhooks and Python** — instantly convert any webhook (zero-code) or Python script into an agent tool.
- **Orchestrate multiple agents** as a DAG — parallel branches, routing logic, loops, human checkpoints
- **Persistent vault** — agents save and share files across sessions and runs
- **Local-first** — runs entirely on your machine with Ollama, or connect any cloud LLM

---

## Synapse UI

https://github.com/user-attachments/assets/78c526d9-c75b-41fa-9353-589d3207e7db


## Synapse Orchestration Demo

### Content Writing Orchestration
This demo showcases a multi-agent content writing orchestration pipeline. The agents autonomously open a browser, research a user-provided topic, draft the content in a Google Doc, and return the shared link. By default, the worker agents utilize `gemini-3-flash-preview`, while the evaluator agents use `gemini-3.1-pro-preview`. Each agent can be configured with different models based on your specific requirements. (Note: The video is sped up 2x to fit on GitHub.)

https://github.com/user-attachments/assets/4eec5db8-70d0-47b6-8608-f52b1f7b7d68

### Autonomous Code Development & PR Creation
This demo highlights a multi-agent software development system that writes code and generates pull requests on its own. A human-in-the-loop step is integrated into each stage, allowing you to review and confirm the agents' actions before the system finalizes the PR and outputs the repository link.

https://github.com/user-attachments/assets/95a511e1-e3e9-4812-b9ca-f7f4c28ef80f

## The Tool Ecosystem

Synapse agents are powerful because of what they can do. Every tool is a separate MCP process — isolated, composable, and safe.

### Native Tool Servers

These run automatically when Synapse starts:

| Tool Server | What It Does |
|---|---|
| **Sandbox** | Execute Python code in an isolated Docker container (512 MB RAM, 1 CPU). Pre-loaded with pandas, numpy, matplotlib, scikit-learn, requests, and more. Read/write files in the persistent vault. |
| **Vault** | Persistent file storage for agents. Create, read, update, patch, and list files across sessions. JSON deep-merge, text find-replace, and directory listing built in. |
| **SQL Agent** | Connect to any database (PostgreSQL, MySQL, SQLite). List tables, introspect schemas, run read queries. Supports any SQLAlchemy-compatible connection string. |
| **Browser** | Full browser automation via Playwright MCP. Navigate pages, click, fill forms, take screenshots, extract content. Powered by Chromium. |
| **PDF Parser** | Extract text and tables from any PDF by URL. Tables converted to Markdown. Page-by-page extraction. |
| **Excel Parser** | Parse `.xlsx` files from URL. Multi-sheet support. Converts all sheets to Markdown tables. |
| **Collect Data** | Generate dynamic forms that pause execution and collect user input. Supports text, number, email, date, phone, and option fields. |
| **Time** | Natural language date/time parsing. Handles relative offsets, weekday targets, timezone conversions, and complex expressions like "next Friday at 3pm EST". |
| **Code Search** | Semantic code search across indexed repositories using vector embeddings. Search by natural language query, get back relevant code snippets with file paths and line numbers. |
| **Web Scraper** | Powerful web scraping powered by crawl4ai. Scrape any URL to clean markdown, extract structured data with CSS schemas, crawl multiple URLs in parallel, capture screenshots, handle infinite-scroll pages, and run multi-step authenticated sessions. Built-in stealth mode bypasses anti-bot protections — works on LinkedIn, financial sites, and JavaScript-heavy pages. |

### Built-in MCP Servers

Enabled automatically when configured:

| Server | What It Does |
|---|---|
| **Filesystem** (`@modelcontextprotocol/server-filesystem`) | Full read/write access to your local code repositories. Configure which paths to expose in Settings → Repos. |
| **Google Workspace** (`workspace-mcp`) | Gmail (read, search, send), Google Drive (list, read, create files), and Google Calendar (events, scheduling). One-click OAuth setup in Settings. |
| **Playwright** (`@playwright/mcp`) | Browser control — already included in the native Browser tool above, available separately for headless automation. |
| **Sequential Thinking** (`npx @modelcontextprotocol/server-sequential-thinking`) | Structured step-by-step reasoning for complex, multi-stage problems. Agents break tasks into explicit thought chains before acting. Enabled by default. |
| **Memory** (`npx @modelcontextprotocol/server-memory`) | Persistent knowledge graph memory across sessions. Agents store and retrieve facts, relationships, and context between runs. Enabled by default. |

### Remote MCP Servers

Connect to any MCP server over the network — no code needed. Synapse supports native OAuth and Personal Access Token (PAT) authentication.

**To add a remote server:**

1. Open **Settings → MCP Servers**
2. Click the **Remote (URL)** tab at the top of the form
3. Optionally select a **preset** (Vercel, GitHub Copilot, Jira, Zapier, Figma, Fetch) to auto-fill the URL and token fields
4. Enter a **Server Name** and the **Server URL**
5. **Bearer Token / PAT** — leave empty to use OAuth (a browser window will open for authorization), or paste a personal access token for PAT-based servers (GitHub, Figma)
6. Click **Connect Server**

Synapse prefixes external tools with `<server-unique-name>__` followed by the tool name to prevent naming collisions. Any MCP-compatible API becomes an agent tool instantly.

Find more on the [MCP servers registry](https://github.com/modelcontextprotocol/servers).

### Local (stdio) MCP Servers

For servers that run as local processes, click the **Local (stdio)** tab and enter the command and arguments:

```
Command:   uvx
Arguments: mcp-server-git
```

Use the **Git** preset to auto-fill this. Add environment variables (API keys, secrets) directly in the form — no config file editing required.

### Custom Tools (n8n & Python)

Turn any automation workflow or Python logic into an agent tool.

1. Build a workflow in n8n (or any webhook-compatible tool), or expose an API via a Python program
2. Add it to Synapse in **Settings → Custom Tools**
3. Your agent now has that tool — it sees the name, description, and schema, and calls it like any other tool

This is the fastest way to give agents access to internal APIs, proprietary systems, or multi-step processes that you've already automated. n8n's 400+ node library or your own custom Python logic becomes your agent's extended toolkit.

---

## Building Agents

Create specialized agents in **Settings → Agents**. Each agent is an independent ReAct loop with its own:

- **System prompt** — define its persona, expertise, and constraints
- **Tool selection** — give it access to all tools, or restrict to a specific subset
- **Model override** — run different agents on different models (e.g., fast model for routing, capable model for analysis)
- **Code repositories** — link repos for semantic code search and filesystem access
- **LLM provider** — mix local Ollama models with cloud APIs per agent

### Example: Research Agent

```json
{
  "name": "Research Agent",
  "description": "Deep research using web browsing and document parsing",
  "tools": ["browser_navigate", "browser_snapshot", "parse_pdf", "parse_xlsx", "vault_write"],
  "system_prompt": "You are a thorough research analyst. For any research task: browse primary sources, extract key data, parse any documents you find, and save a structured report to the vault."
}
```

### Example: Data Agent

```json
{
  "name": "Data Agent",
  "description": "Analyzes data files and databases, produces reports",
  "tools": ["list_tables", "get_table_schema", "run_sql_query", "execute_python", "vault_write", "vault_read"],
  "system_prompt": "You are a data analyst. Explore the database schema, write SQL queries to extract insights, then use Python (pandas/matplotlib) to analyze and visualize results. Save all outputs to the vault."
}
```

### Example: Developer Agent

```json
{
  "name": "Strict Developer",
  "description": "Writes production-ready code, creates APIs, and runs self-correcting tests",
  "tools": ["execute_python", "mcp_github", "mcp_slack", "vault_write", "vault_read"],
  "system_prompt": "You are a senior backend engineer. Write robust, functional code, execute it using the Python tool to verify logic, and save the final output to the vault."
}
```

---

## Orchestrating Agents

Individual agents are powerful. Orchestrations are transformative.

An orchestration is a directed graph (DAG) of steps — you wire agents together, add routing logic, run things in parallel, loop over datasets, and checkpoint for human review. Build them visually on the canvas or define them in JSON.

### Step Types

| Step | What It Does |
|---|---|
| **Agent** | Run an agent's full ReAct loop. Pass context from shared state as input. Capture the result as an output key. |
| **LLM** | Make a direct LLM call without spinning up a full agent loop. Use for single-shot generation, summarization, classification, or prompt templating against shared state. Faster and cheaper than a full agent step when tool use isn't needed. |
| **Tool** | Execute a specific MCP tool directly — no agent reasoning, no loop. Pass inputs from shared state, write the raw tool output back to state. Ideal for deterministic data-fetching steps (e.g., run a SQL query, read a vault file, call an API). |
| **Evaluator** | Ask an LLM to make a routing decision. Maps decision labels to next steps. Use this to branch based on analysis results. |
| **Parallel** | Run multiple agent branches. Each branch runs sequentially (respects shared resources like browser). |
| **Merge** | Combine outputs from parallel branches. Strategies: list (accumulate), concat (join text), dict (merge objects). |
| **Loop** | Repeat a set of steps N times. Use with transforms to iterate over lists or refine outputs. |
| **Transform** | Execute arbitrary Python against the shared state dict. Reshape data, compute values, filter lists. |
| **Human** | Pause and ask a human for input via a generated form. Execution resumes when the user responds. Fully resumable. |
| **End** | Finalize the workflow. |

### Shared State

Every step reads from and writes to a shared state dictionary. Define the schema upfront:

```json
"state_schema": {
  "query": { "type": "string", "description": "Initial user query" },
  "research_results": { "type": "string", "description": "Raw research output" },
  "analysis": { "type": "string", "description": "Structured analysis" },
  "approved": { "type": "boolean", "default": false }
}
```

Steps use `input_keys` to pull from state and `output_key` to write back. This is how agents hand off work to each other.

---

## Example: End-to-End Research → Report Orchestration

Here's a complete orchestration that combines 5 agents to go from a question to a published report with human approval:

```
User Query
    │
    ▼
[1. Research Agent]          → Browses web, parses PDFs, saves raw findings to vault
    │ output: research_raw
    ▼
[2. Parallel Step]
    ├── [3. Data Agent]      → Pulls supporting data from SQL, runs Python analysis
    └── [4. Fact Checker]    → Cross-references key claims via browser
    │ output: data_analysis, verified_facts
    ▼
[5. Merge]                   → Combines data_analysis + verified_facts
    │
    ▼
[6. Writer Agent]            → Synthesizes all inputs into structured report, saves to vault
    │ output: report_draft
    ▼
[7. Quality Evaluator]       → Routes: "approved" → Human Review | "needs_revision" → Writer Agent
    │
    ▼
[8. Human Review]            → Shows draft, collects approval or revision notes
    │
    ▼
[9. Publisher Agent]         → Sends report via email (Gmail MCP), posts to Drive
    │
    ▼
[END]
```

This orchestration:
- Runs 3 agents in parallel (saves time)
- Routes automatically based on quality assessment
- Loops the writer if revisions are needed
- Pauses for human approval before publishing
- Uses vault to pass files between agents
- Publishes via Gmail and Google Drive

Build this visually on the canvas in about 10 minutes.

---

## Example: Stock Analysis Orchestration

The included "Stock Intraday Trading" orchestration shows how to combine market data, risk analysis, and human decisions:

```
[1. Portfolio Analyzer]     → Checks current positions via Zerodha MCP
    │
    ▼
[2. Login Router]           → Evaluator: logged in? → continue | not logged in? → prompt user
    │
    ▼
[3. Parallel Analysis]
    ├── [NSE Stock Analyzer]        → Technical analysis on watchlist
    ├── [Beta Data Fetcher]         → Fetches beta/volatility data
    └── [Current Events Agent]      → Browses news, checks sentiment
    │
    ▼
[4. Merge + Strategy Transform]    → Python transform: compute risk-adjusted scores
    │
    ▼
[5. Human Approval]                → Shows recommended trades, waits for confirmation
    │
    ▼
[END]
```

---

## Schedules

Automate agent and orchestration runs on a recurring schedule.

- **Interval** — run every N minutes/hours/days (e.g. monitor a feed, poll an API)
- **Cron / Fixed Time** — run at specific times (e.g. every day at 9 AM for a morning standup report)
- **Prompt** — The prompt is what the agent will receive each time the schedule fires. Think of it as a standing instruction.
- **Messaging notifications** — If the selected agent has a connected messaging channel (Slack, Telegram, etc.), the result is sent there automatically after each run.

---

## Messaging

Connect your agents to Telegram, Discord, Slack, Teams, or WhatsApp.

Enable **Multi-Agent Mode** in a channel so users can switch agents mid-chat using `/agent <name>` and list them with `/agents`. The channel's bound agent is the default.

---

## Import / Export

Export your orchestrations, agents, MCP servers, and tools as a portable bundle, or import one from another Synapse instance.

**Example Packs:** Synapse includes curated collections of agents, orchestrations, and MCP servers. Select a pack to preview what will be imported before committing:
- **Starter Pack** — Get up and running fast, includes a Personal Assistant with full tool access and a Web Research Agent.
- **Developer Pack** — Built for engineering teams, includes a Code Review Agent, Software Engineer Agent, QA Engineer, and a Dev base orchestration.
- **Productivity Pack** — Business and content power-users, includes a Data Analyst, Content Writer, Jira Analyst, Slack Notifier.

---

## Vault Management

The **Vault** is a persistent file directory (`data/vault/`) that acts as shared storage for all your agents. 

- **UI File Explorer** — Manage your vault directly in **Settings → Vault**. Create, edit, and delete `.md`, `.json`, and `.txt` files in a full-featured markdown and JSON editor.
- **Context Injection** — Instantly reference files inside agent system prompts or orchestration templates by typing `@`. The UI provides an intelligent dropdown that searches the vault, allowing you to seamlessly embed documents, guides, or skill configurations into LLM contexts as `@[path/to/file.md]`.
- **Agent Access** — Agents have built-in tool access to dynamically read, write, and patch files in the vault across sessions.

---

## Configuration

### Supported LLM Providers

| Provider | Mode | Notes |
|---|---|---|
| **Ollama** | Local | Any model pulled via `ollama pull`. Default: `mistral-nemo` |
| **Anthropic** | Cloud | Claude 3.5, Claude 3 Opus, Claude 3.7 Sonnet, etc. |
| **OpenAI** | Cloud | GPT-4o, GPT-4 Turbo, o1, o3-mini, etc. |
| **Gemini** | Cloud | Gemini 1.5 Pro, Gemini 2.0 Flash, etc. |
| **xAI (Grok)** | Cloud | Grok-2, Grok-3, Grok-3 Mini. Base URL: `https://api.x.ai/v1`. Set `XAI_API_KEY`. |
| **DeepSeek** | Cloud | DeepSeek-V3, DeepSeek-R1 (reasoning model). Base URL: `https://api.deepseek.com`. Set `DEEPSEEK_API_KEY`. |

Switch providers per-agent or globally in **Settings → Model**.

### Environment Variables

```bash
# Copy and edit
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `SYNAPSE_DATA_DIR` | `~/.synapse/data` | Where agents store files, memory, and state |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `SYNAPSE_BACKEND_PORT` | `8765` | Backend API port |
| `SYNAPSE_FRONTEND_PORT` | `3000` | Frontend UI port |
| `BACKEND_URL` | `http://127.0.0.1:8765` | Backend URL as seen by Next.js server (set in Docker) |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

---

## Manual Setup

### Backend

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3.11 main.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:<SYNAPSE_FRONTEND_PORT>` (default: `http://localhost:3000`)

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Ollama** (optional, for local models): [ollama.com](https://ollama.com)
  ```bash
  ollama pull mistral-nemo   # or any model you prefer
  ```
- **Docker** (optional, for sandbox code execution and Docker deployment)

---

## Architecture

```
frontend/                    Next.js 14 — chat UI, agent builder, orchestration canvas
  src/components/
    settings/
      McpServersTab.tsx      MCP server management UI (Local/Remote tabs, OAuth + PAT)
backend/
  core/
    server.py                FastAPI app — MCP session lifecycle, startup
    react_engine.py          ReAct agent loop — reasoning + tool execution
    tools.py                 Tool aggregation (MCP + virtual + custom)
    vault.py                 Persistent file storage
    config.py                Settings loader (SYNAPSE_DATA_DIR)
    mcp_client.py            External MCP server manager (stdio + remote/OAuth)
    routes/                  API route handlers
    orchestration/
      engine.py              DAG-based workflow executor
      steps.py               Step executors: Agent, LLM, Tool, Evaluator, Parallel,
                             Merge, Loop, Transform, Human, End
      models_orchestration.py  Data models for all step types
      state.py               Shared state + checkpointing
      logger.py              Per-run audit logs
  tools/                     Built-in MCP tool scripts (stdio processes)
    sequential_thinking/     Default sequential-thinking MCP server
    memory/                  Default knowledge-graph memory MCP server
  services/                  Business logic (code indexer, memory store)
  data/                      User data — gitignored
    user_agents.json         Agent configurations
    orchestrations.json      Orchestration definitions
    mcp_servers.json         Remote MCP server configs
    vault/                   Agent file storage
```

**Frontend ↔ Backend:** Next.js proxies `/api/*` and `/auth/*` to the backend via `next.config.ts` rewrites. Server-side routes use `BACKEND_URL` env var.

**MCP Transport:** Local servers use stdio transport. Remote servers use Streamable HTTP (SSE) with OAuth 2.0 PKCE or Bearer token auth. Synapse manages token refresh and session lifecycle automatically.

**Default MCP Servers:** Sequential Thinking and Memory servers start automatically with Synapse — no configuration required. They give every agent structured reasoning chains and persistent cross-session memory out of the box.

---

## Upcoming Features (Roadmap)

We are constantly improving Synapse AI. Here are a few features currently in the pipeline:

- **AI Builder Agent:** A native agent that can dynamically design workflows, orchestrations, and build other agents on the fly based on your prompts.
- **Spawn Sub-Agent Tool:** Allow agents to natively spawn and delegate tasks to temporary sub-agents mid-execution.
- **Compact Conversations:** A conversation option optimized to handle large contexts smoothly, compressing message history automatically.
- **Global Variable:** Support for defining global variables that can be dynamically injected into agent prompts, orchestrations, custom tools, and MCP server environments.
---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, architecture details, how to add MCP tool servers, and the PR checklist.

## License

Synapse AI is licensed under AGPL v3 to ensure it remains open and free, and to prevent cloud monopolies from offering it as a managed service without contributing back to the community.

AGPL-3.0-only — see [LICENSE](LICENSE)
