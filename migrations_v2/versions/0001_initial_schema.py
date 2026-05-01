"""initial v2.1 schema — 17 tables, 2 stored functions

Revision ID: 0001
Revises:
Create Date: 2026-05-01

Creates the full v2.1 schema in an isolated Alembic chain (migrations_v2/).
The v1.8/v1.9 schema in the legacy migrations/ directory is untouched.
No data is seeded here; reference data comes in 0002, format catalogue in 0003.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# PostgreSQL forbids subqueries inside CHECK constraints.
# The required_fields shape rule is enforced via validate_required_fields(),
# an IMMUTABLE function created early in upgrade() and called by both
# complaint_categories and complaint_subcategories CHECK constraints.
# The function body implements the exact shape Doc A v2.1 specifies.

_PREFIX_PATTERN = r"^[A-Z]{3}-[A-Z]{3}$"


def _x(sql: str) -> None:
    op.execute(sa.text(sql))


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Extensions
    # -----------------------------------------------------------------------
    _x("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # -----------------------------------------------------------------------
    # Helper: validate_required_fields
    # Implements the Doc A v2.1 shape rule for required_fields JSONB arrays.
    # Must exist before complaint_categories and complaint_subcategories.
    # -----------------------------------------------------------------------
    _x("""
        CREATE OR REPLACE FUNCTION validate_required_fields(fields JSONB)
        RETURNS BOOLEAN
        LANGUAGE plpgsql
        IMMUTABLE
        AS $$
        DECLARE
            f JSONB;
        BEGIN
            IF jsonb_typeof(fields) != 'array' THEN
                RETURN FALSE;
            END IF;
            FOR f IN SELECT * FROM jsonb_array_elements(fields)
            LOOP
                IF NOT (
                    f ? 'name'     AND
                    f ? 'type'     AND
                    f ? 'required' AND
                    f ? 'label_en' AND
                    f ? 'label_te' AND
                    f ? 'label_hi' AND
                    jsonb_typeof(f->'required') = 'boolean' AND
                    f->>'type' IN (
                        'enum', 'string', 'integer', 'date',
                        'phone', 'yes_no', 'free_text', 'media'
                    )
                ) THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            RETURN TRUE;
        END;
        $$
    """)

    # -----------------------------------------------------------------------
    # 1. constituencies
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE constituencies (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(200) NOT NULL,
            name_te     VARCHAR(200),
            name_hi     VARCHAR(200),
            state       VARCHAR(100) NOT NULL,
            is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_constituencies_active ON constituencies(is_active)")

    # -----------------------------------------------------------------------
    # 2. mandals
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE mandals (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            constituency_id UUID        REFERENCES constituencies(id) ON DELETE RESTRICT,
            name            VARCHAR(200) NOT NULL,
            name_te         VARCHAR(200),
            name_hi         VARCHAR(200),
            is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
            sort_order      INTEGER     NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_mandals_constituency ON mandals(constituency_id, is_active, sort_order)")

    # -----------------------------------------------------------------------
    # 3. wards
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE wards (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            mandal_id       UUID        NOT NULL REFERENCES mandals(id) ON DELETE RESTRICT,
            ward_number     INTEGER     NOT NULL,
            ward_name       VARCHAR(200),
            centroid_lat    NUMERIC(9,6),
            centroid_lng    NUMERIC(9,6),
            is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (mandal_id, ward_number)
        )
    """)
    _x("CREATE INDEX idx_wards_mandal ON wards(mandal_id, is_active)")

    # -----------------------------------------------------------------------
    # 4. complaint_categories
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE complaint_categories (
            id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            code                  VARCHAR(20) NOT NULL UNIQUE,
            parent_group          VARCHAR(30) NOT NULL,
            display_name_en       VARCHAR(200) NOT NULL,
            display_name_te       VARCHAR(200),
            display_name_hi       VARCHAR(200),
            icon_emoji            VARCHAR(20),
            default_routing_queue VARCHAR(50) NOT NULL,
            requires_geo          BOOLEAN     NOT NULL DEFAULT FALSE,
            requires_photo        BOOLEAN     NOT NULL DEFAULT FALSE,
            is_active             BOOLEAN     NOT NULL DEFAULT TRUE,
            sort_order            INTEGER     NOT NULL DEFAULT 0,
            required_fields       JSONB       NOT NULL DEFAULT '[]'::jsonb,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_complaint_categories_required_fields CHECK (
                validate_required_fields(required_fields)
            )
        )
    """)
    _x("CREATE INDEX idx_complaint_categories_active ON complaint_categories(is_active, sort_order)")
    _x("CREATE INDEX idx_complaint_categories_parent ON complaint_categories(parent_group, is_active)")

    # -----------------------------------------------------------------------
    # 5. complaint_subcategories
    # -----------------------------------------------------------------------
    _x(f"""
        CREATE TABLE complaint_subcategories (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id      UUID        NOT NULL REFERENCES complaint_categories(id) ON DELETE RESTRICT,
            code             VARCHAR(30) NOT NULL UNIQUE,
            ticket_id_prefix VARCHAR(10) NOT NULL,
            display_name_en  VARCHAR(200) NOT NULL,
            display_name_te  VARCHAR(200),
            display_name_hi  VARCHAR(200),
            required_fields  JSONB       NOT NULL DEFAULT '[]'::jsonb,
            sla_hours        INTEGER,
            is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
            sort_order       INTEGER     NOT NULL DEFAULT 0,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_subcategories_prefix CHECK (
                ticket_id_prefix ~ '{_PREFIX_PATTERN}'
            ),
            CONSTRAINT chk_subcategories_required_fields CHECK (
                validate_required_fields(required_fields)
            )
        )
    """)
    _x("CREATE UNIQUE INDEX uq_subcategories_prefix ON complaint_subcategories(ticket_id_prefix)")
    _x("CREATE INDEX idx_complaint_subcategories_category ON complaint_subcategories(category_id, is_active)")

    # -----------------------------------------------------------------------
    # 6. citizens
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE citizens (
            id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name                  VARCHAR(255),
            mobile                VARCHAR(40),
            voter_id              VARCHAR(20),
            dob                   DATE,
            gender                VARCHAR(20),
            ward_id               UUID        REFERENCES wards(id)   ON DELETE RESTRICT,
            village               VARCHAR(200),
            mandal_id             UUID        REFERENCES mandals(id) ON DELETE RESTRICT,
            ward_number           INTEGER,
            pincode               VARCHAR(10),
            lat                   NUMERIC(9,6),
            lng                   NUMERIC(9,6),
            preferred_language    VARCHAR(20),
            registration_complete BOOLEAN     NOT NULL DEFAULT FALSE,
            notes                 JSONB       NOT NULL DEFAULT '{}'::jsonb,
            registered_at         TIMESTAMPTZ,
            last_seen_at          TIMESTAMPTZ,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_citizens_mobile   ON citizens(mobile)")
    _x("CREATE INDEX idx_citizens_ward     ON citizens(ward_id)")
    _x("CREATE INDEX idx_citizens_mandal   ON citizens(mandal_id)")
    _x("CREATE INDEX idx_citizens_reg      ON citizens(registration_complete)")

    # -----------------------------------------------------------------------
    # 7. conversations
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE conversations (
            id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            channel            VARCHAR(20) NOT NULL
                               CHECK (channel IN ('telegram', 'whatsapp')),
            channel_chat_id    VARCHAR(100) NOT NULL,
            citizen_id         UUID        REFERENCES citizens(id) ON DELETE RESTRICT,
            last_message_at    TIMESTAMPTZ,
            summary_data       JSONB       NOT NULL DEFAULT '{}'::jsonb,
            session_state      VARCHAR(20) NOT NULL DEFAULT 'active'
                               CHECK (session_state IN ('active', 'idle', 'blocked', 'closed')),
            preferred_language VARCHAR(20),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (channel, channel_chat_id)
        )
    """)
    _x("CREATE INDEX idx_conversations_citizen ON conversations(citizen_id)")
    _x("CREATE INDEX idx_conversations_channel ON conversations(channel, last_message_at DESC)")
    _x("CREATE INDEX idx_conversations_state   ON conversations(session_state, last_message_at DESC)")

    # -----------------------------------------------------------------------
    # 8. messages
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE messages (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
            direction       VARCHAR(10) NOT NULL
                            CHECK (direction IN ('inbound', 'outbound')),
            content         TEXT        NOT NULL,
            content_type    VARCHAR(20) NOT NULL DEFAULT 'text'
                            CHECK (content_type IN ('text', 'photo', 'document', 'voice', 'location')),
            channel_msg_id  VARCHAR(100),
            metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at DESC)")

    # -----------------------------------------------------------------------
    # 9. tickets
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE tickets (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_number    VARCHAR(20) NOT NULL,
            citizen_id       UUID        REFERENCES citizens(id)               ON DELETE RESTRICT,
            conversation_id  UUID        REFERENCES conversations(id)          ON DELETE RESTRICT,
            category_code    VARCHAR(20) REFERENCES complaint_categories(code) ON DELETE RESTRICT,
            subcategory_code VARCHAR(30) REFERENCES complaint_subcategories(code) ON DELETE RESTRICT,
            ward_id          UUID        REFERENCES wards(id)                  ON DELETE RESTRICT,
            mandal_id        UUID        REFERENCES mandals(id)                ON DELETE RESTRICT,
            status           VARCHAR(30) NOT NULL DEFAULT 'open'
                             CHECK (status IN (
                                 'draft', 'open', 'routed', 'acknowledged',
                                 'in_progress', 'awaiting_citizen', 'resolved',
                                 'closed', 'cancelled', 'escalated'
                             )),
            priority         VARCHAR(20) NOT NULL DEFAULT 'normal'
                             CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
            description      TEXT,
            structured_data  JSONB       NOT NULL DEFAULT '{}'::jsonb,
            sla_due_at       TIMESTAMPTZ,
            created_by_agent VARCHAR(50),
            deleted_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_tickets_number CHECK (
                ticket_number ~ '^[A-Z]{3}-[A-Z]{3}-[0-9]{6}-[0-9]{4}$'
            )
        )
    """)
    _x("CREATE UNIQUE INDEX uq_tickets_number_active ON tickets(ticket_number) WHERE deleted_at IS NULL")
    _x("CREATE INDEX idx_tickets_citizen      ON tickets(citizen_id,      created_at DESC)")
    _x("CREATE INDEX idx_tickets_status       ON tickets(status,           created_at DESC) WHERE deleted_at IS NULL")
    _x("CREATE INDEX idx_tickets_category     ON tickets(category_code,   created_at DESC)")
    _x("CREATE INDEX idx_tickets_conversation ON tickets(conversation_id)")

    # -----------------------------------------------------------------------
    # 10. ticket_updates
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE ticket_updates (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id  UUID        NOT NULL REFERENCES tickets(id) ON DELETE RESTRICT,
            status     VARCHAR(30),
            note       TEXT,
            source     VARCHAR(50),
            actor      VARCHAR(100),
            metadata   JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_ticket_updates_ticket ON ticket_updates(ticket_id, created_at DESC)")

    # -----------------------------------------------------------------------
    # 11. media_uploads
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE media_uploads (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id       UUID        REFERENCES tickets(id)       ON DELETE RESTRICT,
            citizen_id      UUID        REFERENCES citizens(id)      ON DELETE RESTRICT,
            conversation_id UUID        REFERENCES conversations(id) ON DELETE RESTRICT,
            file_kind       VARCHAR(20) NOT NULL
                            CHECK (file_kind IN ('photo', 'document', 'voice', 'video')),
            channel_file_id VARCHAR(200) NOT NULL,
            file_url        TEXT,
            metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_media_uploads_ticket  ON media_uploads(ticket_id)")
    _x("CREATE INDEX idx_media_uploads_citizen ON media_uploads(citizen_id)")

    # -----------------------------------------------------------------------
    # 12. agent_actions
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE agent_actions (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_name      VARCHAR(50)  NOT NULL,
            action_type     VARCHAR(100) NOT NULL,
            citizen_id      UUID         REFERENCES citizens(id)      ON DELETE RESTRICT,
            ticket_id       UUID         REFERENCES tickets(id)       ON DELETE RESTRICT,
            conversation_id UUID         REFERENCES conversations(id) ON DELETE RESTRICT,
            payload         JSONB        NOT NULL DEFAULT '{}'::jsonb,
            response        JSONB        NOT NULL DEFAULT '{}'::jsonb,
            status          VARCHAR(20)  NOT NULL
                            CHECK (status IN ('pending', 'success', 'error', 'partial')),
            idempotency_key VARCHAR(200) UNIQUE,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_agent_actions_agent   ON agent_actions(agent_name,  created_at DESC)")
    _x("CREATE INDEX idx_agent_actions_citizen ON agent_actions(citizen_id,  created_at DESC) WHERE citizen_id  IS NOT NULL")
    _x("CREATE INDEX idx_agent_actions_ticket  ON agent_actions(ticket_id,   created_at DESC) WHERE ticket_id   IS NOT NULL")

    # -----------------------------------------------------------------------
    # 13. daily_ticket_sequences
    # -----------------------------------------------------------------------
    _x(f"""
        CREATE TABLE daily_ticket_sequences (
            date             DATE        NOT NULL,
            ticket_id_prefix VARCHAR(10) NOT NULL,
            next_seq         INTEGER     NOT NULL DEFAULT 1,
            PRIMARY KEY (date, ticket_id_prefix),
            CONSTRAINT chk_dts_prefix CHECK (
                ticket_id_prefix ~ '{_PREFIX_PATTERN}'
            )
        )
    """)

    # -----------------------------------------------------------------------
    # 14. human_review_queue
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE human_review_queue (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id     UUID        REFERENCES conversations(id)  ON DELETE RESTRICT,
            citizen_id          UUID        REFERENCES citizens(id)       ON DELETE RESTRICT,
            ticket_id           UUID        REFERENCES tickets(id)        ON DELETE RESTRICT,
            triggered_by_agent  VARCHAR(50) NOT NULL,
            reason              VARCHAR(50) NOT NULL,
            suggested_priority  VARCHAR(20) NOT NULL DEFAULT 'normal'
                                CHECK (suggested_priority IN ('urgent', 'normal')),
            summary             TEXT        NOT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending', 'in_progress', 'resolved', 'dismissed')),
            assigned_to_user_id UUID,
            resolved_at         TIMESTAMPTZ,
            resolution_notes    TEXT,
            agent_action_id     UUID        REFERENCES agent_actions(id) ON DELETE RESTRICT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_hrq_pending  ON human_review_queue(suggested_priority, created_at) WHERE status = 'pending'")
    _x("CREATE INDEX idx_hrq_assigned ON human_review_queue(assigned_to_user_id) WHERE status IN ('pending', 'in_progress')")

    # -----------------------------------------------------------------------
    # 15. officer_contacts
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE officer_contacts (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            name                 VARCHAR(255) NOT NULL,
            title                VARCHAR(100),
            department           VARCHAR(100),
            queue_name           VARCHAR(50),
            phone                VARCHAR(40),
            email                VARCHAR(200),
            mandal_id            UUID        REFERENCES mandals(id) ON DELETE RESTRICT,
            ward_id              UUID        REFERENCES wards(id)   ON DELETE RESTRICT,
            is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
            is_default_for_queue BOOLEAN     NOT NULL DEFAULT FALSE,
            language_preference  VARCHAR(20),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_officer_contacts_queue ON officer_contacts(queue_name, is_active, is_default_for_queue)")

    # -----------------------------------------------------------------------
    # 16. officer_messages
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE officer_messages (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            officer_id     UUID        REFERENCES officer_contacts(id) ON DELETE RESTRICT,
            ticket_id      UUID        REFERENCES tickets(id)          ON DELETE RESTRICT,
            direction      VARCHAR(10) NOT NULL
                           CHECK (direction IN ('inbound', 'outbound')),
            channel        VARCHAR(20) NOT NULL
                           CHECK (channel IN ('telegram', 'whatsapp', 'email', 'sms')),
            message_text   TEXT,
            status         VARCHAR(20) NOT NULL DEFAULT 'queued'
                           CHECK (status IN ('queued', 'sent', 'delivered', 'failed', 'received')),
            channel_msg_id VARCHAR(200),
            metadata       JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    _x("CREATE INDEX idx_officer_messages_officer ON officer_messages(officer_id, created_at DESC)")
    _x("CREATE INDEX idx_officer_messages_ticket  ON officer_messages(ticket_id,  created_at DESC)")

    # -----------------------------------------------------------------------
    # 17. relationships  (schema only — Geo phase populates this)
    # -----------------------------------------------------------------------
    _x("""
        CREATE TABLE relationships (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            citizen_a_id UUID        NOT NULL REFERENCES citizens(id) ON DELETE RESTRICT,
            citizen_b_id UUID        NOT NULL REFERENCES citizens(id) ON DELETE RESTRICT,
            rel_type     VARCHAR(50) NOT NULL,
            metadata     JSONB       NOT NULL DEFAULT '{}'::jsonb,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_relationships_no_self_loop CHECK (citizen_a_id != citizen_b_id)
        )
    """)
    _x("CREATE INDEX idx_relationships_citizen_a ON relationships(citizen_a_id)")
    _x("CREATE INDEX idx_relationships_citizen_b ON relationships(citizen_b_id)")

    # -----------------------------------------------------------------------
    # Stored function: allocate_ticket_number  (Doc A v2.1 §2.3)
    # Atomically increments the daily sequence for p_prefix and returns the
    # formatted ticket number: PREFIX-DDMMYY-NNNN
    # -----------------------------------------------------------------------
    _x("""
        CREATE OR REPLACE FUNCTION allocate_ticket_number(p_prefix VARCHAR(10))
        RETURNS VARCHAR(20)
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_date_str TEXT    := to_char(CURRENT_DATE, 'DDMMYY');
            v_seq      INTEGER;
        BEGIN
            INSERT INTO daily_ticket_sequences (date, ticket_id_prefix, next_seq)
            VALUES (CURRENT_DATE, p_prefix, 2)
            ON CONFLICT (date, ticket_id_prefix)
            DO UPDATE
                SET next_seq = daily_ticket_sequences.next_seq + 1
            RETURNING next_seq - 1 INTO v_seq;

            RETURN p_prefix || '-' || v_date_str || '-' || lpad(v_seq::TEXT, 4, '0');
        END;
        $$
    """)

    # -----------------------------------------------------------------------
    # Stored function: fn_citizen_registration_status  (Doc A v2.1 §2.6)
    # Returns 'complete' | 'partial' | 'new' computed from a citizens row.
    # Intended as a virtual/computed column callable via SQL.
    # -----------------------------------------------------------------------
    _x("""
        CREATE OR REPLACE FUNCTION fn_citizen_registration_status(c citizens)
        RETURNS TEXT
        LANGUAGE plpgsql
        STABLE
        AS $$
        BEGIN
            IF c.registration_complete THEN
                RETURN 'complete';
            END IF;
            IF c.name        IS NOT NULL
               AND c.mobile  IS NOT NULL
               AND c.ward_id IS NOT NULL
               AND c.mandal_id IS NOT NULL
            THEN
                RETURN 'partial';
            END IF;
            RETURN 'new';
        END;
        $$
    """)


# ---------------------------------------------------------------------------
# downgrade — drop everything in reverse FK dependency order
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # fn_citizen_registration_status takes a citizens row-type argument,
    # creating a PG type dependency; must be dropped before the citizens table.
    _x("DROP FUNCTION IF EXISTS fn_citizen_registration_status(citizens)")

    # allocate_ticket_number only executes SQL on daily_ticket_sequences —
    # no type dependency, so it can go here or after; drop early for clarity.
    _x("DROP FUNCTION IF EXISTS allocate_ticket_number(VARCHAR)")

    # tables in strict reverse FK-dependency order
    _x("DROP TABLE IF EXISTS relationships")
    _x("DROP TABLE IF EXISTS officer_messages")
    _x("DROP TABLE IF EXISTS officer_contacts")
    _x("DROP TABLE IF EXISTS human_review_queue")
    _x("DROP TABLE IF EXISTS daily_ticket_sequences")
    _x("DROP TABLE IF EXISTS agent_actions")
    _x("DROP TABLE IF EXISTS media_uploads")
    _x("DROP TABLE IF EXISTS ticket_updates")
    _x("DROP TABLE IF EXISTS tickets")
    _x("DROP TABLE IF EXISTS messages")
    _x("DROP TABLE IF EXISTS conversations")
    _x("DROP TABLE IF EXISTS citizens")
    _x("DROP TABLE IF EXISTS complaint_subcategories")
    _x("DROP TABLE IF EXISTS complaint_categories")
    _x("DROP TABLE IF EXISTS wards")
    _x("DROP TABLE IF EXISTS mandals")
    _x("DROP TABLE IF EXISTS constituencies")

    # validate_required_fields is referenced by CHECK constraints on
    # complaint_categories and complaint_subcategories; drop it last,
    # after those tables are gone.
    _x("DROP FUNCTION IF EXISTS validate_required_fields(JSONB)")
