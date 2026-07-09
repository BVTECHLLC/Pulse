"""v1.23 Browser & SaaS Guardian — kill the app blindspot, then govern it.

Classic software inventory can't see browser-based apps, so shadow IT and SaaS
sprawl are invisible to every RMM. Pulse's agent now harvests each device's
browser reality (extensions installed + the web apps actually used, from
browser data) and this service turns it into a governed catalog:

  * ingest()      — upsert what a device reported (deduped per device+kind+id)
  * inventory()   — the per-client rollup: each SaaS/web app (mapped to a
                    friendly name/category via the catalog below) and each
                    extension, with device counts, usage weight and its
                    review status (unreviewed / approved / blocked)
  * decide()      — approve or block an identifier for a client
  * agent_policy()— what one device must ENFORCE: blocked domains (hosts-file),
                    blocked extension ids (Chrome/Edge blocklist policy), and
                    the 'protect browsers' switch (SafeBrowsing/SmartScreen on)

Deterministic; the agent applies policy idempotently on its hourly tick.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import BrowserItem, BrowserPolicy, Client, Device

MAX_ITEMS_PER_REPORT = 120

# Domains that are plumbing, not "apps someone uses" — never listed.
IGNORE_SUFFIXES = (
    "google.com", "gstatic.com", "googleapis.com", "googleusercontent.com",
    "doubleclick.net", "googletagmanager.com", "google-analytics.com",
    "bing.com", "msn.com", "microsoft.com", "microsoftonline.com", "msftauth.net",
    "windows.com", "windowsupdate.com", "live.com", "azureedge.net",
    "cloudflare.com", "cloudfront.net", "akamaized.net", "fastly.net",
    "mozilla.org", "mozilla.net", "firefox.com", "duckduckgo.com",
    "yahoo.com", "wikipedia.org", "gvt1.com", "adnxs.com", "criteo.com",
    "facebook.net", "fbcdn.net", "twimg.com", "ytimg.com", "youtube.com",
    "localhost",
)

# Known SaaS: domain suffix -> (name, category). Unknown domains still show,
# under their own hostname, category "Uncategorized".
SAAS_CATALOG: dict[str, tuple[str, str]] = {
    "dropbox.com": ("Dropbox", "File storage"),
    "box.com": ("Box", "File storage"),
    "drive.google.com": ("Google Drive", "File storage"),
    "wetransfer.com": ("WeTransfer", "File transfer"),
    "slack.com": ("Slack", "Messaging"),
    "discord.com": ("Discord", "Messaging"),
    "zoom.us": ("Zoom", "Meetings"),
    "teams.microsoft.com": ("Microsoft Teams", "Meetings"),
    "meet.google.com": ("Google Meet", "Meetings"),
    "notion.so": ("Notion", "Docs & wiki"),
    "notion.site": ("Notion", "Docs & wiki"),
    "atlassian.net": ("Jira / Confluence", "Project mgmt"),
    "trello.com": ("Trello", "Project mgmt"),
    "asana.com": ("Asana", "Project mgmt"),
    "monday.com": ("Monday.com", "Project mgmt"),
    "clickup.com": ("ClickUp", "Project mgmt"),
    "airtable.com": ("Airtable", "Database"),
    "salesforce.com": ("Salesforce", "CRM"),
    "hubspot.com": ("HubSpot", "CRM"),
    "pipedrive.com": ("Pipedrive", "CRM"),
    "zendesk.com": ("Zendesk", "Support"),
    "freshdesk.com": ("Freshdesk", "Support"),
    "intercom.com": ("Intercom", "Support"),
    "quickbooks.intuit.com": ("QuickBooks Online", "Accounting"),
    "xero.com": ("Xero", "Accounting"),
    "gusto.com": ("Gusto", "Payroll/HR"),
    "adp.com": ("ADP", "Payroll/HR"),
    "bamboohr.com": ("BambooHR", "Payroll/HR"),
    "docusign.com": ("DocuSign", "e-Signature"),
    "docusign.net": ("DocuSign", "e-Signature"),
    "hellosign.com": ("Dropbox Sign", "e-Signature"),
    "pandadoc.com": ("PandaDoc", "e-Signature"),
    "canva.com": ("Canva", "Design"),
    "figma.com": ("Figma", "Design"),
    "adobe.com": ("Adobe Creative Cloud", "Design"),
    "mailchimp.com": ("Mailchimp", "Marketing"),
    "constantcontact.com": ("Constant Contact", "Marketing"),
    "chatgpt.com": ("ChatGPT", "AI"),
    "openai.com": ("OpenAI", "AI"),
    "claude.ai": ("Claude", "AI"),
    "gemini.google.com": ("Google Gemini", "AI"),
    "midjourney.com": ("Midjourney", "AI"),
    "github.com": ("GitHub", "Dev tools"),
    "gitlab.com": ("GitLab", "Dev tools"),
    "bitbucket.org": ("Bitbucket", "Dev tools"),
    "aws.amazon.com": ("AWS Console", "Cloud"),
    "portal.azure.com": ("Azure Portal", "Cloud"),
    "console.cloud.google.com": ("Google Cloud Console", "Cloud"),
    "digitalocean.com": ("DigitalOcean", "Cloud"),
    "linode.com": ("Linode / Akamai", "Cloud"),
    "godaddy.com": ("GoDaddy", "Domains/Hosting"),
    "namecheap.com": ("Namecheap", "Domains/Hosting"),
    "wix.com": ("Wix", "Website builder"),
    "squarespace.com": ("Squarespace", "Website builder"),
    "wordpress.com": ("WordPress.com", "Website builder"),
    "shopify.com": ("Shopify", "e-Commerce"),
    "stripe.com": ("Stripe", "Payments"),
    "paypal.com": ("PayPal", "Payments"),
    "square.com": ("Square", "Payments"),
    "netflix.com": ("Netflix", "Personal/Streaming"),
    "hulu.com": ("Hulu", "Personal/Streaming"),
    "spotify.com": ("Spotify", "Personal/Streaming"),
    "reddit.com": ("Reddit", "Social"),
    "facebook.com": ("Facebook", "Social"),
    "instagram.com": ("Instagram", "Social"),
    "tiktok.com": ("TikTok", "Social"),
    "x.com": ("X (Twitter)", "Social"),
    "linkedin.com": ("LinkedIn", "Social"),
    "whatsapp.com": ("WhatsApp Web", "Messaging"),
    "telegram.org": ("Telegram Web", "Messaging"),
    "web.telegram.org": ("Telegram Web", "Messaging"),
    "grammarly.com": ("Grammarly", "Writing"),
    "calendly.com": ("Calendly", "Scheduling"),
    "lastpass.com": ("LastPass", "Passwords"),
    "1password.com": ("1Password", "Passwords"),
    "bitwarden.com": ("Bitwarden", "Passwords"),
    "anydesk.com": ("AnyDesk", "Remote access"),
    "teamviewer.com": ("TeamViewer", "Remote access"),
    "chrome.google.com": ("Chrome Web Store", "Browser"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm_host(host: str) -> str:
    h = (host or "").strip().lower().rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    return h[:200]


def _ignored(host: str) -> bool:
    return any(host == suf or host.endswith("." + suf) for suf in IGNORE_SUFFIXES)


def classify(host: str) -> tuple[str, str]:
    """(friendly name, category) for a domain — catalog match by suffix."""
    h = _norm_host(host)
    for suf, (name, cat) in SAAS_CATALOG.items():
        if h == suf or h.endswith("." + suf):
            return name, cat
    return h, "Uncategorized"


def ingest(db: Session, device: Device, payload: dict) -> dict:
    """Upsert one device's browser report. Commits. Returns counts."""
    now = _utcnow()
    seen = {(r.kind, r.identifier): r for r in
            db.query(BrowserItem).filter(BrowserItem.device_id == device.id).all()}
    n_ext = n_web = 0
    for e in (payload.get("extensions") or [])[:MAX_ITEMS_PER_REPORT]:
        ident = str(e.get("id") or "").strip()[:200]
        if not ident:
            continue
        row = seen.get(("extension", ident))
        if row is None:
            row = BrowserItem(client_id=device.client_id, device_id=device.id,
                              kind="extension", identifier=ident, first_seen=now)
            db.add(row)
            seen[("extension", ident)] = row
        row.browser = str(e.get("browser") or "")[:20] or row.browser
        row.name = str(e.get("name") or "")[:200] or row.name or ident
        row.version = str(e.get("version") or "")[:40] or row.version
        row.permissions = str(e.get("permissions") or "")[:500] or row.permissions
        row.last_seen = now
        n_ext += 1
    for w in (payload.get("domains") or [])[:MAX_ITEMS_PER_REPORT]:
        host = _norm_host(str(w.get("host") or ""))
        if not host or "." not in host or _ignored(host):
            continue
        row = seen.get(("webapp", host))
        if row is None:
            row = BrowserItem(client_id=device.client_id, device_id=device.id,
                              kind="webapp", identifier=host, first_seen=now, hits=0)
            db.add(row)
            seen[("webapp", host)] = row
        try:
            row.hits = max(int(row.hits or 0), int(w.get("hits") or 0))
        except (TypeError, ValueError):
            pass
        nm, _cat = classify(host)
        row.name = nm
        row.last_seen = now
        n_web += 1
    db.commit()
    return {"extensions": n_ext, "webapps": n_web}


