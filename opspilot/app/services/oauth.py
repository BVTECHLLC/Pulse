"""v0.23 OAuth2 (authorization-code + PKCE) framework.

Powers two things from one flow:
  * SSO sign-in   — "Sign in with Microsoft / Google", matched to an existing user
  * Connectors    — store an encrypted access/refresh token for an external service

Providers light up automatically when their credentials are configured. Custom
providers can be added at runtime via register_provider() (also used by tests).
No third-party OAuth client lib — just urllib + PKCE done correctly."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib import request as urlreq
from urllib.parse import urlencode

from ..core.config import get_settings


# --- PKCE ------------------------------------------------------------------- #
def gen_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def challenge_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


# --- Provider registry ------------------------------------------------------ #
# Each provider: authorize_url, token_url, userinfo_url, scopes, client_id,
# client_secret, email_fields (try in order), name.
_PROVIDERS: dict[str, dict] = {}


def register_provider(key: str, cfg: dict) -> None:
    _PROVIDERS[key] = cfg


def normalize_tenant(tenant: str | None) -> str:
    """An MSP portal signs people in with their M365 *work/school* accounts.
    Empty or 'common' would also allow personal Microsoft accounts (the
    account.live.com path) and lets an address that exists as both silently land
    on the wrong one — so we coerce those to 'organizations' (any work/school
    tenant). A specific tenant GUID (or 'consumers') is respected as given."""
    t = (tenant or "").strip()
    if not t or t.lower() == "common":
        return "organizations"
    return t


def _register_microsoft(*, client_id: str, client_secret: str, tenant: str,
                        login_base: str, graph_base: str) -> None:
    tenant = normalize_tenant(tenant)
    base = f"{login_base}/{tenant}/oauth2/v2.0"
    register_provider("microsoft", {
        "name": "Microsoft",
        "authorize_url": f"{base}/authorize",
        "token_url": f"{base}/token",
        "userinfo_url": f"{graph_base}/me",
        "scopes": ["openid", "email", "profile", "User.Read", "offline_access"],
        "client_id": str(client_id),
        "client_secret": str(client_secret),
        "email_fields": ["mail", "userPrincipalName"],
        # select_account: always show the account picker so a cached personal
        # login can't hijack the flow — the user explicitly picks their work account.
        "extra_authorize": {"prompt": "select_account"},
    })


def _seed() -> None:
    s = get_settings()
    if s.ms_oauth_enabled:
        _register_microsoft(client_id=s.M365_CLIENT_ID, client_secret=s.M365_CLIENT_SECRET,
                            tenant=s.MS_OAUTH_TENANT, login_base=s.M365_LOGIN_BASE,
                            graph_base=s.M365_GRAPH_BASE)
    if s.google_oauth_enabled:
        register_provider("google", {
            "name": "Google",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scopes": ["openid", "email", "profile"],
            "client_id": s.GOOGLE_CLIENT_ID,
            "client_secret": s.GOOGLE_CLIENT_SECRET,
            "email_fields": ["email"],
            "extra_authorize": {"access_type": "offline", "prompt": "consent"},
        })


_seed()


def sync_vault_providers(db) -> None:
    """Register/refresh the Microsoft + Google SSO providers from the secure vault
    so sign-in lights up from what was configured in Settings (no box env vars
    needed). Called at the start of every OAuth request. Microsoft falls back to
    the M365 mailbox app's credentials when a dedicated SSO app isn't set, so one
    Entra app can power both mail and login."""
    from . import secure_config
    s = get_settings()

    sso = secure_config.get_platform(db, "sso_login")
    sso_cfg = (sso.config if sso else None) or {}
    mbox = secure_config.get_platform(db, "m365_mailbox")
    mbox_cfg = (mbox.config if mbox else None) or {}

    # --- Microsoft ---
    # A confidential OAuth app authenticates with BOTH its client_id and its own
    # client_secret; the redirect URI must be registered on THAT SAME app. So we
    # never mix a dedicated SSO app's id with the mailbox app's secret (that would
    # trade a "no reply address" error for an opaque "invalid client" one). Prefer
    # a fully-configured dedicated SSO app; otherwise fall back to the mailbox app
    # as a matched id+secret pair.
    sso_id = secure_config.get_secret(sso_cfg, "ms_client_id") or sso_cfg.get("ms_client_id")
    sso_secret = secure_config.get_secret(sso_cfg, "ms_client_secret") or sso_cfg.get("ms_client_secret")
    mbox_id = secure_config.get_secret(mbox_cfg, "client_id") or mbox_cfg.get("client_id")
    mbox_secret = secure_config.get_secret(mbox_cfg, "client_secret")
    if sso_id and sso_secret:
        ms_id, ms_secret = sso_id, sso_secret
    elif mbox_id and mbox_secret:
        ms_id, ms_secret = mbox_id, mbox_secret
    else:
        ms_id = ms_secret = None
    ms_tenant = (sso_cfg.get("ms_tenant")
                 or secure_config.get_secret(mbox_cfg, "tenant_id") or mbox_cfg.get("tenant_id")
                 or s.MS_OAUTH_TENANT)
    if ms_id and ms_secret:
        _register_microsoft(client_id=ms_id, client_secret=ms_secret, tenant=ms_tenant,
                            login_base=s.M365_LOGIN_BASE, graph_base=s.M365_GRAPH_BASE)

    # --- Google ---
    g_id = secure_config.get_secret(sso_cfg, "google_client_id") or sso_cfg.get("google_client_id")
    g_secret = secure_config.get_secret(sso_cfg, "google_client_secret")
    if g_id and g_secret:
        register_provider("google", {
            "name": "Google",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "scopes": ["openid", "email", "profile"],
            "client_id": str(g_id), "client_secret": str(g_secret),
            "email_fields": ["email"],
            "extra_authorize": {"access_type": "offline", "prompt": "consent"},
        })


def get_provider(key: str) -> dict | None:
    return _PROVIDERS.get(key)


def enabled_providers() -> list[dict]:
    return [{"key": k, "name": v["name"]} for k, v in _PROVIDERS.items()]


# --- Flow steps ------------------------------------------------------------- #
def authorize_url(provider_key: str, *, state: str, code_challenge: str,
                  redirect_uri: str) -> str:
    p = _PROVIDERS[provider_key]
    params = {
        "client_id": p["client_id"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(p["scopes"]),
        "state": state,
    }
    if not p.get("no_pkce"):              # LinkedIn's token endpoint rejects PKCE params
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    params.update(p.get("extra_authorize", {}))
    return f"{p['authorize_url']}?{urlencode(params)}"


class TokenError(Exception):
    """A token endpoint returned an OAuth error. Carries the provider's own
    error/description (e.g. Microsoft's `invalid_client` + `AADSTS7000215...`)
    so failures are diagnosable in the logs. NEVER contains the client secret —
    the token endpoint echoes only error codes, request/correlation ids, and the
    (already public) client_id."""
    def __init__(self, status: int, error: str | None, description: str | None):
        self.status = status
        self.error = error or "error"
        self.description = (description or "")[:400]
        super().__init__(f"{status} {self.error}: {self.description}")


def _post_form(url: str, data: dict) -> dict:
    body = urlencode(data).encode()
    req = urlreq.Request(url, data=body, method="POST",
                         headers={"Content-Type": "application/x-www-form-urlencoded",
                                  "Accept": "application/json"})
    try:
        with urlreq.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode() or "{}")
    except urlreq.HTTPError as he:  # 4xx/5xx from the token endpoint
        try:
            payload = json.loads(he.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            payload = {}
        raise TokenError(he.code, payload.get("error"),
                         payload.get("error_description")) from None


def exchange_code(provider_key: str, *, code: str, code_verifier: str,
                  redirect_uri: str) -> dict:
    p = _PROVIDERS[provider_key]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": p["client_id"],
        "client_secret": p["client_secret"],
    }
    if not p.get("no_pkce"):
        data["code_verifier"] = code_verifier
    return _post_form(p["token_url"], data)


def refresh_token(provider_key: str, *, refresh: str) -> dict:
    p = _PROVIDERS[provider_key]
    return _post_form(p["token_url"], {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": p["client_id"],
        "client_secret": p["client_secret"],
    })


def fetch_email(provider_key: str, access_token: str) -> str | None:
    p = _PROVIDERS[provider_key]
    url = p.get("userinfo_url")
    if not url:
        return None
    req = urlreq.Request(url, headers={"Authorization": f"Bearer {access_token}",
                                       "Accept": "application/json"})
    try:
        with urlreq.urlopen(req, timeout=15) as r:
            info = json.loads(r.read().decode() or "{}")
    except Exception:
        return None
    for f in p.get("email_fields", ["email"]):
        if info.get(f):
            return str(info[f]).lower()
    return None


def fetch_userinfo(provider_key: str, access_token: str) -> dict:
    """Raw userinfo payload (LinkedIn needs `sub` -> person URN)."""
    p = _PROVIDERS.get(provider_key) or {}
    url = p.get("userinfo_url")
    if not url:
        return {}
    req = urlreq.Request(url, headers={"Authorization": f"Bearer {access_token}",
                                       "Accept": "application/json"})
    try:
        with urlreq.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception:
        return {}


def decode_id_token_claims(id_token: str | None) -> dict:
    """Return the claims from an OIDC id_token WITHOUT signature verification.

    This is safe for our use: the id_token is delivered directly by the
    provider's token endpoint over TLS, in an authenticated server-to-server
    code exchange (client_id + client_secret) — it never passes through the
    browser. We only read identity claims (email/upn), never authorize on it
    alone; the real gate is that the resolved email must match a provisioned
    Pulse user."""
    if not id_token or id_token.count(".") < 2:
        return {}
    payload = id_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)   # restore base64 padding
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}


def candidate_emails(provider_key: str, tok: dict, access_token: str | None) -> list[str]:
    """Every email/UPN this sign-in could reasonably be matched on, best first.

    Pulls from the id_token claims (reliable across work/personal accounts) and
    then the provider's userinfo endpoint (Graph /me for Microsoft). De-duped,
    lowercased. Matching against a provisioned user is done case-insensitively by
    the caller."""
    out: list[str] = []

    def add(v):
        if v and isinstance(v, str) and "@" in v:
            e = v.strip().lower()
            if e not in out:
                out.append(e)

    claims = decode_id_token_claims((tok or {}).get("id_token"))
    for k in ("email", "preferred_username", "upn", "unique_name"):
        add(claims.get(k))

    if access_token:
        try:
            info = fetch_userinfo(provider_key, access_token)
        except Exception:
            info = {}
        p = _PROVIDERS.get(provider_key) or {}
        for f in p.get("email_fields", ["email"]):
            add(info.get(f))
        # personal-account Graph responses sometimes only carry these
        for f in ("mail", "userPrincipalName", "otherMails"):
            v = info.get(f)
            if isinstance(v, list):
                for item in v:
                    add(item)
            else:
                add(v)
    return out


# --------------------------------------------------------------------------- #
# Self-refreshing connections: store the OAuth token and ALWAYS hand back a
# valid access token, refreshing (and persisting the rotated refresh token —
# critical for QuickBooks, which rotates on every refresh) when it's expired.
# This is what makes a connected integration "never expire again".
# --------------------------------------------------------------------------- #
def get_valid_token(db, provider: str) -> str | None:
    """Return a fresh access token for a connected provider, refreshing on demand.
    None if the provider was never connected."""
    from ..models import OAuthToken
    from . import crypto
    row = (db.query(OAuthToken).filter(OAuthToken.provider == provider)
           .order_by(OAuthToken.id.desc()).first())
    if not row:
        return None
    now = datetime.now(timezone.utc)
    exp = row.expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp is None or exp > now + timedelta(seconds=120):
        return crypto.decrypt(row.access_token_enc)
    # Expired — try to refresh (needs the provider registered + a refresh token).
    refresh = crypto.decrypt(row.refresh_token_enc) if row.refresh_token_enc else None
    if not refresh or not get_provider(provider):
        return crypto.decrypt(row.access_token_enc)   # best effort
    try:
        tok = refresh_token(provider, refresh=refresh)
    except Exception:
        return crypto.decrypt(row.access_token_enc)
    if not tok.get("access_token"):
        return crypto.decrypt(row.access_token_enc)
    row.access_token_enc = crypto.encrypt(tok["access_token"])
    if tok.get("refresh_token"):                       # persist the ROTATED refresh token
        row.refresh_token_enc = crypto.encrypt(tok["refresh_token"])
    if tok.get("expires_in"):
        row.expires_at = now + timedelta(seconds=int(tok["expires_in"]))
    db.commit()
    return tok["access_token"]


def sync_connect_providers(db) -> None:
    """Register OAuth *connect* providers (LinkedIn / Google / QuickBooks) using
    each integration's app credentials from the vault, so one-click Connect works."""
    from . import secure_config

    def creds(prov, id_key="client_id", secret_key="client_secret"):
        c = secure_config.get_platform(db, prov)
        cfg = (c.config if c else None) or {}
        return (secure_config.get_secret(cfg, id_key) or cfg.get(id_key),
                secure_config.get_secret(cfg, secret_key), cfg)

    li_id, li_secret, _ = creds("pub_linkedin", "li_client_id", "li_client_secret")
    if li_id and li_secret:
        register_provider("linkedin", {
            "name": "LinkedIn",
            "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
            "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
            "userinfo_url": "https://api.linkedin.com/v2/userinfo",
            "scopes": ["openid", "profile", "email", "w_member_social"],
            "client_id": str(li_id), "client_secret": str(li_secret),
            "no_pkce": True,
        })
    g_id, g_secret, _ = creds("gbp")
    if g_id and g_secret:
        register_provider("google_gbp", {
            "name": "Google Business Profile",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": ["https://www.googleapis.com/auth/business.manage"],
            "client_id": str(g_id), "client_secret": str(g_secret),
            "extra_authorize": {"access_type": "offline", "prompt": "consent"},
        })
    q_id, q_secret, qcfg = creds("quickbooks")
    if q_id and q_secret:
        sandbox = bool(qcfg.get("sandbox"))
        register_provider("quickbooks", {
            "name": "QuickBooks",
            "authorize_url": "https://appcenter.intuit.com/connect/oauth2",
            "token_url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            "scopes": ["com.intuit.quickbooks.accounting"],
            "client_id": str(q_id), "client_secret": str(q_secret),
            "extra_authorize": {"access_type": "offline"},
            "sandbox": sandbox,
        })
