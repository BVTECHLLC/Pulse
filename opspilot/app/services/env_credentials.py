"""v1.0 .env → vault credential loader.

Most integrations read their credentials from the encrypted vault (filled in via
the Settings UI). This bridge lets you ALSO configure them straight from
environment variables: on every boot we copy any recognized env var into the
right vault provider/field, so putting keys in `.env` "just works" without
clicking through Settings.

Rules (v1.171 — the portal is authoritative):
  * Env only FILLS GAPS. A value saved in the portal (Settings / Connection
    Center) is never overwritten by .env. Before v1.171 env won on every boot,
    so every deploy silently reverted what the operator had just saved — the
    "I keep plugging in LinkedIn and it never takes" loop (a rotated LinkedIn
    secret reverted to the stale .env one; Google Business / SSO creds were
    replaced with .env PLACEHOLDER text like "# paste ... here").
  * Placeholder / comment text is never stored: values starting with "#",
    "<...>" templates and "paste/your_..." instructions are ignored, and an
    unquoted inline " # comment" is stripped. Placeholder junk already sitting
    in the vault for a mapped field is scrubbed so the tile honestly reads
    "needs credentials" instead of "configured but broken".
  * Escape hatch: PULSE_ENV_CREDS_OVERRIDE=1 restores the old "env wins" rule
    for one boot (e.g. a deliberate key rotation done only in .env).
  * Secret-looking fields are encrypted at rest by the vault automatically.
"""
from __future__ import annotations

import os
import re

from sqlalchemy.orm import Session

from . import secure_config

