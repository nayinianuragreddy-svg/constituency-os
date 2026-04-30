from datetime import datetime, timezone

from app.agents.communication.transitions import resolve_next
from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult
from app.agents.communication.validators import validate_voter_id

STATE_NAME = "s2_register_voter_id"


def handle(conversation, message, context) -> StateResult:
    text = (message or "").strip()
    extracted = (context.get("extracted") or {}).get("voter_id")
    candidate = extracted or text
    result = validate_voter_id(candidate)
    if not result.is_valid:
        attempts = int(conversation.get("invalid_attempts_in_state", 0)) + 1
        return StateResult(
            next_state=STATE_NAME,
            reply_text=result.error_hint,
            reply_buttons=[Button("Skip", "skip")],
            db_writes=[DbWrite("update", "citizen_conversations", values={"invalid_attempts_in_state": attempts})],
        )

    outcome = result.code
    next_state = resolve_next(STATE_NAME, outcome)
    writes = [DbWrite("update", "citizen_conversations", values={"invalid_attempts_in_state": 0})]
    if outcome == "skip":
        writes.append(DbWrite("upsert", "citizens", values={"voter_id": None, "voter_id_skipped_at": datetime.now(timezone.utc).isoformat()}))
        logs = [ActionLog("voter_id.skipped", {"state": STATE_NAME}), ActionLog("field.collected", {"field": "voter_id", "value": None})]
        reply = "Noted. We can collect voter ID later. Please select your mandal."
        field_collected = ("voter_id", None)
    else:
        writes.append(DbWrite("upsert", "citizens", values={"voter_id": result.normalized_value, "voter_id_skipped_at": None}))
        logs = [ActionLog("field.collected", {"field": "voter_id", "value": result.normalized_value})]
        reply = "Thanks. Please select your mandal."
        field_collected = ("voter_id", result.normalized_value)

    return StateResult(
        next_state=next_state,
        reply_text=reply,
        field_collected=field_collected,
        db_writes=writes,
        agent_actions_to_log=logs,
    )
