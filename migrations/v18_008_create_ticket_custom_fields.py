from sqlalchemy import text
SQL = """
CREATE TABLE IF NOT EXISTS ticket_custom_fields (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    field_name VARCHAR(80) NOT NULL,
    field_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticket_id, field_name)
);
CREATE INDEX IF NOT EXISTS idx_tcf_ticket ON ticket_custom_fields (ticket_id);
CREATE INDEX IF NOT EXISTS idx_tcf_field_name ON ticket_custom_fields (field_name);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
