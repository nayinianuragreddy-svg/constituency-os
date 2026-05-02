"""save_citizen_field: persist a citizen attribute to the citizens table.

Per Doc C v2.1 §5.1.

Behavior:
- If the conversation has a citizen_id, UPDATE the existing citizens row.
- If not, INSERT a new citizens row, set the conversation's citizen_id to the new row's id.
- After the write, recompute registration_complete (true iff name, mobile, ward_id, mandal_id all present).

Allowed field names (matching actual citizens table columns from migration 0001):
  name, mobile, ward_id, mandal_id, voter_id, dob, village.

Note: the citizens table has no 'address' column; 'village' is the free-text
location field. 'dob' is a DATE column; pass ISO string YYYY-MM-DD.

Validation:
- name: non-empty string
- mobile: 10-digit Indian mobile (regex ^[6-9]\\d{9}$ after stripping spaces/hyphens/+91)
- ward_id, mandal_id: valid UUID strings (FK enforced by DB)
- voter_id: optional, free-form string
- dob: ISO date YYYY-MM-DD
- village: free-form string
"""

from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult, ToolError


ALLOWED_FIELDS = {"name", "mobile", "ward_id", "mandal_id", "voter_id", "dob", "village"}
MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")


class SaveCitizenField(Tool):
    name = "save_citizen_field"
    description = (
        "Save a single field on the citizen's record. "
        "Use this when the citizen has provided their name, mobile, ward, mandal, "
        "voter ID, date of birth, or village/address."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "field_name": {
                "type": "string",
                "enum": sorted(ALLOWED_FIELDS),
                "description": "The field to save.",
            },
            "value": {
                "type": "string",
                "description": (
                    "The value to save. "
                    "For ward_id and mandal_id, pass the UUID as a string. "
                    "For dob, pass ISO date YYYY-MM-DD."
                ),
            },
        },
        "required": ["field_name", "value"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        field_name = inputs.get("field_name")
        value = inputs.get("value")

        if field_name not in ALLOWED_FIELDS:
            return ToolResult(success=False, data={}, error=f"unknown field: {field_name}")

        if not value or not isinstance(value, str):
            return ToolResult(
                success=False, data={}, error=f"value for {field_name} must be a non-empty string"
            )

        # Field-specific validation
        if field_name == "mobile":
            cleaned = value.replace(" ", "").replace("-", "").replace("+91", "")
            if not MOBILE_PATTERN.match(cleaned):
                return ToolResult(
                    success=False, data={}, error=f"invalid Indian mobile: {value!r}"
                )
            value = cleaned
        elif field_name in ("ward_id", "mandal_id"):
            try:
                uuid.UUID(value)
            except (ValueError, TypeError):
                return ToolResult(
                    success=False, data={}, error=f"{field_name} must be a valid UUID"
                )

        with engine.begin() as conn:
            row = conn.execute(
                sa.text("SELECT citizen_id FROM conversations WHERE id = :cid"),
                {"cid": conversation_id},
            ).fetchone()

            if row is None:
                return ToolResult(success=False, data={}, error="conversation not found")

            citizen_id = row[0]

            if citizen_id is None:
                # No citizen yet — create one
                citizen_id = str(uuid.uuid4())
                conn.execute(
                    sa.text(
                        f"INSERT INTO citizens (id, {field_name}, registration_complete)"
                        " VALUES (:id, :value, false)"
                    ),
                    {"id": citizen_id, "value": value},
                )
                conn.execute(
                    sa.text(
                        "UPDATE conversations SET citizen_id = :cid WHERE id = :conv_id"
                    ),
                    {"cid": citizen_id, "conv_id": conversation_id},
                )
            else:
                citizen_id = str(citizen_id)
                conn.execute(
                    sa.text(f"UPDATE citizens SET {field_name} = :value WHERE id = :id"),
                    {"value": value, "id": citizen_id},
                )

            # Recompute registration_complete
            conn.execute(
                sa.text(
                    """
                    UPDATE citizens
                    SET registration_complete = (
                        name IS NOT NULL
                        AND mobile IS NOT NULL
                        AND ward_id IS NOT NULL
                        AND mandal_id IS NOT NULL
                    )
                    WHERE id = :id
                    """
                ),
                {"id": citizen_id},
            )

        return ToolResult(
            success=True,
            data={"citizen_id": citizen_id, "field_saved": field_name, "value": value},
        )
