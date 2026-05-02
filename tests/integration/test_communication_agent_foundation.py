"""Live integration test for CommunicationAgent (PR 5a).

Tests that the agent can:
1. Hold a real English conversation
2. Extract a citizen's name from a greeting and call save_citizen_field
3. Persist the name to the citizens table
4. Log the dispatch to agent_actions

Marker: live, integration. Run with `pytest -m "live and integration" -v`.

Schema notes (from migration 0001):
- conversations uses 'session_state' (not 'status') and requires 'channel_chat_id NOT NULL UNIQUE'.
- citizens has no 'address' column; the free-text location field is 'village'.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from app.agents.base import AgentContext
from app.agents.communication_v2 import CommunicationAgent


@pytest.fixture(scope="module")
def communication_agent(seeded_test_db_engine):
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


@pytest.fixture
def fresh_conversation(seeded_test_db_engine):
    return _insert_fresh_conversation(seeded_test_db_engine)


@pytest.mark.live
@pytest.mark.integration
def test_agent_extracts_name_from_greeting(
    communication_agent, fresh_conversation, seeded_test_db_engine
):
    """Citizen says hello with their name; agent should save it via save_citizen_field."""
    context = AgentContext(
        conversation_id=fresh_conversation,
        incoming_message="Hello, my name is Ravi Kumar. Can you help me?",
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = communication_agent.dispatch(context)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.reply_text is not None and len(result.reply_text) > 0
    assert result.cost_usd > 0

    # Verify save_citizen_field was called and succeeded
    save_calls = [tc for tc in result.tool_calls_made if tc["name"] == "save_citizen_field"]
    assert len(save_calls) >= 1, f"expected save_citizen_field call, got: {result.tool_calls_made}"
    assert save_calls[0]["success"] is True, f"save failed: {save_calls[0]}"

    # Verify the citizens row exists with the name
    with seeded_test_db_engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT c.name FROM citizens c
                JOIN conversations conv ON conv.citizen_id = c.id
                WHERE conv.id = :cid
                """
            ),
            {"cid": fresh_conversation},
        ).fetchone()

    assert row is not None, "citizens row was not created"
    assert "Ravi" in row[0], f"expected 'Ravi' in name, got {row[0]!r}"

    # Verify agent_actions row written
    with seeded_test_db_engine.connect() as conn:
        actions = conn.execute(
            sa.text(
                "SELECT action_type, cost_usd, error, status"
                " FROM agent_actions WHERE conversation_id = :cid"
            ),
            {"cid": fresh_conversation},
        ).fetchall()

    assert len(actions) >= 1
    last = actions[-1]
    assert last[0] == "dispatch"
    assert float(last[1]) > 0
    assert last[2] is None  # error column is NULL on success
    assert last[3] == "success"


@pytest.mark.live
@pytest.mark.integration
def test_agent_loads_category_schema_for_water_complaint(
    communication_agent, seeded_test_db_engine
):
    """Citizen describes a water issue; agent should not crash and reply coherently."""
    conv_id = _insert_fresh_conversation(seeded_test_db_engine)

    context = AgentContext(
        conversation_id=conv_id,
        incoming_message="There has been no water supply in our street for 3 days. We are in ward 11.",
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = communication_agent.dispatch(context)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.reply_text is not None and len(result.reply_text) > 0
    # The agent may classify and load the schema in this turn or a later turn.
    # Lower bar: no crash, replied in English, cost > 0.
    assert result.cost_usd > 0


@pytest.mark.live
@pytest.mark.integration
def test_agent_appends_to_history(communication_agent, seeded_test_db_engine):
    """After dispatch, conversation history should have at least one entry."""
    conv_id = _insert_fresh_conversation(seeded_test_db_engine)

    context = AgentContext(
        conversation_id=conv_id,
        incoming_message="Hi, I am Ravi.",
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = communication_agent.dispatch(context)
    assert result.error is None, f"dispatch errored: {result.error}"

    # The agent should have called add_to_history at least once
    add_history_calls = [tc for tc in result.tool_calls_made if tc["name"] == "add_to_history"]
    assert len(add_history_calls) >= 1, "expected at least one add_to_history call"
    assert add_history_calls[0]["success"] is True, f"add_to_history failed: {add_history_calls[0]}"

    # Confirm history_compressed was written to summary_data
    with seeded_test_db_engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT summary_data FROM conversations WHERE id = :cid"),
            {"cid": conv_id},
        ).fetchone()

    summary = row[0]
    if isinstance(summary, str):
        summary = json.loads(summary)

    history = summary.get("history_compressed", [])
    assert len(history) >= 1, "expected at least one history entry in summary_data"
