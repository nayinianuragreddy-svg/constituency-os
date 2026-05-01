"""jurisdictional structure — districts, municipalities, villages, wards reshape

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01

Adds three new tables (districts, municipalities, villages), adds district_id
FK to constituencies and mandals, reshapes wards so a ward belongs to EITHER
a mandal OR a municipality (XOR), and adds a structured village_id FK to
citizens alongside the existing free-text village column.

No data is seeded here; reference data comes in PR 2b.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. districts
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE districts (
            id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR(200) NOT NULL,
            name_te    VARCHAR(200),
            name_hi    VARCHAR(200),
            state      VARCHAR(100) NOT NULL,
            code       VARCHAR(20),
            is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            UNIQUE (state, name)
        )
    """)
    _x("CREATE INDEX idx_districts_state ON districts(state, is_active)")

    # -----------------------------------------------------------------------
    # 2. municipalities  (depends on districts and constituencies)
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE municipalities (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            district_id     UUID         REFERENCES districts(id)      ON DELETE RESTRICT,
            constituency_id UUID         REFERENCES constituencies(id) ON DELETE RESTRICT,
            name            VARCHAR(200) NOT NULL,
            name_te         VARCHAR(200),
            name_hi         VARCHAR(200),
            type            VARCHAR(30)  NOT NULL
                            CHECK (type IN (
                                'municipality', 'municipal_corporation',
                                'gram_panchayat', 'nagar_panchayat'
                            )),
            is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
            sort_order      INTEGER      NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_municipalities_constituency ON municipalities(constituency_id, is_active)")
    _x("CREATE INDEX idx_municipalities_district     ON municipalities(district_id,     is_active)")

    # -----------------------------------------------------------------------
    # 3. villages  (depends on mandals)
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE villages (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            mandal_id   UUID         NOT NULL REFERENCES mandals(id) ON DELETE RESTRICT,
            name        VARCHAR(200) NOT NULL,
            name_te     VARCHAR(200),
            name_hi     VARCHAR(200),
            census_code VARCHAR(20),
            is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
            sort_order  INTEGER      NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_villages_mandal ON villages(mandal_id, is_active, sort_order)")
    _x("CREATE UNIQUE INDEX uq_villages_census_code ON villages(census_code) WHERE census_code IS NOT NULL")

    # -----------------------------------------------------------------------
    # 4. constituencies — add district_id FK (nullable for backwards-compat)
    # -----------------------------------------------------------------------
    _x("ALTER TABLE constituencies ADD COLUMN district_id UUID REFERENCES districts(id) ON DELETE RESTRICT")
    _x("CREATE INDEX idx_constituencies_district ON constituencies(district_id)")

    # -----------------------------------------------------------------------
    # 5. mandals — add district_id FK (nullable for backwards-compat)
    # -----------------------------------------------------------------------
    _x("ALTER TABLE mandals ADD COLUMN district_id UUID REFERENCES districts(id) ON DELETE RESTRICT")
    _x("CREATE INDEX idx_mandals_district ON mandals(district_id, is_active)")

    # -----------------------------------------------------------------------
    # 6. wards reshape — XOR: belongs to mandal OR municipality, never both/neither
    #
    #    Step a: make mandal_id nullable, add municipality_id
    #    Step b: add XOR check constraint
    #    Step c: replace UNIQUE (mandal_id, ward_number) with two partial uniques
    # -----------------------------------------------------------------------

    # Step a
    _x("ALTER TABLE wards ALTER COLUMN mandal_id DROP NOT NULL")
    _x("ALTER TABLE wards ADD COLUMN municipality_id UUID REFERENCES municipalities(id) ON DELETE RESTRICT")

    # Step b
    _x("""
        ALTER TABLE wards
          ADD CONSTRAINT chk_wards_mandal_xor_municipality CHECK (
              (mandal_id IS NOT NULL AND municipality_id IS NULL) OR
              (mandal_id IS NULL     AND municipality_id IS NOT NULL)
          )
    """)

    # Step c — drop the auto-named UNIQUE (mandal_id, ward_number) from 0001
    _x("""
        DO $$
        DECLARE
            v_constraint TEXT;
        BEGIN
            SELECT conname INTO v_constraint
            FROM pg_constraint
            WHERE conrelid = 'wards'::regclass
              AND contype  = 'u'
              AND pg_get_constraintdef(oid) LIKE '%(mandal_id, ward_number)%';

            IF v_constraint IS NOT NULL THEN
                EXECUTE format('ALTER TABLE wards DROP CONSTRAINT %I', v_constraint);
            END IF;
        END $$
    """)

    # Replace with two partial unique indexes
    _x("""
        CREATE UNIQUE INDEX uq_wards_mandal_ward_number
          ON wards(mandal_id, ward_number)
          WHERE mandal_id IS NOT NULL
    """)
    _x("""
        CREATE UNIQUE INDEX uq_wards_municipality_ward_number
          ON wards(municipality_id, ward_number)
          WHERE municipality_id IS NOT NULL
    """)
    _x("""
        CREATE INDEX idx_wards_municipality
          ON wards(municipality_id, is_active)
          WHERE municipality_id IS NOT NULL
    """)

    # -----------------------------------------------------------------------
    # 7. citizens — add structured village_id FK alongside free-text village
    # -----------------------------------------------------------------------
    _x("ALTER TABLE citizens ADD COLUMN village_id UUID REFERENCES villages(id) ON DELETE RESTRICT")
    _x("CREATE INDEX idx_citizens_village ON citizens(village_id)")


# ---------------------------------------------------------------------------
# downgrade — strict reverse order
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 1. Drop indexes added in this migration
    _x("DROP INDEX IF EXISTS idx_citizens_village")
    _x("DROP INDEX IF EXISTS idx_wards_municipality")
    _x("DROP INDEX IF EXISTS uq_wards_municipality_ward_number")
    _x("DROP INDEX IF EXISTS uq_wards_mandal_ward_number")
    _x("DROP INDEX IF EXISTS idx_mandals_district")
    _x("DROP INDEX IF EXISTS idx_constituencies_district")
    _x("DROP INDEX IF EXISTS idx_villages_mandal")
    _x("DROP INDEX IF EXISTS uq_villages_census_code")
    _x("DROP INDEX IF EXISTS idx_municipalities_constituency")
    _x("DROP INDEX IF EXISTS idx_municipalities_district")
    _x("DROP INDEX IF EXISTS idx_districts_state")

    # 2. Drop the XOR check constraint
    _x("ALTER TABLE wards DROP CONSTRAINT IF EXISTS chk_wards_mandal_xor_municipality")

    # 3. Recreate the original UNIQUE (mandal_id, ward_number) constraint
    _x("ALTER TABLE wards ADD CONSTRAINT wards_mandal_id_ward_number_key UNIQUE (mandal_id, ward_number)")

    # 4. Restore mandal_id NOT NULL (safe pre-data; fails if NULLs exist)
    _x("ALTER TABLE wards ALTER COLUMN mandal_id SET NOT NULL")

    # 5. Drop wards.municipality_id
    _x("ALTER TABLE wards DROP COLUMN IF EXISTS municipality_id")

    # 6. Drop citizens.village_id
    _x("ALTER TABLE citizens DROP COLUMN IF EXISTS village_id")

    # 7. Drop mandals.district_id
    _x("ALTER TABLE mandals DROP COLUMN IF EXISTS district_id")

    # 8. Drop constituencies.district_id
    _x("ALTER TABLE constituencies DROP COLUMN IF EXISTS district_id")

    # 9. Drop villages
    _x("DROP TABLE IF EXISTS villages")

    # 10. Drop municipalities
    _x("DROP TABLE IF EXISTS municipalities")

    # 11. Drop districts
    _x("DROP TABLE IF EXISTS districts")
