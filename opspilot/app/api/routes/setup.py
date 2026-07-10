"""v0.72 Guided setup status — a friendly "what's connected / what's left"
checklist so a new operator can get fully live without hunting through Settings.
Staff-only; read-only aggregation over the vault + a couple of tables.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.db import get_db
from ...core.deps import require_roles
from ...models import Device, M365Connection, Role, SocialPost, User
from ...services import autopost, secure_config

router = APIRouter(prefix="/api/setup", tags=["setup"])
_s = get_settings()


def _configured(db: Session, provider: str, required) -> bool:
    conn = secure_config.get_platform(db, provider)
    cfg = (conn.config if conn else None) or {}
    return secure_config.configured(cfg, required)


def _payment_methods_set(db: Session) -> bool:
    """True if at least one non-note payment-method field is filled in."""
    conn = secure_config.get_platform(db, "payment_methods")
    cfg = (conn.config if conn else None) or {}
    return any(str(v).strip() for k, v in cfg.items() if k != "methods_note")


@router.get("/status")
def setup_status(db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """A checklist of setup steps with done/undone + where to finish each."""
    devices = db.query(Device).count()
    queued = db.query(SocialPost).count()
    ap_cfg = autopost.get_config(db)
    ap_ready = autopost.channel_readiness(db)

    items = [
        {"key": "agent", "label": "Deploy the endpoint agent",
         "done": devices > 0, "tab": "devices",
         "hint": "Devices → Deploy Agent → download the installer and run it on a PC."},
        {"key": "m365", "label": "Connect Microsoft 365",
         "done": db.query(M365Connection).count() > 0, "tab": "billing",
         "hint": "Billing → Microsoft 365 → Connect a client tenant for Secure Score."},
        {"key": "stripe", "label": "Accept card payments (Stripe)",
         "done": _configured(db, "stripe", ("secret_key",)), "tab": "settings",
         "hint": "Settings → Stripe Payments so clients can pay invoices online."},
        {"key": "payment_methods", "label": "Add payment methods (PayPal/wire/…)",
         "done": _payment_methods_set(db), "tab": "settings",
         "hint": "Settings → Payment Methods to show every way to pay on invoices."},
        {"key": "quickbooks", "label": "Connect QuickBooks Online",
         "done": _configured(db, "quickbooks", ("client_id", "client_secret", "refresh_token")),
         "tab": "settings", "hint": "Settings → QuickBooks Online to sync invoices."},
        {"key": "dialpad", "label": "Connect Dialpad (power dialer)",
         "done": _configured(db, "dialpad", ("api_key", "user_id")), "tab": "settings",
         "hint": "Settings → Dialpad to enable click-to-call + the power dialer."},
        {"key": "linkedin", "label": "Connect LinkedIn (auto-posting)",
         "done": ap_ready.get("linkedin", False), "tab": "settings",
         "hint": "Settings → Publishers → Connect LinkedIn."},
        {"key": "gbp", "label": "Connect Google Business Profile",
         "done": ap_ready.get("google_business", False), "tab": "settings",
         "hint": "Settings → Google Business Profile → Connect, then pick your location."},
        {"key": "autopost", "label": "Turn on auto-posting",
         "done": bool(ap_cfg["enabled"] and queued > 0), "tab": "content",
         "hint": "Content Studio → Auto-post queue → add posts + enable."},
        {"key": "email", "label": "Set up outbound email (reminders/receipts)",
         "done": bool(_s.email_enabled), "tab": "settings",
         "hint": "Set SMTP_HOST so payment reminders actually send."},
    ]
    done = sum(1 for i in items if i["done"])
    return {"items": items, "done": done, "total": len(items),
            "pct": round(done / len(items) * 100) if items else 0}


# --------------------------------------------------------------------------- #
# v1.22 Connection Center — EVERY connector, its live status, what it unlocks,
# the exact provider console page to get the credential, and where in Pulse to
# paste it. One page to go live.
# --------------------------------------------------------------------------- #
@router.get("/connections")
def connection_center(db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Every connector with: live status, what it unlocks, a deep link to the
    provider console (Get credential), and the fields to paste it right here
    (Enter credential -> encrypted in the vault)."""
    from ...services import ai as ai_svc, jp_site
    from ...models import OAuthToken

    def vault_has(provider, *keys):
        conn = secure_config.get_platform(db, provider)
        cfg = (conn.config if conn else None) or {}
        return all(secure_config.get_secret(cfg, k) or cfg.get(k) for k in keys)

    li = db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count() > 0
    gbp = db.query(OAuthToken).filter(OAuthToken.provider == "google_gbp").count() > 0
    qb = db.query(OAuthToken).filter(OAuthToken.provider == "quickbooks").count() > 0

    status = {
        "anthropic": ai_svc.enabled(),
        "gitlab_sites": jp_site.configured(db, "bvtech") and jp_site.configured(db, "jp"),
        "m365_mailbox": vault_has("m365_mailbox", "client_id", "client_secret")
                        or bool(_s.M365_CLIENT_ID and _s.M365_CLIENT_SECRET),
        "pub_linkedin": li or vault_has("pub_linkedin", "li_client_id"),
        "gbp": gbp or vault_has("gbp", "client_id"),
        "stripe": vault_has("stripe", "secret_key"),
        "smtp": bool(_s.SMTP_HOST),
        "quickbooks": qb or vault_has("quickbooks", "client_id"),
        "hubspot": vault_has("hubspot", "token"),
        "dialpad": vault_has("dialpad", "api_key"),
        "google_places": vault_has("google_places", "api_key"),
        "tacticalrmm": vault_has("tacticalrmm", "api_key"),
    }
    items = []
    for spec in CONNECTORS:
        it = dict(spec)
        it["connected"] = bool(status.get(spec["key"]))
        it["fields"] = spec.get("fields", [])
        it["can_enter"] = bool(spec.get("fields"))
        it["needs_connect"] = spec.get("needs_connect", False)
        items.append(it)
    p1 = [i for i in items if i["priority"] == 1]
    done = sum(1 for i in items if i["connected"])
    return {"items": items, "total": len(items), "connected": done,
            "go_live_ready": all(i["connected"] for i in p1),
            "score_pct": round(100 * done / len(items))}


