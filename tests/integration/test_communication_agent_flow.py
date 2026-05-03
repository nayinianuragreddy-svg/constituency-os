"""Integration tests for CommunicationAgent conversation flow (PR 5b).

Tests the two new tools: extract_structured_data and confirm_with_citizen,
plus the multi-hop dispatch loop.

Marker: live, integration. Run with `pytest -m "live and integration" -v`.
The substring_grounding test does not call the LLM and runs without -m live.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from app.agents.base import AgentContext
from app.agents.communication_v2 import CommunicationAgent
from app.agents.communication_v2.tools.extract_structured_data import ExtractStructuredData


@pytest.fixture(scope="module")
def flow_agent(seeded_test_db_engine):
    return CommunicationAgent(
        engine=seeded_test_db_engine,
        constituency_config={
            "mla_name": "Anurag Reddy garu",
            "name": "Ibrahimpatnam",
        },
    )


def _insert_fresh_conversation(engine) -> str:
    """Create a fresh conversations row. Returns the conversation id."""
    conv_id = str(uuid.uuid4())
    channel_chat_id = str(uuid.uuid4())
    summary = {
        "language_preference": "english",
        "language_script": "roman",
        "history_compressed": [],
        "citizen": {},
    }
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO conversations
                    (id, channel, channel_chat_id, citizen_id,
                     last_message_at, summary_data, session_state)
                VALUES
                    (:id, 'telegram', :channel_chat_id, NULL,
                     now(), :s, 'active')
                """
            ),
            {"id": conv_id, "channel_chat_id": channel_chat_id, "s": json.dumps(summary)},
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