def _policy(db: Session, client_id: int) -> BrowserPolicy:
    pol = (db.query(BrowserPolicy)
           .filter(BrowserPolicy.client_id == client_id).first())
    if pol is None:
        pol = BrowserPolicy(client_id=client_id, decisions={}, protect=False)
        db.add(pol)
        db.flush()
    return pol


def decide(db: Session, client_id: int, identifier: str, action: str) -> dict:
    """approve | block | clear one identifier for a client. Commits."""
    if action not in ("approve", "block", "clear"):
        raise ValueError("action must be approve|block|clear")
    pol = _policy(db, client_id)
    decisions = dict(pol.decisions or {})
    ident = _norm_host(identifier) if "." in identifier else identifier.strip()
    if action == "clear":
        decisions.pop(ident, None)
    else:
        decisions[ident] = "approved" if action == "approve" else "blocked"
    pol.decisions = decisions
    pol.updated_at = _utcnow()
    db.commit()
    return {"identifier": ident, "status": decisions.get(ident, "unreviewed")}


def set_protect(db: Session, client_id: int, protect: bool) -> dict:
    pol = _policy(db, client_id)
    pol.protect = bool(protect)
    pol.updated_at = _utcnow()
    db.commit()
    return {"client_id": client_id, "protect": pol.protect}


