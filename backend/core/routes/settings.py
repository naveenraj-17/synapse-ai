"""
Settings, personal details, Google Maps, and config endpoints.
"""
import os
import json
from typing import Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
import httpx

from core.config import load_settings, SETTINGS_FILE, DATA_DIR, CREDENTIALS_FILE, TOKEN_FILE
from core.models import Settings, PersonalDetails, MapsDetailsRequest
from core.personal_details import load_personal_details, save_personal_details
from core.llm_providers import _make_aws_client, OLLAMA_MODEL
from core.json_store import JsonStore
from services.n8n_sync import sync_global_config, fetch_global_config

router = APIRouter()

_settings_store = JsonStore(SETTINGS_FILE, default_factory=dict, cache_ttl=2.0)


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


def _normalize_point(address: Optional[str], lat: Optional[float], lng: Optional[float]) -> Tuple[str, dict]:
    """Return (distance-matrix-string, meta) or raise HTTPException for invalid input."""
    addr = (address or "").strip()
    has_coords = lat is not None and lng is not None
    if addr and has_coords:
        return f"{lat},{lng}", {"type": "latlng", "address": addr, "location": {"lat": lat, "lng": lng}}
    if has_coords:
        return f"{lat},{lng}", {"type": "latlng", "location": {"lat": lat, "lng": lng}}
    if addr:
        return addr, {"type": "address", "address": addr}
    raise HTTPException(status_code=422, detail="Both origin and destination must be provided as an address or as lat/lng.")


def _build_directions_url(origin: str, destination: str, travel_mode: str) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote(origin)}"
        f"&destination={quote(destination)}"
        f"&travelmode={quote(travel_mode)}"
    )


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
    try:
        settings = await fetch_global_config(settings)
    except Exception as e:
        print(f"Warning: Failed to fetch n8n config: {e}")
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

    # Sync with n8n if configured
    try:
        data = await sync_global_config(data)
    except Exception as e:
        print(f"Error syncing with n8n: {e}")

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


# --- Maps ---

@router.post("/api/maps/details")
async def get_maps_details(request: MapsDetailsRequest):
    """Compute distance and duration between two points using Google Distance Matrix API."""
    settings = load_settings()
    api_key = (settings.get("google_maps_api_key") or os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="google_maps_api_key is not configured")

    origin_str, origin_meta = _normalize_point(request.origin_address, request.origin_lat, request.origin_lng)
    dest_str, dest_meta = _normalize_point(request.destination_address, request.destination_lat, request.destination_lng)

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin_str,
        "destinations": dest_str,
        "mode": request.travel_mode,
        "units": request.units,
        "key": api_key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail=f"Google Maps API returned non-JSON response (status {resp.status_code})")

    api_status = data.get("status")
    if api_status != "OK":
        message = data.get("error_message") or api_status or "Unknown error"
        raise HTTPException(status_code=502, detail=f"Google Distance Matrix error: {message}")

    rows = data.get("rows") or []
    elements = (rows[0].get("elements") if rows and isinstance(rows[0], dict) else None) or []
    element = elements[0] if elements else {}
    element_status = element.get("status")
    if element_status != "OK":
        raise HTTPException(status_code=502, detail=f"No route found: {element_status}")

    distance = element.get("distance") or {}
    duration = element.get("duration") or {}
    distance_m = distance.get("value")
    duration_s = duration.get("value")

    directions_url = _build_directions_url(origin_str, dest_str, request.travel_mode)

    return {
        "provider": "google_distance_matrix",
        "travel_mode": request.travel_mode,
        "units": request.units,
        "origin": origin_meta,
        "destination": dest_meta,
        "distance": {
            "meters": distance_m,
            "kilometers": (distance_m / 1000.0) if isinstance(distance_m, (int, float)) else None,
            "text": distance.get("text"),
        },
        "duration": {
            "seconds": duration_s,
            "minutes": (duration_s / 60.0) if isinstance(duration_s, (int, float)) else None,
            "text": duration.get("text"),
        },
        "directions_url": directions_url,
    }


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
