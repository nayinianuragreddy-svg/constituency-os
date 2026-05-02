"""Unit tests for BaseAgent skeleton — updated in PR 4e.

PR 4e makes dispatch() concrete and introduces response_schema() as the new
abstract method. Unit tests use object() sentinels for engine/llm_client/
prompt_renderer since contract-enforcement tests do not exercise real dispatch.
"""

import pytest
from app.agents.base import BaseAgent, AgentContext, AgentResult


class _StubAgent(BaseAgent):
    """Minimal subclass for testing the contract enforcement."""
    agent_name = "test_stub"
    runtime_pattern = "reactive"

    def response_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"reply_text": {"type": "string"}},
            "required": ["reply_text"],
            "additionalProperties": False,
        }

    def dispatch(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            reply_text="stub",
            tool_calls_made=[],
            cost_usd=0.0,
            hops_used=0,
            escalated=False,
            error=None,
        )


def test_subclass_without_agent_name_raises():
    class BadAgent(BaseAgent):
        runtime_pattern = "reactive"

        def response_schema(self) -> dict:
            return {}

    with pytest.raises(ValueError, match="agent_name"):
        BadAgent(engine=object(), llm_client=object(), prompt_renderer=object())


def test_subclass_without_runtime_pattern_raises():
    class BadAgent(BaseAgent):
        agent_name = "x"

        def response_schema(self) -> dict:
            return {}

    with pytest.raises(ValueError, match="runtime_pattern"):
        BadAgent(engine=object(), llm_client=object(), prompt_renderer=object())


def test_stub_agent_instantiates_and_dispatches():
    agent = _StubAgent(engine=object(), llm_client=object(), prompt_renderer=object())
    ctx = AgentContext(
        conversation_id="00000000-0000-0000-0000-000000000001",
        incoming_message="hello",
        incoming_message_script="roman",
        citizen_id=None,
    )
    result = agent.dispatch(ctx)
    assert result.reply_text == "stub"
    assert result.escalated is False
