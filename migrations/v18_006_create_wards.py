from sqlalchemy import text
SQL = """
CREATE TABLE IF NOT EXISTS wards (
    id SERIAL PRIMARY KEY,
    office_id INTEGER NOT NULL REFERENCES offices(id),
    mandal_id INTEGER NOT NULL REFERENCES mandals(id),
    ward_number INTEGER NOT NULL,
    ward_name VARCHAR(120),
    centroid_lat NUMERIC(9,6) NOT NULL,
    centroid_lng NUMERIC(9,6) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, mandal_id, ward_number)
);
CREATE INDEX IF NOT EXISTS idx_wards_office_mandal ON wards (office_id, mandal_id, ward_number);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
