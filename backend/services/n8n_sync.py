import json
import httpx
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Constants for n8n Webhook
# User provided: http://localhost:5678/webhook-test/get-config
# We assume n8n_url is http://localhost:5678
WEBHOOK_PATH = "/webhook/get-config"

async def _n8n_request(client: httpx.AsyncClient, method: str, url: str, headers: Dict[str, str], json_data: Any = None) -> Any:
    try:
        print(f"DEBUG: n8n Request {method} {url} Payload: {json_data}")
        resp = await client.request(method, url, headers=headers, json=json_data)
        resp.raise_for_status()
        # Some webhooks might return 200 OK with text "Webhook received", or JSON
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return resp.text
    except httpx.HTTPStatusError as e:
        logger.error(f"n8n API Error {e.response.status_code}: {e.response.text}")
        print(f"DEBUG: n8n API Error: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"n8n Request Failed: {e}")
        print(f"DEBUG: n8n Request Failed: {e}")
        raise

async def fetch_global_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetches the current global_config from n8n webhook and updates the settings dict.
    """
    n8n_url = (settings.get("n8n_url") or "").rstrip("/")
    api_key = settings.get("n8n_api_key") # Webhook might not verify API key if not configured, but sending it is safe

    if not n8n_url:
        return settings

    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        url = f"{n8n_url}{WEBHOOK_PATH}"
        
        try:
            # GET returns list of { "key": "...", "value": "...", "id": ... }
            data = await _n8n_request(client, "GET", url, headers)
            print(f"DEBUG: Fetch response: {data}")
            
            # Ensure data is a list
            if isinstance(data, list):
                new_config = {}
                for item in data:
                    if isinstance(item, dict):
                        key = item.get("key")
                        val = item.get("value")
                        if key:
                            new_config[key] = str(val) if val is not None else ""
                
                if new_config:
                    settings["global_config"] = new_config
            else:
                print(f"DEBUG: Unexpected response format (expected list): {type(data)}")

        except Exception as e:
            logger.error(f"Failed to fetch global config from n8n webhook: {e}")
            pass

    return settings

async def sync_global_config(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Syncs global_config settings to n8n via webhook.
    """
    n8n_url = (settings.get("n8n_url") or "").rstrip("/")
    api_key = settings.get("n8n_api_key")
    global_config = settings.get("global_config", {})
    
    if not n8n_url:
        return settings

    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        url = f"{n8n_url}{WEBHOOK_PATH}"

        # 1. Fetch current state to get IDs
        existing_map = {} # key -> id
        try:
            current_data = await _n8n_request(client, "GET", url, headers)
            if isinstance(current_data, list):
                for item in current_data:
                    if isinstance(item, dict):
                        k = item.get("key")
                        i = item.get("id")
                        if k and i is not None:
                            existing_map[k] = i
        except Exception as e:
            logger.error(f"Failed to fetch current config for sync: {e}")
            # If fetch fails, we might create duplicates if we blindly POST. 
            # Safe strategy: abort sync if we can't read state.
            return settings

        # 2. Sync
        for key, value in global_config.items():
            try:
                if key in existing_map:
                    # Update (PUT)
                    row_id = existing_map[key]
                    payload = {
                        "id": row_id,
                        "key": key,
                        "value": value
                    }
                    await _n8n_request(client, "PUT", url, headers, json_data=payload)
                else:
                    # Create (POST)
                    payload = {
                        "key": key,
                        "value": value
                    }
                    await _n8n_request(client, "POST", url, headers, json_data=payload)
            except Exception as e:
                logger.error(f"Failed to sync key {key}: {e}")

    return settings
