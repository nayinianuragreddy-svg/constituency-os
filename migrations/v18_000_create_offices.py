from sqlalchemy import text

SQL = """
CREATE TABLE IF NOT EXISTS offices (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL DEFAULT 'Default Office',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO offices (id, name)
VALUES (1, 'Default Office')
ON CONFLICT (id) DO NOTHING;
SELECT setval('offices_id_seq', GREATEST((SELECT COALESCE(MAX(id), 1) FROM offices), 1), true);
"""


def run(conn) -> None:
    conn.execute(text(SQL))