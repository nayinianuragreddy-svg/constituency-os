"""Bot configuration loader.

Reads constituency_bots rows and decrypts tokens in-memory.
Inactive bots are excluded from all lookups.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.telegram.encryption import TelegramTokenCipher


@dataclass
class BotConfig:
    bot_id: UUID
    constituency_id: UUID
    mla_name: str
    bot_username: str
    bot_token: str          # decrypted, in-memory only
    secret_token: str
    webhook_url: str | None


_SELECT = sa.text("""
    SELECT id, constituency_id, mla_name, bot_username,
           bot_token_encrypted, secret_token, webhook_url
    FROM constituency_bots
    WHERE is_active = TRUE AND {where}
""")


class BotConfigRepository:
    def __init__(self, engine: Engine, cipher: TelegramTokenCipher) -> None:
        self._engine = engine
        self._cipher = cipher

    def _row_to_config(self, row) -> BotConfig:
        return BotConfig(
            bot_id=row[0],
            constituency_id=row[1],
            mla_name=row[2],
            bot_username=row[3],
            bot_token=self._cipher.decrypt(row[4]),
            secret_token=row[5],
            webhook_url=row[6],
        )

    def get_by_secret_token(self, secret_token: str) -> BotConfig | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT id, constituency_id, mla_name, bot_username, "
                    "bot_token_encrypted, secret_token, webhook_url "
                    "FROM constituency_bots "
                    "WHERE is_active = TRUE AND secret_token = :st"
                ),
                {"st": secret_token},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_config(row)

    def get_by_bot_username(self, bot_username: str) -> BotConfig | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT id, constituency_id, mla_name, bot_username, "
                    "bot_token_encrypted, secret_token, webhook_url "
                    "FROM constituency_bots "
                    "WHERE is_active = TRUE AND bot_username = :u"
                ),
                {"u": bot_username},
            ).fetchone()
        if row is None:
            return None
        return self._row_to_config(row)

    def list_active(self) -> list[BotConfig]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT id, constituency_id, mla_name, bot_username, "
                    "bot_token_encrypted, secret_token, webhook_url "
                    "FROM constituency_bots "
                    "WHERE is_active = TRUE "
                    "ORDER BY created_at"
                )
            ).fetchall()
        return [self._row_to_config(r) for r in rows]
