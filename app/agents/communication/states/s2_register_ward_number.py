from app.agents.communication.types import ActionLog, DbWrite, StateResult
from app.agents.communication.validators import validate_ward_number

STATE_NAME = "s2_register_ward_number"


def handle(conversation, message, context) -> StateResult:
    attempts = int(conversation.get("invalid_attempts_in_state", 0))
    valid_wards = set(context.get("valid_wards") or [])
    result = validate_ward_number((message or "").strip(), valid_wards=valid_wards, attempts=attempts)
    if not result.is_valid:
        return StateResult(next_state=STATE_NAME, reply_text=result.error_hint, db_writes=[DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":attempts+1})])
    return StateResult(next_state="s2_register_geo", reply_text="Please share location or type 'use ward centroid'.", field_collected=("ward_number", result.normalized_value), db_writes=[DbWrite("upsert","citizens",values=result.normalized_value if isinstance(result.normalized_value,dict) else {"ward_number":result.normalized_value}), DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":0})], agent_actions_to_log=[ActionLog("field.collected",{"field":"ward_number"})])
