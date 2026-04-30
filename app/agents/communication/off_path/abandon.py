from app.agents.communication.helpers import clear_draft_payload
from app.agents.communication.types import ActionLog, DbWrite, StateResult

STATE_NAME = "s_abandon_handler"


def handle(conversation, message, context) -> StateResult:
    state = conversation.get("current_state", "")
    in_registration = state.startswith("s2_")
    in_complaint = state.startswith("s4") or state.startswith("s5")

    if in_registration:
        return StateResult(
            next_state="s0_identity_check",
            reply_text="No problem. We'll continue your registration next time.",
            db_writes=[DbWrite("update", "citizen_conversations", values={"current_state": "s0_identity_check"})],
            agent_actions_to_log=[ActionLog("registration.partial.saved", {"state": state})],
        )

    if in_complaint:
        return StateResult(
            next_state="s6_returning_user_menu",
            reply_text="Cancelled this complaint draft. You are back at main menu.",
            db_writes=[DbWrite("update", "citizen_conversations", values={"draft_payload": clear_draft_payload(), "draft_ticket_id": None, "current_state": "s6_returning_user_menu"})],
            agent_actions_to_log=[ActionLog("ticket.discarded", {"state": state})],
        )

    return StateResult(next_state=state or "s6_returning_user_menu", reply_text="Okay, ping me anytime.", agent_actions_to_log=[ActionLog("abandon.noop", {"state": state})])
