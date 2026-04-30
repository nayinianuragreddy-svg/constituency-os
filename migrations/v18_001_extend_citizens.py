"""V1.8 migration 001: extend citizens table.

Deviation from docs/database_schema_v2.md approved in D5:
- adds wards_fallback_text VARCHAR(120) NULL for free-text ward fallback storage.
"""

from sqlalchemy import text

SQL = """
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS dob DATE;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS voter_id VARCHAR(20);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS voter_id_skipped_at TIMESTAMPTZ;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS voter_id_skip_acknowledged BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS mandal VARCHAR(120);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS village_or_ward_name VARCHAR(120);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS ward_number INTEGER;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS ward_review_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS wards_fallback_text VARCHAR(120);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS geo_lat NUMERIC(9,6);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS geo_lng NUMERIC(9,6);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS geo_is_approximate BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(8);
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS registration_complete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE citizens ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_citizens_mobile ON citizens (mobile);
CREATE INDEX IF NOT EXISTS idx_citizens_office_ward ON citizens (office_id, ward_number);
"""


def run(conn) -> None:
    conn.execute(text(SQL))
