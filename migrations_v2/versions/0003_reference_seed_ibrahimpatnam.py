"""reference data seed — Ibrahimpatnam constituency

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-01

Seeds reference data for Ibrahimpatnam constituency in Ranga Reddy district,
Telangana state.  Rows created:
  1  district  (Ranga Reddy)
  1  constituency  (Ibrahimpatnam)
  4  mandals  (Abdullapurmet, Ibrahimpatnam, Manchal, Yacharam)
  1  municipality  (Ibrahimpatnam Municipality)
 20  villages  (5 per mandal)
 30  wards  (Ward 1–30, all under Ibrahimpatnam Municipality)

All inserts are idempotent: ON CONFLICT DO NOTHING for tables with natural
unique keys; NOT EXISTS keyed on stable UUIDs for the rest.
"""

import hashlib
import uuid as uuid_module

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


def stable_uuid(seed_str: str) -> str:
    """Deterministic UUID from a seed string.  Reruns produce the same UUID."""
    h = hashlib.md5(seed_str.encode("utf-8")).hexdigest()
    return str(uuid_module.UUID(h))


# ---------------------------------------------------------------------------
# stable UUID constants
# ---------------------------------------------------------------------------

DISTRICT_ID = stable_uuid("district:telangana:ranga_reddy")
CONSTITUENCY_ID = stable_uuid("constituency:telangana:ibrahimpatnam")

MANDAL_ABDULLAPURMET_ID = stable_uuid("mandal:telangana:ranga_reddy:abdullapurmet")
MANDAL_IBRAHIMPATNAM_ID = stable_uuid("mandal:telangana:ranga_reddy:ibrahimpatnam")
MANDAL_MANCHAL_ID       = stable_uuid("mandal:telangana:ranga_reddy:manchal")
MANDAL_YACHARAM_ID      = stable_uuid("mandal:telangana:ranga_reddy:yacharam")

MUNICIPALITY_IBRAHIMPATNAM_ID = stable_uuid("municipality:telangana:ranga_reddy:ibrahimpatnam")

# Villages: 5 per mandal, keyed by (mandal_slug, 1-based index)
_MANDAL_SLUGS = [
    ("abdullapurmet", MANDAL_ABDULLAPURMET_ID),
    ("ibrahimpatnam", MANDAL_IBRAHIMPATNAM_ID),
    ("manchal",       MANDAL_MANCHAL_ID),
    ("yacharam",      MANDAL_YACHARAM_ID),
]
VILLAGE_IDS = {
    (slug, n): stable_uuid(f"village:{slug}:{n}")
    for slug, _ in _MANDAL_SLUGS
    for n in range(1, 6)
}

