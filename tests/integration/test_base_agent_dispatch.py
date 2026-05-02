"""Live end-to-end dispatch test for BaseAgent (PR 4e).

This test composes every runtime component built in PR 4a–4d:
- PromptRenderer (prompt assembly)
- LLMClient (real OpenAI call with structured output)
- StructuredDataValidator (skipped — stub agent has no domain schema)
- SubstringGroundingChecker (skipped — stub agent grounds no text values)
- StateReader (real DB read)
- ActionLogger (real DB write)

If this test passes, the V2.0 runtime is functional. PR 5 builds the
Communication Agent on top of it.

Marker: live, integration. Run with `pytest -m "live and integration" -v`.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
import sqlalchemy as sa

from app.agents.base import BaseAgent, AgentContext, AgentResult
from app.agents.runtime import (
    LLMClient,
    PromptRenderer,
    StructuredDataValidator,
    SubstringGroundingChecker,
)


FIXTURE_PROMPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "fixtures", "dispatch_stub_prompt.md")
)


class DispatchStubAgent(BaseAgent):
    """Minimal stub. No domain schema, no grounding, no tools.

    Only purpose is to exercise the dispatch loop end-to-end.
    Named DispatchStubAgent (not TestStub*) to avoid pytest collecting it as a test class.
    """
    agent_name = "test_stub"
    runtime_pattern = "reactive"
    max_hops = 1

    def response_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reply_text": {"type": "string"},
                "echo": {"type": "string"},
            },
            "required": ["reply_text", "echo"],
            "additionalProperties": False,
        }


@pytest.fixture(scope="module")
def stub_agent(seeded_test_db_engine):
    return DispatchStubAgent(
        engine=seeded_test_db_engine,
        llm_client=LLMClient(),
        prompt_renderer=PromptRenderer("test_stub", FIXTURE_PROMPT),
    )


@pytest.fixture(scope="module")
def seeded_conversation(seeded_test_db_engine):
    """Insert a conversations row and return its id.

    conversations schema (from 0001_initial_schema.py):
      id, channel, channel_chat_id (NOT NULL), citizen_id, last_message_at,
      summary_data, session_state, preferred_language, created_at, updated_at
    """
    conv_id = str(uuid.uuid4())
    channel_chat_id = str(uuid.uuid4())
    summary = {
        "language_preference": "english",
        "language_script": "roman",
        "history_compressed": [],
        "current_complaint": {},
        "citizen": {},
    }
    with seeded_test_db_engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO conversations
                    (id, channel, channel_chat_id, citizen_id,
                     last_message_at, summary_data, session_state)
                VALUES
                    (:id, 'telegram', :channel_chat_id, NULL,
                     now(), :summary, 'active')
                """
            ),
            {"id": conv_id, "channel_chat_id": channel_chat_id, "summary": json.dumps(summary)},
        )
    return conv_id


@pytest.mark.live
@pytest.mark.integration
def test_dispatch_end_to_end(stub_agent, seeded_conversation, seeded_test_db_engine):
    """Real OpenAI, real DB, end-to-end. The full dispatch loop must:
    - load conversation state
    - render prompt
    - call OpenAI with structured output
    - validate / ground (no-ops for stub)
    - log to agent_actions
    - return AgentResult with cost > 0
    """
    context = AgentContext(
        conversation_id=seeded_conversation,
        incoming_message="Hello, can you help me with a water complaint?",
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = stub_agent.dispatch(context)

    assert result.error is None, f"dispatch errored: {result.error}"
    assert result.reply_text is not None and len(result.reply_text) > 0
    assert result.cost_usd > 0, "cost should be > 0 from a real OpenAI call"
    assert result.hops_used == 1
    assert result.escalated is False

    # Confirm the action was logged.
    # agent_actions schema: id, agent_name, action_type, citizen_id, ticket_id,
    # conversation_id, payload (JSONB), response (JSONB), status, idempotency_key,
    # cost_usd, hops_used, error, created_at
    with seeded_test_db_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT action_type, cost_usd, error, status FROM agent_actions WHERE conversation_id = :cid"
            ),
            {"cid": seeded_conversation},
        ).fetchall()

    assert len(rows) >= 1
    dispatch_rows = [r for r in rows if r[0] == "dispatch"]
    assert len(dispatch_rows) >= 1

    last = dispatch_rows[-1]
    assert last[3] == "success"  # status column
    assert float(last[1]) > 0    # cost_usd dedicated column
    assert last[2] is None       # error is NULL on success


@pytest.mark.live
@pytest.mark.integration
def test_dispatch_handles_missing_conversation(stub_agent):
    """If conversation_id does not exist in DB, dispatch returns an error result, not a crash."""
    bad_id = str(uuid.uuid4())
    context = AgentContext(
        conversation_id=bad_id,
        incoming_message="hello",
        incoming_message_script="roman",
        citizen_id=None,
    )

    result = stub_agent.dispatch(context)

    assert result.error is not None
    assert (
        "conversation not found" in result.error.lower()
        or "conversation_id" in result.error.lower()
    )
    assert result.reply_text is None
