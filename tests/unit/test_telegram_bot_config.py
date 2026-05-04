"""Unit tests for BotConfigRepository.

Uses an in-memory SQLite-compatible setup via a small helper that inserts
test rows into the seeded Postgres test DB from the session fixture. Since
BotConfigRepository only does simple SELECT queries, these tests exercise
the full read path including token decryption.
"""

import uuid
import pytest
from cryptography.fernet import Fernet

from app.telegram.encryption import TelegramTokenCipher
from app.telegram.bot_config import BotConfigRepository


@pytest.fixture(scope="module")
def bot_config_engine(seeded_test_db_engine):
    """Reuse the session-scoped seeded engine."""
    return seeded_test_db_engine


@pytest.fixture(scope="module")
def cipher():
    key = Fernet.generate_key().decode()
    return TelegramTokenCipher(key=key)


@pytest.fixture(scope="module")
def bot_rows(bot_config_engine, cipher):
    """Insert test constituency_bots rows, yield them, clean up."""
    import sqlalchemy as sa

    # Insert a constituency row first
    constituency_id = str(uuid.uuid4())
    active_bot_id = str(uuid.uuid4())
    inactive_bot_id = str(uuid.uuid4())
    secret_active = "secret-active-token-abc"
    secret_inactive = "secret-inactive-token-xyz"
    token_plain = "1111111111:AAABBBCCC"

    with bot_config_engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO constituencies (id, name, state) "
                "VALUES (:id, :name, :state)"
            ),
            {"id": constituency_id, "name": "Test Constituency", "state": "Telangana"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO constituency_bots "
                "(id, constituency_id, mla_name, bot_username, "
                "bot_token_encrypted, secret_token, is_active) "
                "VALUES (:id, :cid, :mla, :uname, :tok, :sec, TRUE)"
            ),
            {
                "id": active_bot_id,
                "cid": constituency_id,
                "mla": "Test MLA",
                "uname": "TestActiveBot",
                "tok": cipher.encrypt(token_plain),
                "sec": secret_active,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO constituency_bots "
                "(id, constituency_id, mla_name, bot_username, "
                "bot_token_encrypted, secret_token, is_active) "
                "VALUES (:id, :cid, :mla, :uname, :tok, :sec, FALSE)"
            ),
            {
                "id": inactive_bot_id,
                "cid": constituency_id,
                "mla": "Test MLA",
                "uname": "TestInactiveBot",
                "tok": cipher.encrypt(token_plain),
                "sec": secret_inactive,
            },
        )

    yield {
        "constituency_id": constituency_id,
        "active_bot_id": active_bot_id,
        "inactive_bot_id": inactive_bot_id,
        "secret_active": secret_active,
        "secret_inactive": secret_inactive,
        "token_plain": token_plain,
    }

    # Cleanup
    with bot_config_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM constituency_bots WHERE constituency_id = :cid"),
            {"cid": constituency_id},
        )
        conn.execute(
            sa.text("DELETE FROM constituencies WHERE id = :cid"),
            {"cid": constituency_id},
        )


@pytest.fixture(scope="module")
def repo(bot_config_engine, cipher):
    return BotConfigRepository(bot_config_engine, cipher)


class TestGetBySecretToken:
    def test_returns_bot_config_with_decrypted_token(self, repo, bot_rows):
        cfg = repo.get_by_secret_token(bot_rows["secret_active"])
        assert cfg is not None
        assert cfg.bot_token == bot_rows["token_plain"]
        assert cfg.bot_username == "TestActiveBot"

    def test_returns_none_on_miss(self, repo):
        assert repo.get_by_secret_token("nonexistent-secret") is None

    def test_inactive_bot_not_returned(self, repo, bot_rows):
        assert repo.get_by_secret_token(bot_rows["secret_inactive"]) is None


class TestGetByBotUsername:
    def test_returns_config(self, repo, bot_rows):
        cfg = repo.get_by_bot_username("TestActiveBot")
        assert cfg is not None
        assert cfg.bot_token == bot_rows["token_plain"]

    def test_inactive_not_returned(self, repo):
        assert repo.get_by_bot_username("TestInactiveBot") is None

    def test_miss_returns_none(self, repo):
        assert repo.get_by_bot_username("NoSuchBot") is None


class TestListActive:
    def test_excludes_inactive(self, repo, bot_rows):
        cfgs = repo.list_active()
        usernames = [c.bot_username for c in cfgs]
        assert "TestActiveBot" in usernames
        assert "TestInactiveBot" not in usernames
