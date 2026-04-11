"""
Vault management REST API.

Handles CRUD operations on the user-managed vault directory (data/vault/ minus the
auto-generated tool_outputs/ subfolder).  Only .json and .md files may be created.
"""
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.config import DATA_DIR

router = APIRouter()

# Root directory exposed to the frontend
VAULT_USER_DIR = Path(DATA_DIR) / "vault"
_EXCLUDED = set()
_ALLOWED_EXTENSIONS = {".json", ".md", ".txt"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vault_root() -> Path:
    VAULT_USER_DIR.mkdir(parents=True, exist_ok=True)
    return VAULT_USER_DIR


def _resolve(rel: str) -> Path:
    """Resolve a relative vault path to an absolute path, preventing traversal."""
    root = _vault_root()
    # Strip leading slashes/dots from the client-supplied path
    clean = rel.lstrip("/").lstrip("./")
    resolved = (root / clean).resolve()
    # Ensure it stays inside the vault root
    if not str(resolved).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    return resolved


def _is_excluded(path: Path) -> bool:
    """Return True if the path is inside an excluded subfolder."""
    root = _vault_root().resolve()
    rel = path.resolve().relative_to(root)
    parts = rel.parts
    return len(parts) > 0 and parts[0] in _EXCLUDED


def _build_tree(directory: Path, root: Path) -> list[dict]:
    """Recursively build a file/folder tree, excluding _EXCLUDED dirs."""
    items: list[dict] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return items

    for entry in entries:
        if entry.name.startswith("."):
            continue
        rel_path = str(entry.resolve().relative_to(root.resolve()))
        if entry.is_dir():
            if entry.name in _EXCLUDED:
                continue
            items.append({
                "name": entry.name,
                "path": rel_path,
                "type": "folder",
                "children": _build_tree(entry, root),
            })
        elif entry.is_file():
            items.append({
                "name": entry.name,
                "path": rel_path,
                "type": "file",
                "ext": entry.suffix.lower(),
            })
    return items


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/vault/tree")
async def get_vault_tree():
    """Return the full directory tree beneath the user vault root."""
    root = _vault_root()
    return {"tree": _build_tree(root, root)}


@router.get("/api/vault/search")
async def search_vault_files(q: str = Query(default="", description="Search query")):
    """Search vault files by name (for @ mention autocomplete)."""
    root = _vault_root()
    results: list[dict] = []
    q_lower = q.strip().lower()

    for p in root.rglob("*"):
        if p.is_file() and not _is_excluded(p):
            if not q_lower or q_lower in p.name.lower():
                rel = str(p.resolve().relative_to(root.resolve()))
                results.append({
                    "name": p.name,
                    "path": rel,
                    "ext": p.suffix.lower(),
                })
            if len(results) >= 20:
                break

    return {"files": results}


@router.get("/api/vault/file")
async def get_vault_file(path: str = Query(..., description="Relative path to vault file")):
    """Return the content of a vault file."""
    p = _resolve(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if _is_excluded(p):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        content = p.read_text(encoding="utf-8")
        return {"path": path, "name": p.name, "ext": p.suffix.lower(), "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateFileRequest(BaseModel):
    path: str          # relative parent folder path (empty = vault root)
    name: str          # filename including extension (.json or .md)
    content: Optional[str] = ""


@router.post("/api/vault/file")
async def create_vault_file(req: CreateFileRequest):
    """Create a new .json or .md file in the vault."""
    suffix = Path(req.name).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Only {', '.join(_ALLOWED_EXTENSIONS)} files are allowed")

    parent = _resolve(req.path) if req.path.strip() else _vault_root()
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="Parent path is not a directory")
    if _is_excluded(parent):
        raise HTTPException(status_code=403, detail="Cannot create files in excluded directories")

    target = parent / req.name
    if target.exists():
        raise HTTPException(status_code=409, detail="File already exists")

    # Provide sensible default content
    initial_content = req.content or ""
    if not initial_content:
        if suffix == ".json":
            initial_content = "{}\n"
        elif suffix == ".txt":
            initial_content = ""
        else:
            initial_content = f"# {Path(req.name).stem}\n\n"

    try:
        target.write_text(initial_content, encoding="utf-8")
        root = _vault_root()
        rel = str(target.resolve().relative_to(root.resolve()))
        return {"path": rel, "name": target.name, "ext": suffix, "content": initial_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateFileRequest(BaseModel):
    path: str
    content: str


@router.put("/api/vault/file")
async def update_vault_file(req: UpdateFileRequest):
    """Update the content of an existing vault file."""
    p = _resolve(req.path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if _is_excluded(p):
        raise HTTPException(status_code=403, detail="Access denied")
    if p.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Cannot edit this file type")
    try:
        p.write_text(req.content, encoding="utf-8")
        return {"status": "ok", "path": req.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateFolderRequest(BaseModel):
    path: str    # relative parent path (empty = vault root)
    name: str    # new folder name


@router.post("/api/vault/folder")
async def create_vault_folder(req: CreateFolderRequest):
    """Create a new folder inside the vault."""
    if req.name in _EXCLUDED:
        raise HTTPException(status_code=400, detail="Reserved folder name")

    parent = _resolve(req.path) if req.path.strip() else _vault_root()
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="Parent path is not a directory")
    if _is_excluded(parent):
        raise HTTPException(status_code=403, detail="Cannot create folders in excluded directories")

    target = parent / req.name
    if target.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")

    try:
        target.mkdir(parents=True)
        root = _vault_root()
        rel = str(target.resolve().relative_to(root.resolve()))
        return {"path": rel, "name": req.name, "type": "folder"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DeleteItemRequest(BaseModel):
    path: str


@router.delete("/api/vault/item")
async def delete_vault_item(req: DeleteItemRequest):
    """Delete a file or folder (recursive) from the vault."""
    p = _resolve(req.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if _is_excluded(p):
        raise HTTPException(status_code=403, detail="Cannot delete system directories")

    # Prevent deleting a direct child that matches an excluded name
    root = _vault_root().resolve()
    rel_parts = p.resolve().relative_to(root).parts
    if len(rel_parts) == 1 and rel_parts[0] in _EXCLUDED:
        raise HTTPException(status_code=403, detail="Cannot delete system directories")

    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"status": "ok", "path": req.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
