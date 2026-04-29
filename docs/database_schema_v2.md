# Constituency OS — Database Schema V2

**Purpose:** Full database schema needed to implement `intake_spec_v1.md` and `state_machine_v2.md`. Defines new tables, extensions to existing tables, indexes, and seed data.

**Reading order:** read intake spec and state machine first. This doc is the storage layer those two reference.

**Migration discipline:**
- Every schema change is a numbered Alembic migration
- Migrations are forward-only (no destructive rollbacks for prototype; we recreate dev DB if needed)
- Seed data lives in a separate seed script, not in migrations
- Existing V0/V1 tables are extended, not replaced — backward compatibility maintained

---

## Existing tables (V0/V1) — kept, with extensions

These tables already exist. V1.8 only ADDS columns; never removes.

### `offices` (already exists)

No changes. Office_id = 1 for prototype.

### `citizens` (extend)

Existing columns kept: `id`, `office_id`, `telegram_chat_id`, `name`, `mobile`, `ward`, `created_at`, `updated_at`.

**Add:**
| Column | Type | Default | Notes |
|---|---|---|---|
| `dob` | DATE | NULL | citizen's date of birth |
| `voter_id` | VARCHAR(20) | NULL | EPIC format, optional |
| `voter_id_skipped_at` | TIMESTAMPTZ | NULL | set when citizen skips voter_id during registration |
| `voter_id_skip_acknowledged` | BOOLEAN | FALSE | TRUE after 2nd skip during welfare flow — never re-prompted |
| `mandal` | VARCHAR(120) | NULL | from seeded mandal list |
| `village_or_ward_name` | VARCHAR(120) | NULL | free text label |
| `ward_number` | INTEGER | NULL | from seeded ward list (or free-text fallback) |
| `ward_review_required` | BOOLEAN | FALSE | TRUE if ward_number was free-text fallback |
| `geo_lat` | NUMERIC(9,6) | NULL | citizen's location |
| `geo_lng` | NUMERIC(9,6) | NULL | citizen's location |
| `geo_is_approximate` | BOOLEAN | FALSE | TRUE if ward centroid used as fallback |
| `preferred_language` | VARCHAR(8) | NULL | 'en', 'te', 'hi', 'mixed' |
| `registration_complete` | BOOLEAN | FALSE | TRUE only after `s2_register_done` reached |
| `last_active_at` | TIMESTAMPTZ | NULL | updated on every inbound message |

**Indexes:**
- existing: `idx_citizens_telegram_chat_id` (already exists, unique)
- new: `idx_citizens_mobile` (for dedup checks)
- new: `idx_citizens_office_ward` on `(office_id, ward_number)` (for clustering queries by Dashboard)

### `tickets` (extend)

Existing columns kept: `id`, `office_id`, `citizen_id`, `status`, `created_at`, `updated_at`.

**Add:**
| Column | Type | Default | Notes |
|---|---|---|---|
| `ticket_id_human` | VARCHAR(40) | NOT NULL | format `[CATEGORY-CODE]-[DDMMYY]-[SEQUENCE]` e.g. `PUB-WTR-280426-0042` |
| `category_code` | VARCHAR(8) | NOT NULL | one of 14 codes — `PUB-WTR`, `PUB-ELC`, `PRV-POL`, `APT-MTG`, etc. |
| `severity_or_urgency` | VARCHAR(40) | NULL | per-subcategory urgency or severity value |
| `location_text` | TEXT | NULL | citizen-provided exact location |
| `complaint_geo_lat` | NUMERIC(9,6) | NULL | optional, may differ from citizen.geo_lat |
| `complaint_geo_lng` | NUMERIC(9,6) | NULL | optional |
| `assigned_queue` | VARCHAR(40) | NOT NULL | resolved from `complaint_categories.default_routing_queue` at ticket-creation time |
| `assigned_officer_id` | INTEGER | NULL | FK to `officer_mappings.id` once Department agent assigns |
| `requires_review` | BOOLEAN | FALSE | TRUE for free-text-ward tickets, others-uncategorised, etc. |
| `media_file_ids` | JSONB | '[]' | array of telegram file_id strings for photos/docs |
| `language_at_creation` | VARCHAR(8) | NULL | snapshot of citizen's language when ticket created |

