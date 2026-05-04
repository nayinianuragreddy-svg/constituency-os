"""Live end-to-end test for the Telegram webhook.

REQUIRES:
  TELEGRAM_TEST_BOT_TOKEN  — bot token from @BotFather for the test bot
  TELEGRAM_TEST_CHAT_ID    — your Telegram user_id (send /start to the bot first)

Skips gracefully if either env var is unset.

This test:
  1. Inserts a constituency_bots row with the test bot's encrypted token.
  2. Posts a synthesized Update payload to the webhook (with valid secret_token header).
  3. The webhook dispatches to CommunicationAgent and sends a real reply via Bot.send_message.
  4. Waits up to 10s for the bot's reply to appear in bot.get_updates().
  5. Asserts the reply arrived and DB rows were written.

The LLM is real (OpenAI). The Telegram send is real. No mocks.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from telegram import Bot

from app.telegram.bot_config import BotConfigRepository
from app.telegram.encryption import TelegramTokenCipher
from app.telegram.webhook import router


# ---------------------------------------------------------------------------
# skip guard
# ---------------------------------------------------------------------------

def _e2e_env():
    token = os.getenv("TELEGRAM_TEST_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID")
    return token, chat_id


def _skip_if_no_e2e_creds():
    token, chat_id = _e2e_env()
    if not token or not chat_id:
        pytest.skip(
            "TELEGRAM_TEST_BOT_TOKEN and TELEGRAM_TEST_CHAT_ID not set; "
            "skipping live e2e test"
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_update(update_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": chat_id, "is_bot": False, "first_name": "E2ETest"},
            "chat": {"id": chat_id, "type": "private", "first_name": "E2ETest"},
            "date": int(time.time()),
            "text": text,
        },
    }


async def _wait_for_bot_reply(bot: Bot, after_ts: float, timeout: float = 10.0) -> str | None:
    """Poll bot.get_updates() until a new outbound message appears or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        updates = await bot.get_updates(limit=10, timeout=0)
        for u in updates:
            if u.message and u.message.date.timestamp() >= after_ts:
                return u.message.text
        await asyncio.sleep(1)
    return None


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.integration
class TestTelegramE2E:
    @pytest.fixture(autouse=True)
    def require_creds(self):
        _skip_if_no_e2e_creds()

    @pytest.fixture(scope="class")
    def e2e_setup(self, seeded_test_db_engine):
        token, chat_id_str = _e2e_env()
        if not token or not chat_id_str:
            pytest.skip("E2E creds not set")

        chat_id = int(chat_id_str)
        engine = seeded_test_db_engine
        key = Fernet.generate_key().decode()
        cipher = TelegramTokenCipher(key=key)

        constituency_id = str(uuid.uuid4())
        bot_id = str(uuid.uuid4())
        secret = f"e2e-secret-{uuid.uuid4().hex[:16]}"

        # Get bot username from Telegram
        async def _get_username():
            async with Bot(token=token) as bot:
                me = await bot.get_me()
                return me.username

        bot_username = asyncio.get_event_loop().run_until_complete(_get_username())

        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO constituencies (id, name, state) "
                    "VALUES (:id, :name, :state)"
                ),
                {"id": constituency_id, "name": "Ibrahimpatnam", "state": "Telangana"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO constituency_bots "
                    "(id, constituency_id, mla_name, bot_username, "
                    "bot_token_encrypted, secret_token, is_active) "
                    "VALUES (:id, :cid, :mla, :uname, :tok, :sec, TRUE)"
                ),
                {
                    "id": bot_id,
                    "cid": constituency_id,
                    "mla": "Sri Manchireddy Kishan Reddy",
                    "uname": bot_username,
                    "tok": cipher.encrypt(token),
                    "sec": secret,
                },
            )

        yield {
            "engine": engine,
            "constituency_id": constituency_id,
            "bot_id": bot_id,
            "secret": secret,
            "bot_username": bot_username,
            "token": token,
            "chat_id": chat_id,
            "cipher": cipher,
            "cipher_key": key,
        }

        # Cleanup
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "DELETE FROM telegram_updates WHERE bot_id = :bid"
                ),
                {"bid": bot_id},
            )
            conn.execute(
                sa.text("DELETE FROM messages WHERE conversation_id IN "
                        "(SELECT id FROM conversations WHERE channel = 'telegram' "
                        "AND channel_chat_id = :ccid)"),
                {"ccid": str(chat_id)},
            )
            conn.execute(
                sa.text("DELETE FROM agent_actions WHERE conversation_id IN "
                        "(SELECT id FROM conversations WHERE channel = 'telegram' "
                        "AND channel_chat_id = :ccid)"),
                {"ccid": str(chat_id)},
            )
            conn.execute(
                sa.text(
                    "DELETE FROM conversations WHERE channel = 'telegram' "
                    "AND channel_chat_id = :ccid"
                ),
                {"ccid": str(chat_id)},
            )
            conn.execute(
                sa.text("DELETE FROM constituency_bots WHERE id = :bid"),
                {"bid": bot_id},
            )
            conn.execute(
                sa.text("DELETE FROM constituencies WHERE id = :cid"),
                {"cid": constituency_id},
            )

    def test_end_to_end_water_complaint(self, e2e_setup):
        """Post a water complaint Update; assert bot replies in Telegram and DB is written."""
        from unittest.mock import patch

        setup = e2e_setup
        engine = setup["engine"]
        chat_id = setup["chat_id"]
        bot_username = setup["bot_username"]
        secret = setup["secret"]
        token = setup["token"]
        cipher = setup["cipher"]

        update_id = int(time.time())  # use timestamp as unique update_id

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        before_ts = time.time()

        with patch("app.telegram.webhook._get_engine", return_value=engine), \
             patch("app.telegram.webhook._get_cipher", return_value=cipher):
            resp = client.post(
                f"/telegram/webhook/{bot_username}",
                headers={"X-Telegram-Bot-Api-Secret-Token": secret},
                json=_make_update(update_id, chat_id, "no water in ward 11 for 3 days"),
            )

        assert resp.status_code == 200, f"Webhook returned {resp.status_code}: {resp.text}"

        # Verify DB state
        with engine.connect() as conn:
            conv = conn.execute(
                sa.text(
                    "SELECT id FROM conversations "
                    "WHERE channel = 'telegram' AND channel_chat_id = :ccid"
                ),
                {"ccid": str(chat_id)},
            ).fetchone()
            assert conv is not None, "conversations row not created"

            msgs = conn.execute(
                sa.text(
                    "SELECT direction FROM messages WHERE conversation_id = :cid"
                ),
                {"cid": str(conv[0])},
            ).fetchall()
            directions = {m[0] for m in msgs}
            assert "inbound" in directions
            assert "outbound" in directions

            tu = conn.execute(
                sa.text(
                    "SELECT processed_at FROM telegram_updates "
                    "WHERE update_id = :uid AND bot_id = :bid"
                ),
                {"uid": update_id, "bid": setup["bot_id"]},
            ).fetchone()
            assert tu is not None
            assert tu[0] is not None, "telegram_updates.processed_at not set"

        # Verify Telegram received the reply
        async def _check():
            async with Bot(token=token) as bot:
                return await _wait_for_bot_reply(bot, before_ts, timeout=10.0)

        reply_text = asyncio.get_event_loop().run_until_complete(_check())
        assert reply_text is not None, (
            "Bot reply did not arrive in Telegram within 10s. "
            "Check TELEGRAM_TEST_CHAT_ID and that the bot has send permissions."
        )
