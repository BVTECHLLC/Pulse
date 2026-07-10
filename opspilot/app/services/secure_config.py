"""Secure configuration vault (v0.41).

Integration credentials (M365 secrets, Dialpad keys, LinkedIn tokens, QuickBooks
refresh tokens, …) are entered through the Settings UI and stored on an
``IntegrationConnection.config`` JSON blob. This module makes that storage safe:

  * Sensitive values are encrypted at rest with the same Fernet key as cached
    M365 tokens (``services/crypto.py``, derived from SECRET_KEY).
  * Reads NEVER echo a secret back — they return a masked hint (``••••1234``)
    plus a ``configured`` flag so the UI can show "connected" without leaking.
  * Plaintext is only ever decrypted server-side, on demand, to make an
    outbound API call.

Secrets are therefore never committed to the repo and never sent to the browser.

A "platform connection" is a singleton (client_id IS NULL) row per provider that
holds the MSP's own credentials — e.g. the house Microsoft 365 tenant, the
LinkedIn page, the Dialpad account. ``get_platform(db, provider)`` /
``upsert_platform(...)`` manage it.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from ..models import IntegrationConnection
from . import crypto

# Marker prefix on stored ciphertext so we can tell an encrypted value from a
# plain one (legacy rows, non-secret config) without a schema change.
_ENC_PREFIX = "enc::"

# Any config key whose name contains one of these tokens is treated as a secret:
# encrypted on write, masked on read. Conservative by design — better to mask a
# harmless value than to leak a real one.
_SECRET_HINTS = (
    "secret", "password", "passwd", "token", "api_key", "apikey", "key",
    "client_secret", "refresh_token", "access_token", "private", "credential",
)


def is_secret_key(name: str) -> bool:
    n = name.lower()
    # "client_id" / "tenant_id" / "user_id" are identifiers, not secrets.
    if n in ("client_id", "tenant_id", "user_id", "account_id", "location_id",
             "person_urn", "redirect_uri", "site_url", "base_url", "from_email",
             "sender_email", "mailbox", "number", "phone"):
        return False
    return any(h in n for h in _SECRET_HINTS)


def _mask(value: str) -> str:
    if not value:
        return ""
    tail = value[-4:] if len(value) >= 4 else value
    return "••••" + tail


def encrypt_config(raw: dict, *, previous: dict | None = None) -> dict:
    """Return a config dict safe to persist.

    Secret-looking keys are Fernet-encrypted and tagged with ``_ENC_PREFIX``.
    A sentinel value of ``""`` or ``None`` for a secret key means "leave the
    existing stored secret untouched" (so a UI round-trip that submits the mask
    never wipes the real value). Non-secret keys pass through verbatim.
    """
    previous = previous or {}
    out: dict = {}
    for k, v in (raw or {}).items():
        if is_secret_key(k):
            # Empty / masked submission -> keep whatever was already stored.
            if v in (None, "") or (isinstance(v, str) and v.startswith("••••")):
                if k in previous:
                    out[k] = previous[k]
                continue
            out[k] = _ENC_PREFIX + crypto.encrypt(str(v))
        else:
            out[k] = v
    # Partial-update semantics: any previously-stored key the caller didn't
    # mention is retained untouched. Callers strip None/absent fields before
    # calling, so omission means "leave as-is"; submit "" to clear a field.
    for k, v in previous.items():
        if k not in out:
            out[k] = v
    return out


def decrypt_value(stored: object) -> str | None:
    """Decrypt one stored config value (handles both encrypted and plain)."""
    if not isinstance(stored, str):
        return stored  # type: ignore[return-value]
    if stored.startswith(_ENC_PREFIX):
        return crypto.decrypt(stored[len(_ENC_PREFIX):])
    return stored


def get_secret(config: dict | None, key: str) -> str | None:
    """Server-side: pull a single decrypted secret out of a stored config."""
    if not config or key not in config:
        return None
    return decrypt_value(config[key])


def secret_state(config: dict | None, key: str) -> str:
    """'missing' | 'ok' | 'unreadable' for one stored secret. 'unreadable' means
    a ciphertext IS stored but will not decrypt with the current SECRET_KEY (the
    silent failure that looks like 'saved but not connected'): re-entering fixes
    it. Distinguishing this from 'missing' turns a mystery into an instruction."""
    if not config or key not in config or config[key] in (None, ""):
        return "missing"
    raw = config[key]
    if isinstance(raw, str) and raw.startswith(_ENC_PREFIX):
        return "ok" if crypto.decrypt(raw[len(_ENC_PREFIX):]) else "unreadable"
    return "ok"


def public_view(config: dict | None) -> dict:
    """Browser-safe projection: secrets become a masked hint, others pass through.

    Returns ``{key: {"value": <plain|None>, "secret": bool, "set": bool,
    "hint": <masked|None>}}`` so the UI can render inputs without ever holding a
    real secret.
    """
    out: dict = {}
    for k, v in (config or {}).items():
        if is_secret_key(k):
            plain = decrypt_value(v)
            out[k] = {"secret": True, "set": bool(plain),
                      "hint": _mask(plain) if plain else None, "value": None}
        else:
            out[k] = {"secret": False, "set": v not in (None, ""),
                      "hint": None, "value": v}
    return out


def configured(config: dict | None, required: Iterable[str]) -> bool:
    """True iff every required key has a non-empty (decrypted) value."""
    cfg = config or {}
    for k in required:
        if is_secret_key(k):
            if not decrypt_value(cfg.get(k)):
                return False
        elif not cfg.get(k):
            return False
    return True


# --------------------------------------------------------------------------- #
# Platform (MSP-owned) singleton connections
# --------------------------------------------------------------------------- #
def get_platform(db: Session, provider: str) -> IntegrationConnection | None:
    return (db.query(IntegrationConnection)
            .filter(IntegrationConnection.provider == provider,
                    IntegrationConnection.client_id.is_(None))
            .order_by(IntegrationConnection.id.asc())
            .first())


def upsert_platform(db: Session, provider: str, name: str, category: str,
                    new_config: dict) -> IntegrationConnection:
    conn = get_platform(db, provider)
    if conn is None:
        conn = IntegrationConnection(provider=provider, name=name, category=category,
                                     config={}, client_id=None, enabled=True)
        db.add(conn)
    merged = encrypt_config(new_config, previous=conn.config or {})
    conn.config = merged
    conn.name = name or conn.name
    if category:
        conn.category = category
    db.commit()
    db.refresh(conn)
    return conn
