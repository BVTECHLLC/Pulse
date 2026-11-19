"""Global email suppression list + signed one-click unsubscribe tokens.

Any address on this list is NEVER emailed again by any outreach sender (client
prospecting, and the disabled personal/legal one-shot channel). This is the
do-not-contact backbone behind the public unsubscribe page.

An unsubscribe link carries an HMAC-signed token of the recipient's address, so
one click opts out that exact address — no login and no database lookup to build
the link, and the token can't be forged to unsubscribe someone else's address by
guessing. The list itself lives in the encrypted config vault (provider
``email_suppression``) so it persists across restarts and deploys.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "email_suppression"


def _secret() -> bytes:
    from ..core.config import get_settings
    return (get_settings().SECRET_KEY or "bvtech-suppression").encode()


def normalize(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    e = normalize(email)
    return "@" in e and "." in e.split("@")[-1] and len(e) <= 254 and " " not in e


# --------------------------------------------------------------------------- #
# Signed tokens (same construction as the academy certificate codes)
# --------------------------------------------------------------------------- #
def token_for(email: str) -> str:
    e = normalize(email)
    sig = hmac.new(_secret(), ("unsub:" + e).encode(), hashlib.sha256).hexdigest()[:20]
    body = base64.urlsafe_b64encode(e.encode()).decode().rstrip("=")
    return f"{body}.{sig}"


def email_from_token(token: str) -> str | None:
    try:
        body, sig = (token or "").rsplit(".", 1)
        e = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        exp = hmac.new(_secret(), ("unsub:" + normalize(e)).encode(),
                       hashlib.sha256).hexdigest()[:20]
        if not hmac.compare_digest(sig, exp):
            return None
        return normalize(e)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# The list
# --------------------------------------------------------------------------- #
def _load(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = dict((conn.config if conn else None) or {})
    return dict(cfg.get("emails") or {})


def is_suppressed(db: Session, email: str) -> bool:
    if not email:
        return False
    return normalize(email) in _load(db)


def suppress(db: Session, email: str, source: str = "unsubscribe") -> bool:
    """Add an address to the do-not-contact list. Returns True if it is now
    suppressed (including when it already was). Idempotent."""
    e = normalize(email)
    if not valid_email(e):
        return False
    emails = _load(db)
    if e not in emails:
        emails[e] = {"ts": datetime.now(timezone.utc).isoformat(), "src": source[:40]}
        secure_config.upsert_platform(db, PROVIDER, "Email Suppression", "System",
                                      {"emails": emails})
    return True


def unsuppress(db: Session, email: str) -> bool:
    """Remove an address (staff action — someone re-opted-in). Returns True if it
    was present and removed."""
    e = normalize(email)
    emails = _load(db)
    if e in emails:
        emails.pop(e, None)
        secure_config.upsert_platform(db, PROVIDER, "Email Suppression", "System",
                                      {"emails": emails})
        return True
    return False


def count(db: Session) -> int:
    return len(_load(db))


def all_entries(db: Session) -> list[dict]:
    return sorted(({"email": k, **(v if isinstance(v, dict) else {})}
                   for k, v in _load(db).items()),
                  key=lambda r: r.get("ts") or "", reverse=True)


# --------------------------------------------------------------------------- #
# The unsubscribe link + email footer (CAN-SPAM: clear opt-out on every message)
# --------------------------------------------------------------------------- #
def unsubscribe_url(email: str, base: str | None = None) -> str:
    if base is None:
        from ..core.config import get_settings
        base = (get_settings().PUBLIC_BASE_URL or "https://portal.bvtech.org")
    return f"{base.rstrip('/')}/unsubscribe?e={token_for(email)}"


def unsubscribe_line(email: str, base: str | None = None) -> str:
    """The plain-text opt-out line appended to outreach emails."""
    return ("Don't want these emails? Unsubscribe instantly: "
            + unsubscribe_url(email, base))
