"""v0.23 OAuth2 routes — SSO sign-in and connector authorization.

Flow:
  /api/oauth/{provider}/login    (public)  -> 302 to provider (purpose=sso)
  /api/oauth/{provider}/connect  (staff)   -> 302 to provider (purpose=connect)
  /api/oauth/{provider}/callback (public)  -> exchange code, then either sign the
        matched user in (sso) or store an encrypted token (connect).

CSRF is enforced by a single-use server-side state row; the PKCE verifier never
leaves the server."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.db import get_db
from ...core.deps import require_roles
from ...core.security import random_token
from pydantic import BaseModel

from ...models import OAuthState, OAuthToken, Role, User
from ...services import audit, crypto, oauth, secure_config
from .auth import issue_session

router = APIRouter(prefix="/api/oauth", tags=["oauth"])
_s = get_settings()

_STATE_TTL = timedelta(minutes=10)


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _redirect_uri(request: Request, provider: str) -> str:
    return f"{_base_url(request)}/api/oauth/{provider}/callback"


# --------------------------------------------------------------------------- #
# SSO settings — configure the Microsoft/Google sign-in apps from the UI (vault).
# --------------------------------------------------------------------------- #
class SSOSettingsIn(BaseModel):
    ms_client_id: str | None = None
    ms_client_secret: str | None = None
    ms_tenant: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None


@router.get("/sso-settings")
def get_sso_settings(request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    conn = secure_config.get_platform(db, "sso_login")
    cfg = (conn.config if conn else None) or {}
    oauth.sync_vault_providers(db)
    active = {p["key"] for p in oauth.enabled_providers()}
    base = _base_url(request)
    return {
        "fields": secure_config.public_view(cfg),
        "ms_tenant": cfg.get("ms_tenant"),
        "providers_active": sorted(active),
        "redirect_uris": {
            "microsoft": f"{base}/api/oauth/microsoft/callback",
            "google": f"{base}/api/oauth/google/callback",
        },
        # convenience: Microsoft SSO can reuse the M365 mailbox app
        "microsoft_uses_mailbox": bool(
            (secure_config.get_platform(db, "m365_mailbox") or None)
            and "microsoft" in active and not cfg.get("ms_client_id")),
    }


@router.put("/sso-settings")
def save_sso_settings(body: SSOSettingsIn, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER))):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = secure_config.upsert_platform(db, "sso_login", "Single Sign-On", "Identity", payload)
    audit.record(db, action="sso.configure", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="integration", target_id=str(conn.id),
                 ip=_ip(request), detail="sso credentials")
    oauth.sync_vault_providers(db)
    return {"ok": True, "providers_active": sorted(p["key"] for p in oauth.enabled_providers())}


@router.get("/connections")
def connections(request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """One-click OAuth connect status per integration: is the app configured (so
    Connect can run) and is it currently connected (token stored)."""
    oauth.sync_connect_providers(db)
    base = _base_url(request)
    avail = {p["key"] for p in oauth.enabled_providers()}
    out = []
    for key, label in (("linkedin", "LinkedIn"), ("google_gbp", "Google Business Profile"),
                       ("quickbooks", "QuickBooks")):
        tok = (db.query(OAuthToken).filter(OAuthToken.provider == key)
               .order_by(OAuthToken.id.desc()).first())
        out.append({"key": key, "name": label, "app_configured": key in avail,
                    "connected": bool(tok),
                    "account": tok.account_email if tok else None,
                    "connect_url": f"{base}/api/oauth/{key}/connect"})
    return {"connections": out}


@router.get("/providers")
def providers(db: Session = Depends(get_db)):
    """Which SSO/connector providers are configured (drives the login buttons).
    Resolves providers from the vault first so SSO lights up from Settings."""
    oauth.sync_vault_providers(db)
    return {"providers": oauth.enabled_providers(), "sso_allowed": _s.OAUTH_ALLOW_SSO}


def _start(request: Request, db: Session, provider: str, purpose: str,
           user_id: int | None, next_url: str | None) -> RedirectResponse:
    oauth.sync_vault_providers(db)
    oauth.sync_connect_providers(db)
    if not oauth.get_provider(provider):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Provider '{provider}' is not configured")
    verifier = oauth.gen_verifier()
    state = random_token(24)
    redirect_uri = _redirect_uri(request, provider)
    db.add(OAuthState(id=state, provider=provider, purpose=purpose, code_verifier=verifier,
                      redirect_uri=redirect_uri, next_url=next_url, user_id=user_id))
    db.commit()
    url = oauth.authorize_url(provider, state=state,
                              code_challenge=oauth.challenge_s256(verifier),
                              redirect_uri=redirect_uri)
    return RedirectResponse(url, status_code=302)


@router.get("/{provider}/login")
def sso_login(provider: str, request: Request, db: Session = Depends(get_db), next: str = "/dashboard"):
    if not _s.OAUTH_ALLOW_SSO:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "SSO sign-in is disabled")
    return _start(request, db, provider, "sso", None, next)


@router.get("/{provider}/connect")
def connect(provider: str, request: Request, db: Session = Depends(get_db),
            user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    return _start(request, db, provider, "connect", user.id, "/dashboard")


def _consume_state(db: Session, provider: str, state: str) -> OAuthState:
    row = db.get(OAuthState, state)
    if not row or row.provider != provider:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > _STATE_TTL:
        db.delete(row); db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth state expired — try again")
    return row


@router.get("/{provider}/callback")
def callback(provider: str, request: Request, response: Response,
             state: str = "", code: str = "", error: str = "",
             db: Session = Depends(get_db)):
    if error:
        return RedirectResponse(f"/?oauth_error={error}", status_code=302)
    oauth.sync_vault_providers(db)   # ensure the provider config is present
    oauth.sync_connect_providers(db)
    st = _consume_state(db, provider, state)
    purpose, redirect_uri = st.purpose, st.redirect_uri
    uid, next_url, verifier = st.user_id, st.next_url, st.code_verifier
    db.delete(st)   # single use — consume before any network call
    db.commit()

    try:
        tok = oauth.exchange_code(provider, code=code, code_verifier=verifier,
                                  redirect_uri=redirect_uri)
    except Exception:
        return RedirectResponse("/?oauth_error=exchange_failed", status_code=302)
    access = tok.get("access_token")
    if not access:
        return RedirectResponse("/?oauth_error=no_token", status_code=302)
    email = oauth.fetch_email(provider, access)

    if purpose == "sso":
        if not _s.OAUTH_ALLOW_SSO:
            return RedirectResponse("/?oauth_error=sso_disabled", status_code=302)
        user = db.query(User).filter(User.email == (email or "")).first() if email else None
        if not user or not user.is_active:
            audit.record(db, action="login.oauth_no_match", actor_email=email, ip=_ip(request),
                         success=False, detail=f"provider={provider}")
            return RedirectResponse("/?oauth_error=no_account", status_code=302)
        dest = "/portal" if user.role in (Role.CLIENT_ADMIN, Role.CLIENT_VIEWER) else "/dashboard"
        redirect = RedirectResponse(dest, status_code=302)
        issue_session(db, user, request, redirect, method=f"oauth:{provider}")
        return redirect

    # purpose == "connect": store the encrypted token (with refresh) for the user.
    _store_token(db, provider, tok, user_id=uid, email=email)
    # Provider-specifics so the integration is immediately usable:
    try:
        if provider == "linkedin":
            # LinkedIn's person URN comes from userinfo `sub` — auto-fill it so the
            # publisher needs nothing typed by hand.
            info = oauth.fetch_userinfo("linkedin", access)
            sub = info.get("sub")
            if sub:
                secure_config.upsert_platform(db, "pub_linkedin", "LinkedIn Publisher", "Marketing",
                                              {"person_urn": f"urn:li:person:{sub}"})
        elif provider == "quickbooks":
            # QBO returns the company id as `realmId` on the redirect — persist it.
            realm = request.query_params.get("realmId")
            if realm:
                secure_config.upsert_platform(db, "quickbooks", "QuickBooks Online", "Accounting",
                                              {"realm_id": realm})
        elif provider == "google_gbp":
            # The Google Business poster reads the "gbp" vault entry — copy the
            # refresh token there so connecting once makes posting work (you still
            # set account_name + location_name in Settings → Google Business).
            rt = tok.get("refresh_token")
            if rt:
                secure_config.upsert_platform(db, "gbp", "Google Business Profile", "Marketing",
                                              {"refresh_token": rt})
    except Exception:
        pass
    audit.record(db, action="oauth.connected", actor_user_id=uid, actor_email=email,
                 target_type="oauth_token", ip=_ip(request), detail=f"provider={provider}")
    return RedirectResponse((next_url or "/dashboard"), status_code=302)


def _store_token(db: Session, provider: str, tok: dict, *, user_id: int | None,
                 email: str | None, client_id: int | None = None) -> OAuthToken:
    expires_at = None
    if tok.get("expires_in"):
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tok["expires_in"]))
        except Exception:
            expires_at = None
    row = OAuthToken(
        provider=provider, user_id=user_id, client_id=client_id, account_email=email,
        access_token_enc=crypto.encrypt(tok["access_token"]),
        refresh_token_enc=crypto.encrypt(tok["refresh_token"]) if tok.get("refresh_token") else None,
        scope=tok.get("scope"), expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    return row


@router.get("/tokens")
def list_tokens(db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Connected provider accounts (no secret material is ever returned)."""
    rows = db.query(OAuthToken).order_by(OAuthToken.id.desc()).all()
    return [{"id": t.id, "provider": t.provider, "account_email": t.account_email,
             "scope": t.scope, "has_refresh": bool(t.refresh_token_enc),
             "expires_at": t.expires_at.isoformat() if t.expires_at else None,
             "created_at": t.created_at.isoformat() if t.created_at else None} for t in rows]


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = db.get(OAuthToken, token_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    db.delete(t)
    db.commit()
    audit.record(db, action="oauth.disconnected", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="oauth_token", target_id=str(token_id),
                 ip=_ip(request))
