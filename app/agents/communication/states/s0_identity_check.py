from app.agents.communication.types import StateResult

STATE_NAME = "s0_identity_check"

def handle(conversation, message, context) -> StateResult:
    citizen = context.get("citizen")
    if citizen and citizen.get("registration_complete"):
        return StateResult(next_state="s6_returning_user_menu", reply_text="Welcome back.")
    if citizen and not citizen.get("registration_complete"):
        return StateResult(next_state=citizen.get("resume_state","s2_register_name"), reply_text="Let's continue your registration.")
    return StateResult(next_state="s1_greet", reply_text="Namaskaram! Let's get started. Please share your full name.")
