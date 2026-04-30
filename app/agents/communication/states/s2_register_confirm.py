from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult

STATE_NAME = "s2_register_confirm"


def _summary(citizen: dict) -> str:
    return (
        f"Please confirm your details:\n"
        f"Name: {citizen.get('name','-')}\n"
        f"DOB: {citizen.get('dob','-')}\n"
        f"Mobile: {citizen.get('mobile','-')}\n"
        f"Voter ID: {citizen.get('voter_id') or 'Not provided'}\n"
        f"Mandal: {citizen.get('mandal','-')}\n"
        f"Village/Ward: {citizen.get('village_or_ward_name','-')}\n"
        f"Ward Number: {citizen.get('ward_number') or citizen.get('wards_fallback_text','-')}\n"
        f"Location: {'Approximate' if citizen.get('geo_is_approximate') else 'Captured'}"
    )


def _edit_buttons() -> list[Button]:
    return [
        Button("✅ Yes, all correct", "confirm"),
        Button("✏️ Edit Name", "edit:name"),
        Button("✏️ Edit DOB", "edit:dob"),
        Button("✏️ Edit Mobile", "edit:mobile"),
        Button("✏️ Edit Voter ID", "edit:voter_id"),
        Button("✏️ Edit Mandal", "edit:mandal"),
        Button("✏️ Edit Village/Ward Name", "edit:village_ward"),
        Button("✏️ Edit Ward", "edit:ward_number"),
        Button("✏️ Edit Location", "edit:geo"),
        Button("❌ Cancel", "cancel"),
    ]


def handle(conversation, message, context) -> StateResult:
    citizen = context.get("citizen") or {}
    text = (message or "").strip().lower()
    summary = _summary(citizen)

    if text in {"", "show", "review"}:
        return StateResult(next_state=STATE_NAME, reply_text=summary, reply_buttons=_edit_buttons())

    if text in {"confirm", "yes"}:
        return StateResult(
            next_state="s2_register_done",
            reply_text="Great, registration complete.",
            db_writes=[
                DbWrite("upsert", "citizens", values={"registration_complete": True}),
                DbWrite("update", "citizen_conversations", values={"invalid_attempts_in_state": 0, "pending_cancel_warning": False}),
            ],
            agent_actions_to_log=[ActionLog("registration.completed", {})],
        )

    if text in {"cancel", "no"}:
        if conversation.get("pending_cancel_warning"):
            return StateResult(
                next_state=STATE_NAME,
                reply_text="Keeping your details. Please confirm or edit any field.",
                reply_buttons=_edit_buttons(),
                db_writes=[DbWrite("update", "citizen_conversations", values={"pending_cancel_warning": False})],
            )
        return StateResult(
            next_state=STATE_NAME,
            reply_text="Are you sure? This will clear your registration.",
            reply_buttons=[Button("Yes, discard", "cancel_confirm_yes"), Button("No, keep my details", "cancel_confirm_no")],
            db_writes=[DbWrite("update", "citizen_conversations", values={"pending_cancel_warning": True})],
        )

    if text in {"cancel_confirm_no", "keep"}:
        return StateResult(
            next_state=STATE_NAME,
            reply_text=summary,
            reply_buttons=_edit_buttons(),
            db_writes=[DbWrite("update", "citizen_conversations", values={"pending_cancel_warning": False})],
        )

    if text in {"cancel_confirm_yes", "discard"}:
        return StateResult(
            next_state="s1_greet",
            reply_text="Okay, discarded. Starting over.",
            db_writes=[
                DbWrite("upsert", "citizens", values={
                    "name": None,
                    "dob": None,
                    "mobile": None,
                    "voter_id": None,
                    "mandal": None,
                    "village_or_ward_name": None,
                    "ward_number": None,
                    "wards_fallback_text": None,
                    "geo_lat": None,
                    "geo_lng": None,
                    "geo_is_approximate": False,
                    "registration_complete": False,
                }),
                DbWrite("update", "citizen_conversations", values={"pending_cancel_warning": False}),
            ],
            agent_actions_to_log=[ActionLog("registration.discarded", {})],
        )

    if text.startswith("edit:"):
        field = text.split(":", 1)[1]
        return StateResult(
            next_state=STATE_NAME,
            reply_text=f"Okay, let's edit {field}. Please provide the updated value.",
            db_writes=[
                DbWrite("update", "citizen_conversations", values={"pending_cancel_warning": False}),
                DbWrite("update", "citizen_conversations", values={"pending_fix_field": field}),
            ],
            agent_actions_to_log=[
                ActionLog("fix_field.invoked", {"field": field}),
                ActionLog("state.transition", {"from": STATE_NAME, "to": STATE_NAME, "mode": "guard_dispatch"}),
            ],
        )

    return StateResult(next_state=STATE_NAME, reply_text=summary, reply_buttons=_edit_buttons())
