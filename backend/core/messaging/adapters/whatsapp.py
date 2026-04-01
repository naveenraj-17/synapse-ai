"""
WhatsApp adapter with two paths:

Path A — Meta Cloud API (official, requires Business account):
  Credentials: phone_number_id, access_token, verify_token
  Incoming: FastAPI webhook at /api/messaging/whatsapp/webhook/{channel_id}
  Outgoing: HTTPX call to Meta Graph API

Path B — Unofficial (Playwright-based, no Business account needed):
  Uses existing Playwright Chromium to drive WhatsApp Web.
  WARNING: This uses an unofficial approach and may violate WhatsApp ToS.
  The user must explicitly acknowledge the risk to enable this path.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from core.messaging.base import MessagingAdapter

if TYPE_CHECKING:
    from core.messaging.manager import MessagingManager

logger = logging.getLogger(__name__)

META_API_URL = "https://graph.facebook.com/v18.0"


class WhatsAppAdapter(MessagingAdapter):

    def __init__(self, channel: dict, manager: "MessagingManager"):
        super().__init__(channel, manager)
        creds = channel["credentials"]
        self.mode: str = creds.get("whatsapp_mode", "meta_api")  # "meta_api" | "unofficial"

        # Meta API credentials
        self.phone_number_id: str = creds.get("phone_number_id", "")
        self.access_token: str = creds.get("access_token", "")
        self.verify_token: str = creds.get("verify_token", "synapse_verify")

        # Unofficial mode
        self._playwright_task: asyncio.Task | None = None
        self._playwright_page = None
        self._browser = None
        self._playwright = None

    async def start(self) -> None:
        if self.mode == "meta_api":
            await self._start_meta()
        else:
            await self._start_unofficial()

    async def stop(self) -> None:
        if self.mode == "meta_api":
            self.manager.unregister_whatsapp_adapter(self.channel_id)
        else:
            await self._stop_unofficial()
        logger.info("[WhatsApp] Adapter stopped for channel %s", self.channel_id)

    # ------------------------------------------------------------------ #
    # Meta Cloud API path
    # ------------------------------------------------------------------ #

    async def _start_meta(self) -> None:
        if not self.phone_number_id or not self.access_token:
            raise ValueError(
                "WhatsApp Meta API requires phone_number_id and access_token."
            )
        # Register with manager so the webhook route can dispatch here
        self.manager.register_whatsapp_adapter(self.channel_id, self)
        logger.info(
            "[WhatsApp/Meta] Adapter ready for channel %s (webhook mode)",
            self.channel_id,
        )

    async def _send_raw(self, chat_id: str, text: str) -> None:
        if self.mode == "meta_api":
            await self._send_meta(chat_id, text)
        else:
            await self._send_unofficial(chat_id, text)

    async def _send_meta(self, to: str, text: str) -> None:
        if not text.strip():
            return
        try:
            import httpx
            url = f"{META_API_URL}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
        except Exception as e:
            logger.error("[WhatsApp/Meta] Send failed to %s: %s", to, e)

    async def process_webhook(self, data: dict) -> None:
        """Process an incoming webhook payload from Meta."""
        try:
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []):
                        if msg.get("type") != "text":
                            continue
                        from_number = msg["from"]
                        text = msg["text"]["body"]
                        session_id = f"whatsapp_{self.channel_id}_{from_number}"
                        await self._dispatch(from_number, text, from_number, session_id)
        except Exception as e:
            logger.error("[WhatsApp/Meta] Webhook processing error: %s", e)

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Verify the Meta webhook subscription."""
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        return None

    # ------------------------------------------------------------------ #
    # Unofficial Playwright path
    # ------------------------------------------------------------------ #

    async def _start_unofficial(self) -> None:
        logger.warning(
            "[WhatsApp/Unofficial] Starting unofficial mode for channel %s. "
            "This uses Playwright to drive WhatsApp Web. "
            "Use at your own risk — may violate WhatsApp ToS.",
            self.channel_id,
        )
        self._playwright_task = asyncio.create_task(self._run_playwright_session())

    async def _run_playwright_session(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "[WhatsApp/Unofficial] Playwright not available. "
                "Install it or use Meta API path."
            )
            return

        try:
            playwright = await async_playwright().start()
            self._playwright = playwright

            # Launch browser with persistent context to preserve WhatsApp Web session
            from core.config import DATA_DIR
            import os
            user_data_dir = os.path.join(DATA_DIR, "whatsapp_sessions", self.channel_id)
            os.makedirs(user_data_dir, exist_ok=True)

            browser = await playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,  # WhatsApp Web requires non-headless for QR
                args=["--no-sandbox"],
            )
            self._browser = browser

            page = await browser.new_page()
            self._playwright_page = page

            await page.goto("https://web.whatsapp.com")
            logger.info(
                "[WhatsApp/Unofficial] WhatsApp Web opened for channel %s. "
                "Scan the QR code in the browser to authenticate.",
                self.channel_id,
            )

            # Wait for QR to be scanned (up to 5 minutes)
            try:
                await page.wait_for_selector('[data-testid="default-user"]', timeout=300_000)
                logger.info("[WhatsApp/Unofficial] Authenticated for channel %s", self.channel_id)
            except Exception:
                logger.warning("[WhatsApp/Unofficial] QR scan timed out for channel %s", self.channel_id)
                return

            # Polling loop to check for new messages
            # NOTE: Full message interception would require MutationObserver injection.
            # This is a simplified placeholder — real implementation would inject JS
            # to listen to DOM changes and call back to the Python side.
            logger.info(
                "[WhatsApp/Unofficial] Message polling not fully implemented. "
                "This path is experimental."
            )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[WhatsApp/Unofficial] Error: %s", e)

    async def _stop_unofficial(self) -> None:
        if self._playwright_task:
            self._playwright_task.cancel()
            try:
                await self._playwright_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

    async def _send_unofficial(self, to: str, text: str) -> None:
        logger.warning("[WhatsApp/Unofficial] Proactive send not implemented.")
