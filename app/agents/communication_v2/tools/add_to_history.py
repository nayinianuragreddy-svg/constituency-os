"""add_to_history: append an entry to conversations.summary_data.history_compressed.

Per Doc C v2.1 §5.3.

Behavior:
- Read current summary_data.
- Append {"role": "agent" | "citizen", "text": <text>, "ts": <iso utc>} to history_compressed.
- Trim to last 200 entries to bound size.
- Write back.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.agents.communication_v2.tools.base import Tool, ToolResult


HISTORY_TRIM_LIMIT = 200


class AddToHistory(Tool):
    name = "add_to_history"
    description = (
        "Append a message to the conversation history. "
        "Call this for every agent reply and every citizen message worth retaining."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                # "assistant" is accepted as an alias for "agent" because OpenAI models
                # default to the "assistant" chat role name. Stored value is always "agent".
                "enum": ["agent", "assistant", "citizen"],
            },
            "text": {
                "type": "string",
                "description": "The message content to append.",
            },
        },
        "required": ["role", "text"],
        "additionalProperties": False,
    }

    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        role = inputs.get("role")
        text = inputs.get("text")

        if role not in ("agent", "assistant", "citizen"):
            return ToolResult(
                success=False, data={}, error=f"role must be 'agent', 'assistant', or 'citizen', got {role!r}"
            )

        # Normalize "assistant" → "agent" so stored history is always canonical
        if role == "assistant":
            role = "agent"
        if not text or not isinstance(text, str):
            return ToolResult(success=False, data={}, error="text must be a non-empty string")

        new_entry = {
            "role": role,
            "text": text,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

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

            history = summary.get("history_compressed") or []
            if not isinstance(history, list):
                history = []
            history.append(new_entry)
            history = history[-HISTORY_TRIM_LIMIT:]
            summary["history_compressed"] = history

            conn.execute(
                sa.text(
                    "UPDATE conversations SET summary_data = :s WHERE id = :cid"
                ),
                {"s": json.dumps(summary), "cid": conversation_id},
            )

        return ToolResult(success=True, data={"history_length": len(history)})
