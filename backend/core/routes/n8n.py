"""
n8n integration endpoints (workflow listing, webhook discovery).
"""
from fastapi import APIRouter, HTTPException
import httpx

from core.config import load_settings

router = APIRouter()


def _get_n8n_config():
    settings = load_settings()
    base_url = (settings.get("n8n_url") or "").strip()
    api_key = (settings.get("n8n_api_key") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="n8n_url is not configured")
    if not api_key:
        raise HTTPException(status_code=400, detail="n8n_api_key is not configured")
    return base_url.rstrip("/"), api_key


async def _n8n_request(method: str, path: str):
    base_url, api_key = _get_n8n_config()
    url = f"{base_url}{path}"
    headers = {"X-N8N-API-KEY": api_key}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, url, headers=headers)
            if resp.status_code in (401, 403):
                raise HTTPException(status_code=401, detail="n8n authentication failed")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"n8n request failed: {str(e)}")


@router.get("/api/n8n/workflows")
async def n8n_list_workflows():
    """Lists workflows from n8n (requires n8n_url + n8n_api_key in settings)."""
    data = await _n8n_request("GET", "/api/v1/workflows")

    workflows = []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        workflows = data.get("data")
    elif isinstance(data, list):
        workflows = data

    return [
        {
            "id": str(w.get("id")) if w.get("id") is not None else "",
            "name": w.get("name") or "",
            "active": bool(w.get("active")) if w.get("active") is not None else False,
            "updatedAt": w.get("updatedAt") or w.get("updated_at") or None,
        }
        for w in workflows
        if w is not None
    ]


@router.get("/api/n8n/workflows/{workflow_id}/webhook")
async def n8n_get_workflow_webhook(workflow_id: str):
    """Derives the production webhook URL for a workflow by locating a Webhook trigger node."""
    base_url, _ = _get_n8n_config()
    workflow = await _n8n_request("GET", f"/api/v1/workflows/{workflow_id}")

    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not isinstance(nodes, list):
        raise HTTPException(status_code=404, detail="Workflow nodes not found")

    webhook_node = None
    for node in nodes:
        if isinstance(node, dict) and (node.get("type") == "n8n-nodes-base.webhook"):
            webhook_node = node
            break
    if webhook_node is None:
        for node in nodes:
            t = (node.get("type") or "") if isinstance(node, dict) else ""
            if "webhook" in t.lower():
                webhook_node = node
                break

    if webhook_node is None:
        raise HTTPException(status_code=404, detail="No webhook trigger node found in workflow")

    parameters = webhook_node.get("parameters") if isinstance(webhook_node, dict) else None
    path = parameters.get("path") if isinstance(parameters, dict) else None
    if not path or not isinstance(path, str):
        raise HTTPException(status_code=404, detail="Webhook path not found in workflow")

    clean_path = path.lstrip("/")
    production_url = f"{base_url}/webhook/{clean_path}"
    return {"workflowId": str(workflow_id), "path": clean_path, "productionUrl": production_url}
