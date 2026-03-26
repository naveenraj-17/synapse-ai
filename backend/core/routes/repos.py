"""
Repo management endpoints (CRUD + reindex).
"""
import os
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from core.models import Repo
from core.config import DATA_DIR
from core.json_store import JsonStore

router = APIRouter()

_repos_store = JsonStore(os.path.join(DATA_DIR, "repos.json"))


def load_repos() -> list[dict]:
    return _repos_store.load()


def save_repos(repos: list[dict]):
    _repos_store.save(repos)

@router.get("/api/repos")
async def get_repos():
    # Update statuses if needed or simply return
    repos = load_repos()
    
    # Reconcile status from the actual DB state for ALL repos
    try:
        from services.code_indexer import get_index_status
        updated = False
        for r in repos:
            stats = get_index_status(r["id"])
            if stats["status"] == "indexed":
                if r.get("status") != "indexed" or r.get("file_count") != stats["count"]:
                    r["status"] = "indexed"
                    r["file_count"] = stats["count"]
                    updated = True
            elif stats["status"] == "error":
                if r.get("status") != "error":
                    r["status"] = "error"
                    updated = True
        # Persist corrected statuses so tools/agents see the right state
        if updated:
            save_repos(repos)
    except ImportError:
        pass

    return repos

@router.post("/api/repos")
async def create_repo(repo: Repo, background_tasks: BackgroundTasks):
    repos = load_repos()
    for i, r in enumerate(repos):
        if r["id"] == repo.id:
            repos[i] = repo.dict()
            save_repos(repos)
            return repo

    repos.append(repo.dict())
    save_repos(repos)

    # Auto-index new repos if path exists
    if os.path.isdir(repo.path):
        try:
            from services.code_indexer import run_index
            for r in repos:
                if r["id"] == repo.id:
                    r["status"] = "indexing"
                    break
            save_repos(repos)
            background_tasks.add_task(run_index, repo.id, repo.path, repo.included_patterns, repo.excluded_patterns)
        except ImportError:
            pass

    return repo

@router.delete("/api/repos/{repo_id}")
async def delete_repo(repo_id: str):
    repos = load_repos()
    repos = [r for r in repos if r["id"] != repo_id]
    save_repos(repos)
    # TODO: also drop table in DB via code_indexer.drop_index(repo_id)
    try:
        from services.code_indexer import drop_index
        drop_index(repo_id)
    except Exception as e:
        print(f"Error dropping index for repo {repo_id}: {e}")
    return {"status": "success"}

@router.post("/api/repos/{repo_id}/reindex")
async def reindex_repo(repo_id: str, background_tasks: BackgroundTasks):
    repos = load_repos()
    repo = next((r for r in repos if r["id"] == repo_id), None)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    if repo.get("status") == "indexing":
        raise HTTPException(status_code=409, detail="Repo is already being indexed")

    if not os.path.isdir(repo.get("path", "")):
        raise HTTPException(status_code=400, detail=f"Repo path does not exist: {repo.get('path')}")

    # Set status
    repo["status"] = "indexing"
    for i, r in enumerate(repos):
        if r["id"] == repo_id:
            repos[i] = repo
            break
    save_repos(repos)
    
    # Run in background
    try:
        from services.code_indexer import run_index
        background_tasks.add_task(run_index, repo_id, repo["path"], repo["included_patterns"], repo["excluded_patterns"])
    except ImportError as e:
        print("Indexer unavailable:", e)
        repo["status"] = "error"
        save_repos(repos)
        raise HTTPException(status_code=500, detail="Indexer service not available")

    return {"status": "indexing_started"}
