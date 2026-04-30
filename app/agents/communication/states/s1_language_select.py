from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult
from app.agents.communication.validators import validate_issue_type

STATE_NAME = "s1_language_select"


def handle(conversation, message, context) -> StateResult:
    text = (message or "").strip().lower()
    extracted = (context.get("extracted") or {}).get("language", "")
    choice = extracted or text
    mapping = {"telugu": "te", "te": "te", "hindi": "hi", "hi": "hi", "english": "en", "en": "en"}
    if choice not in mapping:
        return StateResult(next_state=STATE_NAME, reply_text="Please choose Telugu, Hindi, or English.", reply_buttons=[Button("Telugu","te"),Button("Hindi","hi"),Button("English","en")], db_writes=[DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":conversation.get("invalid_attempts_in_state",0)+1})])
    lang = mapping[choice]
    return StateResult(next_state="s2_register_name", reply_text="Please share your full name.", field_collected=("preferred_language", lang), db_writes=[DbWrite("upsert","citizens",values={"preferred_language": lang}), DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":0})], agent_actions_to_log=[ActionLog("field.collected",{"field":"preferred_language","value":lang})])
