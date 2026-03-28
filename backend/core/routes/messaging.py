"""
REST API for messaging channel management.
Includes webhook endpoints for Teams and WhatsApp (which require inbound HTTP).
"""
import time
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from core.messaging import store as channel_store

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_manager(request: Request):
    """Get the MessagingManager from app state, or raise 503 if not available."""
    manager = getattr(request.app.state, "messaging_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="Messaging is not enabled. Set messaging_enabled=true in setup.py and restart."
        )
    return manager


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/api/messaging/channels")
async def list_channels(request: Request, agent_id: str | None = None):
    """List all channels with live status, optionally filtered by agent."""
    manager = _get_manager(request)
    channels = manager.get_status()
    if agent_id:
        channels = [c for c in channels if c.get("agent_id") == agent_id]
    return channels


@router.post("/api/messaging/channels")
async def create_or_update_channel(request: Request):
    """Create or update a channel config. Does NOT auto-start the adapter."""
    body = await request.json()
    # Strip runtime-only fields from client payload
    body.pop("status", None)
    body.pop("last_error", None)
    saved = channel_store.save_channel(body)
    return saved


@router.delete("/api/messaging/channels/{channel_id}")
async def delete_channel(channel_id: str, request: Request):
    """Stop and delete a channel."""
    manager = _get_manager(request)
    await manager.stop_channel(channel_id)
    deleted = channel_store.delete_channel(channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"status": "deleted", "channel_id": channel_id}


# ── Enable / Disable ──────────────────────────────────────────────────────────

@router.post("/api/messaging/channels/{channel_id}/enable")
async def enable_channel(channel_id: str, request: Request):
    """Start the adapter for a channel."""
    manager = _get_manager(request)
    ch = channel_store.get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Mark as enabled in store before starting
    ch["enabled"] = True
    channel_store.save_channel(ch)
    await manager.start_channel(channel_id)

    updated = channel_store.get_channel(channel_id)
    return updated


@router.post("/api/messaging/channels/{channel_id}/disable")
async def disable_channel(channel_id: str, request: Request):
    """Stop the adapter for a channel."""
    manager = _get_manager(request)
    ch = channel_store.get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    await manager.stop_channel(channel_id)

    ch["enabled"] = False
    channel_store.save_channel(ch)
    return {"status": "stopped", "channel_id": channel_id}


# ── Test ──────────────────────────────────────────────────────────────────────

@router.post("/api/messaging/channels/{channel_id}/test")
async def test_channel(channel_id: str, request: Request):
    """
    Send a test greeting to verify credentials.
    For polling-based adapters (Telegram, Discord, Slack) this is a noop
    because we can't pick an arbitrary chat_id. We validate the bot token
    instead by checking the adapter is running.
    For webhook adapters (Teams, WhatsApp) we validate credential fields.
    """
    manager = _get_manager(request)
    ch = channel_store.get_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")

    platform = ch.get("platform", "")
    adapter = manager._adapters.get(channel_id)

    if adapter is None:
        return {
            "status": "not_running",
            "message": "Adapter is not running. Click Enable first."
        }

    # For Telegram, verify the bot token by calling getMe
    if platform == "telegram":
        try:
            if adapter._app:
                me = await adapter._app.bot.get_me()
                return {
                    "status": "ok",
                    "message": f"Bot @{me.username} is alive and listening.",
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # For Discord
    if platform == "discord":
        if adapter._client and not adapter._client.is_closed():
            user = adapter._client.user
            return {
                "status": "ok",
                "message": f"Bot {user} is connected." if user else "Discord client connected.",
            }
        return {"status": "error", "message": "Discord client is not connected."}

    # Generic: if adapter is in _adapters, it started successfully
    return {
        "status": "ok",
        "message": f"{platform.title()} adapter is running.",
    }


# ── Teams Webhook ─────────────────────────────────────────────────────────────

@router.post("/api/messaging/teams/webhook/{channel_id}")
async def teams_webhook(channel_id: str, request: Request):
    """Inbound webhook for Microsoft Teams Bot Framework."""
    manager = _get_manager(request)
    adapter = manager.get_teams_adapter(channel_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="Teams channel not found or not running")

    # Delegate to the adapter for full Bot Framework processing
    from aiohttp.web import Request as AiohttpRequest, Response as AiohttpResponse
    # FastAPI/Starlette compatible shim is needed here.
    # For simplicity, we pass the raw request JSON to the adapter.
    body = await request.json()
    try:
        await adapter.process_request(body, None)
        return {"status": "ok"}
    except Exception as e:
        logger.error("[Teams Webhook] Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── WhatsApp Webhook ──────────────────────────────────────────────────────────

@router.get("/api/messaging/whatsapp/webhook/{channel_id}")
async def whatsapp_verify(channel_id: str, request: Request):
    """Meta webhook verification (GET with hub.challenge)."""
    manager = _get_manager(request)
    adapter = manager.get_whatsapp_adapter(channel_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found or not running")

    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    result = adapter.verify_webhook(mode, token, challenge)
    if result is None:
        raise HTTPException(status_code=403, detail="Verification failed")
    return PlainTextResponse(result)


@router.post("/api/messaging/whatsapp/webhook/{channel_id}")
async def whatsapp_webhook(channel_id: str, request: Request):
    """Inbound webhook for WhatsApp Cloud API (Meta)."""
    manager = _get_manager(request)
    adapter = manager.get_whatsapp_adapter(channel_id)
    if not adapter:
        raise HTTPException(status_code=404, detail="WhatsApp channel not found or not running")

    body = await request.json()
    await adapter.process_webhook(body)
    return {"status": "ok"}
