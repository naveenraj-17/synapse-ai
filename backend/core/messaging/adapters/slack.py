"""
Slack adapter using slack-bolt >= 1.18 with Socket Mode.
No public URL required — uses an outbound WebSocket connection to Slack.

Required Slack App permissions:
  Bot Token Scopes: app_mentions:read, channels:history, chat:write, im:history, im:write
  Event Subscriptions: message.im, app_mention
  Socket Mode: enabled (generates App-Level Token with connections:write scope)
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from core.messaging.base import MessagingAdapter

if TYPE_CHECKING:
    from core.messaging.manager import MessagingManager

logger = logging.getLogger(__name__)


class SlackAdapter(MessagingAdapter):

    def __init__(self, channel: dict, manager: "MessagingManager"):
        super().__init__(channel, manager)
        self._handler = None
        self._task: asyncio.Task | None = None
        creds = channel["credentials"]
        self.bot_token: str = creds["bot_token"]   # xoxb-...
        self.app_token: str = creds["app_token"]   # xapp-...

    async def start(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        except ImportError:
            raise RuntimeError(
                "slack-bolt is not installed. Enable messaging in setup to install it."
            )

        app = AsyncApp(token=self.bot_token)

        # ── Event: direct messages ──────────────────────────────────────
        @app.event("message")
        async def handle_dm(event, say, client):
            # Only handle DMs (channel_type == "im")
            if event.get("channel_type") != "im":
                return
            if event.get("bot_id"):  # ignore bot messages
                return

            chat_id = event["channel"]
            user_id = event.get("user", chat_id)
            text = event.get("text", "").strip()
            session_id = f"slack_{self.channel_id}_{chat_id}_{user_id}"

            if text.startswith("/"):
                parts = text.split(" ", 1)
                consumed = await self._handle_command(
                    chat_id, parts[0], parts[1] if len(parts) > 1 else "", session_id
                )
                if consumed:
                    return

            # Show typing indicator (Slack doesn't have a built-in typing indicator
            # via events API, so we just proceed)
            await self._dispatch(chat_id, text, user_id, session_id)

        # ── Event: @mentions in channels ────────────────────────────────
        @app.event("app_mention")
        async def handle_mention(event, say, client):
            chat_id = event["channel"]
            user_id = event.get("user", chat_id)
            # Strip the bot mention
            text = event.get("text", "")
            # Remove <@BOTID> prefix
            import re
            text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
            session_id = f"slack_{self.channel_id}_{chat_id}_{user_id}"

            if text.startswith("/"):
                parts = text.split(" ", 1)
                consumed = await self._handle_command(
                    chat_id, parts[0], parts[1] if len(parts) > 1 else "", session_id
                )
                if consumed:
                    return

            await self._dispatch(chat_id, text, user_id, session_id)

        self._slack_app = app
        handler = AsyncSocketModeHandler(app, self.app_token)
        self._handler = handler

        async def _run():
            logger.info("[Slack] Starting Socket Mode for channel %s", self.channel_id)
            await handler.start_async()

        self._task = asyncio.create_task(_run())
        logger.info("[Slack] Adapter started for channel %s", self.channel_id)

    async def stop(self) -> None:
        if self._handler:
            try:
                await self._handler.close_async()
            except Exception as e:
                logger.warning("[Slack] Stop error: %s", e)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("[Slack] Adapter stopped for channel %s", self.channel_id)

    async def _send_raw(self, chat_id: str, text: str) -> None:
        if not self._slack_app or not text.strip():
            return
        await self._slack_app.client.chat_postMessage(
            channel=chat_id,
            text=text,
            mrkdwn=True,
        )
