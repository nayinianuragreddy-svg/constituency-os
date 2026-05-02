"""PromptRenderer: deterministic system prompt assembly for V2.0 agents.

Per Doc B v2.1 §2.1. Pure function: same inputs always produce same output.

The renderer takes:
- a prompt template path (a Markdown file with str.format placeholders)
- a conversation summary dict (the conversations.summary_data jsonb structure from Doc C §7.1)
- an optional category schema dict (the loaded sub-category from load_category_schema)
- a constituency config dict (MLA name, constituency name)
- an optional current_date_ist datetime (defaults to now in IST)

It returns a fully rendered system prompt string ready to send to OpenAI.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


# IST is UTC+5:30, fixed offset (no DST in India)
IST = timezone(timedelta(hours=5, minutes=30))

# Cap on history_compressed entries rendered into the prompt, per Doc B v2.1 §2.1
HISTORY_RENDER_CAP = 20


class PromptRendererError(Exception):
    """Raised when prompt rendering fails (template not found, missing placeholder, etc.)."""


class PromptRenderer:
    """Renders a system prompt template with conversation state substitutions.

    Initialized once per agent (template loaded from disk at construction time).
    Called once per dispatch (render() executes the substitution).
    """

    def __init__(self, agent_name: str, prompt_template_path: str) -> None:
        if not agent_name:
            raise PromptRendererError("agent_name must be a non-empty string")
        if not prompt_template_path:
            raise PromptRendererError("prompt_template_path must be a non-empty string")
        if not os.path.isfile(prompt_template_path):
            raise PromptRendererError(
                f"prompt template not found at: {prompt_template_path}"
            )

        self.agent_name = agent_name
        self.prompt_template_path = prompt_template_path
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            self.template = f.read()

    def render(
        self,
        conversation_summary: dict,
        category_schema: Optional[dict] = None,
        constituency_config: Optional[dict] = None,
        current_date_ist: Optional[datetime] = None,
    ) -> str:
        """Render the template with the given inputs.

        Raises PromptRendererError if a required placeholder is missing from inputs.
        """
        constituency_config = constituency_config or {}

        if current_date_ist is None:
            current_date_ist = datetime.now(IST)

        substitutions = {
            "preferred_language": conversation_summary.get("language_preference", "english"),
            "last_message_script": conversation_summary.get("language_script", "roman"),
            "conversation_summary": self._format_summary(conversation_summary),
            "current_category_schema": (
                self._format_schema(category_schema)
                if category_schema
                else "Not loaded yet."
            ),
            "current_date_ist": current_date_ist.strftime("%d %B %Y, %A, %H:%M IST"),
            "MLA_NAME": constituency_config.get("mla_name", "the MLA"),
            "CONSTITUENCY_NAME": constituency_config.get("name", "this constituency"),
        }

        try:
            return self.template.format(**substitutions)
        except KeyError as exc:
            raise PromptRendererError(
                f"template contains placeholder {exc!s} that was not provided in substitutions"
            ) from exc
        except IndexError as exc:
            raise PromptRendererError(
                f"template has malformed placeholder syntax: {exc!s}"
            ) from exc

    def _format_summary(self, summary: dict) -> str:
        """Render the conversation summary jsonb as a compact, LLM-readable text block.

        Per Doc B v2.1 §2.1: history_compressed is truncated to last HISTORY_RENDER_CAP entries.
        """
        lines: list[str] = []

        citizen = summary.get("citizen") or {}
        if citizen:
            lines.append("CITIZEN")
            fields_known = citizen.get("fields_known") or {}
            for key, value in fields_known.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        current_complaint = summary.get("current_complaint") or {}
        if current_complaint:
            lines.append("CURRENT COMPLAINT")
            for key in ("phase", "category_code", "subcategory_code", "ticket_id_prefix"):
                if current_complaint.get(key):
                    lines.append(f"  {key}: {current_complaint[key]}")

            current_format = current_complaint.get("current_format") or {}
            fields = current_format.get("fields") or []
            if fields:
                lines.append("  fields:")
                for f in fields:
                    name = f.get("name", "?")
                    value = f.get("value")
                    required = f.get("required", False)
                    state = "FILLED" if value not in (None, "") else "PENDING"
                    req_marker = " (required)" if required else ""
                    if value not in (None, ""):
                        lines.append(f"    - {name}{req_marker}: {value} [{state}]")
                    else:
                        lines.append(f"    - {name}{req_marker}: [{state}]")
            lines.append("")

        history = summary.get("history_compressed") or []
        if history:
            lines.append("RECENT HISTORY")
            recent = history[-HISTORY_RENDER_CAP:]
            for entry in recent:
                role = entry.get("role", "?")
                text = entry.get("text", "")
                lines.append(f"  {role}: {text}")
            lines.append("")

        open_questions = summary.get("open_questions") or []
        if open_questions:
            lines.append("OPEN QUESTIONS")
            for q in open_questions:
                lines.append(f"  - {q}")
            lines.append("")

        if not lines:
            return "No conversation state yet."

        return "\n".join(lines).rstrip()

    def _format_schema(self, schema: dict) -> str:
        """Render a loaded category schema as a clear, LLM-readable list.

        Per Doc B v2.1 §2.1, the rendered output looks like:
            Required fields for PUB.WATER:
              1. issue_type (enum: no_supply | contamination | ...) - REQUIRED
              2. exact_location (string) - REQUIRED
              ...
        """
        subcategory_code = schema.get("subcategory_code", "?")
        fields = schema.get("fields") or []

        lines: list[str] = [f"Required fields for {subcategory_code}:"]
        for idx, f in enumerate(fields, start=1):
            name = f.get("name", "?")
            ftype = f.get("type", "?")
            required = f.get("required", False)
            options = f.get("options")

            if ftype == "enum" and options:
                options_str = " | ".join(options)
                type_clause = f"enum: {options_str}"
            else:
                type_clause = ftype

            req_marker = "REQUIRED" if required else "OPTIONAL"
            lines.append(f"  {idx}. {name} ({type_clause}) - {req_marker}")

        return "\n".join(lines)
