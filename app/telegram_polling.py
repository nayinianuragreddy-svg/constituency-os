from __future__ import annotations

import time

from dotenv import load_dotenv

from app.config import TELEGRAM_BOT_TOKEN
from app.db import SessionLocal, init_db
from app.telegram_adapter import TelegramApiClient, process_incoming_update


def run_polling(poll_interval_seconds: float = 1.0) -> None:
    load_dotenv()
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
            finally:
                db.close()
            next_offset = int(update["update_id"]) + 1
        time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    run_polling()
