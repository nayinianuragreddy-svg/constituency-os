from sqlalchemy import text
SQL = """
CREATE TABLE IF NOT EXISTS daily_ticket_sequences (
    id SERIAL PRIMARY KEY,
    office_id INTEGER NOT NULL REFERENCES offices(id),
    sequence_date DATE NOT NULL,
    last_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, sequence_date)
);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
