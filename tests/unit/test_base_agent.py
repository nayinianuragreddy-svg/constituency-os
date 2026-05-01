"""Unit tests for BaseAgent skeleton from PR 4a.

These tests confirm the abstract class enforces the contract correctly.
Real dispatch tests come in PR 4e.
"""

import pytest
from app.agents.base import BaseAgent, AgentContext, AgentResult


class _StubAgent(BaseAgent):
    """Minimal subclass for testing the contract enforcement."""
    agent_name = "test_stub"
    runtime_pattern = "reactive"

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

        def dispatch(self, context):
            return AgentResult(None, [], 0.0, 0, False, None)

    with pytest.raises(ValueError, match="agent_name"):
        BadAgent()


def test_subclass_without_runtime_pattern_raises():
    class BadAgent(BaseAgent):
        agent_name = "x"

        def dispatch(self, context):
            return AgentResult(None, [], 0.0, 0, False, None)

    with pytest.raises(ValueError, match="runtime_pattern"):
        BadAgent()


def test_stub_agent_instantiates_and_dispatches():
    agent = _StubAgent()
    ctx = AgentContext(
        conversation_id="00000000-0000-0000-0000-000000000001",
        incoming_message="hello",
        incoming_message_script="roman",
        citizen_id=None,
    )
    result = agent.dispatch(ctx)
    assert result.reply_text == "stub"
    assert result.escalated is False


def test_unimplemented_methods_raise_not_implemented():
    """The four methods that PR 4e implements should raise NotImplementedError in PR 4a."""
    agent = _StubAgent()
    ctx = AgentContext(
        conversation_id="00000000-0000-0000-0000-000000000001",
        incoming_message="hello",
        incoming_message_script="roman",
        citizen_id=None,
    )
    with pytest.raises(NotImplementedError, match="PR 4e"):
        agent.read_state(ctx)
    with pytest.raises(NotImplementedError, match="PR 4e"):
        agent.call_llm([], [])
    with pytest.raises(NotImplementedError, match="PR 4e"):
        agent.log_action({})
