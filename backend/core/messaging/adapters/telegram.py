"""
Telegram adapter using python-telegram-bot >= 20 (async long-polling).
No public URL required — polling is outbound-only.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from core.messaging.base import MessagingAdapter

if TYPE_CHECKING:
    from core.messaging.manager import MessagingManager

logger = logging.getLogger(__name__)


class TelegramAdapter(MessagingAdapter):

    def __init__(self, channel: dict, manager: "MessagingManager"):
        super().__init__(channel, manager)
        self._app = None
        self._task: asyncio.Task | None = None
        self.bot_token: str = channel["credentials"]["bot_token"]

    async def start(self) -> None:
        try:
            from telegram.ext import Application, MessageHandler, CommandHandler, filters
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot is not installed. "
                "Enable messaging in setup to install it."
            )

        app = (
            Application.builder()
            .token(self.bot_token)
            .build()
        )
        self._app = app

        # Register command handlers
        for cmd in ["start", "help", "reset", "agents"]:
            app.add_handler(CommandHandler(cmd, self._on_command))
        app.add_handler(CommandHandler("agent", self._on_command))

        # Register plain text handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

        async def _run():
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            logger.info("[Telegram] Polling started for channel %s", self.channel_id)
            # Keep running until stopped
            while True:
                await asyncio.sleep(3600)

        self._task = asyncio.create_task(_run())
        logger.info("[Telegram] Adapter started for channel %s", self.channel_id)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning("[Telegram] Stop error: %s", e)
        logger.info("[Telegram] Adapter stopped for channel %s", self.channel_id)

    async def _send_raw(self, chat_id: str, text: str) -> None:
        from telegram.constants import ParseMode
        if not self._app or not text.strip():
            return
        await self._app.bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #

    async def _on_command(self, update, context) -> None:
        if not update.message:
            return
        msg = update.message
        chat_id = str(msg.chat_id)
        # Full text like "/agent MyBot" → command="/agent", args="MyBot"
        text = msg.text or ""
        parts = text.split(" ", 1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        session_id = f"telegram_{self.channel_id}_{chat_id}"
        await self._handle_command(chat_id, command, args, session_id)

    async def _on_message(self, update, context) -> None:
        if not update.message or not update.message.text:
            return
        msg = update.message
        chat_id = str(msg.chat_id)
        user_id = str(msg.from_user.id) if msg.from_user else chat_id
        session_id = f"telegram_{self.channel_id}_{chat_id}"

        # Show typing indicator
        try:
            await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
        except Exception:
            pass

        await self._dispatch(chat_id, msg.text, user_id, session_id)
