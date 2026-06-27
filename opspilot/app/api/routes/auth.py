"""Authentication endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.db import get_db
from ...core.deps import current_user
from ...core.security import (
    create_access_token, generate_totp_secret, hash_password, needs_rehash,
    random_token, totp_provisioning_uri, verify_password, verify_totp,
)
from ...models import AuthSession, User
from ...services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])
_s = get_settings()


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


def _client_ip(req: Request) -> str:
    # Cloudflare passes the real client IP here.
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _set_cookies(resp: Response, access: str, refresh: str) -> None:
    resp.set_cookie(
        "access_token", access, httponly=True, secure=_s.COOKIE_SECURE,
        samesite="lax", max_age=_s.ACCESS_TOKEN_TTL_MIN * 60, domain=_s.COOKIE_DOMAIN,
    )
    resp.set_cookie(
        "refresh_token", refresh, httponly=True, secure=_s.COOKIE_SECURE,
        samesite="lax", max_age=_s.REFRESH_TOKEN_TTL_DAYS * 86400,
        path="/api/auth", domain=_s.COOKIE_DOMAIN,
    )


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    user = db.query(User).filter(User.email == body.email.lower()).first()

    # Constant-ish failure path; never reveal which factor failed.
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        audit.record(db, action="login.fail", actor_email=body.email.lower(), ip=ip, success=False)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if user.mfa_enabled:
        if not body.mfa_code:
            # Signal the client to collect a code, without leaking validity.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code required")
        if not verify_totp(user.mfa_secret or "", body.mfa_code):
            audit.record(db, action="login.mfa_fail", actor_user_id=user.id,
                         actor_email=user.email, ip=ip, success=False)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid MFA code")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    # Create DB-backed session
    sid = random_token(16)
    refresh = random_token(32)
    sess = AuthSession(
        id=sid, user_id=user.id, refresh_hash=hash_password(refresh),
        user_agent=request.headers.get("user-agent", "")[:400], ip=ip,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_s.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(sess)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    access = create_access_token(user_id=user.id, role=user.role.value, session_id=sid)
    _set_cookies(response, access, f"{sid}.{refresh}")
    audit.record(db, action="login.success", actor_user_id=user.id,
                 actor_email=user.email, actor_role=user.role.value, ip=ip)
    return {"ok": True, "role": user.role.value, "mfa_enabled": user.mfa_enabled}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    # Revoke all sessions for this user (logout-everywhere is the safe default).
    db.query(AuthSession).filter(AuthSession.user_id == user.id).update({"revoked": True})
    db.commit()
    response.delete_cookie("access_token", domain=_s.COOKIE_DOMAIN)
    response.delete_cookie("refresh_token", path="/api/auth", domain=_s.COOKIE_DOMAIN)
    audit.record(db, action="logout", actor_user_id=user.id, actor_email=user.email,
                 ip=_client_ip(request))
    return {"ok": True}


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(db: Session = Depends(get_db), user: User = Depends(current_user)):
    secret = generate_totp_secret()
    user.mfa_secret = secret  # not enabled until confirmed
    db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=totp_provisioning_uri(secret, user.email))


class MfaConfirmIn(BaseModel):
    code: str


@router.post("/mfa/confirm")
def mfa_confirm(body: MfaConfirmIn, request: Request,
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not user.mfa_secret or not verify_totp(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code did not verify")
    user.mfa_enabled = True
    db.commit()
    audit.record(db, action="mfa.enabled", actor_user_id=user.id,
                 actor_email=user.email, ip=_client_ip(request))
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name,
        "role": user.role.value, "client_id": user.client_id,
        "mfa_enabled": user.mfa_enabled,
    }
