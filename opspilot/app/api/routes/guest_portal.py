"""Partner / Helper portal — a strictly scoped, read-only window for external
collaborators (Fiverr, LinkedIn, referral partners like Jahid Hasan).

Security model (defense in depth):
  * A GUEST is the lowest-privilege role. It owns NO client, devices, settings,
    scripts, billing — nothing. Every other router requires OWNER/TECH or a
    client scope, none of which a GUEST has, so they 403 by construction.
  * The ONLY thing a guest can do is read mail where from/to/cc is in an
    OWNER-defined allow-list (GuestScope.allowed_emails). That list lives
    server-side; the guest can never read, widen, or bypass it.
  * Reads are enforced twice: a Graph `participants:` $search that only asks for
    matching mail, and a hard in-code intersection check (see m365.py).
  * Read-only: there is no send / delete / reply / settings surface at all.
  * Every access is audited.
"""
from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import current_user, require_roles
from ...core.security import hash_password
from ...models import AuthSession, GuestScope, Role, User
from ...services import audit, m365, secure_config

router = APIRouter(prefix="/api/guest", tags=["guest-portal"])

PROVIDER = "m365_mailbox"
_REQUIRED = ("tenant_id", "client_id", "client_secret")


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _graph_for(db: Session, scope: GuestScope) -> tuple[m365.GraphClient, str]:
    """Build the shared-mailbox Graph client from the OWNER's stored platform
    credentials. The guest never sees or supplies any of this."""
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    if not secure_config.configured(cfg, _REQUIRED):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The mailbox isn't connected yet — ask BVTech to finish Settings → Mailbox.")
    tenant = secure_config.get_secret(cfg, "tenant_id") or cfg.get("tenant_id")
    client_id = secure_config.get_secret(cfg, "client_id") or cfg.get("client_id")
    client_secret = secure_config.get_secret(cfg, "client_secret")
    mailbox = (scope.mailbox or cfg.get("mailbox") or "").strip()
    if not mailbox:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No mailbox configured.")
    return m365.GraphClient(str(tenant), str(client_id), str(client_secret)), mailbox


# --------------------------------------------------------------------------- #
# Guest-facing (role = GUEST only)
# --------------------------------------------------------------------------- #
def require_guest(db: Session = Depends(get_db),
                 user: User = Depends(current_user)) -> tuple[User, GuestScope]:
    if user.role != Role.GUEST:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a helper account.")
    scope = db.query(GuestScope).filter(GuestScope.user_id == user.id).first()
    if not scope or not scope.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Your helper access is not active. Please contact BVTech.")
    return user, scope


@router.get("/me")
def guest_me(ctx: tuple[User, GuestScope] = Depends(require_guest)):
    user, scope = ctx
    lmap = scope.label_map()
    leads = [{"email": e, "label": lmap.get(e, e)} for e in scope.emails()]
    return {
        "email": user.email,
        "name": user.full_name or user.email.split("@")[0],
        "label": scope.label or "Referral partner",
        "can_view_body": bool(scope.can_view_body),
        "leads": leads,
        "lead_count": len(leads),
    }


@router.get("/messages")
def guest_messages(request: Request, lead: str | None = Query(None),
                   ctx: tuple[User, GuestScope] = Depends(require_guest),
                   db: Session = Depends(get_db)):
    user, scope = ctx
    allowed = set(scope.emails())
    if not allowed:
        return {"messages": [], "lead": None}
    # If a specific lead is requested it MUST be in the allow-list — never trust
    # the parameter to widen scope.
    if lead:
        lead = lead.strip().lower()
        if lead not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "That contact isn't in your list.")
        allowed = {lead}
    graph, mailbox = _graph_for(db, scope)
    try:
        msgs = graph.list_scoped_messages(mailbox, allowed, top=50)
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Mailbox read failed: {e}")
    if not scope.can_view_body:
        for m in msgs:
            m.pop("preview", None)
    audit.record(db, action="guest.messages", actor_user_id=user.id, actor_email=user.email,
                 actor_role="guest", ip=_ip(request),
                 detail=f"lead={lead or 'all'} n={len(msgs)}")
    return {"messages": msgs, "lead": lead, "count": len(msgs)}


@router.get("/messages/{message_id}")
def guest_message(message_id: str, request: Request,
                  ctx: tuple[User, GuestScope] = Depends(require_guest),
                  db: Session = Depends(get_db)):
    user, scope = ctx
    allowed = set(scope.emails())
    graph, mailbox = _graph_for(db, scope)
    try:
        msg = graph.get_message_if_allowed(mailbox, message_id, allowed,
                                           include_body=bool(scope.can_view_body))
    except m365.GraphError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Mailbox read failed: {e}")
    if not msg:
        # 404, not 403 — don't confirm an out-of-scope message even exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found.")
    audit.record(db, action="guest.message.open", actor_user_id=user.id, actor_email=user.email,
                 actor_role="guest", ip=_ip(request), detail=f"id={message_id[:24]}")
    return msg


# --------------------------------------------------------------------------- #
# Owner admin: manage helpers (OWNER only)
# --------------------------------------------------------------------------- #
class InviteIn(BaseModel):
    email: EmailStr
    label: str | None = None
    allowed_emails: list[str] = []
    labels: dict[str, str] = {}
    can_view_body: bool = True
    mailbox: str | None = None


