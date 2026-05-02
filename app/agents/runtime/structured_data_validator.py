"""StructuredDataValidator: cross-validation of LLM structured output against category schema.

Per Doc B v2.1 §2.2. Pure function: same inputs always produce same output (validated or
specific error raised).

The validator takes:
- payload: dict of {field_name: value} produced by the LLM via structured outputs
- schema: dict with shape {"subcategory_code": str, "fields": [field_def, ...]}
  where field_def matches the required_fields jsonb shape from Doc A v2.1 §2.5

It returns the payload unchanged on success. On failure it raises StructuredDataValidatorError
with a precise message naming the offending field.

Field types supported (matching Doc A v2.1 §2.5 CHECK constraint):
- enum, string, integer, date, phone, yes_no, free_text, media
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

ALLOWED_TYPES = {"enum", "string", "integer", "date", "phone", "yes_no", "free_text", "media"}

# Indian mobile: optional +91, then 10 digits starting with 6-9 per current TRAI rules.
PHONE_PATTERN = re.compile(r"^(\+91)?[6-9]\d{9}$")

# yes_no accepts boolean True/False or strings "yes"/"no" (case insensitive)
YES_VALUES = {"yes", "true", "1"}
NO_VALUES = {"no", "false", "0"}


class StructuredDataValidatorError(Exception):
    """Raised when the LLM payload fails cross-validation against the schema."""


class StructuredDataValidator:
    """Validates LLM structured output against a category schema.

    Stateless. One instance per agent, called once per dispatch.
    """

    def validate(self, payload: dict, schema: dict) -> dict:
        """Validate the payload against the schema. Returns the payload on success.

        Raises StructuredDataValidatorError on any violation, with the field name
        and the specific failure mode in the message.
        """
        if not isinstance(payload, dict):
            raise StructuredDataValidatorError(
                f"payload must be a dict, got {type(payload).__name__}"
            )
        if not isinstance(schema, dict):
            raise StructuredDataValidatorError(
                f"schema must be a dict, got {type(schema).__name__}"
            )

        fields = schema.get("fields") or []
        if not isinstance(fields, list):
            raise StructuredDataValidatorError("schema.fields must be a list")

        for field in fields:
            self._validate_field(field, payload)

        return payload

    def _validate_field(self, field: dict, payload: dict) -> None:
        name = field.get("name")
        ftype = field.get("type")
        required = field.get("required", False)

        if not name:
            raise StructuredDataValidatorError("schema field missing 'name' key")
        if ftype not in ALLOWED_TYPES:
            raise StructuredDataValidatorError(
                f"field '{name}' has unsupported type '{ftype}'; "
                f"must be one of {sorted(ALLOWED_TYPES)}"
            )

        if name not in payload or payload[name] in (None, ""):
            if required:
                raise StructuredDataValidatorError(
                    f"required field '{name}' is missing from payload"
                )
            return

        value = payload[name]

        if ftype == "enum":
            options = field.get("options") or []
            if not options:
                raise StructuredDataValidatorError(
                    f"enum field '{name}' has no options declared in schema"
                )
            if value not in options:
                raise StructuredDataValidatorError(
                    f"field '{name}' has value '{value}' not in allowed options {options}"
                )

        elif ftype in ("string", "free_text"):
            if not isinstance(value, str):
                raise StructuredDataValidatorError(
                    f"field '{name}' must be a string, got {type(value).__name__}"
                )
            self._apply_validation_hint(name, value, field.get("validation_hint"), kind="string")

        elif ftype == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise StructuredDataValidatorError(
                    f"field '{name}' must be an integer, got {type(value).__name__}"
                )
            self._apply_validation_hint(name, value, field.get("validation_hint"), kind="integer")

        elif ftype == "date":
            if isinstance(value, str):
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError as exc:
                    raise StructuredDataValidatorError(
                        f"field '{name}' must be ISO date YYYY-MM-DD, got '{value}'"
                    ) from exc
            else:
                raise StructuredDataValidatorError(
                    f"field '{name}' must be a date string, got {type(value).__name__}"
                )

        elif ftype == "phone":
            if not isinstance(value, str):
                raise StructuredDataValidatorError(
                    f"field '{name}' must be a phone string, got {type(value).__name__}"
                )
            if not PHONE_PATTERN.match(value.replace(" ", "").replace("-", "")):
                raise StructuredDataValidatorError(
                    f"field '{name}' has invalid Indian mobile format: '{value}'"
                )

        elif ftype == "yes_no":
            if isinstance(value, bool):
                return
            if isinstance(value, str):
                v_low = value.strip().lower()
                if v_low in YES_VALUES or v_low in NO_VALUES:
                    return
                raise StructuredDataValidatorError(
                    f"field '{name}' must be yes/no/true/false, got '{value}'"
                )
            raise StructuredDataValidatorError(
                f"field '{name}' must be yes_no boolean or yes/no string, got {type(value).__name__}"
            )

        elif ftype == "media":
            # Media is a marker that the LLM expects an attachment reference.
            # The reference itself comes from the media_uploads table by ID.
            # The validator only checks the value is a string ID or None (already handled above).
            if not isinstance(value, str):
                raise StructuredDataValidatorError(
                    f"field '{name}' must be a media reference string, got {type(value).__name__}"
                )

    def _apply_validation_hint(self, name: str, value: Any, hint: Any, kind: str) -> None:
        """Apply min/max/min_length/max_length constraints from a validation_hint string.

        Hint format: 'min=1', 'max=120', 'min_length=10,max_length=100', etc.
        Multiple constraints comma-separated.
        """
        if not hint:
            return
        if not isinstance(hint, str):
            raise StructuredDataValidatorError(
                f"field '{name}' has non-string validation_hint, cannot interpret"
            )

        constraints = [c.strip() for c in hint.split(",") if c.strip()]
        for constraint in constraints:
            if "=" not in constraint:
                continue  # silently ignore malformed fragments per defensive design
            key, _, raw = constraint.partition("=")
            key = key.strip()
            raw = raw.strip()
            try:
                limit = int(raw)
            except ValueError:
                continue

            if key == "min" and kind == "integer" and value < limit:
                raise StructuredDataValidatorError(
                    f"field '{name}' value {value} is below min={limit}"
                )
            if key == "max" and kind == "integer" and value > limit:
                raise StructuredDataValidatorError(
                    f"field '{name}' value {value} exceeds max={limit}"
                )
            if key == "min_length" and kind == "string" and len(value) < limit:
                raise StructuredDataValidatorError(
                    f"field '{name}' length {len(value)} is below min_length={limit}"
                )
            if key == "max_length" and kind == "string" and len(value) > limit:
                raise StructuredDataValidatorError(
                    f"field '{name}' length {len(value)} exceeds max_length={limit}"
                )
