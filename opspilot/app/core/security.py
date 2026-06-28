"""Security primitives: password hashing, JWT tokens, TOTP MFA, enrollment tokens.

Design notes:
- Argon2id for passwords (memory-hard, current OWASP recommendation).
- JWTs are short-lived access tokens; refresh handled via DB-backed session rows
  so we can revoke (logout-everywhere, on role change, on suspected compromise).
- MFA is TOTP (RFC 6238), compatible with any authenticator app.
"""
from __future__ import annotations

import base64
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()  # sane secure defaults
_ALGO = "HS256"


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, stored_hash: str) -> bool:
    try:
        _ph.verify(stored_hash, plain)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored_hash)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# JWT access tokens
# --------------------------------------------------------------------------- #
def create_access_token(*, user_id: int, role: str, session_id: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "sid": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=s.ACCESS_TOKEN_TTL_MIN),
        "typ": "access",
    }
    return jwt.encode(payload, s.SECRET_KEY, algorithm=_ALGO)


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.SECRET_KEY, algorithms=[_ALGO])


# --------------------------------------------------------------------------- #
# TOTP MFA (no external dep — RFC 6238 implementation)
# --------------------------------------------------------------------------- #
def generate_totp_secret() -> str:
    """Base32 secret for an authenticator app."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    import struct
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, "sha1").digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    """Verify a TOTP code allowing +/- `window` steps for clock drift."""
    if not code or not code.isdigit():
        return False
    counter = int(datetime.now(timezone.utc).timestamp() // 30)
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, counter + drift), code):
            return True
    return False


def totp_provisioning_uri(secret_b32: str, account: str, issuer: str = "BVTech OpsPilot") -> str:
    from urllib.parse import quote
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")


# --------------------------------------------------------------------------- #
# Agent enrollment tokens (signed, single-client-scoped)
# --------------------------------------------------------------------------- #
def mint_enrollment_token(*, client_id: int, ttl_hours: int = 72) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "client_id": client_id,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
        "typ": "enroll",
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, s.AGENT_ENROLL_SECRET, algorithm=_ALGO)


def verify_enrollment_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.AGENT_ENROLL_SECRET, algorithms=[_ALGO])


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


# --- API keys & webhook signing (v0.21 integrations) ------------------------ #
import hashlib  # noqa: E402  (kept local to this feature block)


def hash_api_key(key: str) -> str:
    """Fast, indexable hash for API keys. The key itself is high-entropy, so a
    single SHA-256 is appropriate (and lets us look up by hash on every call)."""
    return hashlib.sha256(key.encode()).hexdigest()


def sign_hmac(secret: str, body: bytes) -> str:
    """HMAC-SHA256 signature for outbound webhook payloads (hex)."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