def _clean_emails(items: list[str]) -> list[str]:
    seen, out = set(), []
    for raw in items or []:
        e = (raw or "").strip().lower()
        if "@" in e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _scope_summary(db: Session, scope: GuestScope) -> dict:
    u = db.get(User, scope.user_id)
    return {
        "user_id": scope.user_id,
        "email": u.email if u else "?",
        "name": (u.full_name if u else None) or "",
        "label": scope.label or "",
        "active": bool(scope.active and (u.is_active if u else False)),
        "can_view_body": bool(scope.can_view_body),
        "lead_count": len(scope.emails()),
        "leads": scope.emails(),
        "mailbox": scope.mailbox or "",
    }


@router.get("/admin/list")
def admin_list(db: Session = Depends(get_db),
               owner: User = Depends(require_roles(Role.OWNER))):
    rows = db.query(GuestScope).all()
    return {"helpers": [_scope_summary(db, s) for s in rows]}


@router.post("/admin/invite")
def admin_invite(body: InviteIn, request: Request, db: Session = Depends(get_db),
                 owner: User = Depends(require_roles(Role.OWNER))):
    email = str(body.email).strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing and existing.role != Role.GUEST:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That email already belongs to a non-helper account.")
    temp = secrets.token_urlsafe(9)
    if existing:
        user = existing
        user.password_hash = hash_password(temp)
        user.is_active = True
        user.full_name = body.label or user.full_name
    else:
        user = User(email=email, full_name=(body.label or email.split("@")[0])[:200],
                    password_hash=hash_password(temp), role=Role.GUEST,
                    client_id=None, is_active=True, provisioned_via="invite")
        db.add(user)
        db.flush()
    scope = db.query(GuestScope).filter(GuestScope.user_id == user.id).first()
    if not scope:
        scope = GuestScope(user_id=user.id, created_by=owner.id)
        db.add(scope)
    scope.label = body.label or scope.label
    scope.allowed_emails = json.dumps(_clean_emails(body.allowed_emails))
    scope.labels = json.dumps({k.strip().lower(): v for k, v in (body.labels or {}).items() if k.strip()})
    scope.can_view_body = bool(body.can_view_body)
    scope.mailbox = (body.mailbox or "").strip() or None
    scope.active = True
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001 — surface a real reason, never a bare 500
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Could not save helper (database): {type(e).__name__}. "
                            "If this persists, the server may need a restart to finish a schema update.")
    audit.record(db, action="guest.invited", actor_user_id=owner.id, actor_email=owner.email,
                 actor_role=owner.role.value, ip=_ip(request),
                 target_type="guest", target_id=str(user.id),
                 detail=f"email={email} leads={len(scope.emails())}")
    return {"ok": True, "email": email, "temp_password": temp,
            "login_url": "/login?as=helper",
            "lead_count": len(scope.emails())}


@router.post("/admin/{user_id}/reset")
def admin_reset(user_id: int, request: Request, db: Session = Depends(get_db),
                owner: User = Depends(require_roles(Role.OWNER))):
    user = db.get(User, user_id)
    if not user or user.role != Role.GUEST:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Helper not found.")
    temp = secrets.token_urlsafe(9)
    user.password_hash = hash_password(temp)
    # New password everywhere → revoke any live sessions.
    db.query(AuthSession).filter(AuthSession.user_id == user.id).update({"revoked": True})
    db.commit()
    audit.record(db, action="guest.reset", actor_user_id=owner.id, actor_email=owner.email,
                 actor_role=owner.role.value, ip=_ip(request), target_type="guest",
                 target_id=str(user.id))
    return {"ok": True, "email": user.email, "temp_password": temp, "login_url": "/login?as=helper"}


class ActiveIn(BaseModel):
    active: bool


@router.post("/admin/{user_id}/active")
def admin_active(user_id: int, body: ActiveIn, request: Request, db: Session = Depends(get_db),
                 owner: User = Depends(require_roles(Role.OWNER))):
    user = db.get(User, user_id)
    scope = db.query(GuestScope).filter(GuestScope.user_id == user_id).first()
    if not user or user.role != Role.GUEST or not scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Helper not found.")
    scope.active = bool(body.active)
    user.is_active = bool(body.active)
    if not body.active:
        db.query(AuthSession).filter(AuthSession.user_id == user.id).update({"revoked": True})
    db.commit()
    audit.record(db, action="guest.active", actor_user_id=owner.id, actor_email=owner.email,
                 actor_role=owner.role.value, ip=_ip(request), target_type="guest",
                 target_id=str(user.id), detail=f"active={body.active}")
    return {"ok": True, "active": scope.active}


class ScopeIn(BaseModel):
    allowed_emails: list[str] | None = None
    labels: dict[str, str] | None = None
    can_view_body: bool | None = None
    label: str | None = None


@router.post("/admin/{user_id}/scope")
def admin_scope(user_id: int, body: ScopeIn, request: Request, db: Session = Depends(get_db),
                owner: User = Depends(require_roles(Role.OWNER))):
    scope = db.query(GuestScope).filter(GuestScope.user_id == user_id).first()
    if not scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Helper not found.")
    if body.allowed_emails is not None:
        scope.allowed_emails = json.dumps(_clean_emails(body.allowed_emails))
    if body.labels is not None:
        scope.labels = json.dumps({k.strip().lower(): v for k, v in body.labels.items() if k.strip()})
    if body.can_view_body is not None:
        scope.can_view_body = bool(body.can_view_body)
    if body.label is not None:
        scope.label = body.label
    db.commit()
    audit.record(db, action="guest.scope", actor_user_id=owner.id, actor_email=owner.email,
                 actor_role=owner.role.value, ip=_ip(request), target_type="guest",
                 target_id=str(user_id), detail=f"leads={len(scope.emails())}")
    return {"ok": True, "lead_count": len(scope.emails())}
