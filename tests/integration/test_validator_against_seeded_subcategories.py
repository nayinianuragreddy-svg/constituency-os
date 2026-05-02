"""Integration test: run StructuredDataValidator against all 14 subcategories
loaded from a real test database.

This test:
1. Creates a fresh test DB and runs all 5 migrations
2. Loads each of the 14 complaint_subcategories rows
3. For each subcategory, runs the validator against:
   - a payload missing one required field (must raise)
   - a payload with a valid value for every required field (must pass)

If any subcategory's seeded required_fields jsonb is malformed in a way the
unit tests didn't catch, this test surfaces it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.agents.runtime import (
    StructuredDataValidator,
    StructuredDataValidatorError,
)


def _value_for_type(ftype: str, options=None, hint: str = "") -> object:
    """Return a representative valid value for each field type."""
    if ftype == "enum":
        return options[0] if options else "fallback"
    if ftype == "string":
        val = "Some Location Description"
        return _pad_for_min_length(val, hint)
    if ftype == "free_text":
        val = "This is a sufficiently long description for validation purposes."
        return _pad_for_min_length(val, hint)
    if ftype == "integer":
        # Use the min value if specified, or 5 as a safe default
        for c in hint.split(","):
            c = c.strip()
            if c.startswith("min="):
                return int(c.split("=")[1])
        return 5
    if ftype == "date":
        return "2026-04-15"
    if ftype == "phone":
        return "9876543210"
    if ftype == "yes_no":
        return True
    if ftype == "media":
        return "media_upload_abc123"
    raise ValueError(f"unknown type: {ftype}")


def _pad_for_min_length(val: str, hint: str) -> str:
    for c in hint.split(","):
        c = c.strip()
        if c.startswith("min_length="):
            min_len = int(c.split("=")[1])
            if len(val) < min_len:
                return "x" * min_len
    return val


@pytest.mark.integration
def test_all_14_subcategories_validate_correctly(seeded_test_db_engine):
    """For every seeded subcategory, validate that:
    - a complete payload passes
    - omitting any one required field raises StructuredDataValidatorError
    """
    validator = StructuredDataValidator()

    with seeded_test_db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT code, required_fields FROM complaint_subcategories ORDER BY code")
        ).fetchall()

    assert len(rows) == 14, f"expected 14 subcategories, got {len(rows)}"

    for code, required_fields in rows:
        schema = {"subcategory_code": code, "fields": required_fields}

        # Build a complete valid payload, respecting validation_hint constraints
        payload = {}
        for field in required_fields:
            hint = field.get("validation_hint") or ""
            payload[field["name"]] = _value_for_type(
                field["type"], field.get("options"), hint
            )

        # Full payload must validate
        try:
            validator.validate(payload, schema)
        except StructuredDataValidatorError as exc:
            pytest.fail(
                f"subcategory {code}: complete payload should validate but raised: {exc}\n"
                f"payload: {payload}\nschema fields: {required_fields}"
            )

        # Omit each required field one at a time and confirm validator raises
        required_field_names = [f["name"] for f in required_fields if f.get("required")]
        for missing in required_field_names:
            partial = {k: v for k, v in payload.items() if k != missing}
            with pytest.raises(StructuredDataValidatorError, match=f"required field '{missing}'"):
                validator.validate(partial, schema)
