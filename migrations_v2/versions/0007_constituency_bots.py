"""constituency_bots — one Telegram bot per constituency

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-04

One row per deployed Telegram bot. The bot's identity IS the constituency.
Tokens are stored encrypted with Fernet (see app/telegram/encryption.py).
secret_token is plaintext because its only purpose is verifying the
X-Telegram-Bot-Api-Secret-Token header on incoming webhook calls. Leaking
it only enables fake webhook calls which still fail dispatch on a bad bot_token.

mla_name is stored here (not on constituencies) because the MLA's display name
may differ from the constituency's administrative name, and this is the table
that maps constituency to bot identity.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade() -> None:
    _x("""
        CREATE TABLE constituency_bots (
            id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            constituency_id      UUID         NOT NULL REFERENCES constituencies(id) ON DELETE RESTRICT,
            mla_name             VARCHAR(200) NOT NULL,
            bot_username         VARCHAR(64)  NOT NULL,
            bot_token_encrypted  TEXT         NOT NULL,
            secret_token         VARCHAR(256) NOT NULL,
            is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
            webhook_url          TEXT,
            created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_constituency_bots_username     UNIQUE (bot_username),
            CONSTRAINT uq_constituency_bots_secret_token UNIQUE (secret_token)
        )
    """)
    _x("CREATE INDEX idx_constituency_bots_active ON constituency_bots(is_active)")
    _x("CREATE INDEX idx_constituency_bots_constituency ON constituency_bots(constituency_id)")
    # At most one active bot per constituency
    _x(
        "CREATE UNIQUE INDEX uq_constituency_bots_active_constituency "
        "ON constituency_bots(constituency_id) WHERE is_active = TRUE"
    )


def downgrade() -> None:
    _x("DROP INDEX IF EXISTS uq_constituency_bots_active_constituency")
    _x("DROP INDEX IF EXISTS idx_constituency_bots_constituency")
    _x("DROP INDEX IF EXISTS idx_constituency_bots_active")
    _x("DROP TABLE IF EXISTS constituency_bots")
