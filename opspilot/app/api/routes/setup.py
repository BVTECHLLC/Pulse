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
def _ready(state: str, label: str, action: str) -> dict:
    return {"state": state, "status_label": label, "next_action": action}


def _connector_readiness(db, spec: dict, connected: bool) -> dict:
    """Plain-English 'what's left to do' for one connector tile, so the Settings
    page SHOWS the exact next step instead of a bare red/green dot. (v1.145)
    state: 'ready' (fully working) | 'action' (saved but one step remains) |
    'missing' (nothing saved yet)."""
    from ...models import OAuthToken
    key = spec["key"]

    def vcfg(provider):
        c = secure_config.get_platform(db, provider)
        return (c.config if c else None) or {}

    def has_tok(provider):
        return db.query(OAuthToken).filter(OAuthToken.provider == provider).count() > 0

    def secret(cfg, k):
        return secure_config.get_secret(cfg, k) or cfg.get(k)

    # --- Google Business listings: creds -> Connect -> Account/Location -> ready
    gbp_map = {"gbp": ("google_gbp", "gbp", "google_business"),
               "gbp_personal": ("google_gbp_personal", "gbp_personal", "google_business_personal")}
    if key in gbp_map:
        provider, vkey, channel = gbp_map[key]
        cfg = vcfg(vkey)
        app = bool(secret(cfg, "client_id")) and bool(secure_config.get_secret(cfg, "client_secret"))
        tok = has_tok(provider) or bool(secure_config.get_secret(cfg, "refresh_token"))
        loc = bool(cfg.get("account_name") and cfg.get("location_name"))
        if autopost.get_reauth(db, channel):
            return _ready("action", "Reconnect needed",
                          "Google token expired — click Connect to re-authorize.")
        if not app:
            return _ready("missing", "Not set up",
                          "Paste your Google OAuth Client ID + Secret below, then click Connect.")
        if not tok:
            return _ready("action", "Click Connect",
                          "Credentials saved ✓ — now click Connect and approve with your Google account.")
        if not loc:
            return _ready("action", "Set Account + Location",
                          "Connected ✓ — now fill Account name + Location name (from business.google.com) so it can post.")
        return _ready("ready", "Ready", "Posting one update per week. Nothing more to do.")

    # --- LinkedIn publisher: app creds and/or a pasted token -> daily posting
    if key == "pub_linkedin":
        cfg = vcfg("pub_linkedin")
        app = bool(secret(cfg, "li_client_id")) and bool(secure_config.get_secret(cfg, "li_client_secret"))
        manual = bool(secure_config.get_secret(cfg, "access_token")) and bool(secret(cfg, "person_urn"))
        tok_oauth = has_tok("linkedin")
        if autopost.get_reauth(db, "linkedin"):
            return _ready("action", "Reconnect needed",
                          "LinkedIn token expired — click Connect (or paste a fresh token) to resume daily posting.")
        if tok_oauth or manual:
            if not app:
                return _ready("ready", "Connected",
                              "Posting daily via your saved token. Tip: also paste the app Client ID + Secret "
                              "and click Connect so the token self-refreshes and never expires.")
            return _ready("ready", "Ready", "Posting daily with self-refreshing OAuth. Nothing more to do.")
        if app:
            return _ready("action", "Click Connect",
                          "App credentials saved ✓ — click Connect and approve to start daily posting.")
        return _ready("missing", "Not set up",
                      "Paste the LinkedIn app Client ID + Secret below, then click Connect.")

    # --- QuickBooks / other one-click connectors
    if spec.get("needs_connect"):
        prov = {"quickbooks": "quickbooks"}.get(key, key)
        if connected and has_tok(prov):
            return _ready("ready", "Connected", "Authorized and ready.")
        if connected:
            return _ready("action", "Click Connect",
                          "Credentials saved ✓ — click Connect to authorize.")
        return _ready("missing", "Not set up", spec.get("console_hint") or "Add credentials, then Connect.")

    # --- Everything else (API-key style)
    if connected:
        return _ready("ready", "Connected", "")
    return _ready("missing", "Not set up", spec.get("console_hint") or "Add credentials to enable.")


