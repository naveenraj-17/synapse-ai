"""
Synthetic data, models, bedrock, config, history endpoints.
"""
import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from core.config import load_settings, DATA_DIR
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
    async def fetch_ollama() -> tuple[bool, list[str], list[str]]:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])]
                    # Simple heuristic: models with 'embed' in name are likely for embeddings
                    embeds = [m for m in models if "embed" in m.lower()]
                    return True, models, embeds
        except Exception:
            pass
        return False, [], []

    async def fetch_openai() -> tuple[bool, list[str], list[str]]:
        if not openai_key:
            return False, OPENAI_FALLBACK, ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    chat_models = sorted(set(
                        m["id"] for m in data
                        if m.get("id", "").startswith(("gpt-4", "gpt-3.5"))
                        and "instruct" not in m.get("id", "")
                    ), reverse=True)
                    embed_models = sorted(set(
                        m["id"] for m in data if "embedding" in m.get("id", "")
                    ))
                    return True, chat_models if chat_models else OPENAI_FALLBACK, embed_models if embed_models else ["text-embedding-3-small", "text-embedding-3-large"]
        except Exception as e:
            print(f"Error fetching OpenAI models: {e}")
        return True, OPENAI_FALLBACK, ["text-embedding-3-small", "text-embedding-3-large"]

    async def fetch_anthropic() -> tuple[bool, list[str], list[str]]:
        if not anthropic_key:
            return False, ANTHROPIC_FALLBACK, []
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
                    return True, models if models else ANTHROPIC_FALLBACK, []
        except Exception as e:
            print(f"Error fetching Anthropic models: {e}")
        return True, ANTHROPIC_FALLBACK, []

    async def fetch_gemini() -> tuple[bool, list[str], list[str]]:
        if not gemini_key:
            return False, GEMINI_FALLBACK, ["text-embedding-004", "gemini-embedding-001"]
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}",
                    timeout=5.0,
                )
                if r.status_code == 200:
                    data = r.json().get("models", [])
                    chat_models = []
                    embed_models = []
                    for m in data:
                        name = m.get("name", "").replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            chat_models.append(name)
                        if "embedContent" in methods:
                            embed_models.append(name)
                    return True, sorted(set(chat_models)) if chat_models else GEMINI_FALLBACK, sorted(set(embed_models)) if embed_models else ["text-embedding-004"]
        except Exception as e:
            print(f"Error fetching Gemini models: {e}")
        return True, GEMINI_FALLBACK, ["text-embedding-004"]

    async def fetch_grok() -> tuple[bool, list[str], list[str]]:
        if not grok_key:
            return False, GROK_FALLBACK, []
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
                    return True, models if models else GROK_FALLBACK, []
        except Exception as e:
            print(f"Error fetching Grok models: {e}")
        return True, GROK_FALLBACK, []

    async def fetch_deepseek() -> tuple[bool, list[str], list[str]]:
        if not deepseek_key:
            return False, DEEPSEEK_FALLBACK, []
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
                    return True, models if models else DEEPSEEK_FALLBACK, []
        except Exception as e:
            print(f"Error fetching DeepSeek models: {e}")
        return True, DEEPSEEK_FALLBACK, []

    async def fetch_bedrock() -> tuple[bool, list[str], list[str]]:
        if not bedrock_available:
            return False, BEDROCK_FALLBACK, ["amazon.titan-embed-text-v1", "amazon.titan-embed-text-v2:0"]
        try:
            # Bedrock foundation models include embeddings
            def _list():
                c = _make_aws_client("bedrock", settings.get("aws_region", "us-east-1"), settings)
                resp = c.list_foundation_models()
                chat = []
                embed = []
                for m in resp.get("modelSummaries", []):
                    mid = f"bedrock.{m['modelId']}"
                    if "EMBEDDING" in m.get("outputModalities", []):
                        embed.append(mid)
                    else:
                        chat.append(mid)
                return chat, embed
            
            chat, embed = await asyncio.to_thread(_list)
            return True, chat if chat else BEDROCK_FALLBACK, embed if embed else ["bedrock.amazon.titan-embed-text-v1"]
        except Exception:
            return True, BEDROCK_FALLBACK, ["bedrock.amazon.titan-embed-text-v1"]

    # Run all fetches concurrently
    results = await asyncio.gather(
        fetch_ollama(), fetch_openai(), fetch_anthropic(), 
        fetch_gemini(), fetch_grok(), fetch_deepseek(), fetch_bedrock()
    )

    ollama_avail, ollama_chat, ollama_embed = results[0]
    openai_avail, openai_chat, openai_embed = results[1]
    anthropic_avail, anthropic_chat, anthropic_embed = results[2]
    gemini_avail, gemini_chat, gemini_embed = results[3]
    grok_avail, grok_chat, grok_embed = results[4]
    deepseek_avail, deepseek_chat, deepseek_embed = results[5]
    bedrock_avail, bedrock_chat, bedrock_embed = results[6]

    # --- Build provider map ---
    providers = {
        "ollama": {"available": ollama_avail, "models": ollama_chat, "embedding_models": ollama_embed},
        "gemini": {"available": gemini_avail, "models": gemini_chat, "embedding_models": gemini_embed},
        "anthropic": {"available": anthropic_avail, "models": anthropic_chat, "embedding_models": anthropic_embed},
        "openai": {"available": openai_avail, "models": openai_chat, "embedding_models": openai_embed},
        "grok": {"available": grok_avail, "models": grok_chat, "embedding_models": grok_embed},
        "deepseek": {"available": deepseek_avail, "models": deepseek_chat, "embedding_models": deepseek_embed},
        "bedrock": {"available": bedrock_avail, "models": bedrock_chat, "embedding_models": bedrock_embed},
    }

    # --- Flat list of all available models ---
    all_available = []
    for name, info in providers.items():
        if info["available"]:
            all_available.extend(info["models"])

    # --- Backward compat ---
    cloud_models = gemini_chat + anthropic_chat + openai_chat + grok_chat + deepseek_chat + BEDROCK_FALLBACK

    return {
        "providers": providers,
        "all_available": all_available,
        "local": ollama_chat,
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

        profiles = []
        next_token = None
        while True:
            kwargs: dict = {}
            if next_token:
                kwargs["nextToken"] = next_token
            resp = client.list_inference_profiles(**kwargs)
            print(f"Fetched {len(resp.get('inferenceProfileSummaries', []))} profiles from Bedrock")
            for s in resp.get("inferenceProfileSummaries") or []:
                if not isinstance(s, dict):
                    continue
                profiles.append(
                    {
                        "id": s.get("inferenceProfileId") or s.get("id") or "",
                        "arn": s.get("inferenceProfileArn") or s.get("arn") or "",
                        "name": s.get("inferenceProfileName") or s.get("name") or "",
                        "status": s.get("status") or "",
                        "type": s.get("type") or "",
                    }
                )
            next_token = resp.get("nextToken")
            if not next_token:
                break

        return sorted(profiles, key=lambda p: (p.get("name") or p.get("arn") or p.get("id") or ""))

    try:
        profiles = await asyncio.to_thread(_list_profiles_sync)
        return {"profiles": profiles}
    except Exception as e:
        error_msg = str(e)
        print(f"Error listing Bedrock inference profiles: {error_msg}")
        return {
            "profiles": [],
            "error": error_msg,
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


# --- Bulk Memory Clear ---

class MemoryClearRequest(BaseModel):
    items: List[Literal["chat_history", "orchestration_history", "agent_logs", "usage", "repos", "db_configs"]]


@router.post("/api/memory/clear")
async def clear_memory_items(req: MemoryClearRequest):
    """Clear selected memory/data categories in one request."""
    from core.usage_tracker import clear_usage_logs

    items = set(req.items)
    results = {}

    # Chat sessions
    if "chat_history" in items:
        session_state.clear()
        cleared = 0
        if os.path.isdir(_CHAT_SESSIONS_DIR):
            for fname in os.listdir(_CHAT_SESSIONS_DIR):
                if fname.endswith(".json"):
                    try:
                        os.remove(os.path.join(_CHAT_SESSIONS_DIR, fname))
                        cleared += 1
                    except Exception:
                        pass
        results["chat_history"] = f"Cleared {cleared} session(s)"

    # Orchestration run history
    if "orchestration_history" in items:
        count = 0
        for logs_dir in [
            Path(__file__).parent.parent.parent / "logs" / "orchestration_runs",
            Path(__file__).parent.parent.parent / "logs" / "orchestration_logs",
        ]:
            if logs_dir.is_dir():
                for f in logs_dir.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                            count += 1
                        except Exception:
                            pass
        results["orchestration_history"] = f"Cleared {count} file(s)"

    # Agent run logs
    if "agent_logs" in items:
        count = 0
        agent_logs_dir = Path(__file__).parent.parent.parent / "logs" / "agent_logs"
        if agent_logs_dir.is_dir():
            for f in agent_logs_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                        count += 1
                    except Exception:
                        pass
        results["agent_logs"] = f"Cleared {count} file(s)"

    # Usage logs
    if "usage" in items:
        count = clear_usage_logs()
        results["usage"] = f"Cleared {count} usage record(s)"

    # Repositories
    if "repos" in items:
        repos_path = os.path.join(DATA_DIR, "repos.json")
        repos = []
        if os.path.exists(repos_path):
            try:
                with open(repos_path) as f:
                    repos = json.load(f)
            except Exception:
                pass
        for repo in repos:
            try:
                from services.code_indexer import drop_index
                drop_index(repo["id"])
            except Exception as e:
                print(f"Error dropping index for repo {repo.get('id')}: {e}")
        with open(repos_path, "w") as f:
            json.dump([], f)
        results["repos"] = f"Cleared {len(repos)} repo(s)"

    # Database configurations
    if "db_configs" in items:
        configs_path = os.path.join(DATA_DIR, "db_configs.json")
        configs = []
        if os.path.exists(configs_path):
            try:
                with open(configs_path) as f:
                    configs = json.load(f)
            except Exception:
                pass
        with open(configs_path, "w") as f:
            json.dump([], f)
        results["db_configs"] = f"Cleared {len(configs)} config(s)"

    return {"status": "success", "cleared": results}
