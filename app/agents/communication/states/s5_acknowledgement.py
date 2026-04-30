from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult
from app.agents.communication.validators import validate_free_text
from app.agents.communication.transitions import resolve_next

STATE_NAME = "s5_acknowledgement"

def handle(conversation, message, context) -> StateResult:
    text=(message or "").strip()
    if STATE_NAME=="s1_greet":
        return StateResult(next_state="s1_language_select", reply_text="Your complaint is registered.", reply_buttons=[Button("Telugu","te"),Button("Hindi","hi"),Button("English","en")])
    if STATE_NAME in {"s2_register_done","s5_acknowledgement"}:
        return StateResult(next_state="s6_returning_user_menu", reply_text="Your complaint is registered.")
    v=validate_free_text(text)
    if not v.is_valid:
        return StateResult(next_state=STATE_NAME, reply_text=v.error_hint, db_writes=[DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":conversation.get("invalid_attempts_in_state",0)+1})])
    next_state=resolve_next(STATE_NAME,"valid")
    return StateResult(next_state=next_state, reply_text="Your complaint is registered.", field_collected=("acknowledgement",v.normalized_value), db_writes=[DbWrite("upsert","citizens",values={"acknowledgement":v.normalized_value})], agent_actions_to_log=[ActionLog("field.collected",{"field":"acknowledgement"})])
