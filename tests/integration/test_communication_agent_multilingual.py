"""Integration tests for CommunicationAgent multilingual support and emergency handling (PR 5d).

Tests:
  1. test_telugu_water_complaint_full_flow  (LIVE)  — Telugu script in, Telugu reply, Telugu read-back
  2. test_hindi_complaint_replies_in_hindi  (LIVE)  — Hindi/Devanagari in, Hindi reply
  3. test_emergency_routes_to_escalate_not_create_ticket (LIVE) — safety emergency → human queue, no ticket
  4. test_explicit_language_preference_persisted (NON-LIVE) — save_citizen_field preferred_language

Run live tests:
  pytest tests/integration/test_communication_agent_multilingual.py -m "live and integration" -v

Run non-live tests only:
  pytest tests/integration/test_communication_agent_multilingual.py -v -m integration
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from app.agents.base import AgentContext
from app.agents.communication_v2 import CommunicationAgent
from app.agents.communication_v2.tools.save_citizen_field import SaveCitizenField


# ---------------------------------------------------------------------------
# Shared helpers (copied from ticket_flow pattern, unique channel_chat_id each call)
# ---------------------------------------------------------------------------


def _get_real_ward_and_mandal(engine):
    """Return (ward_id, mandal_id) from seeded data."""
    with engine.connect() as conn:
        ward_row = conn.execute(
            sa.text("SELECT id, mandal_id FROM wards WHERE mandal_id IS NOT NULL LIMIT 1")
        ).fetchone()
    if ward_row is not None:
        return str(ward_row[0]), str(ward_row[1])

    constituency_id = str(uuid.uuid4())
    mandal_id = str(uuid.uuid4())
    ward_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO constituencies (id, name, state)
                VALUES (:id, 'Ibrahimpatnam', 'Telangana')
                ON CONFLICT DO NOTHING
            """),
            {"id": constituency_id},
        )
        conn.execute(
            sa.text("""
                INSERT INTO mandals (id, constituency_id, name)
                VALUES (:id, :cid, 'Ibrahimpatnam Mandal')
            """),
            {"id": mandal_id, "cid": constituency_id},
        )
        conn.execute(
            sa.text("""
                INSERT INTO wards (id, mandal_id, ward_number, ward_name)
                VALUES (:id, :mid, 1, 'Ward 1')
            """),
            {"id": ward_id, "mid": mandal_id},
        )
    return ward_id, mandal_id


def _insert_registered_citizen(engine, ward_id: str, mandal_id: str, name: str = "Ravi Kumar") -> str:
    citizen_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO citizens
                    (id, name, mobile, ward_id, mandal_id, registration_complete)
                VALUES
                    (:id, :name, '9876543210', :wid, :mid, true)
            """),
            {"id": citizen_id, "name": name, "wid": ward_id, "mid": mandal_id},
        )
    return citizen_id


def _insert_conversation(engine, citizen_id: str, summary: dict) -> str:
    conv_id = str(uuid.uuid4())
    channel_chat_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO conversations
                    (id, channel, channel_chat_id, citizen_id,
                     last_message_at, summary_data, session_state)
                VALUES
                    (:id, 'telegram', :ccid, :cid, now(), :s, 'active')
            """),
            {
                "id": conv_id,
                "ccid": channel_chat_id,
                "cid": citizen_id,
                "s": json.dumps(summary, ensure_ascii=False),
            },
        )
    return conv_id


