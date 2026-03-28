"""
Authentication routes (Google OAuth).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from services.google import get_auth_url, finish_auth

router = APIRouter()

# This must match exactly what's registered in your Google Cloud Console
# OAuth 2.0 Client → Authorized redirect URIs.
# Add "http://localhost:8000/auth/callback" to your OAuth app in Google Cloud Console.
REDIRECT_URI = "http://localhost:8000/auth/callback"


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
        return RedirectResponse("http://localhost:3000?google_auth=success")
    except Exception as e:
        return RedirectResponse(f"http://localhost:3000?google_auth=error&reason={str(e)}")
