from app.agents.communication.helpers import generate_ticket_id_human
from app.agents.communication.types import ActionLog, DbWrite, StateResult

STATE_NAME = "s5_ticket_generated"


def handle(conversation, message, context) -> StateResult:
    draft = conversation.get("draft_payload") or {}
    office_id = context.get("office_id", 1)
    citizen_id = context.get("citizen_id")
    category_code = draft.get("category_code", "PUB-OTH")
    sequence = int(context.get("daily_sequence", 1))
    ticket_id_human = generate_ticket_id_human(category_code, sequence)

    ticket_values = {
        "office_id": office_id,
        "citizen_id": citizen_id,
        "ticket_id_human": ticket_id_human,
        "category_code": category_code,
        "assigned_queue": draft.get("assigned_queue", "pa_inbox"),
        "language_at_creation": draft.get("language_at_creation", context.get("language", "en")),
        "media_file_ids": draft.get("media_file_ids", []),
        "status": "open",
    }

    db_writes = [
        DbWrite("raw", "daily_ticket_sequences", sql="UPSERT_DAILY_SEQUENCE", params={"office_id": office_id}),
        DbWrite("insert", "tickets", values=ticket_values),
    ]

    custom_fields = draft.get("custom_fields", {})
    for field_name, field_value in custom_fields.items():
        db_writes.append(DbWrite("insert", "ticket_custom_fields", values={"ticket_id_human": ticket_id_human, "field_name": field_name, "field_value": str(field_value)}))

    db_writes.append(DbWrite("update", "citizen_conversations", values={"draft_ticket_id": None, "draft_payload": {}}))

    logs = [
        ActionLog("ticket.created", {"ticket_id_human": ticket_id_human, "category_code": category_code}),
        ActionLog("state.transition", {"from": STATE_NAME, "to": "s5_acknowledgement"}),
    ]

    return StateResult(
        next_state="s5_acknowledgement",
        reply_text=f"Ticket generated successfully: {ticket_id_human}",
        field_collected=("ticket_id_human", ticket_id_human),
        db_writes=db_writes,
        agent_actions_to_log=logs,
    )
