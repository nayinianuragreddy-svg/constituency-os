from sqlalchemy import text
SQL = """
CREATE TABLE IF NOT EXISTS mandals (
    id SERIAL PRIMARY KEY,
    office_id INTEGER NOT NULL REFERENCES offices(id),
    name VARCHAR(120) NOT NULL,
    name_te VARCHAR(120),
    name_hi VARCHAR(120),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, name)
);
CREATE INDEX IF NOT EXISTS idx_mandals_office_active ON mandals (office_id, is_active, sort_order);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
