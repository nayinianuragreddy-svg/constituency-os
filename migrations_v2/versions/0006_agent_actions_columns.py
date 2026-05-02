"""agent_actions — promote cost_usd, hops_used, error to dedicated columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-02

Doc B v2.1 §4 specified cost_usd, hops_used, and error as dedicated columns on
agent_actions. PR 4e shipped a workaround that stored them inside the payload
JSONB under _cost_usd, _hops_used, and _error keys. This migration fixes the
gap: adds the three columns, backfills existing rows from the JSONB workaround,
then locks in NOT NULL defaults and CHECK constraints.

The prefixed keys in existing payload rows are left intact for audit
traceability. New code no longer writes them.
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
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
    # Step 1: add three nullable columns so backfill can run without a default
    _x("ALTER TABLE agent_actions ADD COLUMN cost_usd  NUMERIC(10, 6)")
    _x("ALTER TABLE agent_actions ADD COLUMN hops_used INTEGER")
    _x("ALTER TABLE agent_actions ADD COLUMN error     TEXT")

    # Step 2: backfill from existing payload JSONB workaround keys
    _x("""
        UPDATE agent_actions
        SET cost_usd = (payload->>'_cost_usd')::NUMERIC
        WHERE payload->>'_cost_usd' IS NOT NULL
    """)
    _x("""
        UPDATE agent_actions
        SET hops_used = (payload->>'_hops_used')::INTEGER
        WHERE payload->>'_hops_used' IS NOT NULL
    """)
    _x("""
        UPDATE agent_actions
        SET error = payload->>'_error'
        WHERE payload->>'_error' IS NOT NULL
    """)

    # Step 3: set defaults and NOT NULL for cost_usd and hops_used.
    # Rows that had no JSONB workaround values (e.g. inserted before PR 4e)
    # default to 0 before the constraint is applied.
    _x("UPDATE agent_actions SET cost_usd  = 0.0 WHERE cost_usd  IS NULL")
    _x("UPDATE agent_actions SET hops_used = 0   WHERE hops_used IS NULL")

    _x("ALTER TABLE agent_actions ALTER COLUMN cost_usd  SET DEFAULT 0.0")
    _x("ALTER TABLE agent_actions ALTER COLUMN hops_used SET DEFAULT 0")
    _x("ALTER TABLE agent_actions ALTER COLUMN cost_usd  SET NOT NULL")
    _x("ALTER TABLE agent_actions ALTER COLUMN hops_used SET NOT NULL")
    # error stays nullable — NULL means no error occurred

    # Step 4: CHECK constraints enforce non-negative values
    _x("""
        ALTER TABLE agent_actions
        ADD CONSTRAINT chk_agent_actions_costs
        CHECK (cost_usd >= 0 AND hops_used >= 0)
    """)


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    _x("ALTER TABLE agent_actions DROP CONSTRAINT chk_agent_actions_costs")
    _x("ALTER TABLE agent_actions ALTER COLUMN cost_usd  DROP NOT NULL")
    _x("ALTER TABLE agent_actions ALTER COLUMN hops_used DROP NOT NULL")
    _x("ALTER TABLE agent_actions ALTER COLUMN cost_usd  DROP DEFAULT")
    _x("ALTER TABLE agent_actions ALTER COLUMN hops_used DROP DEFAULT")
    _x("ALTER TABLE agent_actions DROP COLUMN error")
    _x("ALTER TABLE agent_actions DROP COLUMN hops_used")
    _x("ALTER TABLE agent_actions DROP COLUMN cost_usd")
