from app.agents.communication.transitions import ALLOWED_FIX_STATES, FIX_FIELD_TO_STATE
from app.agents.communication.types import ActionLog, DbWrite, StateResult

STATE_NAME = "s_fix_field"


def handle(conversation, message, context) -> StateResult:
    current_state = conversation.get("current_state", "")
    draft_status = (conversation.get("draft_payload") or {}).get("ticket_status")
    if draft_status and draft_status != "draft":
        return StateResult(
            next_state=current_state,
            reply_text="This complaint is already registered. Please contact office for updates.",
            agent_actions_to_log=[ActionLog("fix_field.rejected", {"reason": "ticket_created"})],
        )

    if current_state not in ALLOWED_FIX_STATES:
        return StateResult(
            next_state=current_state,
            reply_text="You can edit fields only while registration/complaint is in progress.",
            agent_actions_to_log=[ActionLog("fix_field.rejected", {"reason": "invalid_state", "state": current_state})],
        )

    field_name = context.get("fix_field") or ""
    target_state = FIX_FIELD_TO_STATE.get(field_name)
    if not target_state:
        return StateResult(
            next_state=current_state,
            reply_text="I couldn't identify which field to edit. Please use the edit buttons.",
            agent_actions_to_log=[ActionLog("fix_field.rejected", {"reason": "unknown_field", "field": field_name})],
        )

    writes = [
        DbWrite("update", "citizen_conversations", values={"return_to_state": current_state, "current_state": target_state, "invalid_attempts_in_state": 0}),
    ]
    logs = [ActionLog("fix_field.invoked", {"field": field_name, "from_state": current_state, "to_state": target_state})]
    return StateResult(next_state=target_state, reply_text=f"Okay, let's update {field_name}.", db_writes=writes, agent_actions_to_log=logs)
