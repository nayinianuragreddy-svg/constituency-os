"""StateReader: loads conversations.summary_data from the database.

Per Doc B v2.1 §3, every dispatch call reads the latest conversation summary
before rendering the prompt. The summary is a jsonb column following the
shape in Doc C v2.1 §7.1.
"""

from __future__ import annotations

import uuid
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.engine import Engine


class StateReaderError(Exception):
    pass


class StateReader:
    """Stateless. Reads conversation state by conversation_id."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(self, conversation_id: str) -> dict:
        """Return the summary_data jsonb for the given conversation.

        Returns an empty dict if the conversation exists but has no summary yet.
        Raises StateReaderError if the conversation does not exist.
        """
        try:
            conv_uuid = uuid.UUID(str(conversation_id))
        except (ValueError, TypeError) as exc:
            raise StateReaderError(f"invalid conversation_id: {conversation_id!r}") from exc

        with self._engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT summary_data FROM conversations WHERE id = :cid"),
                {"cid": str(conv_uuid)},
            ).fetchone()

        if row is None:
            raise StateReaderError(f"conversation not found: {conversation_id}")

        summary = row[0]
        if summary is None:
            return {}
        if isinstance(summary, dict):
            return summary
        # Some drivers return jsonb as text; best-effort parse
        import json as _json
        try:
            return _json.loads(summary)
        except (TypeError, ValueError):
            return {}
