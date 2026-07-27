"""v1.29 Cloudflare — cache purge so published content is visible IMMEDIATELY.

Both sites deploy via Cloudflare, and Cloudflare's edge cache can keep serving
the OLD listing/post HTML for hours after a successful deploy. That reads as
"Pulse said it posted but the site didn't change." One API token fixes it:

  * paste a Cloudflare API token (Connection Center -> Cloudflare) with
    Zone.Zone:Read + Zone.Cache Purge:Purge on bvtech.org + jordanpolasek.com
  * zone IDs are DISCOVERED automatically by domain name and cached
  * every publish purges exactly the URLs that changed (post + listings)

Best-effort by design: a missing/broken token never blocks a publish — the
commit still lands and Cloudflare's cache simply expires on its own schedule.
"""
from __future__ import annotations

import json
import urllib.request

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "cloudflare"
API = "https://api.cloudflare.com/client/v4"

# site key (jp_site.SITES) -> apex domain the zone is looked up by
SITE_DOMAINS = {"bvtech": "bvtech.org", "jp": "jordanpolasek.com",
                "autumn": "autumnpolasek.com", "txplants": "tx-plants.com"}


def _http(method: str, url: str, token: str, payload: dict | None = None,
          email: str | None = None) -> dict:
    """Cloudflare speaks TWO auth dialects and rejects the wrong one with 401:
      * API Token  -> Authorization: Bearer <token>
      * Global API Key (the legacy full-access key) -> X-Auth-Key + X-Auth-Email
    When `email` is supplied we send the Global-Key headers; otherwise Bearer."""
    if email:
        headers = {"X-Auth-Key": token, "X-Auth-Email": email,
                   "Content-Type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {token}",
                   "Content-Type": "application/json"}
    req = urllib.request.Request(url, method=method, headers=headers)
    data = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(req, data=data, timeout=20) as r:
        body = r.read().decode()
    return json.loads(body) if body else {}


_HTTP = _http   # test seam


def _cfg(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    return dict((conn.config if conn else None) or {})


def get_token(db: Session) -> str | None:
    """Token comes from the Connection Center (encrypted, preferred) OR, when
    that isn't set, from the box environment — CLOUDFLARE_PURGE_TOKEN so the
    Linode host can auto-purge every publish with zero portal config."""
    tok = secure_config.get_secret(_cfg(db), "api_token")
    if tok:
        return tok
    import os
    return (os.environ.get("CLOUDFLARE_PURGE_TOKEN")
            or os.environ.get("CLOUDFLARE_API_TOKEN") or None)


def get_auth_email(db: Session) -> str | None:
    """Set only when the stored credential is a Global API Key."""
    cfg = _cfg(db)
    return (cfg.get("auth_email") or "").strip() or None


def looks_like_global_key(token: str) -> bool:
    """Global API Keys are 37 lowercase-hex chars; API Tokens are longer,
    mixed-case, and often start with letters/underscores."""
    import re as _re
    return bool(_re.fullmatch(r"[0-9a-f]{37}", token or ""))


def configured(db: Session) -> bool:
    return bool(get_token(db))


def _zone_id(db: Session, site: str) -> str | None:
    """Zone id for a site — cached in config after first lookup by domain."""
    domain = SITE_DOMAINS.get(site)
    token = get_token(db)
    if not (domain and token):
        return None
    cfg = _cfg(db)
    zones = dict(cfg.get("zones") or {})
    if zones.get(domain):
        return zones[domain]
    try:
        out = _HTTP("GET", f"{API}/zones?name={domain}", token, email=get_auth_email(db))
        results = out.get("result") or []
        zid = results[0]["id"] if results else None
    except Exception:  # noqa: BLE001
        return None
    if zid:
        zones[domain] = zid
        # Partial update: only touch the zones cache — never re-submit the stored
        # (already-encrypted) token, which would double-encrypt and corrupt it.
        secure_config.upsert_platform(db, PROVIDER, "Cloudflare", "Publishing",
                                      {"zones": zones})
    return zid


def purge_urls(db: Session, site: str, urls: list[str]) -> dict:
    """Purge specific URLs from Cloudflare's cache. Never raises; returns
    {ok, detail} so callers can surface (not fail on) purge problems."""
    token = get_token(db)
    if not token:
        return {"ok": False, "detail": "Cloudflare not connected (cache clears on its own TTL)"}
    zid = _zone_id(db, site)
    if not zid:
        return {"ok": False, "detail": f"no Cloudflare zone found for {SITE_DOMAINS.get(site)} "
                                       "(token needs Zone:Read on that domain)"}
    try:
        out = _HTTP("POST", f"{API}/zones/{zid}/purge_cache", token,
                    {"files": [u for u in urls if u][:30]}, email=get_auth_email(db))
        if out.get("success"):
            return {"ok": True, "detail": f"purged {len(urls)} URL(s)"}
        return {"ok": False, "detail": str(out.get("errors"))[:160]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)[:160]}


def verify(db: Session) -> dict:
    """Live check: credential valid + which of our zones it can reach. Handles
    BOTH credential types and tells the operator exactly what's missing."""
    token = get_token(db)
    if not token:
        return {"ok": False, "detail": "No Cloudflare API token stored yet."}
    email = get_auth_email(db)

    if email or looks_like_global_key(token):
        # Global API Key path (X-Auth-Key + X-Auth-Email).
        if not email:
            return {"ok": False,
                    "detail": "This looks like your GLOBAL API Key - it also needs your "
                              "Cloudflare account email. Add it in the Cloudflare connector "
                              "(auth email field) and save again."}
        try:
            v = _HTTP("GET", f"{API}/user", token, email=email)
            if not v.get("success"):
                return {"ok": False, "detail": "Global API Key rejected - check the key and email."}
        except Exception as e:  # noqa: BLE001
            m = str(e)
            return {"ok": False,
                    "detail": "Global API Key rejected (401) - key or email is wrong."
                    if "401" in m else f"Cloudflare check failed: {m[:120]}"}
    else:
        # Scoped API Token path (Bearer).
        try:
            v = _HTTP("GET", f"{API}/user/tokens/verify", token)
            if not v.get("success"):
                return {"ok": False, "detail": "Token rejected by Cloudflare - generate a new one."}
        except Exception as e:  # noqa: BLE001
            m = str(e)
            if "401" in m or "403" in m:
                return {"ok": False,
                        "detail": "Rejected (401). If you pasted the GLOBAL API Key (37-char hex "
                                  "from 'API Keys'), also enter your Cloudflare account email in "
                                  "the connector - or create a scoped API Token instead."}
            return {"ok": False, "detail": f"Cloudflare check failed: {m[:120]}"}

    seen = []
    for site, domain in SITE_DOMAINS.items():
        if _zone_id(db, site):
            seen.append(domain)
    if not seen:
        return {"ok": False, "detail": "Credential is valid but can't see bvtech.org or "
                                       "jordanpolasek.com - scope it to those zones (Zone:Read + Cache Purge)."}
    mode = "Global API Key" if email else "API Token"
    return {"ok": True, "detail": f"Verified ({mode}) - can purge cache for: {', '.join(seen)}."}
