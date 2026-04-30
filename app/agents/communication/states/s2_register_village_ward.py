from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult
from app.agents.communication.validators import validate_village_ward
from app.agents.communication.transitions import resolve_next

STATE_NAME = "s2_register_village_ward"

def handle(conversation, message, context) -> StateResult:
    text=(message or "").strip()
    if STATE_NAME=="s1_greet":
        return StateResult(next_state="s1_language_select", reply_text="Please share ward number.", reply_buttons=[Button("Telugu","te"),Button("Hindi","hi"),Button("English","en")])
    if STATE_NAME in {"s2_register_done","s5_acknowledgement"}:
        return StateResult(next_state="s2_register_ward_number", reply_text="Please share ward number.")
    v=validate_village_ward(text)
    if not v.is_valid:
        return StateResult(next_state=STATE_NAME, reply_text=v.error_hint, db_writes=[DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":conversation.get("invalid_attempts_in_state",0)+1})])
    next_state=resolve_next(STATE_NAME,"valid")
    return StateResult(next_state=next_state, reply_text="Please share ward number.", field_collected=("village_ward",v.normalized_value), db_writes=[DbWrite("upsert","citizens",values={"village_ward":v.normalized_value})], agent_actions_to_log=[ActionLog("field.collected",{"field":"village_ward"})])
