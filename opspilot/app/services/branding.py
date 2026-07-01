"""v0.75 White-label branding.

Everything a reseller MSP needs to make the portal *theirs*: company + product
name, logo, accent color, support email, tagline, footer. Stored on the
``branding`` platform vault row (all public-safe values — no secrets), with
sensible defaults from settings so an un-branded install still looks finished.

`public_branding(db)` is served unauthenticated (the login page needs it), so it
only ever returns display values.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..core.config import get_settings
from . import secure_config

PROVIDER = "branding"
_FIELDS = ("company", "product", "logo_url", "accent", "support_email",
           "tagline", "footer_note")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _defaults() -> dict:
    s = get_settings()
    # APP_NAME is like "BVTech OpsPilot" — split into company + product for defaults.
    parts = (s.APP_NAME or "OpsPilot").split(" ", 1)
    company = parts[0] if len(parts) > 1 else "BVTech"
    product = parts[1] if len(parts) > 1 else s.APP_NAME
    return {"company": company, "product": product, "logo_url": "",
            "accent": "#6c5ce7", "support_email": s.SUPPORT_EMAIL,
            "tagline": "Managed IT & Security", "footer_note": ""}


def public_branding(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    out = _defaults()
    for k in _FIELDS:
        v = cfg.get(k)
        if v not in (None, ""):
            out[k] = v
    # Guard the color so a bad value can't break the CSS.
    if not _HEX.match(str(out.get("accent", ""))):
        out["accent"] = "#6c5ce7"
    out["app_name"] = f"{out['company']} {out['product']}".strip()
    return out


def save_branding(db: Session, fields: dict) -> dict:
    payload = {k: str(v)[:300] for k, v in (fields or {}).items()
               if k in _FIELDS and v is not None}
    if "accent" in payload and not _HEX.match(payload["accent"]):
        payload.pop("accent")   # ignore invalid colors instead of persisting them
    secure_config.upsert_platform(db, PROVIDER, "Branding", "White-label", payload)
    return public_branding(db)
