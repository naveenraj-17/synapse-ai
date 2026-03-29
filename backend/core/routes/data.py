"""
Synthetic data, models, bedrock, config, history endpoints.
"""
import os
import json
import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
import httpx

from core.config import load_settings
from core.llm_providers import _make_aws_client
from core.session import session_state, _CHAT_SESSIONS_DIR
from services.synthetic_data import generate_synthetic_data, SyntheticDataRequest, current_job, DATASETS_DIR

router = APIRouter()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
# --- Synthetic Data ---

@router.post("/api/synthetic/generate")
async def start_synthetic_generation(req: SyntheticDataRequest):
    if current_job["status"] == "generating":
        raise HTTPException(status_code=400, detail="A generation job is already running.")

    asyncio.create_task(generate_synthetic_data(req))
    return {"status": "started", "message": "Generation started in background."}


@router.get("/api/synthetic/status")
async def get_synthetic_status():
    return current_job


@router.get("/api/synthetic/datasets")
async def list_datasets():
    if not os.path.exists(DATASETS_DIR):
        return []
    files = [f for f in os.listdir(DATASETS_DIR) if f.endswith(".jsonl")]
    results = []
    for f in files:
        path = os.path.join(DATASETS_DIR, f)
        stats = os.stat(path)
        results.append({
            "filename": f,
            "size": stats.st_size,
            "created": datetime.fromtimestamp(stats.st_ctime).isoformat()
        })
    return sorted(results, key=lambda x: x["created"], reverse=True)


# --- Models ---

@router.get("/api/models")
async def get_models():
    """Fetches available models dynamically from each provider's API."""
    settings = load_settings()

    # --- Fallback model lists (used when API calls fail) ---
    GEMINI_FALLBACK = ["gemini-2.5-pro-preview-05-06", "gemini-2.5-flash-preview-04-17", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]
    ANTHROPIC_FALLBACK = ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
    OPENAI_FALLBACK = ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini"]
    BEDROCK_FALLBACK = ["bedrock.anthropic.claude-3-5-sonnet-20240620-v1:0", "bedrock.anthropic.claude-3-sonnet-20240229-v1:0"]
    GROK_FALLBACK = ["grok-3", "grok-3-mini", "grok-2-1212", "grok-2-vision-1212"]
    DEEPSEEK_FALLBACK = ["deepseek-chat", "deepseek-reasoner"]

    # --- Check API keys ---
    gemini_key = (settings.get("gemini_key") or "").strip()
    anthropic_key = (settings.get("anthropic_key") or "").strip()
    openai_key = (settings.get("openai_key") or "").strip()
    grok_key = (settings.get("grok_key") or "").strip()
    deepseek_key = (settings.get("deepseek_key") or "").strip()
    bedrock_available = bool((settings.get("bedrock_api_key") or "").strip() or
                             (settings.get("aws_access_key_id") or "").strip())

    # --- Fetch models from each provider concurrently ---
    async def fetch_ollama() -> tuple[bool, list[str]]:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])]
                    return True, models
        except Exception:
            pass
        return False, []

    async def fetch_openai() -> tuple[bool, list[str]]:
        if not openai_key:
            return False, OPENAI_FALLBACK
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    # Filter to chat models only (gpt-*)
                    models = sorted(set(
                        m["id"] for m in data
                        if m.get("id", "").startswith(("gpt-4", "gpt-3.5"))
                        and "instruct" not in m.get("id", "")
                    ), reverse=True)
                    return True, models if models else OPENAI_FALLBACK
        except Exception as e:
            print(f"Error fetching OpenAI models: {e}")
        return True, OPENAI_FALLBACK  # Key present, assume available

    async def fetch_anthropic() -> tuple[bool, list[str]]:
        if not anthropic_key:
            return False, ANTHROPIC_FALLBACK
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    models = sorted(set(m["id"] for m in data if m.get("id")), reverse=True)
                    return True, models if models else ANTHROPIC_FALLBACK
        except Exception as e:
            print(f"Error fetching Anthropic models: {e}")
        return True, ANTHROPIC_FALLBACK  # Key present, assume available

    async def fetch_gemini() -> tuple[bool, list[str]]:
        if not gemini_key:
            return False, GEMINI_FALLBACK
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}",
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("models", [])
                    # Filter to generateContent-capable models and extract clean names
                    models = []
                    for m in data:
                        name = m.get("name", "")  # e.g. "models/gemini-2.0-flash"
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods and name.startswith("models/"):
                            clean = name.replace("models/", "")
                            models.append(clean)
                    return True, sorted(set(models)) if models else GEMINI_FALLBACK
        except Exception as e:
            print(f"Error fetching Gemini models: {e}")
        return True, GEMINI_FALLBACK  # Key present, assume available

    async def fetch_grok() -> tuple[bool, list[str]]:
        if not grok_key:
            return False, GROK_FALLBACK
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {grok_key}"},
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    models = sorted(set(
                        m["id"] for m in data if m.get("id", "").startswith("grok")
                    ), reverse=True)
                    return True, models if models else GROK_FALLBACK
        except Exception as e:
            print(f"Error fetching Grok models: {e}")
        return True, GROK_FALLBACK  # Key present, assume available

    async def fetch_deepseek() -> tuple[bool, list[str]]:
        if not deepseek_key:
            return False, DEEPSEEK_FALLBACK
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.deepseek.com/v1/models",
                    headers={"Authorization": f"Bearer {deepseek_key}"},
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    models = sorted(set(
                        m["id"] for m in data if m.get("id", "").startswith("deepseek")
                    ), reverse=True)
                    return True, models if models else DEEPSEEK_FALLBACK
        except Exception as e:
            print(f"Error fetching DeepSeek models: {e}")
        return True, DEEPSEEK_FALLBACK  # Key present, assume available

    # Run all fetches concurrently
    ollama_result, openai_result, anthropic_result, gemini_result, grok_result, deepseek_result = await asyncio.gather(
        fetch_ollama(), fetch_openai(), fetch_anthropic(), fetch_gemini(), fetch_grok(), fetch_deepseek()
    )

    ollama_available, local_models = ollama_result
    openai_avail, openai_models = openai_result
    anthropic_avail, anthropic_models = anthropic_result
    gemini_avail, gemini_models = gemini_result
    grok_avail, grok_models = grok_result
    deepseek_avail, deepseek_models = deepseek_result

    # --- Build provider map ---
    providers = {
        "ollama": {"available": ollama_available, "models": local_models},
        "gemini": {"available": gemini_avail, "models": gemini_models},
        "anthropic": {"available": anthropic_avail, "models": anthropic_models},
        "openai": {"available": openai_avail, "models": openai_models},
        "grok": {"available": grok_avail, "models": grok_models},
        "deepseek": {"available": deepseek_avail, "models": deepseek_models},
        "bedrock": {"available": bedrock_available, "models": BEDROCK_FALLBACK},
    }

    # --- Flat list of all available models ---
    all_available = []
    for name, info in providers.items():
        if info["available"]:
            all_available.extend(info["models"])

    # --- Backward compat ---
    cloud_models = gemini_models + anthropic_models + openai_models + grok_models + deepseek_models + BEDROCK_FALLBACK

    return {
        "providers": providers,
        "all_available": all_available,
        "local": local_models,
        "cloud": cloud_models,
    }




