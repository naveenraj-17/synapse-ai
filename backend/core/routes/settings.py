"""
Settings, personal details, and config endpoints.
"""
import os
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.config import load_settings, SETTINGS_FILE, DATA_DIR, CREDENTIALS_FILE, TOKEN_FILE
from core.models import Settings, PersonalDetails
from core.personal_details import load_personal_details, save_personal_details
from core.llm_providers import _make_aws_client, OLLAMA_MODEL
from core.json_store import JsonStore

router = APIRouter()

_settings_store = JsonStore(SETTINGS_FILE, default_factory=dict, cache_ttl=2.0)

# Path to the examples directory (sibling of this file's package root)
_EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "examples")


def save_settings(settings: dict):
    _settings_store.save(settings)


def _init_memory_store(settings: dict):
    """Initialize the long-term memory store.

    Chat memory always uses Ollama with nomic-embed-text (384d) — a small, fast,
    local model that stays consistent regardless of the LLM provider mode.
    Code embeddings use provider models separately (see services/code_indexer.py).
    """
    try:
        from core.memory import MemoryStore as _MemoryStore
    except ImportError:
        return None

    return _MemoryStore(model="nomic-embed-text", embed_fn=None)


# --- Status & Settings ---

@router.get("/api/status")
async def get_status():
    from core.routes.agents import load_user_agents, active_agent_id
    from core.llm_providers import detect_provider_from_model

    user_agents = load_user_agents()
    agents_status = {}
    for a in user_agents:
        agents_status[a["id"]] = {"name": a["name"], "status": "online"}

    current_settings = load_settings()
    default_model = current_settings.get("model", "mistral")

    # Resolve active agent's model
    active_agent = next((a for a in user_agents if a["id"] == active_agent_id), None)
    resolved_model = default_model
    if active_agent and active_agent.get("model"):
        resolved_model = active_agent["model"]

    provider = detect_provider_from_model(resolved_model)

    return {
        "agents": agents_status,
        "active_agent_id": active_agent_id,
        "overall": "operational",
        "model": resolved_model,
        "mode": current_settings.get("mode", "local"),
        "provider": provider,
    }


@router.get("/api/settings")
async def get_settings():
    settings = load_settings()
    return settings


@router.post("/api/settings")
async def update_settings(settings: Settings):
    print(f"DEBUG: update_settings called with: {settings.dict()}")
    # Get the latest payload and strip unset values to avoid overwriting existing properties with defaults
    try:
        data = settings.dict(exclude_unset=True)
    except Exception:
        data = settings.dict()
        
    existing = load_settings()
    existing.update(data)
    data = existing

    save_settings(data)

    # Reinitialize memory so embeddings provider matches the new mode.
    import core.server as _server
    try:
        from core.memory import MemoryStore as _MemoryStore
    except ImportError:
        _MemoryStore = None
    
    if _MemoryStore:
        try:
            _server.memory_store = _init_memory_store(data)
        except Exception as e:
            print(f"Warning: failed to reinitialize MemoryStore after settings update: {e}")
    return data


# --- Personal Details ---

@router.get("/api/personal-details")
async def get_personal_details_api():
    return load_personal_details()


@router.post("/api/personal-details")
async def update_personal_details_api(details: PersonalDetails):
    data = details.dict()
    return save_personal_details(data)


# --- Google Credentials & Config ---

@router.post("/api/setup/google-credentials")
async def upload_google_creds(request: Request):
    try:
        data = await request.json()
        print(f"DEBUG: Received credentials upload (Type: {type(data)})")

        if isinstance(data, str):
            parsed = json.loads(data)
        else:
            parsed = data

        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(parsed, f, indent=4)

        return {"status": "success", "message": "Credentials saved successfully."}
    except Exception as e:
        print(f"Error saving credentials: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")


@router.post("/api/setup/google-token")
async def upload_google_token(request: Request):
    try:
        data = await request.json()
        print(f"DEBUG: Received token upload (Type: {type(data)})")

        if isinstance(data, str):
            parsed = json.loads(data)
        else:
            parsed = data

        with open(TOKEN_FILE, 'w') as f:
            json.dump(parsed, f, indent=4)

        return {"status": "success", "message": "Token saved successfully."}
    except Exception as e:
        print(f"Error saving token: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")


@router.get("/api/config")
async def get_config():
    has_credentials = os.path.exists(CREDENTIALS_FILE)
    has_token = os.path.exists(TOKEN_FILE)

    if not has_credentials:
        return {"has_credentials": False, "is_connected": False}

    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            creds = json.load(f)
            app_info = creds.get("web") or creds.get("installed", {})

        client_id_full = app_info.get("client_id", "")
        # Mask: show only last 4 chars, e.g. ****h453
        masked_client_id = ("****" + client_id_full[-8:]) if len(client_id_full) > 8 else "****"

        # Read user email from token.json if available
        user_email = None
        if has_token:
            try:
                with open(TOKEN_FILE, 'r') as tf:
                    token_data = json.load(tf)
                    user_email = token_data.get("id_token_hint") or token_data.get("email")
                    # google-auth stores it in the token as a raw JWT — try to decode the id_token
                    if not user_email and token_data.get("id_token"):
                        import base64
                        id_token = token_data["id_token"]
                        payload_b64 = id_token.split(".")[1]
                        # Add padding
                        payload_b64 += "=" * (4 - len(payload_b64) % 4)
                        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                        user_email = payload.get("email")
            except Exception:
                pass

        return {
            "has_credentials": True,
            "client_id": masked_client_id,
            "project_id": app_info.get("project_id", ""),
            "is_connected": has_token,
            "user_email": user_email,
        }
    except Exception as e:
        return {"has_credentials": True, "error": str(e), "is_connected": has_token}


@router.get("/api/file")
async def get_file(path: str):
    """Serve a local file. Restricted to the user's home directory and data dir."""
    resolved = os.path.realpath(path)
    home_dir = os.path.expanduser("~")
    allowed_bases = [home_dir, DATA_DIR]
    if not any(resolved.startswith(os.path.realpath(base)) for base in allowed_bases):
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directories")
    if not os.path.exists(resolved) or not os.path.isfile(resolved):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(resolved)


# --- Example Packs ---

@router.get("/api/examples")
async def get_examples():
    """Return the list of available example packs from backend/examples/index.json."""
    index_path = os.path.join(_EXAMPLES_DIR, "index.json")
    if not os.path.exists(index_path):
        return []
    try:
        with open(index_path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load examples index: {e}")


@router.get("/api/examples/{example_id}")
async def get_example_bundle(example_id: str):
    """Return the import bundle JSON for a specific example pack."""
    # Sanitize: only alphanumeric and underscores
    safe_id = "".join(c for c in example_id if c.isalnum() or c == "_")
    bundle_path = os.path.realpath(os.path.join(_EXAMPLES_DIR, f"{safe_id}.bundle.json"))
    # Ensure it stays within the examples directory
    if not bundle_path.startswith(os.path.realpath(_EXAMPLES_DIR)):
        raise HTTPException(status_code=403, detail="Invalid example ID")
    if not os.path.exists(bundle_path):
        raise HTTPException(status_code=404, detail=f"Example pack '{example_id}' not found")
    try:
        with open(bundle_path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load example bundle: {e}")
