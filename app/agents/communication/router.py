from importlib import import_module
import inspect
from typing import Any

from app.core.llm import llm_call, load_prompt

from . import globals as global_guards
from .types import DbWrite, StateResult


def _contains_substring(source: str, candidate: str) -> bool:
    s = (source or "").lower()
    c = (candidate or "").lower()
    return bool(c and c in s)


def _call_intent_router(message: str, context: dict[str, Any]) -> dict[str, Any] | None:
    meta = {
        "agent_name": "communication",
        "purpose": "intent_router",
        "office_id": context.get("office_id", 1),
        "citizen_id": context.get("citizen_id"),
        "ticket_id": context.get("ticket_id"),
        "idempotency_key": context.get("idempotency_key", ""),
    }
    call_kwargs = {
        "system_prompt": load_prompt("communication_intent_router"),
        "response_format": "json",
        "metadata": meta,
    }
    params = inspect.signature(llm_call).parameters
    if "user_message" in params:
        call_kwargs["user_message"] = message
    else:
        call_kwargs["user_prompt"] = message
    res = llm_call(**call_kwargs)
    if not res.success or not isinstance(res.parsed_json, dict):
        return None
    parsed = dict(res.parsed_json)
    extracted = parsed.get("extracted") or {}
    safe_extracted = {}
    for k, v in extracted.items():
        if isinstance(v, str) and not _contains_substring(message, v):
            continue
        safe_extracted[k] = v
    parsed["extracted"] = safe_extracted
    return parsed


def _apply_writes(context: dict[str, Any], writes: list[DbWrite]) -> None:
    writer = context.get("db_write")
    if not callable(writer):
        return
    for write in writes:
        writer(write)


def _log_actions(context: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    logger = context.get("log_action")
    if not callable(logger):
        return
    for action in actions:
        logger(action)


def process_message(conversation: dict, message: str, context: dict[str, Any]) -> StateResult:
    context = dict(context)
    context["conversation"] = conversation
    context["message"] = message
    context.setdefault("current_state", conversation.get("current_state", "s0_identity_check"))

    intent_data = _call_intent_router(message, context) if context.get("llm_enabled", True) else None
    if intent_data:
        context.update(intent_data)

    guard_chain = [
        global_guards.g_unknown_chat,
        global_guards.g_session_resume,
        global_guards.g_abandon,
        global_guards.g_off_path_status,
        global_guards.g_off_path_fix,
        global_guards.g_off_path_unclear,
    ]

    for guard in guard_chain:
        if guard(context):
            if guard.__name__ == "g_session_resume":
                result = import_module("app.agents.communication.off_path.session_resume").handle(conversation, message, context)
            elif guard.__name__ == "g_abandon":
                result = import_module("app.agents.communication.off_path.abandon").handle(conversation, message, context)
            elif guard.__name__ == "g_off_path_fix":
                result = import_module("app.agents.communication.off_path.fix_field").handle(conversation, message, context)
            else:
                result = StateResult(next_state=context["current_state"], reply_text="I didn't understand. Please try again.")  # V1.9: route through reply_drafter for language-aware phrasing
            _apply_writes(context, result.db_writes)
            _log_actions(context, [a.__dict__ for a in result.agent_actions_to_log])
            return result

    state_name = context["current_state"]
    state_module = import_module(f"app.agents.communication.states.{state_name}")
    result: StateResult = state_module.handle(conversation, message, context)
    _apply_writes(context, result.db_writes)
    _log_actions(context, [a.__dict__ for a in result.agent_actions_to_log])

    persist = context.get("persist_state")
    if callable(persist):
        persist(result.next_state)

    sender = context.get("send_reply")
    if callable(sender) and (result.reply_text or result.reply_buttons):
        sender(result.reply_text, result.reply_buttons)

    return result


handle_message = process_message
