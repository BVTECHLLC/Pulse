"""v2.1 White-label branding.

Everything a reseller MSP needs to make the portal *theirs*: company + product
name, logo, primary + secondary accent colors, support email/phone, website,
company address (for CAN-SPAM email footers), the outbound "from" name, tagline,
footer, and a "Powered by" toggle (a reseller turns it off to run the platform
fully as their own). Stored on the ``branding`` platform vault row (all
public-safe values — no secrets), with sensible defaults from settings so an
un-branded install still looks finished.

`public_branding(db)` is served unauthenticated (the login + signing pages need
it), so it only ever returns display values. No migration: the vault row is JSON,
so new fields are purely additive.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..core.config import get_settings
from . import secure_config

PROVIDER = "branding"
# String display fields persisted verbatim (truncated). powered_by is "on"/"off".
_FIELDS = ("company", "product", "logo_url", "accent", "accent2",
           "support_email", "support_phone", "website_url", "company_address",
           "email_from_name", "tagline", "footer_note", "powered_by")
_COLOR_FIELDS = ("accent", "accent2")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_DEFAULT_ACCENT = "#6c5ce7"
_DEFAULT_ACCENT2 = "#4834d4"


def _defaults() -> dict:
    s = get_settings()
    # APP_NAME is like "BVTech OpsPilot" — split into company + product for defaults.
    parts = (s.APP_NAME or "OpsPilot").split(" ", 1)
    company = parts[0] if len(parts) > 1 else "BVTech"
    product = parts[1] if len(parts) > 1 else s.APP_NAME
    return {"company": company, "product": product, "logo_url": "",
            "accent": _DEFAULT_ACCENT, "accent2": _DEFAULT_ACCENT2,
            "support_email": s.SUPPORT_EMAIL, "support_phone": "",
            "website_url": "", "company_address": "", "email_from_name": "",
            "tagline": "Managed IT & Security", "footer_note": "",
            "powered_by": "on"}


def _truthy(v) -> bool:
    return str(v).strip().lower() not in ("off", "false", "0", "no", "")


def public_branding(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    out = _defaults()
    for k in _FIELDS:
        v = cfg.get(k)
        if v not in (None, ""):
            out[k] = v
    # Guard colors so a bad value can't break the CSS.
    if not _HEX.match(str(out.get("accent", ""))):
        out["accent"] = _DEFAULT_ACCENT
    if not _HEX.match(str(out.get("accent2", ""))):
        out["accent2"] = out["accent"]
    out["app_name"] = f"{out['company']} {out['product']}".strip()
    # Convenience: a real boolean for templates, plus the stored "on"/"off".
    out["powered_by"] = _truthy(out.get("powered_by", "on"))
    # The "from" name used on outbound email falls back to the brand name.
    if not out.get("email_from_name"):
        out["email_from_name"] = out["app_name"]
    return out


def save_branding(db: Session, fields: dict) -> dict:
    payload = {}
    for k, v in (fields or {}).items():
        if k not in _FIELDS or v is None:
            continue
        if k == "powered_by":
            payload[k] = "on" if _truthy(v) else "off"
        else:
            payload[k] = str(v)[:300]
    for cf in _COLOR_FIELDS:
        if cf in payload and not _HEX.match(payload[cf]):
            payload.pop(cf)   # ignore invalid colors instead of persisting them
    secure_config.upsert_platform(db, PROVIDER, "Branding", "White-label", payload)
    return public_branding(db)
