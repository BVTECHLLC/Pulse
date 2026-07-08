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
from sqlalchemy import func
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
        "ms_tenant_effective": oauth.normalize_tenant(cfg.get("ms_tenant") or _s.MS_OAUTH_TENANT),
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


class ProvisionIn(BaseModel):
    enabled: bool


@router.get("/sso-provisioning")
def get_sso_provisioning(db: Session = Depends(get_db),
                         user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    from ...services import sso_provision
    return sso_provision.get_config(db)


@router.put("/sso-provisioning")
def save_sso_provisioning(body: ProvisionIn, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(require_roles(Role.OWNER))):
    from ...services import sso_provision
    out = sso_provision.save_config(db, {"enabled": body.enabled})
    audit.record(db, action="sso.provisioning", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="sso_provisioning", ip=_ip(request),
                 detail=f"enabled={out['enabled']}")
    return out


@router.get("/sso-diagnostics")
def sso_diagnostics(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Show, in plain language, exactly what SSO sign-in needs and what the last
    attempt actually returned — so "the portal doesn't know who I am" becomes a
    visible, fixable checklist instead of a mystery.

    The key line is the last failed attempt: it tells you the exact email
    Microsoft/Google handed us and whether a Pulse login exists for it (SSO only
    signs in an already-provisioned user; it never creates accounts)."""
    from ...models import AuditLog
    oauth.sync_vault_providers(db)
    active = {p["key"] for p in oauth.enabled_providers()}
    base = _base_url(request)

    sso = secure_config.get_platform(db, "sso_login")
    sso_cfg = (sso.config if sso else None) or {}
    mbox = secure_config.get_platform(db, "m365_mailbox")
    reuses_mailbox = bool(mbox and "microsoft" in active and not sso_cfg.get("ms_client_id"))
    eff_tenant = oauth.normalize_tenant(sso_cfg.get("ms_tenant") or _s.MS_OAUTH_TENANT)

    def _user_for(email: str | None):
        if not email or "@" not in email:
            return None
        return (db.query(User).filter(func.lower(User.email) == email.strip().lower()).first())

    # Most recent failed + successful SSO attempts (either provider). "Failed"
    # covers both no-account-match and a token-exchange error (bad/expired secret,
    # redirect/PKCE mismatch) so the panel explains either failure mode.
    last_fail = (db.query(AuditLog)
                 .filter(AuditLog.action.in_(["login.oauth_no_match",
                                              "login.oauth_exchange_failed"]))
                 .order_by(AuditLog.ts.desc()).first())
    last_ok = (db.query(AuditLog).filter(AuditLog.action == "login.oauth_success")
               .order_by(AuditLog.ts.desc()).first())

    fail_view = None
    if last_fail and last_fail.action == "login.oauth_exchange_failed":
        # Token exchange blew up before we ever saw an email. The detail carries
        # the provider's own reason (e.g. AADSTS7000215 invalid_client).
        d = last_fail.detail or ""
        invalid_secret = "invalid_client" in d or "7000215" in d
        redirect_pkce = "invalid_grant" in d or "redirect" in d.lower()
        fail_view = {
            "when": last_fail.ts.isoformat() if last_fail.ts else None,
            "detail": d,
            "emails_returned": [],
            "resolved_now": False,
            "hint": ("The OAuth app's client secret is wrong or expired — create a "
                     "fresh secret on THAT app and set M365_SSO_CLIENT_SECRET, then "
                     "restart." if invalid_secret else
                     "Redirect URI or PKCE mismatch — confirm the Entra app's Web "
                     "redirect URI is exactly the one shown below." if redirect_pkce else
                     "Sign-in failed at token exchange. See the reason in `detail`."),
        }
    elif last_fail:
        tried = [e.strip() for e in (last_fail.actor_email or "").split(",") if e.strip()]
        matched_now = next((e for e in tried if _user_for(e)), None)
        fail_view = {
            "when": last_fail.ts.isoformat() if last_fail.ts else None,
            "detail": last_fail.detail,
            "emails_returned": tried,
            # if a user now exists for one of those emails, the earlier failure is
            # already resolved (e.g. after inviting that address).
            "resolved_now": bool(matched_now),
            "hint": (f"A Pulse login now exists for {matched_now} — try signing in again."
                     if matched_now else
                     "No active Pulse user has that email. Invite/onboard that exact "
                     "address (Clients → Onboard, or add a staff user), then retry."),
        }

    ms_checklist = [
        {"label": "Microsoft SSO app configured (client ID + secret)",
         "ok": "microsoft" in active,
         "hint": "Add the SSO app in Settings, or reuse your M365 mailbox app."},
        {"label": "Redirect URI registered in your Entra app",
         "ok": None,
         "hint": f"Add exactly: {base}/api/oauth/microsoft/callback"},
        {"label": "Supported account types = any organizational directory",
         "ok": None,
         "hint": "In Entra → App registration → Authentication. This lets you and "
                 "every client's M365 org sign in (work/school accounts)."},
        {"label": "Delegated permissions: openid, email, profile, User.Read",
         "ok": None, "hint": "Entra → API permissions → Microsoft Graph (delegated)."},
        {"label": "Your own email maps to a Pulse login",
         "ok": bool(_user_for(user.email)),
         "hint": "SSO signs in an existing user matched by email; it never creates one."},
    ]
    from ...services import sso_provision
    return {
        "providers_active": sorted(active),
        "your_login": {"email": user.email, "role": user.role.value},
        "auto_provision": sso_provision.get_config(db),
        "microsoft": {
            "app_configured": "microsoft" in active,
            "effective_tenant": eff_tenant,
            "work_accounts_only": eff_tenant not in ("common", "consumers"),
            "reuses_mailbox_app": reuses_mailbox,
            "redirect_uri": f"{base}/api/oauth/microsoft/callback",
            "checklist": ms_checklist,
        },
        "google": {
            "app_configured": "google" in active,
            "redirect_uri": f"{base}/api/oauth/google/callback",
        },
        "last_failed_attempt": fail_view,
        "last_successful_attempt": (
            {"when": last_ok.ts.isoformat() if last_ok.ts else None,
             "email": last_ok.actor_email, "detail": last_ok.detail} if last_ok else None),
    }


@router.get("/connections")
def connections(request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """One-click OAuth connect status per integration: is the app configured (so
    Connect can run) and is it currently connected (token stored)."""
    oauth.sync_vault_providers(db)
    oauth.sync_connect_providers(db)
    base = _base_url(request)
    avail = {p["key"] for p in oauth.enabled_providers()}
    # Where to register the callback URL, per provider console. The #1 connect
    # failure ("redirect_uri does not match the registered value") is fixed by
    # pasting the EXACT redirect_uri below into this screen:
    hints = {
        "linkedin": "LinkedIn Developers → your app → Auth tab → OAuth 2.0 settings → "
                    "'Authorized redirect URLs for your app' → Add, paste EXACTLY this URL, Update.",
        "google_gbp": "Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 "
                      "Client → 'Authorized redirect URIs' → Add URI, paste EXACTLY this URL, Save.",
        "quickbooks": "Intuit Developer → your app → Keys & OAuth → 'Redirect URIs' → "
                      "Add URI, paste EXACTLY this URL, Save.",
        "microsoft": "Microsoft Entra → App registrations → your app → Authentication → "
                     "'Web' platform → Redirect URIs → add EXACTLY this URL.",
        "google": "Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 "
                  "Client → 'Authorized redirect URIs' → add EXACTLY this URL.",
    }
    out = []
    for key, label in (("linkedin", "LinkedIn"), ("google_gbp", "Google Business Profile"),
                       ("quickbooks", "QuickBooks"), ("microsoft", "Microsoft (SSO + M365)"),
                       ("google", "Google (SSO)")):
        tok = (db.query(OAuthToken).filter(OAuthToken.provider == key)
               .order_by(OAuthToken.id.desc()).first())
        out.append({"key": key, "name": label, "app_configured": key in avail,
                    "connected": bool(tok),
                    "account": tok.account_email if tok else None,
                    "connect_url": f"{base}/api/oauth/{key}/connect",
                    "redirect_uri": f"{base}/api/oauth/{key}/callback",
                    "console_hint": hints.get(key, "")})
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
        safe = "".join(ch for ch in error if ch.isalnum() or ch in "_-")[:60]
        return RedirectResponse(f"/?oauth_error={safe}&oauth_provider={provider}", status_code=302)
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
    except Exception as e:  # noqa: BLE001
        # Surface the provider's real reason in the logs (safe: no secret is ever
        # echoed by a token endpoint — just an error code + correlation id). This
        # turns an opaque "please try again" into a one-line diagnosis, e.g.
        # invalid_client (wrong/expired secret) vs invalid_grant (redirect/PKCE).
        print(f"[oauth] {provider} token exchange failed: {e}")
        try:
            audit.record(db, action="login.oauth_exchange_failed", ip=_ip(request),
                         success=False, detail=f"provider={provider} {str(e)[:400]}")
        except Exception:  # noqa: BLE001
            pass
        return RedirectResponse("/?oauth_error=exchange_failed", status_code=302)
    access = tok.get("access_token")
    # For SSO we only need identity (the id_token), which is present even when no
    # access_token/Graph scope was granted — so don't hard-fail on a missing
    # access token until we've tried the id_token claims.
    candidates = oauth.candidate_emails(provider, tok, access)
    email = candidates[0] if candidates else None

    if purpose == "sso":
        if not _s.OAUTH_ALLOW_SSO:
            return RedirectResponse("/?oauth_error=sso_disabled", status_code=302)
        # Match a provisioned user against ANY email/UPN this sign-in presented,
        # case-insensitively. This is the real authorization gate — SSO never
        # creates accounts, it only signs in someone already invited/onboarded.
        user = None
        for cand in candidates:
            user = (db.query(User)
                    .filter(func.lower(User.email) == cand)
                    .filter(User.is_active.is_(True)).first())
            if user:
                email = cand
                break
        if not user:
            # Zero-touch client SSO: if one of the presented emails belongs (by
            # domain) to exactly one onboarded client, create a read-only viewer.
            from ...services import sso_provision
            claims = oauth.decode_id_token_claims(tok.get("id_token"))
            name = claims.get("name")
            for cand in candidates:
                user = sso_provision.maybe_autoprovision(db, cand, full_name=name)
                if user:
                    email = cand
                    audit.record(db, action="login.oauth_autoprovision", actor_user_id=user.id,
                                 actor_email=user.email, actor_role=user.role.value,
                                 client_id=user.client_id, ip=_ip(request),
                                 detail=f"provider={provider} client_id={user.client_id}")
                    # Tell staff a new person came in the zero-touch door, so they
                    # can review/promote/deactivate in Users & Access.
                    try:
                        from ...models import Client, Notification
                        from ...services import notifications as _notif
                        cli = db.get(Client, user.client_id) if user.client_id else None
                        cname = cli.name if cli else "a client"
                        msg = (f"New self-service SSO login: {user.email} "
                               f"(read-only, {cname}). Review in Users & Access.")
                        db.add(Notification(client_id=None, target_user_id=None,
                                            kind="access", severity="info", message=msg[:1000]))
                        db.commit()
                        _notif.fanout(db, message=msg, severity="info", client_id=None)
                    except Exception:
                        pass
                    break
        if not user:
            audit.record(db, action="login.oauth_no_match",
                         actor_email=(email or ",".join(candidates) or None), ip=_ip(request),
                         success=False, detail=f"provider={provider} tried={len(candidates)}")
            return RedirectResponse("/?oauth_error=no_account", status_code=302)
        dest = "/portal" if user.role in (Role.CLIENT_ADMIN, Role.CLIENT_VIEWER) else "/dashboard"
        redirect = RedirectResponse(dest, status_code=302)
        issue_session(db, user, request, redirect, method=f"oauth:{provider}")
        audit.record(db, action="login.oauth_success", actor_user_id=user.id, actor_email=user.email,
                     actor_role=user.role.value, ip=_ip(request), detail=f"provider={provider}")
        return redirect

    if not access:
        return RedirectResponse("/?oauth_error=no_token", status_code=302)

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
