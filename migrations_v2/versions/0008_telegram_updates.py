"""telegram_updates — deduplication log for incoming Telegram webhook calls

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-04

Telegram retries webhook deliveries on non-200 responses. This table prevents
double-processing by treating (update_id, bot_id) as the dedup key. On any
retry, the unique constraint raises an IntegrityError which the webhook handler
catches and converts to an immediate 200 response.

conversation_id is nullable because the conversation row may not exist yet
at INSERT time (first message from a new citizen).
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    _x("""
        CREATE TABLE telegram_updates (
            update_id       BIGINT       NOT NULL,
            bot_id          UUID         NOT NULL REFERENCES constituency_bots(id) ON DELETE RESTRICT,
            conversation_id UUID         REFERENCES conversations(id) ON DELETE SET NULL,
            received_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            processed_at    TIMESTAMPTZ,
            error           TEXT,
            PRIMARY KEY (update_id, bot_id)
        )
    """)
    _x("CREATE INDEX idx_telegram_updates_conversation ON telegram_updates(conversation_id)")
    _x("CREATE INDEX idx_telegram_updates_received ON telegram_updates(received_at DESC)")


def downgrade() -> None:
    _x("DROP INDEX IF EXISTS idx_telegram_updates_received")
    _x("DROP INDEX IF EXISTS idx_telegram_updates_conversation")
    _x("DROP TABLE IF EXISTS telegram_updates")
