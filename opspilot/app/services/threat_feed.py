"""v1.147 Pulse-native threat feed — the REAL data behind bvtech.org's live
Threat Map, served from telemetry WE own instead of a stray Cloudflare Worker
token that silently dies.

Sources, in order of richness:
  1. Pulse's own 404 bot-probe log (``bvtech_404`` vault) — every scanner that
     hits a bad URL on the live site (relayed by the site Worker). Real, always-on.
  2. A honeypot / proof-of-work rejection counter (``threat_feed`` vault),
     incremented by captcha.verify whenever a bot trips the human-check.
  3. A failed-login counter, incremented by the auth layer on bad credentials.
  4. OPTIONAL Cloudflare GraphQL analytics (firewall events) when a
     ``cloudflare_analytics`` token is stored — the true edge numbers.

Everything is best-effort and self-healing: any source that errors is skipped,
the endpoint never 500s, and the map shows real zeros rather than a broken feed.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "threat_feed"
_CACHE: dict = {"at": 0.0, "data": None}
_CACHE_TTL = 60.0   # seconds — the map polls often; one aggregate per minute

# Scanner / exploit probe paths => "malware probes"; everything else a bot hits
# that 404s is ordinary "bot traffic". Substring match, lowercased.
_MALWARE_MARKERS = (
    "wp-admin", "wp-login", "xmlrpc", "/.env", "/.git", "phpmyadmin", "/.aws",
    "/vendor/", "eval-stdin", "/shell", "/cgi-bin", "/.ssh", "/config.", "/backup",
    "/solr", "/actuator", "/boaform", "/hnap1", "/.vscode", "wp-content/plugins",
    "/administrator", "/phpunit", "/thinkphp", "/jenkins", "/manager/html",
)


def _today_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def record(db: Session, kind: str, n: int = 1) -> None:
    """Increment a daily counter (kind in: honeypot, failed_login, bot, malware).
    Best-effort; a telemetry write must never break the request that calls it."""
    try:
        conn = secure_config.get_platform(db, PROVIDER)
        cfg = dict((conn.config if conn else None) or {})
        counters = dict(cfg.get("counters") or {})
        day = _today_key()
        bucket = dict(counters.get(day) or {})
        bucket[kind] = int(bucket.get(kind, 0)) + int(n)
        counters[day] = bucket
        # keep only the last 3 days
        for k in list(counters.keys()):
            if k < _today_key(datetime.now(timezone.utc) - timedelta(days=2)):
                counters.pop(k, None)
        secure_config.upsert_platform(db, PROVIDER, "Threat Feed", "Telemetry",
                                      {"counters": counters})
    except Exception:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _counter_sum(db: Session, kind: str, days: int = 1) -> int:
    conn = secure_config.get_platform(db, PROVIDER)
    cfg = (conn.config if conn else None) or {}
    counters = cfg.get("counters") or {}
    total = 0
    for i in range(days):
        day = _today_key(datetime.now(timezone.utc) - timedelta(days=i))
        total += int((counters.get(day) or {}).get(kind, 0))
    return total


def _probe_counts(db: Session) -> tuple[int, int, list[dict]]:
    """(bot_traffic, malware_probes, recent_feed) from the 404 bot-probe log."""
    conn = secure_config.get_platform(db, "bvtech_404")
    hits = ((conn.config if conn else None) or {}).get("hits") or {}
    bot = mal = 0
    feed = []
    for path, row in hits.items():
        c = int((row or {}).get("count", 0))
        low = str(path).lower()
        is_mal = any(m in low for m in _MALWARE_MARKERS)
        if is_mal:
            mal += c
        else:
            bot += c
        feed.append({"path": path[:80], "count": c,
                     "type": "malware probe" if is_mal else "bot",
                     "last": (row or {}).get("last")})
    feed.sort(key=lambda r: r.get("last") or "", reverse=True)
    return bot, mal, feed[:12]


def _cloudflare(db: Session) -> dict | None:
    """Real edge numbers from Cloudflare's GraphQL analytics, when a
    ``cloudflare_analytics`` token (Account/Zone Analytics:Read) is stored.
    Returns {failed_logins, bot, malware} or None. Fully self-healing."""
    import json
    import urllib.request
    conn = secure_config.get_platform(db, "cloudflare_analytics")
    cfg = (conn.config if conn else None) or {}
    token = secure_config.get_secret(cfg, "api_token") or cfg.get("api_token")
    zone = cfg.get("zone_id")
    if not (token and zone):
        return None
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = {
        "query": """query($zone:String!,$since:Time!){viewer{zones(filter:{zoneTag:$zone}){
          firewallEventsAdaptiveGroups(limit:1,filter:{datetime_geq:$since}){count}
        }}}""",
        "variables": {"zone": zone, "since": since},
    }
    try:
        req = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/graphql",
            data=json.dumps(query).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            body = json.loads(r.read().decode())
        groups = (body.get("data", {}).get("viewer", {}).get("zones", [{}]) or [{}])[0]
        events = sum(int(g.get("count", 0))
                     for g in (groups.get("firewallEventsAdaptiveGroups") or []))
        # All blocked edge events are hostile traffic; we surface the total and let
        # the per-category breakdown come from Pulse's own classification above.
        return {"blocked_edge_24h": events}
    except Exception:  # noqa: BLE001 — token dead / schema change / offline: skip
        return None


def snapshot(db: Session, *, force: bool = False) -> dict:
    """The live Threat Map payload. Cached ~60s. Never raises."""
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["at"]) < _CACHE_TTL:
        return _CACHE["data"]
    try:
        bot, mal, feed = _probe_counts(db)
    except Exception:  # noqa: BLE001
        bot, mal, feed = 0, 0, []
    try:
        honeypot = _counter_sum(db, "honeypot", days=1)
        failed = _counter_sum(db, "failed_login", days=1)
    except Exception:  # noqa: BLE001
        honeypot = failed = 0
    cf = None
    try:
        cf = _cloudflare(db)
    except Exception:  # noqa: BLE001
        cf = None
    edge_total = (cf or {}).get("blocked_edge_24h")
    data = {
        "failed_logins_24h": failed,
        "honeypot_hits": honeypot,
        "bot_traffic": bot,
        "malware_probes": mal,
        "edge_blocked_24h": edge_total,               # None unless CF token set
        "total_24h": (failed + honeypot + bot + mal) + (edge_total or 0),
        "feed": feed,
        "cloudflare_connected": cf is not None,
        "source": "BVTech honeypots + edge defenses (Pulse telemetry"
                  + (" + Cloudflare analytics)" if cf is not None else ")"),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    _CACHE["data"], _CACHE["at"] = data, now
    return data
