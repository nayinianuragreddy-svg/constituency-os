"""confirm_with_citizen: render a deterministic read-back for citizen confirmation.

Per Doc C v2.1 §5.5 and §7.3.

When all required complaint fields are collected, this tool generates a fixed-template
read-back showing every collected field's value. The citizen must confirm before a ticket
is created.

Supports three languages: English, Telugu, and Hindi. Field labels remain in English
(DB labels are not translated in PR 5d; label translation is a future PR).

The read-back is NOT LLM-generated. This guarantees it is always complete and never
invents or omits fields (per Doc C §7.3).

If confirmation_reads exceeds 3, the tool returns an error indicating the agent should
escalate to a human.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult

MAX_CONFIRMATION_READS = 3

# Read-back templates per language. {fields_block} is substituted at render time.
# Field labels remain in English (PR 5d scope; full label translation is a future PR).
_ENGLISH_INTRO = "I have noted your concern as follows:"
_ENGLISH_OUTRO = 'Is this correct? If correct, please say "yes". If anything needs to change, please tell me what.'

_TELUGU_INTRO = "మీ సమస్యను నేను ఈ విధంగా గమనించాను:"
_TELUGU_OUTRO = 'ఇది సరిగ్గా ఉందా? సరిగ్గా ఉంటే "అవును" అని చెప్పండి. ఏదైనా మార్చాలంటే చెప్పండి.'

_HINDI_INTRO = "मैंने आपकी समस्या को इस प्रकार समझा है:"
_HINDI_OUTRO = 'क्या यह सही है? यदि सही है, तो कृपया "हाँ" कहें। यदि कुछ बदलना है, तो कृपया बताएं।'

_TEMPLATES = {
    "english": (_ENGLISH_INTRO, _ENGLISH_OUTRO),
    "telugu": (_TELUGU_INTRO, _TELUGU_OUTRO),
    "hindi": (_HINDI_INTRO, _HINDI_OUTRO),
}


class ConfirmWithCitizen(Tool):
    name = "confirm_with_citizen"
    description = (
        "Render a deterministic confirmation read-back once all required complaint fields "
        "have been collected. Call this only after extract_structured_data reports "
        "all_required_collected=true. The returned readback_text must be sent to the citizen "
        "as the reply_text. Supports English, Telugu, and Hindi."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["english", "telugu", "hindi"],
                "description": (
                    "Language for the confirmation read-back. "
                    "Pass 'telugu' for Telugu-script conversations, 'hindi' for Devanagari, "
                    "'english' for Roman-script conversations."
                ),
            },
        },
        "required": ["language"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        # LLM-provided language is accepted as a hint, but the actual language used
        # is taken from summary_data.language_preference when available. This prevents
        # the model from mis-defaulting to "english" on non-English conversations
        # (same pattern as add_to_history role normalization in PR 5b.1).
        language_hint = inputs.get("language", "english")

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

            # Resolve language: prefer the conversation's stored preference over the LLM hint.
            db_language = summary.get("language_preference", "")
            language = db_language if db_language in _TEMPLATES else language_hint
            if language not in _TEMPLATES:
                language = "english"

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

            # Select the template for the requested language (default English on invalid input)
            intro, outro = _TEMPLATES.get(language, _TEMPLATES["english"])

            # Build fields block (labels stay in English per PR 5d scope)
            field_lines: list[str] = []
            for field in fields:
                name = field.get("name", "")
                value = field.get("value")
                if value is None or value == "":
                    continue  # skip optional fields citizen didn't provide
                label = label_map.get(name) or name.replace("_", " ").title()
                field_lines.append(f"- {label}: {value}")

            lines = [intro] + field_lines + [outro]
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
