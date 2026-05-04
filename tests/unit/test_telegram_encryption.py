"""Unit tests for TelegramTokenCipher."""

import os
import pytest
from cryptography.fernet import Fernet

from app.telegram.encryption import TelegramTokenCipher, EncryptionError


@pytest.fixture
def valid_key():
    return Fernet.generate_key().decode()


@pytest.fixture
def cipher(valid_key):
    return TelegramTokenCipher(key=valid_key)


class TestEncryptDecryptRoundTrip:
    def test_round_trip(self, cipher):
        token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        assert cipher.decrypt(cipher.encrypt(token)) == token

    def test_round_trip_short_value(self, cipher):
        assert cipher.decrypt(cipher.encrypt("abc")) == "abc"

    def test_ciphertext_differs_from_plaintext(self, cipher):
        token = "some-bot-token"
        assert cipher.encrypt(token) != token


class TestBadKey:
    def test_wrong_length_raises(self):
        with pytest.raises(EncryptionError):
            TelegramTokenCipher(key="tooshort")

    def test_invalid_base64_raises(self):
        with pytest.raises(EncryptionError):
            TelegramTokenCipher(key="!" * 44)


class TestMissingEnvVar:
    def test_no_key_no_env_raises(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionError, match="TELEGRAM_TOKEN_ENCRYPTION_KEY"):
            TelegramTokenCipher()

    def test_env_var_used_when_key_not_passed(self, monkeypatch):
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", key)
        cipher = TelegramTokenCipher()
        assert cipher.decrypt(cipher.encrypt("hello")) == "hello"


class TestEmptyPlaintext:
    def test_empty_raises_value_error(self, cipher):
        with pytest.raises(ValueError):
            cipher.encrypt("")


class TestWrongKey:
    def test_decrypt_wrong_key_raises_encryption_error(self, valid_key):
        cipher1 = TelegramTokenCipher(key=valid_key)
        cipher2 = TelegramTokenCipher(key=Fernet.generate_key().decode())
        ciphertext = cipher1.encrypt("some-token")
        with pytest.raises(EncryptionError, match="decrypt"):
            cipher2.decrypt(ciphertext)
