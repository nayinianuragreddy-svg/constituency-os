"""Outbound Telegram message sender.

Wraps python-telegram-bot's Bot.send_message with rate limiting.
Splits messages >4096 chars into multiple chunks (Telegram's hard limit).
"""

from __future__ import annotations

import logging
from uuid import UUID

from telegram import Bot
from telegram.error import TelegramError

from app.telegram.bot_config import BotConfig
from app.telegram.rate_limiter import TelegramRateLimiter

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LEN = 4096


class TelegramSendError(Exception):
    pass


class TelegramSender:
    def __init__(self, rate_limiter: TelegramRateLimiter) -> None:
        self._rate_limiter = rate_limiter

    async def send_message(self, bot_config: BotConfig, chat_id: int, text: str) -> int:
        """Send text to chat_id. Returns message_id of the last chunk sent."""
        if not text:
            raise TelegramSendError("Cannot send empty message")

        chunks = _split_text(text)
        bot = Bot(token=bot_config.bot_token)
        last_msg_id = 0

        async with bot:
            for chunk in chunks:
                await self._rate_limiter.acquire(bot_config.bot_id, chat_id)
                try:
                    msg = await bot.send_message(chat_id=chat_id, text=chunk)
                    last_msg_id = msg.message_id
                except TelegramError as exc:
                    raise TelegramSendError(f"Telegram send failed: {exc}") from exc

        return last_msg_id


def _split_text(text: str) -> list[str]:
    """Split text into chunks of at most _MAX_MESSAGE_LEN chars."""
    if len(text) <= _MAX_MESSAGE_LEN:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:_MAX_MESSAGE_LEN])
        text = text[_MAX_MESSAGE_LEN:]
    return chunks
