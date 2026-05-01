"""format catalogue seed — 3 categories, 14 subcategories, English-only labels

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-01

Seeds the canonical format catalogue from Doc C v2.1 §6.
No schema changes. Data only.
  3  complaint categories   (PUBLIC, PRIVATE, APPOINTMENT)
 14  complaint subcategories (PUB.WATER … APT.FLC)

All inserts are idempotent: NOT EXISTS keyed on stable UUIDs.
Label translations (label_te, label_hi) are English placeholders;
real translations land in a later migration after translator review.
"""

import hashlib
import json
import uuid as uuid_module

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


def stable_uuid(seed_str: str) -> str:
    """Deterministic UUID from a seed string. Reruns produce the same UUID."""
    h = hashlib.md5(seed_str.encode("utf-8")).hexdigest()
    return str(uuid_module.UUID(h))


def with_placeholder_translations(fields: list[dict]) -> list[dict]:
    """Fill label_te and label_hi with label_en for every field. Real translations land in a later migration."""
    out = []
    for f in fields:
        f2 = dict(f)
        f2["label_te"] = f["label_en"]
        f2["label_hi"] = f["label_en"]
        out.append(f2)
    return out


# ---------------------------------------------------------------------------
# stable UUID constants — categories
# ---------------------------------------------------------------------------

CATEGORY_PUBLIC_ID      = stable_uuid("category:public")
CATEGORY_PRIVATE_ID     = stable_uuid("category:private")
CATEGORY_APPOINTMENT_ID = stable_uuid("category:appointment")

# ---------------------------------------------------------------------------
# stable UUID constants — subcategories
# ---------------------------------------------------------------------------

SUBCAT_PUB_WATER_ID = stable_uuid("subcategory:pub:water")
SUBCAT_PUB_ELEC_ID  = stable_uuid("subcategory:pub:elec")
SUBCAT_PUB_SANI_ID  = stable_uuid("subcategory:pub:sani")
SUBCAT_PUB_RNB_ID   = stable_uuid("subcategory:pub:rnb")
SUBCAT_PUB_OTH_ID   = stable_uuid("subcategory:pub:oth")
SUBCAT_PRV_POL_ID   = stable_uuid("subcategory:prv:pol")
SUBCAT_PRV_REV_ID   = stable_uuid("subcategory:prv:rev")
SUBCAT_PRV_WEL_ID   = stable_uuid("subcategory:prv:wel")
SUBCAT_PRV_MED_ID   = stable_uuid("subcategory:prv:med")
SUBCAT_PRV_EDU_ID   = stable_uuid("subcategory:prv:edu")
SUBCAT_PRV_OTH_ID   = stable_uuid("subcategory:prv:oth")
SUBCAT_APT_MEET_ID  = stable_uuid("subcategory:apt:meet")
SUBCAT_APT_EVT_ID   = stable_uuid("subcategory:apt:evt")
SUBCAT_APT_FLC_ID   = stable_uuid("subcategory:apt:flc")


# ---------------------------------------------------------------------------
# required_fields constants
# ---------------------------------------------------------------------------