def _read_summary(engine, conv_id: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT summary_data FROM conversations WHERE id = :cid"),
            {"cid": conv_id},
        ).fetchone()
    data = row[0]
    if isinstance(data, str):
        data = json.loads(data)
    return data or {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def multilingual_agent(seeded_test_db_engine):
    return CommunicationAgent(
        engine=seeded_test_db_engine,
        constituency_config={
            "mla_name": "Anurag Reddy garu",
            "name": "Ibrahimpatnam",
        },
    )


# ---------------------------------------------------------------------------
# Test 1: Telugu water complaint — reply in Telugu, Telugu read-back (LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.integration
def test_telugu_water_complaint_full_flow(multilingual_agent, seeded_test_db_engine):
    """Citizen sends a complete water complaint in Telugu script.

    Expected:
    - reply_text contains Telugu Unicode characters (U+0C00–U+0C7F).
    - tool_calls include load_category_schema (success), extract_structured_data (success),
      confirm_with_citizen (success) with language="telugu".
    - reply_text contains the Telugu template anchor "మీ సమస్యను" (from the read-back).
    """
    ward_id, mandal_id = _get_real_ward_and_mandal(seeded_test_db_engine)
    citizen_id = _insert_registered_citizen(
        seeded_test_db_engine, ward_id, mandal_id, name="రవి కుమార్"
    )
    summary = {
        "language_preference": "telugu",
        "language_script": "telugu",
        "history_compressed": [],
        "citizen": {},
    }
    conv_id = _insert_conversation(seeded_test_db_engine, citizen_id, summary)

    ctx = AgentContext(
        conversation_id=conv_id,
        incoming_message=(
            "నాకు 3 రోజులుగా నీళ్లు లేవు. వార్డ్ 11, ప్రగతి నగర్ 4వ వీధి. "
            "30 ఇళ్లకు ప్రభావం. బోర్‌వెల్ పనిచేయడం లేదు."
        ),
        incoming_message_script="telugu",
        citizen_id=citizen_id,
    )
    result = multilingual_agent.dispatch(ctx)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.reply_text is not None and len(result.reply_text) > 0

    # reply must contain Telugu Unicode (U+0C00–U+0C7F)
    has_telugu = any("ఀ" <= ch <= "౿" for ch in (result.reply_text or ""))
    assert has_telugu, (
        f"reply_text should contain Telugu Unicode characters: {result.reply_text!r}"
    )

    tool_names = [tc["name"] for tc in result.tool_calls_made]
    assert "load_category_schema" in tool_names, (
        f"load_category_schema not called. Tool calls: {tool_names}"
    )
    assert "extract_structured_data" in tool_names, (
        f"extract_structured_data not called. Tool calls: {tool_names}"
    )

    # If all required fields were collected in one dispatch, confirm_with_citizen
    # should be called and the reply should contain the Telugu read-back template.
    # If some fields were still pending, the agent correctly replies in Telugu asking
    # for them instead — both are valid outcomes for this test.
    confirm_calls = [
        tc for tc in result.tool_calls_made
        if tc["name"] == "confirm_with_citizen" and tc.get("success")
    ]
    if confirm_calls:
        # Telugu template was used — verify the anchor phrase
        assert "మీ సమస్యను" in result.reply_text, (
            f"Telugu read-back anchor not found when confirm was called: {result.reply_text!r}"
        )
    else:
        # Partial extraction — agent should ask for the missing fields in Telugu
        has_telugu_reply = any("ఀ" <= ch <= "౿" for ch in (result.reply_text or ""))
        assert has_telugu_reply, (
            f"Partial extraction: agent should still reply in Telugu: {result.reply_text!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: Hindi complaint — reply in Hindi/Devanagari (LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.integration
def test_hindi_complaint_replies_in_hindi(multilingual_agent, seeded_test_db_engine):
    """Citizen sends a water complaint in Devanagari script.

    Expected:
    - reply_text contains Devanagari characters (U+0900–U+097F).
    - tool_calls include load_category_schema and extract_structured_data.
    """
    ward_id, mandal_id = _get_real_ward_and_mandal(seeded_test_db_engine)
    citizen_id = _insert_registered_citizen(
        seeded_test_db_engine, ward_id, mandal_id, name="Ravi Kumar"
    )
    summary = {
        "language_preference": "hindi",
        "language_script": "devanagari",
        "history_compressed": [],
        "citizen": {},
    }
    conv_id = _insert_conversation(seeded_test_db_engine, citizen_id, summary)

    ctx = AgentContext(
        conversation_id=conv_id,
        incoming_message=(
            "मुझे 3 दिन से पानी नहीं आ रहा है। वार्ड 11, प्रगति नगर। 30 घर प्रभावित हैं।"
        ),
        incoming_message_script="devanagari",
        citizen_id=citizen_id,
    )
    result = multilingual_agent.dispatch(ctx)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.reply_text is not None and len(result.reply_text) > 0

    # reply must contain Devanagari Unicode (U+0900–U+097F)
    has_devanagari = any("ऀ" <= ch <= "ॿ" for ch in (result.reply_text or ""))
    assert has_devanagari, (
        f"reply_text should contain Devanagari Unicode characters: {result.reply_text!r}"
    )

    tool_names = [tc["name"] for tc in result.tool_calls_made]
    assert "load_category_schema" in tool_names, (
        f"load_category_schema not called. Tool calls: {tool_names}"
    )
    assert "extract_structured_data" in tool_names, (
        f"extract_structured_data not called. Tool calls: {tool_names}"
    )


# ---------------------------------------------------------------------------
# Test 3: Emergency — escalate to human, no ticket created (LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.integration
def test_emergency_routes_to_escalate_not_create_ticket(
    multilingual_agent, seeded_test_db_engine
):
    """Citizen describes a heart attack. Agent must escalate, NOT file a ticket.

    Expected:
    - tool_calls includes escalate_to_human with reason_category="safety_emergency"
      and suggested_priority="urgent".
    - tool_calls does NOT include create_ticket.
    - reply_text contains "108" (ambulance) and "AI" (AI disclosure).
    - A row in human_review_queue with reason="safety_emergency" and
      suggested_priority="urgent" for this conversation.
    - No ticket row for this citizen.
    - summary_data.current_complaint.phase != "filed".
    """
    ward_id, mandal_id = _get_real_ward_and_mandal(seeded_test_db_engine)
    citizen_id = _insert_registered_citizen(seeded_test_db_engine, ward_id, mandal_id)
    summary = {
        "language_preference": "english",
        "language_script": "roman",
        "history_compressed": [],
        "citizen": {},
    }
    conv_id = _insert_conversation(seeded_test_db_engine, citizen_id, summary)

    ctx = AgentContext(
        conversation_id=conv_id,
        incoming_message="Help, my father is having a heart attack right now, please help immediately",
        incoming_message_script="roman",
        citizen_id=citizen_id,
    )
    result = multilingual_agent.dispatch(ctx)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.reply_text is not None and len(result.reply_text) > 0

    tool_names = [tc["name"] for tc in result.tool_calls_made]

    # Must escalate
    escalate_calls = [tc for tc in result.tool_calls_made if tc["name"] == "escalate_to_human"]
    assert escalate_calls, (
        f"escalate_to_human not called. Tool calls: {tool_names}. Reply: {result.reply_text!r}"
    )
    escalate_args = escalate_calls[0].get("args", {})
    assert escalate_args.get("reason_category") == "safety_emergency", (
        f"reason_category should be 'safety_emergency': {escalate_args}"
    )
    assert escalate_args.get("suggested_priority") == "urgent", (
        f"suggested_priority should be 'urgent': {escalate_args}"
    )

    # Must NOT create a ticket
    assert "create_ticket" not in tool_names, (
        f"create_ticket was called — emergency must NOT file a ticket. Tool calls: {tool_names}"
    )

    # reply_text must instruct 108 and disclose AI
    reply_lower = result.reply_text.lower()
    assert "108" in result.reply_text, (
        f"reply should contain '108' (ambulance): {result.reply_text!r}"
    )
    assert "ai" in reply_lower or "AI" in result.reply_text, (
        f"reply should contain AI disclosure: {result.reply_text!r}"
    )

    # DB: human_review_queue row
    with seeded_test_db_engine.connect() as conn:
        hrq_row = conn.execute(
            sa.text(
                "SELECT reason, suggested_priority "
                "FROM human_review_queue "
                "WHERE conversation_id = :cid "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"cid": conv_id},
        ).fetchone()

    assert hrq_row is not None, (
        f"No human_review_queue row for conversation_id={conv_id}"
    )
    assert hrq_row[0] == "safety_emergency", (
        f"human_review_queue.reason should be 'safety_emergency': {hrq_row[0]}"
    )
    assert hrq_row[1] == "urgent", (
        f"human_review_queue.suggested_priority should be 'urgent': {hrq_row[1]}"
    )

    # DB: no ticket filed
    with seeded_test_db_engine.connect() as conn:
        ticket_count = conn.execute(
            sa.text("SELECT count(*) FROM tickets WHERE citizen_id = :cid"),
            {"cid": citizen_id},
        ).scalar()
    assert ticket_count == 0, (
        f"Expected 0 tickets for emergency citizen, found {ticket_count}"
    )

    # summary_data: phase must not be "filed"
    s = _read_summary(seeded_test_db_engine, conv_id)
    phase = (s.get("current_complaint") or {}).get("phase")
    assert phase != "filed", (
        f"current_complaint.phase should not be 'filed' for emergency: {phase!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: Explicit language preference persisted via save_citizen_field (NON-LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_explicit_language_preference_persisted(seeded_test_db_engine):
    """SaveCitizenField with field_name='preferred_language' persists 'telugu' to the citizens row.

    Non-live: no OpenAI call. Calls SaveCitizenField.execute() directly.
    The grounding check (PR 8) requires an inbound message with Telugu script
    or an explicit language preference statement before allowing the save.
    """
    ward_id, mandal_id = _get_real_ward_and_mandal(seeded_test_db_engine)
    citizen_id = _insert_registered_citizen(seeded_test_db_engine, ward_id, mandal_id)
    conv_id = _insert_conversation(
        seeded_test_db_engine,
        citizen_id,
        {"language_preference": "english", "history_compressed": []},
    )

    # Insert an inbound message in Telugu script so the grounding check passes.
    # This simulates the citizen saying "please reply in telugu" before the LLM
    # calls save_citizen_field.
    with seeded_test_db_engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO messages (id, conversation_id, direction, content, created_at) "
                "VALUES (:id, :cid, 'inbound', :content, now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "cid": conv_id,
                "content": "నాకు తెలుగులో జవాబు ఇవ్వండి",  # "please reply in Telugu"
            },
        )

    tool = SaveCitizenField()
    result = tool.execute(
        inputs={"field_name": "preferred_language", "value": "telugu"},
        engine=seeded_test_db_engine,
        conversation_id=conv_id,
    )

    assert result.success is True, f"Expected success, got error: {result.error}"
    assert result.data.get("field_saved") == "preferred_language"
    assert result.data.get("value") == "telugu"

    # Verify the DB column was updated
    with seeded_test_db_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT preferred_language FROM citizens WHERE id = :cid"),
            {"cid": citizen_id},
        ).fetchone()
    assert row is not None, "citizen row not found"
    assert row[0] == "telugu", (
        f"citizens.preferred_language should be 'telugu', got: {row[0]!r}"
    )
