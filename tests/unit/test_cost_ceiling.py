"""Unit tests for the cost ceiling enforcement in CommunicationAgent.dispatch().

Tests verify that:
- Dispatch proceeds normally when today's cost is below the ceiling.
- Dispatch is blocked with cost_ceiling_exceeded when at or above the ceiling.
- The denial message is localised to the citizen's script.
- The ceiling defaults to 6.00 when missing from constituency_config.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.base import AgentContext, AgentResult
from app.agents.communication_v2.agent import CommunicationAgent


def _make_agent(constituency_config: dict | None = None) -> CommunicationAgent:
    """Build a CommunicationAgent with mocked LLM and engine."""
    engine = MagicMock()
    llm_client = MagicMock()
    agent = CommunicationAgent(
        engine=engine,
        llm_client=llm_client,
        constituency_config=constituency_config or {"mla_name": "Test MLA", "name": "Test"},
    )
    return agent


def _ctx(script: str = "roman") -> AgentContext:
    return AgentContext(
        conversation_id="conv-test",
        incoming_message="hello",
        incoming_message_script=script,
        citizen_id=None,
    )


# ---------------------------------------------------------------------------
# Below ceiling — dispatch proceeds
# ---------------------------------------------------------------------------

def test_below_ceiling_calls_llm():
    agent = _make_agent({"mla_name": "Test", "name": "Test", "cost_ceiling_usd_per_day": 6.00})

    with patch.object(agent, "_compute_today_cost_usd", return_value=1.50), \
         patch.object(agent, "_state_reader") as mock_sr, \
         patch.object(agent, "_prompt_renderer") as mock_pr, \
         patch.object(agent, "_llm_client") as mock_llm:

        mock_sr.read.return_value = {}
        mock_pr.render.return_value = "system prompt"
        mock_llm.call.return_value = MagicMock(
            cost_usd=0.01,
            input_tokens=100,
            output_tokens=50,
            parsed={"reply_text": "Hello!", "tool_calls": []},
        )

        result = agent.dispatch(_ctx())

    assert result.error is None
    assert mock_llm.call.called


# ---------------------------------------------------------------------------
# At ceiling — dispatch blocked
# ---------------------------------------------------------------------------

def test_at_ceiling_blocks_dispatch():
    agent = _make_agent({"mla_name": "Test", "name": "Test", "cost_ceiling_usd_per_day": 6.00})

    with patch.object(agent, "_compute_today_cost_usd", return_value=6.00), \
         patch.object(agent, "_llm_client") as mock_llm:

        result = agent.dispatch(_ctx())

    assert result.error == "cost_ceiling_exceeded"
    assert not mock_llm.call.called
    assert result.cost_usd == 0.0
    assert result.hops_used == 0


# ---------------------------------------------------------------------------
# Above ceiling — dispatch blocked
# ---------------------------------------------------------------------------

def test_above_ceiling_blocks_dispatch():
    agent = _make_agent({"mla_name": "Test", "name": "Test", "cost_ceiling_usd_per_day": 6.00})

    with patch.object(agent, "_compute_today_cost_usd", return_value=7.42), \
         patch.object(agent, "_llm_client") as mock_llm:

        result = agent.dispatch(_ctx())

    assert result.error == "cost_ceiling_exceeded"
    assert not mock_llm.call.called


# ---------------------------------------------------------------------------
# Localised denial messages
# ---------------------------------------------------------------------------

def test_ceiling_message_telugu():
    agent = _make_agent()
    with patch.object(agent, "_compute_today_cost_usd", return_value=10.0):
        result = agent.dispatch(_ctx(script="telugu"))
    assert result.error == "cost_ceiling_exceeded"
    # Telugu script characters present
    assert any(0x0C00 <= ord(c) <= 0x0C7F for c in (result.reply_text or ""))


def test_ceiling_message_hindi():
    agent = _make_agent()
    with patch.object(agent, "_compute_today_cost_usd", return_value=10.0):
        result = agent.dispatch(_ctx(script="devanagari"))
    assert result.error == "cost_ceiling_exceeded"
    # Devanagari script characters present
    assert any(0x0900 <= ord(c) <= 0x097F for c in (result.reply_text or ""))


def test_ceiling_message_english():
    agent = _make_agent()
    with patch.object(agent, "_compute_today_cost_usd", return_value=10.0):
        result = agent.dispatch(_ctx(script="roman"))
    assert result.error == "cost_ceiling_exceeded"
    assert "unavailable" in (result.reply_text or "").lower()


# ---------------------------------------------------------------------------
# Default ceiling is 6.00
# ---------------------------------------------------------------------------

def test_default_ceiling_is_6_usd():
    agent = _make_agent({"mla_name": "Test", "name": "Test"})
    # 5.99 should NOT trigger ceiling
    with patch.object(agent, "_compute_today_cost_usd", return_value=5.99), \
         patch.object(agent, "_state_reader") as mock_sr, \
         patch.object(agent, "_prompt_renderer") as mock_pr, \
         patch.object(agent, "_llm_client") as mock_llm:

        mock_sr.read.return_value = {}
        mock_pr.render.return_value = "system prompt"
        mock_llm.call.return_value = MagicMock(
            cost_usd=0.01,
            input_tokens=100,
            output_tokens=50,
            parsed={"reply_text": "Hello!", "tool_calls": []},
        )

        result = agent.dispatch(_ctx())

    assert result.error is None
    assert mock_llm.call.called


def test_default_ceiling_triggers_at_6_usd():
    agent = _make_agent({"mla_name": "Test", "name": "Test"})
    with patch.object(agent, "_compute_today_cost_usd", return_value=6.00), \
         patch.object(agent, "_llm_client") as mock_llm:

        result = agent.dispatch(_ctx())

    assert result.error == "cost_ceiling_exceeded"
    assert not mock_llm.call.called
