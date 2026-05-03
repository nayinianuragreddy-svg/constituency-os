"""create_ticket: file a ticket after the citizen has confirmed their complaint.

Per Doc C v2.1 §5.6 and §7.4.

Preconditions (checked in order):
1. conversation must have a citizen_id set
2. citizens.registration_complete must be True
3. summary_data.current_complaint.confirmation_state must be "pending"
4. summary_data.current_complaint.fields_pending must be empty list
5. summary_data.current_complaint.subcategory_code must be set
6. summary_data.current_complaint.ticket_id_prefix must be set

Schema adaptations vs spec (from migration 0001):
- tickets table has: id, ticket_number, citizen_id, conversation_id, category_code,
  subcategory_code, ward_id, mandal_id, status, priority, title, description,
  structured_data, sla_due_at, created_by_agent, assigned_officer_id, resolved_at,
  resolution_notes, lat, lng, deleted_at, created_at, updated_at
- No 'created_via' column exists; we use 'created_by_agent' instead.
- ticket_assignments table does NOT exist; no FK constraint to worry about.
- human_review_queue ticket_id FK is optional (no NOT NULL on that column).
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult


class CreateTicket(Tool):
    name = "create_ticket"
    description = (
        "File a ticket after the citizen has confirmed their complaint details via 'yes'/'correct'/'avunu'/'haan'. "
        "Requires registration_complete=true (name, mobile, ward, mandal all collected). "
        "If it returns an error about missing identity, collect the missing fields via save_citizen_field and try again. "
        "Pass the citizen's exact confirmation word as citizen_confirmation."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "citizen_confirmation": {
                "type": "string",
                "enum": ["yes", "confirmed", "correct", "ok", "haan", "avunu"],
                "description": "The citizen's confirmation utterance.",
            },
        },
        "required": ["citizen_confirmation"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        citizen_confirmation = inputs.get("citizen_confirmation")

        with engine.begin() as conn:
            # Read conversation
            conv_row = conn.execute(
                sa.text(
                    "SELECT citizen_id, summary_data FROM conversations WHERE id = :cid FOR UPDATE"
                ),
                {"cid": conversation_id},
            ).fetchone()

            if conv_row is None:
                return ToolResult(success=False, data={}, error="conversation not found")

            citizen_id = conv_row[0]
            summary = conv_row[1] or {}
            if isinstance(summary, str):
                summary = json.loads(summary)
            elif not isinstance(summary, dict):
                summary = {}

            # Precondition 1: conversation must have a citizen_id
            if citizen_id is None:
                return ToolResult(
                    success=False,
                    data={},
                    error="citizen_id is not set on this conversation; collect citizen identity first",
                )

            citizen_id = str(citizen_id)

            # Precondition 2: citizens.registration_complete must be True
            cit_row = conn.execute(
                sa.text(
                    "SELECT name, mobile, ward_id, mandal_id, registration_complete "
                    "FROM citizens WHERE id = :cid"
                ),
                {"cid": citizen_id},
            ).fetchone()

            if cit_row is None:
                return ToolResult(success=False, data={}, error="citizen row not found")

            cit_name, cit_mobile, cit_ward_id, cit_mandal_id, reg_complete = cit_row

            if not reg_complete:
                missing = []
                if not cit_name:
                    missing.append("name")
                if not cit_mobile:
                    missing.append("mobile")
                if not cit_ward_id:
                    missing.append("ward_id")
                if not cit_mandal_id:
                    missing.append("mandal_id")
                return ToolResult(
                    success=False,
                    data={},
                    error=(
                        f"citizen registration is not complete; missing fields: "
                        + ", ".join(missing)
                    ),
                )

            current_complaint = summary.get("current_complaint") or {}

            # Precondition 3: confirmation_state must be "pending"
            confirmation_state = current_complaint.get("confirmation_state")
            if confirmation_state != "pending":
                return ToolResult(
                    success=False,
                    data={},
                    error=(
                        f"confirmation_state must be 'pending' before filing a ticket; "
                        f"current state: {confirmation_state!r}. "
                        "Call confirm_with_citizen first."
                    ),
                )

            # Precondition 4: fields_pending must be empty
            fields_pending = current_complaint.get("fields_pending") or []
            if fields_pending:
                return ToolResult(
                    success=False,
                    data={},
                    error=(
                        f"cannot file ticket: {len(fields_pending)} required field(s) still pending: "
                        + ", ".join(fields_pending)
                    ),
                )

            # Precondition 5: subcategory_code must be set
            subcategory_code = current_complaint.get("subcategory_code")
            if not subcategory_code:
                return ToolResult(
                    success=False,
                    data={},
                    error="subcategory_code is not set in current_complaint",
                )

            # Precondition 6: ticket_id_prefix must be set
            ticket_id_prefix = current_complaint.get("ticket_id_prefix")
            if not ticket_id_prefix:
                return ToolResult(
                    success=False,
                    data={},
                    error="ticket_id_prefix is not set in current_complaint",
                )

            # Read the current_format fields and build structured_data
            current_format = current_complaint.get("current_format") or {}
            format_fields = current_format.get("fields") or []
            # Build structured_data: {field_name: value} for all collected fields
            structured_data = {}
            if isinstance(format_fields, list):
                for f in format_fields:
                    if isinstance(f, dict) and f.get("value") not in (None, ""):
                        structured_data[f.get("name", "")] = f["value"]
            elif isinstance(format_fields, dict):
                # Sometimes stored as dict keyed by field name
                structured_data = {k: v for k, v in format_fields.items() if v not in (None, "")}

            # Look up subcategory details
            subcat_row = conn.execute(
                sa.text(
                    "SELECT id, category_id, sla_hours, display_name_en "
                    "FROM complaint_subcategories WHERE code = :code"
                ),
                {"code": subcategory_code},
            ).fetchone()

            if subcat_row is None:
                return ToolResult(
                    success=False,
                    data={},
                    error=f"subcategory not found: {subcategory_code}",
                )

            subcat_id, category_id, sla_hours, display_name_en = subcat_row

            # Look up category_code from category_id
            cat_row = conn.execute(
                sa.text("SELECT code FROM complaint_categories WHERE id = :id"),
                {"id": str(category_id)},
            ).fetchone()
            category_code = cat_row[0] if cat_row else None

            # Determine priority from summary or default
            priority = current_complaint.get("default_priority", "normal")

            # Allocate ticket number using the stored function
            ticket_num_row = conn.execute(
                sa.text("SELECT allocate_ticket_number(:prefix)"),
                {"prefix": ticket_id_prefix},
            ).fetchone()

            if ticket_num_row is None:
                return ToolResult(
                    success=False,
                    data={},
                    error="allocate_ticket_number returned no result",
                )
            ticket_number = ticket_num_row[0]

            # Build title from structured_data or display name
            location_val = structured_data.get("exact_location") or structured_data.get("location") or ""
            title = display_name_en
            if location_val:
                title = f"{display_name_en} - {location_val}"
            if len(title) > 200:
                title = title[:197] + "..."

            # Build description from structured_data
            description_val = structured_data.get("description") or ""

            # Compute sla_due_at value
            sla_due_at_value = None
            if sla_hours:
                sla_row = conn.execute(
                    sa.text(f"SELECT now() + INTERVAL '{int(sla_hours)} hours'")
                ).fetchone()
                if sla_row:
                    sla_due_at_value = sla_row[0]

            # INSERT the ticket
            ticket_id = str(uuid.uuid4())

            conn.execute(
                sa.text("""
                    INSERT INTO tickets (
                        id, ticket_number, citizen_id, conversation_id,
                        category_code, subcategory_code, ward_id, mandal_id,
                        status, priority, title, description, structured_data,
                        sla_due_at, created_by_agent
                    ) VALUES (
                        :id, :ticket_number, :citizen_id, :conversation_id,
                        :category_code, :subcategory_code, :ward_id, :mandal_id,
                        'open', :priority, :title, :description, CAST(:structured_data AS jsonb),
                        :sla_due_at, 'communication'
                    )
                """),
                {
                    "id": ticket_id,
                    "ticket_number": ticket_number,
                    "citizen_id": citizen_id,
                    "conversation_id": conversation_id,
                    "category_code": category_code,
                    "subcategory_code": subcategory_code,
                    "ward_id": str(cit_ward_id) if cit_ward_id else None,
                    "mandal_id": str(cit_mandal_id) if cit_mandal_id else None,
                    "priority": priority,
                    "title": title,
                    "description": description_val or None,
                    "structured_data": json.dumps(structured_data),
                    "sla_due_at": sla_due_at_value,
                },
            )

            # Update summary_data
            current_complaint["phase"] = "filed"
            current_complaint["confirmation_state"] = "filed"  # prevents double-filing
            current_complaint["ticket_id"] = ticket_id
            current_complaint["ticket_number"] = ticket_number

            history_compressed = summary.get("history_compressed") or []
            history_compressed.append({
                "role": "agent",
                "text": f"Ticket {ticket_number} filed.",
            })
            summary["history_compressed"] = history_compressed
            summary["current_complaint"] = current_complaint

            conn.execute(
                sa.text(
                    "UPDATE conversations SET summary_data = :s WHERE id = :cid"
                ),
                {"s": json.dumps(summary, ensure_ascii=False), "cid": conversation_id},
            )

        return ToolResult(
            success=True,
            data={
                "ticket_number": ticket_number,
                "ticket_id": ticket_id,
                "subcategory_code": subcategory_code,
                "priority": priority,
            },
        )
