"""V1.8 migration 002: extend tickets table."""
from sqlalchemy import text

SQL = """
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ticket_id_human VARCHAR(40);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category_code VARCHAR(8);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS severity_or_urgency VARCHAR(40);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS location_text TEXT;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS complaint_geo_lat NUMERIC(9,6);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS complaint_geo_lng NUMERIC(9,6);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS assigned_queue VARCHAR(40);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS assigned_officer_id INTEGER;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS requires_review BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS media_file_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS language_at_creation VARCHAR(8);
UPDATE tickets SET ticket_id_human = COALESCE(ticket_id_human, CONCAT('LEGACY-', id::text)) WHERE ticket_id_human IS NULL;
UPDATE tickets SET category_code = COALESCE(category_code, 'PUB-OTH') WHERE category_code IS NULL;
UPDATE tickets SET assigned_queue = COALESCE(assigned_queue, 'general_dept') WHERE assigned_queue IS NULL;
ALTER TABLE tickets ALTER COLUMN ticket_id_human SET NOT NULL;
ALTER TABLE tickets ALTER COLUMN category_code SET NOT NULL;
ALTER TABLE tickets ALTER COLUMN assigned_queue SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_human_id ON tickets (ticket_id_human);
CREATE INDEX IF NOT EXISTS idx_tickets_office_status_created ON tickets (office_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_category_code_created ON tickets (category_code, created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_citizen_status ON tickets (citizen_id, status);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
