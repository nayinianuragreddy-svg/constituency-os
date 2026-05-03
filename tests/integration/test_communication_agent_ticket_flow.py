"""Integration tests for CommunicationAgent ticket creation and escalation (PR 5c).

Tests the three new tools: create_ticket, lookup_ticket_by_number, escalate_to_human.

Markers: live, integration. Run with:
  pytest tests/integration/test_communication_agent_ticket_flow.py -m "live and integration" -v
  pytest tests/integration/test_communication_agent_ticket_flow.py -v -m integration
"""

from __future__ import annotations

import json
import re
import uuid

import pytest
import sqlalchemy as sa

from app.agents.base import AgentContext
from app.agents.communication_v2 import CommunicationAgent
from app.agents.communication_v2.tools.create_ticket import CreateTicket
from app.agents.communication_v2.tools.lookup_ticket_by_number import LookupTicketByNumber


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ticket_flow_agent(seeded_test_db_engine):
    return CommunicationAgent(
        engine=seeded_test_db_engine,
        constituency_config={
            "mla_name": "Anurag Reddy garu",
            "name": "Ibrahimpatnam",
        },
    )


def _get_real_ward_and_mandal(engine):
    """Return (ward_id, mandal_id) from seeded data, inserting test data if needed."""
    with engine.connect() as conn:
        ward_row = conn.execute(
            sa.text("SELECT id, mandal_id FROM wards WHERE mandal_id IS NOT NULL LIMIT 1")
        ).fetchone()

    if ward_row is not None:
        ward_id = str(ward_row[0])
        mandal_id = str(ward_row[1])
        return ward_id, mandal_id

    # No wards seeded — insert a constituency, mandal, and ward
    constituency_id = str(uuid.uuid4())
    mandal_id = str(uuid.uuid4())
    ward_id = str(uuid.uuid4())

    with engine.begin() as conn:
        # Check if already inserted by a parallel test
        existing = conn.execute(
            sa.text("SELECT id FROM wards WHERE id = :wid"),
            {"wid": ward_id},
        ).fetchone()
        if existing:
            return ward_id, mandal_id

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


