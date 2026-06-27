"""Symmetric encryption for secrets at rest (e.g. cached M365 tokens).

The Fernet key is derived from SECRET_KEY, so no extra key material is needed —
but rotating SECRET_KEY invalidates stored ciphertext (re-sync re-populates it).
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..core.config import get_settings


def _fernet() -> Fernet:
    # 32-byte key from SECRET_KEY, urlsafe-base64 encoded as Fernet expects.
    digest = hashlib.sha256(get_settings().SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return None