@router.get("/api/bedrock/models")
async def get_bedrock_models():
    """Lists Bedrock foundation models."""
    settings = load_settings()
    region = (settings.get("aws_region") or "us-east-1").strip() or "us-east-1"

    def _list_models_sync():
        client = _make_aws_client("bedrock", region, settings)
        resp = client.list_foundation_models()
        summaries = resp.get("modelSummaries", []) or []
        models: list[str] = []
        for s in summaries:
            model_id = s.get("modelId")
            if model_id:
                models.append(f"bedrock.{model_id}")
        return sorted(set(models))

    try:
        models = await asyncio.to_thread(_list_models_sync)
        return {"models": models}
    except Exception as e:
        print(f"Error listing Bedrock models: {e}")
        return {
            "models": [],
            "error": "Unable to list Bedrock models. Check AWS credentials/permissions and region.",
        }


@router.get("/api/bedrock/inference-profiles")
async def get_bedrock_inference_profiles():
    """Lists Bedrock inference profiles."""
    settings = load_settings()
    region = (settings.get("aws_region") or "us-east-1").strip() or "us-east-1"

    def _list_profiles_sync():
        client = _make_aws_client("bedrock", region, settings)

        if not hasattr(client, "list_inference_profiles"):
            return []

        resp = client.list_inference_profiles()
        summaries = (
            resp.get("inferenceProfileSummaries")
            or resp.get("inferenceProfiles")
            or resp.get("summaries")
            or []
        )
        profiles = []
        for s in summaries or []:
            if not isinstance(s, dict):
                continue
            profiles.append(
                {
                    "id": s.get("inferenceProfileId") or s.get("id") or "",
                    "arn": s.get("inferenceProfileArn") or s.get("arn") or "",
                    "name": s.get("inferenceProfileName") or s.get("name") or "",
                    "status": s.get("status") or "",
                }
            )
        return sorted(profiles, key=lambda p: (p.get("name") or p.get("arn") or p.get("id") or ""))

    try:
        profiles = await asyncio.to_thread(_list_profiles_sync)
        return {"profiles": profiles}
    except Exception as e:
        print(f"Error listing Bedrock inference profiles: {e}")
        return {
            "profiles": [],
            "error": "Unable to list Bedrock inference profiles. Check AWS credentials/permissions and region.",
        }


# --- History Management ---

@router.delete("/api/history/recent")
async def clear_recent_history():
    """Clears all persisted JSON session files and in-memory session state."""
    import shutil
    import os
    session_state.clear()
    # Delete all JSON session files
    cleared = 0
    if os.path.isdir(_CHAT_SESSIONS_DIR):
        for fname in os.listdir(_CHAT_SESSIONS_DIR):
            if fname.endswith(".json"):
                try:
                    os.remove(os.path.join(_CHAT_SESSIONS_DIR, fname))
                    cleared += 1
                except Exception:
                    pass
    return {"status": "success", "message": f"Cleared {cleared} session file(s) and in-memory state."}


@router.delete("/api/history/all")
async def clear_all_history():
    """Clears ALL session files AND long-term ChromaDB memory (report RAG)."""
    import os
    import core.server as _server

    session_state.clear()
    # Delete all JSON session files
    cleared = 0
    if os.path.isdir(_CHAT_SESSIONS_DIR):
        for fname in os.listdir(_CHAT_SESSIONS_DIR):
            if fname.endswith(".json"):
                try:
                    os.remove(os.path.join(_CHAT_SESSIONS_DIR, fname))
                    cleared += 1
                except Exception:
                    pass
    # Clear ChromaDB report-RAG collections
    if _server.memory_store:
        success = _server.memory_store.clear_memory()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to clear long-term memory.")
    return {"status": "success", "message": f"Cleared {cleared} session file(s) and long-term memory."}