@pytest.mark.live
@pytest.mark.integration
def test_full_water_complaint_flow_in_one_dispatch(flow_agent, seeded_test_db_engine):
    """Complete water complaint with all required values in one citizen message.

    The agent must, in one dispatch:
    1. Call load_category_schema for PUB.WATER
    2. Call extract_structured_data with the right values
    3. Call confirm_with_citizen to generate the read-back

    The reply_text should contain the read-back.
    """
    conv_id = _insert_fresh_conversation(seeded_test_db_engine)

    context = AgentContext(
        conversation_id=conv_id,
        incoming_message=(
            "There has been no water supply in our street for 3 days. "
            "We are in ward 11, Pragati Nagar, 4th street. "
            "About 30 households are affected. The borewell is also not working."
        ),
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = flow_agent.dispatch(context)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.cost_usd > 0
    assert result.hops_used >= 2, (
        f"expected at least 2 hops for state-changing tools, got {result.hops_used}"
    )

    tool_names = [tc["name"] for tc in result.tool_calls_made]
    successful = {tc["name"] for tc in result.tool_calls_made if tc.get("success")}

    assert "load_category_schema" in successful, (
        f"load_category_schema not called or failed; tool_calls: {result.tool_calls_made}"
    )

    extract_calls = [
        tc for tc in result.tool_calls_made
        if tc["name"] == "extract_structured_data" and tc.get("success")
    ]
    assert extract_calls, (
        f"extract_structured_data not called or failed; tool_calls: {result.tool_calls_made}"
    )
    extract_data = extract_calls[-1].get("data", {})
    accepted = extract_data.get("accepted_fields", [])
    assert len(accepted) >= 4, (
        f"expected at least 4 accepted fields, got {len(accepted)}: {accepted}"
    )

    assert "confirm_with_citizen" in successful, (
        f"confirm_with_citizen not called or failed; tool_calls: {result.tool_calls_made}"
    )

    # The reply_text should contain the read-back
    assert result.reply_text is not None
    reply_lower = result.reply_text.lower()
    assert any(
        phrase in reply_lower
        for phrase in ["noted your concern", "i have noted", "concern as follows"]
    ), f"reply_text doesn't look like a read-back: {result.reply_text!r}"

    # Verify DB state
    summary = _read_summary(seeded_test_db_engine, conv_id)
    current_complaint = summary.get("current_complaint", {})

    assert current_complaint.get("fields_pending") == [], (
        f"fields_pending should be empty after full collection: {current_complaint.get('fields_pending')}"
    )
    assert current_complaint.get("confirmation_state") == "pending", (
        f"confirmation_state should be 'pending': {current_complaint.get('confirmation_state')}"
    )


@pytest.mark.live
@pytest.mark.integration
def test_partial_complaint_asks_for_missing_field(flow_agent, seeded_test_db_engine):
    """Citizen sends a partial water complaint; agent extracts what it can and asks for more.

    With only "no water for 3 days" the agent should:
    - Call load_category_schema
    - Call extract_structured_data (some fields accepted, others pending)
    - NOT call confirm_with_citizen (premature)
    - Reply asking for at least one missing field
    """
    conv_id = _insert_fresh_conversation(seeded_test_db_engine)

    context = AgentContext(
        conversation_id=conv_id,
        incoming_message="No water in our area for 3 days.",
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = flow_agent.dispatch(context)

    assert result.error is None, f"dispatch errored: {result.error}"

    tool_names_succeeded = {tc["name"] for tc in result.tool_calls_made if tc.get("success")}

    assert "load_category_schema" in tool_names_succeeded, (
        f"load_category_schema not called or failed; tool_calls: {result.tool_calls_made}"
    )

    extract_calls = [
        tc for tc in result.tool_calls_made
        if tc["name"] == "extract_structured_data" and tc.get("success")
    ]
    assert extract_calls, (
        f"extract_structured_data not called or failed; tool_calls: {result.tool_calls_made}"
    )

    extract_data = extract_calls[-1].get("data", {})
    fields_pending = extract_data.get("fields_pending", [])
    assert len(fields_pending) > 0, (
        f"expected pending fields after partial complaint; pending: {fields_pending}"
    )

    # confirm_with_citizen should NOT have been called successfully
    confirm_succeeded = [
        tc for tc in result.tool_calls_made
        if tc["name"] == "confirm_with_citizen" and tc.get("success")
    ]
    assert not confirm_succeeded, (
        f"confirm_with_citizen should not succeed with pending fields; calls: {confirm_succeeded}"
    )

    # Reply should ask for at least one missing field
    assert result.reply_text is not None and len(result.reply_text) > 0
    reply_lower = result.reply_text.lower()
    asked_for_something = any(
        kw in reply_lower
        for kw in ["location", "address", "street", "ward", "household", "describe", "description", "detail"]
    )
    assert asked_for_something, (
        f"reply doesn't seem to ask for missing fields: {result.reply_text!r}"
    )

    # Verify DB state
    summary = _read_summary(seeded_test_db_engine, conv_id)
    current_complaint = summary.get("current_complaint", {})
    assert current_complaint.get("fields_pending"), (
        f"fields_pending in DB should be non-empty after partial complaint"
    )


@pytest.mark.integration
def test_substring_grounding_rejects_invented_value(seeded_test_db_engine):
    """extract_structured_data rejects a field value not present in source_text.

    This is a unit-style integration test against the tool directly (no LLM call).
    We pre-seed a conversation with the PUB.WATER schema already loaded, then call
    extract_structured_data with a households_affected value that doesn't appear in
    the source_text. The field must be rejected.
    """
    conv_id = str(uuid.uuid4())
    channel_chat_id = str(uuid.uuid4())

    # Pre-seed with schema loaded and a partial current_complaint
    summary = {
        "language_preference": "english",
        "language_script": "roman",
        "history_compressed": [],
        "citizen": {},
        "current_complaint": {
            "phase": "collect",
            "category_code": "PUB",
            "subcategory_code": "PUB.WATER",
            "category_schema_loaded": True,
            "ticket_id_prefix": "PUB-WTR",
            "current_format": {
                "fields": [
                    {"name": "issue_type", "required": True, "value": None, "source": None},
                    {"name": "exact_location", "required": True, "value": None, "source": None},
                    {"name": "duration_days", "required": True, "value": None, "source": None},
                    {"name": "households_affected", "required": True, "value": None, "source": None},
                    {"name": "previous_complaint_ref", "required": False, "value": None, "source": None},
                    {"name": "description", "required": True, "value": None, "source": None},
                ]
            },
            "fields_pending": [
                "issue_type", "exact_location", "duration_days",
                "households_affected", "description"
            ],
            "fields_collected_count": 0,
            "fields_required_count": 5,
        },
    }

    with seeded_test_db_engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO conversations
                    (id, channel, channel_chat_id, citizen_id,
                     last_message_at, summary_data, session_state)
                VALUES
                    (:id, 'telegram', :ccid, NULL, now(), :s, 'active')
                """
            ),
            {"id": conv_id, "ccid": channel_chat_id, "s": json.dumps(summary)},
        )

    tool = ExtractStructuredData()
    source_text = "No water in our street."  # "50" is NOT in this text

    result = tool.execute(
        inputs={
            "subcategory_code": "PUB.WATER",
            "source_text": source_text,
            "extracted_fields": [
                {"field_name": "households_affected", "value": "50"},
            ],
        },
        engine=seeded_test_db_engine,
        conversation_id=conv_id,
    )

    assert result.success is True, f"tool should succeed even with rejected fields: {result.error}"
    rejected = result.data.get("rejected_fields", [])
    assert len(rejected) == 1, f"expected 1 rejected field, got {rejected}"
    assert rejected[0]["field_name"] == "households_affected"
    assert "grounded" in rejected[0]["reason"] or "not found" in rejected[0]["reason"].lower()

    accepted = result.data.get("accepted_fields", [])
    assert len(accepted) == 0, f"expected 0 accepted fields, got {accepted}"