PUB_WATER_FIELDS = [
    {"name": "issue_type", "type": "enum", "required": True, "options": ["no_supply", "contamination", "pipeline_break", "borewell", "new_connection"], "label_en": "Issue type"},
    {"name": "exact_location", "type": "string", "required": True, "label_en": "Exact location (village, ward, street)"},
    {"name": "duration_days", "type": "integer", "required": True, "validation_hint": "min=1", "label_en": "Duration (days)"},
    {"name": "households_affected", "type": "integer", "required": True, "validation_hint": "min=1", "label_en": "Households affected"},
    {"name": "previous_complaint_ref", "type": "string", "required": False, "label_en": "Previous complaint reference (if any)"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PUB_ELEC_FIELDS = [
    {"name": "issue_type", "type": "enum", "required": True, "options": ["power_cut", "transformer_fault", "streetlight", "billing_dispute", "new_connection"], "label_en": "Issue type"},
    {"name": "exact_location", "type": "string", "required": True, "label_en": "Exact location"},
    {"name": "duration_days", "type": "integer", "required": True, "validation_hint": "min=1", "label_en": "Duration (days)"},
    {"name": "households_affected", "type": "integer", "required": True, "validation_hint": "min=1", "label_en": "Households affected"},
    {"name": "discom_complaint_ref", "type": "string", "required": False, "label_en": "DISCOM complaint reference (if any)"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PUB_SANI_FIELDS = [
    {"name": "issue_type", "type": "enum", "required": True, "options": ["drainage_overflow", "garbage_not_collected", "open_sewage", "public_toilet_condition"], "label_en": "Issue type"},
    {"name": "exact_location", "type": "string", "required": True, "label_en": "Exact location"},
    {"name": "duration_days", "type": "integer", "required": True, "validation_hint": "min=1", "label_en": "Duration (days)"},
    {"name": "scale_of_impact", "type": "enum", "required": True, "options": ["street_level", "ward_level", "area_wide"], "label_en": "Scale of impact"},
    {"name": "photo_evidence", "type": "media", "required": False, "label_en": "Photo evidence"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PUB_RNB_FIELDS = [
    {"name": "issue_type", "type": "enum", "required": True, "options": ["road_damage", "pothole", "bridge_condition", "govt_building_repair", "drainage_on_road"], "label_en": "Issue type"},
    {"name": "exact_location", "type": "string", "required": True, "label_en": "Exact location"},
    {"name": "severity", "type": "enum", "required": True, "options": ["minor", "moderate", "dangerous"], "label_en": "Severity"},
    {"name": "duration_days", "type": "integer", "required": True, "validation_hint": "min=1", "label_en": "Duration (days)"},
    {"name": "photo_evidence", "type": "media", "required": False, "label_en": "Photo evidence"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PUB_OTH_FIELDS = [
    {"name": "brief_title", "type": "string", "required": True, "validation_hint": "min_length=5,max_length=100", "label_en": "Brief title"},
    {"name": "department_concerned", "type": "string", "required": False, "label_en": "Department concerned (if known)"},
    {"name": "exact_location", "type": "string", "required": True, "label_en": "Exact location"},
    {"name": "urgency_level", "type": "enum", "required": True, "options": ["low", "medium", "high", "emergency"], "label_en": "Urgency level"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
    {"name": "photo_evidence", "type": "media", "required": False, "label_en": "Photo evidence"},
]

PRV_POL_FIELDS = [
    {"name": "nature_of_issue", "type": "enum", "required": True, "options": ["fir_not_registered", "harassment", "false_case", "property_dispute", "threat", "other"], "label_en": "Nature of issue"},
    {"name": "incident_date", "type": "date", "required": True, "label_en": "Incident date"},
    {"name": "police_station", "type": "string", "required": True, "label_en": "Police station"},
    {"name": "fir_number", "type": "string", "required": False, "label_en": "FIR number (NA if none)"},
    {"name": "parties_involved", "type": "free_text", "required": True, "validation_hint": "min_length=5", "label_en": "Parties involved"},
    {"name": "urgency_level", "type": "enum", "required": True, "options": ["normal", "urgent", "emergency"], "label_en": "Urgency level"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PRV_REV_FIELDS = [
    {"name": "issue_type", "type": "enum", "required": True, "options": ["patta", "land_mutation", "encroachment", "survey", "property_tax", "pahani"], "label_en": "Issue type"},
    {"name": "survey_or_plot_number", "type": "string", "required": False, "label_en": "Survey or plot number"},
    {"name": "village_mandal_text", "type": "string", "required": True, "label_en": "Village or mandal"},
    {"name": "status_of_issue", "type": "enum", "required": True, "options": ["fresh_request", "pending", "rejected"], "label_en": "Status of issue"},
    {"name": "relevant_documents", "type": "media", "required": False, "label_en": "Relevant documents"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PRV_WEL_FIELDS = [
    {"name": "welfare_category", "type": "enum", "required": True, "options": ["pension", "housing", "ration_card", "caste_certificate", "women_scheme", "sc_st_scheme", "other"], "label_en": "Welfare category"},
    {"name": "scheme_name", "type": "string", "required": False, "label_en": "Scheme name"},
    {"name": "issue_type", "type": "enum", "required": True, "options": ["new_application", "application_pending", "application_rejected", "amount_not_received"], "label_en": "Issue type"},
    {"name": "application_number", "type": "string", "required": False, "label_en": "Application number"},
    {"name": "pending_duration", "type": "string", "required": True, "label_en": "Pending duration (days or months)"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PRV_MED_FIELDS = [
    {"name": "patient_name", "type": "string", "required": True, "label_en": "Patient name"},
    {"name": "patient_age", "type": "integer", "required": True, "validation_hint": "min=0,max=120", "label_en": "Patient age"},
    {"name": "relation_to_caller", "type": "enum", "required": True, "options": ["self", "family_member", "neighbour"], "label_en": "Relation to caller"},
    {"name": "nature_of_emergency", "type": "enum", "required": True, "options": ["accident", "critical_illness", "hospitalization_support", "financial_aid_for_treatment"], "label_en": "Nature of emergency"},
    {"name": "current_location_or_hospital", "type": "string", "required": True, "label_en": "Current location or hospital"},
    {"name": "urgency_level", "type": "enum", "required": True, "options": ["urgent", "very_urgent", "life_threatening"], "label_en": "Urgency level"},
    {"name": "financial_assistance_needed", "type": "yes_no", "required": True, "label_en": "Financial assistance needed"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PRV_EDU_FIELDS = [
    {"name": "institution_name", "type": "string", "required": True, "label_en": "Institution name"},
    {"name": "issue_type", "type": "enum", "required": True, "options": ["admission", "scholarship", "fee_reimbursement", "infrastructure", "teacher_shortage", "tc", "other"], "label_en": "Issue type"},
    {"name": "student_name", "type": "string", "required": True, "label_en": "Student name"},
    {"name": "class_or_course", "type": "string", "required": True, "label_en": "Class or course"},
    {"name": "status", "type": "enum", "required": True, "options": ["fresh_request", "pending", "rejected"], "label_en": "Status"},
    {"name": "reference_number", "type": "string", "required": False, "label_en": "Reference number"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

PRV_OTH_FIELDS = [
    {"name": "brief_title", "type": "string", "required": True, "validation_hint": "min_length=5,max_length=100", "label_en": "Brief title"},
    {"name": "nature_of_issue", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Nature of issue"},
    {"name": "urgency_level", "type": "enum", "required": True, "options": ["low", "medium", "high", "emergency"], "label_en": "Urgency level"},
    {"name": "relevant_documents", "type": "media", "required": False, "label_en": "Relevant documents"},
    {"name": "description", "type": "free_text", "required": True, "validation_hint": "min_length=10", "label_en": "Description"},
]

# Shared by APT.MEET, APT.EVT, APT.FLC per Doc C §6.14
APPOINTMENT_FIELDS = [
    {"name": "type", "type": "enum", "required": True, "options": ["meeting", "event_invitation", "felicitation", "programme"], "label_en": "Type"},
    {"name": "organisation_or_individual_name", "type": "string", "required": True, "label_en": "Organisation or individual name"},
    {"name": "purpose_or_occasion", "type": "free_text", "required": True, "validation_hint": "min_length=5", "label_en": "Purpose or occasion"},
    {"name": "preferred_date", "type": "date", "required": True, "label_en": "Preferred date"},
    {"name": "preferred_time", "type": "string", "required": True, "label_en": "Preferred time (HH:MM)"},
    {"name": "venue_or_location", "type": "string", "required": True, "label_en": "Venue or location"},
    {"name": "expected_attendees", "type": "integer", "required": False, "validation_hint": "min=0", "label_en": "Expected attendees"},
    {"name": "contact_person_name", "type": "string", "required": True, "label_en": "Contact person name"},
    {"name": "contact_person_number", "type": "phone", "required": True, "label_en": "Contact person number"},
    {"name": "additional_notes", "type": "free_text", "required": False, "label_en": "Additional notes"},
]


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. complaint_categories — 3 rows
    #    required_fields is an empty jsonb array; field definitions live on subcategories.
    #    parent_group mirrors the code for top-level grouping.
    # -----------------------------------------------------------------------
    _categories = [
        # (id, code, display_name_en, default_routing_queue, sort_order)
        (CATEGORY_PUBLIC_ID,      "PUBLIC",      "Public Issue",  "public_issues",  1),
        (CATEGORY_PRIVATE_ID,     "PRIVATE",     "Private Issue", "private_issues", 2),
        (CATEGORY_APPOINTMENT_ID, "APPOINTMENT", "Appointment",   "appointments",   3),
    ]
    for cat_id, code, display_name_en, routing_queue, sort in _categories:
        _x(f"""
            INSERT INTO complaint_categories (
                id, code, parent_group,
                display_name_en, display_name_te, display_name_hi,
                default_routing_queue, is_active, sort_order, required_fields
            )
            SELECT
                '{cat_id}',
                '{code}',
                '{code}',
                '{display_name_en}',
                '{display_name_en}',
                '{display_name_en}',
                '{routing_queue}',
                TRUE,
                {sort},
                '[]'::jsonb
            WHERE NOT EXISTS (
                SELECT 1 FROM complaint_categories WHERE id = '{cat_id}'
            )
        """)

    # -----------------------------------------------------------------------
    # 2. complaint_subcategories — 14 rows
    #    category_id is a UUID FK referencing complaint_categories.id.
    #    required_fields uses parameterised binding to avoid quoting issues.
    # -----------------------------------------------------------------------
    _subcategories = [
        # (id, code, category_id, display_name_en, ticket_id_prefix, sla_hours, sort_order, fields)
        (SUBCAT_PUB_WATER_ID, "PUB.WATER", CATEGORY_PUBLIC_ID,      "Water",            "PUB-WTR",  72,  1, PUB_WATER_FIELDS),
        (SUBCAT_PUB_ELEC_ID,  "PUB.ELEC",  CATEGORY_PUBLIC_ID,      "Electricity",      "PUB-ELC",  48,  2, PUB_ELEC_FIELDS),
        (SUBCAT_PUB_SANI_ID,  "PUB.SANI",  CATEGORY_PUBLIC_ID,      "Sanitation",       "PUB-SAN",  72,  3, PUB_SANI_FIELDS),
        (SUBCAT_PUB_RNB_ID,   "PUB.RNB",   CATEGORY_PUBLIC_ID,      "Roads & Buildings","PUB-RNB",  96,  4, PUB_RNB_FIELDS),
        (SUBCAT_PUB_OTH_ID,   "PUB.OTH",   CATEGORY_PUBLIC_ID,      "Public Others",    "PUB-OTH",  96,  5, PUB_OTH_FIELDS),
        (SUBCAT_PRV_POL_ID,   "PRV.POL",   CATEGORY_PRIVATE_ID,     "Police",           "PRV-POL",  48,  1, PRV_POL_FIELDS),
        (SUBCAT_PRV_REV_ID,   "PRV.REV",   CATEGORY_PRIVATE_ID,     "Revenue",          "PRV-REV",  168, 2, PRV_REV_FIELDS),
        (SUBCAT_PRV_WEL_ID,   "PRV.WEL",   CATEGORY_PRIVATE_ID,     "Welfare",          "PRV-WEL",  120, 3, PRV_WEL_FIELDS),
        (SUBCAT_PRV_MED_ID,   "PRV.MED",   CATEGORY_PRIVATE_ID,     "Medical",          "PRV-MED",  24,  4, PRV_MED_FIELDS),
        (SUBCAT_PRV_EDU_ID,   "PRV.EDU",   CATEGORY_PRIVATE_ID,     "Education",        "PRV-EDU",  120, 5, PRV_EDU_FIELDS),
        (SUBCAT_PRV_OTH_ID,   "PRV.OTH",   CATEGORY_PRIVATE_ID,     "Private Others",   "PRV-OTH",  120, 6, PRV_OTH_FIELDS),
        (SUBCAT_APT_MEET_ID,  "APT.MEET",  CATEGORY_APPOINTMENT_ID, "Meeting",          "APT-MTG",  48,  1, APPOINTMENT_FIELDS),
        (SUBCAT_APT_EVT_ID,   "APT.EVT",   CATEGORY_APPOINTMENT_ID, "Event",            "APT-EVT",  48,  2, APPOINTMENT_FIELDS),
        (SUBCAT_APT_FLC_ID,   "APT.FLC",   CATEGORY_APPOINTMENT_ID, "Felicitation",     "APT-FLC",  48,  3, APPOINTMENT_FIELDS),
    ]
    for subcat_id, code, cat_id, display_name_en, prefix, sla, sort, fields in _subcategories:
        fields_json = json.dumps(with_placeholder_translations(fields))
        _x(f"""
            INSERT INTO complaint_subcategories (
                id, category_id, code,
                display_name_en, display_name_te, display_name_hi,
                ticket_id_prefix, sla_hours, is_active, sort_order, required_fields
            )
            SELECT
                '{subcat_id}',
                '{cat_id}',
                '{code}',
                '{display_name_en}',
                '{display_name_en}',
                '{display_name_en}',
                '{prefix}',
                {sla},
                TRUE,
                {sort},
                '{fields_json}'::jsonb
            WHERE NOT EXISTS (
                SELECT 1 FROM complaint_subcategories WHERE id = '{subcat_id}'
            )
        """)


# ---------------------------------------------------------------------------
# downgrade — delete in reverse FK dependency order
# ---------------------------------------------------------------------------


def downgrade() -> None:
    _subcat_ids = ", ".join(f"'{sid}'" for sid in [
        SUBCAT_PUB_WATER_ID, SUBCAT_PUB_ELEC_ID, SUBCAT_PUB_SANI_ID,
        SUBCAT_PUB_RNB_ID,   SUBCAT_PUB_OTH_ID,
        SUBCAT_PRV_POL_ID,   SUBCAT_PRV_REV_ID,  SUBCAT_PRV_WEL_ID,
        SUBCAT_PRV_MED_ID,   SUBCAT_PRV_EDU_ID,  SUBCAT_PRV_OTH_ID,
        SUBCAT_APT_MEET_ID,  SUBCAT_APT_EVT_ID,  SUBCAT_APT_FLC_ID,
    ])
    _x(f"DELETE FROM complaint_subcategories WHERE id IN ({_subcat_ids})")

    _cat_ids = ", ".join(f"'{cid}'" for cid in [
        CATEGORY_PUBLIC_ID, CATEGORY_PRIVATE_ID, CATEGORY_APPOINTMENT_ID,
    ])
    _x(f"DELETE FROM complaint_categories WHERE id IN ({_cat_ids})")
