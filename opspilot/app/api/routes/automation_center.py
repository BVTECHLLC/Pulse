"""v2.3 Growth Autopilot — mission control.

Aggregates the marketing/growth automations (content, outreach, scrapers, AI,
compliance) into ONE cockpit payload plus a prioritized go-live checklist. The
engines themselves already run server-side on the box via the heartbeat tick;
this is a read-only status + "what do I flip to go fully live" view. OWNER only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import require_roles
from ...models import CrmContact, Role, User
from ...services import ai, content_autopilot, outbound, secure_config, suppression

_MAILBOX_PROVIDER = "m365_mailbox"   # routes/mailbox.py PROVIDER — the M365 inbox reply-stop scans

router = APIRouter(prefix="/api/automation", tags=["automation"])


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — a cockpit must never 500 on one sub-status
        return default


@router.get("/center")
def center(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.OWNER))):
    content = _safe(lambda: content_autopilot.status(db), {"enabled": False, "channels": []})
    chans = content.get("channels", [])

    def ch(k):
        return next((c for c in chans if c.get("key") == k), {})

    sites_connected = bool(ch("bvtech").get("connected") and ch("jp").get("connected"))
    li_connected = bool(ch("linkedin").get("connected"))
    gbp_connected = bool(ch("gbp").get("connected"))
    txp = ch("txplants")

    ocfg = _safe(lambda: outbound.get_config(db), {}) or {}
    env_mode = _safe(outbound._env_mode, "off")
    enabled = bool(ocfg.get("enabled"))
    live = (env_mode == "live") or enabled
    sender_set = bool(ocfg.get("sender"))
    addr_set = bool(ocfg.get("physical_address"))
    leads = _safe(lambda: db.query(CrmContact).filter(CrmContact.email.isnot(None)).count(), 0)
    dnc = _safe(lambda: db.query(CrmContact).filter(CrmContact.do_not_contact.is_(True)).count(), 0)
    supp = _safe(lambda: suppression.count(db), 0)
    # The content engine runs on the FREE Groq LLM (vault "groq") — which is a
    # different check from ai.enabled() (that one is the PAID Claude key). Either
    # one means posts are AI-written.
    ai_free = _safe(ai.free_llm_enabled, False)
    ai_paid = _safe(ai.enabled, False)
    ai_on = bool(ai_free or ai_paid)

    mbox = _safe(lambda: secure_config.get_platform(db, _MAILBOX_PROVIDER) is not None, False)

    def item(key, label, done, how, prio):
        return {"key": key, "label": label, "done": bool(done), "how": how, "priority": prio}

    checklist = [
        item("ai", "AI content brain connected (Groq free LLM)", ai_on,
             "Settings → add your free Groq key to the vault so every post is AI-written and costs you $0 in Claude.", 1),
        item("content_on", "Daily content autopilot ON", content.get("enabled"),
             "Content Studio → Content Autopilot → turn it ON (it posts daily on a safe stagger).", 1),
        item("sites", "Website publishing connected (GitLab)", sites_connected,
             "Content Autopilot → connect your GitLab token — ONE token covers bvtech.org, /news (CVE), jordanpolasek.com and the homepage marquee.", 2),
        item("linkedin", "LinkedIn connected — daily post", li_connected,
             "Settings → One-click Connect → LinkedIn (Connect →).", 2),
        item("ob_ident", "Cold email: sender + mailing address set", sender_set and addr_set,
             "Outreach → set your From-address and a physical mailing address (required by CAN-SPAM).", 2),
        item("ob_live", "Cold email program LIVE", live,
             "Outreach → flip the program to Live. It ramps slowly (20/day, +15/day) so you never get flagged.", 2),
        item("reply_stop", "Reply-stop armed (mailbox connected)", mbox,
             "Settings → connect your Microsoft 365 mailbox so a reply or 'STOP' auto-removes them from outreach within ~15 min.", 2),
        item("gbp", "Google Business connected — weekly post", gbp_connected,
             "Settings → Google Business Profile: connect and pick your location.", 3),
        item("txplants", "tx-plants.com daily post on", bool(txp.get("connected") and txp.get("enabled")),
             "Content Autopilot → connect the tx-plants.com repo + enable its channel.", 4),
    ]
    ready = sum(1 for c in checklist if c["done"])

    return {
        "ready": ready, "total": len(checklist),
        "live": live, "ai_connected": ai_on,
        "ai": {"connected": ai_on, "free_groq": ai_free, "paid_claude": ai_paid,
               "provider": "Groq (free)" if ai_free else ("Claude" if ai_paid else "none")},
        "content": content,
        "outbound": {
            "mode": "live" if live else ("test" if env_mode == "test" else "off"),
            "sender_set": sender_set, "address_set": addr_set,
            "ramp_target": ocfg.get("target"), "started_on": ocfg.get("started_on"),
            "leads_with_email": leads, "do_not_contact": dnc, "suppressed": supp,
        },
        "prospecting": {
            "auto": True,
            "note": "Auto-scrapes fresh Texas MSP leads (free OpenStreetMap, or Google Places if a key is set) whenever the lead pool runs low — while outreach is armed.",
        },
        "compliance": {
            "unsubscribe_page": "/unsubscribe", "one_click": True,
            "suppressed": supp, "reply_stop": mbox,
        },
        "checklist": sorted(checklist, key=lambda c: (c["done"], c["priority"])),
    }
