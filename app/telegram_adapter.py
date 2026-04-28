from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AgentAction
from app.v1 import handle_citizen_message


class TelegramSender(Protocol):
    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """Send a message to a Telegram chat."""


@dataclass
class TelegramApiClient:
    bot_token: str
    timeout_seconds: float = 30.0

    @property
    def _base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    def get_updates(self, offset: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset

        response = httpx.post(f"{self._base_url}/getUpdates", json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {body}")
        return body.get("result", [])

    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram sendMessage failed: {body}")
        return body


def process_incoming_update(db: Session, update: dict[str, Any], sender: TelegramSender) -> dict[str, Any]:
    """Shared Telegram update processor used by polling and future webhook mode."""

    update_id = update.get("update_id")
    if update_id is None:
        return {"status": "ignored", "reason": "missing_update_id"}

    idempotency_key = f"telegram:update:{update_id}"

    action = AgentAction(
        idempotency_key=idempotency_key,
        channel="telegram",
        action_type="incoming_update",
        status="processing",
        payload=update,
    )
    db.add(action)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        action = db.query(AgentAction).filter(AgentAction.idempotency_key == idempotency_key).first()
        if action is None:
            raise
        if action.status == "processed":
            return {
                "status": "duplicate_skipped",
                "idempotency_key": idempotency_key,
                "update_id": update_id,
            }
        action.status = "processing"
        action.payload = update
        db.flush()

    message = update.get("message") or {}
    text = message.get("text")
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not text or chat_id is None:
        action.status = "ignored"
        action.response_payload = {"reason": "unsupported_update"}
        db.commit()
        return {
            "status": "ignored",
            "reason": "unsupported_update",
            "idempotency_key": idempotency_key,
        }

    try:
        reply = handle_citizen_message(db, telegram_chat_id=str(chat_id), text=text)
        send_result = sender.send_message(chat_id=str(chat_id), text=reply)
    except Exception as exc:
        action.status = "error"
        action.response_payload = {"error": str(exc)}
        db.commit()
        raise

    action.status = "processed"
    action.response_payload = {
        "chat_id": str(chat_id),
        "reply": reply,
        "send_result": send_result,
    }
    db.commit()

    return {
        "status": "processed",
        "idempotency_key": idempotency_key,
        "update_id": update_id,
        "chat_id": str(chat_id),
        "reply": reply,
    }