# The single source of truth: status logic (above) + save logic (below) both
# derive from this. `fields` renders the Enter-credential inputs; `save` names
# the vault provider (secret-named keys are auto-encrypted by upsert_platform).
CONNECTORS = [
    {"key": "anthropic", "name": "Claude AI (Anthropic)", "priority": 1,
     "unlocks": "EVERYTHING intelligent: Copilot + fleet sweeps, ticket triage, vCIO "
                "reviews, morning briefing, foresight, all daily content writing.",
     "console_url": "https://console.anthropic.com/settings/keys",
     "console_hint": "Console -> API keys -> Create Key -> copy (starts sk-ant-...)",
     "save": "anthropic",
     "fields": [{"key": "api_key", "label": "Anthropic API key", "secret": True}]},
    {"key": "gitlab_sites", "name": "Websites (bvtech.org + jordanpolasek.com)", "priority": 1,
     "unlocks": "Daily blog posts to BOTH sites with Cloudflare deploy verification + auto-revert.",
     "console_url": "https://gitlab.com/-/user_settings/personal_access_tokens",
     "console_hint": "Generate token -> name 'Pulse Publisher' -> scope: api -> copy (glpat-...)",
     "save": "gitlab_sites",
     "fields": [{"key": "token", "label": "GitLab token (api scope) - connects BOTH sites", "secret": True}]},
    {"key": "m365_mailbox", "name": "Microsoft 365 (mail + SSO)", "priority": 1,
     "unlocks": "Secure mailbox (read/send as help@bvtech.org) + Microsoft sign-in for you + clients.",
     "console_url": "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
     "console_hint": "App registrations -> your app -> copy Application (client) ID + Directory "
                     "(tenant) ID; Certificates & secrets -> New client secret. Add the redirect "
                     "URL from One-click Connect.",
     "save": "m365_mailbox",
     "fields": [{"key": "client_id", "label": "Application (client) ID", "secret": False},
                {"key": "tenant_id", "label": "Directory (tenant) ID", "secret": False},
                {"key": "client_secret", "label": "Client secret VALUE", "secret": True}]},
    {"key": "pub_linkedin", "name": "LinkedIn", "priority": 2,
     "unlocks": "Daily LinkedIn posts + campaign cross-posting.",
     "console_url": "https://www.linkedin.com/developers/apps",
     "console_hint": "Create app -> Auth tab -> add the redirect URL from One-click Connect -> "
                     "copy Client ID + Secret. After saving here, click Connect on the LinkedIn tile.",
     "save": "pub_linkedin", "needs_connect": True,
     "fields": [{"key": "li_client_id", "label": "LinkedIn Client ID", "secret": False},
                {"key": "li_client_secret", "label": "LinkedIn Client Secret", "secret": True}]},
    {"key": "gbp", "name": "Google Business Profile", "priority": 2,
     "unlocks": "Daily local updates on your Google listing (huge local-SEO lever).",
     "console_url": "https://console.cloud.google.com/apis/credentials",
     "console_hint": "OAuth client (Web) -> add the redirect URL from One-click Connect -> copy "
                     "ID + secret. After saving, Connect on the GBP tile, then pick your location.",
     "save": "gbp", "needs_connect": True,
     "fields": [{"key": "client_id", "label": "OAuth Client ID", "secret": False},
                {"key": "client_secret", "label": "OAuth Client Secret", "secret": True}]},
    {"key": "stripe", "name": "Stripe payments", "priority": 2,
     "unlocks": "Clients pay invoices online; payments auto-reconcile.",
     "console_url": "https://dashboard.stripe.com/apikeys",
     "console_hint": "Developers -> API keys -> copy the Secret key (sk_live_...)",
     "save": "stripe",
     "fields": [{"key": "secret_key", "label": "Stripe Secret key", "secret": True}]},
    {"key": "smtp", "name": "Outbound email (SMTP)", "priority": 2,
     "unlocks": "Client reports, invoices, SLA alerts, weekly digest, payment reminders BY EMAIL.",
     "console_url": None,
     "console_hint": "Server env only: SMTP_HOST/PORT/USER/PASSWORD/FROM (e.g. M365 SMTP or "
                     "Postmark), then restart Pulse.",
     "save": None, "fields": []},
    {"key": "quickbooks", "name": "QuickBooks Online", "priority": 3,
     "unlocks": "Pulse invoices sync into QuickBooks.",
     "console_url": "https://developer.intuit.com/app/developer/dashboard",
     "console_hint": "Create app -> Keys & OAuth -> add the redirect URL from One-click Connect -> "
                     "copy Client ID + Secret. After saving, Connect on the QuickBooks tile.",
     "save": "quickbooks", "needs_connect": True,
     "fields": [{"key": "client_id", "label": "QuickBooks Client ID", "secret": False},
                {"key": "client_secret", "label": "QuickBooks Client Secret", "secret": True}]},
    {"key": "hubspot", "name": "HubSpot", "priority": 3,
     "unlocks": "CRM contact sync to HubSpot.",
     "console_url": "https://app.hubspot.com/private-apps",
     "console_hint": "Private apps -> Create -> scope crm.objects.contacts read/write -> copy token",
     "save": "hubspot",
     "fields": [{"key": "token", "label": "HubSpot private-app token", "secret": True}]},
    {"key": "dialpad", "name": "Dialpad", "priority": 3,
     "unlocks": "Click-to-call + power dialer + call coaching from the CRM.",
     "console_url": "https://dialpad.com/apps",
     "console_hint": "Admin settings -> API keys -> create key",
     "save": "dialpad",
     "fields": [{"key": "api_key", "label": "Dialpad API key", "secret": True}]},
    {"key": "google_places", "name": "Google Places (lead gen)", "priority": 3,
     "unlocks": "Prospecting engine: pull ranked business leads per metro/industry.",
     "console_url": "https://console.cloud.google.com/apis/credentials",
     "console_hint": "Create an API key restricted to Places API -> copy it",
     "save": "google_places",
     "fields": [{"key": "api_key", "label": "Google Places API key", "secret": True}]},
    {"key": "tacticalrmm", "name": "TacticalRMM bridge", "priority": 3,
     "unlocks": "Legacy RMM view - optional; Pulse's native agent replaces it.",
     "console_url": None,
     "console_hint": "Your TRMM server -> Settings -> API keys",
     "save": "tacticalrmm",
     "fields": [{"key": "base_url", "label": "TRMM API base URL", "secret": False},
                {"key": "api_key", "label": "TRMM API key", "secret": True}]},
]

