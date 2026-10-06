"""v1.89 SEO / AEO / GEO daily automation — make every site rank in search
engines AND get cited by AI answer engines (ChatGPT, Perplexity, Google AI
Overviews, Claude), hands-free, at $0 LLM cost.

Runs once per day per CONNECTED site (gated on jp_site config, so it no-ops
cleanly while a GitLab token is missing). Every step is best-effort and wrapped
so it can NEVER break the heartbeat. Three pillars:

  * SEO  — IndexNow instant indexing: the moment a post ships, Bing / Yandex /
    Seznam (and, through Bing, Copilot + ChatGPT search) are pinged to crawl the
    new URL within minutes instead of days. A one-time key file is auto-placed
    at the site root.
  * AEO  — robots.txt is kept open to the answer-engine crawlers (GPTBot,
    OAI-SearchBot, PerplexityBot, ClaudeBot, Google-Extended, …) and points at
    the sitemap, so the sites are eligible to be quoted in AI answers.
  * GEO  — an llms.txt file (the emerging standard AI crawlers read first) is
    maintained at each site root: a clean, link-rich summary of what the
    business does and its best pages, so generative engines describe it right.

Deterministic throughout — no paid tokens spent. The HTTP call is seam-injected
(``_HTTP_FN``) for offline tests.
"""
from __future__ import annotations

import json
import secrets as _secrets
from datetime import datetime, timezone
from urllib import error as _urlerror
from urllib import request as _urlrequest

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "seo_boost"
SITES = ("bvtech", "jp", "txplants")
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

# Answer-engine + search crawlers we explicitly WELCOME (GEO/AEO depends on
# being crawlable by these). robots.txt is kept open to every one of them.
AI_CRAWLERS = (
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Perplexity-User",
    "ClaudeBot", "Claude-Web", "anthropic-ai", "Google-Extended", "Googlebot",
    "Bingbot", "Applebot", "Applebot-Extended", "CCBot", "Amazonbot",
    "DuckAssistBot", "cohere-ai", "Meta-ExternalAgent", "YouBot",
)

# Per-site public identity used to write llms.txt (the GEO summary file).
SEO_PROFILE = {
    "bvtech": {
        "name": "BVTech",
        "tagline": "Managed IT services & cybersecurity for Texas small businesses",
        "summary": ("BVTech LLC is a Texas-based managed IT services provider "
                    "(MSP) serving small and mid-sized businesses in Sugar Land, "
                    "Houston, Austin, and San Antonio. Services include managed "
                    "IT support, cybersecurity, cloud, compliance, and a daily "
                    "CISA Known-Exploited-Vulnerabilities (KEV) threat feed."),
        "links": [("Blog", "/blog/"), ("Services", "/services"),
                  ("Why BVTech", "/why-us"), ("Contact", "/contact"),
                  ("Book a consultation", "/book")],
    },
    "jp": {
        "name": "Jordan Polasek",
        "tagline": "Texas IT & cybersecurity writing for small-business owners",
        "summary": ("Jordan Polasek writes practical IT, cybersecurity, and "
                    "cloud guidance for Texas small-business owners — plain-"
                    "English advice on protecting and modernizing a business."),
        "links": [("Articles", "/blog/"), ("About", "/about")],
    },
    "txplants": {
        "name": "TX-Plants",
        "tagline": "Texas native plants, homesteading & self-reliance",
        "summary": ("TX-Plants is a Texas gardening and homesteading resource: "
                    "native and edible plants, foraging, land stewardship, and "
                    "practical self-reliance for the Texas climate."),
        "links": [("Blog", "/blog/"), ("Plant guides", "/blog/")],
    },
}


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #
def get_config(db: Session) -> dict:
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    return {
        "enabled": bool(raw.get("enabled", True)),   # on by default; no-ops until a site connects
        "indexnow_ids": dict(raw.get("indexnow_ids") or {}),          # per-site IndexNow key
        "last": dict(raw.get("last") or {}),          # per-site last-run ISO date
        "_raw": raw,
    }


def save_config(db: Session, **fields) -> dict:
    cur = get_config(db)["_raw"]
    cur.update({k: v for k, v in fields.items() if v is not None})
    secure_config.upsert_platform(db, PROVIDER, "SEO/AEO/GEO Autopilot", "Growth", cur)
    return cur


def _indexnow_key(db: Session, site: str) -> str:
    cfg = get_config(db)
    keys = cfg["indexnow_ids"]
    if not keys.get(site):
        keys[site] = _secrets.token_hex(16)   # 32 hex chars — IndexNow spec
        save_config(db, indexnow_ids=keys)
    return keys[site]


# --------------------------------------------------------------------------- #
# HTTP (seam-injected for tests)
# --------------------------------------------------------------------------- #
def _http_post(url: str, payload: dict) -> int:
    data = json.dumps(payload).encode()
    req = _urlrequest.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "BVTech-OpsPilot-SEO"})
    try:
        with _urlrequest.urlopen(req, timeout=15) as r:
            return r.status
    except _urlerror.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001 — network blip: report as 0, retry tomorrow
        return 0


_HTTP_FN = _http_post   # test seam


# --------------------------------------------------------------------------- #
# File builders (deterministic — no LLM, no paid tokens)
# --------------------------------------------------------------------------- #
def _host(site_url: str) -> str:
    return site_url.split("://", 1)[-1].strip("/")