# provider -> {vault_field: [accepted env var names, first non-empty wins]}
_MAP: dict[str, dict[str, list[str]]] = {
    "stripe": {
        "secret_key": ["STRIPE_SECRET_KEY", "STRIPE_API_KEY"],
        "webhook_secret": ["STRIPE_WEBHOOK_SECRET"],
    },
    "quickbooks": {
        "client_id": ["QUICKBOOKS_CLIENT_ID", "QBO_CLIENT_ID"],
        "client_secret": ["QUICKBOOKS_CLIENT_SECRET", "QBO_CLIENT_SECRET"],
        "refresh_token": ["QUICKBOOKS_REFRESH_TOKEN", "QBO_REFRESH_TOKEN"],
        "realm_id": ["QUICKBOOKS_REALM_ID", "QBO_REALM_ID"],
        "sandbox": ["QUICKBOOKS_SANDBOX"],   # bool-ish; only set when truthy
    },
    "gbp": {
        # Google Business shares the Google OAuth app with Google sign-in.
        "client_id": ["GBP_CLIENT_ID", "GOOGLE_BUSINESS_CLIENT_ID", "gbp_client_id", "google_client_id"],
        "client_secret": ["GBP_CLIENT_SECRET", "GOOGLE_BUSINESS_CLIENT_SECRET", "gbp_client_secret", "google_client_secret"],
        "refresh_token": ["GBP_REFRESH_TOKEN", "GOOGLE_BUSINESS_REFRESH_TOKEN", "gbp_refresh_token"],
        "account_name": ["GBP_ACCOUNT_NAME", "gbp_account_name"],
        "location_name": ["GBP_LOCATION_NAME", "gbp_location_name"],
    },
    "pub_linkedin": {
        "li_client_id": ["LINKEDIN_CLIENT_ID", "linkedin_client_id"],
        "li_client_secret": ["LINKEDIN_CLIENT_SECRET", "linkedin_client_secret"],
        "person_urn": ["LINKEDIN_PERSON_URN", "linkedin_person_urn"],
        "access_token": ["LINKEDIN_ACCESS_TOKEN", "linkedin_access_token"],
    },
    "dialpad": {
        "api_key": ["DIALPAD_API_KEY", "dialpad_key"],
        "user_id": ["DIALPAD_USER_ID", "dialpad_user_id"],
        "caller_number": ["DIALPAD_CALLER_NUMBER", "dialpad_number"],
    },
    "hubspot": {
        "token": ["HUBSPOT_API_KEY", "HUBSPOT_ACCESS_TOKEN", "HUBSPOT_TOKEN",
                  "HUBSPOT_PRIVATE_APP_TOKEN", "hubspot_token"],
    },
    "tacticalrmm": {
        "base_url": ["TACTICAL_BASE_URL", "TACTICALRMM_BASE_URL", "TRMM_BASE_URL", "trmm_api_url"],
        "api_key": ["TACTICAL_API_KEY", "TACTICALRMM_API_KEY", "TRMM_API_KEY", "trmm_api_key"],
    },
    "m365_mailbox": {
        "client_id": ["M365_CLIENT_ID"],
        "client_secret": ["M365_CLIENT_SECRET"],
        "tenant_id": ["M365_TENANT_ID"],
        "mailbox": ["M365_MAILBOX", "sender_email"],
    },
    "sso_login": {
        # Microsoft SSO sign-in app. Use a DEDICATED app (with the redirect URI
        # registered) — NOT the mailbox app. id + secret must come from the SAME
        # app or Microsoft rejects the token exchange. Names are matched
        # case-insensitively, so M356_OAUTH_ID / m365_oauth_id also resolve.
        "ms_client_id": ["SSO_MS_CLIENT_ID", "M365_SSO_CLIENT_ID", "M365_OAUTH_CLIENT_ID",
                         "M365_OAUTH_ID", "M356_OAUTH_ID"],
        "ms_client_secret": ["SSO_MS_CLIENT_SECRET", "M365_SSO_CLIENT_SECRET",
                             "M365_OAUTH_CLIENT_SECRET", "M365_OAUTH_SECRET"],
        # Falls back to the mailbox tenant when a dedicated one isn't given.
        "ms_tenant": ["SSO_MS_TENANT", "M365_SSO_TENANT", "M365_TENANT_ID"],
        "google_client_id": ["SSO_GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID", "google_client_id"],
        "google_client_secret": ["SSO_GOOGLE_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET", "google_client_secret"],
    },
    "wp_site": {
        # WordPress (bvtech.org) — REST API with an Application Password.
        "base_url": ["WP_URL", "WP_SITE_URL", "WORDPRESS_URL", "wp_url", "wp_site",
                     "wp_site_url", "bvtech_wp_url"],
        "username": ["WP_USERNAME", "WP_USER", "wp_user", "wp_username", "wp_login"],
        "app_password": ["WP_APP_PASSWORD", "WP_APP_PASS", "WP_APPLICATION_PASSWORD",
                         "wp_app_password", "wp_app_pass", "wp_password", "wp_pass",
                         "wp_key", "wp_token", "wp_api_key"],
    },
    "google_places": {
        "api_key": ["GOOGLE_PLACES_API_KEY", "GOOGLE_MAPS_API_KEY", "google_api_key"],
    },
    "payment_methods": {
        "paypal_handle": ["PAYPAL_HANDLE"],
        "venmo_handle": ["VENMO_HANDLE"],
        "cashapp_cashtag": ["CASHAPP_CASHTAG"],
        "bank_wire": ["BANK_WIRE_DETAILS"],
        "check_payable_to": ["CHECK_PAYABLE_TO"],
    },
}

_META = {
    "stripe": ("Stripe", "Payments"),
    "quickbooks": ("QuickBooks Online", "Accounting"),
    "gbp": ("Google Business Profile", "Marketing"),
    "pub_linkedin": ("LinkedIn Publisher", "Marketing"),
    "dialpad": ("Dialpad", "Telephony"),
    "hubspot": ("HubSpot", "CRM"),
    "tacticalrmm": ("Tactical RMM", "RMM"),
    "m365_mailbox": ("Microsoft 365 Mailbox", "Email"),
    "sso_login": ("Single Sign-On", "Identity"),
    "wp_site": ("WordPress (bvtech.org)", "Website"),
    "google_places": ("Google Places", "Prospecting"),
    "payment_methods": ("Payment Methods", "Payments"),
}