_CONNECTOR_BY_KEY = {c["key"]: c for c in CONNECTORS}


class SaveCredIn(BaseModel):
    values: dict


@router.post("/connections/{key}")
def save_connection(key: str, body: SaveCredIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER))):
    """Enter-credential: save one connector's fields, ENCRYPTED at rest. Blank
    values are ignored (keeps the saved secret). Secret-named keys are auto-
    encrypted by the vault; ids/urls are stored plainly."""
    spec = _CONNECTOR_BY_KEY.get(key)
    if not spec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown connector '{key}'.")
    if not spec.get("save") or not spec.get("fields"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "This connector is configured elsewhere (see its hint).")
    allowed = {f["key"] for f in spec["fields"]}
    payload = {k: str(v).strip() for k, v in (body.values or {}).items()
               if k in allowed and str(v).strip()}
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to save - fill in a field.")

    prov = spec["save"]
    if prov == "anthropic":
        from ...services import ai as ai_svc
        secure_config.upsert_platform(db, "anthropic", "Claude (Anthropic)", "AI",
                                      {"api_key": payload["api_key"]})
        ai_svc.refresh_key_cache()
        return {"key": key, "connected": ai_svc.enabled()}
    if prov == "gitlab_sites":
        from ...services import jp_site
        jp_site.save_shared_token(db, payload["token"])
        return {"key": key,
                "connected": jp_site.configured(db, "bvtech") and jp_site.configured(db, "jp")}

    _names = {"m365_mailbox": ("M365 Mailbox", "Mail"),
              "pub_linkedin": ("LinkedIn", "Publishing"),
              "gbp": ("Google Business Profile", "Publishing"),
              "stripe": ("Stripe", "Payments"),
              "quickbooks": ("QuickBooks", "Accounting"),
              "hubspot": ("HubSpot", "CRM"),
              "dialpad": ("Dialpad", "Telephony"),
              "google_places": ("Google Places", "Prospecting"),
              "tacticalrmm": ("TacticalRMM", "RMM")}
    nm, cat = _names.get(prov, (spec["name"], "Integration"))
    secure_config.upsert_platform(db, prov, nm, cat, payload)
    return {"key": key, "connected": True, "needs_connect": spec.get("needs_connect", False)}