**Indexes:**
- new: `idx_tickets_human_id` unique on `ticket_id_human`
- new: `idx_tickets_office_status_created` on `(office_id, status, created_at)`
- new: `idx_tickets_category_code_created` on `(category_code, created_at)`
- new: `idx_tickets_citizen_status` on `(citizen_id, status)`

**Status values (extend if not already present):**
`draft`, `open`, `routed`, `acknowledged`, `in_progress`, `awaiting_citizen`, `resolved`, `closed`, `cancelled`, `escalated`

### `agent_actions` (no schema change)

Already in place from V0. Continue using existing shape:
`agent_name`, `action_type`, `payload (JSONB)`, `idempotency_key`, `office_id`, `created_at`, etc.

V1.8 adds new `action_type` values used:
- `state.transition` — state machine moved
- `field.collected` — single field value saved to draft
- `ticket.draft.created`
- `ticket.draft.updated`
- `ticket.created`
- `ticket.discarded`
- `registration.completed`
- `registration.partial.saved`
- `voter_id.skipped`
- `fix_field.invoked`
- `session.resumed`
- `escalation.handoff` — when "Talk to Office" is tapped

### `agent_alerts` (no schema change for V1.8)

Existing schema fine. Dashboard agent will write here in phase 4 (later).

### `officer_mappings` (extend)

Existing: officer contact + ward + department.

**Add:**
| Column | Type | Default | Notes |
|---|---|---|---|
| `queue_name` | VARCHAR(40) | NOT NULL | logical queue this officer belongs to: `pa_inbox`, `water_dept`, `electricity_dept`, `sanitation_dept`, `rnb_dept`, `revenue_dept`, `welfare_dept`, `police_liaison`, `medical_liaison`, `education_liaison`, `general_dept` |
| `is_default_for_queue` | BOOLEAN | FALSE | TRUE for primary officer of that queue in that office |
| `language_preference` | VARCHAR(8) | NULL | for officer_message drafting later |

**Indexes:**
- new: `idx_officer_queue_office` on `(office_id, queue_name, is_default_for_queue)`

---

## New tables (V1.8)

### `complaint_categories`

The 14-code taxonomy. Seed data fills this. Code reads from this; not hardcoded anywhere.

```sql
CREATE TABLE complaint_categories (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(8) NOT NULL UNIQUE,        -- 'PUB-WTR'
    parent_group    VARCHAR(20) NOT NULL,              -- 'public' | 'private' | 'appointment'
    display_name_en VARCHAR(120) NOT NULL,             -- 'Public — Water'
    display_name_te VARCHAR(120),                      -- Telugu
    display_name_hi VARCHAR(120),                      -- Hindi
    icon_emoji      VARCHAR(10),                       -- '🔵', '🟠', '📅'
    default_routing_queue VARCHAR(40) NOT NULL,        -- 'water_dept', 'pa_inbox', etc.
    requires_geo    BOOLEAN NOT NULL DEFAULT FALSE,
    requires_photo  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_complaint_categories_active ON complaint_categories (is_active, sort_order);
CREATE INDEX idx_complaint_categories_parent ON complaint_categories (parent_group, is_active);
```

**Seed data — 14 rows:**

| code | parent_group | display_name_en | default_routing_queue | sort_order |
|---|---|---|---|---|
| PUB-WTR | public | Public — Water | water_dept | 10 |
| PUB-ELC | public | Public — Electricity | electricity_dept | 20 |
| PUB-SAN | public | Public — Sanitation | sanitation_dept | 30 |
| PUB-RNB | public | Public — Roads & Buildings | rnb_dept | 40 |
| PUB-OTH | public | Public — Others | pa_inbox | 50 |
| PRV-POL | private | Private — Police | police_liaison | 60 |
| PRV-REV | private | Private — Revenue | revenue_dept | 70 |
| PRV-WEL | private | Private — Welfare | welfare_dept | 80 |
| PRV-MED | private | Private — Medical | medical_liaison | 90 |
| PRV-EDU | private | Private — Education | education_liaison | 100 |
| PRV-OTH | private | Private — Others | pa_inbox | 110 |
| APT-MTG | appointment | Appointment — Meeting Request | pa_inbox | 120 |
| APT-EVT | appointment | Appointment — Event Invitation | pa_inbox | 130 |
| APT-FEL | appointment | Appointment — Felicitation/Programme | pa_inbox | 140 |

### `mandals`

Seeded list of mandals/municipalities for the office's constituency.

