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
from ..models import Client, Role, User
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


def normalize_domains(value) -> list[str]:
    """Clean a user-supplied domain list/string into lowercased bare domains.
    Accepts a list or a comma/space/newline-separated string; strips a leading
    '@' or 'https://' and any path so 'https://Acme.COM/' -> 'acme.com'."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace("\n", ",").replace(" ", ",").split(",")
    else:
        parts = list(value)
    out: list[str] = []
    for p in parts:
        d = str(p or "").strip().lower()
        if not d:
            continue
        d = d.split("://", 1)[-1]        # drop scheme
        d = d.split("/", 1)[0]           # drop path
        d = d.lstrip("@").strip(".")
        if "." in d and d not in out and d not in _FREE_DOMAINS:
            out.append(d)
    return out


def _explicit_client_ids(db: Session, domain: str) -> set[int]:
    """Clients that have explicitly authorized this domain in Client.sso_domains."""
    ids: set[int] = set()
    # sso_domains is small JSON per row; scan active clients that have any set.
    for c in db.query(Client).filter(Client.is_active.is_(True)).all():
        doms = c.sso_domains or []
        if isinstance(doms, list) and domain in [str(d).strip().lower() for d in doms]:
            ids.add(c.id)
    return ids


def _anchor_client_id(db: Session, domain: str) -> int | None:
    """The single client this domain belongs to. Two independent signals:
      1. an EXPLICIT authorization in Client.sso_domains (owner opted the domain
         in — works even before anyone from the client has logged in), or
      2. an existing active client user already on that exact domain (implicit
         anchor from onboarding).
    Explicit wins outright when unambiguous. Otherwise we fall back to the
    implicit anchor. Any ambiguity (the domain maps to >1 client) → refuse."""
    explicit = _explicit_client_ids(db, domain)
    if len(explicit) == 1:
        return next(iter(explicit))
    if len(explicit) > 1:
        return None   # two clients both claim the domain — refuse

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
        provisioned_via="sso",                            # flagged for the admin view
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def maybe_staff_autoprovision(db: Session, email: str | None, *,
                              full_name: str | None = None):
    """Sign your OWN team in with company SSO. If `email` is on one of your staff
    domains (config.staff_sso_domains) and no user exists yet, create a staff
    account: OWNER for the bootstrap-admin address, TECH for everyone else on the
    domain. Returns the User, or None. Safe because only you control accounts on
    your domain in your IdP — a domain match is a teammate, not a stranger."""
    from ..core.config import get_settings
    s = get_settings()
    if not s.STAFF_SSO_AUTO_PROVISION:
        return None
    email = (email or "").strip().lower()
    dom = _domain(email)
    if not dom or dom in _FREE_DOMAINS or dom not in s.staff_sso_domains():
        return None
    if db.query(User).filter(func.lower(User.email) == email).first():
        return None
    is_admin = email == (s.BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
    user = User(
        email=email,
        full_name=(full_name or email.split("@")[0])[:200],
        password_hash=hash_password(random_token(24)),   # SSO-only
        role=Role.OWNER if is_admin else Role.TECH,       # admin -> full access; else operational
        client_id=None,                                   # staff are not client-scoped
        is_active=True,
        provisioned_via="sso",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
