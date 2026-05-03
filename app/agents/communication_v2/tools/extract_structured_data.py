"""extract_structured_data: validate and persist complaint field values.

Per Doc C v2.1 §5.4 and Doc B v2.1 §3.2.

The LLM extracts (field_name, value) pairs from the citizen's message. This tool:
1. Checks each value is grounded in the citizen's source_text (per field type).
2. Validates each accepted value against the schema's type and validation_hint.
3. Persists accepted values to conversations.summary_data.current_complaint.current_format.
4. Returns accepted fields, rejected fields, pending required fields, and
   a flag indicating whether all required fields have been collected.

Grounding rules per field type:
- enum, yes_no, media: skip grounding (canonical value / reference, not extracted text)
- integer, phone, date: digit-only normalized substring match against source_text
- string, free_text, name, village: case-insensitive normalized substring match
- voter_id: alphanumeric stripped, case-insensitive match
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult
from app.agents.runtime import StructuredDataValidator, StructuredDataValidatorError

logger = logging.getLogger(__name__)

# Types that skip grounding entirely
_NO_GROUND_TYPES = {"enum", "yes_no", "media"}

# Types where only digit characters are compared
_DIGIT_GROUND_TYPES = {"integer", "phone", "date"}

_NORMALIZE_STRIP = re.compile(r"[\s\-_,.\(\)]")


def _normalize(text: str) -> str:
    """Lowercase, NFC-normalize, strip punctuation/whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = _NORMALIZE_STRIP.sub("", text)
    return text


def _digits_only(text: str) -> str:
    return re.sub(r"\D", "", text)


def _is_grounded(value: str, source_text: str, field_type: str) -> bool:
    """Return True if value is sufficiently grounded in source_text for the given type."""
    if field_type in _NO_GROUND_TYPES:
        return True

    if field_type == "voter_id":
        # Alphanumeric stripped, case-insensitive
        norm_val = re.sub(r"[^a-z0-9]", "", value.lower())
        norm_src = re.sub(r"[^a-z0-9]", "", source_text.lower())
        return bool(norm_val) and norm_val in norm_src

    if field_type in _DIGIT_GROUND_TYPES:
        digits_val = _digits_only(value)
        digits_src = _digits_only(source_text)
        return bool(digits_val) and digits_val in digits_src

    # string, free_text, name, village, and any unknown types: normalized substring
    norm_val = _normalize(value)
    norm_src = _normalize(source_text)
    return bool(norm_val) and norm_val in norm_src


_validator = StructuredDataValidator()


