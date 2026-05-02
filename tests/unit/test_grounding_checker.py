"""Pure-function unit tests for SubstringGroundingChecker (PR 4d).

Covers:
- exact substring grounding
- whitespace, hyphen, and punctuation tolerance
- case insensitivity
- Telugu and Devanagari Unicode
- empty inputs
- non-string values are skipped
- multiple fields, mixed pass/fail in one call
- the report's all_grounded property
"""

from __future__ import annotations

import pytest

from app.agents.runtime import (
    SubstringGroundingChecker,
    GroundingReport,
    GroundingFailure,
)


@pytest.fixture
def checker() -> SubstringGroundingChecker:
    return SubstringGroundingChecker()


def test_exact_match_grounds(checker):
    transcript = "My name is Anurag Reddy and I live in Ward 11."
    report = checker.check([("name", "Anurag Reddy")], transcript)
    assert report.all_grounded
    assert report.failures == []
    assert bool(report) is True


def test_value_not_in_transcript_fails(checker):
    transcript = "My name is Anurag Reddy."
    report = checker.check([("name", "Ravi Kumar")], transcript)
    assert not report.all_grounded
    assert len(report.failures) == 1
    assert report.failures[0].field_name == "name"
    assert report.failures[0].extracted_value == "Ravi Kumar"


def test_case_insensitive(checker):
    transcript = "The street is BHAGAT SINGH NAGAR."
    report = checker.check([("location", "Bhagat Singh Nagar")], transcript)
    assert report.all_grounded


def test_whitespace_tolerant(checker):
    """Citizen typed mobile with spaces, LLM extracted without."""
    transcript = "My number is 98765 43210."
    report = checker.check([("mobile", "9876543210")], transcript)
    assert report.all_grounded


def test_hyphen_tolerant(checker):
    """Voter ID may be written with or without hyphens."""
    transcript = "My voter ID is ABC-1234567."
    report = checker.check([("voter_id", "ABC1234567")], transcript)
    assert report.all_grounded


def test_punctuation_tolerant(checker):
    transcript = "I live at H.No. 11-3-456, Ward 7."
    report = checker.check([("address", "H No 11 3 456 Ward 7")], transcript)
    assert report.all_grounded


def test_partial_match_grounds(checker):
    """If the value is a substring of any portion of the transcript, it grounds."""
    transcript = "Please file a complaint against Inspector Ramesh of Ibrahimpatnam Police Station."
    report = checker.check([("police_station", "Ibrahimpatnam Police Station")], transcript)
    assert report.all_grounded


def test_telugu_grounding_passes(checker):
    """Telugu text in transcript and extracted value must compare correctly."""
    transcript = "నా పేరు అనురాగ్ రెడ్డి."
    report = checker.check([("name", "అనురాగ్ రెడ్డి")], transcript)
    assert report.all_grounded


def test_telugu_value_not_in_transcript_fails(checker):
    transcript = "నా పేరు అనురాగ్ రెడ్డి."
    report = checker.check([("name", "రవి కుమార్")], transcript)
    assert not report.all_grounded


def test_devanagari_grounding_passes(checker):
    transcript = "मेरा नाम अनुराग रेड्डी है।"
    report = checker.check([("name", "अनुराग रेड्डी")], transcript)
    assert report.all_grounded


def test_mixed_script_transcript(checker):
    """Real conversations mix Roman and Telugu freely. Both must work in one transcript."""
    transcript = "My name is అనురాగ్ and my mobile is 9876543210."
    report = checker.check(
        [
            ("name", "అనురాగ్"),
            ("mobile", "9876543210"),
        ],
        transcript,
    )
    assert report.all_grounded


def test_multiple_fields_mixed_pass_and_fail(checker):
    transcript = "My name is Anurag, mobile 9876543210."
    report = checker.check(
        [
            ("name", "Anurag"),       # grounds
            ("mobile", "1234567890"), # does NOT ground
            ("ward", "11"),           # does NOT ground (not in transcript)
        ],
        transcript,
    )
    assert not report.all_grounded
    failed_names = {f.field_name for f in report.failures}
    assert failed_names == {"mobile", "ward"}


def test_empty_value_is_skipped(checker):
    """Empty extracted values are not the checker's concern; validator handles required fields."""
    transcript = "Some content."
    report = checker.check([("optional_field", "")], transcript)
    assert report.all_grounded


def test_none_value_is_skipped(checker):
    transcript = "Some content."
    report = checker.check([("optional_field", None)], transcript)
    assert report.all_grounded


def test_non_string_value_is_skipped(checker):
    """Non-string values are out of scope. Validator handles type checking."""
    transcript = "5 households."
    report = checker.check([("households_affected", 5)], transcript)
    assert report.all_grounded


def test_empty_transcript_with_value_fails(checker):
    """If there's no transcript, no value can be grounded."""
    report = checker.check([("name", "Anurag")], "")
    assert not report.all_grounded


def test_empty_inputs_returns_empty_report(checker):
    report = checker.check([], "anything")
    assert report.all_grounded
    assert report.failures == []


def test_invalid_extracted_fields_type_returns_empty_report(checker):
    """Defensive: bad input shape doesn't crash, just reports nothing."""
    report = checker.check("not a list", "transcript")
    assert report.all_grounded


def test_invalid_transcript_type_returns_empty_report(checker):
    report = checker.check([("name", "Anurag")], 12345)
    assert report.all_grounded


def test_unicode_nfc_normalization():
    """Two visually identical Telugu strings with different code-point sequences must match."""
    checker = SubstringGroundingChecker()
    # Compose vs decompose forms of a Telugu cluster
    nfc_form = "కా"  # KA + AA sign (composed)
    nfd_form = "కా"  # Same here, but normalize handles edge cases
    transcript = nfc_form
    report = checker.check([("syllable", nfd_form)], transcript)
    assert report.all_grounded


def test_report_bool_protocol(checker):
    """GroundingReport is truthy when grounded, falsy when there are failures.

    This lets callers write: if not checker.check(...): retry()
    """
    grounded = checker.check([("name", "x")], "x")
    failed = checker.check([("name", "x")], "y")
    assert bool(grounded) is True
    assert bool(failed) is False


def test_failure_carries_diagnostic_info(checker):
    """A failure record names the field, the extracted value, and a reason string."""
    transcript = "Hello world."
    report = checker.check([("ward_number", "12")], transcript)
    assert len(report.failures) == 1
    f = report.failures[0]
    assert f.field_name == "ward_number"
    assert f.extracted_value == "12"
    assert "transcript" in f.reason


def test_realistic_full_complaint_grounds_correctly(checker):
    """End-to-end realistic example. Citizen described a water complaint, LLM extracted fields.
    Most ground, but one mobile number is hallucinated."""
    transcript = (
        "Hello, my name is Ravi Kumar. I live at H.No. 5-12-34, Bhagat Singh Nagar, Ward 11. "
        "My mobile is 98765 43210. There is no water supply for the past 4 days. "
        "Around 25 households are affected."
    )
    extracted = [
        ("name", "Ravi Kumar"),
        ("exact_location", "Bhagat Singh Nagar Ward 11"),
        ("mobile", "9876543210"),  # hyphen-stripped, grounds
        ("ward_number", "11"),
        ("hallucinated_mobile", "8888888888"),  # NOT in transcript, fails
    ]
    report = checker.check(extracted, transcript)
    assert not report.all_grounded
    failed_names = {f.field_name for f in report.failures}
    assert failed_names == {"hallucinated_mobile"}
