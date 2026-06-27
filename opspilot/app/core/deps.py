"""Auth & RBAC dependencies.

current_user()      -> resolves the access-token cookie/header to a User
require_roles(...)  -> guard factory
enforce_client_scope-> client users can only touch their own client_id
"""
from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .db import get_db
from .security import decode_token
from ..models import AuthSession, Role, User, STAFF_ROLES


def _extract_token(
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    if access_token:
        return access_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def current_user(
    token: str = Depends(_extract_token),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if payload.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    sid = payload.get("sid")
    sess = db.get(AuthSession, sid) if sid else None
    if not sess or sess.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")

    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user


def require_roles(*roles: Role):
    allowed = set(roles)

    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return guard


def is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def assert_client_access(user: User, client_id: int) -> None:
    """Staff may access any client; client users only their own."""
    if is_staff(user):
        return
    if user.client_id != client_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Outside your client scope")
