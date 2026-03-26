"""
Authentication routes (Google OAuth).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from services.google import get_auth_url, finish_auth

router = APIRouter()

REDIRECT_URI = "http://localhost:3000/auth/callback"


@router.get("/auth/login")
async def login():
    try:
        auth_url = get_auth_url(redirect_uri=REDIRECT_URI)
        return RedirectResponse(auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/callback")
async def callback(code: str):
    try:
        finish_auth(code=code, redirect_uri=REDIRECT_URI)
        return RedirectResponse("http://localhost:3000")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
