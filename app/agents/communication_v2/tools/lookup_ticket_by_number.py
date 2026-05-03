"""lookup_ticket_by_number: look up a ticket by its ticket number, with per-caller field filtering.

Per Doc C v2.1 §5.7.

Callers and their field sets:

"communication" (citizen-safe):
    ticket_number, status, assigned_department, last_update_timestamp,
    sla_remaining_hours, complaint_summary_short

"dashboard" or "master" (full):
    ticket_number, ticket_id, status, priority, subcategory_code,
    subcategory_display_en, citizen (dict with name/mobile/ward_id/mandal_id/voter_id),
    title, description, structured_data, internal_notes, created_at,
    last_update_timestamp, sla_hours, sla_remaining_hours, agent_actions_count

"department":
    ticket_number, ticket_id, status, priority, subcategory_code, title,
    description, structured_data, assigned_officer, deadline_at, internal_notes

NOTE: Only the "communication" caller is exercised in PR 5c integration tests.
Other callers are infrastructure for future agents.

Schema adaptations vs spec (from migration 0001):
- tickets table has no 'internal_notes' column; returned as null.
- tickets table has no 'assigned_officer' column (officer is via assigned_officer_id FK);
  for department caller we return officer name if assigned_officer_id is set, else null.
- tickets table has no 'deadline_at' column; 'sla_due_at' is the closest equivalent,
  returned as deadline_at for department caller.
- tickets table has no 'last_update_timestamp' column; 'updated_at' is used instead.
- tickets table has no 'complaint_summary_short' column; built from title + subcategory.
- 'assigned_department' is derived from subcategory's default_routing_queue.
- 'sla_remaining_hours' is computed from sla_due_at - now() if sla_due_at is set.
"""

from __future__ import annotations

import json
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult

_ALLOWED_CALLERS = {"communication", "dashboard", "master", "department"}


