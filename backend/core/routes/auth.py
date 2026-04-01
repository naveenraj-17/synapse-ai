"""
Authentication routes (Google OAuth).
"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from services.google import get_auth_url, finish_auth

router = APIRouter()

# Read ports from env so they always match the running servers.
_BACKEND_PORT = int(os.getenv("SYNAPSE_BACKEND_PORT", "8000"))
_FRONTEND_PORT = int(os.getenv("SYNAPSE_FRONTEND_PORT", "3000"))

# This must match exactly what's registered in your Google Cloud Console
# OAuth 2.0 Client → Authorized redirect URIs.
# Add "http://localhost:<SYNAPSE_BACKEND_PORT>/auth/callback" to your OAuth app.
REDIRECT_URI = f"http://localhost:{_BACKEND_PORT}/auth/callback"
_FRONTEND_BASE = f"http://localhost:{_FRONTEND_PORT}"


@router.get("/auth/login")
async def login():
    try:
        auth_url = get_auth_url(redirect_uri=REDIRECT_URI)
        return RedirectResponse(auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/callback")
async def callback(code: str, state: str = None):
    try:
        finish_auth(code=code, redirect_uri=REDIRECT_URI)
        # Redirect back to the frontend with a success flag so the UI can refresh
        return RedirectResponse(f"{_FRONTEND_BASE}?google_auth=success")
    except Exception as e:
        return RedirectResponse(f"{_FRONTEND_BASE}?google_auth=error&reason={str(e)}")
