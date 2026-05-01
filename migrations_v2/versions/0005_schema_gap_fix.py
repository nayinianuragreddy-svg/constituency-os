"""schema gap fix — add default_priority to complaint_subcategories

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-01

Doc A v2.1 §4.1 requires complaint_subcategories.default_priority so the
Communication Agent can read subcat.default_priority at ticket creation time.
The column was absent from 0001. All 14 seeded rows are backfilled to 'medium';
the runtime overrides priority per conversation context.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # Step 1: add column as nullable so the backfill can run without a default
    _x("ALTER TABLE complaint_subcategories ADD COLUMN default_priority VARCHAR(20)")

    # Step 2: backfill — all 14 existing rows get 'medium'
    _x("UPDATE complaint_subcategories SET default_priority = 'medium'")

    # Step 3: lock in NOT NULL now that every row has a value
    _x("ALTER TABLE complaint_subcategories ALTER COLUMN default_priority SET NOT NULL")

    # Step 4: enforce the allowed priority vocabulary
    _x("""
        ALTER TABLE complaint_subcategories
        ADD CONSTRAINT chk_subcategories_priority
        CHECK (default_priority IN ('low', 'medium', 'high', 'critical'))
    """)


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    _x("ALTER TABLE complaint_subcategories DROP CONSTRAINT chk_subcategories_priority")
    _x("ALTER TABLE complaint_subcategories DROP COLUMN default_priority")
