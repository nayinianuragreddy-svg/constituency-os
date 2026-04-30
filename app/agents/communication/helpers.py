from datetime import datetime
from typing import Any
import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from .types import Button, DbWrite


def generate_ticket_id_human(category_code: str, sequence: int, when: datetime | None = None) -> str:
    d = (when or datetime.utcnow()).strftime("%d%m%y")
    return f"{category_code}-{d}-{sequence:04d}"


def execute_db_write(db: Session, write: DbWrite, context: dict[str, Any]) -> Any:
    if write.operation == "raw" and write.sql == "UPSERT_DAILY_SEQUENCE":
        office_id = write.params["office_id"]
        row = db.execute(text("""
            INSERT INTO daily_ticket_sequences (office_id, sequence_date, last_sequence, updated_at)
            VALUES (:office_id, CURRENT_DATE, 1, now())
            ON CONFLICT (office_id, sequence_date)
            DO UPDATE SET last_sequence = daily_ticket_sequences.last_sequence + 1, updated_at = now()
            RETURNING last_sequence
        """), {"office_id": office_id}).fetchone()
        context["daily_sequence"] = int(row[0])
        return row[0]

    if write.operation == "update" and write.table == "citizen_conversations":
        vals = dict(write.values)
        chat_id = context["telegram_chat_id"]
        if "draft_payload" in vals and isinstance(vals["draft_payload"], dict) and "$merge" in vals["draft_payload"]:
            merge = vals.pop("draft_payload")["$merge"]
            db.execute(text("UPDATE citizen_conversations SET draft_payload = COALESCE(draft_payload,'{}'::jsonb) || CAST(:merge AS jsonb), updated_at=now() WHERE telegram_chat_id=:chat_id"), {"merge": json.dumps(merge), "chat_id": chat_id})
        if vals:
            set_expr = ", ".join(f"{k}=:{k}" for k in vals.keys())
            vals["chat_id"] = chat_id
            db.execute(text(f"UPDATE citizen_conversations SET {set_expr}, updated_at=now() WHERE telegram_chat_id=:chat_id"), vals)
        return None

    if write.operation == "upsert" and write.table == "citizens":
        vals = dict(write.values)
        vals.setdefault("telegram_chat_id", context["telegram_chat_id"])
        cols = ", ".join(vals.keys())
        binds = ", ".join(f":{k}" for k in vals.keys())
        updates = ", ".join(f"{k}=EXCLUDED.{k}" for k in vals.keys() if k != "telegram_chat_id")
        db.execute(text(f"INSERT INTO citizens ({cols}) VALUES ({binds}) ON CONFLICT (telegram_chat_id) DO UPDATE SET {updates}"), vals)
        return None

    if write.operation == "insert":
        vals = dict(write.values)
        cols = ", ".join(vals.keys())
        binds = ", ".join(f":{k}" for k in vals.keys())
        db.execute(text(f"INSERT INTO {write.table} ({cols}) VALUES ({binds})"), vals)
        return None


def to_inline_keyboard(buttons: list[Button] | None) -> dict[str, Any] | None:
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": b.text, "callback_data": b.value}] for b in buttons]}