class ExtractStructuredData(Tool):
    name = "extract_structured_data"
    description = (
        "Validate and persist complaint field values extracted from a citizen message. "
        "Call this after load_category_schema when the citizen has provided complaint details. "
        "Pass the citizen's exact message as source_text and the (field_name, value) pairs you identified."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "subcategory_code": {
                "type": "string",
                "description": "Must match the loaded schema's subcategory_code.",
            },
            "source_text": {
                "type": "string",
                "description": "The citizen's exact message from which values were extracted.",
            },
            "extracted_fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["field_name", "value"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["subcategory_code", "source_text", "extracted_fields"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        subcategory_code = inputs.get("subcategory_code", "")
        source_text = inputs.get("source_text", "")
        extracted_fields = inputs.get("extracted_fields") or []

        if not subcategory_code:
            return ToolResult(success=False, data={}, error="subcategory_code is required")
        if not source_text:
            return ToolResult(success=False, data={}, error="source_text is required")

        # Load the raw schema from DB
        schema_fields = self._load_schema_fields(engine, subcategory_code)
        if schema_fields is None:
            return ToolResult(
                success=False,
                data={},
                error=f"subcategory not found: {subcategory_code}",
            )

        # Read the conversation summary
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

            # Verify schema is loaded in state (either loaded this dispatch or prior)
            if not current_complaint.get("category_schema_loaded"):
                # Allow proceeding — the agent may have just loaded it in the same dispatch
                # but summary was read before the load_category_schema write. We re-check
                # by trusting that if we have schema_fields from DB, we can proceed.
                pass

            # Initialize current_format if not yet present
            current_format = current_complaint.get("current_format") or {}
            if not current_format.get("fields"):
                current_format = {
                    "fields": [
                        {
                            "name": f["name"],
                            "required": f.get("required", False),
                            "value": None,
                            "source": None,
                        }
                        for f in schema_fields
                    ]
                }

            # Build a lookup from field name to schema field def
            schema_by_name = {f["name"]: f for f in schema_fields}

            # Build a mutable lookup from field name to current_format entry
            fmt_by_name: dict[str, dict] = {}
            for entry in current_format["fields"]:
                fmt_by_name[entry["name"]] = entry

            accepted_fields: list[dict] = []
            rejected_fields: list[dict] = []

            for item in extracted_fields:
                field_name = item.get("field_name", "")
                value = item.get("value", "")

                if field_name not in schema_by_name:
                    rejected_fields.append({
                        "field_name": field_name,
                        "value": value,
                        "reason": f"field '{field_name}' not in schema for {subcategory_code}",
                    })
                    continue

                schema_field = schema_by_name[field_name]
                field_type = schema_field.get("type", "string")

                # Step 1: grounding check
                if not _is_grounded(value, source_text, field_type):
                    rejected_fields.append({
                        "field_name": field_name,
                        "value": value,
                        "reason": "value not grounded in source_text",
                    })
                    continue

                # Step 2: per-field validation using StructuredDataValidator
                # Build a minimal payload and schema for single-field validation
                single_payload = self._coerce_value(value, field_type)
                single_schema = {"fields": [schema_field]}
                try:
                    _validator.validate({field_name: single_payload}, single_schema)
                except StructuredDataValidatorError as exc:
                    rejected_fields.append({
                        "field_name": field_name,
                        "value": value,
                        "reason": str(exc),
                    })
                    continue

                # Accepted — write to current_format
                if field_name in fmt_by_name:
                    fmt_by_name[field_name]["value"] = single_payload
                    fmt_by_name[field_name]["source"] = source_text
                else:
                    fmt_by_name[field_name] = {
                        "name": field_name,
                        "required": schema_field.get("required", False),
                        "value": single_payload,
                        "source": source_text,
                    }

                accepted_fields.append({"field_name": field_name, "value": single_payload})

            # Rebuild current_format.fields preserving original order
            current_format["fields"] = list(fmt_by_name.values())

            # Recompute counts
            required_fields = [f for f in schema_fields if f.get("required", False)]
            fields_required_count = len(required_fields)
            fields_pending = [
                f["name"]
                for f in required_fields
                if fmt_by_name.get(f["name"], {}).get("value") in (None, "")
            ]
            fields_collected_count = fields_required_count - len(fields_pending)
            all_required_collected = len(fields_pending) == 0

            # Determine category_code from subcategory_code prefix (e.g. "PUB" from "PUB.WATER")
            category_code = subcategory_code.split(".")[0] if "." in subcategory_code else subcategory_code

            # Fetch ticket_id_prefix and display_name_en from DB
            ticket_id_prefix, display_name_en = self._load_meta(engine, subcategory_code)

            # Update current_complaint
            current_complaint.update({
                "phase": "collect",
                "category_code": category_code,
                "subcategory_code": subcategory_code,
                "category_schema_loaded": True,
                "ticket_id_prefix": ticket_id_prefix,
                "current_format": current_format,
                "fields_pending": fields_pending,
                "fields_collected_count": fields_collected_count,
                "fields_required_count": fields_required_count,
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
                "accepted_fields": accepted_fields,
                "rejected_fields": rejected_fields,
                "fields_pending": fields_pending,
                "all_required_collected": all_required_collected,
                "fields_collected_count": fields_collected_count,
                "fields_required_count": fields_required_count,
            },
        )

    def _load_schema_fields(
        self, engine: Engine, subcategory_code: str
    ) -> Optional[list]:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT required_fields FROM complaint_subcategories"
                    " WHERE code = :code AND is_active = true"
                ),
                {"code": subcategory_code},
            ).fetchone()
        if row is None:
            return None
        fields = row[0]
        if isinstance(fields, str):
            fields = json.loads(fields)
        return fields or []

    def _load_meta(self, engine: Engine, subcategory_code: str) -> tuple[str, str]:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT ticket_id_prefix, display_name_en"
                    " FROM complaint_subcategories WHERE code = :code"
                ),
                {"code": subcategory_code},
            ).fetchone()
        if row is None:
            return ("", "")
        return (row[0] or "", row[1] or "")

    @staticmethod
    def _coerce_value(value: str, field_type: str):
        """Coerce string value to the appropriate Python type for validation."""
        if field_type == "integer":
            try:
                return int(value)
            except (ValueError, TypeError):
                return value
        return value
