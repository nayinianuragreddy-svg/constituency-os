from __future__ import annotations

import time
import traceback
import uuid

from dotenv import load_dotenv

from app.config import TELEGRAM_BOT_TOKEN
from app.db import SessionLocal, init_db
from app.models import AgentAction
from app.telegram_adapter import TelegramApiClient, process_incoming_update


def run_polling(poll_interval_seconds: float = 1.0) -> None:
    load_dotenv(override=True)
    init_db()

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing. Set it in your environment or .env before starting polling mode."
        )

    client = TelegramApiClient(bot_token=TELEGRAM_BOT_TOKEN)
    next_offset: int | None = None

    print("Starting Telegram polling mode...")
    while True:
        updates = client.get_updates(offset=next_offset, timeout=20)
        for update in updates:
            db = SessionLocal()
            try:
                result = process_incoming_update(db=db, update=update, sender=client)
                print(f"telegram_update_result={result}")
            except Exception as exc:
                db.rollback()
                _log_update_error(update=update, error=exc)
                _try_send_fallback_message(client=client, update=update)
            finally:
                db.close()
            next_offset = int(update["update_id"]) + 1
        time.sleep(poll_interval_seconds)


def _log_update_error(update: dict, error: Exception) -> None:
    db = SessionLocal()
    try:
        update_id = update.get("update_id", "unknown")
        idempotency_key = f"telegram:update:error:{update_id}:{uuid.uuid4().hex}"
        db.add(
            AgentAction(
                idempotency_key=idempotency_key,
                channel="telegram",
                action_type="telegram.update.error",
                status="error",
                payload={
                    "update": update,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                },
                response_payload={},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        print("telegram_update_error_log_failed")
    finally:
        db.close()


def _try_send_fallback_message(client: TelegramApiClient, update: dict) -> None:
    chat_id = ((update.get("message") or {}).get("chat") or {}).get("id")
    if chat_id is None:
        return
    try:
        client.send_message(
            chat_id=str(chat_id),
            text="Sorry, something went wrong while processing your message. Please try again.",
        )
    except Exception:
        print("telegram_update_fallback_send_failed")


if __name__ == "__main__":
    run_polling()
