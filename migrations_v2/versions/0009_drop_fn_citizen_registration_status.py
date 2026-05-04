"""Drop unused fn_citizen_registration_status stored function.

The function is unused — Python in save_citizen_field reimplements the same
logic via a SQL UPDATE. Keeping it creates a PG type dependency on the citizens
table that complicates future schema changes.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-04
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fn_citizen_registration_status(citizens) CASCADE;")


def downgrade() -> None:
    # Recreate the original function verbatim (from migration 0001).
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_citizen_registration_status(c citizens)
        RETURNS BOOLEAN
        LANGUAGE plpgsql
        IMMUTABLE
        AS $$
        BEGIN
            RETURN c.name      IS NOT NULL
               AND c.mobile    IS NOT NULL
               AND c.ward_id   IS NOT NULL
               AND c.mandal_id IS NOT NULL;
        END;
        $$
    """)
