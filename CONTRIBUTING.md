# Contributing to Synapse

## Development Setup

**Prerequisites:** Python 3.11+, Node.js 18+, [Ollama](https://ollama.com/) (optional)

```bash
git clone https://github.com/naveenraj-17/synapse
cd synapse
bash setup.sh      # installs all dependencies
bash start.sh      # starts backend (port 8000) + frontend (port 3000)
```

Or manually:

```bash
# Backend
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3.11 main.py

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Architecture

```
backend/
  core/
    server.py          # FastAPI app + MCP session lifecycle
    config.py          # Settings loader (reads SYNAPSE_DATA_DIR env var)
    vault.py           # Large-output file storage
    react_engine.py    # ReAct agent loop
    mcp_client.py      # External MCP server manager
    routes/            # FastAPI route handlers (chat, agents, settings, ...)
  tools/               # Built-in MCP tool scripts (run as subprocesses)
  services/            # Business logic (code indexer, etc.)
  data/                # User data — gitignored in production
frontend/
  src/app/             # Next.js 14 app router
    api/               # Server-side proxy routes to backend
    page.tsx           # Main chat UI
  src/components/      # React components
```

**Frontend ↔ Backend:** The Next.js dev server proxies `/api/*` and `/auth/*` to `http://127.0.0.1:8000` via `next.config.ts` rewrites. Server-side API routes use the `BACKEND_URL` environment variable (default `http://127.0.0.1:8000`).

**Data directory:** All user data is stored in `SYNAPSE_DATA_DIR` (default `backend/data/` in dev, `~/.synapse/data/` in packaged installs). Never hardcode paths relative to `__file__` — always read from `core.config.DATA_DIR`.

## Adding a Built-in MCP Tool

1. Create `backend/tools/my_tool.py` — implement a standard MCP server using the `mcp` library
2. Register it in `backend/core/server.py` in the `AGENTS` dict:
   ```python
   AGENTS = {
       ...
       "my_tool": str(TOOLS_DIR / "my_tool.py"),
   }
   ```
3. The tool's functions are automatically registered and available to the agent

## Adding an API Route

1. Create `backend/core/routes/my_route.py` with a FastAPI `APIRouter`
2. Register it in `backend/core/server.py`:
   ```python
   from core.routes.my_route import router as my_router
   app.include_router(my_router)
   ```

## PR Checklist

- [ ] No secrets or API keys committed (check `backend/data/` files)
- [ ] Data paths use `DATA_DIR` from `core.config`, not hardcoded paths
- [ ] `next.config.ts` still has `output: 'standalone'`
- [ ] New env vars documented in `.env.example`
- [ ] Frontend server-side routes use `process.env.BACKEND_URL`

## Publishing a Release

```bash
# 1. Bump version in pyproject.toml and package.json

# 2. Build and publish Python package
bash scripts/build_frontend.sh
pip install hatch && hatch build
twine upload dist/*

# 3. Build and publish npm package
node scripts/bundle-frontend.js
npm publish --access public

# Or: push a version tag and let GitHub Actions handle it
git tag v0.2.0 && git push --tags
```
