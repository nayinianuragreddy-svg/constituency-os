"""V1.8 migration 003: extend officer_mappings."""
from sqlalchemy import text

SQL = """
ALTER TABLE officer_mappings ADD COLUMN IF NOT EXISTS queue_name VARCHAR(40);
ALTER TABLE officer_mappings ADD COLUMN IF NOT EXISTS is_default_for_queue BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE officer_mappings ADD COLUMN IF NOT EXISTS language_preference VARCHAR(8);
UPDATE officer_mappings
SET queue_name = COALESCE(queue_name,
    CASE
        WHEN lower(department) LIKE '%water%' THEN 'water_dept'
        WHEN lower(department) LIKE '%electric%' THEN 'electricity_dept'
        WHEN lower(department) LIKE '%sanitation%' THEN 'sanitation_dept'
        WHEN lower(department) LIKE '%road%' THEN 'rnb_dept'
        ELSE 'general_dept'
    END
)
WHERE queue_name IS NULL;
ALTER TABLE officer_mappings ALTER COLUMN queue_name SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_officer_queue_office ON officer_mappings (office_id, queue_name, is_default_for_queue);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
