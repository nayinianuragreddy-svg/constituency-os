from app.agents.communication.types import ActionLog, DbWrite, StateResult
from app.agents.communication.validators import validate_urgency
from app.agents.communication.transitions import resolve_next

STATE_NAME = "s4a_others_urgency"

def handle(conversation, message, context) -> StateResult:
    text = (message or "").strip()
    result = validate_urgency(text)
    if not result.is_valid:
        return StateResult(
            next_state=STATE_NAME,
            reply_text=result.error_hint,
            db_writes=[DbWrite("update", "citizen_conversations", values={"invalid_attempts_in_state": conversation.get("invalid_attempts_in_state", 0) + 1})],
        )
    next_state = resolve_next(STATE_NAME, result.code)
    return StateResult(
        next_state=next_state,
        reply_text="Please provide detailed description.",
        field_collected=("others_urgency", result.normalized_value),
        db_writes=[
            DbWrite("update", "citizen_conversations", values={"invalid_attempts_in_state": 0}),
            DbWrite("update", "citizen_conversations", values={"draft_payload": {"$merge": {"others_urgency": result.normalized_value}}}),
        ],
        agent_actions_to_log=[ActionLog("field.collected", {"field": "others_urgency", "value": result.normalized_value})],
    )
