"""Fernet symmetric encryption for Telegram bot tokens.

Bot tokens are stored encrypted in constituency_bots.bot_token_encrypted.
The encryption key comes from env var TELEGRAM_TOKEN_ENCRYPTION_KEY.

Generate a key for .env:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    pass


class TelegramTokenCipher:
    def __init__(self, key: str | None = None) -> None:
        raw = key or os.getenv("TELEGRAM_TOKEN_ENCRYPTION_KEY")
        if not raw:
            raise EncryptionError(
                "TELEGRAM_TOKEN_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        raw = raw.strip()
        # Fernet keys are 44-char base64url-encoded 32-byte strings
        if len(raw) != 44:
            raise EncryptionError(
                f"Invalid TELEGRAM_TOKEN_ENCRYPTION_KEY: expected 44 chars, got {len(raw)}. "
                "Regenerate with Fernet.generate_key()."
            )
        try:
            self._fernet = Fernet(raw.encode())
        except (ValueError, Exception) as exc:
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
