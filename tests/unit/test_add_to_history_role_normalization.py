"""Unit tests for add_to_history role normalization (PR 5b1).

Verifies that:
- role="assistant" is accepted and stored as "agent"
- role="agent" passes through unchanged
- role="user" (or any other non-enum value) is rejected

These tests write to a real Postgres DB via seeded_test_db_engine because
add_to_history uses FOR UPDATE which SQLite does not support.
They do NOT call the LLM, so no 'live' mark is needed.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from app.agents.communication_v2.tools.add_to_history import AddToHistory


@pytest.fixture(scope="module")
def tool() -> AddToHistory:
    return AddToHistory()


def _insert_conversation(engine) -> str:
    """Insert a minimal conversation row and return its id."""
    conv_id = str(uuid.uuid4())
    summary = {"history_compressed": []}
    with engine.begin() as conn:
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
            {"id": conv_id, "ccid": str(uuid.uuid4()), "s": json.dumps(summary)},
        )
    return conv_id


def _read_history(engine, conv_id: str) -> list:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT summary_data FROM conversations WHERE id = :cid"),
            {"cid": conv_id},
        ).fetchone()
    data = row[0]
    if isinstance(data, str):
        data = json.loads(data)
    return data.get("history_compressed", [])


@pytest.mark.integration
def test_role_assistant_normalized_to_agent(tool, seeded_test_db_engine):
    """role='assistant' must be accepted and stored as 'agent'."""
    conv_id = _insert_conversation(seeded_test_db_engine)

    result = tool.execute(
        {"role": "assistant", "text": "I can help you with that."},
        seeded_test_db_engine,
        conv_id,
    )

    assert result.success is True, f"expected success, got error: {result.error}"

    history = _read_history(seeded_test_db_engine, conv_id)
    assert len(history) == 1
    assert history[0]["role"] == "agent", (
        f"stored role should be 'agent', got {history[0]['role']!r}"
    )
    assert history[0]["text"] == "I can help you with that."


@pytest.mark.integration
def test_role_agent_passes_through(tool, seeded_test_db_engine):
    """role='agent' must be accepted and stored as 'agent' unchanged."""
    conv_id = _insert_conversation(seeded_test_db_engine)

    result = tool.execute(
        {"role": "agent", "text": "Thank you for reaching out."},
        seeded_test_db_engine,
        conv_id,
    )

    assert result.success is True, f"expected success, got error: {result.error}"

    history = _read_history(seeded_test_db_engine, conv_id)
    assert len(history) == 1
    assert history[0]["role"] == "agent"


@pytest.mark.integration
def test_role_invalid_rejected(tool, seeded_test_db_engine):
    """role values outside the allowed set must be rejected."""
    conv_id = _insert_conversation(seeded_test_db_engine)

    for bad_role in ("user", "system", "bot", ""):
        result = tool.execute(
            {"role": bad_role, "text": "some text"},
            seeded_test_db_engine,
            conv_id,
        )
        assert result.success is False, (
            f"role={bad_role!r} should be rejected but was accepted"
        )

    # Confirm nothing was written
    history = _read_history(seeded_test_db_engine, conv_id)
    assert len(history) == 0
