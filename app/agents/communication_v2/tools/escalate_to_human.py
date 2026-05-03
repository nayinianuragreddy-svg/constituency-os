"""escalate_to_human: write to human_review_queue and update conversation state.

Per Doc C v2.1 §5.8.

HIGH BAR required for escalation. Call ONLY when genuinely concerning:
  ESCALATE for: medical emergency, violence, accident, threat to life, child in danger;
                contradictory story/signs of fraud/impersonation/bypass requests/threats
                by the citizen; court matters or things MLA's office legally cannot do.
  DO NOT escalate for: citizen confused about ward (just ask), multi-turn gathering
                (normal), citizen asks to talk to human (acknowledge and continue unless
                red flag), stuck loops (rephrase).

Schema adaptations vs spec (from migration 0001):
  human_review_queue columns: id, conversation_id, citizen_id, ticket_id,
      triggered_by_agent, reason, suggested_priority, summary, status,
      assigned_to_user_id, resolved_at, resolution_notes, agent_action_id,
      created_at, updated_at

  conversations.session_state CHECK constraint allows:
      'active', 'idle', 'blocked', 'closed'
  'escalated' is NOT in the allowed values. We set session_state to 'blocked'
  as the closest available state after escalation (conversation is held for human review).
  We record the escalation phase in summary_data.current_complaint.phase = "escalated_to_human".
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult

_REASON_CATEGORIES = {"safety_emergency", "suspicious_activity", "out_of_scope", "other"}
_PRIORITY_VALUES = {"urgent", "normal"}


class EscalateToHuman(Tool):
    name = "escalate_to_human"
    description = (
        "Call ONLY when genuinely concerning. HIGH BAR required.\n"
        "ESCALATE for: medical emergency, violence, accident, threat to life, child in danger; "
        "contradictory story/signs of fraud/impersonation/bypass requests/threats by the citizen; "
        "court matters or things MLA's office legally cannot do.\n"
        "DO NOT escalate for: citizen confused about ward (just ask), multi-turn gathering details (normal), "
        "citizen asks to talk to human (acknowledge and continue unless red flag), stuck loops (rephrase).\n"
        "Use suggested_priority='urgent' only for safety emergencies. "
        "Be specific in reason_summary — reference what the citizen actually said."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "reason_category": {
                "type": "string",
                "enum": ["safety_emergency", "suspicious_activity", "out_of_scope", "other"],
                "description": "Category of the escalation reason.",
            },
            "reason_summary": {
                "type": "string",
                "minLength": 10,
                "maxLength": 500,
                "description": "Specific summary of why escalation is needed. Reference what the citizen said.",
            },
            "suggested_priority": {
                "type": "string",
                "enum": ["urgent", "normal"],
                "description": "Use 'urgent' only for safety emergencies.",
            },
        },
        "required": ["reason_category", "reason_summary", "suggested_priority"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        reason_category = inputs.get("reason_category", "")
        reason_summary = inputs.get("reason_summary", "")
        suggested_priority = inputs.get("suggested_priority", "normal")

        # Validate inputs
        if reason_category not in _REASON_CATEGORIES:
            return ToolResult(
                success=False,
                data={},
                error=f"reason_category must be one of {sorted(_REASON_CATEGORIES)}",
            )
        if suggested_priority not in _PRIORITY_VALUES:
            return ToolResult(
                success=False,
                data={},
                error=f"suggested_priority must be one of {sorted(_PRIORITY_VALUES)}",
            )
        if not reason_summary or len(reason_summary) < 10:
            return ToolResult(
                success=False,
                data={},
                error="reason_summary must be at least 10 characters",
            )
        if len(reason_summary) > 500:
            return ToolResult(
                success=False,
                data={},
                error="reason_summary must be at most 500 characters",
            )

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

            citizen_id_str = str(citizen_id) if citizen_id else None

            # Get ticket_id from current_complaint if present
            current_complaint = summary.get("current_complaint") or {}
            ticket_id = current_complaint.get("ticket_id")
            ticket_id_str = str(ticket_id) if ticket_id else None

            # INSERT into human_review_queue
            human_review_id = str(uuid.uuid4())
            conn.execute(
                sa.text("""
                    INSERT INTO human_review_queue (
                        id, conversation_id, citizen_id, ticket_id,
                        triggered_by_agent, reason, suggested_priority,
                        summary, status
                    ) VALUES (
                        :id, :conversation_id, :citizen_id, :ticket_id,
                        'communication', :reason, :suggested_priority,
                        :summary, 'pending'
                    )
                """),
                {
                    "id": human_review_id,
                    "conversation_id": conversation_id,
                    "citizen_id": citizen_id_str,
                    "ticket_id": ticket_id_str,
                    "reason": reason_category,
                    "suggested_priority": suggested_priority,
                    "summary": reason_summary,
                },
            )

            # Update summary_data
            current_complaint["phase"] = "escalated_to_human"
            history_compressed = summary.get("history_compressed") or []
            history_compressed.append({
                "role": "agent",
                "text": reason_summary,
            })
            summary["history_compressed"] = history_compressed
            summary["current_complaint"] = current_complaint

            # Set session_state to 'blocked' (closest valid state; 'escalated' not in CHECK constraint)
            conn.execute(
                sa.text(
                    "UPDATE conversations "
                    "SET summary_data = :s, session_state = 'blocked' "
                    "WHERE id = :cid"
                ),
                {"s": json.dumps(summary, ensure_ascii=False), "cid": conversation_id},
            )

        return ToolResult(
            success=True,
            data={
                "human_review_id": human_review_id,
                "reason_category": reason_category,
                "suggested_priority": suggested_priority,
            },
        )