```sql
CREATE TABLE mandals (
    id          SERIAL PRIMARY KEY,
    office_id   INTEGER NOT NULL REFERENCES offices(id),
    name        VARCHAR(120) NOT NULL,
    name_te     VARCHAR(120),
    name_hi     VARCHAR(120),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, name)
);

CREATE INDEX idx_mandals_office_active ON mandals (office_id, is_active, sort_order);
```

**Seed data:** depends on which test constituency you pick. For prototype, seed 5-10 mandals you'll actually use. If you don't have real ones yet, seed placeholders: `Test_Mandal_1`, `Test_Mandal_2` — flag for replacement before any real demo.

### `wards`

Seeded list of wards within each mandal.

```sql
CREATE TABLE wards (
    id              SERIAL PRIMARY KEY,
    office_id       INTEGER NOT NULL REFERENCES offices(id),
    mandal_id       INTEGER NOT NULL REFERENCES mandals(id),
    ward_number     INTEGER NOT NULL,
    ward_name       VARCHAR(120),                       -- e.g. 'Madhapur'
    centroid_lat    NUMERIC(9,6) NOT NULL,              -- for geo fallback
    centroid_lng    NUMERIC(9,6) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, mandal_id, ward_number)
);

CREATE INDEX idx_wards_office_mandal ON wards (office_id, mandal_id, ward_number);
```

**Seed data:** 30-100 wards across the seeded mandals, each with centroid coordinates. Centroids matter — they're the geo fallback when citizens skip location share.

### `citizen_conversations`

The state-machine state-holder. One row per `(office_id, citizen_id, telegram_chat_id)`.

```sql
CREATE TABLE citizen_conversations (
    id                  SERIAL PRIMARY KEY,
    office_id           INTEGER NOT NULL REFERENCES offices(id),
    citizen_id          INTEGER REFERENCES citizens(id),       -- NULL until citizen registered
    telegram_chat_id    VARCHAR(40) NOT NULL,
    current_state       VARCHAR(80) NOT NULL,                  -- e.g. 's2_register_dob'
    return_to_state     VARCHAR(80),                           -- for s_fix_field flows
    draft_ticket_id     UUID,                                  -- in-progress complaint draft
    draft_payload       JSONB NOT NULL DEFAULT '{}'::jsonb,    -- accumulated complaint fields
    last_inbound_at     TIMESTAMPTZ,
    last_state_change_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalid_attempts_in_state INTEGER NOT NULL DEFAULT 0,      -- resets on transition
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, telegram_chat_id)
);

CREATE INDEX idx_conv_office_chat ON citizen_conversations (office_id, telegram_chat_id);
CREATE INDEX idx_conv_state_active ON citizen_conversations (current_state, last_inbound_at);
```

**Notes:**
- One conversation per chat_id, not per citizen — handles unregistered first-time visits
- `draft_payload` accumulates fields in JSONB during the complaint flow; flushed to `tickets` + `ticket_custom_fields` on confirmation
- `invalid_attempts_in_state` is the counter used for the "3 invalid attempts → offer Talk to Office" rule

### `ticket_custom_fields`

Per-subcategory fields stored as key-value rows. Decoupled from tickets so adding new subcategories doesn't require schema changes.

```sql
CREATE TABLE ticket_custom_fields (
    id          SERIAL PRIMARY KEY,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    field_name  VARCHAR(80) NOT NULL,
    field_value TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticket_id, field_name)
);

CREATE INDEX idx_tcf_ticket ON ticket_custom_fields (ticket_id);
CREATE INDEX idx_tcf_field_name ON ticket_custom_fields (field_name);
```

**Note:** alternative shape — store everything as JSONB on `tickets.custom_fields_json`. Reason for going row-per-field instead: easier to filter ("all tickets where `households_affected > 100`") and easier for Dashboard agent's clustering queries later. Trade-off accepted.

### `daily_ticket_sequences`

Tracks per-day ticket sequence numbers for the human-readable ticket ID. Prevents collisions and races.

```sql
CREATE TABLE daily_ticket_sequences (
    id              SERIAL PRIMARY KEY,
    office_id       INTEGER NOT NULL REFERENCES offices(id),
    sequence_date   DATE NOT NULL,
    last_sequence   INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, sequence_date)
);
```

