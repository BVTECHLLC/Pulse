"""Auth & RBAC dependencies.

current_user()      -> resolves the access-token cookie/header to a User
require_roles(...)  -> guard factory
enforce_client_scope-> client users can only touch their own client_id
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .db import get_db
from .security import decode_token, hash_api_key
from ..models import APIKey, AuthSession, Role, User, STAFF_ROLES


def _resolve_api_key(db: Session, key: str) -> User | None:
    """Resolve an X-API-Key value to its owning user. The key authenticates as
    that user (inheriting role + client scope). Updates last_used_at."""
    row = (db.query(APIKey)
           .filter(APIKey.key_hash == hash_api_key(key), APIKey.revoked.is_(False))
           .first())
    if not row:
        return None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return user


def current_user(
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> User:
    # 1) Programmatic access via an API key (for external tools / integrations).
    if x_api_key:
        user = _resolve_api_key(db, x_api_key)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        return user

    # 2) Session token (cookie or Bearer).
    if access_token:
        token = access_token
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

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
