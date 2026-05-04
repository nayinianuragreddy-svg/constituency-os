"""FastAPI router for incoming Telegram webhook calls.

One endpoint: POST /telegram/webhook/{bot_username}

Authentication: X-Telegram-Bot-Api-Secret-Token header, matched against
constituency_bots.secret_token for the requested bot.

Deduplication: INSERT into telegram_updates first. UniqueViolation = Telegram
retry; ack 200 immediately without re-dispatching.

Column names match the actual 0001 migration schema:
- messages.content (not body)
- messages.channel_msg_id (not channel_message_id)
- conversations UNIQUE(channel, channel_chat_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from telegram import Update

from app.agents.base import AgentContext
from app.agents.communication_v2.agent import CommunicationAgent
from app.telegram.bot_config import BotConfig, BotConfigRepository
from app.telegram.encryption import TelegramTokenCipher
from app.telegram.rate_limiter import TelegramRateLimiter
from app.telegram.sender import TelegramSender

logger = logging.getLogger(__name__)

router = APIRouter()


def _detect_script(text: str) -> str:
    """Detect dominant Unicode script of text.

    Returns 'telugu' if any Telugu-script char found (U+0C00-U+0C7F),
    'devanagari' if any Devanagari char (U+0900-U+097F), else 'roman'.
    Checks Telugu first because Telugu users code-mix more.
    """
    for ch in text:
        cp = ord(ch)
        if 0x0C00 <= cp <= 0x0C7F:
            return "telugu"
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            return "devanagari"
    return "roman"


def _get_engine():
    """Build a SQLAlchemy engine from DATABASE_URL env var."""
    from sqlalchemy import create_engine
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return create_engine(url)


def _get_cipher() -> TelegramTokenCipher:
    return TelegramTokenCipher()


def _get_repo(engine, cipher: TelegramTokenCipher) -> BotConfigRepository:
    return BotConfigRepository(engine, cipher)


def _get_sender() -> TelegramSender:
    import redis as redis_lib
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = redis_lib.from_url(redis_url)
        r.ping()
    except Exception:
        logger.warning("Redis unavailable, rate limiter in degraded mode")
        r = None
    limiter = TelegramRateLimiter(r)
    return TelegramSender(limiter)


@router.post("/telegram/webhook/{bot_username}")
async def telegram_webhook(
    bot_username: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    # Step 1: require secret token header
    if not x_telegram_bot_api_secret_token:
        raise HTTPException(status_code=401, detail="Missing secret token")

    engine = _get_engine()
    cipher = _get_cipher()
    repo = _get_repo(engine, cipher)

    # Step 2: look up bot by secret token
    bot_config = repo.get_by_secret_token(x_telegram_bot_api_secret_token)
    if bot_config is None:
        raise HTTPException(status_code=401, detail="Invalid secret token")

    # Step 3: verify path bot_username matches
    if bot_config.bot_username != bot_username:
        raise HTTPException(status_code=401, detail="bot_username mismatch")

    # Step 4: parse Update
    body = await request.body()
    try:
        payload = json.loads(body)
        update = Update.de_json(payload, bot=None)
    except Exception as exc:
        logger.error("Failed to parse Telegram Update: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid Update payload")

    # Only handle messages with text
    if not update.message or not update.message.text:
        return {"ok": True}

    update_id = update.update_id
    chat_id = update.message.chat.id
    message_text = update.message.text
    tg_message_id = update.message.message_id

    # Step 5: deduplication INSERT
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO telegram_updates (update_id, bot_id, received_at) "
                    "VALUES (:uid, :bid, :now)"
                ),
                {"uid": update_id, "bid": bot_config.bot_id, "now": datetime.now(timezone.utc)},
            )
    except IntegrityError:
        logger.info("Duplicate update_id=%d for bot %s, acking", update_id, bot_username)
        return {"ok": True}

    conversation_id = None
    try:
        conversation_id, citizen_id = _find_or_create_conversation(
            engine, chat_id, bot_config
        )

        # Step 7: record inbound message
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO messages (id, conversation_id, direction, content, "
                    "channel_msg_id, created_at) "
                    "VALUES (:id, :cid, 'inbound', :content, :cmid, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid": str(conversation_id),
                    "content": message_text,
                    "cmid": str(tg_message_id),
                    "now": datetime.now(timezone.utc),
                },
            )
            # Update last_message_at on conversation
            conn.execute(
                sa.text(
                    "UPDATE conversations SET last_message_at = :now, updated_at = :now "
                    "WHERE id = :cid"
                ),
                {"now": datetime.now(timezone.utc), "cid": str(conversation_id)},
            )

        # Step 8+9: build context and dispatch
        script = _detect_script(message_text)
        ctx = AgentContext(
            conversation_id=str(conversation_id),
            incoming_message=message_text,
            incoming_message_script=script,
            citizen_id=str(citizen_id) if citizen_id else None,
        )

        constituency_config = {
            "mla_name": bot_config.mla_name,
            "name": _get_constituency_name(engine, bot_config.constituency_id),
        }

        agent = CommunicationAgent(engine=engine, constituency_config=constituency_config)

        # Step 10: dispatch (sync, run in executor to avoid blocking event loop)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, agent.dispatch, ctx)

        # Step 11: send reply
        reply_msg_id = None
        if result.reply_text:
            sender = _get_sender()
            reply_msg_id = await sender.send_message(bot_config, chat_id, result.reply_text)

            # Record outbound message
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO messages (id, conversation_id, direction, content, "
                        "channel_msg_id, created_at) "
                        "VALUES (:id, :cid, 'outbound', :content, :cmid, :now)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "cid": str(conversation_id),
                        "content": result.reply_text,
                        "cmid": str(reply_msg_id) if reply_msg_id else None,
                        "now": datetime.now(timezone.utc),
                    },
                )

        # Step 12: mark telegram_updates.processed_at
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE telegram_updates SET processed_at = :now, "
                    "conversation_id = :cid "
                    "WHERE update_id = :uid AND bot_id = :bid"
                ),
                {
                    "now": datetime.now(timezone.utc),
                    "cid": str(conversation_id),
                    "uid": update_id,
                    "bid": bot_config.bot_id,
                },
            )

    except Exception as exc:
        logger.error(
            "Error processing update_id=%d bot=%s: %s",
            update_id, bot_username, exc, exc_info=True,
        )
        # Mark error in telegram_updates so staff can inspect
        try:
            with engine.begin() as conn:
                updates = {
                    "error": str(exc)[:2000],
                    "uid": update_id,
                    "bid": bot_config.bot_id,
                }
                if conversation_id:
                    conn.execute(
                        sa.text(
                            "UPDATE telegram_updates SET error = :error, "
                            "conversation_id = :cid "
                            "WHERE update_id = :uid AND bot_id = :bid"
                        ),
                        {**updates, "cid": str(conversation_id)},
                    )
                else:
                    conn.execute(
                        sa.text(
                            "UPDATE telegram_updates SET error = :error "
                            "WHERE update_id = :uid AND bot_id = :bid"
                        ),
                        updates,
                    )
        except Exception:
            pass
        # Return 200 to prevent Telegram from retrying an unrecoverable error
        return {"ok": False, "error": str(exc)[:200]}

    return {"ok": True}


def _find_or_create_conversation(engine, chat_id: int, bot_config: BotConfig):
    """Find existing conversation by (channel, channel_chat_id) or create a new one.

    Returns (conversation_id, citizen_id). citizen_id may be None for new conversations.
    """
    channel_chat_id = str(chat_id)

    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                "SELECT id, citizen_id FROM conversations "
                "WHERE channel = 'telegram' AND channel_chat_id = :ccid"
            ),
            {"ccid": channel_chat_id},
        ).fetchone()

        if row:
            return row[0], row[1]

        # New conversation
        new_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO conversations "
                "(id, channel, channel_chat_id, session_state, summary_data, created_at, updated_at) "
                "VALUES (:id, 'telegram', :ccid, 'active', :sd, :now, :now)"
            ),
            {
                "id": new_id,
                "ccid": channel_chat_id,
                "sd": json.dumps({"history_compressed": []}),
                "now": datetime.now(timezone.utc),
            },
        )
        return new_id, None


def _get_constituency_name(engine, constituency_id) -> str:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT name FROM constituencies WHERE id = :cid"),
                {"cid": str(constituency_id)},
            ).fetchone()
        return row[0] if row else "this constituency"
    except Exception:
        return "this constituency"