**How it's used:**
```sql
-- atomic increment
UPDATE daily_ticket_sequences
SET last_sequence = last_sequence + 1, updated_at = now()
WHERE office_id = $1 AND sequence_date = CURRENT_DATE
RETURNING last_sequence;

-- if no row found, INSERT with last_sequence=1
```

**Note:** sequence is per-day, per-office — NOT per-category. So `PUB-WTR-280426-0042` and `PRV-POL-280426-0043` would coexist on same day. This makes the human ID unique even if two complaints are filed at the same instant.

### `media_uploads`

Lightweight registry of telegram file_ids referenced by tickets. For audit + future migration to permanent storage.

```sql
CREATE TABLE media_uploads (
    id                  SERIAL PRIMARY KEY,
    office_id           INTEGER NOT NULL REFERENCES offices(id),
    ticket_id           INTEGER REFERENCES tickets(id),
    citizen_id          INTEGER REFERENCES citizens(id),
    telegram_file_id    VARCHAR(200) NOT NULL,
    file_kind           VARCHAR(20) NOT NULL,                  -- 'photo', 'document', 'voice'
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (office_id, telegram_file_id)
);

CREATE INDEX idx_media_ticket ON media_uploads (ticket_id);
```

---

## Existing tables NOT touched in V1.8

These exist from V0/V1/V1.5/V1.6 and are unchanged:

- `messages` — telegram inbound/outbound log
- `human_approvals` — approval gate before officer dispatches
- `agent_alerts` — Dashboard's output queue (not used by Communication agent)
- LLM-related logging tables added in V2 phase 1 (already in place)

---

## Migrations plan

Codex creates migrations in this order:

```
migrations/v18_001_extend_citizens.py
migrations/v18_002_extend_tickets.py
migrations/v18_003_extend_officer_mappings.py
migrations/v18_004_create_complaint_categories.py
migrations/v18_005_create_mandals.py
migrations/v18_006_create_wards.py
migrations/v18_007_create_citizen_conversations.py
migrations/v18_008_create_ticket_custom_fields.py
migrations/v18_009_create_daily_ticket_sequences.py
migrations/v18_010_create_media_uploads.py
```

Then a separate seed script (NOT a migration — seeds get re-run):

```
scripts/seed_v18.py
  - seed complaint_categories (14 rows)
  - seed mandals (5-10 rows for test office)
  - seed wards (30-100 rows for test office)
  - seed officer_mappings with at least one officer per queue
  - ensure offices(id=1) exists
```

---

## Validation rules summary (cross-reference for codex)

These rules drive the deterministic validators called from each ask state. All validators return `(is_valid: bool, normalized_value: str, error_hint: str)`.

| Field | Rule |
|---|---|
| name | 2-80 chars, letters + spaces + standard punctuation |
| dob | valid DD/MM/YYYY, age 18-110 |
| mobile | 10 digits, leading 6/7/8/9 |
| voter_id | 3 letters + 7 digits OR null (skip allowed) |
| mandal | must exist in `mandals` table for this office |
| ward_number | must exist in `wards` table for `(office_id, mandal_id)`; fallback to free-text after 2 invalid attempts |
| geo_lat/lng | valid -90..90 / -180..180; fallback to ward centroid |
| issue_type | must match enum for that subcategory |
| duration_days | integer 0-3650 |
| households_affected | integer 1-10000 |
| free text fields | min/max char lengths per spec |
| photo | optional; if provided, must be valid telegram file_id |

---

## What is NOT in this schema (deferred)

- Vector embeddings or semantic search tables (V3+)
- Memory graph tables (V3+ moat layer)
- Audit immutability (cryptographic chains for tamper-evidence) — eventually for production, not prototype
- Multi-tenant constraints beyond office_id column (V3 will add row-level security)
- Officer-side reply tables beyond what V1 already has — Department agent's phase 3
- Performance partitioning — premature at prototype scale

---

## Estimated table sizes at prototype scale

To set expectations:

- `citizens`: 10-100 rows (you + a teammate + a few testers)
- `tickets`: 50-500 rows during testing
- `ticket_custom_fields`: 250-2500 rows (5x tickets)
- `citizen_conversations`: 10-100 rows (one per chat_id)
- `agent_actions`: 5,000-50,000 rows (every state transition + every llm.call)
- `media_uploads`: 0-100 rows
- `messages`: 1,000-10,000 rows

Total DB size at prototype: well under 100MB. Postgres on a laptop handles this trivially. No partitioning, no read replicas, no caching layer needed.