def inventory(db: Session, client_id: int) -> dict:
    """Per-client rollup for the UI/copilot."""
    pol = (db.query(BrowserPolicy)
           .filter(BrowserPolicy.client_id == client_id).first())
    decisions = dict(pol.decisions or {}) if pol else {}
    rows = db.query(BrowserItem).filter(BrowserItem.client_id == client_id).all()
    web: dict[str, dict] = {}
    ext: dict[str, dict] = {}
    for r in rows:
        if r.kind == "webapp":
            nm, cat = classify(r.identifier)
            g = web.setdefault(r.identifier, {"identifier": r.identifier, "name": nm,
                                              "category": cat, "devices": 0, "hits": 0})
            g["devices"] += 1
            g["hits"] += int(r.hits or 0)
            g["status"] = decisions.get(r.identifier, "unreviewed")
        else:
            g = ext.setdefault(r.identifier, {"identifier": r.identifier,
                                              "name": r.name or r.identifier,
                                              "browser": r.browser,
                                              "permissions": r.permissions or "",
                                              "devices": 0})
            g["devices"] += 1
            g["status"] = decisions.get(r.identifier, "unreviewed")
    webapps = sorted(web.values(), key=lambda x: (-x["devices"], -x["hits"]))
    extensions = sorted(ext.values(), key=lambda x: -x["devices"])
    return {"client_id": client_id, "protect": bool(pol.protect) if pol else False,
            "webapps": webapps, "extensions": extensions,
            "counts": {"webapps": len(webapps), "extensions": len(extensions),
                       "blocked": sum(1 for v in decisions.values() if v == "blocked"),
                       "unreviewed": sum(1 for x in list(web.values()) + list(ext.values())
                                         if x.get("status", "unreviewed") == "unreviewed")}}


def agent_policy(db: Session, device: Device) -> dict:
    """What THIS device must enforce right now."""
    pol = (db.query(BrowserPolicy)
           .filter(BrowserPolicy.client_id == device.client_id).first())
    if pol is None:
        return {"blocked_domains": [], "blocked_extensions": [], "protect": False}
    decisions = dict(pol.decisions or {})
    blocked = [k for k, v in decisions.items() if v == "blocked"]
    return {"blocked_domains": sorted(b for b in blocked if "." in b),
            "blocked_extensions": sorted(b for b in blocked if "." not in b),
            "protect": bool(pol.protect)}
