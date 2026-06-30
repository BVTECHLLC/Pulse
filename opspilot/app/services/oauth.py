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


def _seed() -> None:
    s = get_settings()
    if s.ms_oauth_enabled:
        base = f"{s.M365_LOGIN_BASE}/{s.MS_OAUTH_TENANT}/oauth2/v2.0"
        register_provider("microsoft", {
            "name": "Microsoft",
            "authorize_url": f"{base}/authorize",
            "token_url": f"{base}/token",
            "userinfo_url": f"{s.M365_GRAPH_BASE}/me",
            "scopes": ["openid", "email", "profile", "User.Read", "offline_access"],
            "client_id": s.M365_CLIENT_ID,
            "client_secret": s.M365_CLIENT_SECRET,
            "email_fields": ["mail", "userPrincipalName"],
        })
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
    ms_id = secure_config.get_secret(sso_cfg, "ms_client_id") or sso_cfg.get("ms_client_id") \
        or secure_config.get_secret(mbox_cfg, "client_id") or mbox_cfg.get("client_id")
    ms_secret = secure_config.get_secret(sso_cfg, "ms_client_secret") \
        or secure_config.get_secret(mbox_cfg, "client_secret")
    ms_tenant = (sso_cfg.get("ms_tenant")
                 or secure_config.get_secret(mbox_cfg, "tenant_id") or mbox_cfg.get("tenant_id")
                 or s.MS_OAUTH_TENANT)
    if ms_id and ms_secret:
        base = f"{s.M365_LOGIN_BASE}/{ms_tenant}/oauth2/v2.0"
        register_provider("microsoft", {
            "name": "Microsoft",
            "authorize_url": f"{base}/authorize", "token_url": f"{base}/token",
            "userinfo_url": f"{s.M365_GRAPH_BASE}/me",
            "scopes": ["openid", "email", "profile", "User.Read", "offline_access"],
            "client_id": str(ms_id), "client_secret": str(ms_secret),
            "email_fields": ["mail", "userPrincipalName"],
        })

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
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    params.update(p.get("extra_authorize", {}))
    return f"{p['authorize_url']}?{urlencode(params)}"


def _post_form(url: str, data: dict) -> dict:
    body = urlencode(data).encode()
    req = urlreq.Request(url, data=body, method="POST",
                         headers={"Content-Type": "application/x-www-form-urlencoded",
                                  "Accept": "application/json"})
    with urlreq.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode() or "{}")


def exchange_code(provider_key: str, *, code: str, code_verifier: str,
                  redirect_uri: str) -> dict:
    p = _PROVIDERS[provider_key]
    return _post_form(p["token_url"], {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": p["client_id"],
        "client_secret": p["client_secret"],
        "code_verifier": code_verifier,
    })


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
