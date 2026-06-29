"""Unit tests for app/core/deps.py — authentication, RBAC, and tenant scoping.

This is multi-tenant SaaS: a scope bug leaks one client's data to another, so
the authz primitives are tested directly (calling the dependency functions with
explicit args rather than going through HTTP).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core import deps
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import AuthSession, Role


# --------------------------------------------------------------------------- #
# is_staff / assert_client_access — tenant isolation
# --------------------------------------------------------------------------- #
def test_is_staff(make_user):
    assert deps.is_staff(make_user(role=Role.OWNER)) is True
    assert deps.is_staff(make_user(role=Role.TECH)) is True
    assert deps.is_staff(make_user(role=Role.CLIENT_ADMIN, client_id=1)) is False
    assert deps.is_staff(make_user(role=Role.CLIENT_VIEWER, client_id=1)) is False


def test_staff_can_access_any_client(make_user):
    staff = make_user(role=Role.OWNER)
    deps.assert_client_access(staff, client_id=1)
    deps.assert_client_access(staff, client_id=999)  # no raise


def test_client_user_can_access_own_client(make_user):
    user = make_user(role=Role.CLIENT_ADMIN, client_id=5)
    deps.assert_client_access(user, client_id=5)  # no raise


def test_client_user_cannot_access_other_client(make_user):
    user = make_user(role=Role.CLIENT_VIEWER, client_id=5)
    with pytest.raises(HTTPException) as ei:
        deps.assert_client_access(user, client_id=6)
    assert ei.value.status_code == 403


# --------------------------------------------------------------------------- #
# require_roles — guard factory
# --------------------------------------------------------------------------- #
def test_require_roles_allows_listed_role(make_user):
    guard = deps.require_roles(Role.OWNER, Role.TECH)
    owner = make_user(role=Role.OWNER)
    assert guard(user=owner) is owner


def test_require_roles_blocks_unlisted_role(make_user):
    guard = deps.require_roles(Role.OWNER)
    tech = make_user(role=Role.TECH)
    with pytest.raises(HTTPException) as ei:
        guard(user=tech)
    assert ei.value.status_code == 403


# --------------------------------------------------------------------------- #
# current_user — session-token path
# --------------------------------------------------------------------------- #
# NOTE: when a FastAPI dependency is called directly (not through the framework),
# its Cookie()/Header() defaults are FieldInfo objects, not None — so every auth
# argument must be passed explicitly, using None for the ones not under test.
def _call(db, *, access_token=None, authorization=None, x_api_key=None):
    return deps.current_user(db=db, access_token=access_token,
                             authorization=authorization, x_api_key=x_api_key)


def test_current_user_via_cookie_token(db, make_user, login):
    user = make_user(role=Role.OWNER)
    token, _ = login(user)
    resolved = _call(db, access_token=token)
    assert resolved.id == user.id


def test_current_user_via_bearer_header(db, make_user, login):
    user = make_user(role=Role.TECH)
    token, _ = login(user)
    resolved = _call(db, authorization=f"Bearer {token}")
    assert resolved.id == user.id


def test_current_user_no_credentials_is_401(db):
    with pytest.raises(HTTPException) as ei:
        _call(db)
    assert ei.value.status_code == 401


def test_current_user_garbage_token_is_401(db):
    with pytest.raises(HTTPException) as ei:
        _call(db, access_token="not.a.jwt")
    assert ei.value.status_code == 401


def test_current_user_revoked_session_is_401(db, make_user, login):
    user = make_user(role=Role.OWNER)
    token, sess = login(user)
    sess.revoked = True
    db.commit()
    with pytest.raises(HTTPException) as ei:
        _call(db, access_token=token)
    assert ei.value.status_code == 401


def test_current_user_inactive_user_is_401(db, make_user, login):
    user = make_user(role=Role.OWNER)
    token, _ = login(user)
    user.is_active = False
    db.commit()
    with pytest.raises(HTTPException) as ei:
        _call(db, access_token=token)
    assert ei.value.status_code == 401


def test_current_user_rejects_wrong_token_type(db, make_user):
    """An enrollment-typed token must not authenticate a user session."""
    user = make_user(role=Role.OWNER)
    sid = "sid-typ"
    db.add(AuthSession(id=sid, user_id=user.id, refresh_hash="x" * 16,
                       expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    db.commit()
    s = get_settings()
    wrong_typ = jwt.encode(
        {"sub": str(user.id), "role": "owner", "sid": sid, "typ": "enroll",
         "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        s.SECRET_KEY, algorithm="HS256",
    )
    with pytest.raises(HTTPException) as ei:
        _call(db, access_token=wrong_typ)
    assert ei.value.status_code == 401


def test_current_user_expired_token_is_401(db, make_user, login):
    user = make_user(role=Role.OWNER)
    _, sess = login(user)
    s = get_settings()
    expired = jwt.encode(
        {"sub": str(user.id), "role": "owner", "sid": sess.id, "typ": "access",
         "iat": datetime.now(timezone.utc) - timedelta(hours=2),
         "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        s.SECRET_KEY, algorithm="HS256",
    )
    with pytest.raises(HTTPException) as ei:
        _call(db, access_token=expired)
    assert ei.value.status_code == 401


# --------------------------------------------------------------------------- #
# current_user — API-key path
# --------------------------------------------------------------------------- #
def test_current_user_via_api_key(db, make_user, make_api_key):
    user = make_user(role=Role.TECH)
    key = make_api_key(user)
    resolved = _call(db, x_api_key=key)
    assert resolved.id == user.id


def test_api_key_updates_last_used_at(db, make_user, make_api_key):
    from app.models import APIKey
    user = make_user(role=Role.TECH)
    key = make_api_key(user)
    _call(db, x_api_key=key)
    row = db.query(APIKey).filter(APIKey.user_id == user.id).first()
    assert row.last_used_at is not None


def test_revoked_api_key_is_401(db, make_user, make_api_key):
    user = make_user(role=Role.TECH)
    key = make_api_key(user, revoked=True)
    with pytest.raises(HTTPException) as ei:
        _call(db, x_api_key=key)
    assert ei.value.status_code == 401


def test_api_key_for_inactive_user_is_401(db, make_user, make_api_key):
    user = make_user(role=Role.TECH, is_active=False)
    key = make_api_key(user)
    with pytest.raises(HTTPException) as ei:
        _call(db, x_api_key=key)
    assert ei.value.status_code == 401


def test_unknown_api_key_is_401(db):
    with pytest.raises(HTTPException) as ei:
        _call(db, x_api_key="pk_live_does_not_exist")
    assert ei.value.status_code == 401