def build_llms_txt(site: str, now: datetime) -> str:
    """The GEO standard file AI crawlers read first (llms.txt)."""
    from . import jp_site
    prof = SEO_PROFILE[site]
    base = jp_site.SITES[site]["site"].rstrip("/")
    lines = [f"# {prof['name']}", "", f"> {prof['tagline']}", "",
             prof["summary"], "", "## Key pages", ""]
    for label, path in prof["links"]:
        url = path if path.startswith("http") else base + path
        lines.append(f"- [{label}]({url})")
    lines += ["", f"## Sitemap", "", f"- [Full sitemap]({base}/sitemap.xml)", "",
              f"_Last updated {now.date().isoformat()}._", ""]
    return "\n".join(lines)


def build_robots_txt(site: str, existing: str | None) -> str:
    """Keep robots.txt open to answer-engine crawlers + point at the sitemap.
    Never tightens an existing allow — only ensures AI bots aren't blocked and
    the Sitemap line is present."""
    from . import jp_site
    base = jp_site.SITES[site]["site"].rstrip("/")
    sitemap_line = f"Sitemap: {base}/sitemap.xml"
    if existing and "Sitemap:" in existing and all(
            b in existing for b in ("GPTBot", "PerplexityBot", "ClaudeBot")):
        return existing  # already welcoming — leave it as the owner has it
    blocks = ["# Managed by BVTech OpsPilot — welcomes search + AI answer engines"]
    for bot in AI_CRAWLERS:
        blocks.append(f"User-agent: {bot}\nAllow: /")
    blocks.append("User-agent: *\nAllow: /")
    blocks.append(sitemap_line)
    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------- #
# Daily pass
# --------------------------------------------------------------------------- #
def _ensure_file(ops: dict, path: str, content: str) -> str:
    """Create or update a root file only when its content actually changed."""
    cur = ops["fetch"](path)
    if cur is not None and cur.strip() == content.strip():
        return "unchanged"
    ops["commit"](path, content, f"seo: refresh {path} (via Pulse)", cur is not None)
    return "updated" if cur is not None else "created"


def run_for_site(db: Session, site: str, now: datetime,
                 new_urls: list[str] | None = None) -> dict:
    from . import jp_site
    cfg = jp_site.get_config(db, site)
    if not cfg.get("configured"):
        return {"ran": False, "reason": "not_connected"}
    meta = jp_site.SITES[site]
    base = meta["site"].rstrip("/")
    ops = jp_site._repo_ops(cfg)
    out: dict = {"ran": True}
    # 1) IndexNow key file at the site root
    key = _indexnow_key(db, site)
    key_path = f"{key}.txt"
    try:
        if ops["fetch"](key_path) is None:
            ops["commit"](key_path, key, "seo: IndexNow key (via Pulse)", False)
        out["indexnow_key"] = "ready"
    except Exception as e:  # noqa: BLE001
        out["indexnow_key"] = f"error: {str(e)[:80]}"
    # 2) llms.txt (GEO) + robots.txt (AEO)
    try:
        out["llms_txt"] = _ensure_file(ops, "llms.txt", build_llms_txt(site, now))
    except Exception as e:  # noqa: BLE001
        out["llms_txt"] = f"error: {str(e)[:80]}"
    try:
        robots = build_robots_txt(site, ops["fetch"]("robots.txt"))
        out["robots_txt"] = _ensure_file(ops, "robots.txt", robots)
    except Exception as e:  # noqa: BLE001
        out["robots_txt"] = f"error: {str(e)[:80]}"
    # 3) IndexNow ping — the day's new URLs + the always-refresh roots
    urls = list(dict.fromkeys((new_urls or []) + [
        f"{base}/", f"{base}/blog/", f"{base}/sitemap.xml"]))
    try:
        status = _HTTP_FN(INDEXNOW_ENDPOINT, {
            "host": _host(base), "key": key,
            "keyLocation": f"{base}/{key_path}", "urlList": urls})
        out["indexnow_ping"] = {"status": status, "urls": len(urls),
                                "ok": status in (200, 202)}
    except Exception as e:  # noqa: BLE001
        out["indexnow_ping"] = {"error": str(e)[:80]}
    return out


def run_daily(db: Session, now: datetime | None = None,
              new_urls_by_site: dict | None = None, *, force: bool = False) -> dict:
    """Heartbeat entry. Once/day per connected site. Harmless when no site is
    connected (every site returns not_connected) or the feature is disabled."""
    now = now or datetime.now(timezone.utc)
    cfg = get_config(db)
    if not force and not cfg["enabled"]:
        return {"ran": False, "reason": "disabled"}
    today = now.date().isoformat()
    results: dict = {}
    for site in SITES:
        if not force and cfg["last"].get(site) == today:
            results[site] = {"ran": False, "reason": "already_today"}
            continue
        try:
            r = run_for_site(db, site, now, (new_urls_by_site or {}).get(site))
        except Exception as e:  # noqa: BLE001
            db.rollback()
            r = {"ran": False, "error": str(e)[:150]}
        results[site] = r
        if r.get("ran"):
            cfg["last"][site] = today
            save_config(db, last=cfg["last"])
    return {"ran": True, "results": results}
