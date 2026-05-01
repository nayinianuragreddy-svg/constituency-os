"""Unit tests for PromptRenderer (PR 4b).

These tests lock in the rendering contract:
- Same inputs produce same output (determinism)
- Every placeholder gets substituted
- Missing inputs default to documented fallback strings
- Malformed inputs raise PromptRendererError, not silent corruption
- history_compressed is truncated to HISTORY_RENDER_CAP entries
- category schema renders with REQUIRED/OPTIONAL markers and enum options
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import pytest

from app.agents.runtime.prompt_renderer import (
    PromptRenderer,
    PromptRendererError,
    HISTORY_RENDER_CAP,
    IST,
)


FIXTURE_TEMPLATE = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "test_prompt_template.md"
)


def _renderer() -> PromptRenderer:
    return PromptRenderer(agent_name="test", prompt_template_path=FIXTURE_TEMPLATE)


def _fixed_date() -> datetime:
    return datetime(2026, 5, 1, 14, 30, 0, tzinfo=IST)


def test_init_rejects_empty_agent_name():
    with pytest.raises(PromptRendererError, match="agent_name"):
        PromptRenderer(agent_name="", prompt_template_path=FIXTURE_TEMPLATE)


def test_init_rejects_empty_template_path():
    with pytest.raises(PromptRendererError, match="prompt_template_path"):
        PromptRenderer(agent_name="test", prompt_template_path="")


def test_init_rejects_missing_template_file():
    with pytest.raises(PromptRendererError, match="not found"):
        PromptRenderer(
            agent_name="test",
            prompt_template_path="/nonexistent/path/to/template.md",
        )


def test_render_with_minimal_inputs_uses_defaults():
    rendered = _renderer().render(
        conversation_summary={},
        current_date_ist=_fixed_date(),
    )

    assert "the MLA" in rendered
    assert "this constituency" in rendered
    assert "english" in rendered
    assert "roman" in rendered
    assert "Not loaded yet." in rendered
    assert "01 May 2026" in rendered
    assert "No conversation state yet." in rendered


def test_render_substitutes_constituency_config():
    rendered = _renderer().render(
        conversation_summary={},
        constituency_config={
            "mla_name": "Anurag Reddy garu",
            "name": "Ibrahimpatnam",
        },
        current_date_ist=_fixed_date(),
    )

    assert "Anurag Reddy garu" in rendered
    assert "Ibrahimpatnam" in rendered


def test_render_substitutes_language_and_script_from_summary():
    rendered = _renderer().render(
        conversation_summary={
            "language_preference": "telugu",
            "language_script": "telugu",
        },
        current_date_ist=_fixed_date(),
    )

    assert "telugu" in rendered.lower()


def test_render_is_deterministic():
    """Same inputs MUST produce same output. This is the core contract."""
    summary = {
        "language_preference": "english",
        "language_script": "roman",
        "citizen": {"fields_known": {"name": "Ravi", "ward_number": "11"}},
    }
    fixed_date = _fixed_date()

    a = _renderer().render(conversation_summary=summary, current_date_ist=fixed_date)
    b = _renderer().render(conversation_summary=summary, current_date_ist=fixed_date)

    assert a == b


def test_render_formats_citizen_fields():
    rendered = _renderer().render(
        conversation_summary={
            "citizen": {
                "fields_known": {
                    "name": "Anurag Reddy",
                    "mobile": "9876543210",
                    "ward_number": "11",
                }
            }
        },
        current_date_ist=_fixed_date(),
    )

    assert "Anurag Reddy" in rendered
    assert "9876543210" in rendered
    assert "11" in rendered


def test_render_formats_current_complaint_with_pending_and_filled_fields():
    rendered = _renderer().render(
        conversation_summary={
            "current_complaint": {
                "phase": "collect",
                "category_code": "PUBLIC",
                "subcategory_code": "PUB.WATER",
                "ticket_id_prefix": "PUB-WTR",
                "current_format": {
                    "fields": [
                        {"name": "issue_type", "required": True, "value": "no_supply"},
                        {"name": "households_affected", "required": True, "value": None},
                        {"name": "previous_complaint_ref", "required": False, "value": None},
                    ]
                },
            }
        },
        current_date_ist=_fixed_date(),
    )

    assert "PUB.WATER" in rendered
    assert "issue_type" in rendered
    assert "no_supply" in rendered
    assert "FILLED" in rendered
    assert "PENDING" in rendered
    assert "households_affected" in rendered


def test_render_truncates_history_to_cap():
    """history_compressed beyond HISTORY_RENDER_CAP entries must be dropped from the rendered output."""
    history = [
        {"role": "citizen", "text": f"message number {i}"}
        for i in range(HISTORY_RENDER_CAP + 5)
    ]
    rendered = _renderer().render(
        conversation_summary={"history_compressed": history},
        current_date_ist=_fixed_date(),
    )

    # The first 5 messages should NOT appear in the rendered output.
    # Check with a trailing newline to avoid "message number 1" matching inside "message number 10".
    for i in range(5):
        assert f"message number {i}\n" not in rendered

    # The last HISTORY_RENDER_CAP messages SHOULD appear
    for i in range(5, HISTORY_RENDER_CAP + 5):
        assert f"message number {i}" in rendered


def test_render_formats_loaded_category_schema_with_enum_options():
    schema = {
        "subcategory_code": "PUB.WATER",
        "fields": [
            {
                "name": "issue_type",
                "type": "enum",
                "required": True,
                "options": ["no_supply", "contamination", "pipeline_break"],
            },
            {
                "name": "exact_location",
                "type": "string",
                "required": True,
            },
            {
                "name": "previous_complaint_ref",
                "type": "string",
                "required": False,
            },
        ],
    }
    rendered = _renderer().render(
        conversation_summary={},
        category_schema=schema,
        current_date_ist=_fixed_date(),
    )

    assert "Required fields for PUB.WATER" in rendered
    assert "issue_type" in rendered
    assert "no_supply | contamination | pipeline_break" in rendered
    assert "REQUIRED" in rendered
    assert "OPTIONAL" in rendered


def test_render_formats_open_questions():
    rendered = _renderer().render(
        conversation_summary={
            "open_questions": ["What is the ward number?", "How many days has the issue been ongoing?"]
        },
        current_date_ist=_fixed_date(),
    )

    assert "What is the ward number?" in rendered
    assert "How many days has the issue been ongoing?" in rendered


def test_render_raises_on_missing_placeholder_in_template(tmp_path):
    """If the template references a placeholder we do not supply, render() must fail loudly."""
    bad_template = tmp_path / "bad_template.md"
    bad_template.write_text("Hello {undefined_placeholder}.")

    renderer = PromptRenderer(
        agent_name="test", prompt_template_path=str(bad_template)
    )

    with pytest.raises(PromptRendererError, match="undefined_placeholder"):
        renderer.render(conversation_summary={}, current_date_ist=_fixed_date())


def test_render_handles_telugu_unicode_in_inputs():
    """Telugu strings in fields_known must survive substitution intact (no encoding errors)."""
    rendered = _renderer().render(
        conversation_summary={
            "citizen": {"fields_known": {"name": "అనురాగ్ రెడ్డి"}}
        },
        current_date_ist=_fixed_date(),
    )

    assert "అనురాగ్ రెడ్డి" in rendered


def test_default_current_date_ist_is_now():
    """If current_date_ist is None, render uses datetime.now(IST). Smoke test that it doesn't crash."""
    rendered = _renderer().render(conversation_summary={})
    # The current year should appear in the rendered output
    current_year = str(datetime.now(IST).year)
    assert current_year in rendered
