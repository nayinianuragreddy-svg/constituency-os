"""Integration tests for the Telegram webhook handler.

Uses synthesized Update payloads and a mocked TelegramSender.
No real Telegram API calls. No live LLM calls.
Marker: @pytest.mark.integration (no live).

The webhook is tested via FastAPI's TestClient. TelegramSender is patched
at the module level so no actual Telegram send occurs.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.telegram.bot_config import BotConfig, BotConfigRepository
from app.telegram.encryption import TelegramTokenCipher
from app.telegram.webhook import router


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_update(update_id: int, chat_id: int, text: str, message_id: int = 1) -> dict:
    """Build a minimal Telegram Update payload."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private", "first_name": "Test"},
            "date": int(time.time()),
            "text": text,
        },
    }


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cipher():
    return TelegramTokenCipher(key=Fernet.generate_key().decode())


@pytest.fixture(scope="module")
def webhook_test_db(seeded_test_db_engine, cipher):
    """Insert test bot + constituency rows; yield row info; clean up."""
    engine = seeded_test_db_engine
    constituency_id = str(uuid.uuid4())
    bot_id = str(uuid.uuid4())
    secret = "wh-test-secret-token-12345"
    bot_username = "WebhookTestBot"
    token_plain = "9999999999:TESTTOKEN"

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
                "tok": cipher.encrypt(token_plain),
                "sec": secret,
            },
        )

    yield {
        "engine": engine,
        "constituency_id": constituency_id,
        "bot_id": bot_id,
        "secret": secret,
        "bot_username": bot_username,
        "token_plain": token_plain,
    }

    with engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM telegram_updates WHERE bot_id = :bid"),
            {"bid": bot_id},
        )
        conn.execute(
            sa.text("DELETE FROM constituency_bots WHERE id = :bid"),
            {"bid": bot_id},
        )
        conn.execute(
            sa.text("DELETE FROM constituencies WHERE id = :cid"),
            {"cid": constituency_id},
        )


@pytest.fixture
def app():
    return _make_app()


@pytest.fixture
def client(app):
    return TestClient(app)


# ---------------------------------------------------------------------------
# patch helpers
# ---------------------------------------------------------------------------

def _mock_agent_result(reply_text: str = "Test reply from agent"):
    from app.agents.base import AgentResult
    result = AgentResult(
        reply_text=reply_text,
        tool_calls_made=[],
        cost_usd=0.0001,
        hops_used=1,
        escalated=False,
        error=None,
    )
    return result


def _patch_dispatch(reply_text="Test reply from agent"):
    """Patch CommunicationAgent.dispatch to return a fake result."""
    return patch(
        "app.telegram.webhook.CommunicationAgent.dispatch",
        return_value=_mock_agent_result(reply_text),
    )


def _patch_sender(sent_msg_id: int = 42):
    """Patch TelegramSender.send_message to record calls without sending."""
    mock = AsyncMock(return_value=sent_msg_id)
    return patch("app.telegram.webhook.TelegramSender.send_message", mock), mock


def _patch_engine(db):
    """Patch _get_engine to return the test engine."""
    return patch("app.telegram.webhook._get_engine", return_value=db["engine"])


def _patch_cipher(test_cipher):
    return patch("app.telegram.webhook._get_cipher", return_value=test_cipher)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHappyPath:
    def test_new_conversation_dispatches_and_replies(self, client, webhook_test_db, cipher):
        db = webhook_test_db
        chat_id = 700100001
        update_id = 900001

        with _patch_engine(db), _patch_cipher(cipher), _patch_dispatch() as mock_dispatch:
            sender_ctx, mock_send = _patch_sender()
            with sender_ctx:
                resp = client.post(
                    f"/telegram/webhook/{db['bot_username']}",
                    headers={"X-Telegram-Bot-Api-Secret-Token": db["secret"]},
                    json=_make_update(update_id, chat_id, "no water for 3 days"),
                )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_dispatch.assert_called_once()
        mock_send.assert_called_once()

        # Verify DB rows
        engine = db["engine"]
        with engine.connect() as conn:
            # conversations row created
            conv = conn.execute(
                sa.text(
                    "SELECT id, session_state FROM conversations "
                    "WHERE channel = 'telegram' AND channel_chat_id = :ccid"
                ),
                {"ccid": str(chat_id)},
            ).fetchone()
            assert conv is not None
            assert conv[1] == "active"

            # inbound + outbound messages
            msgs = conn.execute(
                sa.text(
                    "SELECT direction FROM messages WHERE conversation_id = :cid "
                    "ORDER BY created_at"
                ),
                {"cid": str(conv[0])},
            ).fetchall()
            directions = [m[0] for m in msgs]
            assert "inbound" in directions
            assert "outbound" in directions

            # telegram_updates row marked processed
            tu = conn.execute(
                sa.text(
                    "SELECT processed_at FROM telegram_updates "
                    "WHERE update_id = :uid AND bot_id = :bid"
                ),
                {"uid": update_id, "bid": db["bot_id"]},
            ).fetchone()
            assert tu is not None
            assert tu[0] is not None  # processed_at set


