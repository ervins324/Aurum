"""Symmetric encryption helpers for storing sensitive credentials (e.g. API
tokens and keys) in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.

The secret key is read from AURUM_ENCRYPTION_KEY in the environment.  If the
variable is absent, a fresh random key is generated in-process and printed to
stderr once on startup — this means every restart with no key set loses access
to previously encrypted values.  For production use, persist the key in .env
(AURUM_ENCRYPTION_KEY=<base64-url-safe 32-byte key>) and never commit it.

Generating a permanent key:
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import logging
import os
import sys

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("aurum.encryption")

# Load or generate the Fernet key once at import time.
_raw_key = os.environ.get("AURUM_ENCRYPTION_KEY", "")

if _raw_key:
    # Accept a base64-url-safe key as produced by Fernet.generate_key().
    _fernet = Fernet(_raw_key.encode())
else:
    # No key configured — generate a temporary one and warn loudly.
    _temp_key = Fernet.generate_key()
    _fernet = Fernet(_temp_key)
    print(
        "[aurum] WARNING: AURUM_ENCRYPTION_KEY is not set. "
        "A temporary encryption key has been generated for this process.  "
        "Any credentials stored now will be unreadable after restart.  "
        f"Add this to your .env to persist them:\n  AURUM_ENCRYPTION_KEY={_temp_key.decode()}",
        file=sys.stderr,
    )


def encrypt(plaintext: str) -> str:
    """Return a Fernet-encrypted, base64-url-safe token string."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a token produced by encrypt().  Raises ValueError on failure."""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Decryption failed — token is invalid or key has changed") from exc


def mask(plaintext: str) -> str:
    """Return a safe display preview: first 3 + last 3 chars with '…' in the
    middle, or the full string if shorter than 8 characters."""
    if len(plaintext) < 8:
        return "***"
    return f"{plaintext[:3]}…{plaintext[-3:]}"
