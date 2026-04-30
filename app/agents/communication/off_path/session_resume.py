from app.agents.communication.types import ActionLog, DbWrite, StateResult

STATE_NAME = "s_session_resume"


def handle(conversation, message, context) -> StateResult:
    answer = (message or "").strip().lower()
    last_state = conversation.get("current_state", "s0_identity_check")

    if answer in {"yes", "y", "continue"}:
        return StateResult(
            next_state=last_state,
            reply_text=f"Resuming where we left off ({last_state}).",
            db_writes=[DbWrite("update", "citizen_conversations", values={"current_state": last_state, "invalid_attempts_in_state": 0})],
            agent_actions_to_log=[ActionLog("session.resumed", {"state": last_state})],
        )

    if answer in {"no", "n"}:
        return StateResult(
            next_state="s_abandon_handler",
            reply_text="Okay, we won't resume the old flow.",
            agent_actions_to_log=[ActionLog("session.resume.declined", {"state": last_state})],
        )

    return StateResult(
        next_state=STATE_NAME,
        reply_text="Welcome back. Do you want to continue where we left off? Reply Yes or No.",
        db_writes=[DbWrite("update", "citizen_conversations", values={"current_state": STATE_NAME})],
    )