# Wards: 30 under Ibrahimpatnam Municipality
WARD_IDS = {n: stable_uuid(f"ward:ibrahimpatnam_municipality:{n}") for n in range(1, 31)}


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. districts — Ranga Reddy
    #    UNIQUE (state, name) exists so ON CONFLICT DO NOTHING is safe.
    # -----------------------------------------------------------------------
    _x(f"""
        INSERT INTO districts (id, name, name_te, name_hi, state, code, is_active)
        VALUES (
            '{DISTRICT_ID}',
            'Ranga Reddy',
            'రంగారెడ్డి',
            'रंगारेड्डी',
            'Telangana',
            'TG-RR',
            TRUE
        )
        ON CONFLICT (state, name) DO NOTHING
    """)

    # -----------------------------------------------------------------------
    # 2. constituencies — Ibrahimpatnam
    #    No natural unique key; use NOT EXISTS keyed on stable id.
    # -----------------------------------------------------------------------
    _x(f"""
        INSERT INTO constituencies (id, district_id, name, name_te, name_hi, state, is_active)
        SELECT
            '{CONSTITUENCY_ID}',
            '{DISTRICT_ID}',
            'Ibrahimpatnam',
            'ఇబ్రహీంపట్నం',
            'इब्राहिमपटनम',
            'Telangana',
            TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM constituencies WHERE id = '{CONSTITUENCY_ID}'
        )
    """)

    # -----------------------------------------------------------------------
    # 3. mandals — 4 mandals
    #    No natural unique key; use NOT EXISTS keyed on stable id.
    # -----------------------------------------------------------------------
    _mandals = [
        (MANDAL_ABDULLAPURMET_ID, "Abdullapurmet", "అబ్దుల్లాపూర్మెట్", 1),
        (MANDAL_IBRAHIMPATNAM_ID, "Ibrahimpatnam", "ఇబ్రహీంపట్నం",     2),
        (MANDAL_MANCHAL_ID,       "Manchal",        "మంచాల్",             3),
        (MANDAL_YACHARAM_ID,      "Yacharam",       "యాచారం",             4),
    ]
    for mid, name, name_te, sort in _mandals:
        _x(f"""
            INSERT INTO mandals
                (id, district_id, constituency_id, name, name_te, sort_order, is_active)
            SELECT
                '{mid}',
                '{DISTRICT_ID}',
                '{CONSTITUENCY_ID}',
                '{name}',
                '{name_te}',
                {sort},
                TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM mandals WHERE id = '{mid}'
            )
        """)

    # -----------------------------------------------------------------------
    # 4. municipalities — Ibrahimpatnam Municipality
    #    No natural unique key; use NOT EXISTS keyed on stable id.
    # -----------------------------------------------------------------------
    _x(f"""
        INSERT INTO municipalities
            (id, district_id, constituency_id, name, name_te, name_hi, type, sort_order, is_active)
        SELECT
            '{MUNICIPALITY_IBRAHIMPATNAM_ID}',
            '{DISTRICT_ID}',
            '{CONSTITUENCY_ID}',
            'Ibrahimpatnam Municipality',
            'ఇబ్రహీంపట్నం పురపాలక సంఘం',
            NULL,
            'municipality',
            1,
            TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM municipalities WHERE id = '{MUNICIPALITY_IBRAHIMPATNAM_ID}'
        )
    """)

    # -----------------------------------------------------------------------
    # 5. villages — 5 per mandal, 20 total
    #    No natural unique key; use NOT EXISTS keyed on stable id.
    # -----------------------------------------------------------------------
    for slug, mandal_id in _MANDAL_SLUGS:
        for n in range(1, 6):
            vid = VILLAGE_IDS[(slug, n)]
            _x(f"""
                INSERT INTO villages
                    (id, mandal_id, name, name_te, name_hi, census_code, sort_order, is_active)
                SELECT
                    '{vid}',
                    '{mandal_id}',
                    'Village {n}',
                    NULL,
                    NULL,
                    NULL,
                    {n},
                    TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM villages WHERE id = '{vid}'
                )
            """)

    # -----------------------------------------------------------------------
    # 6. wards — Ward 1–30, all under Ibrahimpatnam Municipality
    #    mandal_id is NULL (municipality-based ward, satisfies XOR constraint).
    #    No natural unique key; use NOT EXISTS keyed on stable id.
    # -----------------------------------------------------------------------
    for n in range(1, 31):
        wid = WARD_IDS[n]
        _x(f"""
            INSERT INTO wards
                (id, mandal_id, municipality_id, ward_number, ward_name,
                 centroid_lat, centroid_lng, is_active)
            SELECT
                '{wid}',
                NULL,
                '{MUNICIPALITY_IBRAHIMPATNAM_ID}',
                {n},
                'Ward {n}',
                NULL,
                NULL,
                TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM wards WHERE id = '{wid}'
            )
        """)


# ---------------------------------------------------------------------------
# downgrade — delete in reverse FK dependency order
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # wards
    _ward_ids = ", ".join(f"'{WARD_IDS[n]}'" for n in range(1, 31))
    _x(f"DELETE FROM wards WHERE id IN ({_ward_ids})")

    # villages
    _village_ids = ", ".join(
        f"'{VILLAGE_IDS[(slug, n)]}'"
        for slug, _ in _MANDAL_SLUGS
        for n in range(1, 6)
    )
    _x(f"DELETE FROM villages WHERE id IN ({_village_ids})")

    # municipality
    _x(f"DELETE FROM municipalities WHERE id = '{MUNICIPALITY_IBRAHIMPATNAM_ID}'")

    # mandals
    _mandal_ids = ", ".join(
        f"'{mid}'"
        for mid in [
            MANDAL_ABDULLAPURMET_ID,
            MANDAL_IBRAHIMPATNAM_ID,
            MANDAL_MANCHAL_ID,
            MANDAL_YACHARAM_ID,
        ]
    )
    _x(f"DELETE FROM mandals WHERE id IN ({_mandal_ids})")

    # constituency
    _x(f"DELETE FROM constituencies WHERE id = '{CONSTITUENCY_ID}'")

    # district
    _x(f"DELETE FROM districts WHERE id = '{DISTRICT_ID}'")
