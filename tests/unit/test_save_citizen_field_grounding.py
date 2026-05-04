"""Unit tests for preferred_language grounding in save_citizen_field.

Tests the _is_grounded_for_language helper directly and the full execute()
path via mocked DB engine to verify the grounding gate.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.communication_v2.tools.save_citizen_field import (
    SaveCitizenField,
    _is_grounded_for_language,
)


# ---------------------------------------------------------------------------
# Pure grounding function tests (no DB needed)
# ---------------------------------------------------------------------------

def test_telugu_script_grounds_telugu():
    assert _is_grounded_for_language("telugu", "నాకు 3 రోజులుగా నీళ్లు లేవు") is True


def test_english_message_does_not_ground_telugu():
    assert _is_grounded_for_language("telugu", "Yes, that is correct.") is False


def test_devanagari_script_grounds_hindi():
    assert _is_grounded_for_language("hindi", "मुझे 3 दिन से पानी नहीं") is True


def test_roman_script_grounds_english():
    assert _is_grounded_for_language("english", "no water for 3 days") is True


def test_explicit_telugu_statement_grounds_telugu():
    assert _is_grounded_for_language("telugu", "please reply in telugu") is True


def test_explicit_hindi_statement_grounds_hindi():
    assert _is_grounded_for_language("hindi", "मुझे हिंदी में जवाब दीजिये") is True


def test_telugu_script_does_not_ground_english():
    assert _is_grounded_for_language("english", "నాకు సహాయం కావాలి") is False


def test_devanagari_does_not_ground_english():
    assert _is_grounded_for_language("english", "मुझे मदद चाहिए") is False


def test_explicit_english_grounds_english():
    assert _is_grounded_for_language("english", "please reply in english") is True


# ---------------------------------------------------------------------------
# Full execute() tests via mocked engine
# ---------------------------------------------------------------------------

def _make_engine(last_message: str | None):
    """Build a mock engine that returns last_message as the most recent inbound."""
    engine = MagicMock()
    conn = MagicMock()
    # Used for grounding check (connect, not begin)
    conn.execute.return_value.fetchone.return_value = (last_message,) if last_message is not None else None
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine


def test_execute_telugu_grounded_by_script():
    engine = _make_engine("నాకు 3 రోజులుగా నీళ్లు లేవు")
    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "preferred_language", "value": "telugu"},
        engine,
        "conv-1",
    )
    assert result.success is True


def test_execute_telugu_rejected_for_english_confirmation():
    engine = _make_engine("Yes, that is correct.")
    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "preferred_language", "value": "telugu"},
        engine,
        "conv-1",
    )
    assert result.success is False
    assert "not grounded" in result.error


def test_execute_hindi_grounded_by_script():
    engine = _make_engine("मुझे 3 दिन से पानी नहीं")
    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "preferred_language", "value": "hindi"},
        engine,
        "conv-1",
    )
    assert result.success is True


def test_execute_english_grounded_by_roman_script():
    engine = _make_engine("no water for 3 days")
    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "preferred_language", "value": "english"},
        engine,
        "conv-1",
    )
    assert result.success is True


def test_execute_telugu_grounded_by_explicit_statement():
    engine = _make_engine("please reply in telugu")
    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "preferred_language", "value": "telugu"},
        engine,
        "conv-1",
    )
    assert result.success is True


def test_execute_hindi_grounded_by_explicit_statement():
    engine = _make_engine("मुझे हिंदी में जवाब दीजिये")
    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "preferred_language", "value": "hindi"},
        engine,
        "conv-1",
    )
    assert result.success is True


def test_execute_other_field_bypasses_grounding():
    """Non-language fields must not be affected by the grounding logic."""
    engine = MagicMock()
    # Simulate the conversation lookup returning a citizen_id and successful UPDATE
    begin_conn = MagicMock()
    begin_conn.execute.return_value.fetchone.return_value = ("citizen-uuid-1",)
    engine.begin.return_value.__enter__ = MagicMock(return_value=begin_conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)

    tool = SaveCitizenField()
    result = tool.execute(
        {"field_name": "name", "value": "Ravi Kumar"},
        engine,
        "conv-1",
    )
    assert result.success is True
    assert result.data.get("field_saved") == "name"
