from datetime import datetime, timedelta, timezone


def g_unknown_chat(context: dict) -> bool:
    convo = context.get("conversation")
    return convo is None


def g_off_path_fix(context: dict) -> bool:
    intent = context.get("intent")
    state = context.get("current_state", "")
    if intent != "fix_earlier":
        return False
    allowed = state.startswith("s2_") or state.startswith("s4") or state in {"s2_register_confirm", "s5_complaint_confirm"}
    return bool(allowed)


def g_off_path_status(context: dict) -> bool:
    return context.get("intent") == "ask_status"


def g_off_path_unclear(context: dict) -> bool:
    intent = context.get("intent")
    confidence = float(context.get("confidence", 0.0))
    state = context.get("current_state", "")
    if intent == "unclear":
        return True
    if confidence < 0.70 and state not in {"s0_identity_check", "s1_greet", "s2_register_done", "s5_ticket_generated"}:
        return True
    return False


def g_abandon(context: dict) -> bool:
    text = (context.get("message") or "").strip().lower()
    intent = context.get("intent")
    if intent == "abandon":
        return True
    return text in {"/cancel", "cancel", "never mind", "leave it", "stop"}


def g_session_resume(context: dict) -> bool:
    last_inbound = context.get("last_inbound_at")
    if not last_inbound:
        return False
    if isinstance(last_inbound, str):
        last_inbound = datetime.fromisoformat(last_inbound)
    return datetime.now(timezone.utc) - last_inbound > timedelta(hours=24)
