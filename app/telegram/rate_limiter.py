"""Redis-backed rate limiter for outbound Telegram messages.

Enforces Telegram's limits:
- Per-chat: 1 message per second
- Per-bot: 30 messages per second

If Redis is unreachable, logs a warning and proceeds without limiting (degraded mode).
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)

_PER_CHAT_INTERVAL = 1.0       # seconds between sends to same chat
_PER_BOT_WINDOW = 1.0          # sliding window for per-bot count
_PER_BOT_LIMIT = 30            # max sends per bot per window


class TelegramRateLimiter:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def acquire(self, bot_id: UUID, chat_id: int) -> None:
        try:
            await self._acquire_per_chat(chat_id)
            await self._acquire_per_bot(bot_id)
        except Exception as exc:
            # Any Redis error falls through to degraded mode
            if not isinstance(exc, asyncio.CancelledError):
                logger.warning(
                    "Rate limiter Redis error (degraded mode, proceeding): %s", exc
                )

    async def _acquire_per_chat(self, chat_id: int) -> None:
        key = f"telegram:chat:{chat_id}:last_send"
        try:
            raw = self._redis.get(key)
            if raw is not None:
                last = float(raw)
                now = time.time()
                delta = now - last
                if delta < _PER_CHAT_INTERVAL:
                    await asyncio.sleep(_PER_CHAT_INTERVAL - delta)
            self._redis.set(key, str(time.time()), ex=10)
        except Exception:
            raise

    async def _acquire_per_bot(self, bot_id: UUID) -> None:
        key = f"telegram:bot:{bot_id}:sends"
        try:
            now = time.time()
            window_start = now - _PER_BOT_WINDOW
            # Remove entries older than the window
            self._redis.zremrangebyscore(key, "-inf", window_start)
            count = self._redis.zcard(key)
            if count >= _PER_BOT_LIMIT:
                # Find the oldest entry in the window and sleep until it expires
                oldest = self._redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_ts = oldest[0][1]
                    sleep_for = (oldest_ts + _PER_BOT_WINDOW) - now
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
            # Add current send with unique member (now + random suffix)
            member = f"{now}:{chat_id}"
            self._redis.zadd(key, {member: now})
            self._redis.expire(key, 10)
        except Exception:
            raise