@router.get("/connections")
def connection_center(db: Session = Depends(get_db),
                      user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """Every connector with: live status, what it unlocks, a deep link to the
    provider console (Get credential), and the fields to paste it right here
    (Enter credential -> encrypted in the vault)."""
    from ...services import ai as ai_svc, cloudflare as _cf_svc_mod, jp_site
    from ...models import OAuthToken

    def vault_has(provider, *keys):
        conn = secure_config.get_platform(db, provider)
        cfg = (conn.config if conn else None) or {}
        return all(secure_config.get_secret(cfg, k) or cfg.get(k) for k in keys)

    li = db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count() > 0
    gbp = db.query(OAuthToken).filter(OAuthToken.provider == "google_gbp").count() > 0
    gbp_p = db.query(OAuthToken).filter(OAuthToken.provider == "google_gbp_personal").count() > 0
    qb = db.query(OAuthToken).filter(OAuthToken.provider == "quickbooks").count() > 0

    status = {
        "anthropic": ai_svc.enabled(),
        "gitlab_sites": jp_site.configured(db, "bvtech") and jp_site.configured(db, "jp"),
        "bvtech_github": jp_site.get_config(db, "bvtech").get("forge") == "github",
        "cloudflare": _cf_svc_mod.configured(db),
        "m365_mailbox": vault_has("m365_mailbox", "client_id", "client_secret")
                        or bool(_s.M365_CLIENT_ID and _s.M365_CLIENT_SECRET),
        "pub_linkedin": li or vault_has("pub_linkedin", "li_client_id"),
        "gbp": gbp or vault_has("gbp", "client_id"),
        "gbp_personal": gbp_p or vault_has("gbp_personal", "client_id"),
        "stripe": vault_has("stripe", "secret_key"),
        "smtp": bool(_s.SMTP_HOST),
        "quickbooks": qb or vault_has("quickbooks", "client_id"),
        "hubspot": vault_has("hubspot", "token"),
        "dialpad": vault_has("dialpad", "api_key"),
        "google_places": vault_has("google_places", "api_key"),
        "tacticalrmm": vault_has("tacticalrmm", "api_key"),
        "groq": vault_has("groq", "api_key"),
        "custom_api": vault_has("custom_api", "api_key"),
        "cloudflare_analytics": vault_has("cloudflare_analytics", "api_token"),
    }
    items = []
    for spec in CONNECTORS:
        it = dict(spec)
        it["connected"] = bool(status.get(spec["key"]))
        it["fields"] = spec.get("fields", [])
        it["can_enter"] = bool(spec.get("fields"))
        it["needs_connect"] = spec.get("needs_connect", False)
        # Detect the silent "saved but unreadable" state (SECRET_KEY changed):
        # a ciphertext is stored but won't decrypt -> tell the user to re-enter.
        sp = spec.get("secret_provider")
        it["credential_state"] = None
        if sp:
            conn = secure_config.get_platform(db, sp)
            cfg = (conn.config if conn else None) or {}
            it["credential_state"] = secure_config.secret_state(cfg, spec["secret_field"])
        it["testable"] = spec["key"] in ("gitlab_sites", "anthropic", "stripe", "hubspot",
                                         "cloudflare", "bvtech_github", "groq")
        # v1.145: plain-English "what's left to do" so each tile is self-explaining.
        rd = _connector_readiness(db, spec, it["connected"])
        it["state"] = rd["state"]                 # ready | action | missing
        it["status_label"] = rd["status_label"]   # short pill text
        it["next_action"] = rd["next_action"]     # exact next step
        # A tile is "ready" only when fully functional (not just creds saved).
        it["ready"] = rd["state"] == "ready"
        items.append(it)
    p1 = [i for i in items if i["priority"] == 1]
    done = sum(1 for i in items if i["connected"])
    ready_n = sum(1 for i in items if i.get("ready"))
    # A compact "what still needs a step" list the UI can show at the top.
    needs = [{"key": i["key"], "name": i["name"], "status_label": i["status_label"],
              "next_action": i["next_action"]}
             for i in items if i["state"] == "action"]
    return {"items": items, "total": len(items), "connected": done, "ready": ready_n,
            "go_live_ready": all(i["connected"] for i in p1),
            "needs_action": needs,
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
     "save": "anthropic", "secret_provider": "anthropic", "secret_field": "api_key",
     "fields": [{"key": "api_key", "label": "Anthropic API key", "secret": True}]},
    {"key": "gitlab_sites", "name": "Websites (bvtech.org + jordanpolasek.com)", "priority": 1,
     "unlocks": "Daily blog posts to BOTH sites with Cloudflare deploy verification + auto-revert.",
     "console_url": "https://gitlab.com/-/user_settings/personal_access_tokens",
     "console_hint": "Generate token -> name 'Pulse Publisher' -> scope: api -> copy (glpat-...)",
     "save": "gitlab_sites", "secret_provider": "gitlab", "secret_field": "token",
     "fields": [{"key": "token", "label": "GitLab token (api scope) - connects BOTH sites", "secret": True}]},
    {"key": "bvtech_github", "name": "bvtech.org on GitHub (optional)", "priority": 3,
     "unlocks": "OPTIONAL - only if bvtech.org ever moves to GitHub. The live site "
                "deploys from GitLab (BVTECHLLC-group/bvtech-website-new), which the "
                "Websites tile above already covers. Leave this disconnected.",
     "console_url": "https://github.com/settings/personal-access-tokens/new",
     "console_hint": "Fine-grained token -> Repository access: Only select repositories -> "
                     "bvtech-website-new -> Permissions: Contents = Read and write -> Generate",
     "save": "bvtech_github", "secret_provider": "bvtech_site", "secret_field": "gh_token",
     "fields": [{"key": "gh_token",
                 "label": "GitHub fine-grained PAT (Contents: Read and write)", "secret": True},
                {"key": "github_repo",
                 "label": "Repo (owner/name on GitHub)", "secret": False},
                {"key": "github_active",
                 "label": "Use GitHub instead of GitLab? (yes/no - default yes once a "
                          "token is saved; set no to switch back to GitLab)", "secret": False}]},
    {"key": "cloudflare", "name": "Cloudflare (instant cache purge)", "priority": 1,
     "unlocks": "Published posts show on the sites IMMEDIATELY - without this, "
                "Cloudflare's edge cache can serve the old page for hours.",
     "console_url": "https://dash.cloudflare.com/profile/api-tokens",
     "console_hint": "Create Token -> Custom -> permissions Zone:Read + Cache Purge:Purge "
                     "-> include zones bvtech.org AND jordanpolasek.com -> copy",
     "save": "cloudflare", "secret_provider": "cloudflare", "secret_field": "api_token",
     "fields": [{"key": "api_token",
                 "label": "Cloudflare API Token - or your Global API Key", "secret": True},
                {"key": "auth_email",
                 "label": "Cloudflare account email (ONLY needed with the Global API Key)",
                 "secret": False}]},
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
    {"key": "gbp", "name": "Google Business Profile (Business)", "priority": 2,
     "unlocks": "WEEKLY local update on your BVTech Google listing (big local-SEO lever). "
                "Google is intentionally capped at one post per week so you never risk spam.",
     "console_url": "https://console.cloud.google.com/apis/credentials",
     "console_hint": "OAuth client (Web) -> add the redirect URL from One-click Connect -> copy "
                     "ID + secret. After saving, Connect on the GBP tile, then fill Account + "
                     "Location name below (from Business Profile Manager).",
     "save": "gbp", "needs_connect": True,
     "fields": [{"key": "client_id", "label": "OAuth Client ID", "secret": False},
                {"key": "client_secret", "label": "OAuth Client Secret", "secret": True},
                {"key": "account_name", "label": "Account name (accounts/123…)", "secret": False},
                {"key": "location_name", "label": "Location name (locations/456…)", "secret": False}]},
    {"key": "gbp_personal", "name": "Google Business Profile (Personal — jordanpolasek.com)",
     "priority": 2,
     "unlocks": "WEEKLY update on your PERSONAL Google listing (jordanpolasek.com), separate "
                "from the BVTech business listing. Also one post per week max — never spammed.",
     "console_url": "https://console.cloud.google.com/apis/credentials",
     "console_hint": "Use the SAME Google Cloud project as the business listing — just add this "
                     "tile's redirect URL as a second Authorized redirect URI, then Connect here "
                     "with your personal Google account (hydro77845@gmail.com) and fill Account + "
                     "Location below.",
     "save": "gbp_personal", "needs_connect": True,
     "fields": [{"key": "client_id", "label": "OAuth Client ID", "secret": False},
                {"key": "client_secret", "label": "OAuth Client Secret", "secret": True},
                {"key": "account_name", "label": "Account name (accounts/123…)", "secret": False},
                {"key": "location_name", "label": "Location name (locations/456…)", "secret": False}]},
    {"key": "cloudflare_analytics", "name": "Cloudflare Threat Analytics (live Threat Map)",
     "priority": 3,
     "unlocks": "Feeds the live bvtech.org Threat Map with REAL Cloudflare edge numbers "
                "(blocked attacks, bot traffic) — so it's driven by Pulse, never a stray "
                "Worker token that silently dies.",
     "console_url": "https://dash.cloudflare.com/profile/api-tokens",
     "console_hint": "Create Token → permission Account Analytics:Read (or Zone Analytics:Read) "
                     "on bvtech.org → copy. Then paste your bvtech.org Zone ID (zone Overview page).",
     "save": "cloudflare_analytics", "secret_provider": "cloudflare_analytics", "secret_field": "api_token",
     "fields": [{"key": "api_token", "label": "Cloudflare Analytics token", "secret": True},
                {"key": "zone_id", "label": "bvtech.org Zone ID", "secret": False}]},
    {"key": "stripe", "name": "Stripe payments", "priority": 2,
     "unlocks": "Clients pay invoices online; payments auto-reconcile.",
     "console_url": "https://dashboard.stripe.com/apikeys",
     "console_hint": "Developers -> API keys -> copy the Secret key (sk_live_...)",
     "save": "stripe", "secret_provider": "stripe", "secret_field": "secret_key",
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
     "save": "hubspot", "secret_provider": "hubspot", "secret_field": "token",
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
    {"key": "groq", "name": "Groq (FREE AI engine)", "priority": 2,
     "unlocks": "FREE AI: runs daily posts, Copilot, ticket triage and all content "
                "writing on Groq's free API instead of spending paid Claude tokens. "
                "Claude stays as the premium fallback when Groq is down.",
     "console_url": "https://console.groq.com/keys",
     "console_hint": "console.groq.com -> API Keys -> Create API Key -> copy (starts gsk_...). "
                     "Free to create; no credit card.",
     "save": "groq", "secret_provider": "groq", "secret_field": "api_key",
     "fields": [{"key": "api_key", "label": "Groq API key (gsk_...)", "secret": True},
                {"key": "model",
                 "label": "Model (optional - default llama-3.3-70b-versatile)", "secret": False}]},
    {"key": "custom_api", "name": "Custom API key (general slot)", "priority": 3,
     "unlocks": "A general-purpose, encrypted slot to store ANY API key or token you "
                "want Pulse to keep safe. Label what it's for and paste it - then tell "
                "me and I'll wire it into a feature.",
     "console_url": None,
     "console_hint": "Paste any key you want stored securely (encrypted at rest). Add a "
                     "label and, if the service needs one, a base URL.",
     "save": "custom_api", "secret_provider": "custom_api", "secret_field": "api_key",
     "fields": [{"key": "label", "label": "What is this key for? (e.g. OpenAI, Twilio, SendGrid)",
                 "secret": False},
                {"key": "api_key", "label": "API key / token", "secret": True},
                {"key": "base_url", "label": "Base URL (optional)", "secret": False}]},
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
        v = _verify_connector(db, "anthropic")
        return {"key": key, "connected": ai_svc.enabled(),
                "verified": v.get("ok"), "detail": v.get("detail")}
    if prov == "groq":
        from ...services import ai as ai_svc
        gp = {k: v for k, v in payload.items() if k in ("api_key", "model")}
        secure_config.upsert_platform(db, "groq", "Groq (free AI)", "AI", gp)
        ai_svc.refresh_key_cache()            # pick up the new key immediately
        try:
            st = ai_svc.free_llm_selftest()
            detail = (f"Groq live — using {st.get('model_used')}" if st.get("ok")
                      else "Saved, but the live test failed: " + (st.get("error") or "unknown")[:160])
            ok = bool(st.get("ok"))
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"Saved, but could not reach Groq: {str(e)[:160]}"
        return {"key": key, "connected": ai_svc.free_llm_enabled(),
                "verified": ok, "detail": detail}
    if prov == "gitlab_sites":
        from ...services import jp_site
        jp_site.save_shared_token(db, payload["token"])
        v = jp_site.verify_token(db)
        return {"key": key,
                "connected": jp_site.configured(db, "bvtech") and jp_site.configured(db, "jp"),
                "verified": v.get("ok"), "detail": v.get("detail")}
    if prov == "bvtech_github":
        from ...services import jp_site
        gh_payload = {k: v for k, v in payload.items()
                      if k in ("gh_token", "github_repo", "github_active")}
        secure_config.upsert_platform(db, "bvtech_site", "BVTech.org Site", "Publishing",
                                      gh_payload)
        # Turning the switch off is a valid save even with no token in payload.
        if jp_site.get_config(db, "bvtech").get("forge") != "github":
            return {"key": key, "connected": False, "verified": True,
                    "detail": "GitHub publishing is OFF - bvtech.org publishes via "
                              "GitLab (the Websites tile)."}
        v = jp_site.gh_verify(db)
        return {"key": key, "connected": v.get("ok", False),
                "verified": v.get("ok"), "detail": v.get("detail")}
    if prov == "cloudflare":
        from ...services import cloudflare
        cf_payload = {k: v for k, v in payload.items() if k in ("api_token", "auth_email")}
        secure_config.upsert_platform(db, "cloudflare", "Cloudflare", "Publishing", cf_payload)
        # New credential -> stale zone cache could point at zones the old
        # credential saw; clear it so discovery re-runs with the new auth.
        conn = secure_config.get_platform(db, "cloudflare")
        raw = dict((conn.config if conn else None) or {})
        if raw.pop("zones", None) is not None:
            conn.config = raw
            db.commit()
        v = cloudflare.verify(db)
        return {"key": key, "connected": cloudflare.configured(db),
                "verified": v.get("ok"), "detail": v.get("detail")}

    _names = {"m365_mailbox": ("M365 Mailbox", "Mail"),
              "pub_linkedin": ("LinkedIn", "Publishing"),
              "gbp": ("Google Business Profile", "Publishing"),
              "gbp_personal": ("Google Business Profile (Personal)", "Publishing"),
              "stripe": ("Stripe", "Payments"),
              "quickbooks": ("QuickBooks", "Accounting"),
              "hubspot": ("HubSpot", "CRM"),
              "dialpad": ("Dialpad", "Telephony"),
              "google_places": ("Google Places", "Prospecting"),
              "tacticalrmm": ("TacticalRMM", "RMM"),
              "groq": ("Groq (free AI)", "AI"),
              "custom_api": ("Custom API key", "Integration"),
              "cloudflare_analytics": ("Cloudflare Threat Analytics", "Telemetry")}
    nm, cat = _names.get(prov, (spec["name"], "Integration"))
    secure_config.upsert_platform(db, prov, nm, cat, payload)
    if prov in ("gbp", "gbp_personal", "pub_linkedin"):
        # New credentials lift the delivery pause; queued posts resume next tick.
        autopost.clear_reauth(db, prov)
    return {"key": key, "connected": True, "needs_connect": spec.get("needs_connect", False)}


# --------------------------------------------------------------------------- #
# v1.25 Live verification — the tile's green/red means "the credential WORKS",
# not just "a string is stored". Turns "saved but red" into a real answer.
# --------------------------------------------------------------------------- #
def _verify_connector(db: Session, key: str) -> dict:
    from ...services import ai as ai_svc, cloudflare, jp_site
    if key == "gitlab_sites":
        return jp_site.verify_token(db)
    if key == "cloudflare":
        return cloudflare.verify(db)
    if key == "bvtech_github":
        return jp_site.gh_verify(db)
    if key == "anthropic":
        if not ai_svc.enabled():
            return {"ok": False, "detail": "No Claude key stored yet."}
        try:
            ai_svc.complete("Reply with exactly: ok", "ping", max_tokens=8)
            return {"ok": True, "detail": f"Verified - Claude responded (key from {ai_svc.key_source()})."}
        except ai_svc.AIError as e:
            return {"ok": False, "detail": str(e)[:160]}
    if key == "stripe":
        conn = secure_config.get_platform(db, "stripe")
        sk = secure_config.get_secret((conn.config if conn else None) or {}, "secret_key")
        if not sk:
            return {"ok": False, "detail": "No Stripe secret key stored yet."}
        import urllib.request
        try:
            req = urllib.request.Request("https://api.stripe.com/v1/balance",
                                         headers={"Authorization": f"Bearer {sk}"})
            with urllib.request.urlopen(req, timeout=20):
                return {"ok": True, "detail": "Verified - Stripe key authenticates."}
        except Exception as e:  # noqa: BLE001
            m = str(e)
            return {"ok": False, "detail": "Stripe rejected the key (401)." if "401" in m
                    else f"Stripe check failed: {m[:120]}"}
    if key == "hubspot":
        conn = secure_config.get_platform(db, "hubspot")
        tok = secure_config.get_secret((conn.config if conn else None) or {}, "token")
        if not tok:
            return {"ok": False, "detail": "No HubSpot token stored yet."}
        import urllib.request
        try:
            req = urllib.request.Request(
                "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
                headers={"Authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(req, timeout=20):
                return {"ok": True, "detail": "Verified - HubSpot token authenticates."}
        except Exception as e:  # noqa: BLE001
            m = str(e)
            return {"ok": False, "detail": "HubSpot rejected the token (401)." if "401" in m
                    else f"HubSpot check failed: {m[:120]}"}
    return {"ok": None, "detail": "No live test for this connector."}


@router.post("/connections/{key}/test")
def test_connection(key: str, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if key not in _CONNECTOR_BY_KEY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown connector '{key}'.")
    return _verify_connector(db, key)
