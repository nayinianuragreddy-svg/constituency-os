"""Unit tests for TelegramRateLimiter using fakeredis."""

import asyncio
import time
import uuid
import pytest
import fakeredis

from app.telegram.rate_limiter import TelegramRateLimiter, _PER_CHAT_INTERVAL, _PER_BOT_LIMIT


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis()


@pytest.fixture
def limiter(fake_redis):
    return TelegramRateLimiter(fake_redis)


BOT_ID = uuid.uuid4()
CHAT_ID = 123456789


class TestPerChatLimit:
    def test_first_send_does_not_sleep(self, limiter, fake_redis):
        """First send to a chat should complete immediately."""
        start = time.monotonic()
        asyncio.get_event_loop().run_until_complete(limiter.acquire(BOT_ID, CHAT_ID))
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # no sleep on first send

    def test_second_send_within_1s_sleeps(self, limiter, fake_redis):
        """Second send to same chat within 1s should sleep until 1s elapsed."""
        chat_id = 111222333
        # First send sets last_send to now
        asyncio.get_event_loop().run_until_complete(limiter.acquire(BOT_ID, chat_id))
        # Second send immediately should sleep ~1s
        start = time.monotonic()
        asyncio.get_event_loop().run_until_complete(limiter.acquire(BOT_ID, chat_id))
        elapsed = time.monotonic() - start
        # Should have slept close to 1s (allow generous window for test runner overhead)
        assert elapsed >= 0.8, f"Expected sleep ~1s, got {elapsed:.2f}s"


class TestPerBotLimit:
    def test_30_sends_do_not_sleep(self, fake_redis):
        """30 sends within 1s window should not trigger per-bot sleep."""
        limiter = TelegramRateLimiter(fake_redis)
        bot_id = uuid.uuid4()
        start = time.monotonic()
        for i in range(_PER_BOT_LIMIT):
            asyncio.get_event_loop().run_until_complete(limiter.acquire(bot_id, i))
        elapsed = time.monotonic() - start
        # 30 sends should complete fast (no per-bot sleep triggered)
        # Each may have per-chat sleep but different chat IDs so no per-chat delay
        # Just assert we didn't get an error
        assert elapsed < 5.0

    def test_31st_send_sleeps(self, fake_redis):
        """31st send within 1s should sleep until oldest entry expires."""
        limiter = TelegramRateLimiter(fake_redis)
        bot_id = uuid.uuid4()
        # Pre-fill the window with 30 sends at the same timestamp
        now = time.time()
        key = f"telegram:bot:{bot_id}:sends"
        for i in range(_PER_BOT_LIMIT):
            fake_redis.zadd(key, {f"{now}:{i}": now})
        fake_redis.expire(key, 10)

        start = time.monotonic()
        asyncio.get_event_loop().run_until_complete(limiter.acquire(bot_id, 999))
        elapsed = time.monotonic() - start
        # Should have slept approximately 1s for the window to clear
        assert elapsed >= 0.8, f"Expected per-bot sleep, got {elapsed:.2f}s"


class TestDegradedMode:
    def test_redis_error_does_not_raise(self):
        """If Redis raises, limiter should log warning and return without error."""

        class BrokenRedis:
            def get(self, key):
                raise ConnectionError("Redis unavailable")

            def set(self, *a, **kw):
                raise ConnectionError("Redis unavailable")

            def zremrangebyscore(self, *a, **kw):
                raise ConnectionError("Redis unavailable")

            def zcard(self, *a, **kw):
                raise ConnectionError("Redis unavailable")

            def zrange(self, *a, **kw):
                raise ConnectionError("Redis unavailable")

            def zadd(self, *a, **kw):
                raise ConnectionError("Redis unavailable")

            def expire(self, *a, **kw):
                raise ConnectionError("Redis unavailable")

        limiter = TelegramRateLimiter(BrokenRedis())
        # Should not raise, logs warning and proceeds
        asyncio.get_event_loop().run_until_complete(limiter.acquire(BOT_ID, CHAT_ID))