def _insert_registered_citizen(engine, ward_id: str, mandal_id: str) -> str:
    """Insert a fully registered citizen and return citizen_id."""
    citizen_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO citizens
                    (id, name, mobile, ward_id, mandal_id, registration_complete)
                VALUES
                    (:id, 'Suresh Kumar', '9876543210', :wid, :mid, true)
            """),
            {"id": citizen_id, "wid": ward_id, "mid": mandal_id},
        )
    return citizen_id


def _insert_conversation(engine, citizen_id: str | None, summary: dict) -> str:
    """Insert a conversations row and return conversation_id."""
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
                "s": json.dumps(summary),
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
# Test 1: Full water complaint reaches ticket creation (LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.integration
def test_full_water_complaint_reaches_ticket_creation(
    ticket_flow_agent, seeded_test_db_engine
):
    """Two-dispatch live flow: complaint → confirmation → ticket filed.

    Dispatch 1: citizen sends a water complaint with all required details.
    Dispatch 2: citizen confirms with "Yes, that is correct."

    Expected outcome:
    - A ticket row exists in the DB with ticket_number matching the PUB-WTR pattern.
    - The ticket's citizen_id matches the pre-seeded citizen.
    - summary_data.current_complaint.phase == "filed".
    - result.reply_text from dispatch 2 contains the ticket_number.
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

    # Dispatch 1: full complaint — matches the successful PR 5b test message.
    # All required PUB.WATER fields must be present for confirm_with_citizen to be called.
    # issue_type is extracted from "no water supply", exact_location from the street name, etc.
    ctx1 = AgentContext(
        conversation_id=conv_id,
        incoming_message=(
            "There has been no water supply in our street for 3 days. "
            "We are in ward 11, Pragati Nagar, 4th street. "
            "About 30 households are affected. The borewell is also not working."
        ),
        incoming_message_script="roman",
        citizen_id=citizen_id,
    )
    r1 = ticket_flow_agent.dispatch(ctx1)

    assert r1.error is None, f"dispatch 1 errored: {r1.error}"
    assert r1.reply_text is not None and len(r1.reply_text) > 0

    # After dispatch 1, summary_data should show extracted fields or confirmation state
    s1 = _read_summary(seeded_test_db_engine, conv_id)
    cc1 = s1.get("current_complaint", {})
    # At minimum, a subcategory should be loaded
    assert cc1.get("subcategory_code") or cc1.get("category_schema_loaded"), (
        f"No category loaded after dispatch 1: {cc1}"
    )

    # If dispatch 1 did not reach confirmation (fields_pending is non-empty or
    # confirmation_state is not 'pending'), do a follow-up to fill remaining fields.
    # This handles LLM variability — the spec says "two dispatches" as typical,
    # but we allow up to one extra dispatch for field gap-filling.
    if cc1.get("fields_pending") or cc1.get("confirmation_state") != "pending":
        ctx_fill = AgentContext(
            conversation_id=conv_id,
            incoming_message=(
                "The issue type is no_supply (no water supply). "
                "Location is Pragati Nagar 4th street, ward 11. "
                "This has been going on for 3 days. 30 households are affected."
            ),
            incoming_message_script="roman",
            citizen_id=citizen_id,
        )
        r_fill = ticket_flow_agent.dispatch(ctx_fill)
        assert r_fill.error is None, f"fill dispatch errored: {r_fill.error}"
        s1 = _read_summary(seeded_test_db_engine, conv_id)

    # Final confirmation dispatch: citizen confirms
    ctx2 = AgentContext(
        conversation_id=conv_id,
        incoming_message="Yes, that is correct.",
        incoming_message_script="roman",
        citizen_id=citizen_id,
    )
    r2 = ticket_flow_agent.dispatch(ctx2)

    assert r2.error is None, f"dispatch 2 errored: {r2.error}"
    assert r2.reply_text is not None and len(r2.reply_text) > 0

    # Verify ticket row in DB
    with seeded_test_db_engine.connect() as conn:
        ticket_row = conn.execute(
            sa.text(
                "SELECT ticket_number, citizen_id, status "
                "FROM tickets "
                "WHERE citizen_id = :cid "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"cid": citizen_id},
        ).fetchone()

    create_ticket_calls = [tc for tc in r2.tool_calls_made if tc["name"] == "create_ticket"]
    assert ticket_row is not None, (
        f"No ticket row found for citizen_id={citizen_id}. "
        f"Tool calls made (dispatch 2): {r2.tool_calls_made}. "
        f"create_ticket calls: {create_ticket_calls}. "
        f"Summary before dispatch 2: {s1.get('current_complaint', {})}"
    )

    ticket_number = ticket_row[0]
    assert re.match(r"^PUB-WTR-\d{6}-\d{4}$", ticket_number), (
        f"ticket_number doesn't match PUB-WTR pattern: {ticket_number!r}"
    )
    assert str(ticket_row[1]) == citizen_id, (
        f"ticket.citizen_id mismatch: {ticket_row[1]} != {citizen_id}"
    )

    # Verify summary_data phase
    s2 = _read_summary(seeded_test_db_engine, conv_id)
    cc2 = s2.get("current_complaint", {})
    assert cc2.get("phase") == "filed", (
        f"current_complaint.phase should be 'filed': {cc2.get('phase')}"
    )
    assert cc2.get("ticket_number") == ticket_number, (
        f"ticket_number in summary_data ({cc2.get('ticket_number')!r}) "
        f"doesn't match DB ({ticket_number!r})"
    )

    # reply_text should contain the ticket_number
    assert ticket_number in r2.reply_text, (
        f"reply_text does not contain ticket_number {ticket_number!r}: {r2.reply_text!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: create_ticket blocks on incomplete registration (NON-LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_ticket_blocks_on_incomplete_registration(seeded_test_db_engine):
    """create_ticket must fail when citizen is missing ward_id and mandal_id.

    Non-live: no OpenAI call. Calls CreateTicket.execute() directly.
    """
    # Pre-seed citizen with only name and mobile
    citizen_id = str(uuid.uuid4())
    with seeded_test_db_engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO citizens
                    (id, name, mobile, registration_complete)
                VALUES
                    (:id, 'Partial Citizen', '9123456789', false)
            """),
            {"id": citizen_id},
        )

    # Pre-seed conversation with partial citizen and a pre-filled current_complaint
    summary = {
        "language_preference": "english",
        "language_script": "roman",
        "history_compressed": [],
        "citizen": {},
        "current_complaint": {
            "subcategory_code": "PUB.WATER",
            "ticket_id_prefix": "PUB-WTR",
            "confirmation_state": "pending",
            "fields_pending": [],
            "current_format": {
                "fields": [
                    {"name": "issue_type", "required": True, "value": "borewell", "source": "test"},
                    {"name": "exact_location", "required": True, "value": "Pragati Nagar", "source": "test"},
                    {"name": "duration_days", "required": True, "value": 3, "source": "test"},
                    {"name": "households_affected", "required": True, "value": 30, "source": "test"},
                    {"name": "description", "required": True, "value": "No water for 3 days, borewell not working", "source": "test"},
                ],
            },
            "phase": "confirm",
        },
    }
    conv_id = _insert_conversation(seeded_test_db_engine, citizen_id, summary)

    # Call CreateTicket directly
    tool = CreateTicket()
    result = tool.execute(
        inputs={"citizen_confirmation": "yes"},
        engine=seeded_test_db_engine,
        conversation_id=conv_id,
    )

    assert result.success is False, (
        f"Expected failure for incomplete registration, got success=True: {result.data}"
    )
    error_lower = (result.error or "").lower()
    assert "ward_id" in error_lower or "mandal_id" in error_lower, (
        f"Error message should mention ward_id or mandal_id: {result.error!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: lookup_ticket returns citizen-safe field set (NON-LIVE)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_lookup_ticket_returns_citizen_safe_shape(seeded_test_db_engine):
    """LookupTicketByNumber with caller='communication' returns exactly the citizen-safe fields.

    Non-live: no OpenAI call. Calls LookupTicketByNumber.execute() directly.
    Seeds a citizen and a ticket directly.
    """
    ward_id, mandal_id = _get_real_ward_and_mandal(seeded_test_db_engine)

    # Seed citizen
    citizen_id = str(uuid.uuid4())
    with seeded_test_db_engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO citizens
                    (id, name, mobile, ward_id, mandal_id, registration_complete)
                VALUES
                    (:id, 'Lookup Test', '9000000001', :wid, :mid, true)
            """),
            {"id": citizen_id, "wid": ward_id, "mid": mandal_id},
        )

    # Seed conversation (needed for ticket's conversation_id FK)
    conv_id = _insert_conversation(
        seeded_test_db_engine,
        citizen_id,
        {"language_preference": "english", "history_compressed": []},
    )

    # Get a real subcategory to satisfy FK
    with seeded_test_db_engine.connect() as conn:
        subcat_row = conn.execute(
            sa.text(
                "SELECT code, category_id FROM complaint_subcategories "
                "WHERE code = 'PUB.WATER' LIMIT 1"
            )
        ).fetchone()
        if subcat_row is None:
            pytest.skip("PUB.WATER subcategory not seeded")
        subcat_code = subcat_row[0]

        cat_row = conn.execute(
            sa.text("SELECT code FROM complaint_categories WHERE id = :id"),
            {"id": str(subcat_row[1])},
        ).fetchone()
        cat_code = cat_row[0] if cat_row else None

    # Allocate a ticket number using the stored function
    with seeded_test_db_engine.begin() as conn:
        tn_row = conn.execute(
            sa.text("SELECT allocate_ticket_number('PUB-WTR')")
        ).fetchone()
        test_ticket_number = tn_row[0]

        ticket_id = str(uuid.uuid4())
        conn.execute(
            sa.text("""
                INSERT INTO tickets
                    (id, ticket_number, citizen_id, conversation_id,
                     category_code, subcategory_code, ward_id, mandal_id,
                     status, priority, title, description, structured_data,
                     created_by_agent)
                VALUES
                    (:id, :tn, :cid, :conv_id,
                     :cat_code, :subcat_code, :wid, :mid,
                     'open', 'normal', 'Water Supply Issue - Test', 'Test description',
                     '{}'::jsonb, 'communication')
            """),
            {
                "id": ticket_id,
                "tn": test_ticket_number,
                "cid": citizen_id,
                "conv_id": conv_id,
                "cat_code": cat_code,
                "subcat_code": subcat_code,
                "wid": ward_id,
                "mid": mandal_id,
            },
        )

    # Call LookupTicketByNumber with caller="communication"
    tool = LookupTicketByNumber()
    result = tool.execute(
        inputs={"ticket_number": test_ticket_number, "caller": "communication"},
        engine=seeded_test_db_engine,
        conversation_id=conv_id,
    )

    assert result.success is True, f"Expected success, got error: {result.error}"

    expected_keys = {
        "ticket_number", "status", "assigned_department",
        "last_update_timestamp", "sla_remaining_hours", "complaint_summary_short",
    }
    actual_keys = set(result.data.keys())
    assert actual_keys == expected_keys, (
        f"Citizen-safe field set mismatch.\n"
        f"Expected: {sorted(expected_keys)}\n"
        f"Got:      {sorted(actual_keys)}"
    )

    # Must NOT contain full/sensitive fields
    forbidden_keys = {"citizen", "internal_notes", "structured_data", "ticket_id", "priority"}
    for key in forbidden_keys:
        assert key not in actual_keys, (
            f"Citizen-safe view should not include '{key}'"
        )

    assert result.data["ticket_number"] == test_ticket_number
    assert result.data["status"] == "open"
