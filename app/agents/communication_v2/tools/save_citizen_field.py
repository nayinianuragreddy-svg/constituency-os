"""save_citizen_field: persist a citizen attribute to the citizens table.

Per Doc C v2.1 §5.1.

Behavior:
- If the conversation has a citizen_id, UPDATE the existing citizens row.
- If not, INSERT a new citizens row, set the conversation's citizen_id to the new row's id.
- After the write, recompute registration_complete (true iff name, mobile, ward_id, mandal_id all present).

Allowed field names (matching actual citizens table columns from migration 0001):
  name, mobile, ward_id, mandal_id, voter_id, dob, village,
  pincode, gender, preferred_language, location_lat, location_lng, ward_number.

Note: the citizens table has no 'address' column; 'village' is the free-text
location field. 'dob' is a DATE column; pass ISO string YYYY-MM-DD.
'location_lat' maps to the 'lat' column; 'location_lng' maps to the 'lng' column.

Validation:
- name: non-empty string
- mobile: 10-digit Indian mobile (regex ^[6-9]\\d{9}$ after stripping spaces/hyphens/+91)
- ward_id, mandal_id: valid UUID strings (FK enforced by DB)
- voter_id: optional, free-form string
- dob: ISO date YYYY-MM-DD
- village: free-form string
- pincode: 6-digit Indian PIN (regex ^[1-9]\\d{5}$)
- gender: one of {"male", "female", "other", "prefer_not_to_say"}
- preferred_language: one of {"english", "telugu", "hindi"}
  GROUNDING REQUIRED: preferred_language saves are rejected unless the citizen's
  most recent inbound message contains an explicit language preference statement
  or is written in the script of the requested language. This guards against the
  LLM hallucinating a language preference from an unrelated confirmation message.
- location_lat: float between -90 and 90 (stored in citizens.lat)
- location_lng: float between -180 and 180 (stored in citizens.lng)
- ward_number: integer between 1 and 30 (stored in citizens.ward_number)
"""

from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult, ToolError


ALLOWED_FIELDS = {
    "name", "mobile", "ward_id", "mandal_id", "voter_id", "dob", "village",
    "pincode", "gender", "preferred_language", "location_lat", "location_lng", "ward_number",
}
MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")
PINCODE_PATTERN = re.compile(r"^[1-9]\d{5}$")
GENDER_VALUES = {"male", "female", "other", "prefer_not_to_say"}
LANGUAGE_VALUES = {"english", "telugu", "hindi"}

# Map logical field names to actual DB column names (where they differ)
_FIELD_TO_COLUMN = {
    "location_lat": "lat",
    "location_lng": "lng",
}

# Telugu Unicode block: U+0C00–U+0C7F
_TELUGU_PATTERN = re.compile(r"[ఀ-౿]")
# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI_PATTERN = re.compile(r"[ऀ-ॿ]")

# Explicit language-preference phrases (case-insensitive)
_TELUGU_EXPLICIT = re.compile(
    r"in telugu|telugu lo|telugu lo cheppu|నాకు తెలుగు|తెలుగులో",
    re.IGNORECASE,
)
_HINDI_EXPLICIT = re.compile(
    r"in hindi|hindi me\b|hindi mein|मुझे हिंदी|हिंदी में",
    re.IGNORECASE,
)
_ENGLISH_EXPLICIT = re.compile(
    r"in english|english me\b|english lo",
    re.IGNORECASE,
)


def _is_grounded_for_language(value: str, message: str) -> bool:
    """Return True if the message grounds the preferred_language save.

    Two tiers:
    a) Script match — the message is written in the script of the requested language.
    b) Explicit statement — the message contains an explicit language preference phrase.
    """
    if value == "telugu":
        if _TELUGU_PATTERN.search(message):
            return True
        if _TELUGU_EXPLICIT.search(message):
            return True
    elif value == "hindi":
        if _DEVANAGARI_PATTERN.search(message):
            return True
        if _HINDI_EXPLICIT.search(message):
            return True
    elif value == "english":
        # English is grounded when the message has no Telugu or Devanagari chars
        if not _TELUGU_PATTERN.search(message) and not _DEVANAGARI_PATTERN.search(message):
            return True
        if _ENGLISH_EXPLICIT.search(message):
            return True
    return False


class SaveCitizenField(Tool):
    name = "save_citizen_field"
    description = (
        "Save a single field on the citizen's record. "
        "Use this when the citizen has provided their name, mobile, ward, mandal, "
        "voter ID, date of birth, village/address, pincode, gender, preferred language, "
        "GPS coordinates, or ward number."
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
                    "For dob, pass ISO date YYYY-MM-DD. "
                    "For location_lat/location_lng, pass a decimal number as string. "
                    "For ward_number, pass an integer as string."
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
        elif field_name == "pincode":
            if not PINCODE_PATTERN.match(value):
                return ToolResult(
                    success=False,
                    data={},
                    error=f"pincode must be a 6-digit Indian PIN (^[1-9]\\d{{5}}$): {value!r}",
                )
        elif field_name == "gender":
            if value not in GENDER_VALUES:
                return ToolResult(
                    success=False,
                    data={},
                    error=f"gender must be one of {sorted(GENDER_VALUES)}: {value!r}",
                )
        elif field_name == "preferred_language":
            if value not in LANGUAGE_VALUES:
                return ToolResult(
                    success=False,
                    data={},
                    error=f"preferred_language must be one of {sorted(LANGUAGE_VALUES)}: {value!r}",
                )
            # Grounding check: read the most recent inbound message for this conversation
            try:
                with engine.connect() as conn:
                    row = conn.execute(
                        sa.text(
                            "SELECT content FROM messages "
                            "WHERE conversation_id = :cid AND direction = 'inbound' "
                            "ORDER BY created_at DESC LIMIT 1"
                        ),
                        {"cid": conversation_id},
                    ).fetchone()
            except Exception as exc:
                return ToolResult(
                    success=False, data={},
                    error=f"grounding check failed: {exc!r}",
                )
            last_message = row[0] if row else ""
            if not _is_grounded_for_language(value, last_message or ""):
                return ToolResult(
                    success=False,
                    data={},
                    error="preferred_language not grounded in citizen's most recent message",
                )
        elif field_name == "location_lat":
            try:
                lat = float(value)
            except (ValueError, TypeError):
                return ToolResult(
                    success=False, data={}, error=f"location_lat must be a float: {value!r}"
                )
            if not (-90 <= lat <= 90):
                return ToolResult(
                    success=False, data={}, error=f"location_lat must be between -90 and 90: {value!r}"
                )
        elif field_name == "location_lng":
            try:
                lng = float(value)
            except (ValueError, TypeError):
                return ToolResult(
                    success=False, data={}, error=f"location_lng must be a float: {value!r}"
                )
            if not (-180 <= lng <= 180):
                return ToolResult(
                    success=False, data={}, error=f"location_lng must be between -180 and 180: {value!r}"
                )
        elif field_name == "ward_number":
            try:
                wn = int(value)
            except (ValueError, TypeError):
                return ToolResult(
                    success=False, data={}, error=f"ward_number must be an integer: {value!r}"
                )
            if not (1 <= wn <= 30):
                return ToolResult(
                    success=False, data={}, error=f"ward_number must be between 1 and 30: {value!r}"
                )

        # Map logical field name to actual DB column name
        db_column = _FIELD_TO_COLUMN.get(field_name, field_name)

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
                        f"INSERT INTO citizens (id, {db_column}, registration_complete)"
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
                    sa.text(f"UPDATE citizens SET {db_column} = :value WHERE id = :id"),
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
