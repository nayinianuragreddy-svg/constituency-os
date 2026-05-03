"""load_category_schema: fetch a subcategory's required_fields and metadata.

Per Doc C v2.1 §5.2.

Returns the subcategory's full record so the agent can render the schema in the
next prompt and start collecting fields.

Columns read (migration 0001 + 0005):
  code, display_name_en, ticket_id_prefix, default_priority, sla_hours, required_fields

PR 5b addition: after loading, the tool writes category_schema_loaded=True and the
subcategory_code to conversations.summary_data.current_complaint so the multi-hop
dispatch loop can render the schema in subsequent prompts.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult


class LoadCategorySchema(Tool):
    name = "load_category_schema"
    description = (
        "Load the required_fields and metadata for a complaint subcategory. "
        "Use this once the citizen's complaint has been classified into one of the 14 subcategories."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "subcategory_code": {
                "type": "string",
                "description": (
                    "One of: PUB.WATER, PUB.ELEC, PUB.SANI, PUB.RNB, PUB.OTH, "
                    "PRV.POL, PRV.REV, PRV.WEL, PRV.MED, PRV.EDU, PRV.OTH, "
                    "APT.MEET, APT.EVT, APT.FLC."
                ),
            },
        },
        "required": ["subcategory_code"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        code = inputs.get("subcategory_code")
        if not code:
            return ToolResult(success=False, data={}, error="subcategory_code is required")

        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    """
                    SELECT code, display_name_en, ticket_id_prefix,
                           default_priority, sla_hours, required_fields
                    FROM complaint_subcategories
                    WHERE code = :code AND is_active = true
                    """
                ),
                {"code": code},
            ).fetchone()

        if row is None:
            return ToolResult(success=False, data={}, error=f"subcategory not found: {code}")

        category_code = code.split(".")[0] if "." in code else code

        # Persist the loaded state so subsequent hops see category_schema_loaded=True
        with engine.begin() as conn:
            conv_row = conn.execute(
                sa.text(
                    "SELECT summary_data FROM conversations WHERE id = :cid FOR UPDATE"
                ),
                {"cid": conversation_id},
            ).fetchone()

            if conv_row is not None:
                summary = conv_row[0] or {}
                if isinstance(summary, str):
                    summary = json.loads(summary)
                elif not isinstance(summary, dict):
                    summary = {}

                current_complaint = summary.get("current_complaint") or {}
                current_complaint.update({
                    "phase": "collect",
                    "category_code": category_code,
                    "subcategory_code": code,
                    "category_schema_loaded": True,
                    "ticket_id_prefix": row[2] or "",
                })
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
                "subcategory_code": row[0],
                "display_name_en": row[1],
                "ticket_id_prefix": row[2],
                "default_priority": row[3],
                "sla_hours": row[4],
                "required_fields": row[5],
            },
        )
