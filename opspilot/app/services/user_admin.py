"""v0.88 Users & Access administration.

A staff-facing directory of every login (staff + client users), with the safe
lifecycle actions an MSP needs: promote/demote a client user between viewer and
admin, activate/deactivate, and issue a password reset. SSO self-registrations
(v0.87) are flagged so the owner has clean oversight of everyone who came in the
zero-touch door.

Guardrails live here (not in the route) so every caller is protected:
  * You cannot change or deactivate your own account through this surface.
  * Staff/OWNER accounts are not editable here — this manages CLIENT users only,
    so an MSP admin panel can never accidentally elevate someone to staff or lock
    out the owner. (Staff are managed by the platform operator directly.)
  * Role changes are constrained to CLIENT_ADMIN <-> CLIENT_VIEWER.
  * You never deactivate the last active OWNER.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core.security import hash_password, random_token
from ..models import Client, Role, STAFF_ROLES, User

_CLIENT_ROLES = {Role.CLIENT_ADMIN, Role.CLIENT_VIEWER}


class UserAdminError(Exception):
    """Raised with a human message + HTTP-ish code for the route to surface."""
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def serialize(u: User, *, client_name: str | None = None) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role.value,
        "is_staff": u.role in STAFF_ROLES,
        "client_id": u.client_id,
        "client_name": client_name,
        "is_active": u.is_active,
        "provisioned_via": u.provisioned_via,   # "sso" or None
        "sso_provisioned": u.provisioned_via == "sso",
        "mfa_enabled": bool(u.mfa_enabled),
        "last_login_at": _aware(u.last_login_at).isoformat() if u.last_login_at else None,
        "created_at": _aware(u.created_at).isoformat() if u.created_at else None,
    }


def list_users(db: Session, *, client_id: int | None = None, role: str | None = None,
               sso_only: bool = False, include_inactive: bool = True,
               q: str | None = None) -> list[dict]:
    query = db.query(User)
    if client_id is not None:
        query = query.filter(User.client_id == client_id)
    if role:
        try:
            query = query.filter(User.role == Role(role))
        except ValueError:
            raise UserAdminError(f"Unknown role '{role}'", 400)
    if sso_only:
        query = query.filter(User.provisioned_via == "sso")
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    if q:
        like = f"%{q.strip().lower()}%"
        from sqlalchemy import func, or_
        query = query.filter(or_(func.lower(User.email).like(like),
                                 func.lower(func.coalesce(User.full_name, "")).like(like)))
    users = query.order_by(User.is_active.desc(), User.email).all()
    # resolve client names in one pass
    names: dict[int, str] = {}
    cids = {u.client_id for u in users if u.client_id}
    if cids:
        for c in db.query(Client).filter(Client.id.in_(cids)).all():
            names[c.id] = c.name
    return [serialize(u, client_name=names.get(u.client_id)) for u in users]


def _load_editable_client_user(db: Session, actor: User, user_id: int) -> User:
    target = db.get(User, user_id)
    if not target:
        raise UserAdminError("User not found", 404)
    if target.id == actor.id:
        raise UserAdminError("You cannot modify your own account here", 400)
    if target.role in STAFF_ROLES:
        raise UserAdminError("Staff accounts are not managed from this panel", 403)
    if target.role not in _CLIENT_ROLES:
        raise UserAdminError("Only client users can be managed here", 400)
    return target


def set_role(db: Session, actor: User, user_id: int, role: str) -> dict:
    target = _load_editable_client_user(db, actor, user_id)
    try:
        new_role = Role(role)
    except ValueError:
        raise UserAdminError(f"Unknown role '{role}'", 400)
    if new_role not in _CLIENT_ROLES:
        raise UserAdminError("Role must be client_admin or client_viewer", 400)
    target.role = new_role
    # A promoted user is now a "real" managed account — clear the auto-provision
    # flag so it stops showing as a self-registered viewer.
    if new_role == Role.CLIENT_ADMIN and target.provisioned_via == "sso":
        target.provisioned_via = None
    db.commit()
    db.refresh(target)
    return serialize(target)


def set_active(db: Session, actor: User, user_id: int, active: bool) -> dict:
    target = _load_editable_client_user(db, actor, user_id)
    target.is_active = bool(active)
    db.commit()
    db.refresh(target)
    return serialize(target)


def reset_password(db: Session, actor: User, user_id: int) -> tuple[dict, str]:
    """Issue a fresh temporary password for a client user. Returns (user, temp_pw);
    the route emails it and shows it once."""
    target = _load_editable_client_user(db, actor, user_id)
    temp_pw = random_token(12)
    target.password_hash = hash_password(temp_pw)
    target.is_active = True   # a reset re-enables the login
    db.commit()
    db.refresh(target)
    return serialize(target), temp_pw


def summary(db: Session) -> dict:
    """Counts for the header: total, staff, client admins, viewers, SSO-provisioned,
    inactive."""
    from sqlalchemy import func
    rows = db.query(User.role, User.is_active, User.provisioned_via).all()
    total = len(rows)
    staff = sum(1 for r in rows if r[0] in STAFF_ROLES)
    admins = sum(1 for r in rows if r[0] == Role.CLIENT_ADMIN)
    viewers = sum(1 for r in rows if r[0] == Role.CLIENT_VIEWER)
    sso = sum(1 for r in rows if r[2] == "sso")
    inactive = sum(1 for r in rows if not r[1])
    return {"total": total, "staff": staff, "client_admins": admins,
            "client_viewers": viewers, "sso_provisioned": sso, "inactive": inactive}
