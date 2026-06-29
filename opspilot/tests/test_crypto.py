"""Unit tests for app/services/crypto.py — at-rest secret encryption (Fernet)."""
from __future__ import annotations

from app.services import crypto


def test_encrypt_decrypt_roundtrip():
    secret = "ms-graph-refresh-token-value"
    ct = crypto.encrypt(secret)
    assert ct != secret  # actually encrypted
    assert crypto.decrypt(ct) == secret


def test_ciphertext_is_non_deterministic():
    # Fernet embeds a random IV, so the same plaintext encrypts differently.
    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_decrypt_tampered_ciphertext_returns_none():
    ct = crypto.encrypt("payload")
    tampered = ct[:-4] + ("AAAA" if not ct.endswith("AAAA") else "BBBB")
    assert crypto.decrypt(tampered) is None


def test_decrypt_garbage_returns_none():
    assert crypto.decrypt("not-a-fernet-token") is None
    assert crypto.decrypt("") is None


def test_roundtrip_handles_unicode_and_empty():
    for value in ["", "naïve—token™", "🔐"]:
        assert crypto.decrypt(crypto.encrypt(value)) == value
