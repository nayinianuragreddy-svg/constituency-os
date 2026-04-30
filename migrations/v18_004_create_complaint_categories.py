from sqlalchemy import text

SQL = """
CREATE TABLE IF NOT EXISTS complaint_categories (
    id SERIAL PRIMARY KEY,
    code VARCHAR(8) NOT NULL UNIQUE,
    parent_group VARCHAR(20) NOT NULL,
    display_name_en VARCHAR(120) NOT NULL,
    display_name_te VARCHAR(120),
    display_name_hi VARCHAR(120),
    icon_emoji VARCHAR(10),
    default_routing_queue VARCHAR(40) NOT NULL,
    requires_geo BOOLEAN NOT NULL DEFAULT FALSE,
    requires_photo BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_complaint_categories_active ON complaint_categories (is_active, sort_order);
CREATE INDEX IF NOT EXISTS idx_complaint_categories_parent ON complaint_categories (parent_group, is_active);
"""

def run(conn) -> None:
    conn.execute(text(SQL))
