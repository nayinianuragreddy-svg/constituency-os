from sqlalchemy import text
SQL = """
CREATE TABLE IF NOT EXISTS media_uploads (
    id SERIAL PRIMARY KEY,
    office_id INTEGER NOT NULL REFERENCES offices(id),
    ticket_id INTEGER REFERENCES tickets(id),
    citizen_id INTEGER REFERENCES citizens(id),
    telegram_file_id VARCHAR(200) NOT NULL,
    file_kind VARCHAR(20) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, telegram_file_id)
);
CREATE INDEX IF NOT EXISTS idx_media_ticket ON media_uploads (ticket_id);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
