"""v0.87 Just-in-time SSO provisioning (zero-touch client logins).

When someone signs in with Microsoft/Google and no Pulse user matches, we can
create a **read-only CLIENT_VIEWER** for them automatically — but only when it's
provably safe:

  * The email domain must already "belong" to exactly one onboarded client,
    proven by an existing ACTIVE client-scoped user (the CLIENT_ADMIN created at
    onboarding) on that same domain. One anchored client → provision; zero or
    ambiguous (2+) → refuse.
  * Free/public email domains (gmail, outlook, icloud, …) never auto-provision —
    they aren't org-owned, so they can't prove membership of a client.
  * The new account is always the lowest privilege (CLIENT_VIEWER), scoped to
    that client, and SSO-only (a random password it can't know). It is never
    staff, never CLIENT_ADMIN.

This makes client SSO truly zero-touch: onboard a client once (which anchors
their domain), and every colleague on that domain can then sign in themselves as
a read-only portal user — without ever elevating anyone or letting a stranger in.

Off is one toggle away (``sso_provisioning`` vault: {"enabled": false}).
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.security import hash_password, random_token
from ..models import Role, User
from . import secure_config

PROVIDER = "sso_provisioning"

# Consumer/free mailbox domains — an address here proves nothing about a client,
# so it can never auto-provision.
_FREE_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "yahoo.com", "ymail.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "gmx.com", "gmx.net", "mail.com",
    "zoho.com", "yandex.com", "pm.me", "hey.com", "fastmail.com",
}


def _defaults() -> dict:
    return {"enabled": True}


def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    out = _defaults()
    if "enabled" in cfg:
        out["enabled"] = bool(cfg["enabled"])
    return out


def save_config(db: Session, fields: dict) -> dict:
    payload = {"enabled": bool(fields.get("enabled", get_config(db)["enabled"]))}
    secure_config.upsert_platform(db, PROVIDER, "SSO Provisioning", "Identity", payload)
    return get_config(db)


def _domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    dom = email.rsplit("@", 1)[-1].strip().lower()
    return dom or None


def _anchor_client_id(db: Session, domain: str) -> int | None:
    """The single onboarded client whose domain this is, proven by an existing
    active client-scoped user on that exact domain. Returns None if there is no
    anchor or the domain spans more than one client (ambiguous → refuse)."""
    rows = (db.query(User)
            .filter(User.is_active.is_(True),
                    User.client_id.isnot(None),
                    User.role.in_([Role.CLIENT_ADMIN, Role.CLIENT_VIEWER]),
                    func.lower(User.email).like(f"%@{domain}"))
            .all())
    client_ids = set()
    for u in rows:
        # LIKE is a prefilter; confirm the exact domain in Python.
        if _domain(u.email) == domain and u.client_id is not None:
            client_ids.add(u.client_id)
    if len(client_ids) == 1:
        return next(iter(client_ids))
    return None


def maybe_autoprovision(db: Session, email: str | None, *, full_name: str | None = None):
    """Create a read-only CLIENT_VIEWER for `email` iff it's provably safe.
    Returns the new User, or None (caller then falls back to 'no account')."""
    if not get_config(db).get("enabled"):
        return None
    email = (email or "").strip().lower()
    dom = _domain(email)
    if not dom or dom in _FREE_DOMAINS:
        return None
    # Someone with this exact email already exists — never our job to create.
    if db.query(User).filter(func.lower(User.email) == email).first():
        return None
    client_id = _anchor_client_id(db, dom)
    if client_id is None:
        return None
    user = User(
        email=email,
        full_name=(full_name or email.split("@")[0])[:200],
        password_hash=hash_password(random_token(24)),   # SSO-only; unknown password
        role=Role.CLIENT_VIEWER,                          # lowest privilege, always
        client_id=client_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
