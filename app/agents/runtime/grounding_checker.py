"""SubstringGroundingChecker: verifies LLM-extracted values appear in the conversation transcript.

Per Doc B v2.1 §2.3. Pure function: same inputs always produce same output.

Defense scope: catches hallucinated factual data (numbers, IDs, names, locations) that
the LLM extracted as structured fields but never actually appeared in the citizen's
messages. Does NOT apply to:
- enum-typed fields (the value is chosen from a list, not extracted from text)
- yes_no fields (value is a binary classification)
- date fields (LLM may legitimately convert "yesterday" to ISO format)
- computed numeric fields (households_affected, duration_days)

The caller passes in only the fields that should be grounded. The checker does not
infer which fields to check.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


# Characters that may appear in extracted values but vary in the transcript.
# We strip these before comparison so "98765-43210" matches "9876543210" and
# "Ward 11" matches "ward11".
NORMALIZE_STRIP_PATTERN = re.compile(r"[\s\-_,.\(\)]")


@dataclass
class GroundingFailure:
    """One field that failed grounding."""
    field_name: str
    extracted_value: str
    reason: str


@dataclass
class GroundingReport:
    """Result of running grounding on a list of fields."""
    failures: list[GroundingFailure] = field(default_factory=list)

    @property
    def all_grounded(self) -> bool:
        return len(self.failures) == 0

    def __bool__(self) -> bool:
        # Truthy when grounded (no failures), falsy when there are failures.
        return self.all_grounded


class SubstringGroundingChecker:
    """Verifies extracted values appear, in some normalized form, in the transcript.

    Stateless. One instance per agent.
    """

    def check(
        self,
        extracted_fields: list[tuple[str, str]],
        transcript: str,
    ) -> GroundingReport:
        """Check every (field_name, value) pair against the transcript.

        Returns a GroundingReport listing any failures. Does not raise.
        """
        if not isinstance(extracted_fields, list):
            return GroundingReport(failures=[])
        if not isinstance(transcript, str):
            return GroundingReport(failures=[])

        norm_transcript = self._normalize(transcript)
        failures: list[GroundingFailure] = []

        for field_name, value in extracted_fields:
            if value is None or value == "":
                # Empty values cannot be checked. Caller must decide if this is a problem.
                continue
            if not isinstance(value, str):
                # Non-string values are not the checker's responsibility (validator handles them)
                continue

            norm_value = self._normalize(value)
            if not norm_value:
                continue

            if norm_value not in norm_transcript:
                failures.append(GroundingFailure(
                    field_name=field_name,
                    extracted_value=value,
                    reason="value not found in transcript after normalization",
                ))

        return GroundingReport(failures=failures)

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase, NFC-normalize unicode, strip punctuation/whitespace.

        NFC normalization ensures Telugu and Devanagari scripts compare correctly
        even when typed with different combining-character sequences.
        """
        if not text:
            return ""
        text = unicodedata.normalize("NFC", text)
        text = text.lower()
        text = NORMALIZE_STRIP_PATTERN.sub("", text)
        return text
