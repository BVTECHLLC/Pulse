"""Unit tests for app/core/security.py — the security primitives.

These are pure functions with a large blast radius if wrong, so they're tested
in isolation (no DB, no HTTP). The TOTP/HOTP cases assert against the canonical
RFC 4226 / RFC 6238 test vectors.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.config import get_settings


# --------------------------------------------------------------------------- #
# Passwords (Argon2id)
# --------------------------------------------------------------------------- #
def test_password_hash_roundtrip():
    h = security.hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"  # never stored in plaintext
    assert security.verify_password("correct horse battery staple", h) is True


def test_password_wrong_is_rejected():
    h = security.hash_password("right-password")
    assert security.verify_password("wrong-password", h) is False


def test_password_hashes_are_salted_and_unique():
    a = security.hash_password("same")
    b = security.hash_password("same")
    assert a != b  # distinct salts
    assert security.verify_password("same", a)
    assert security.verify_password("same", b)


def test_verify_password_never_raises_on_garbage_hash():
    # A corrupt/garbage stored hash must be a clean False, not an exception.
    assert security.verify_password("anything", "not-a-real-argon2-hash") is False


# --------------------------------------------------------------------------- #
# JWT access tokens
# --------------------------------------------------------------------------- #
def test_access_token_roundtrip():
    tok = security.create_access_token(user_id=42, role="owner", session_id="sid-1")
    payload = security.decode_token(tok)
    assert payload["sub"] == "42"
    assert payload["role"] == "owner"
    assert payload["sid"] == "sid-1"
    assert payload["typ"] == "access"


def test_access_token_rejects_wrong_secret():
    tok = security.create_access_token(user_id=1, role="tech", session_id="s")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(tok, "the-wrong-secret", algorithms=["HS256"])


def test_decode_rejects_expired_token():
    s = get_settings()
    expired = jwt.encode(
        {
            "sub": "1", "role": "owner", "sid": "s", "typ": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        s.SECRET_KEY, algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_token(expired)


def test_decode_rejects_tampered_token():
    tok = security.create_access_token(user_id=1, role="owner", session_id="s")
    tampered = tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb")
    with pytest.raises(jwt.PyJWTError):
        security.decode_token(tampered)


# --------------------------------------------------------------------------- #
# Enrollment tokens — separately keyed from user sessions
# --------------------------------------------------------------------------- #
def test_enrollment_token_roundtrip():
    tok = security.mint_enrollment_token(client_id=7)
    payload = security.verify_enrollment_token(tok)
    assert payload["client_id"] == 7
    assert payload["typ"] == "enroll"
    assert "jti" in payload


def test_enrollment_token_uses_separate_secret():
    """An enrollment token must NOT validate against the user-session secret."""
    tok = security.mint_enrollment_token(client_id=1)
    s = get_settings()
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(tok, s.SECRET_KEY, algorithms=["HS256"])  # SECRET_KEY != AGENT_ENROLL_SECRET


def test_enrollment_token_expires():
    tok = security.mint_enrollment_token(client_id=1, ttl_hours=-1)  # already expired
    with pytest.raises(jwt.ExpiredSignatureError):
        security.verify_enrollment_token(tok)


# --------------------------------------------------------------------------- #
# TOTP / HOTP — RFC 4226 & RFC 6238 test vectors
# --------------------------------------------------------------------------- #
# RFC 4226 Appendix D shared secret: ASCII "12345678901234567890".
_RFC_SECRET_B32 = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
# RFC 4226 Appendix D: 6-digit HOTP values for counters 0..9.
_RFC4226_HOTP = [
    "755224", "287082", "359152", "969429", "338314",
    "254676", "287922", "162583", "399871", "520489",
]


@pytest.mark.parametrize("counter,expected", list(enumerate(_RFC4226_HOTP)))
def test_hotp_matches_rfc4226_vectors(counter, expected):
    assert security._hotp(_RFC_SECRET_B32, counter) == expected


def test_verify_totp_accepts_current_code():
    secret = security.generate_totp_secret()
    counter = int(datetime.now(timezone.utc).timestamp() // 30)
    code = security._hotp(secret, counter)
    assert security.verify_totp(secret, code) is True


def test_verify_totp_accepts_drift_within_window():
    secret = security.generate_totp_secret()
    counter = int(datetime.now(timezone.utc).timestamp() // 30)
    assert security.verify_totp(secret, security._hotp(secret, counter - 1)) is True
    assert security.verify_totp(secret, security._hotp(secret, counter + 1)) is True


def test_verify_totp_rejects_code_outside_window():
    secret = security.generate_totp_secret()
    counter = int(datetime.now(timezone.utc).timestamp() // 30)
    far = security._hotp(secret, counter - 5)  # 5 steps ago, window is +/-1
    assert security.verify_totp(secret, far) is False


def test_verify_totp_rejects_non_numeric_and_empty():
    secret = security.generate_totp_secret()
    assert security.verify_totp(secret, "") is False
    assert security.verify_totp(secret, "abcdef") is False
    assert security.verify_totp(secret, None) is False  # type: ignore[arg-type]


def test_generate_totp_secret_is_valid_base32():
    secret = security.generate_totp_secret()
    # decodable as base32 once padded — proves it's a usable authenticator secret
    base64.b32decode(secret + "=" * (-len(secret) % 8))


def test_totp_provisioning_uri_shape():
    uri = security.totp_provisioning_uri("ABC234", account="a@b.com")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC234" in uri
    assert "issuer=" in uri


# --------------------------------------------------------------------------- #
# API keys & webhook signing
# --------------------------------------------------------------------------- #
def test_hash_api_key_is_deterministic_and_irreversible():
    h1 = security.hash_api_key("pk_live_abc")
    h2 = security.hash_api_key("pk_live_abc")
    assert h1 == h2  # deterministic so we can look up by hash
    assert h1 != "pk_live_abc"
    assert len(h1) == 64  # sha256 hex
    assert security.hash_api_key("pk_live_abd") != h1


def test_sign_hmac_is_stable_and_key_dependent():
    body = b'{"event":"ping"}'
    sig = security.sign_hmac("shared-secret", body)
    assert sig == security.sign_hmac("shared-secret", body)
    assert sig != security.sign_hmac("other-secret", body)
    assert len(sig) == 64  # sha256 hex


def test_constant_time_eq():
    assert security.constant_time_eq("abc", "abc") is True
    assert security.constant_time_eq("abc", "abd") is False


def test_random_token_unique_and_urlsafe():
    a, b = security.random_token(), security.random_token()
    assert a != b
    assert "/" not in a and "+" not in a  # url-safe alphabet
