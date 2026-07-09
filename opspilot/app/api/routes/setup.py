"""v0.72 Guided setup status — a friendly "what's connected / what's left"
checklist so a new operator can get fully live without hunting through Settings.
Staff-only; read-only aggregation over the vault + a couple of tables.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
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
    from ...services import ai as ai_svc, jp_site, oauth as oauth_svc
    from ...models import OAuthToken

    def vault_has(provider: str, *keys: str) -> bool:
        conn = secure_config.get_platform(db, provider)
        cfg = (conn.config if conn else None) or {}
        return all(secure_config.get_secret(cfg, k) or cfg.get(k) for k in keys)

    li_oauth = db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count() > 0
    gbp_oauth = db.query(OAuthToken).filter(OAuthToken.provider == "google_gbp").count() > 0
    qb_oauth = db.query(OAuthToken).filter(OAuthToken.provider == "quickbooks").count() > 0

    items = [
        # -------- Priority 1: the brain + the money-makers --------
        {"key": "anthropic", "name": "Claude AI (Anthropic)", "priority": 1,
         "connected": ai_svc.enabled(),
         "unlocks": "EVERYTHING intelligent: Copilot + fleet sweeps, ticket triage, "
                    "vCIO reviews, morning briefing, foresight narratives, all daily content writing.",
         "console_url": "https://console.anthropic.com/settings/keys",
         "console_hint": "Console → API keys → Create Key → copy (starts sk-ant-…)",
         "where": "Paste right here in the Connection Center", "inline": "anthropic"},
        {"key": "gitlab_sites", "name": "Websites (bvtech.org + jordanpolasek.com)", "priority": 1,
         "connected": jp_site.configured(db, "bvtech") and jp_site.configured(db, "jp"),
         "unlocks": "Daily blog posts to BOTH sites with Cloudflare deploy verification + auto-revert.",
         "console_url": "https://gitlab.com/-/user_settings/personal_access_tokens",
         "console_hint": "Generate token → name 'Pulse Publisher' → scope: api → copy (glpat-…)",
         "where": "Marketing → Content Autopilot → paste token → Connect both sites"},
        {"key": "m365_mailbox", "name": "Microsoft 365 (mail + SSO)", "priority": 1,
         "connected": vault_has("m365_mailbox", "client_id", "client_secret")
                      or bool(_s.M365_CLIENT_ID and _s.M365_CLIENT_SECRET),
         "unlocks": "Secure mailbox (read/send as help@bvtech.org), Microsoft sign-in for you + clients.",
         "console_url": "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
         "console_hint": "App registrations → New → add the redirect URL from One-click Connect → "
                         "Certificates & secrets → New client secret",
         "where": "Settings → M365 Mailbox / SSO cards"},
        # -------- Priority 2: growth + billing --------
        {"key": "pub_linkedin", "name": "LinkedIn", "priority": 2,
         "connected": li_oauth or vault_has("pub_linkedin", "access_token"),
         "unlocks": "Daily LinkedIn posts (Content Autopilot) + campaign cross-posting.",
         "console_url": "https://www.linkedin.com/developers/apps",
         "console_hint": "Create app → Auth tab → add the redirect URL from One-click Connect → "
                         "copy Client ID + Secret → save in Settings → then Connect",
         "where": "Settings → One-click Connect (LinkedIn tile)"},
        {"key": "gbp", "name": "Google Business Profile", "priority": 2,
         "connected": gbp_oauth or vault_has("gbp", "refresh_token"),
         "unlocks": "Daily local updates on your Google listing (huge local-SEO lever).",
         "console_url": "https://console.cloud.google.com/apis/credentials",
         "console_hint": "OAuth client (Web) → add the redirect URL from One-click Connect → "
                         "copy ID + secret → save in Settings → Connect → pick your location",
         "where": "Settings → Google Business Profile card"},
        {"key": "stripe", "name": "Stripe payments", "priority": 2,
         "connected": vault_has("stripe", "secret_key"),
         "unlocks": "Clients pay invoices online; payments auto-reconcile.",
         "console_url": "https://dashboard.stripe.com/apikeys",
         "console_hint": "Developers → API keys → copy the Secret key (sk_live_…)",
         "where": "Settings → Payments card"},
        {"key": "smtp", "name": "Outbound email (SMTP)", "priority": 2,
         "connected": bool(_s.SMTP_HOST),
         "unlocks": "Client reports, invoices, SLA alerts, weekly digest, payment reminders BY EMAIL.",
         "console_url": None,
         "console_hint": "Server env: SMTP_HOST/PORT/USER/PASSWORD/FROM (e.g. M365 SMTP or Postmark), "
                         "then restart Pulse",
         "where": "Server .env (one-time)"},
        # -------- Priority 3: nice-to-haves --------
        {"key": "quickbooks", "name": "QuickBooks Online", "priority": 3,
         "connected": qb_oauth or vault_has("quickbooks", "refresh_token"),
         "unlocks": "Pulse invoices sync into QuickBooks.",
         "console_url": "https://developer.intuit.com/app/developer/dashboard",
         "console_hint": "Create app → Keys & OAuth → add the redirect URL from One-click Connect → "
                         "copy Client ID + Secret",
         "where": "Settings → QuickBooks card, then One-click Connect"},
        {"key": "hubspot", "name": "HubSpot", "priority": 3,
         "connected": vault_has("hubspot", "token"),
         "unlocks": "CRM contact sync to HubSpot.",
         "console_url": "https://app.hubspot.com/private-apps",
         "console_hint": "Private apps → Create → scope crm.objects.contacts read/write → copy token",
         "where": "Settings → HubSpot card"},
        {"key": "dialpad", "name": "Dialpad", "priority": 3,
         "connected": vault_has("dialpad", "api_key"),
         "unlocks": "Click-to-call + power dialer + call coaching from the CRM.",
         "console_url": "https://dialpad.com/apps",
         "console_hint": "Admin settings → API keys → create key",
         "where": "Settings → Dialpad card"},
        {"key": "google_places", "name": "Google Places (lead gen)", "priority": 3,
         "connected": vault_has("google_places", "api_key"),
         "unlocks": "Prospecting engine: pull ranked business leads per metro/industry.",
         "console_url": "https://console.cloud.google.com/apis/credentials",
         "console_hint": "API key restricted to Places API",
         "where": "Settings → Prospecting card"},
        {"key": "tacticalrmm", "name": "TacticalRMM bridge", "priority": 3,
         "connected": vault_has("tacticalrmm", "api_key"),
         "unlocks": "Legacy RMM view — optional; Pulse's native agent replaces it.",
         "console_url": None, "console_hint": "Your TRMM server → API keys",
         "where": "Settings → TacticalRMM card"},
    ]
    p1 = [i for i in items if i["priority"] == 1]
    done = sum(1 for i in items if i["connected"])
    return {"items": items, "total": len(items), "connected": done,
            "go_live_ready": all(i["connected"] for i in p1),
            "score_pct": round(100 * done / len(items))}
