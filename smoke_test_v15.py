import os
from pathlib import Path
from typing import Any

os.environ["DATABASE_URL"] = f"sqlite:///{Path('smoke_v15.db').absolute()}"

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import AgentAction, CitizenConversation  # noqa: E402
from app.telegram_adapter import process_incoming_update  # noqa: E402


class FakeTelegramSender:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []

    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        payload = {"chat_id": chat_id, "text": text}
        self.sent_messages.append(payload)
        return {"ok": True, "result": payload}


def main() -> None:
    db_file = Path("smoke_v15.db")
    if db_file.exists():
        db_file.unlink()

    init_db()
    db = SessionLocal()
    sender = FakeTelegramSender()

    try:
        update = {
            "update_id": 9001,
            "message": {
                "message_id": 101,
                "chat": {"id": 123456789, "type": "private"},
                "text": "Hi",
            },
        }

        first = process_incoming_update(db=db, update=update, sender=sender)
        assert first["status"] == "processed"
        assert len(sender.sent_messages) == 1
        assert "full name" in sender.sent_messages[0]["text"]

        duplicate = process_incoming_update(db=db, update=update, sender=sender)
        assert duplicate["status"] == "duplicate_skipped"
        assert len(sender.sent_messages) == 1

        action_count = db.query(AgentAction).filter(AgentAction.idempotency_key == "telegram:update:9001").count()
        assert action_count == 1

        convo = (
            db.query(CitizenConversation)
            .filter(CitizenConversation.telegram_chat_id == "123456789")
            .first()
        )
        assert convo is not None

        print("V1.5 smoke test passed.")
        print(first)
        print(duplicate)
    finally:
        db.close()


if __name__ == "__main__":
    main()
