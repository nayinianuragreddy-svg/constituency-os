"""Pure-function unit tests for StructuredDataValidator (PR 4c)."""

from __future__ import annotations

import pytest

from app.agents.runtime import (
    StructuredDataValidator,
    StructuredDataValidatorError,
)


@pytest.fixture
def validator() -> StructuredDataValidator:
    return StructuredDataValidator()


def test_payload_must_be_dict(validator):
    with pytest.raises(StructuredDataValidatorError, match="payload"):
        validator.validate("not a dict", {"fields": []})


def test_schema_must_be_dict(validator):
    with pytest.raises(StructuredDataValidatorError, match="schema"):
        validator.validate({}, "not a dict")


def test_required_field_missing_raises(validator):
    schema = {"fields": [{"name": "issue_type", "type": "enum", "required": True, "options": ["a", "b"]}]}
    with pytest.raises(StructuredDataValidatorError, match="required field 'issue_type'"):
        validator.validate({}, schema)


def test_required_field_empty_string_raises(validator):
    schema = {"fields": [{"name": "exact_location", "type": "string", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="required field 'exact_location'"):
        validator.validate({"exact_location": ""}, schema)


def test_optional_field_missing_passes(validator):
    schema = {"fields": [{"name": "fir_number", "type": "string", "required": False}]}
    assert validator.validate({}, schema) == {}


def test_enum_value_in_options_passes(validator):
    schema = {"fields": [{"name": "issue_type", "type": "enum", "required": True, "options": ["no_supply", "contamination"]}]}
    assert validator.validate({"issue_type": "no_supply"}, schema) == {"issue_type": "no_supply"}


def test_enum_value_not_in_options_raises(validator):
    schema = {"fields": [{"name": "issue_type", "type": "enum", "required": True, "options": ["no_supply", "contamination"]}]}
    with pytest.raises(StructuredDataValidatorError, match="not in allowed options"):
        validator.validate({"issue_type": "water_problem"}, schema)


def test_enum_with_no_options_in_schema_raises(validator):
    schema = {"fields": [{"name": "issue_type", "type": "enum", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="no options declared"):
        validator.validate({"issue_type": "anything"}, schema)


def test_string_must_be_string(validator):
    schema = {"fields": [{"name": "name", "type": "string", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="must be a string"):
        validator.validate({"name": 12345}, schema)


def test_string_min_length_enforced(validator):
    schema = {"fields": [{"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10"}]}
    with pytest.raises(StructuredDataValidatorError, match="below min_length"):
        validator.validate({"description": "short"}, schema)


def test_string_max_length_enforced(validator):
    schema = {"fields": [{"name": "title", "type": "string", "required": True, "validation_hint": "min_length=5,max_length=10"}]}
    with pytest.raises(StructuredDataValidatorError, match="exceeds max_length"):
        validator.validate({"title": "this is way too long"}, schema)


def test_integer_must_be_int(validator):
    schema = {"fields": [{"name": "households_affected", "type": "integer", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="must be an integer"):
        validator.validate({"households_affected": "5"}, schema)


def test_integer_bool_rejected(validator):
    """True is technically an int in Python, but should be rejected for integer fields."""
    schema = {"fields": [{"name": "count", "type": "integer", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="must be an integer"):
        validator.validate({"count": True}, schema)


def test_integer_min_enforced(validator):
    schema = {"fields": [{"name": "duration_days", "type": "integer", "required": True, "validation_hint": "min=1"}]}
    with pytest.raises(StructuredDataValidatorError, match="below min"):
        validator.validate({"duration_days": 0}, schema)


def test_integer_max_enforced(validator):
    schema = {"fields": [{"name": "patient_age", "type": "integer", "required": True, "validation_hint": "min=0,max=120"}]}
    with pytest.raises(StructuredDataValidatorError, match="exceeds max"):
        validator.validate({"patient_age": 200}, schema)


def test_integer_within_range_passes(validator):
    schema = {"fields": [{"name": "patient_age", "type": "integer", "required": True, "validation_hint": "min=0,max=120"}]}
    assert validator.validate({"patient_age": 45}, schema) == {"patient_age": 45}


def test_date_iso_format_passes(validator):
    schema = {"fields": [{"name": "incident_date", "type": "date", "required": True}]}
    assert validator.validate({"incident_date": "2026-04-15"}, schema) == {"incident_date": "2026-04-15"}


def test_date_invalid_format_raises(validator):
    schema = {"fields": [{"name": "incident_date", "type": "date", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="ISO date"):
        validator.validate({"incident_date": "15/04/2026"}, schema)


def test_phone_indian_mobile_passes(validator):
    schema = {"fields": [{"name": "mobile", "type": "phone", "required": True}]}
    assert validator.validate({"mobile": "9876543210"}, schema) == {"mobile": "9876543210"}


def test_phone_with_country_code_passes(validator):
    schema = {"fields": [{"name": "mobile", "type": "phone", "required": True}]}
    assert validator.validate({"mobile": "+919876543210"}, schema) == {"mobile": "+919876543210"}


def test_phone_with_spaces_and_hyphens_passes(validator):
    schema = {"fields": [{"name": "mobile", "type": "phone", "required": True}]}
    assert validator.validate({"mobile": "98765-43210"}, schema) == {"mobile": "98765-43210"}


def test_phone_invalid_format_raises(validator):
    schema = {"fields": [{"name": "mobile", "type": "phone", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="invalid Indian mobile"):
        validator.validate({"mobile": "12345"}, schema)


def test_phone_starting_with_5_or_below_raises(validator):
    """Indian mobiles must start with 6-9 per current TRAI rules."""
    schema = {"fields": [{"name": "mobile", "type": "phone", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="invalid Indian mobile"):
        validator.validate({"mobile": "5876543210"}, schema)


def test_yes_no_boolean_passes(validator):
    schema = {"fields": [{"name": "consent", "type": "yes_no", "required": True}]}
    assert validator.validate({"consent": True}, schema) == {"consent": True}


def test_yes_no_string_yes_passes(validator):
    schema = {"fields": [{"name": "consent", "type": "yes_no", "required": True}]}
    assert validator.validate({"consent": "yes"}, schema) == {"consent": "yes"}


def test_yes_no_invalid_value_raises(validator):
    schema = {"fields": [{"name": "consent", "type": "yes_no", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="must be yes/no"):
        validator.validate({"consent": "maybe"}, schema)


def test_media_string_passes(validator):
    schema = {"fields": [{"name": "photo", "type": "media", "required": False}]}
    assert validator.validate({"photo": "media_upload_id_abc123"}, schema) == {"photo": "media_upload_id_abc123"}


def test_media_non_string_raises(validator):
    schema = {"fields": [{"name": "photo", "type": "media", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="media reference string"):
        validator.validate({"photo": 12345}, schema)


def test_unsupported_type_raises(validator):
    """A schema with an unknown type must fail loudly, not silently pass."""
    schema = {"fields": [{"name": "exotic", "type": "ufo", "required": True}]}
    with pytest.raises(StructuredDataValidatorError, match="unsupported type"):
        validator.validate({"exotic": "anything"}, schema)


def test_full_realistic_water_complaint_passes(validator):
    """End-to-end test with a realistic PUB.WATER payload matching Doc C §6.3."""
    schema = {
        "subcategory_code": "PUB.WATER",
        "fields": [
            {"name": "issue_type", "type": "enum", "required": True, "options": ["no_supply", "contamination", "pipeline_break", "borewell", "new_connection"]},
            {"name": "exact_location", "type": "string", "required": True},
            {"name": "duration_days", "type": "integer", "required": True, "validation_hint": "min=1"},
            {"name": "households_affected", "type": "integer", "required": True, "validation_hint": "min=1"},
            {"name": "previous_complaint_ref", "type": "string", "required": False},
            {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10"},
        ],
    }
    payload = {
        "issue_type": "no_supply",
        "exact_location": "Ward 11, Bhagat Singh Nagar, near the Hanuman temple",
        "duration_days": 4,
        "households_affected": 25,
        "description": "No water supply in the entire street for the past four days",
    }
    assert validator.validate(payload, schema) == payload
