"""Token encryption helpers.

GitHub personal access tokens are stored encrypted in the database using
Fernet symmetric encryption.  The key is derived from the GREEN_SECRET_KEY
environment variable (a default is used for local development — set a strong
random value in production).
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    """Return a Fernet instance derived from the configured secret."""
    secret = os.getenv(
        "GREEN_SECRET_KEY",
        "green-software-demo-secret-key-change-in-production",
    )
    # Fernet requires a URL-safe base64-encoded 32-byte key.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token for storage."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored token back to plaintext."""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return ""
