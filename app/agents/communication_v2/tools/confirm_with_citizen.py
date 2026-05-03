"""confirm_with_citizen: render a deterministic read-back for citizen confirmation.

Per Doc C v2.1 §5.5 and §7.3.

When all required complaint fields are collected, this tool generates a fixed-template
read-back showing every collected field's value. The citizen must confirm before a ticket
is created.

NOTE: PR 5b ships English-only. The language parameter is accepted and validated but only
English is rendered. Telugu and Hindi templates are added in PR 5d.

The read-back is NOT LLM-generated. This guarantees it is always complete and never
invents or omits fields (per Doc C §7.3).

If confirmation_reads exceeds 3, the tool returns an error indicating the agent should
escalate to a human. PR 5c will add escalate_to_human to handle this case.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult

MAX_CONFIRMATION_READS = 3


class ConfirmWithCitizen(Tool):
    name = "confirm_with_citizen"
    description = (
        "Render a deterministic confirmation read-back once all required complaint fields "
        "have been collected. Call this only after extract_structured_data reports "
        "all_required_collected=true. The returned readback_text must be sent to the citizen "
        "as the reply_text."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["english", "telugu", "hindi"],
                "description": "Language for the confirmation read-back. Only 'english' is rendered in PR 5b.",
            },
        },
        "required": ["language"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        language = inputs.get("language", "english")

        with engine.begin() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT summary_data FROM conversations WHERE id = :cid FOR UPDATE"
                ),
                {"cid": conversation_id},
            ).fetchone()

            if row is None:
                return ToolResult(success=False, data={}, error="conversation not found")

            summary = row[0] or {}
            if isinstance(summary, str):
                summary = json.loads(summary)
            elif not isinstance(summary, dict):
                summary = {}

            current_complaint = summary.get("current_complaint") or {}
            current_format = current_complaint.get("current_format") or {}
            fields = current_format.get("fields") or []

            if not fields:
                return ToolResult(
                    success=False,
                    data={},
                    error="current_format is missing or has no fields; call extract_structured_data first",
                )

            fields_pending = current_complaint.get("fields_pending") or []
            if fields_pending:
                return ToolResult(
                    success=False,
                    data={},
                    error=(
                        f"cannot confirm: {len(fields_pending)} required field(s) still pending: "
                        + ", ".join(fields_pending)
                    ),
                )

            # Guard against confirmation loop
            confirmation_reads = current_complaint.get("confirmation_reads", 0)
            if confirmation_reads >= MAX_CONFIRMATION_READS:
                return ToolResult(
                    success=False,
                    data={},
                    error=(
                        f"confirmation_reads limit ({MAX_CONFIRMATION_READS}) reached; "
                        "escalate to a human agent"
                    ),
                )

            # Fetch label_en values from the schema so the read-back is human-friendly
            subcategory_code = current_complaint.get("subcategory_code", "")
            label_map = self._load_labels(engine, subcategory_code)

            # Build read-back text (English only in PR 5b)
            lines: list[str] = ["I have noted your concern as follows:"]
            for field in fields:
                name = field.get("name", "")
                value = field.get("value")
                if value is None or value == "":
                    continue  # skip optional fields citizen didn't provide
                label = label_map.get(name) or name.replace("_", " ").title()
                lines.append(f"- {label}: {value}")

            lines.append(
                'Is this correct? If correct, please say "yes". '
                "If anything needs to change, please tell me what."
            )
            readback_text = "\n".join(lines)

            # Update state
            confirmation_reads += 1
            current_complaint["confirmation_state"] = "pending"
            current_complaint["confirmation_reads"] = confirmation_reads
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
                "readback_text": readback_text,
                "confirmation_state": "pending",
                "confirmation_reads": confirmation_reads,
            },
        )

    def _load_labels(self, engine: Engine, subcategory_code: str) -> dict[str, str]:
        """Fetch a {field_name: label_en} map from the schema."""
        if not subcategory_code:
            return {}
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT required_fields FROM complaint_subcategories"
                    " WHERE code = :code AND is_active = true"
                ),
                {"code": subcategory_code},
            ).fetchone()
        if row is None:
            return {}
        fields = row[0]
        if isinstance(fields, str):
            import json as _json
            fields = _json.loads(fields)
        if not isinstance(fields, list):
            return {}
        return {f["name"]: f.get("label_en", f["name"]) for f in fields if "name" in f}