_TRUTHY = {"1", "true", "yes", "on", "y", "t"}


# Instruction / template text that must never be stored as a credential.
_PLACEHOLDER_MARKERS = ("paste ", "paste_", "paste-", "<", ">", "your_", "your-", "your ",
                        "replace me", "replace_me", "changeme", "change_me", "value again")
_PLACEHOLDER_WORDS = {"todo", "tbd", "none", "null", "changeme", "xxx", "placeholder"}


def clean_value(v) -> str | None:
    """Normalize one env/vault value: strip whitespace and wrapping quotes, cut
    an unquoted inline ' # comment', and return None for empty or placeholder
    text. Real values may contain inner spaces (WordPress app passwords do)."""
    if v is None:
        return None
    s = str(v).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    else:
        s = re.split(r"\s+#", s, maxsplit=1)[0].strip()
    if not s or s.startswith("#"):
        return None
    low = s.lower()
    if low in _PLACEHOLDER_WORDS or any(m in low for m in _PLACEHOLDER_MARKERS):
        return None
    return s


def _stored(cfg: dict, field: str) -> str | None:
    try:
        return secure_config.get_secret(cfg, field) or cfg.get(field)
    except Exception:  # noqa: BLE001 — undecryptable == unusable
        return None


def load(db: Session) -> dict:
    """Fill EMPTY vault fields from recognized env vars (never overwrite a value
    saved in the portal). Returns {provider: [fields set]}."""
    # Case-insensitive index so a mis-cased key (M356_OAuth_ID, google_api_key)
    # still resolves. Exact matches always win over the folded fallback.
    env_ci = {k.lower(): v for k, v in os.environ.items()}
    override = str(os.environ.get("PULSE_ENV_CREDS_OVERRIDE", "")).lower() in _TRUTHY

    def _resolve(names: list[str]) -> str | None:
        for name in names:
            v = os.environ.get(name)
            if v is None:
                v = env_ci.get(name.lower())
            v = clean_value(v)
            if v is not None:
                return v
        return None

    applied: dict[str, list[str]] = {}
    for provider, fields in _MAP.items():
        conn = secure_config.get_platform(db, provider)
        cur = dict((conn.config if conn else None) or {})
        payload: dict[str, str] = {}
        scrub: list[str] = []
        for vault_field, env_names in fields.items():
            raw = _stored(cur, vault_field)
            have = clean_value(raw)
            if have is None and cur.get(vault_field) not in (None, ""):
                scrub.append(vault_field)          # placeholder junk in the vault
            val = _resolve(env_names)
            if have is not None and not (override and val is not None):
                if vault_field != "sandbox" and have != str(raw):
                    payload[vault_field] = have    # strip a pasted inline comment
                continue                           # portal value wins
            if val is None:
                continue
            if vault_field == "sandbox":       # bool-ish: only store when truthy
                if val.lower() in _TRUTHY:
                    payload[vault_field] = "true"
                continue
            payload[vault_field] = val
        scrub = [f for f in scrub if f not in payload]
        if scrub and conn is not None:
            try:
                conn.config = {k: v for k, v in cur.items() if k not in scrub}
                db.commit()
                print(f"[env-creds] {provider}: cleared placeholder text from {sorted(scrub)}")
            except Exception as e:  # noqa: BLE001
                db.rollback()
                print(f"[env-creds] {provider} scrub skipped: {e}")
        if payload:
            name, cat = _META.get(provider, (provider, "Integration"))
            try:
                secure_config.upsert_platform(db, provider, name, cat, payload)
                applied[provider] = sorted(payload.keys())
            except Exception as e:  # noqa: BLE001
                print(f"[env-creds] {provider} skipped: {e}")
    return applied
