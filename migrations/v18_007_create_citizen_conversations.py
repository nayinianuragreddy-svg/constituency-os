from sqlalchemy import text
SQL = """
CREATE TABLE IF NOT EXISTS citizen_conversations_v18 (
    id SERIAL PRIMARY KEY,
    office_id INTEGER NOT NULL REFERENCES offices(id),
    citizen_id INTEGER REFERENCES citizens(id),
    telegram_chat_id VARCHAR(40) NOT NULL,
    current_state VARCHAR(80) NOT NULL,
    return_to_state VARCHAR(80),
    draft_ticket_id UUID,
    draft_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_inbound_at TIMESTAMPTZ,
    last_state_change_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalid_attempts_in_state INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, telegram_chat_id)
);
CREATE INDEX IF NOT EXISTS idx_conv_office_chat ON citizen_conversations_v18 (office_id, telegram_chat_id);
CREATE INDEX IF NOT EXISTS idx_conv_state_active ON citizen_conversations_v18 (current_state, last_inbound_at);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
