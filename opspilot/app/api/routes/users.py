"""v0.88 Users & Access management — staff directory + safe lifecycle actions.

Read is OWNER/TECH. Mutations (role, active, password reset) are OWNER-only:
they change who can access client data, so they sit with the account owner.
All guardrails live in services.user_admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Role, User
from ...services import audit, email as email_svc, user_admin

router = APIRouter(prefix="/api/users", tags=["users"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _guard(fn):
    try:
        return fn()
    except user_admin.UserAdminError as e:
        raise HTTPException(e.code, e.message)


@router.get("")
def list_users(client_id: int | None = None, role: str | None = None,
               sso_only: bool = False, include_inactive: bool = True, q: str | None = None,
               db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    users = _guard(lambda: user_admin.list_users(
        db, client_id=client_id, role=role, sso_only=sso_only,
        include_inactive=include_inactive, q=q))
    return {"users": users, "summary": user_admin.summary(db)}


class RoleIn(BaseModel):
    role: str


@router.patch("/{user_id}/role")
def set_role(user_id: int, body: RoleIn, request: Request, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.OWNER))):
    out = _guard(lambda: user_admin.set_role(db, user, user_id, body.role))
    audit.record(db, action="user.set_role", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="user", target_id=str(user_id),
                 client_id=out.get("client_id"), ip=_ip(request), detail=f"role={out['role']}")
    return out


class ActiveIn(BaseModel):
    active: bool


@router.patch("/{user_id}/active")
def set_active(user_id: int, body: ActiveIn, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.OWNER))):
    out = _guard(lambda: user_admin.set_active(db, user, user_id, body.active))
    audit.record(db, action="user.set_active", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="user", target_id=str(user_id),
                 client_id=out.get("client_id"), ip=_ip(request),
                 detail=f"active={out['is_active']}")
    return out


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER))):
    out, temp_pw = _guard(lambda: user_admin.reset_password(db, user, user_id))
    emailed = False
    try:
        emailed = email_svc.send_invite(out["email"], out.get("full_name"), temp_pw, out["role"])
    except Exception:
        emailed = False
    audit.record(db, action="user.reset_password", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="user", target_id=str(user_id),
                 client_id=out.get("client_id"), ip=_ip(request), detail="password reset issued")
    return {**out, "temp_password": temp_pw, "emailed": emailed}
