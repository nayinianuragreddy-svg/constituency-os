"""Fernet symmetric encryption for Telegram bot tokens.

Bot tokens are stored encrypted in constituency_bots.bot_token_encrypted.

Two ways to provide the key, in order of preference:

1. TELEGRAM_TOKEN_ENCRYPTION_KEY_HEX
   64-char hex-encoded 32-byte key. Preferred for cloud platforms (e.g. Railway)
   that mangle base64 padding. Generate with:
       python -c "import secrets; print(secrets.token_bytes(32).hex())"

2. TELEGRAM_TOKEN_ENCRYPTION_KEY
   44-char base64url-encoded Fernet key. Native cryptography.fernet format.
   Generate with:
       python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   If only 43 chars are provided (some platforms strip the trailing '='), the
   missing padding is restored automatically.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    pass


def _key_from_hex(hex_value: str) -> bytes:
    """Convert 64-char hex to a Fernet-shaped base64url key."""
    try:
        raw_bytes = bytes.fromhex(hex_value)
    except ValueError as exc:
        raise EncryptionError(f"Invalid hex key: {exc}") from exc
    if len(raw_bytes) != 32:
        raise EncryptionError(
            f"Invalid TELEGRAM_TOKEN_ENCRYPTION_KEY_HEX: expected 32 bytes "
            f"(64 hex chars), got {len(raw_bytes)} bytes."
        )
    return base64.urlsafe_b64encode(raw_bytes)


def _key_from_fernet_str(fernet_value: str) -> bytes:
    """Validate a 44-char Fernet key string. Restore '=' padding if 43 chars."""
    s = fernet_value.strip()
    # Some platforms strip trailing '=' from env values; restore it.
    if len(s) == 43:
        s = s + "="
    if len(s) != 44:
        raise EncryptionError(
            f"Invalid TELEGRAM_TOKEN_ENCRYPTION_KEY: expected 44 chars "
            f"(or 43 with stripped padding), got {len(s)}."
        )
    return s.encode()


class TelegramTokenCipher:
    def __init__(self, key: str | None = None) -> None:
        # Explicit key arg wins, used for tests.
        if key is not None:
            fernet_key = _key_from_fernet_str(key)
        else:
            hex_value = os.getenv("TELEGRAM_TOKEN_ENCRYPTION_KEY_HEX", "").strip()
            fernet_value = os.getenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", "").strip()

            if hex_value:
                fernet_key = _key_from_hex(hex_value)
            elif fernet_value:
                fernet_key = _key_from_fernet_str(fernet_value)
            else:
                raise EncryptionError(
                    "Neither TELEGRAM_TOKEN_ENCRYPTION_KEY_HEX nor "
                    "TELEGRAM_TOKEN_ENCRYPTION_KEY is set. "
                    "Generate a hex key with: "
                    "python -c \"import secrets; print(secrets.token_bytes(32).hex())\""
                )

        try:
            self._fernet = Fernet(fernet_key)
        except (ValueError, binascii.Error) as exc:
            raise EncryptionError(f"Invalid encryption key: {exc}") from exc

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("plaintext must be non-empty")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise EncryptionError("Failed to decrypt token: invalid ciphertext or wrong key") from exc