@pytest.mark.integration
class TestDeduplication:
    def test_duplicate_update_not_reprocessed(self, client, webhook_test_db, cipher):
        db = webhook_test_db
        chat_id = 700100002
        update_id = 900002

        dispatch_call_count = 0

        def counting_dispatch(ctx):
            nonlocal dispatch_call_count
            dispatch_call_count += 1
            return _mock_agent_result()

        with _patch_engine(db), _patch_cipher(cipher):
            with patch("app.telegram.webhook.CommunicationAgent.dispatch", side_effect=counting_dispatch):
                sender_ctx, mock_send = _patch_sender()
                with sender_ctx:
                    # First call
                    r1 = client.post(
                        f"/telegram/webhook/{db['bot_username']}",
                        headers={"X-Telegram-Bot-Api-Secret-Token": db["secret"]},
                        json=_make_update(update_id, chat_id, "test dedup"),
                    )
                    # Second call with same update_id
                    r2 = client.post(
                        f"/telegram/webhook/{db['bot_username']}",
                        headers={"X-Telegram-Bot-Api-Secret-Token": db["secret"]},
                        json=_make_update(update_id, chat_id, "test dedup"),
                    )

        assert r1.status_code == 200
        assert r2.status_code == 200
        # Agent dispatched only once
        assert dispatch_call_count == 1
        # Message sent only once
        assert mock_send.call_count == 1


@pytest.mark.integration
class TestAuthFailures:
    def test_missing_secret_token_returns_401(self, client, webhook_test_db, cipher):
        db = webhook_test_db
        with _patch_engine(db), _patch_cipher(cipher):
            resp = client.post(
                f"/telegram/webhook/{db['bot_username']}",
                json=_make_update(999901, 700200001, "hello"),
            )
        assert resp.status_code == 401

    def test_invalid_secret_token_returns_401(self, client, webhook_test_db, cipher):
        db = webhook_test_db
        with _patch_engine(db), _patch_cipher(cipher):
            resp = client.post(
                f"/telegram/webhook/{db['bot_username']}",
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
                json=_make_update(999902, 700200002, "hello"),
            )
        assert resp.status_code == 401

    def test_bot_username_mismatch_returns_401(self, client, webhook_test_db, cipher):
        db = webhook_test_db
        with _patch_engine(db), _patch_cipher(cipher):
            resp = client.post(
                "/telegram/webhook/WrongBotUsername",
                headers={"X-Telegram-Bot-Api-Secret-Token": db["secret"]},
                json=_make_update(999903, 700200003, "hello"),
            )
        assert resp.status_code == 401


@pytest.mark.integration
class TestExistingConversation:
    def test_reuses_existing_conversation_row(self, client, webhook_test_db, cipher):
        """Two messages from same chat_id reuse the same conversations row."""
        db = webhook_test_db
        chat_id = 700100010

        def run_one(update_id, text):
            with _patch_engine(db), _patch_cipher(cipher), _patch_dispatch(text):
                sender_ctx, _ = _patch_sender()
                with sender_ctx:
                    return client.post(
                        f"/telegram/webhook/{db['bot_username']}",
                        headers={"X-Telegram-Bot-Api-Secret-Token": db["secret"]},
                        json=_make_update(update_id, chat_id, text),
                    )

        r1 = run_one(900010, "first message")
        r2 = run_one(900011, "second message")
        assert r1.status_code == 200
        assert r2.status_code == 200

        engine = db["engine"]
        with engine.connect() as conn:
            count = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM conversations "
                    "WHERE channel = 'telegram' AND channel_chat_id = :ccid"
                ),
                {"ccid": str(chat_id)},
            ).fetchone()[0]
        assert count == 1  # only one conversation row


@pytest.mark.integration
class TestScriptDetection:
    def test_telugu_message_sets_script_telugu(self, client, webhook_test_db, cipher):
        """AgentContext receives incoming_message_script='telugu' for Telugu text."""
        db = webhook_test_db
        chat_id = 700100020
        captured_ctx = {}

        def capturing_dispatch(ctx):
            captured_ctx["script"] = ctx.incoming_message_script
            return _mock_agent_result()

        with _patch_engine(db), _patch_cipher(cipher):
            with patch(
                "app.telegram.webhook.CommunicationAgent.dispatch",
                side_effect=capturing_dispatch,
            ):
                sender_ctx, _ = _patch_sender()
                with sender_ctx:
                    client.post(
                        f"/telegram/webhook/{db['bot_username']}",
                        headers={"X-Telegram-Bot-Api-Secret-Token": db["secret"]},
                        json=_make_update(
                            900020, chat_id,
                            "మా నాన్నకి హార్ట్ ఎటాక్ వచ్చింది",  # Telugu
                        ),
                    )

        assert captured_ctx.get("script") == "telugu"
