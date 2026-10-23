"""bvtech.org health audit (v1.97) — read-only, one call, plain-text report.

Answers "what actually happened on the site this month" from primary evidence
instead of the autopilot's own OK flags: the repo's commit history (what was
published, per Central-time day), Cloudflare's Workers build result per commit,
the autopilot's per-channel last success / last error, failure notifications,
the visible order and dates of the listing pages, and the KEV marquee.

    docker exec opspilot-api-1 python -c "from app.core.db import SessionLocal; \
from app.services import site_audit; print(site_audit.bvtech_report(SessionLocal()))"
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

CT = ZoneInfo("America/Chicago")


def _kind(title: str) -> str:
    t = title.lower()
    if "kev ticker" in t:
        return "TICKER"
    if t.startswith("blog: bvtech news"):
        return "NEWS"
    if any(k in t for k in ("sync listings", "duplicate", "re-date", "re-stamp", "re-order",
                            "repair", "nudge", "trim", "dedupe", "sweep")):
        return "MAINT"
    if t.startswith("blog:"):
        return "SMB"
    return "OTHER"


def _commits(cfg: dict, since: datetime) -> list[dict]:
    from . import jp_site as J
    out, page = [], 1
    while page <= 5:
        batch = J._HTTP("GET", f"{J._proj_url(cfg)}/repository/commits?ref_name={cfg['branch']}"
                        f"&since={quote(since.isoformat())}&per_page=100&page={page}", cfg["token"])
        if not batch:
            break
        out += batch
        if len(batch) < 100:
            break
        page += 1
    return out


def _cards(h: str, pat: str, n: int = 10) -> list[tuple[str, str, str]]:
    from . import jp_site as J
    rows = []
    for a, b in J._all_card_spans(h, pat)[:n]:
        card = h[a:b]
        lm = re.search(pat, card)
        slug = J._slug_of(lm.group(0)[6:-1]) if lm else "?"
        d = J._date_from_text(re.sub(r"<[^>]+>", " ", card))
        t = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", card, re.S)
        title = re.sub(r"<[^>]+>", "", t.group(1)).strip()[:52] if t else "?"
        rows.append((d.isoformat() if d else "no-date",
                     "NEWS" if slug.startswith("bvtech-news") else "SMB", title))
    return rows


def bvtech_report(db: Session, days: int = 31) -> str:
    from . import content_autopilot as CA
    from . import jp_site as J
    from . import secure_config
    from ..models import Notification

    L: list[str] = []
    now = datetime.now(timezone.utc)
    today = now.astimezone(CT).date()
    start = today - timedelta(days=days - 1)
    cfg = J.get_config(db, "bvtech")
    if not cfg["configured"]:
        return "bvtech.org not connected (GitLab token needed)"

    ap = CA.get_config(db)
    raw_ap = dict(getattr(secure_config.get_platform(db, CA.PROVIDER), "config", None) or {})
    L.append(f"== AUTOPILOT  enabled={ap['enabled']} hour_utc={ap['hour_utc']}")
    for ch in CA.CHANNELS:
        err = (raw_ap.get("last_error") or {}).get(ch)
        L.append(f"   {ch:9} on={ap['channels'].get(ch, True)!s:5} last_ok={ap['last'].get(ch)}"
                 + (f"  LAST ERROR {err.get('date')}: {err.get('error', '')[:110]}" if err else ""))

    for ch, e in (raw_ap.get("llm_error") or {}).items():
        L.append(f"   AI WRITING FAILED {ch} {e.get('date')}: {e.get('error', '')[:120]}")

    since = datetime.combine(start, datetime.min.time(), CT).astimezone(timezone.utc)
    notes = (db.query(Notification).filter(Notification.created_at >= since)
             .order_by(Notification.created_at.desc()).limit(400).all())
    bad = [n for n in notes if n.severity in ("warning", "error", "critical")
           and re.search(r"bvtech|news|kev|marquee|autopilot|blog|listing", n.message, re.I)]
    L.append(f"\n== FAILURE NOTICES since {start} ({len(bad)})")
    for n in bad[:15]:
        L.append(f"   {n.created_at.astimezone(CT):%m-%d %H:%M}  {n.message[:130]}")

    commits = _commits(cfg, since)
    per: dict[date, dict[str, list[str]]] = {}
    for c in commits:
        d = datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")).astimezone(CT).date()
        per.setdefault(d, {}).setdefault(_kind(c["title"]), []).append(c["title"])
    L.append(f"\n== PUBLISHED PER DAY (CT) from repo history — {len(commits)} commits")
    L.append("   date        SMB NEWS TICKER  MAINT  first SMB title")
    missing = {"SMB": [], "NEWS": [], "TICKER": []}
    d = start
    while d <= today:
        k = per.get(d, {})
        for key in missing:
            if not k.get(key):
                missing[key].append(d.strftime("%m-%d"))
        smb = (k.get("SMB") or [""])[0].replace("blog: ", "")[:44]
        L.append(f"   {d} {len(k.get('SMB', [])):3} {len(k.get('NEWS', [])):4} "
                 f"{len(k.get('TICKER', [])):6} {len(k.get('MAINT', [])):6}  {smb}")
        d += timedelta(days=1)
    for key, ds in missing.items():
        L.append(f"   missing {key:6}: {len(ds)} day(s) {' '.join(ds) if ds else '-'}")
    recent = [t for dd, k in per.items() if dd > today - timedelta(days=14)
              for t in k.get("SMB", [])]
    uniq = len({t.replace(" (via Pulse)", "") for t in recent})
    L.append(f"   SMB titles last 14 days: {len(recent)} posts, {uniq} distinct"
             + ("  <- RECYCLING backup posts (AI writing is failing)"
                if recent and uniq <= len(recent) // 2 else ""))

    L.append("\n== CLOUDFLARE WORKERS BUILDS (last 25 commits)")
    fails = 0
    for c in commits[:25]:
        st = J._HTTP("GET", f"{J._proj_url(cfg)}/repository/commits/{c['id']}/statuses",
                     cfg["token"])
        s = st[0]["status"] if st else "none"
        if s not in ("success", "none"):
            fails += 1
            L.append(f"   {s.upper():8} {c['created_at'][:16]} {c['title'][:70]}")
    L.append(f"   non-success builds: {fails}")

    pat = J._link_pat_for("blog-file", "blog")
    for lp in ("index.html", "blog/index.html", "news/index.html"):
        h = J._fetch_file(cfg, lp)
        if h is None:
            L.append(f"\n== {lp}: MISSING")
            continue
        rows = _cards(h, pat)
        dated = [r[0] for r in rows if r[0] != "no-date"]
        ordered = dated == sorted(dated, reverse=True)
        slugs = re.findall(r'href="[^"]*/blog/([a-z0-9\-]+)\.html"', h)
        dupes = len(slugs) - len(set(slugs))
        L.append(f"\n== {lp}: top cards (newest-first? {ordered}; repeated links {dupes})")
        for r in rows:
            L.append(f"   {r[0]:10} {r[1]:4} {r[2]}")

    home = J._fetch_file(cfg, "index.html") or ""
    items = re.findall(r'<span class="tk-item[^"]*">(.*?)</span>', home, re.S)
    raw_bv = dict(getattr(secure_config.get_platform(db, J.SITES["bvtech"]["provider"]),
                         "config", None) or {})
    L.append(f"\n== KEV MARQUEE  items={len(items)} last_refresh={raw_bv.get('last_kev_ticker')}")
    for it in items[:3]:
        L.append("   " + re.sub(r"<[^>]+>", "", it).strip()[:110])
    return "\n".join(L)
