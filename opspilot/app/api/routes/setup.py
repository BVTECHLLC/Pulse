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
