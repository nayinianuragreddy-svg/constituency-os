"""One-shot script: encrypt a Telegram bot token and insert constituency_bots row.

Reads from environment:
    TELEGRAM_BOT_TOKEN              the plaintext bot token from BotFather
    TELEGRAM_TOKEN_ENCRYPTION_KEY   the Fernet key (already on Railway)
    DATABASE_URL                    Postgres connection string (Railway-injected)

Optional, with sensible defaults:
    BOT_USERNAME                    default: MLAAgentbot
    MLA_NAME                        default: Ibrahimpatnam MLA
    CONSTITUENCY_NAME               default: Ibrahimpatnam

Behavior:
    1. Looks up the constituency UUID by name.
    2. Refuses to insert if an active bot already exists for that constituency
       (the partial unique index from migration 0007 enforces this anyway,
       but we surface the error cleanly).
    3. Encrypts the bot token with Fernet.
    4. Generates a fresh 32-byte hex secret_token.
    5. INSERTs the row.
    6. Prints the secret_token to stdout so the operator can register the
       webhook with Telegram. The bot token is NEVER printed.

Run on Railway via:
    railway run python scripts/insert_bot_row.py
or via the Railway one-off command runner UI.

After running, delete TELEGRAM_BOT_TOKEN from Railway env vars. The token
now lives only in encrypted form in constituency_bots.bot_token_encrypted.
"""

from __future__ import annotations

import os
import secrets
import sys
from uuid import UUID

import sqlalchemy as sa

from app.telegram.encryption import TelegramTokenCipher


def main() -> int:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var not set", file=sys.stderr)
        return 1

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("ERROR: DATABASE_URL env var not set", file=sys.stderr)
        return 1

    # Match the URL rewrite logic from migrations_v2/env.py: SQLAlchemy needs
    # the +psycopg dialect prefix when using psycopg v3.
    if db_url.startswith("postgres://"):
        db_url = "postgresql+psycopg" + db_url[len("postgres"):]
    elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    bot_username = os.environ.get("BOT_USERNAME", "MLAAgentbot").strip()
    mla_name = os.environ.get("MLA_NAME", "Ibrahimpatnam MLA").strip()
    constituency_name = os.environ.get("CONSTITUENCY_NAME", "Ibrahimpatnam").strip()

    # Encrypt the token. Cipher reads TELEGRAM_TOKEN_ENCRYPTION_KEY from env.
    cipher = TelegramTokenCipher()
    encrypted_token = cipher.encrypt(bot_token)

    # Verify roundtrip before writing to DB. If decryption fails we fail loud
    # rather than store an unrecoverable blob.
    if cipher.decrypt(encrypted_token) != bot_token:
        print("ERROR: encryption roundtrip failed, aborting", file=sys.stderr)
        return 1

    # Generate fresh secret_token for Telegram webhook header verification.
    # 32 bytes hex-encoded -> 64 chars, fits in the VARCHAR(256) column.
    secret_token = secrets.token_hex(32)

    engine = sa.create_engine(db_url)

    with engine.begin() as conn:
        # Look up the constituency.
        row = conn.execute(
            sa.text("SELECT id FROM constituencies WHERE name = :name"),
            {"name": constituency_name},
        ).fetchone()
        if row is None:
            print(
                f"ERROR: no constituency named '{constituency_name}' found. "
                f"Migration 0003 should have seeded it. Run alembic upgrade head first.",
                file=sys.stderr,
            )
            return 1
        constituency_id: UUID = row[0]

        # Check for existing active bot for this constituency.
        existing = conn.execute(
            sa.text(
                "SELECT id, bot_username FROM constituency_bots "
                "WHERE constituency_id = :cid AND is_active = TRUE"
            ),
            {"cid": constituency_id},
        ).fetchone()
        if existing is not None:
            print(
                f"ERROR: an active bot already exists for {constituency_name} "
                f"(bot_id={existing[0]}, username={existing[1]}). "
                f"Deactivate it first or use a different constituency.",
                file=sys.stderr,
            )
            return 1

        # Check bot_username is globally unique.
        username_taken = conn.execute(
            sa.text("SELECT id FROM constituency_bots WHERE bot_username = :u"),
            {"u": bot_username},
        ).fetchone()
        if username_taken is not None:
            print(
                f"ERROR: bot_username '{bot_username}' already exists in DB "
                f"(id={username_taken[0]}). Username must be globally unique.",
                file=sys.stderr,
            )
            return 1

        # INSERT the row.
        result = conn.execute(
            sa.text(
                """
                INSERT INTO constituency_bots
                    (constituency_id, mla_name, bot_username,
                     bot_token_encrypted, secret_token, is_active)
                VALUES
                    (:cid, :mla, :uname, :enc, :st, TRUE)
                RETURNING id
                """
            ),
            {
                "cid": constituency_id,
                "mla": mla_name,
                "uname": bot_username,
                "enc": encrypted_token,
                "st": secret_token,
            },
        )
        bot_id = result.fetchone()[0]

    print(f"OK: inserted constituency_bots row")
    print(f"  bot_id          = {bot_id}")
    print(f"  constituency_id = {constituency_id}")
    print(f"  bot_username    = {bot_username}")
    print(f"  mla_name        = {mla_name}")
    print(f"")
    print(f"SECRET_TOKEN (save this, you will need it for the Telegram setWebhook call):")
    print(f"  {secret_token}")
    print(f"")
    print(f"Next: register the webhook with Telegram using this secret_token.")
    print(f"Then DELETE the TELEGRAM_BOT_TOKEN env var from Railway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
