"""
Discord adapter using discord.py >= 2.3.
No public URL required — uses a persistent websocket connection to Discord.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from core.messaging.base import MessagingAdapter

if TYPE_CHECKING:
    from core.messaging.manager import MessagingManager

logger = logging.getLogger(__name__)


class DiscordAdapter(MessagingAdapter):

    def __init__(self, channel: dict, manager: "MessagingManager"):
        super().__init__(channel, manager)
        self._client = None
        self._task: asyncio.Task | None = None
        creds = channel["credentials"]
        self.bot_token: str = creds["bot_token"]
        # Optional: restrict to a specific Discord channel ID
        self.restrict_channel_id: str | None = creds.get("channel_id")

    async def start(self) -> None:
        try:
            import discord
        except ImportError:
            raise RuntimeError(
                "discord.py is not installed. Enable messaging in setup to install it."
            )

        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready():
            logger.info("[Discord] Logged in as %s for channel %s",
                        client.user, self.channel_id)

        @client.event
        async def on_message(message: discord.Message):
            # Ignore own messages
            if message.author == client.user:
                return
            # Restrict to specific channel if configured
            if self.restrict_channel_id and str(message.channel.id) != self.restrict_channel_id:
                return
            # Only respond to DMs OR @mentions in servers
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mention = client.user in message.mentions
            if not is_dm and not is_mention:
                return

            chat_id = str(message.channel.id)
            user_id = str(message.author.id)
            session_id = f"discord_{self.channel_id}_{chat_id}_{user_id}"

            # Strip bot mention from text
            text = message.content
            if client.user:
                text = text.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()

            # Check for commands
            if text.startswith("/"):
                parts = text.split(" ", 1)
                consumed = await self._handle_command(
                    chat_id, parts[0], parts[1] if len(parts) > 1 else "", session_id
                )
                if consumed:
                    return

            # Show typing indicator
            async with message.channel.typing():
                await self._dispatch(chat_id, text, user_id, session_id)

        async def _run():
            await client.start(self.bot_token)

        self._task = asyncio.create_task(_run())
        logger.info("[Discord] Adapter started for channel %s", self.channel_id)

    async def stop(self) -> None:
        if self._client and not self._client.is_closed():
            await self._client.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("[Discord] Adapter stopped for channel %s", self.channel_id)

    async def _send_raw(self, chat_id: str, text: str) -> None:
        if not self._client or not text.strip():
            return
        channel = self._client.get_channel(int(chat_id))
        if channel is None:
            try:
                channel = await self._client.fetch_channel(int(chat_id))
            except Exception as e:
                logger.error("[Discord] Cannot fetch channel %s: %s", chat_id, e)
                return
        await channel.send(text)
