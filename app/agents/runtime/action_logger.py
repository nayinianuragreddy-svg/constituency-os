"""ActionLogger: writes agent_actions rows to the database.

Per Doc B v2.1 §4. Every dispatch call writes one row recording what the agent
did, the cost, hops used, and any error.

cost_usd, hops_used, and error are written to their dedicated columns (added in
migration 0006). The status column is set to 'success' or 'error'.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.engine import Engine


class ActionLogger:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def log(
        self,
        agent_name: str,
        conversation_id: Optional[str],
        action_type: str,
        payload: dict,
        cost_usd: float,
        hops_used: int,
        error: Optional[str] = None,
    ) -> str:
        """Insert one agent_actions row. Returns the generated UUID as a string.

        action_type is a short string like 'dispatch', 'tool_call', 'escalation'.
        payload is anything serialisable to jsonb that captures what happened.
        cost_usd, hops_used, and error are written to their dedicated columns.
        """
        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        status = "error" if error else "success"

        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO agent_actions
                        (id, agent_name, action_type, conversation_id,
                         payload, response, status,
                         cost_usd, hops_used, error,
                         created_at)
                    VALUES
                        (:id, :agent_name, :action_type, :conversation_id,
                         :payload, :response, :status,
                         :cost_usd, :hops_used, :error,
                         :created_at)
                    """
                ),
                {
                    "id": action_id,
                    "agent_name": agent_name,
                    "action_type": action_type,
                    "conversation_id": conversation_id,
                    "payload": json.dumps(payload),
                    "response": "{}",
                    "status": status,
                    "cost_usd": cost_usd,
                    "hops_used": hops_used,
                    "error": error,
                    "created_at": now,
                },
            )

        return action_id