class LookupTicketByNumber(Tool):
    name = "lookup_ticket_by_number"
    description = (
        "When the citizen mentions an existing ticket number (e.g., 'what happened to PUB-WTR-280426-0042?'), "
        "call this with caller='communication' to fetch its status. "
        "Returns a citizen-safe view: ticket_number, status, assigned_department, "
        "last_update_timestamp, sla_remaining_hours."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ticket_number": {
                "type": "string",
                "pattern": r"^[A-Z]{3}-[A-Z]{3}-[0-9]{6}-[0-9]{4}$",
                "description": "The ticket number to look up.",
            },
            "caller": {
                "type": "string",
                "enum": ["communication", "dashboard", "master", "department"],
                "description": "Who is calling this tool. Determines the returned field set.",
            },
        },
        "required": ["ticket_number", "caller"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        ticket_number = inputs.get("ticket_number", "")
        caller = inputs.get("caller", "")

        if caller not in _ALLOWED_CALLERS:
            return ToolResult(
                success=False,
                data={},
                error=f"caller must be one of {sorted(_ALLOWED_CALLERS)}; got {caller!r}",
            )

        with engine.connect() as conn:
            row = conn.execute(
                sa.text("""
                    SELECT
                        t.id,
                        t.ticket_number,
                        t.citizen_id,
                        t.status,
                        t.priority,
                        t.subcategory_code,
                        t.title,
                        t.description,
                        t.structured_data,
                        t.sla_due_at,
                        t.updated_at,
                        t.created_at,
                        t.assigned_officer_id,
                        cs.display_name_en  AS subcategory_display_en,
                        cs.sla_hours        AS sla_hours,
                        cc.default_routing_queue AS default_routing_queue,
                        EXTRACT(EPOCH FROM (t.sla_due_at - now())) / 3600 AS sla_remaining_hours
                    FROM tickets t
                    LEFT JOIN complaint_subcategories cs ON cs.code = t.subcategory_code
                    LEFT JOIN complaint_categories cc ON cc.id = cs.category_id
                    WHERE t.ticket_number = :tn
                      AND t.deleted_at IS NULL
                """),
                {"tn": ticket_number},
            ).fetchone()

            if row is None:
                return ToolResult(
                    success=False,
                    data={},
                    error=f"ticket not found: {ticket_number}",
                )

            (
                ticket_id, t_number, citizen_id, status, priority, subcategory_code,
                title, description, structured_data, sla_due_at, updated_at, created_at,
                assigned_officer_id, subcategory_display_en, sla_hours, default_routing_queue,
                sla_remaining_hours,
            ) = row

            # Normalize structured_data
            if isinstance(structured_data, str):
                try:
                    structured_data = json.loads(structured_data)
                except Exception:
                    structured_data = {}
            if structured_data is None:
                structured_data = {}

            # sla_remaining_hours: round to 1 decimal if present
            sla_remaining_hours_val: Optional[float] = None
            if sla_remaining_hours is not None:
                sla_remaining_hours_val = round(float(sla_remaining_hours), 1)

            # assigned_department: use default_routing_queue from the joined category
            # If the join on cc is broken (category_id stored as UUID not code), fall back
            # to deriving from subcategory_code prefix
            assigned_department = default_routing_queue
            if not assigned_department and subcategory_code:
                prefix = subcategory_code.split(".")[0].lower() if "." in subcategory_code else ""
                assigned_department = f"{prefix}_issues" if prefix else None

            # complaint_summary_short for citizen caller
            complaint_summary_short = title or subcategory_display_en or subcategory_code or ""

            if caller == "communication":
                result_data = {
                    "ticket_number": t_number,
                    "status": status,
                    "assigned_department": assigned_department,
                    "last_update_timestamp": updated_at.isoformat() if updated_at else None,
                    "sla_remaining_hours": sla_remaining_hours_val,
                    "complaint_summary_short": complaint_summary_short,
                }

            elif caller in ("dashboard", "master"):
                # Fetch citizen details
                citizen_data = {}
                if citizen_id:
                    cit_row = conn.execute(
                        sa.text(
                            "SELECT name, mobile, ward_id, mandal_id, voter_id "
                            "FROM citizens WHERE id = :cid"
                        ),
                        {"cid": str(citizen_id)},
                    ).fetchone()
                    if cit_row:
                        citizen_data = {
                            "name": cit_row[0],
                            "mobile": cit_row[1],
                            "ward_id": str(cit_row[2]) if cit_row[2] else None,
                            "mandal_id": str(cit_row[3]) if cit_row[3] else None,
                            "voter_id": cit_row[4],
                        }

                # agent_actions_count
                actions_count_row = conn.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM agent_actions WHERE ticket_id = :tid"
                    ),
                    {"tid": str(ticket_id)},
                ).fetchone()
                agent_actions_count = actions_count_row[0] if actions_count_row else 0

                result_data = {
                    "ticket_number": t_number,
                    "ticket_id": str(ticket_id),
                    "status": status,
                    "priority": priority,
                    "subcategory_code": subcategory_code,
                    "subcategory_display_en": subcategory_display_en,
                    "citizen": citizen_data,
                    "title": title,
                    "description": description,
                    "structured_data": structured_data,
                    "internal_notes": None,  # column does not exist in migration 0001
                    "created_at": created_at.isoformat() if created_at else None,
                    "last_update_timestamp": updated_at.isoformat() if updated_at else None,
                    "sla_hours": sla_hours,
                    "sla_remaining_hours": sla_remaining_hours_val,
                    "agent_actions_count": agent_actions_count,
                }

            else:  # department
                # assigned_officer: look up officer name if assigned_officer_id is set
                assigned_officer = None
                if assigned_officer_id:
                    off_row = conn.execute(
                        sa.text("SELECT name FROM officer_contacts WHERE id = :oid"),
                        {"oid": str(assigned_officer_id)},
                    ).fetchone()
                    if off_row:
                        assigned_officer = off_row[0]

                result_data = {
                    "ticket_number": t_number,
                    "ticket_id": str(ticket_id),
                    "status": status,
                    "priority": priority,
                    "subcategory_code": subcategory_code,
                    "title": title,
                    "description": description,
                    "structured_data": structured_data,
                    "assigned_officer": assigned_officer,
                    "deadline_at": sla_due_at.isoformat() if sla_due_at else None,  # sla_due_at used as deadline_at
                    "internal_notes": None,  # column does not exist in migration 0001
                }

        return ToolResult(success=True, data=result_data)
