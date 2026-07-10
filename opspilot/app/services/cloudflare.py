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
SITE_DOMAINS = {"bvtech": "bvtech.org", "jp": "jordanpolasek.com"}


def _http(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    data = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(req, data=data, timeout=20) as r:
        body = r.read().decode()
    return json.loads(body) if body else {}


_HTTP = _http   # test seam


def _cfg(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    return dict((conn.config if conn else None) or {})


def get_token(db: Session) -> str | None:
    return secure_config.get_secret(_cfg(db), "api_token") or None


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
        out = _HTTP("GET", f"{API}/zones?name={domain}", token)
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
                    {"files": [u for u in urls if u][:30]})
        if out.get("success"):
            return {"ok": True, "detail": f"purged {len(urls)} URL(s)"}
        return {"ok": False, "detail": str(out.get("errors"))[:160]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": str(e)[:160]}


def verify(db: Session) -> dict:
    """Live check: token valid + which of our zones it can see."""
    token = get_token(db)
    if not token:
        return {"ok": False, "detail": "No Cloudflare API token stored yet."}
    try:
        v = _HTTP("GET", f"{API}/user/tokens/verify", token)
        if not v.get("success"):
            return {"ok": False, "detail": "Token rejected by Cloudflare - generate a new one."}
    except Exception as e:  # noqa: BLE001
        m = str(e)
        return {"ok": False, "detail": "Token rejected (401/403) - wrong or expired token."
                if ("401" in m or "403" in m) else f"Cloudflare check failed: {m[:120]}"}
    seen = []
    for site, domain in SITE_DOMAINS.items():
        if _zone_id(db, site):
            seen.append(domain)
    if not seen:
        return {"ok": False, "detail": "Token is valid but can't see bvtech.org or "
                                       "jordanpolasek.com - scope it to those zones (Zone:Read + Cache Purge)."}
    return {"ok": True, "detail": f"Verified - can purge cache for: {', '.join(seen)}."}
