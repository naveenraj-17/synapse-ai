# Synapse AI — A Multi-Agent Orchestrator

**Build AI agents that actually do things.** Synapse is an open-source platform for creating, connecting, and orchestrating AI agents powered by any LLM — local or cloud. Agents use real tools: browsing the web, querying databases, executing code, reading files, managing emails, trading stocks, and anything else you can wrap in an MCP server or n8n workflow.

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

### Docker
```bash
git clone https://github.com/naveenraj-17/synapse
cd synapse
docker-compose up
```

### npm
```bash
npm install -g synapse-ai
synapse
```
Python 3.11+ required. All Python dependencies are installed automatically on first run.

### pip / uv
```bash
pip install synapse-ai
synapse

# or with uv:
uvx synapse-ai
```
Node.js 18+ required.

---

## What Makes Synapse Different

Most AI agent frameworks give you a loop and a few toy tools. Synapse gives you a production-grade platform:

- **ReAct reasoning engine** — agents think, act, observe, and iterate up to 30 turns per task
- **8 built-in tool servers** ready to use out of the box
- **Plug in any MCP server** — local stdio or remote HTTP, added in seconds
- **Build custom tools with n8n** — turn any automation workflow into an agent tool with zero code
- **Orchestrate multiple agents** as a DAG — parallel branches, routing logic, loops, human checkpoints
- **Persistent vault** — agents save and share files across sessions and runs
- **Local-first** — runs entirely on your machine with Ollama, or connect any cloud LLM

---

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
| **Maps** | Geocoding and routing via Google Maps API. Distance calculations (metric/imperial). Directions URL generation. Accepts addresses or lat/lng coordinates. |
| **Collect Data** | Generate dynamic forms that pause execution and collect user input. Supports text, number, email, date, phone, and option fields. |
| **Time** | Natural language date/time parsing. Handles relative offsets, weekday targets, timezone conversions, and complex expressions like "next Friday at 3pm EST". |
| **Code Search** | Semantic code search across indexed repositories using vector embeddings. Search by natural language query, get back relevant code snippets with file paths and line numbers. |

### Built-in MCP Servers

Enabled automatically when configured:

| Server | What It Does |
|---|---|
| **Filesystem** (`@modelcontextprotocol/server-filesystem`) | Full read/write access to your local code repositories. Configure which paths to expose in Settings → Repos. |
| **Google Workspace** (`workspace-mcp`) | Gmail (read, search, send), Google Drive (list, read, create files), and Google Calendar (events, scheduling). One-click OAuth setup in Settings. |
| **Playwright** (`@playwright/mcp`) | Browser control — already included in the native Browser tool above, available separately for headless automation. |

### Remote MCP Servers

Connect to any MCP server over the network — no code needed. Add it once in **Settings → MCP Servers**:

```json
{
  "name": "Stripe",
  "command": "npx",
  "args": ["mcp-remote", "https://mcp.stripe.com/v1/sse"],
  "env": { "STRIPE_SECRET_KEY": "sk_..." }
}
```

Synapse prefixes external tools with `ext_mcp_` to prevent naming collisions. Any MCP-compatible API becomes an agent tool instantly.

**Examples you can add:**
- Zerodha (stock trading): `npx mcp-remote https://mcp.kite.trade/mcp`
- GitHub, Linear, Notion, Slack, Stripe — any service with an MCP endpoint
- Your own self-hosted MCP server

### Custom Tools via n8n

Turn any automation workflow into an agent tool — without writing code.

1. Build a workflow in n8n (or any webhook-compatible tool)
2. Add it to Synapse in **Settings → Custom Tools**
3. Your agent now has that tool — it sees the name, description, and schema, and calls it like any other tool

This is the fastest way to give agents access to internal APIs, proprietary systems, or multi-step processes that you've already automated. n8n's 400+ node library becomes your agent's extended toolkit.

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

### Example: Stock Agent

```json
{
  "name": "NSE Stock Agent",
  "description": "Intraday analysis and portfolio management",
  "tools": ["ext_mcp_zerodha_*", "parse_pdf", "execute_python", "vault_write", "get_datetime"],
  "system_prompt": "You are a quantitative trader. Access live market data, analyze positions, run calculations in Python, and provide actionable trading insights."
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

## Configuration

### Supported LLM Providers

| Provider | Mode | Notes |
|---|---|---|
| **Ollama** | Local | Any model pulled via `ollama pull`. Default: `mistral-nemo` |
| **Anthropic** | Cloud | Claude 3.5, Claude 3 Opus, etc. |
| **OpenAI** | Cloud | GPT-4o, GPT-4 Turbo, etc. |
| **Gemini** | Cloud | Gemini 1.5 Pro, Flash, etc. |

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
| `SYNAPSE_BACKEND_PORT` | `8000` | Backend API port |
| `SYNAPSE_FRONTEND_PORT` | `3000` | Frontend UI port |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Backend URL as seen by Next.js server (set in Docker) |
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

Open [http://localhost:3000](http://localhost:3000)

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
backend/
  core/
    server.py                FastAPI app — MCP session lifecycle, startup
    react_engine.py          ReAct agent loop — reasoning + tool execution
    tools.py                 Tool aggregation (MCP + virtual + custom)
    vault.py                 Persistent file storage
    config.py                Settings loader (SYNAPSE_DATA_DIR)
    mcp_client.py            External MCP server manager
    routes/                  API route handlers
    orchestration/
      engine.py              DAG-based workflow executor
      steps.py               Step type executors
      models_orchestration.py  Data models
      state.py               Shared state + checkpointing
      logger.py              Per-run audit logs
  tools/                     Built-in MCP tool scripts (stdio processes)
  services/                  Business logic (code indexer, memory store)
  data/                      User data — gitignored
    user_agents.json         Agent configurations
    orchestrations.json      Orchestration definitions
    mcp_servers.json         Remote MCP server configs
    vault/                   Agent file storage
```

**Frontend ↔ Backend:** Next.js proxies `/api/*` and `/auth/*` to the backend via `next.config.ts` rewrites. Server-side routes use `BACKEND_URL` env var.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, architecture details, how to add MCP tool servers, and the PR checklist.

## License

MIT — see [LICENSE](LICENSE)
